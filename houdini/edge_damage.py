import hou
import os

file_paths = os.environ.get('CACHED_FILES')
file_paths = open(file_paths)
file_paths = file_paths.readlines()
file_paths = [x[0:-1] for x in file_paths] #strip \n character

hip_path = os.environ.get("HIP_PATH")
hou.hipFile.save(hip_path)

geo = hou.node("/obj").createNode("geo")
merge = geo.createNode("merge")

i = 0
for file in file_paths:
    # create attribute create
    attribcreate = geo.createNode('attribcreate')
    attribcreate.parm('name1').set('class')
    attribcreate.parm('value1v1').set(i)
    attribcreate.parm('class1').set('primitive')
    attribcreate.parm('type1').set('int')


    # create file node
    file_node = geo.createNode("file")
    file_node.parm('file').set(file)
    file_node.setHardLocked(True)

    # connect nodes
    merge.setNextInput(attribcreate,0)
    attribcreate.setNextInput(file_node,0)

    i += 1

edge_damage = geo.createNode("edge_damage")
edge_damage.setNextInput(merge,0)

# create generate bake geometry node
bake_geo = geo.createNode("generate_bake_geometry")
bake_geo.setNextInput(edge_damage,0)


geo.layoutChildren()
