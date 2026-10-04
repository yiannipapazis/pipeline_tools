# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import bpy
import bpy.utils.previews
import subprocess
import os
import tempfile
import json
import importlib

if "bpy" in locals() and "utils" in locals():
    importlib.reload(utils)
else:
    try:
        from . import utils
    except ImportError:
        import utils

def get_houdini():
    json_path = os.path.join(os.getenv("APPDATA", ""), "PipelineSettings.JSON")
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            data = json.load(f)
            return data.get("software", {}).get("houdini", "")
    return ""

TEMPDIR = tempfile.gettempdir()

bl_info = {
    "name": "Pipeline Tools",
    "author": "Yianni Papazis",
    "description": "Pipeline asset and material management tools",
    "blender": (5, 1, 0),
    "version": (0, 1, 0),
    "location": "View3D > Topbar & Material Properties",
    "warning": "",
    "category": "Generic"
}

# ------------------------------------------------------------------------
# UI List and Settings
# ------------------------------------------------------------------------

class MaterialItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Material Name")
    selected: bpy.props.BoolProperty(name="Selected", default=False)

def update_texture_list(self, context):
    refresh_materials_list(self)

def refresh_materials_list(settings):
    if not settings:
        return
    textures_path = getattr(settings, "texture_path", "")
    mat_type = getattr(settings, "material_type", "AORM")

    found = utils.scan_texture_directory(textures_path, mat_type)

    # Preserve currently selected item names
    selected_names = {item.name for item in settings.materials if item.selected}

    settings.materials.clear()
    for mat_name in sorted(found.keys()):
        item = settings.materials.add()
        item.name = mat_name
        item.selected = (mat_name in selected_names)

class PipelineSettings(bpy.types.PropertyGroup):
    texture_path: bpy.props.StringProperty(
        name="Texture Path",
        default="//../textures/",
        subtype="DIR_PATH",
        options={'PATH_SUPPORTS_BLEND_RELATIVE'},
        description="Path where to search for textures",
        update=update_texture_list
    )

    material_type: bpy.props.EnumProperty(
        items=utils.MATERIAL_TYPE_ENUM_ITEMS,
        name="Material Type",
        description="The type of material to create (filters texture sets)",
        default="AORM",
        update=update_texture_list
    )

    materials: bpy.props.CollectionProperty(type=MaterialItem)
    active_material_index: bpy.props.IntProperty(name="Active Index", default=0)
    search_filter: bpy.props.StringProperty(
        name="Filter",
        description="Filter material list by name",
        default=""
    )

class PIPELINE_UL_MaterialList(bpy.types.UIList):
    """Searchable material list UI with selection checkboxes"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(item, "selected", text="")
            row.label(text=item.name, icon='MATERIAL')
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=item.name, icon='MATERIAL')

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        flt_flags = [self.bitflag_filter_item] * len(items)
        flt_neworder = []

        # Use UIList built-in search filter or the search_filter property
        filter_text = self.filter_name
        settings = getattr(context.scene, "PipelineSettings", None)
        if not filter_text and settings and settings.search_filter:
            filter_text = settings.search_filter

        if filter_text:
            flt_flags = bpy.types.UI_UL_list.filter_items_by_name(
                filter_text, self.bitflag_filter_item, items, "name",
                reverse=False
            )

        return flt_flags, flt_neworder

# ------------------------------------------------------------------------
# Operators
# ------------------------------------------------------------------------

class PIPELINE_OT_RefreshTextures(bpy.types.Operator):
    bl_idname = "pipeline.refresh_textures"
    bl_label = "Refresh Textures"
    bl_description = "Scan the texture folder and refresh the list based on Material Type"

    def execute(self, context):
        settings = context.scene.PipelineSettings
        refresh_materials_list(settings)
        count = len(settings.materials)
        self.report({'INFO'}, f"Found {count} matching {settings.material_type} materials")
        return {'FINISHED'}

class PIPELINE_OT_SelectAllMaterials(bpy.types.Operator):
    bl_idname = "pipeline.select_all_materials"
    bl_label = "Select All"
    bl_description = "Select or deselect all materials in the list"

    action: bpy.props.EnumProperty(
        items=[
            ('SELECT', "Select All", ""),
            ('DESELECT', "Deselect All", "")
        ],
        default='SELECT'
    )

    def execute(self, context):
        state = (self.action == 'SELECT')
        for item in context.scene.PipelineSettings.materials:
            item.selected = state
        return {'FINISHED'}

class PIPELINE_OT_ReloadOperators(bpy.types.Operator):
    bl_idname = "pipeline.reload_operators"
    bl_label = "Reload Operators"
    bl_description = "Reload Pipeline Tools modules and re-register without restarting Blender"

    def execute(self, context):
        try:
            reloaded = utils.reload_addon_modules()
            # Also re-import into this module
            importlib.reload(utils)
            self.report({'INFO'}, f"Pipeline Tools reloaded: {', '.join(reloaded) if reloaded else 'Done'}")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to reload: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}

class BuildMaterial(bpy.types.Operator):
    bl_idname = "object.build_material"
    bl_label = "Build Material"
    bl_description = "Build single material or blended shader network from selected textures"

    def execute(self, context):
        settings = context.scene.PipelineSettings
        textures_path = os.path.normpath(bpy.path.abspath(settings.texture_path))
        mat_type = settings.material_type

        # Find matching textures
        available = utils.scan_texture_directory(textures_path, mat_type)
        if not available:
            self.report({'WARNING'}, f"No valid {mat_type} texture sets found in '{textures_path}'")
            return {'CANCELLED'}

        # Get user-selected materials (checkboxes)
        selected_mats = [item.name for item in settings.materials if item.selected and item.name in available]

        # If none selected with checkboxes, fallback to active item in the UIList
        if not selected_mats:
            if 0 <= settings.active_material_index < len(settings.materials):
                active_item = settings.materials[settings.active_material_index]
                if active_item.name in available:
                    selected_mats = [active_item.name]

        if not selected_mats:
            self.report({'WARNING'}, "No material selected. Please select at least one material in the list.")
            return {'CANCELLED'}

        # Ensure active material exists
        active_obj = context.active_object
        if active_obj:
            if not active_obj.active_material:
                active_material = bpy.data.materials.new(name=f"M_{selected_mats[0]}")
                active_obj.active_material = active_material
            else:
                active_material = active_obj.active_material
        else:
            active_material = bpy.data.materials.new(name=f"M_{selected_mats[0]}")

        try:
            if len(selected_mats) == 1:
                mat_name = selected_mats[0]
                active_material.name = f"M_{mat_name}_{mat_type}"
                utils.build_single_material_network(
                    active_material,
                    mat_name,
                    available[mat_name],
                    material_type=mat_type
                )
                self.report({'INFO'}, f"Built single {mat_type} material for '{mat_name}'")
            else:
                blend_name = f"M_{'_'.join(selected_mats[:2])}_Blend"
                active_material.name = blend_name
                utils.build_blended_material_network(
                    active_material,
                    selected_mats,
                    available,
                    material_type=mat_type,
                    active_obj=active_obj
                )
                self.report({'INFO'}, f"Built blended {mat_type} material for {len(selected_mats)} materials")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to build material: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}

# ------------------------------------------------------------------------
# Pipeline Menu & Legacy Operators
# ------------------------------------------------------------------------

def cache_selected():
    folder_path = bpy.data.filepath
    if not folder_path:
        return
    folder_path = folder_path.replace("\\", "/")
    folder_path = folder_path[0:folder_path.rfind("/")] + '/export/'

    try:
        os.makedirs(folder_path, exist_ok=True)
    except OSError:
        pass

    selected_objects = bpy.context.selected_objects
    data_path = os.path.join(TEMPDIR, 'cached_files.txt')

    with open(data_path, "w") as f:
        for obj in selected_objects:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            file_dir = folder_path + obj.name + '.obj'
            f.write(file_dir + '\n')
            bpy.ops.export_scene.obj(filepath=file_dir, use_selection=True)

class CacheSelected(bpy.types.Operator):
    bl_idname = "object.cache_selected"
    bl_label = "Cache Selected"

    @classmethod
    def poll(cls, context):
        return bpy.data.is_saved is True

    def execute(self, context):
        cache_selected()
        return {'FINISHED'}

class EdgeDamage(bpy.types.Operator):
    bl_idname = "object.edge_damage"
    bl_label = "Edge Damage"
    bl_description = "Caches Selected. Loads files in Houdini and sets up Edge Damage network"

    name: bpy.props.StringProperty(name="Object Name", default="")

    @classmethod
    def poll(cls, context):
        return bpy.data.is_saved is True and len(bpy.context.selected_objects) > 0

    def execute(self, context):
        houdini_bin = get_houdini()
        if not houdini_bin:
            self.report({'WARNING'}, "Houdini path not configured in PipelineSettings.JSON")
            return {'CANCELLED'}

        cache_selected()
        addon_path = os.path.dirname(__file__)

        hip_path = bpy.data.filepath
        hip_path = os.path.dirname(hip_path)
        hip_path = os.path.join(hip_path, "houdini")
        os.makedirs(hip_path, exist_ok=True)
        hip_path = os.path.join(hip_path, self.name + ".hiplc")
        os.environ['HIP_PATH'] = hip_path

        subprocess.Popen([houdini_bin, os.path.join(addon_path, "houdini/edge_damage.py")])
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

class ImportCached(bpy.types.Operator):
    bl_idname = "object.importcached"
    bl_label = "Import Cached"

    @classmethod
    def poll(cls, context):
        path = os.path.join(tempfile.gettempdir(), 'cache.fbx')
        return os.path.exists(path)

    def execute(self, context):
        path = os.path.join(tempfile.gettempdir(), 'cache.fbx')
        bpy.ops.import_scene.fbx(filepath=path, global_scale=100)
        return {'FINISHED'}

class RelatedFiles(bpy.types.Menu):
    bl_label = "Related Files"
    bl_idname = "TOPBAR_MT_relatedFiles"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Files")

        if not bpy.data.is_saved:
            return

        path = bpy.data.filepath
        path = path[0:path.rfind('\\')+1]
        types = ("blend", "hip", "spp")

        if not os.path.isdir(path):
            return

        files = os.listdir(path)
        unique_files = []
        for f in files:
            ftype = f.split('.')[-1]
            if ftype in types:
                unique_name = f.split('.')[0]
                if unique_name not in unique_files:
                    unique_files.append(unique_name)
                    layout.label(text=unique_name)

class TOPBAR_MT_pipeline_menu(bpy.types.Menu):
    bl_label = "Pipeline"

    def draw(self, context):
        layout = self.layout
        icon_id = custom_icons["houdini"].icon_id if "houdini" in custom_icons else 0
        layout.operator(EdgeDamage.bl_idname, icon_value=icon_id)
        layout.operator(CacheSelected.bl_idname, icon='FILE_TICK')
        layout.operator(ImportCached.bl_idname, icon='IMPORT')
        layout.menu(RelatedFiles.bl_idname)
        layout.separator()
        layout.operator("pipeline.reload_operators", icon='FILE_REFRESH')

    def menu_draw(self, context):
        self.layout.menu("TOPBAR_MT_pipeline_menu")

# ------------------------------------------------------------------------
# UI Panel
# ------------------------------------------------------------------------

class WORLD_PT_TexturePath(bpy.types.Panel):
    bl_label = "Pipeline"
    bl_idname = "WORLD_PT_TexturePath"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'material'

    def draw(self, context):
        layout = self.layout
        settings = context.scene.PipelineSettings

        # Directory & Type Configuration
        box = layout.box()
        box.prop(settings, "texture_path")
        box.prop(settings, "material_type")

        # Material List Header Controls
        header = box.row(align=True)
        header.prop(settings, "search_filter", text="", icon='VIEWZOOM')
        header.operator("pipeline.refresh_textures", text="", icon='FILE_REFRESH')
        op_sel = header.operator("pipeline.select_all_materials", text="", icon='CHECKBOX_HLT')
        op_sel.action = 'SELECT'
        op_desel = header.operator("pipeline.select_all_materials", text="", icon='CHECKBOX_DEHLT')
        op_desel.action = 'DESELECT'

        # Searchable UIList with Multi-select Checkboxes
        box.template_list(
            "PIPELINE_UL_MaterialList",
            "",
            settings,
            "materials",
            settings,
            "active_material_index",
            rows=6
        )

        selected_count = sum(1 for m in settings.materials if m.selected)
        if selected_count > 1:
            box.label(text=f"{selected_count} materials selected (Height Blended)", icon='INFO')
        elif selected_count == 1:
            box.label(text="1 material selected (Single Shader)", icon='INFO')
        else:
            box.label(text="Select checkbox(es) or active item", icon='INFO')

        # Build Material Action
        btn_row = layout.row(align=True)
        btn_row.scale_y = 1.3
        btn_row.operator(BuildMaterial.bl_idname, text="Build Material", icon='MATERIAL')

        # Quick Reload Button
        reload_row = layout.row()
        reload_row.operator("pipeline.reload_operators", text="Reload Operators", icon='FILE_REFRESH')

# ------------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------------

classes = (
    MaterialItem,
    PipelineSettings,
    PIPELINE_UL_MaterialList,
    PIPELINE_OT_RefreshTextures,
    PIPELINE_OT_SelectAllMaterials,
    PIPELINE_OT_ReloadOperators,
    BuildMaterial,
    CacheSelected,
    EdgeDamage,
    ImportCached,
    RelatedFiles,
    TOPBAR_MT_pipeline_menu,
    WORLD_PT_TexturePath,
)

custom_icons = None

def register():
    global custom_icons

    for c in classes:
        bpy.utils.register_class(c)

    bpy.types.TOPBAR_MT_editor_menus.append(TOPBAR_MT_pipeline_menu.menu_draw)

    addon_path = os.path.dirname(__file__)
    icons_dir = os.path.join(addon_path, "icons")

    custom_icons = bpy.utils.previews.new()
    icon_file = os.path.join(icons_dir, "Houdini3D_icon.png")
    if os.path.exists(icon_file):
        custom_icons.load("houdini", icon_file, 'IMAGE')

    bpy.types.Scene.PipelineSettings = bpy.props.PointerProperty(type=PipelineSettings)

def unregister():
    global custom_icons

    try:
        bpy.types.TOPBAR_MT_editor_menus.remove(TOPBAR_MT_pipeline_menu.menu_draw)
    except Exception:
        pass

    if hasattr(bpy.types.Scene, "PipelineSettings"):
        del bpy.types.Scene.PipelineSettings

    if custom_icons is not None:
        try:
            bpy.utils.previews.remove(custom_icons)
        except Exception:
            pass
        custom_icons = None

    for c in reversed(classes):
        try:
            bpy.utils.unregister_class(c)
        except RuntimeError:
            pass

if __name__ == "__main__":
    register()
