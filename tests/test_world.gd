extends SceneTree
const World = preload("res://scripts/traffic_world.gd")
const Math = preload("res://scripts/traffic_math.gd")
var passed: int = 0
var failed: int = 0

func _initialize() -> void:
	call_deferred("_run")

func check(condition: bool, label: String) -> void:
	if condition:
		passed += 1
		print("PASS ", label)
	else:
		failed += 1
		push_error("FAIL " + label)

func advance(world: RefCounted, seconds: float) -> void:
	for i in range(roundi(seconds * 60.0)):
		world.tick(1.0 / 60.0)

func no_overlaps(world: RefCounted) -> bool:
	for i in range(world.vehicles.size()):
		for j in range(i + 1, world.vehicles.size()):
			if Math.overlap(world.vehicles[i], world.vehicles[j]):
				return false
	return true

func _run() -> void:
	var motion: Dictionary = Math.follow_speed(20.0, 25.0, 0.1, 0.0, 1.0 / 60.0)
	check(float(motion.distance) == 0.0 and float(motion.speed) == 0.0, "Límite de avance evita invadir un obstáculo inmediato")
	var path_ok: bool = true
	for heading in range(4):
		for turn in [-1, 0, 1]:
			var path: Dictionary = Math.make_turn_path(heading, turn)
			var start: Dictionary = Math.path_pose(path, 0.0)
			var finish: Dictionary = Math.path_pose(path, float(path.length))
			var f: Vector2 = Math.forward(heading)
			var g: Vector2 = Math.forward(int(path.next_heading))
			var expected_start: Vector2 = -f * 16.5 + Vector2(-f.y, f.x) * 3.5
			var expected_finish: Vector2 = g * 16.5 + Vector2(-g.y, g.x) * 3.5
			path_ok = path_ok and expected_start.distance_to(Vector2(float(start.x), float(start.z))) < 0.0001
			path_ok = path_ok and expected_finish.distance_to(Vector2(float(finish.x), float(finish.z))) < 0.0001
			path_ok = path_ok and absf(wrapf(float(start.yaw) - Math.yaw_for(heading), -PI, PI)) < 0.0001
			path_ok = path_ok and absf(wrapf(float(finish.yaw) - Math.yaw_for(int(path.next_heading)), -PI, PI)) < 0.0001
	check(path_ok, "Doce rutas conservan posición y tangente al entrar y salir")
	var world = World.new()
	check(world.vehicles.size() == 12 and no_overlaps(world), "Doce vehículos iniciales separados en cuatro accesos")
	world.reset(false)
	world.controller.clearance = 10000.0
	var waiting: Dictionary = world.create_vehicle(0, 30.0)
	advance(world, 20.0)
	check(float(waiting.z) <= -(15.4 + 2.4) and float(waiting.speed) < 0.001 and not bool(waiting.committed), "Rojo mantiene el parachoques antes de la línea sin compromiso")
	check(not world.is_occupied(), "Un auto detenido ante la línea no bloquea el despeje")
	world.reset(false)
	advance(world, 30.0)
	check(world.controller.stage == "ALL_RED" and world.vehicles.is_empty(), "FTI sin vehículos permanece todo rojo")
	for mode: String in ["fti", "adaptive", "fixed"]:
		world.reset()
		world.set_mode(mode)
		var safe: bool = true
		for i in range(14400):
			world.tick(1.0 / 60.0)
			if i % 30 == 0 and not no_overlaps(world):
				safe = false
				break
		check(safe, mode + ": 240 segundos sin solapamientos SAT")
		check(int(world.statistics.turns) >= 5 and int(world.statistics.crossings) >= 5 and int(world.statistics.departures) >= 5, mode + ": giros, cruces y reposición progresan")
		check(float(world.statistics.max_step) < 0.3, mode + ": avance continuo menor de 30 cm por paso")
		print("METRICS ", mode, " ", JSON.stringify(world.statistics))
	world.reset()
	world.set_mode("fti")
	world.sensor_enabled = false
	advance(world, 20.0)
	check(world.controller.fallback and world.controller.running_mode == "fixed", "Pérdida de sensores activa respaldo fijo")
	world.sensor_enabled = true
	advance(world, 20.0)
	check(not world.controller.fallback and world.controller.running_mode == world.controller.mode, "Recuperación de sensores restaura el modo solicitado")
	var snapshot: Dictionary = world.snapshot()
	var text: String = JSON.stringify(snapshot)
	check(JSON.parse_string(text) is Dictionary and not text.contains("Vector2"), "Instantánea JSON contiene poses simples y ningún recurso visual")
	var other = World.new()
	world.reset()
	world.set_mode("fti")
	advance(world, 30.0)
	advance(other, 30.0)
	check(JSON.stringify(world.snapshot()) == JSON.stringify(other.snapshot()), "Mismos pasos y entradas producen el mismo estado")
	var before: float = world.simulation_time
	var mode_before: String = world.controller.mode
	world.tick(1.0)
	check(not world.set_mode("inexistente") and world.controller.mode == mode_before and world.simulation_time == before, "Rechaza modo desconocido y pasos excesivos")
	print("WORLD_TESTS ", passed, " passed, ", failed, " failed")
	quit(0 if failed == 0 else 1)
