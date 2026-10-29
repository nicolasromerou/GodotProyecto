extends RefCounted
## Volúmenes y mobiliario reconstruidos a partir de Cruce_Calles.png.
## Las parcelas quedan fuera de la calzada y de sus esquinas redondeadas.
## Los objetos estáticos se agrupan por material para mantener pocas llamadas.

class Builder:
	extends RefCounted
	var parent: Node3D
	var groups: Dictionary = {}
	var fade_materials: Array[StandardMaterial3D] = []
	var counts: Dictionary = {"buildings": 0, "trees": 0, "streetlights": 0, "benches": 0, "parked_cars": 0, "parking_spaces": 0}

	func _init(target: Node3D) -> void:
		parent = target

	func material(color: Color, fade: bool = false, roughness: float = 0.86) -> StandardMaterial3D:
		var result := StandardMaterial3D.new()
		result.albedo_color = color
		result.roughness = roughness
		if fade: fade_materials.append(result)
		return result

	func shape(kind: String, size: Vector3, at: Vector3, surface: Material, yaw: float = 0.0) -> void:
		var key: String = kind + str(surface.get_instance_id())
		if not groups.has(key):
			var mesh: Mesh
			if kind == "sphere":
				var sphere := SphereMesh.new()
				sphere.radius = 0.5
				sphere.height = 1.0
				sphere.radial_segments = 10
				sphere.rings = 5
				mesh = sphere
			elif kind == "cylinder":
				var cylinder := CylinderMesh.new()
				cylinder.top_radius = 0.5
				cylinder.bottom_radius = 0.5
				cylinder.height = 1.0
				cylinder.radial_segments = 8
				mesh = cylinder
			else:
				var box := BoxMesh.new()
				box.size = Vector3.ONE
				mesh = box
			groups[key] = {"mesh": mesh, "material": surface, "transforms": []}
		var rotation := Basis(Vector3.UP, yaw)
		groups[key].transforms.append(Transform3D(Basis(rotation.x * size.x, rotation.y * size.y, rotation.z * size.z), at))

	func box(size: Vector3, at: Vector3, surface: Material, yaw: float = 0.0) -> void:
		shape("box", size, at, surface, yaw)

	func emit() -> void:
		for key in groups:
			var group: Dictionary = groups[key]
			var multimesh := MultiMesh.new()
			multimesh.transform_format = MultiMesh.TRANSFORM_3D
			multimesh.mesh = group.mesh
			multimesh.instance_count = group.transforms.size()
			for index in range(group.transforms.size()): multimesh.set_instance_transform(index, group.transforms[index])
			var holder := MultiMeshInstance3D.new()
			holder.name = "Environment_" + key
			holder.multimesh = multimesh
			holder.material_override = group.material
			parent.add_child(holder)

static func build(parent: Node3D, centers: Array, building_material: Material, tree_positions: Array = []) -> Dictionary:
	var b := Builder.new(parent)
	var walls: Array[Material] = [building_material]
	if building_material is StandardMaterial3D: b.fade_materials.append(building_material)
	walls.append(b.material(Color("d9d5c9"), true))
	walls.append(b.material(Color("c5cecd"), true))
	var trim := b.material(Color("969c99"), true)
	var frame := b.material(Color("ece8dc"), true)
	var glazing := b.material(Color("405966"), true, 0.28)
	glazing.metallic = 0.16
	var roof := b.material(Color("bfc1b8"), true)
	var equipment := b.material(Color("9fa9a8"), true)
	var awnings: Array[Material] = [b.material(Color("53796e"), true), b.material(Color("af795f"), true), b.material(Color("817b65"), true)]
	var paving := b.material(Color("c4c4b9"))
	var paving_edge := b.material(Color("969c92"))
	var planter_edge := b.material(Color("d1d0c3"))
	var grass := b.material(Color("6e9352"))
	var dark_asphalt := b.material(Color("5b6060"))
	var parking_paint := b.material(Color("dcded6"))
	var timber := b.material(Color("937354"))
	var dark_metal := b.material(Color("45504f"), false, 0.55)
	var trunk := b.material(Color("655344"))
	var leaves: Array[Material] = [b.material(Color("4b7650")), b.material(Color("5d8751")), b.material(Color("6e9358"))]
	var lamp := b.material(Color("e8dfb7"))
	lamp.emission_enabled = true
	lamp.emission = Color("d6c38f")
	lamp.emission_energy_multiplier = 0.16
	var car_paints: Array[Material] = [b.material(Color("ced5d2")), b.material(Color("66838e")), b.material(Color("a67c69")), b.material(Color("777c84"))]
	var rubber := b.material(Color("333d3e"))
	var car_glass := b.material(Color("4d6269"), false, 0.3)
	var headlights := b.material(Color("d5d6bf"))
	var taillights := b.material(Color("9d5e58"))
	for index in range(centers.size()):
		var center: Vector2 = centers[index]
		for sx in [-1, 1]:
			for sz in [-1, 1]:
				var variant: int = posmod(index + sx * 3 + sz * 5, 6)
				var parcel := Vector3(center.x + sx * 58.5, -0.055, center.y + sz * 58.5)
				b.box(Vector3(83, 0.10, 83), parcel, paving)
				# Thin property outlines preserve the architectural-plan language.
				b.box(Vector3(0.12, 0.035, 79), parcel + Vector3(sx * 40.5, 0.275, 0), paving_edge)
				b.box(Vector3(79, 0.035, 0.12), parcel + Vector3(0, 0.275, sz * 40.5), paving_edge)
				var near_size := Vector2(25.0 + float(variant % 2) * 3.0, 23.0)
				var near := Vector3(center.x + sx * 35, 0, center.y + sz * 35)
				_building(b, near, near_size, 2 + variant % 2, walls[variant % 3], trim, frame, glazing, roof, equipment, awnings[variant % 3], sz)
				var far := Vector3(center.x + sx * 76, 0, center.y + sz * 51)
				_building(b, far, Vector2(29, 29), 2 + (variant + 1) % 3, walls[(variant + 1) % 3], trim, frame, glazing, roof, equipment, awnings[(variant + 1) % 3], sz)
				# Small public garden instead of a repeated empty concrete block.
				var garden := Vector3(center.x + sx * 37, 0.235, center.y + sz * 80)
				b.box(Vector3(33, 0.11, 25), garden, grass)
				b.box(Vector3(3.1, 0.035, 25.5), garden + Vector3(0, 0.085, 0), paving)
				b.box(Vector3(33.5, 0.035, 2.5), garden + Vector3(0, 0.085, sz * 3), paving)
				_tree(b, garden + Vector3(-10, 0.05, -6), 4.7 + variant * 0.18, trunk, leaves, variant)
				_tree(b, garden + Vector3(10, 0.05, 5), 4.2 + variant * 0.15, trunk, leaves, variant + 1)
				_bench(b, garden + Vector3(-4.5, 0.07, sz * 4.8), timber, dark_metal)
				_bench(b, garden + Vector3(4.5, 0.07, sz * 4.8), timber, dark_metal)
				# Parking is on the street frontage, with a paved vehicle entrance.
				var parking := Vector3(center.x + sx * 76, 0.205, center.y + sz * 22)
				_parking(b, parking, sz, variant, dark_asphalt, parking_paint, car_paints, car_glass, rubber, headlights, taillights)
				b.box(Vector3(4.5, 0.04, 7.5), Vector3(parking.x + sx * 10.5, 0.205, center.y + sz * 11.8), dark_asphalt)
				# A modest raised planter near each commercial frontage.
				var planter := Vector3(center.x + sx * 20, 0.4, center.y + sz * 57)
				b.box(Vector3(1.6, 0.8, 1.6), planter, planter_edge)
				b.shape("sphere", Vector3(1.8, 1.2, 1.8), planter + Vector3(0, 0.65, 0), leaves[variant % 3])
		for side in [-1, 1]:
			for along in [-58.0, 58.0]:
				var lateral: float = 14.8 if index == 4 and along < 0 else 11.8
				_streetlight(b, Vector3(center.x + side * lateral, 0, center.y + along), Vector3(-side, 0, 0), dark_metal, lamp)
				_streetlight(b, Vector3(center.x + along, 0, center.y + side * 11.8), Vector3(0, 0, -side), dark_metal, lamp)
	# The central landscaped divider is the most recognizable reference feature.
	var median_trees: Array = tree_positions.duplicate()
	if median_trees.is_empty() and centers.size() > 4:
		var central: Vector2 = centers[4]
		median_trees = [Vector3(central.x, 0.12, central.y - 34), Vector3(central.x, 0.12, central.y - 45), Vector3(central.x, 0.12, central.y - 56)]
	for index in range(median_trees.size()):
		var position: Vector3 = median_trees[index]
		_tree(b, position, 5.8 + (index % 2) * 0.6, trunk, leaves, index)
	b.emit()
	return {"fade_materials": b.fade_materials, "counts": b.counts, "batches": b.groups.size()}

static func _building(b: Builder, at: Vector3, footprint: Vector2, floors: int, wall: Material, trim: Material, frame: Material, glass: Material, roof: Material, equipment: Material, awning: Material, frontage: int) -> void:
	var height: float = floors * 3.05 + 0.35
	var width: float = footprint.x
	var depth: float = footprint.y
	b.counts.buildings += 1
	b.box(Vector3(width + 0.30, 0.24, depth + 0.30), at + Vector3(0, 0.16, 0), trim)
	b.box(Vector3(width, height, depth), at + Vector3(0, height * 0.5 + 0.28, 0), wall)
	for floor_index in range(1, floors):
		b.box(Vector3(width + 0.12, 0.10, depth + 0.12), at + Vector3(0, floor_index * 3.05 + 0.28, 0), frame)
	b.box(Vector3(width + 0.5, 0.20, depth + 0.5), at + Vector3(0, height + 0.34, 0), frame)
	b.box(Vector3(width - 0.8, 0.12, depth - 0.8), at + Vector3(0, height + 0.48, 0), roof)
	for side in [-1, 1]:
		b.box(Vector3(width + 0.3, 0.40, 0.18), at + Vector3(0, height + 0.65, side * (depth * 0.5 + 0.05)), wall)
		b.box(Vector3(0.18, 0.40, depth + 0.3), at + Vector3(side * (width * 0.5 + 0.05), height + 0.65, 0), wall)
	var horizontal: int = maxi(2, floori(width / 3.7))
	var side_windows: int = maxi(2, floori(depth / 3.7))
	for floor_index in range(floors):
		var y: float = 1.7 + floor_index * 3.05
		for side in [-1, 1]:
			for column in range(horizontal):
				var x: float = (column + 1) * width / (horizontal + 1) - width * 0.5
				if floor_index == 0 and side == -frontage and absf(x) < 4: continue
				b.box(Vector3(1.72, 1.55, 0.08), at + Vector3(x, y, side * (depth * 0.5 + 0.05)), frame)
				b.box(Vector3(1.40, 1.24, 0.035), at + Vector3(x, y, side * (depth * 0.5 + 0.105)), glass)
			for column in range(side_windows):
				var z: float = (column + 1) * depth / (side_windows + 1) - depth * 0.5
				b.box(Vector3(0.08, 1.55, 1.72), at + Vector3(side * (width * 0.5 + 0.05), y, z), frame)
				b.box(Vector3(0.035, 1.24, 1.40), at + Vector3(side * (width * 0.5 + 0.105), y, z), glass)
	# Glazed storefront, canopy and mullions on the street-facing side.
	var front_z: float = -frontage * (depth * 0.5 + 0.11)
	b.box(Vector3(6.1, 2.15, 0.06), at + Vector3(0, 1.45, front_z), glass)
	for x in [-2.9, -1.0, 1.0, 2.9]: b.box(Vector3(0.09, 2.3, 0.13), at + Vector3(x, 1.48, front_z), frame)
	b.box(Vector3(7.1, 0.18, 1.5), at + Vector3(0, 2.92, front_z - frontage * 0.55), awning)
	# Roof hardware adds depth without hiding the road in a free camera.
	b.box(Vector3(3.3, 1.15, 2.0), at + Vector3(width * 0.2, height + 1.05, 0), equipment)
	b.box(Vector3(2.7, 0.30, 0.04), at + Vector3(width * 0.2, height + 1.2, 1.025), trim)
	b.shape("cylinder", Vector3(0.9, 1.0, 0.9), at + Vector3(-width * 0.2, height + 0.95, depth * 0.2), equipment)

static func _tree(b: Builder, at: Vector3, height: float, trunk: Material, leaves: Array[Material], variant: int) -> void:
	b.counts.trees += 1
	b.shape("cylinder", Vector3(0.30, height * 0.59, 0.30), at + Vector3(0, height * 0.295, 0), trunk)
	var width: float = height * 0.69
	b.shape("sphere", Vector3(width, height * 0.64, width), at + Vector3(0, height * 0.68, 0), leaves[posmod(variant, 3)])
	b.shape("sphere", Vector3(width * 0.76, height * 0.47, width * 0.83), at + Vector3(width * 0.24, height * 0.61, -width * 0.12), leaves[posmod(variant + 1, 3)])
	b.shape("sphere", Vector3(width * 0.72, height * 0.44, width * 0.74), at + Vector3(-width * 0.22, height * 0.58, width * 0.17), leaves[posmod(variant + 2, 3)])

static func _bench(b: Builder, at: Vector3, timber: Material, metal: Material) -> void:
	b.counts.benches += 1
	b.box(Vector3(2.4, 0.13, 0.65), at + Vector3(0, 0.56, 0), timber)
	b.box(Vector3(2.4, 0.62, 0.10), at + Vector3(0, 0.94, 0.28), timber)
	for side in [-1, 1]: b.box(Vector3(0.12, 0.56, 0.53), at + Vector3(side * 0.85, 0.28, 0), metal)

static func _streetlight(b: Builder, at: Vector3, direction: Vector3, metal: Material, lamp: Material) -> void:
	b.counts.streetlights += 1
	b.shape("cylinder", Vector3(0.19, 4.8, 0.19), at + Vector3(0, 2.4, 0), metal)
	b.shape("cylinder", Vector3(0.35, 0.32, 0.35), at + Vector3(0, 0.16, 0), metal)
	var yaw: float = 0.0 if absf(direction.x) > 0.5 else PI * 0.5
	b.box(Vector3(1.5, 0.10, 0.12), at + Vector3(0, 4.72, 0) + direction * 0.65, metal, yaw)
	b.box(Vector3(0.95, 0.13, 0.42), at + Vector3(0, 4.62, 0) + direction * 1.27, metal, yaw)
	b.box(Vector3(0.82, 0.025, 0.32), at + Vector3(0, 4.54, 0) + direction * 1.27, lamp, yaw)

static func _parking(b: Builder, at: Vector3, frontage: int, variant: int, asphalt: Material, paint: Material, car_paints: Array[Material], glass: Material, rubber: Material, headlights: Material, taillights: Material) -> void:
	b.box(Vector3(30, 0.05, 13), at, asphalt)
	for index in range(8):
		b.counts.parking_spaces += 1
		var x: float = -12.6 + index * 3.5
		b.box(Vector3(0.10, 0.018, 5.6), at + Vector3(x, 0.04, -frontage * 2.1), paint)
	b.box(Vector3(25, 0.018, 0.10), at + Vector3(-0.35, 0.04, -frontage * 4.85), paint)
	for slot in [1, 4]:
		var position: Vector3 = at + Vector3(-10.85 + slot * 3.5, -0.055, -frontage * 2.1)
		_parked_car(b, position, car_paints[(variant + slot) % car_paints.size()], glass, rubber, headlights, taillights)

static func _parked_car(b: Builder, at: Vector3, paint: Material, glass: Material, rubber: Material, headlights: Material, taillights: Material) -> void:
	b.counts.parked_cars += 1
	b.box(Vector3(1.72, 0.57, 3.8), at + Vector3(0, 0.67, 0), paint)
	b.box(Vector3(1.48, 0.58, 2.05), at + Vector3(0, 1.17, -0.1), glass)
	b.box(Vector3(1.50, 0.08, 1.65), at + Vector3(0, 1.49, -0.1), paint)
	for side in [-1, 1]:
		for axle in [-1, 1]: b.box(Vector3(0.17, 0.52, 0.62), at + Vector3(side * 0.88, 0.34, axle * 1.15), rubber)
	b.box(Vector3(1.3, 0.12, 0.05), at + Vector3(0, 0.70, 1.92), headlights)
	b.box(Vector3(1.3, 0.10, 0.05), at + Vector3(0, 0.70, -1.92), taillights)
