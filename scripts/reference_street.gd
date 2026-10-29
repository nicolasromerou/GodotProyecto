extends RefCounted
## Reconstrucción volumétrica del trazado de calle/Cruce_Calles.png.
## El acceso norte de I-5 reproduce la avenida dividida y su isla ajardinada.
const REFERENCE_PATH: String = "res://calle/Cruce_Calles.png"
const HALF: float = 7.0
const RADIUS: float = 6.0
const LIMIT: float = 105.0
const CURB_HEIGHT: float = 0.18
const SURFACE_Y: float = 0.025
static var asphalt_polygons: Dictionary = {}

static func is_asphalt(point: Vector2, central: bool = false) -> bool:
	# Coordenadas locales del sector. Excluye la isla elevada, incluido su morro.
	if not asphalt_polygons.has(central):
		asphalt_polygons[central] = {"road": _outline(10.5 if central else HALF, central), "median": _median() if central else PackedVector2Array()}
	var polygons: Dictionary = asphalt_polygons[central]
	return Geometry2D.is_point_in_polygon(point, polygons.road) and (not central or not Geometry2D.is_point_in_polygon(point, polygons.median))

static func build(parent: Node3D, centers: Array, _building_material: Material = null) -> Dictionary:
	var root := Node3D.new()
	root.name = "ReferenceStreet"
	root.set_meta("source_reference", REFERENCE_PATH)
	root.set_meta("lane_width", 3.5)
	parent.add_child(root)
	var asphalt: Material = _surface_material(Color("454546"), false)
	var sidewalk: Material = _surface_material(Color("aaa9a1"), true)
	var curb: Material = _plain(Color("ceccc2"))
	var white: Material = _plain(Color("eeeede"))
	var yellow: Material = _plain(Color("dfbd48"))
	var lawn: Material = _surface_material(Color("678947"), false)
	var path: Material = _surface_material(Color("8c806d"), true)
	var white_boxes: Array = []
	var yellow_boxes: Array = []
	var curb_boxes: Array = []
	var tree_positions: Array[Vector3] = []
	for index in range(centers.size()):
		var center: Vector2 = centers[index]
		var divided: bool = index == 4
		var north_half: float = 10.5 if divided else HALF
		var outline: PackedVector2Array = _outline(north_half, divided)
		_surface(root, outline, center, SURFACE_Y, asphalt)
		for corner in _sidewalks(north_half, divided):
			_surface(root, corner, center, CURB_HEIGHT, sidewalk)
		_curb_outline(curb_boxes, outline, center)
		_marks(white_boxes, yellow_boxes, center, divided)
		if divided:
			var median: PackedVector2Array = _median()
			_surface(root, median, center, CURB_HEIGHT + 0.005, lawn)
			_curb_outline(curb_boxes, median, center)
			# El sendero lateral y los árboles repiten la composición del plano.
			var walkway := PackedVector2Array([Vector2(0.7, -64), Vector2(2.7, -64), Vector2(2.7, -23), Vector2(0.7, -23)])
			_surface(root, walkway, center, CURB_HEIGHT + 0.018, path)
			for z in [-29.0, -40.5, -53.0, -65.0, -77.0]:
				tree_positions.append(Vector3(center.x - 1.4, CURB_HEIGHT, center.y + z))
		_green_verges(root, center, divided, lawn)
	_merge_surfaces(root)
	_batch(root, white_boxes, white, "CrosswalksAndLaneLines")
	_batch(root, yellow_boxes, yellow, "DoubleYellowLines")
	_batch(root, curb_boxes, curb, "RoundedCurbs")
	return {"root": root, "tree_positions": tree_positions, "reference_path": REFERENCE_PATH,
		"lane_width": 3.5, "road_width": 14.0, "north_boulevard_width": 21.0,
		"crosswalk_distance": 18.0, "stop_line_distance": 20.0, "curb_radius": RADIUS,
		"marking_instances": white_boxes.size() + yellow_boxes.size(), "curb_instances": curb_boxes.size()}

static func north_extra(z: float) -> float:
	if z > -16.5: return 0.0
	if z >= -65.0: return 3.5
	var t: float = clampf((-z - 65.0) / 40.0, 0.0, 1.0)
	return 3.5 * (1.0 - t * t * t * (10.0 + t * (-15.0 + 6.0 * t)))

static func _outline(north_half: float, divided: bool) -> PackedVector2Array:
	var points := PackedVector2Array()
	# Sentido de recorrido: desde el extremo N izquierdo, contorno oeste y sur.
	points.append(Vector2(-HALF, -LIMIT))
	if divided:
		for step in range(1, 17):
			var z: float = -LIMIT + step * 40.0 / 16.0
			points.append(Vector2(-(HALF + north_extra(z)), z))
	points.append(Vector2(-north_half, -13.0))
	_arc(points, Vector2(-north_half - RADIUS, -13), RADIUS, 0.0, PI * 0.5)
	points.append(Vector2(-LIMIT, -HALF))
	points.append(Vector2(-LIMIT, HALF))
	points.append(Vector2(-13, HALF))
	_arc(points, Vector2(-13, 13), RADIUS, -PI * 0.5, 0.0)
	points.append(Vector2(-HALF, LIMIT))
	points.append(Vector2(HALF, LIMIT))
	points.append(Vector2(HALF, 13))
	_arc(points, Vector2(13, 13), RADIUS, PI, PI * 1.5)
	points.append(Vector2(LIMIT, HALF))
	points.append(Vector2(LIMIT, -HALF))
	points.append(Vector2(north_half + RADIUS, -HALF))
	_arc(points, Vector2(north_half + RADIUS, -13), RADIUS, PI * 0.5, PI)
	if divided:
		points.append(Vector2(north_half, -65))
		for step in range(1, 17):
			var z: float = -65.0 - step * 40.0 / 16.0
			points.append(Vector2(HALF + north_extra(z), z))
	else:
		points.append(Vector2(HALF, -LIMIT))
	return points

static func _sidewalks(north_half: float, divided: bool) -> Array:
	var nw := PackedVector2Array([Vector2(-LIMIT, -LIMIT), Vector2(-HALF, -LIMIT)])
	if divided:
		for step in range(1, 17):
			var z: float = -LIMIT + step * 40.0 / 16.0
			nw.append(Vector2(-(HALF + north_extra(z)), z))
	nw.append(Vector2(-north_half, -13))
	_arc(nw, Vector2(-north_half - RADIUS, -13), RADIUS, 0, PI * 0.5)
	nw.append(Vector2(-LIMIT, -HALF))
	var ne := PackedVector2Array([Vector2(HALF, -LIMIT), Vector2(LIMIT, -LIMIT), Vector2(LIMIT, -HALF), Vector2(north_half + RADIUS, -HALF)])
	_arc(ne, Vector2(north_half + RADIUS, -13), RADIUS, PI * 0.5, PI)
	if divided:
		ne.append(Vector2(north_half, -65))
		for step in range(1, 17):
			var z: float = -65.0 - step * 40.0 / 16.0
			ne.append(Vector2(HALF + north_extra(z), z))
	var sw := PackedVector2Array([Vector2(-LIMIT, HALF), Vector2(-13, HALF)])
	_arc(sw, Vector2(-13, 13), RADIUS, -PI * 0.5, 0)
	sw.append_array(PackedVector2Array([Vector2(-HALF, LIMIT), Vector2(-LIMIT, LIMIT)]))
	var se := PackedVector2Array([Vector2(13, HALF), Vector2(LIMIT, HALF), Vector2(LIMIT, LIMIT), Vector2(HALF, LIMIT), Vector2(HALF, 13)])
	_arc(se, Vector2(13, 13), RADIUS, PI, PI * 1.5)
	return [nw, ne, sw, se]

static func _median() -> PackedVector2Array:
	var points := PackedVector2Array([Vector2(3.5, -20)])
	# Punta semicircular del separador, como en la referencia.
	_arc(points, Vector2(0, -20), 3.5, 0, PI)
	points.append(Vector2(-3.5, -65))
	for step in range(1, 17):
		var z: float = -65.0 - step * 40.0 / 16.0
		points.append(Vector2(-north_extra(z), z))
	for step in range(15, -1, -1):
		var z: float = -65.0 - step * 40.0 / 16.0
		points.append(Vector2(north_extra(z), z))
	points.append(Vector2(3.5, -20))
	return points

static func _arc(points: PackedVector2Array, center: Vector2, radius: float, start: float, finish: float) -> void:
	for step in range(1, 17):
		var angle: float = lerpf(start, finish, step / 16.0)
		points.append(center + Vector2(cos(angle), sin(angle)) * radius)

static func _surface(parent: Node3D, outline: PackedVector2Array, center: Vector2, height: float, material: Material) -> void:
	var points: PackedVector2Array = outline.duplicate()
	# Quitar vértices consecutivos duplicados de tangencias o cierres.
	for index in range(points.size() - 1, 0, -1):
		if points[index].distance_to(points[index - 1]) < 0.0001: points.remove_at(index)
	if points.size() > 2 and points[0].distance_to(points[points.size() - 1]) < 0.0001: points.remove_at(points.size() - 1)
	var triangles: PackedInt32Array = Geometry2D.triangulate_polygon(points)
	if triangles.is_empty():
		push_error("No se pudo triangular una superficie del trazado de referencia")
		return
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	for point in points:
		vertices.append(Vector3(center.x + point.x, height, center.y + point.y))
		normals.append(Vector3.UP)
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_INDEX] = triangles
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	instance.material_override = material
	parent.add_child(instance)

static func _marks(white: Array, yellow: Array, center: Vector2, divided: bool) -> void:
	for side in [-1, 1]:
		# Doble amarilla EW y sur; el norte central utiliza mediana ajardinada.
		for offset in [-0.11, 0.11]:
			_line(yellow, center + Vector2(side * 22.5, offset), center + Vector2(side * LIMIT, offset), 0.09)
		_line(yellow, center + Vector2(side * 0.11, 22.5), center + Vector2(side * 0.11, LIMIT), 0.09)
		if not divided:
			_line(yellow, center + Vector2(side * 0.11, -22.5), center + Vector2(side * 0.11, -LIMIT), 0.09)
		# Líneas blancas discontinuas de separación de los dos carriles.
		for step in range(16):
			var along: float = 24.0 + step * 5.0
			_line(white, center + Vector2(side * along, -3.5), center + Vector2(side * (along + 2.7), -3.5), 0.12)
			_line(white, center + Vector2(side * along, 3.5), center + Vector2(side * (along + 2.7), 3.5), 0.12)
			_line(white, center + Vector2(side * 3.5, along), center + Vector2(side * 3.5, along + 2.7), 0.12)
			var extra_a: float = north_extra(-along) if divided else 0.0
			var extra_b: float = north_extra(-(along + 2.7)) if divided else 0.0
			_line(white, center + Vector2(side * (3.5 + extra_a), -along), center + Vector2(side * (3.5 + extra_b), -(along + 2.7)), 0.12)
		# Cebra transversal en E y O.
		for stripe in range(14):
			_box(white, Vector3(2.4, 0.015, 0.52), Vector3(center.x + side * 18.0, 0.045, center.y - 6.6 + stripe * 1.0))
	# Cruces de peatones y barras de detención siguen el borde real del trazado.
	for stripe in range(14):
		_box(white, Vector3(0.52, 0.015, 2.4), Vector3(center.x - 6.6 + stripe, 0.045, center.y + 18.0))
	if divided:
		for side in [-1, 1]:
			for stripe in range(7):
				_box(white, Vector3(0.52, 0.015, 2.4), Vector3(center.x + side * (3.9 + stripe), 0.045, center.y - 18.0))
	else:
		for stripe in range(14):
			_box(white, Vector3(0.52, 0.015, 2.4), Vector3(center.x - 6.6 + stripe, 0.045, center.y - 18.0))
	var extra: float = 3.5 if divided else 0.0
	_box(white, Vector3(6.8, 0.018, 0.30), Vector3(center.x - 3.5 - extra, 0.05, center.y - 20.0))
	_box(white, Vector3(6.8, 0.018, 0.30), Vector3(center.x + 3.5, 0.05, center.y + 20.0))
	_box(white, Vector3(0.30, 0.018, 6.8), Vector3(center.x + 20.0, 0.05, center.y - 3.5))
	_box(white, Vector3(0.30, 0.018, 6.8), Vector3(center.x - 20.0, 0.05, center.y + 3.5))

static func _green_verges(root: Node3D, center: Vector2, divided: bool, lawn: Material) -> void:
	for side in [-1, 1]:
		for direction in [-1, 1]:
			var a: float = direction * 24.0
			var b: float = direction * 99.0
			var ew := PackedVector2Array([Vector2(a, side * 7.35), Vector2(b, side * 7.35), Vector2(b, side * 8.8), Vector2(a, side * 8.8)])
			_surface(root, ew, center, CURB_HEIGHT + 0.006, lawn)
			var ns := PackedVector2Array()
			for step in range(17):
				var z: float = lerpf(a, b, step / 16.0)
				var extra: float = north_extra(z) if divided and z < 0.0 else 0.0
				ns.append(Vector2(side * (7.35 + extra), z))
			for step in range(16, -1, -1):
				var z: float = lerpf(a, b, step / 16.0)
				var extra: float = north_extra(z) if divided and z < 0.0 else 0.0
				ns.append(Vector2(side * (8.8 + extra), z))
			_surface(root, ns, center, CURB_HEIGHT + 0.006, lawn)

static func _merge_surfaces(root: Node3D) -> void:
	# Una superficie por material para toda la red; los bordillos y marcas son MultiMesh.
	var groups: Dictionary = {}
	for child in root.get_children():
		if not child is MeshInstance3D: continue
		var material: Material = child.material_override
		var key: int = material.get_instance_id()
		if not groups.has(key):
			var tool := SurfaceTool.new()
			tool.begin(Mesh.PRIMITIVE_TRIANGLES)
			tool.set_material(material)
			groups[key] = {"tool": tool, "material": material}
		groups[key].tool.append_from(child.mesh, 0, Transform3D.IDENTITY)
		root.remove_child(child)
		child.queue_free()
	for key in groups:
		var instance := MeshInstance3D.new()
		instance.mesh = groups[key].tool.commit()
		instance.material_override = groups[key].material
		root.add_child(instance)

static func _curb_outline(boxes: Array, outline: PackedVector2Array, center: Vector2) -> void:
	for index in range(outline.size()):
		var a: Vector2 = outline[index]
		var b: Vector2 = outline[(index + 1) % outline.size()]
		if (absf(a.x) > 104.99 and absf(b.x) > 104.99) or (absf(a.y) > 104.99 and absf(b.y) > 104.99): continue
		var direction: Vector2 = b - a
		if direction.length() < 0.001: continue
		var midpoint: Vector2 = center + (a + b) * 0.5
		var basis: Basis = _local_scale(Basis(Vector3.UP, -atan2(direction.y, direction.x)), Vector3(direction.length() + 0.025, CURB_HEIGHT, 0.20))
		boxes.append(Transform3D(basis, Vector3(midpoint.x, CURB_HEIGHT * 0.5, midpoint.y)))

static func _line(boxes: Array, a: Vector2, b: Vector2, width: float) -> void:
	var direction: Vector2 = b - a
	var midpoint: Vector2 = (a + b) * 0.5
	var basis: Basis = _local_scale(Basis(Vector3.UP, -atan2(direction.y, direction.x)), Vector3(direction.length(), 0.013, width))
	boxes.append(Transform3D(basis, Vector3(midpoint.x, 0.043, midpoint.y)))

static func _box(boxes: Array, size: Vector3, at: Vector3) -> void:
	boxes.append(Transform3D(Basis.IDENTITY.scaled(size), at))

static func _local_scale(rotation: Basis, size: Vector3) -> Basis:
	return Basis(rotation.x * size.x, rotation.y * size.y, rotation.z * size.z)

static func _batch(parent: Node3D, transforms: Array, material: Material, title: String) -> void:
	if transforms.is_empty(): return
	var mesh := BoxMesh.new()
	mesh.size = Vector3.ONE
	var multi := MultiMesh.new()
	multi.transform_format = MultiMesh.TRANSFORM_3D
	multi.mesh = mesh
	multi.instance_count = transforms.size()
	for index in range(transforms.size()): multi.set_instance_transform(index, transforms[index])
	var instance := MultiMeshInstance3D.new()
	instance.name = title
	instance.multimesh = multi
	instance.material_override = material
	parent.add_child(instance)

static func _plain(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.95
	return material

static func _surface_material(color: Color, paving: bool) -> ShaderMaterial:
	var shader := Shader.new()
	shader.code = """shader_type spatial;
render_mode specular_disabled;
uniform vec4 ground_color : source_color;
uniform bool paving = false;
varying vec3 world_position;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
void vertex() { world_position = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz; }
void fragment() {
    float grain = hash(floor(world_position.xz * 8.0));
    float broad = hash(floor(world_position.xz * 1.5));
    float modulation = 0.974 + grain * 0.018 + broad * 0.012;
    if (paving) {
        vec2 joint = abs(fract(world_position.xz * 0.65) - 0.5);
        float seam = step(0.485, max(joint.x, joint.y));
        modulation *= 1.0 - seam * 0.045;
    }
    ALBEDO = ground_color.rgb * modulation;
    ROUGHNESS = 0.97;
}"""
	var material := ShaderMaterial.new()
	material.shader = shader
	material.set_shader_parameter("ground_color", color)
	material.set_shader_parameter("paving", paving)
	return material
