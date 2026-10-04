import bpy
import os
import re
import sys
import importlib

# Supported image extensions
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tga', '.exr', '.tif', '.tiff', '.bmp'}

# Regex patterns for matching texture suffixes
SUFFIX_PATTERNS = {
    'AORM': re.compile(r'^(.*?)[_.\-](AORM|AO_R_M|ARM|ORM)$', re.IGNORECASE),
    'NRAO': re.compile(r'^(.*?)[_.\-](NRAO|DN)$', re.IGNORECASE),
    'BC': re.compile(r'^(.*?)[_.\-](BC(?:_H)?|BaseColor|Base_Color|Albedo|Color)$', re.IGNORECASE),
    'N': re.compile(r'^(.*?)[_.\-](N|Normal|Norm)$', re.IGNORECASE),
}

# ------------------------------------------------------------------------
# Node Group Loader & Texture Node Helper
# ------------------------------------------------------------------------

def get_or_load_node_group(group_name):
    """
    Retrieves an existing node group by name or loads it from Pipeline.blend (or UE4.blend).
    Supports alias fallbacks (e.g., 'Height Blend Materials' <-> 'Height Blend Material').
    """
    if group_name in bpy.data.node_groups:
        return bpy.data.node_groups[group_name]

    fallbacks = [group_name]
    if 'Height Blend' in group_name:
        fallbacks = ['Height Blend Materials', 'Height Blend Material', 'Height Blend']
    elif 'Height Adjust' in group_name:
        fallbacks = ['Height Adjust']
    elif 'AORM' in group_name:
        fallbacks = ['Shader AORM']
    elif 'NRAO' in group_name:
        fallbacks = ['Shader NRAO']

    for alt in fallbacks:
        if alt in bpy.data.node_groups:
            return bpy.data.node_groups[alt]

    addon_dir = os.path.dirname(os.path.abspath(__file__))
    blend_files = [
        os.path.join(addon_dir, 'blend', 'Pipeline.blend')
    ]

    for b_path in blend_files:
        if not os.path.isfile(b_path):
            continue
        try:
            with bpy.data.libraries.load(b_path, link=False) as (data_from, data_to):
                to_load = []
                for ng in data_from.node_groups:
                    if ng in fallbacks or ng in {'smoothstep', 'smoothstep.001'}:
                        to_load.append(ng)
                data_to.node_groups = to_load
        except Exception:
            continue

        for alt in fallbacks:
            if alt in bpy.data.node_groups:
                return bpy.data.node_groups[alt]

    return None


def create_texture_node(nodes, image_path, colorspace='sRGB', location=(0, 0), alpha_mode=None):
    """Creates a ShaderNodeTexImage node and loads the texture."""
    tex_node = nodes.new("ShaderNodeTexImage")
    tex_node.location = location
    if image_path and os.path.isfile(image_path):
        img = bpy.data.images.load(image_path, check_existing=True)
        tex_node.image = img
        if hasattr(img, "colorspace_settings"):
            img.colorspace_settings.name = colorspace
        if alpha_mode and hasattr(img, "alpha_mode"):
            img.alpha_mode = alpha_mode
    return tex_node


# ------------------------------------------------------------------------
# Material Type Class Hierarchy
# ------------------------------------------------------------------------

class BaseMaterialType:
    """
    Abstract base class defining the procedure, validation, and network
    construction for a specific material workflow (e.g. AORM, NRAO).
    """
    id = ""
    name = ""
    description = ""
    shader_group_name = ""

    def is_valid_texture_set(self, textures):
        """Returns True if the scanned textures dict contains the required textures."""
        raise NotImplementedError

    def setup_textures_and_links(self, nodes, links, shader_node, textures, mat_name, y_pos=0):
        """
        Creates image texture nodes and connects them to the shader group inputs.
        Must return a dict containing at least {'bc_node': <node>}.
        """
        raise NotImplementedError

    def build_single_material(self, material, mat_name, textures):
        """Builds a standalone single-material shader network."""
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        nodes.clear()

        # Material Output
        mat_output = nodes.new("ShaderNodeOutputMaterial")
        mat_output.location = (600, 0)
        mat_output.is_active_output = True

        # Shader Group Node
        shader_group = get_or_load_node_group(self.shader_group_name)
        if not shader_group:
            raise ValueError(f"Could not load shader group '{self.shader_group_name}'")

        shader_node = nodes.new("ShaderNodeGroup")
        shader_node.node_tree = shader_group
        shader_node.location = (250, 0)

        # Connect BSDF to Material Output
        bsdf_socket = shader_node.outputs.get("BSDF", shader_node.outputs[0])
        links.new(bsdf_socket, mat_output.inputs["Surface"])

        # Setup textures & connections
        self.setup_textures_and_links(nodes, links, shader_node, textures, mat_name, y_pos=0)

    def build_layer(self, nodes, links, mat_name, textures, height_adjust_group, y_pos):
        """
        Builds a single layer (Shader group + Textures + Height Adjust) for blending.
        Returns a dict: {'name': mat_name, 'shader': s_node, 'height_adjust': ha_node, 'y_pos': y_pos}
        """
        shader_group = get_or_load_node_group(self.shader_group_name)
        if not shader_group:
            raise ValueError(f"Could not load shader group '{self.shader_group_name}'")

        # 1. Shader Group Node
        s_node = nodes.new("ShaderNodeGroup")
        s_node.node_tree = shader_group
        s_node.label = f"{mat_name} ({self.shader_group_name})"
        s_node.location = (0, y_pos)

        # 2. Textures and Links to Shader
        tex_nodes = self.setup_textures_and_links(nodes, links, s_node, textures, mat_name, y_pos)
        bc_node = tex_nodes.get('bc_node')

        # 3. Height Adjust Node fed from Base Color Alpha
        ha_node = nodes.new("ShaderNodeGroup")
        ha_node.node_tree = height_adjust_group
        ha_node.label = f"{mat_name} Height Adjust"
        ha_node.location = (0, y_pos - 320)

        if bc_node:
            links.new(bc_node.outputs["Alpha"], ha_node.inputs["Height"])

        return {
            'name': mat_name,
            'shader': s_node,
            'height_adjust': ha_node,
            'y_pos': y_pos
        }


class AORMMaterialType(BaseMaterialType):
    """AORM Material Workflow (Base Color, Normal, Ambient Occlusion / Roughness / Metallic)."""
    id = "AORM"
    name = "AORM"
    description = "Build AORM Material (Base Color, Normal, AO_R_M)"
    shader_group_name = "Shader AORM"

    def is_valid_texture_set(self, textures):
        return 'AORM' in textures

    def setup_textures_and_links(self, nodes, links, shader_node, textures, mat_name, y_pos=0):
        tex_nodes = {}

        # Base Color (Always Channel Packed)
        bc_path = textures.get('BC')
        bc_node = create_texture_node(
            nodes, bc_path, colorspace='sRGB', location=(-350, y_pos + 150), alpha_mode='CHANNEL_PACKED'
        )
        bc_node.label = f"{mat_name} BC"
        links.new(bc_node.outputs["Color"], shader_node.inputs["Base Color"])
        tex_nodes['bc_node'] = bc_node

        # Normal
        n_path = textures.get('N')
        if n_path:
            n_node = create_texture_node(nodes, n_path, colorspace='Non-Color', location=(-350, y_pos - 100))
            n_node.label = f"{mat_name} Normal"
            links.new(n_node.outputs["Color"], shader_node.inputs["Normal"])
            tex_nodes['n_node'] = n_node

        # AORM
        aorm_path = textures.get('AORM')
        if aorm_path:
            aorm_node = create_texture_node(
                nodes, aorm_path, colorspace='Non-Color', location=(-350, y_pos - 350), alpha_mode='CHANNEL_PACKED'
            )
            aorm_node.label = f"{mat_name} AORM"
            links.new(aorm_node.outputs["Color"], shader_node.inputs["AO R M"])
            tex_nodes['aorm_node'] = aorm_node

        return tex_nodes


class NRAOMaterialType(BaseMaterialType):
    """NRAO Material Workflow (Base Color, Normal/Roughness/AmbientOcclusion packed)."""
    id = "NRAO"
    name = "NRAO"
    description = "Build NRAO Material (Base Color, NRAO packed)"
    shader_group_name = "Shader NRAO"

    def is_valid_texture_set(self, textures):
        return 'NRAO' in textures

    def setup_textures_and_links(self, nodes, links, shader_node, textures, mat_name, y_pos=0):
        tex_nodes = {}

        # Base Color (Always Channel Packed)
        bc_path = textures.get('BC')
        bc_node = create_texture_node(
            nodes, bc_path, colorspace='sRGB', location=(-350, y_pos + 150), alpha_mode='CHANNEL_PACKED'
        )
        bc_node.label = f"{mat_name} BC"
        links.new(bc_node.outputs["Color"], shader_node.inputs["BC"])
        tex_nodes['bc_node'] = bc_node

        # NRAO
        nrao_path = textures.get('NRAO')
        if nrao_path:
            nrao_node = create_texture_node(
                nodes, nrao_path, colorspace='Non-Color', location=(-350, y_pos - 100), alpha_mode='CHANNEL_PACKED'
            )
            nrao_node.label = f"{mat_name} NRAO"
            links.new(nrao_node.outputs["Color"], shader_node.inputs["NRAO.rgb"])
            links.new(nrao_node.outputs["Alpha"], shader_node.inputs["NRAO.a"])
            tex_nodes['nrao_node'] = nrao_node

        return tex_nodes


# ------------------------------------------------------------------------
# Material Type Registry & Factory
# ------------------------------------------------------------------------

MATERIAL_REGISTRY = {
    'AORM': AORMMaterialType(),
    'NRAO': NRAOMaterialType(),
}

MATERIAL_TYPE_ENUM_ITEMS = [
    (m.id, m.name, m.description) for m in MATERIAL_REGISTRY.values()
]

def get_material_type(type_id):
    """Retrieve material type handler instance by ID, defaulting to AORM."""
    return MATERIAL_REGISTRY.get(type_id, MATERIAL_REGISTRY['AORM'])

def get_material_type_enum_items(self=None, context=None):
    """Dynamically returns EnumProperty items from the registry."""
    return [(m.id, m.name, m.description) for m in MATERIAL_REGISTRY.values()]


# ------------------------------------------------------------------------
# High-Level Build & Scan APIs
# ------------------------------------------------------------------------

def scan_texture_directory(textures_path, material_type='AORM'):
    """
    Scans a folder for texture files and groups them by material name.
    Uses the MaterialType class to validate texture requirements.
    """
    if not textures_path:
        return {}

    abs_path = os.path.normpath(bpy.path.abspath(textures_path))
    if not os.path.isdir(abs_path):
        return {}

    materials = {}

    try:
        filenames = os.listdir(abs_path)
    except OSError:
        return {}

    for fname in filenames:
        ext = os.path.splitext(fname)[1].lower()
        if ext not in IMAGE_EXTENSIONS:
            continue

        stem = os.path.splitext(fname)[0]
        full_path = os.path.join(abs_path, fname)

        # Check against suffix patterns
        matched = False
        for role, pattern in SUFFIX_PATTERNS.items():
            match = pattern.match(stem)
            if match:
                mat_name = match.group(1)
                if mat_name not in materials:
                    materials[mat_name] = {}
                materials[mat_name][role] = full_path
                matched = True
                break

    # Filter materials polymorphically using the material type class
    handler = get_material_type(material_type)
    return {
        mat_name: textures
        for mat_name, textures in materials.items()
        if handler.is_valid_texture_set(textures)
    }


def build_single_material_network(material, mat_name, textures, material_type='AORM'):
    """Delegates single material construction to the respective MaterialType class."""
    handler = get_material_type(material_type)
    handler.build_single_material(material, mat_name, textures)


def build_blended_material_network(material, selected_materials, all_textures, material_type='AORM', active_obj=None):
    """
    Builds a blended material network using the Height Blend Materials node group from Pipeline.blend.
    Connects the active object's Color Attribute Alpha to the 'Weight' socket.
    Uses the MaterialType class to construct each material's layer polymorphically.
    """
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    # Material Output
    mat_output = nodes.new("ShaderNodeOutputMaterial")
    mat_output.is_active_output = True

    handler = get_material_type(material_type)
    height_adjust_group = get_or_load_node_group("Height Adjust")
    height_blend_materials_group = get_or_load_node_group("Height Blend Materials") or get_or_load_node_group("Height Blend Material")

    if not height_adjust_group or not height_blend_materials_group:
        raise ValueError("Could not load required node groups (Height Adjust, Height Blend Materials) from Pipeline.blend")

    # Detect active Color Attribute on the active/selected object
    active_color_name = ""
    if active_obj and active_obj.type == 'MESH' and active_obj.data:
        mesh = active_obj.data
        if hasattr(mesh, "color_attributes"):
            active_color = mesh.color_attributes.active_color
            if active_color:
                active_color_name = active_color.name
            elif len(mesh.color_attributes) > 0:
                active_color_name = mesh.color_attributes[0].name

    # Create Color Attribute node
    vcol_node = nodes.new("ShaderNodeVertexColor")
    if active_color_name:
        vcol_node.layer_name = active_color_name
        vcol_node.label = f"Color Attribute ({active_color_name})"
    else:
        vcol_node.label = "Color Attribute (Active)"
    vcol_node.location = (200, 250)

    # Build layers for each material using the MaterialType handler
    layers = []
    y_spacing = 750

    for idx, mat_name in enumerate(selected_materials):
        y_pos = -idx * y_spacing
        textures = all_textures.get(mat_name, {})
        layer = handler.build_layer(nodes, links, mat_name, textures, height_adjust_group, y_pos)
        layers.append(layer)

    # Blend layers together using Height Blend Materials node
    current_shader_output = layers[0]['shader'].outputs["BSDF"]
    current_height_output = layers[0]['height_adjust'].outputs["Return"]

    x_blend_offset = 450

    for idx in range(1, len(layers)):
        next_layer = layers[idx]
        blend_y = (layers[idx - 1]['y_pos'] + next_layer['y_pos']) / 2.0

        # Height Blend Materials Node
        hbm_node = nodes.new("ShaderNodeGroup")
        hbm_node.node_tree = height_blend_materials_group
        hbm_node.label = f"Blend {layers[idx - 1]['name']} -> {next_layer['name']}"
        hbm_node.location = (x_blend_offset + (idx - 1) * 350, blend_y)

        # Connect Color Attribute Alpha to Weight socket
        links.new(vcol_node.outputs["Alpha"], hbm_node.inputs["Weight"])

        # Connect Shaders: bottom is previous layer, top is next layer
        links.new(current_shader_output, hbm_node.inputs["Shader Bottom"])
        links.new(next_layer['shader'].outputs["BSDF"], hbm_node.inputs["Shader Top"])

        # Connect Heights: bottom is previous layer, top is next layer
        links.new(current_height_output, hbm_node.inputs["Height Bottom"])
        links.new(next_layer['height_adjust'].outputs["Return"], hbm_node.inputs["Height Top"])

        current_shader_output = hbm_node.outputs["Shader"]
        current_height_output = hbm_node.outputs["Height"]

    mat_output.location = (x_blend_offset + (len(layers) - 1) * 350 + 250, 0)
    links.new(current_shader_output, mat_output.inputs["Surface"])


def reload_addon_modules():
    """
    Reloads all modules of the pipeline_tools addon and re-registers classes.
    """
    pkg_name = __package__ or __name__.split('.')[0]
    reloaded = []

    root_mod = sys.modules.get(pkg_name)
    if root_mod and hasattr(root_mod, "unregister"):
        try:
            root_mod.unregister()
        except Exception:
            pass

    utils_mod_name = f"{pkg_name}.utils"
    if utils_mod_name in sys.modules:
        importlib.reload(sys.modules[utils_mod_name])
        reloaded.append(utils_mod_name)
    elif "utils" in sys.modules:
        importlib.reload(sys.modules["utils"])
        reloaded.append("utils")

    if root_mod:
        importlib.reload(root_mod)
        reloaded.append(pkg_name)
        if hasattr(root_mod, "register"):
            root_mod.register()

    return reloaded
