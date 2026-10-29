extends RefCounted
## Lee los STL binarios originales sin herramientas externas ni modificar archivos.
## Origen Z arriba, X longitudinal -> Godot Y arriba y frente +Z.
const Catalog = preload("res://scripts/fleet_catalog.gd")
static var cache: Dictionary = {}

static func mesh_for(spec: Dictionary) -> ArrayMesh:
	if cache.has(spec.key):
		return cache[spec.key]
	var data: PackedByteArray = FileAccess.get_file_as_bytes(spec.path)
	if data.size() < 84:
		push_error("STL ausente o incompleto: " + spec.path)
		return null
	var count: int = data.decode_u32(80)
	if count < 1 or data.size() != 84 + count * 50:
		push_error("STL binario inválido: " + spec.path)
		return null
	var points := PackedVector3Array()
	var low := Vector3(INF, INF, INF)
	var high := Vector3(-INF, -INF, -INF)
	for triangle in range(count):
		for corner in range(3):
			var offset: int = 84 + triangle * 50 + 12 + corner * 12
			var point := Vector3(-data.decode_float(offset + 4), data.decode_float(offset + 8), -data.decode_float(offset))
			if not point.is_finite():
				push_error("STL contiene coordenadas no finitas")
				return null
			points.append(point)
			low = low.min(point)
			high = high.max(point)
	var extent: Vector3 = high - low
	if extent.x <= 0.0 or extent.y <= 0.0 or extent.z <= 0.0:
		return null
	var scale := Vector3(float(spec.width) / extent.x, float(spec.length) / extent.z, float(spec.length) / extent.z)
	var center := Vector3((low.x + high.x) * 0.5, low.y, (low.z + high.z) * 0.5)
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	for triangle in range(count):
		var a: Vector3 = (points[triangle * 3] - center) * scale
		var b: Vector3 = (points[triangle * 3 + 1] - center) * scale
		var c: Vector3 = (points[triangle * 3 + 2] - center) * scale
		var normal: Vector3 = (b - a).cross(c - a).normalized()
		# STL es antihorario, ArrayMesh usa caras horarias.
		vertices.append_array(PackedVector3Array([a, c, b]))
		normals.append_array(PackedVector3Array([normal, normal, normal]))
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var material := StandardMaterial3D.new()
	material.albedo_color = spec.color
	material.roughness = 0.7
	mesh.surface_set_material(0, material)
	cache[spec.key] = mesh
	return mesh

static func create_vehicle(id: int) -> Node3D:
	var root := Node3D.new()
	root.name = "Vehicle_%d" % id
	var instance := MeshInstance3D.new()
	instance.mesh = mesh_for(Catalog.for_id(id))
	instance.position.y = 0.05
	root.add_child(instance)
	return root
