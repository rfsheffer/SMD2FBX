import fbx
import sys
import os
from fbx_helpers import save_scene, create_texture


class Polygon:
    def __init__(self):
        self.indicies = []
        self.texture = ''
        self.uvs = []
        self.normals = []


class Vertex:
    class CompSplit:
        def __init__(self, comps):
            comp_len = len(comps)
            self.x = comps[0] if comp_len > 0 else 0
            self.y = comps[1] if comp_len > 1 else 0
            self.z = comps[2] if comp_len > 2 else 0
            self.w = comps[3] if comp_len > 3 else 0

        def compare(self, other):
            return self.x == other.x and self.y == other.y and self.z == other.z and self.w == other.w

        def add(self, other):
            self.x += other.x
            self.y += other.y
            self.z += other.z
            self.w += other.w

    def __init__(self, bone, vert, normal):
        self.bone = bone
        self.vert = Vertex.CompSplit(vert)
        self.normal = Vertex.CompSplit(normal)
        # self.uv = Vertex.CompSplit(uv)

        self.additive_normals = []

    def compare(self, other):
        return self.vert.compare(other.vert)
        # return self.bone == other.bone and \
        #        self.vert.compare(other.vert) and \
        #        self.normal.compare(other.normal) and \
        #        self.uv.compare(other.uv)

    def add_normal(self, other):
        self.additive_normals.append(other.normal)

    def consolidate_normals(self):
        normal = self.normal
        for other_normal in self.additive_normals:
            normal.add(other_normal)
        num_normals = len(self.additive_normals) + 1
        normal.x /= num_normals
        normal.y /= num_normals
        normal.z /= num_normals
        normal.w /= num_normals
        self.additive_normals.clear()


def get_vert_index(vert_array, vertex):
    for index in range(0, len(vert_array)):
        if vert_array[index].compare(vertex):
            vert_array[index].add_normal(vertex)
            return index
    vert_array.append(vertex)
    return len(vert_array) - 1


def read_poly(fp, polygons, verticies):
    cur_line = fp.readline().strip()
    if 'end' in cur_line:
        return False

    polyout = Polygon()
    polyout.texture = cur_line

    tex_path_parts = os.path.splitext(polyout.texture)
    if tex_path_parts[1] == '.vtf':
        # replace it, vtf is not a good extension
        polyout.texture = tex_path_parts[0] + '.png'

    # read the three verts
    for i in range(0, 3):
        poly_line = fp.readline().strip()
        comps = list(filter(None, poly_line.split(' ')))
        bone = int(comps[0])
        vertex = list(map(float, comps[1:4]))
        normal = list(map(float, comps[4:7]))
        uv = list(map(float, comps[7:9]))

        vertex = Vertex(bone, vertex, normal)
        polyout.indicies.append(get_vert_index(verticies, vertex))
        polyout.uvs.append(Vertex.CompSplit(uv))
        polyout.normals.append(Vertex.CompSplit(normal))

    polygons.append(polyout)
    return True


def create_fbx(fbx_path, polygons, verticies):
    # Create the required FBX SDK data structures.
    fbx_manager = fbx.FbxManager.Create()
    fbx_scene = fbx.FbxScene.Create(fbx_manager, '')

    mdl_name = os.path.basename(fbx_path)

    scene_info = fbx.FbxDocumentInfo.Create(fbx_manager, "SceneInfo")
    scene_info.mTitle = mdl_name
    scene_info.mSubject = "Another SMD converter thingy..."
    scene_info.mAuthor = "iDGi"
    scene_info.mRevision = "rev. 1.0"
    scene_info.mKeywords = mdl_name
    scene_info.mComment = "n/a"
    fbx_scene.SetSceneInfo(scene_info)

    root_node = fbx_scene.GetRootNode()

    # add the model node, we will put all the verts and stuff in that
    mdl_node = fbx.FbxNode.Create(fbx_scene, mdl_name)
    root_node.AddChild(mdl_node)

    # create new node for the mesh
    new_node = fbx.FbxNode.Create(fbx_scene, '{0}Node{1}'.format(mdl_name, 0))
    mdl_node.AddChild(new_node)

    new_mesh = fbx.FbxMesh.Create(fbx_scene, '{0}Mesh{1}'.format(mdl_name, 0))
    new_node.SetNodeAttribute(new_mesh)
    new_node.SetShadingMode(fbx.FbxNode.eTextureShading)

    # Init the required number of control points (verticies)
    new_mesh.InitControlPoints(len(verticies))

    # Add all the verticies for this group
    for i in range(0, len(verticies)):
        vertex = verticies[i]
        new_mesh.SetControlPointAt(fbx.FbxVector4(vertex.vert.x, vertex.vert.y, vertex.vert.z), i)

    # Create the layer to store UV and normal data
    layer = new_mesh.GetLayer(0)
    if not layer:
        new_mesh.CreateLayer()
        layer = new_mesh.GetLayer(0)

    # Create the materials.
    # Each polygon face will be assigned a unique material.
    # matLayer = fbx.FbxLayerElementMaterial.Create(new_mesh, "")
    # matLayer.SetMappingMode(fbx.FbxLayerElement.eByPolygon)
    # matLayer.SetReferenceMode(fbx.FbxLayerElement.eIndexToDirect)
    # layer.SetMaterials(matLayer)

    # Setup the indicies (the connections between verticies) per polygon
    for i in range(0, len(polygons)):
        new_mesh.BeginPolygon(i)
        polygon = polygons[i]
        for j in range(0, 3):
            new_mesh.AddPolygon(polygon.indicies[j])
        new_mesh.EndPolygon()

    # create the UV textures mapping.
    # On layer 0 all the faces have the same texture
    uvLayer = fbx.FbxLayerElementUV.Create(new_mesh, '')
    uvLayer.SetMappingMode(fbx.FbxLayerElement.eByPolygonVertex)
    uvLayer.SetReferenceMode(fbx.FbxLayerElement.eDirect)
#
    # For all the verticies, set the UVs
    for i in range(0, len(polygons)):
        polygon = polygons[i]
        for j in range(0, 3):
            uvLayer.GetDirectArray().Add(fbx.FbxVector2(polygon.uvs[j].x, polygon.uvs[j].y))

    layer.SetUVs(uvLayer)

    # specify normals per control point.
    # For compatibility, we follow the rules stated in the
    # layer class documentation: normals are defined on layer 0 and
    # are assigned by control point.
    normLayer = fbx.FbxLayerElementNormal.Create(new_mesh, '')
    normLayer.SetMappingMode(fbx.FbxLayerElement.eByPolygonVertex)  # eByControlPoint
    normLayer.SetReferenceMode(fbx.FbxLayerElement.eDirect)

    for i in range(0, len(polygons)):
        polygon = polygons[i]
        for j in range(0, 3):
            normLayer.GetDirectArray().Add(fbx.FbxVector4(polygon.normals[j].x, polygon.normals[j].y, polygon.normals[j].z, 1.0))

    # for i in range(0, len(verticies)):
    #     vertex = verticies[i]
    #     normLayer.GetDirectArray().Add(fbx.FbxVector4(vertex.normal.x, vertex.normal.y, vertex.normal.z, 1.0))

    layer.SetNormals(normLayer)

    # Set textures
    texture_name = polygons[0].texture

    # Create texture if nessesary
    texture = create_texture(fbx_manager, texture_name, texture_name)

    # We also need a material, create that now
    material_name = fbx.FbxString(texture_name)

    material = fbx.FbxSurfacePhong.Create(fbx_manager, material_name.Buffer())

    # Generate primary and secondary colors.
    material.Emissive.Set(fbx.FbxDouble3(0.0, 0.0, 0.0))
    material.Ambient.Set(fbx.FbxDouble3(1.0, 1.0, 1.0))
    material.Diffuse.Set(fbx.FbxDouble3(1.0, 1.0, 1.0))
    material.Specular.Set(fbx.FbxDouble3(0.0, 0.0, 0.0))
    material.TransparencyFactor.Set(0.0)
    material.Shininess.Set(0.5)
    material.ShadingModel.Set(fbx.FbxString("phong"))

    material_info = (material, texture)

    texLayer = fbx.FbxLayerElementTexture.Create(new_mesh, '')
    texLayer.SetBlendMode(fbx.FbxLayerElementTexture.eModulate)
    texLayer.SetMappingMode(fbx.FbxLayerElement.eByPolygon)
    texLayer.SetReferenceMode(fbx.FbxLayerElement.eIndexToDirect)
    texLayer.GetDirectArray().Add(material_info[1])

    # set all faces to that texture
    for i in range(0, len(polygons)):
        texLayer.GetIndexArray().Add(0)

    layer.SetTextures(fbx.FbxLayerElement.eTextureDiffuse, texLayer)
    new_node.AddMaterial(material_info[0])

    # Save the scene.
    save_scene(fbx_path, fbx_manager, fbx_scene, False)

    # Destroy the fbx manager explicitly, which recursively destroys
    # all the objects that have been created with it.
    fbx_manager.Destroy()
    del fbx_manager, fbx_scene


def main():
    if len(sys.argv) != 2:
        exit()

    polygons = []
    verticies = []
    with open(sys.argv[1], 'r') as fp:
        # Skip to triangles
        while 'triangles' not in fp.readline():
            pass
        # parse the triangles till 'end' is found
        while read_poly(fp, polygons, verticies):
            pass

    # we have all of the polys, now put them in an FBX
    print('Parsed {} polygons!'.format(len(polygons)))
    print('{} unique verticies'.format(len(verticies)))

    for vert in verticies:
        vert.consolidate_normals()
        # print('%f %f %f' % (vert.vert.x, vert.vert.y, vert.vert.z))

    fbx_path = os.path.splitext(sys.argv[1])[0] + '.fbx'
    create_fbx(fbx_path, polygons, verticies)


if __name__ == "__main__":
    main()
