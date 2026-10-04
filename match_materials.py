
import bpy


def match_materials():
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

match_materials()