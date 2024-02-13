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
import subprocess
import os
import tempfile
import json

"""
def get_houdini():
    f = open(os.path.join(os.getenv("APPDATA"),"PipelineSettings.JSON"))
    data = json.load(f)
    return data["software"]["houdini"]
HOUDINI = get_houdini()
TEMPDIR = tempfile.gettempdir()
"""

bl_info = {
    "name" : "Pipeline Tools",
    "author" : "Yianni Papazis",
    "description" : "",
    "blender" : (2, 90, 0),
    "version" : (0, 0, 1),
    "location" : "",
    "warning" : "",
    "category" : "Generic"
}

class TOPBAR_MT_pipeline_menu(bpy.types.Menu):
    #bl_idname = "view3d.menuname"
    bl_label = "Pipeline"

    def draw(self, context):
        layout = self.layout
        #layout.operator(EdgeDamage.bl_idname, icon_value=custom_icons["houdini"].icon_id)
        #layout.operator(CacheSelected.bl_idname, icon='FILE_TICK')
        #layout.operator(ImportCached.bl_idname, icon='IMPORT')
        layout.menu(RelatedFiles.bl_idname)
        layout.operator(MatchMaterials.bl_idname, icon='MATERIAL')
        #layout.menu("TOPBAR_MT_help")

    def menu_draw(self, context):
        self.layout.menu("TOPBAR_MT_pipeline_menu")

"""
def cache_selected():
        folder_path = bpy.data.filepath
        folder_path = folder_path.replace("\\", "/")
        folder_path = folder_path[0:folder_path.rfind("/")]
        folder_path = folder_path + '/cache/'

        try:
            os.makedirs(folder_path)
        except FileExistsError:
            pass

        selected_objects = bpy.context.selected_objects

        data_path = os.path.join(TEMPDIR,'cached_files.txt')

        f = open(data_path,"w+")
        f.truncate(0)
        
        for obj in selected_objects:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            file_dir = folder_path + obj.name + '.obj'
            f.write(file_dir + '\n')        

            bpy.ops.export_scene.obj(filepath = file_dir, use_selection = True)

        f.close()

        os.environ['CACHED_FILES'] = data_path
"""


"""
class ImportCached(bpy.types.Operator):
    bl_idname = "object.importcached"
    bl_label = "Import Cached"
    path = os.path.join(TEMPDIR, 'houdini_temp', 'cache.fbx')

    @classmethod
    def poll(self, context):
        return os.path.exists(path) is True

    def execute(self, context):
        bpy.ops.import_scene.fbx(filepath=self.path, global_scale=100)
        return {'FINISHED'}

"""

class RelatedFiles(bpy.types.Menu):
    bl_label = "Related Files"
    bl_idname = "TOPBAR_MT_relatedFiles"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Files")

        #get file path

        if bpy.data.is_saved is not True:
            return
        else:
            path = bpy.data.filepath
            path = path[0:path.rfind('\\')+1]


        #search files

        #specify relevant types

        types = (
            "blend",
            "hip",
            "spp"
        )

        files = os.listdir(path)
        unique_files = []
        for f in files:
            type = f.split('.')[-1]
            if type not in types:
                pass
            else:
                unique_name = f.split('.')[0]
                if unique_name not in unique_files:
                    unique_files.append(unique_name)
        print(unique_files)

            

        #filter files

        #organise files

        #spawn into menus   

class CacheSelected(bpy.types.Operator):
    bl_idname = "object.cache_selected"
    bl_label = "Cache Selected"

    @classmethod
    def poll(self, context):
        return bpy.data.is_saved is True

    def execute(self, context):
        cache_selected()
        return {'FINISHED'}

class PipelineSettings(bpy.types.PropertyGroup):
    texture_path: bpy.props.StringProperty(
        name="Texture Path",
        default="//..\\textures\\",
        subtype="DIR_PATH",
        description="Define the path where to search for textures"
    )

class BuildMaterial(bpy.types.Operator):
    bl_idname = "object.build_material"
    bl_label = "Build Material"
    bl_description = "Find relevant textures based on material name in the textures folder and set up network"

    def execute(self, context):

        # get material name
        active_material = context.active_object.active_material
        name = active_material.name

        # search folder
        textures_path = os.path.normpath(bpy.path.abspath(
            context.scene.PipelineSettings.texture_path))
        
        dir = os.listdir(textures_path)
        files = [file for file in dir if file.startswith(name)]

        nodes = active_material.node_tree.nodes
        links = active_material.node_tree.links

        #import ue4 node

        object_name = "Shader"

        try:
            material_output = nodes['Material Output']
        except KeyError:
            material_output = nodes.new("ShaderNodeOutputMaterial")
        
        # set all material outputs to inactive
        for node in nodes:
            if node.type == "OUTPUT_MATERIAL":
                node.is_active_output = False
        
        material_output.is_active_output = True
        
        
        shader_group = bpy.data.node_groups.get(object_name)
        if not shader_group:
            blend_path = os.path.join(
                os.path.dirname(__file__), "blend", "UE4.blend")
            inner_name = "NodeTree"
            node = bpy.ops.wm.append(
                filepath=os.path.join(blend_path, inner_name, object_name),
                directory=os.path.join(blend_path, inner_name),
                filename=object_name
            )
            shader_group = bpy.data.node_groups.get(object_name)
        
        shader_group = nodes.new("ShaderNodeGroup")
        shader_group.node_tree = bpy.data.node_groups[object_name]

        for file in files:
            tex_path = os.path.join(textures_path,file)
            tex_node = nodes.new("ShaderNodeTexImage")
            tex = bpy.data.images.load(tex_path, check_existing=True)
            tex_node.image = tex

            name = file.rsplit('.')[0]
            if name.endswith('_BC'):
                links.new(tex_node.outputs[0],shader_group.inputs[0])
                tex_node.image.colorspace_settings.name = "sRGB"
                pass
            elif name.endswith('_AO_R_M'):
                links.new(tex_node.outputs[0],shader_group.inputs[2])
                tex_node.image.colorspace_settings.name = "Non-Color"
                pass
            elif name.endswith('_N'):
                links.new(tex_node.outputs[0], shader_group.inputs[1])
                tex_node.image.colorspace_settings.name = "Non-Color"
                pass
        
        links.new(shader_group.outputs[0], material_output.inputs[0])

        return {'FINISHED'}

class MatchMaterials(bpy.types.Operator):
    bl_idname = "object.match_material"
    bl_label = "Match Materials"
    bl_description = "Match duplicate materials with materials in scene"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):

        objects = bpy.context.selected_objects
        objects = [obj for obj in objects if obj.type == 'MESH']

        for obj in objects:
            for i, slot in enumerate(obj.material_slots):
                name = slot.material.name
                if "." in name:
                    name = name[0:name.rfind(".")]
                    if name in bpy.data.materials:
                        mat = bpy.data.materials[name]
                        obj.material_slots[i].material = mat
        
        return {"FINISHED"}

class WORLD_PT_TexturePath(bpy.types.Panel):
    bl_label = "Pipeline"
    bl_idname = "WORLD_PT_TexturePath"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'material'
    texture_path : bpy.props.StringProperty(name="Texture Path", subtype ="DIR_PATH")

    def draw(self, context):
        layout = self.layout
        layout.operator(BuildMaterial.bl_idname)
        layout.prop(context.scene.PipelineSettings, "texture_path")

classes = (
    WORLD_PT_TexturePath,
    BuildMaterial,
    PipelineSettings,
    RelatedFiles,
    #CacheSelected,
    #ImportCached,
    TOPBAR_MT_pipeline_menu,
    MatchMaterials,
)
def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.TOPBAR_MT_editor_menus.append(TOPBAR_MT_pipeline_menu.menu_draw)

    bpy.types.MATERIAL_MT_context_menu.append(MatchMaterials)

    addon_path = os.path.dirname(__file__)
    icons_dir = os.path.join(addon_path,"icons")

    global custom_icons
    custom_icons = bpy.utils.previews.new()
    custom_icons.load("houdini",os.path.join(icons_dir,"Houdini3D_icon.png"),'IMAGE')

    bpy.types.Scene.PipelineSettings = bpy.props.PointerProperty(
        type=PipelineSettings)

def unregister():
    bpy.types.TOPBAR_MT_editor_menus.remove(TOPBAR_MT_pipeline_menu.menu_draw)

    bpy.types.MATERIAL_MT_context_menu.remove(MatchMaterials)
    for c in classes:
        bpy.utils.unregister_class(c)

if __name__ == "__main__":
    register()
