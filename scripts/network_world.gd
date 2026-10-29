extends RefCounted
## Nueve cruces conectados. Cada coche tiene un único propietario; los vecinos
## aportan poses de consulta para frenar también en los límites entre sectores.
const Junction = preload("res://scripts/traffic_world.gd")
const Math = preload("res://scripts/traffic_math.gd")
const SPACING: float = 210.0
const SCENARIOS = ["normal", "peak_ns", "peak_ew", "empty"]
var junctions: Array = []
var centers: Array[Vector2] = []
var vehicles: Array = []
var simulation_time: float = 0.0
var selected: int = 4
var mode: String = "fti"
var scenario: String = "normal"
var detector_depth: float = 55.0
var events: Array = []
var rows: Array = []
var history: Array = []
var priority_until: Array = []
var next_sample: float = 1.0
var transfers: int = 0
var wraps: int = 0
var controller:
	get: return junctions[selected].controller
var sensor_enabled: bool = true:
	set(value):
		sensor_enabled = value
		for junction in junctions: junction.sensor_enabled = value

func _init() -> void:
	for z in range(3):
		for x in range(3): centers.append(Vector2((x - 1) * SPACING, (z - 1) * SPACING))
	reset()

func reset(_populate: bool = true) -> void:
	load_scenario(scenario)

func load_scenario(key: String) -> bool:
	if key not in SCENARIOS: return false
	scenario = key
	junctions.clear()
	history.clear()
	priority_until.clear()
	events.clear()
	rows.clear()
	simulation_time = 0.0
	next_sample = 1.0
	transfers = 0
	wraps = 0
	sensor_enabled = true
	for index in range(9):
		var junction = Junction.new(false)
		junction.set_mode(mode)
		junction.detector_depth = detector_depth
		junction.next_id = index * 10000 + 1
		junctions.append(junction)
		history.append([])
		priority_until.append(0.0)
		if key != "empty":
			for heading in range(4):
				var quantity: int = 2 if (key == "peak_ns" and heading % 2 == 0) or (key == "peak_ew" and heading % 2 == 1) else 1
				for slot in range(quantity):
					junction.create_vehicle(heading, 36.0 + slot * 19.0, [0, 1, 0, -1, 0][(index + heading + slot) % 5])
	_refresh_vehicles()
	log_event("Escenario: " + key)
	return true

func set_mode(value: String) -> bool:
	if value not in ["fti", "adaptive", "fixed"]: return false
	mode = value
	for junction in junctions: junction.set_mode(value)
	log_event("Modo solicitado: " + value)
	return true

func set_sensor(index: int, enabled: bool) -> void:
	if index < 0 or index >= 9: return
	junctions[index].sensor_enabled = enabled
	log_event("I-%d · sensores %s" % [index + 1, "restaurados" if enabled else "sin señal"])

func set_depth(value: float) -> void:
	detector_depth = clampf(value, 25.0, 85.0)
	for junction in junctions: junction.detector_depth = detector_depth

func request_priority(axis: String) -> bool:
	if axis not in ["NS", "EW", ""]: return false
	junctions[selected].controller.priority = axis
	priority_until[selected] = simulation_time + 20.0 if axis != "" else 0.0
	log_event("I-%d · solicitud V2I %s (20 s)" % [selected + 1, axis])
	return true

func incident() -> bool:
	for vehicle in junctions[selected].vehicles:
		if not vehicle.cleared:
			vehicle.incident_remaining = 12.0
			log_event("I-%d · vehículo %d detenido durante 12 s" % [selected + 1, vehicle.id])
			return true
	return false

func log_event(message: String) -> void:
	events.push_front("%06.1f s · %s" % [simulation_time, message])
	if events.size() > 100: events.pop_back()

func _refresh_vehicles() -> void:
	vehicles.clear()
	for index in range(9):
		for original in junctions[index].vehicles:
			var copy: Dictionary = original.duplicate()
			copy.x = float(original.x) + centers[index].x
			copy.z = float(original.z) + centers[index].y
			copy.junction = index
			vehicles.append(copy)

func tick(dt: float) -> void:
	if dt <= 0.0 or dt > 0.1: return
	simulation_time += dt
	# Todas las consultas vecinas corresponden al inicio del mismo paso.
	_refresh_vehicles()
	for index in range(9):
		var junction = junctions[index]
		junction.external_vehicles.clear()
		for global_pose in vehicles:
			if int(global_pose.junction) == index: continue
			var delta := Vector2(float(global_pose.x), float(global_pose.z)) - centers[index]
			if absf(delta.x) < 195.0 and absf(delta.y) < 195.0:
				var local: Dictionary = global_pose.duplicate()
				local.x = delta.x
				local.z = delta.y
				junction.external_vehicles.append(local)
		if priority_until[index] > 0.0 and simulation_time >= priority_until[index]:
			junction.controller.priority = ""
			priority_until[index] = 0.0
		var before: String = junction.controller.stage + str(junction.controller.active) + junction.controller.running_mode
		junction.tick(dt)
		var after: String = junction.controller.stage + str(junction.controller.active) + junction.controller.running_mode
		if before != after: log_event("I-%d · %s %s · %s" % [index + 1, junction.controller.stage, str(junction.controller.active), junction.controller.running_mode])
	# Transferir tras avanzar TODOS los cruces evita que un auto avance dos veces.
	for index in range(9):
		for vehicle in junctions[index].departed_vehicles:
			_transfer(index, vehicle)
	_refresh_vehicles()
	if simulation_time + 0.000001 >= next_sample:
		_sample()
		next_sample += 1.0

func _transfer(index: int, vehicle: Dictionary) -> void:
	var heading: int = int(vehicle.heading)
	var col: int = index % 3
	var row: int = int(index / 3)
	var next_col: int = col + [0, 1, 0, -1][heading]
	var next_row: int = row + [1, 0, -1, 0][heading]
	var wrapped: bool = next_col < 0 or next_col > 2 or next_row < 0 or next_row > 2
	var target: int = posmod(next_row, 3) * 3 + posmod(next_col, 3)
	var candidate: Dictionary = vehicle.duplicate()
	if wrapped:
		var f: Vector2 = Math.forward(heading)
		var point: Vector2 = -f * 104.8 + Vector2(-f.y, f.x) * Junction.LANE_OFFSET
		candidate.x = point.x
		candidate.z = point.y
	else:
		candidate.x = float(vehicle.x) + centers[index].x - centers[target].x
		candidate.z = float(vehicle.z) + centers[index].y - centers[target].y
	for other in junctions[target].vehicles:
		if Math.overlap(candidate, other, 2.0):
			vehicle.speed = 0.0
			junctions[index].vehicles.append(vehicle)
			return
	candidate.cleared = false
	candidate.committed = false
	candidate.turning = false
	candidate.turn_path = {}
	candidate.hops = int(candidate.get("hops", 0)) + 1
	candidate.planned_turn = [0, 1, 0, -1, 0][(int(candidate.id) + int(candidate.hops)) % 5]
	junctions[target].vehicles.append(candidate)
	transfers += 1
	if wrapped: wraps += 1

func metrics() -> Dictionary:
	var total_speed: float = 0.0
	var queued: int = 0
	var total_wait: float = 0.0
	var incidents: int = 0
	var crossings: int = 0
	var turns: int = 0
	var blocked: int = 0
	for vehicle in vehicles:
		total_speed += float(vehicle.speed) * 3.6
		total_wait += float(vehicle.get("waiting_time", 0.0))
		if float(vehicle.speed) < 14.0 / 3.6: queued += 1
		if float(vehicle.get("incident_remaining", 0.0)) > 0.0: incidents += 1
	for junction in junctions:
		crossings += int(junction.statistics.crossings)
		turns += int(junction.statistics.turns)
		blocked += int(junction.statistics.blocked_moves)
	return {"vehicles": vehicles.size(), "speed_kmh": total_speed / maxf(1.0, vehicles.size()), "queued": queued, "mean_wait": total_wait / maxf(1.0, vehicles.size()), "crossings": crossings, "turns": turns, "incidents": incidents, "blocked_moves": blocked, "transfers": transfers}

func _sample() -> void:
	var summary: Dictionary = metrics()
	for index in range(9):
		var c = junctions[index].controller
		var total: float = 0.0
		for value in c.counts: total += value
		history[index].append(total)
		if history[index].size() > 60: history[index].pop_front()
		rows.append([roundi(next_sample), index + 1, mode, c.running_mode, c.stage, "+".join(c.active), c.counts[0], c.counts[1], c.counts[2], c.counts[3], c.queues[0], c.queues[1], c.queues[2], c.queues[3], summary.speed_kmh, summary.mean_wait, summary.crossings, int(junctions[index].sensor_enabled), int(c.fallback)])
	while rows.size() > 16200: rows.pop_front()

func csv_text() -> String:
	var lines := PackedStringArray(["tiempo_s,cruce,modo_solicitado,modo_activo,fase,accesos,C1,C2,C3,C4,cola_C1,cola_C2,cola_C3,cola_C4,velocidad_media_kmh,espera_acumulada_media_s,cruces_red,sensores,respaldo"])
	for values in rows:
		var fields := PackedStringArray()
		for value in values: fields.append(str(value))
		lines.append(",".join(fields))
	return "\n".join(lines) + "\n"

func config() -> Dictionary:
	var online: Array = []
	for junction in junctions: online.append(junction.sensor_enabled)
	return {"schema": 1, "mode": mode, "scenario": scenario, "detector_depth": detector_depth, "selected": selected, "sensors": online, "junctions": 9, "spacing": SPACING, "tick_hz": 60}

func snapshot() -> Dictionary:
	var nodes: Array = []
	for index in range(9):
		nodes.append({"id": index + 1, "x": centers[index].x, "z": centers[index].y, "controller": junctions[index].controller.snapshot(), "occupied": junctions[index].is_occupied(), "reservation": junctions[index].reservation})
	var poses: Array = []
	for vehicle in vehicles:
		var pose: Dictionary = vehicle.duplicate()
		pose.erase("turn_path")
		poses.append(pose)
	return {"simulation_time": simulation_time, "controller": controller.snapshot(), "junctions": nodes, "vehicles": poses, "metrics": metrics(), "config": config()}
