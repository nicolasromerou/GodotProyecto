extends RefCounted
## Nueve cruces conectados. Cada coche tiene un único propietario; los vecinos
## aportan poses de consulta para frenar también en los límites entre sectores.
const Junction = preload("res://scripts/traffic_world.gd")
const Math = preload("res://scripts/traffic_math.gd")
const SPACING: float = 210.0
const SCENARIOS = ["normal", "peak_ns", "peak_ew", "empty", "open"]
## Escenario "open": la red deja de ser un circuito cerrado. Los vehículos llegan por
## las 12 entradas del borde según un proceso aleatorio con semilla y salen por el
## borde opuesto. Así la demanda varía en el tiempo y las estadísticas tienen forma.
## Llegadas por segundo y por entrada cuando el multiplicador vale 1 (hora punta).
const OPEN_BASE_RATE: float = 0.03
## Llegadas que una entrada bloqueada puede dejar en espera antes de descartarlas.
const OPEN_BACKLOG_LIMIT: int = 4
## Proporción de la demanda por hora del día (0 a 23) respecto de la hora punta.
## Son valores de simulación con dos puntas, mañana y tarde; no provienen de un aforo.
const HOURLY_PROFILE = [0.10, 0.06, 0.05, 0.05, 0.08, 0.20, 0.45, 0.90, 1.00, 0.75, 0.60, 0.62, 0.70, 0.72, 0.62, 0.60, 0.68, 0.85, 1.00, 0.90, 0.60, 0.40, 0.25, 0.15]
## Reparto de tipos en las llegadas: 70 % auto, 22 % camioneta, 8 % bus.
const OPEN_MIX = [["suv", 0.70], ["pickup", 0.92], ["bus", 1.0]]
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
var open_network: bool = false
## Misma semilla, mismas llegadas: el escenario abierto se puede repetir.
var demand_seed: int = 20261110
## Lo fija quien usa la red (la vista, según la hora local). El núcleo no lee el reloj.
var demand_multiplier: float = 1.0
var arrivals: int = 0
var exits: int = 0
var rejected_arrivals: int = 0
var entry_backlog: Array[int] = []
var rng := RandomNumberGenerator.new()
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
	open_network = key == "open"
	arrivals = 0
	exits = 0
	rejected_arrivals = 0
	entry_backlog.assign([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
	rng.seed = demand_seed
	sensor_enabled = true
	for index in range(9):
		var junction = Junction.new(false)
		junction.configure_profile(index == 4)
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

func add_vehicle(junction_index: int, approach: String) -> Dictionary:
	var approach_index: int = ["N", "E", "S", "W"].find(approach)
	if junction_index < 0 or junction_index >= junctions.size() or approach_index < 0:
		return {}
	_refresh_external_vehicles()
	var heading: int = [0, 3, 2, 1][approach_index]
	var vehicle: Dictionary = {}
	for distance: float in [95.0, 83.0, 71.0, 59.0, 47.0, 35.0, 23.0]:
		vehicle = junctions[junction_index].create_vehicle(heading, distance)
		if not vehicle.is_empty(): break
	if vehicle.is_empty():
		return {}
	_refresh_vehicles()
	log_event("I-%d · vehículo %d agregado por acceso %s" % [junction_index + 1, vehicle.id, approach])
	return vehicle

func add_demand(junction_index: int, quantities: Array) -> Dictionary:
	if junction_index < 0 or junction_index >= junctions.size() or quantities.size() != 4:
		return {}
	var requested: Array[int] = []
	for quantity in quantities:
		if typeof(quantity) != TYPE_INT or int(quantity) < 0 or int(quantity) > 30:
			return {}
		requested.append(int(quantity))
	var added: Array[int] = [0, 0, 0, 0]
	var approaches := ["N", "E", "S", "W"]
	for index in range(4):
		for _vehicle_index in range(requested[index]):
			if add_vehicle(junction_index, approaches[index]).is_empty():
				break
			added[index] += 1
	log_event("I-%d · demanda solicitada N/E/S/O %s; agregada %s" % [junction_index + 1, str(requested), str(added)])
	return {"requested": requested, "added": added}

func request_pedestrian(junction_index: int) -> bool:
	if junction_index < 0 or junction_index >= junctions.size():
		return false
	if not junctions[junction_index].controller.request_pedestrian():
		return false
	log_event("I-%d · solicitud peatonal; esperando despeje seguro" % (junction_index + 1))
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

func _refresh_external_vehicles() -> void:
	_refresh_vehicles()
	for index in range(9):
		var junction = junctions[index]
		junction.external_vehicles.clear()
		for global_pose in vehicles:
			if int(global_pose.junction) == index: continue
			var delta := _torus_delta(Vector2(float(global_pose.x), float(global_pose.z)) - centers[index])
			if absf(delta.x) < 195.0 and absf(delta.y) < 195.0:
				var local: Dictionary = global_pose.duplicate()
				local.x = delta.x
				local.z = delta.y
				junction.external_vehicles.append(local)

## La red es un toro de 3 × 3: quien sale por un borde entra por el opuesto. Esta
## función lleva una diferencia de posiciones al camino más corto sobre ese toro,
## para que los cruces del borde también vean a los vecinos del otro lado.
func _torus_delta(delta: Vector2) -> Vector2:
	# En la red abierta los bordes no se conectan: no hay vecinos del otro lado.
	if open_network: return delta
	var half: float = SPACING * 1.5
	return Vector2(wrapf(delta.x, -half, half), wrapf(delta.y, -half, half))

func tick(dt: float) -> void:
	if dt <= 0.0 or dt > 0.1: return
	simulation_time += dt
	# Todas las consultas vecinas corresponden al inicio del mismo paso.
	_refresh_external_vehicles()
	for index in range(9):
		var junction = junctions[index]
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
	if open_network: _spawn_arrivals(dt)
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
	if wrapped and open_network:
		exits += 1
		return
	var target: int = posmod(next_row, 3) * 3 + posmod(next_col, 3)
	var candidate: Dictionary = vehicle.duplicate()
	# Misma posición física vista desde el cruce de destino, también al dar la
	# vuelta por el borde: el coche no salta hacia delante ni hacia atrás.
	var local: Vector2 = _torus_delta(Vector2(float(vehicle.x), float(vehicle.z)) + centers[index] - centers[target])
	candidate.x = local.x
	candidate.z = local.y
	# El margen debe ser menor que la separación lateral entre carriles opuestos
	# (1,3 m entre dos buses). Con 2 m, una cola del sentido contrario impedía el
	# traspaso y el coche seguía avanzando dentro del sector vecino sin pertenecerle.
	for other in junctions[target].vehicles:
		if Math.overlap(candidate, other, 0.1):
			vehicle.speed = 0.0
			junctions[index].vehicles.append(vehicle)
			return
	candidate.cleared = false
	candidate.counted = false
	candidate.committed = false
	candidate.turning = false
	candidate.turn_path = {}
	candidate.hops = int(candidate.get("hops", 0)) + 1
	candidate.planned_turn = [0, 1, 0, -1, 0][(int(candidate.id) + int(candidate.hops)) % 5]
	junctions[target].vehicles.append(candidate)
	transfers += 1
	if wrapped: wraps += 1

## Las 12 entradas del borde, en orden fijo: sentido de marcha 0 (hacia el sur) por
## la fila norte, 1 (hacia el este) por la columna oeste, 2 por la fila sur y 3 por
## la columna este. Devuelve pares [cruce, sentido].
func _entries() -> Array:
	var result: Array = []
	for slot in range(3):
		result.append([slot, 0])
		result.append([slot * 3, 1])
		result.append([6 + slot, 2])
		result.append([slot * 3 + 2, 3])
	return result

func _spawn_arrivals(dt: float) -> void:
	var entries: Array = _entries()
	var chance: float = OPEN_BASE_RATE * clampf(demand_multiplier, 0.0, 2.0) * dt
	for slot in range(entries.size()):
		# Llegadas de Poisson: en un paso corto, la probabilidad de una llegada es tasa × dt.
		if rng.randf() < chance:
			if entry_backlog[slot] < OPEN_BACKLOG_LIMIT: entry_backlog[slot] += 1
			else: rejected_arrivals += 1
		if entry_backlog[slot] == 0: continue
		# Los tres sorteos se hacen siempre, quepa o no el vehículo, para que la
		# secuencia aleatoria no dependa de si la entrada estaba ocupada.
		var draw: float = rng.randf()
		var turn: int = [0, 1, 0, -1, 0][rng.randi_range(0, 4)]
		var model: String = "suv"
		for option in OPEN_MIX:
			if draw <= float(option[1]):
				model = option[0]
				break
		var junction = junctions[int(entries[slot][0])]
		if not junction.create_vehicle(int(entries[slot][1]), 100.0, turn, model).is_empty():
			entry_backlog[slot] -= 1
			arrivals += 1

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
	return {"vehicles": vehicles.size(), "speed_kmh": total_speed / maxf(1.0, vehicles.size()), "queued": queued, "mean_wait": total_wait / maxf(1.0, vehicles.size()), "crossings": crossings, "turns": turns, "incidents": incidents, "blocked_moves": blocked, "transfers": transfers, "arrivals": arrivals, "exits": exits, "rejected_arrivals": rejected_arrivals}

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
	var profiles: Array = []
	for junction in junctions:
		online.append(junction.sensor_enabled)
		profiles.append(junction.road_profile.metadata())
	return {"schema": 2, "mode": mode, "scenario": scenario, "detector_depth": detector_depth, "selected": selected, "sensors": online, "junctions": 9, "spacing": SPACING, "tick_hz": 60, "road_profile": junctions[selected].road_profile.metadata(), "road_profiles": profiles}

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
