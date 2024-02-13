import bpy
objects = bpy.context.selected_objects

for obj in objects:
    bpy.context.view_layer.objects.active = obj
    if obj.type == 'MESH':
        bpy.ops.mesh.customdata_custom_splitnormals_clear()