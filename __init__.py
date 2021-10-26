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

def get_houdini():
    f = open(os.path.join(os.getenv("APPDATA"),"PipelineSettings.JSON"))
    data = json.load(f)
    return data["software"]["houdini"]
HOUDINI = get_houdini()
TEMPDIR = tempfile.gettempdir()

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
        layout.operator(EdgeDamage.bl_idname, icon_value=custom_icons["houdini"].icon_id)
        layout.operator(CacheSelected.bl_idname, icon='FILE_TICK')
        layout.operator(ImportCached.bl_idname, icon='IMPORT')
        layout.menu(RelatedFiles.bl_idname)
        #layout.menu("TOPBAR_MT_help")

    def menu_draw(self, context):
        self.layout.menu("TOPBAR_MT_pipeline_menu")

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

class EdgeDamage(bpy.types.Operator):
    bl_idname = "object.edge_damage"
    bl_label = "Edge Damage"
    bl_description = "Caches Selected. Loads files in Houdini and sets up Edge Damage network"

    name : bpy.props.StringProperty(name="Object Name", default="")

    @classmethod
    def poll(self, context):
        return bpy.data.is_saved is True and bpy.context.selected_objects > 0
    
    def execute(self, context):
        cache_selected()
        addon_path = os.path.dirname(__file__)

        hip_path = bpy.data.filepath
        hip_path = os.path.dirname(hip_path)
        hip_path = os.path.join(hip_path,"houdini")
        os.makedirs(hip_path,exist_ok=True)
        hip_path = os.path.join(hip_path,self.name + ".hiplc")
        os.environ['HIP_PATH'] = hip_path

        subprocess.Popen([HOUDINI,os.path.join(addon_path,"houdini/edge_damage.py")])
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

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
    path: bpy.props.StringProperty(
        name="Texture Path",
        default="// ..\\textures\\",
        subtype="DIR_PATH",
        description="Define the path where to search for textures"
    )

class BuildMaterial(bpy.types.Operator):
    bl_idname = "object.build_material"
    bl_label = "Build Material"
    bl_description = "Find relevant textures based on material name in the textures folder and set up network"

    def execute(self, context):

        #get actuve nateruak name

        #import ue4 node

        #find texture in folder with specified suffix

        #create network
        print(context.scene.PipelineSettings.path)

        return {'FINISHED'}

class WORLD_PT_TexturePath(bpy.types.Panel):
    bl_label = "Pipeline"
    bl_idname = "WORLD_PT_TexturePath"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'material'
    path : bpy.props.StringProperty(name="Texture Path", subtype ="DIR_PATH")

    def draw(self, context):
        layout = self.layout
        layout.operator(BuildMaterial.bl_idname)
        layout.prop(context.scene.PipelineSettings, "path")

classes = (
    EdgeDamage,
    WORLD_PT_TexturePath,
    BuildMaterial,
    PipelineSettings,
    RelatedFiles,
    CacheSelected,
    ImportCached,
    TOPBAR_MT_pipeline_menu
)
def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.TOPBAR_MT_editor_menus.append(TOPBAR_MT_pipeline_menu.menu_draw)

    addon_path = os.path.dirname(__file__)
    icons_dir = os.path.join(addon_path,"icons")

    global custom_icons
    custom_icons = bpy.utils.previews.new()
    custom_icons.load("houdini",os.path.join(icons_dir,"Houdini3D_icon.png"),'IMAGE')

    bpy.types.Scene.PipelineSettings = bpy.props.PointerProperty(
        type=PipelineSettings)

def unregister():
    bpy.types.TOPBAR_MT_editor_menus.remove(TOPBAR_MT_pipeline_menu.menu_draw)
    for c in classes:
        bpy.utils.unregister_class(c)

if __name__ == "__main__":
    register()
