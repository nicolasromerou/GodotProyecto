extends SceneTree
const Profile = preload("res://scripts/road_profile.gd")
const World = preload("res://scripts/traffic_world.gd")
const Math = preload("res://scripts/traffic_math.gd")
const Street = preload("res://scripts/reference_street.gd")
var passed: int = 0
var failed: int = 0

func check(value: bool, label: String) -> void:
	if value: passed += 1
	else:
		failed += 1
		push_error("FAIL " + label)
	print("PASS " if value else "FAIL ", label)

func nose_contact(pose: Dictionary) -> bool:
	# Mediana: cuerpo recto hasta z=-20 y extremo semicircular de radio3,5.
	if Math.overlap(pose, {"x": 0.0, "z": -42.5, "yaw": 0.0, "length": 45.0, "width": 7.0}): return true
	var f := Vector2(sin(float(pose.yaw)), cos(float(pose.yaw)))
	var r := Vector2(f.y, -f.x)
	var delta := Vector2(-float(pose.x), -20.0 - float(pose.z))
	var forward: float = clampf(delta.dot(f), -float(pose.length) * 0.5, float(pose.length) * 0.5)
	var right: float = clampf(delta.dot(r), -float(pose.width) * 0.5, float(pose.width) * 0.5)
	return (delta - f * forward - r * right).length_squared() < 3.5 * 3.5 - 0.00001

func on_asphalt(pose: Dictionary, central: bool) -> bool:
	var f := Vector2(sin(float(pose.yaw)), cos(float(pose.yaw)))
	var r := Vector2(f.y, -f.x)
	var center := Vector2(float(pose.x), float(pose.z))
	var corners: Array[Vector2] = []
	for lengths in [Vector2(1, 1), Vector2(1, -1), Vector2(-1, -1), Vector2(-1, 1)]:
		corners.append(center + f * float(pose.length) * 0.5 * lengths.x + r * float(pose.width) * 0.5 * lengths.y)
	for edge in range(4):
		for sample in range(9):
			if not Street.is_asphalt(corners[edge].lerp(corners[(edge + 1) % 4], sample / 8.0), central): return false
	return true

func _initialize() -> void:
	var central = Profile.new(true)
	var regular = Profile.new(false)
	check(central.approach_offset(0) == 5.25 and central.exit_offset(2) == 5.25, "Carriles del bulevar norte separados de la mediana")
	check(central.approach_offset(1) == 1.75 and regular.approach_offset(0) == 1.75, "Resto de carriles centrados en franjas de3,5m")
	check(absf(central.pose_for_straight(0, -105.0).x + 1.75) < 0.0001, "Extremo de sector coincide con carril vecino")
	var continuous: bool = true
	var max_step: float = 0.0
	for heading in [0, 2]:
		var previous: Vector2 = central.point_for_straight(heading, -105.0)
		for step in range(1, 2101):
			var point: Vector2 = central.point_for_straight(heading, -105.0 + step * 0.1)
			max_step = maxf(max_step, point.distance_to(previous))
			continuous = continuous and point.is_finite() and point.distance_to(previous) < 0.102
			previous = point
	check(continuous, "Transición de anchura continua sin desplazamientos instantáneos")
	var tangent: bool = true
	for position in [-105.0, -65.0, -21.5]:
		var pose: Dictionary = central.pose_for_straight(0, position)
		tangent = tangent and absf(float(pose.yaw)) < 0.001
	check(tangent, "Taper y entrada conservan tangente longitudinal")
	var paths_valid: bool = true
	var median_clear: bool = true
	var curbs_clear: bool = true
	for profile in [regular, central]:
		for heading in range(4):
			for turn in [-1, 0, 1]:
				var path: Dictionary = profile.turn_path(heading, turn)
				var start: Dictionary = Math.path_pose(path, 0)
				var finish: Dictionary = Math.path_pose(path, float(path.length))
				var expected_start: Vector2 = profile.point_for_straight(heading, -21.5)
				var expected_finish: Vector2 = profile.point_for_straight(int(path.next_heading), 21.5)
				paths_valid = paths_valid and expected_start.distance_to(Vector2(start.x, start.z)) < 0.0001 and expected_finish.distance_to(Vector2(finish.x, finish.z)) < 0.0001
				paths_valid = paths_valid and absf(wrapf(float(start.yaw) - Math.yaw_for(heading), -PI, PI)) < 0.001 and absf(wrapf(float(finish.yaw) - Math.yaw_for(int(path.next_heading)), -PI, PI)) < 0.001
				for step in range(401):
					var pose: Dictionary = Math.path_pose(path, float(path.length) * step / 400.0)
					pose.length = 9.4
					pose.width = 2.5
					if profile == central and nose_contact(pose):
						print("MEDIAN_CONTACT h=", heading, " turn=", turn, " step=", step, " ", JSON.stringify(pose))
						median_clear = false
						break
					if not on_asphalt(pose, profile == central):
						print("CURB_CONTACT central=", profile == central, " h=", heading, " turn=", turn, " step=", step, " ", JSON.stringify(pose))
						curbs_clear = false
						break
	check(paths_valid, "Veinticuatro rutas conservan extremos y tangentes del nuevo trazado")
	check(median_clear, "Bus9,4x2,5m no invade cuerpo ni nariz circular de mediana en doce rutas")
	check(curbs_clear, "Perímetro completo del bus queda sobre calzada y fuera de bordillos en veinticuatro rutas")
	var taper_clear: bool = true
	for heading in [0, 2]:
		for step in range(801):
			var pose: Dictionary = central.pose_for_straight(heading, (-100.0 + step * 0.1) if heading == 0 else (20.0 + step * 0.1))
			pose.length = 9.4
			pose.width = 2.5
			if not on_asphalt(pose, true): taper_clear = false
	check(taper_clear, "Bus permanece sobre asfalto durante estrechamiento de bulevar")
	var world = World.new(false)
	world.configure_profile(true)
	world.controller.clearance = 10000.0
	world.next_id = 3
	var vehicle: Dictionary = world.create_vehicle(0, 36.0)
	for _step in range(1200): world.tick(1.0 / 60.0)
	check(float(vehicle.z) + float(vehicle.length) * 0.5 <= -20.0 and not world.is_occupied(), "Rojo detiene el bus antes de línea20m y fuera de volumen de despeje")
	world._sense()
	check(world.controller.counts[0] == 1, "Sensor norte sigue el carril del bulevar")
	vehicle.x = -25.0
	world._sense()
	check(world.controller.counts[0] == 0, "Sensor no cuenta fuera de la franja real")
	world.reset(false)
	world.configure_profile(false)
	world.create_vehicle(0, 36.0, 1)
	world.create_vehicle(1, 36.0, 0)
	for _step in range(3600): world.tick(1.0 / 60.0)
	check(world.statistics.crossings == 2, "Giro derecho no confunde un vehículo detenido del carril contrario con su líder")
	print("ROAD_PROFILE_TESTS ", passed, " passed, ", failed, " failed")
	quit(0 if failed == 0 else 1)
