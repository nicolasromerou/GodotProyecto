class_name FTITrafficController
extends RefCounted
## Port of the simulator's deterministic controller. No rendering, serial or camera dependency.
## Approach order: C1=N, C2=E, C3=S, C4=W. Speeds/times use metres and seconds.

const APPROACHES := ["N", "E", "S", "W"]
const GROUPS := {"NS": ["N", "S"], "EW": ["E", "W"]}

var mode: String = "fti"
var running_mode: String = "fti"
var stage: String = "ALL_RED"
var active: Array = []
var elapsed: float = 0.0
var counts: Array = [0.0, 0.0, 0.0, 0.0]
var queues: Array = [0.0, 0.0, 0.0, 0.0]
var sensor_age: float = 0.0
var cursor: int = 3
var last_axis: String = "EW"
var wait: Array = [0.0, 0.0, 0.0, 0.0]
## Empty string means no priority. Otherwise use NS or EW.
var priority: String = ""
var clearance: float = 1.0
var fallback: bool = false
var reason: String = "Esperando demanda"

func _init(selected_mode: String = "fti") -> void:
	mode = selected_mode
	running_mode = selected_mode

func sense(new_counts: Array, new_queues: Variant = null) -> void:
	counts = _sanitize_readings(new_counts)
	queues = _sanitize_readings(new_counts if new_queues == null else new_queues)
	sensor_age = 0.0

func _sanitize_readings(values: Array) -> Array:
	var result: Array = [0.0, 0.0, 0.0, 0.0]
	for i in range(mini(4, values.size())):
		var number: float = float(values[i]) if values[i] != null else 0.0
		result[i] = maxf(0.0, number) if is_finite(number) else 0.0
	return result

func light(approach: String) -> String:
	return stage if active.has(approach) else "RED"

func yellow_duration() -> float:
	return 2.0 if running_mode == "fti" else 2.5

func green_duration() -> float:
	return 5.0 if running_mode == "fti" else (11.0 if running_mode == "fixed" else 16.0)

func step(dt: float, occupied: bool = false) -> void:
	sensor_age += dt
	elapsed += dt
	fallback = sensor_age >= 5.0
	var requested: String = "fixed" if fallback else mode
	for i in range(4):
		wait[i] = wait[i] + dt if counts[i] > 0.0 and light(APPROACHES[i]) != "GREEN" else 0.0
	# Algorithm changes and sensor loss must finish yellow and clearance first.
	if requested != running_mode and stage == "GREEN":
		stage = "YELLOW"
		elapsed = 0.0
		reason = "Transición de modo"
	if stage == "YELLOW":
		if elapsed >= yellow_duration():
			stage = "ALL_RED"
			elapsed = 0.0
			active = []
		return
	if stage == "ALL_RED":
		if elapsed < clearance or occupied:
			reason = "Despejando vehículos dentro del cruce" if occupied else "Intervalo de despeje"
			return
		running_mode = requested
		if requested == "fti":
			for offset in range(1, 5):
				var idx: int = (cursor + offset) % 4
				if counts[idx] > 0.0:
					cursor = idx
					active = [APPROACHES[idx]]
					stage = "GREEN"
					elapsed = 0.0
					reason = "Demanda C%d: turno de 5 s" % (idx + 1)
					return
			reason = "Sin demanda: los cuatro accesos en rojo"
			return
		var axis: String = "EW" if last_axis == "NS" else "NS"
		if requested == "adaptive":
			var ns: float = queues[0] + queues[2]
			var ew: float = queues[1] + queues[3]
			if _priority_has_demand():
				axis = priority
			elif ns == 0.0 and ew > 0.0:
				axis = "EW"
			elif ew == 0.0 and ns > 0.0:
				axis = "NS"
			elif active.is_empty() and float(wait.max()) > 25.0:
				axis = "NS" if wait[0] + wait[2] >= wait[1] + wait[3] else "EW"
		active = GROUPS[axis].duplicate()
		last_axis = axis
		stage = "GREEN"
		elapsed = 0.0
		if fallback:
			reason = "Respaldo fijo por pérdida de sensores"
		elif requested == "fixed":
			reason = "Alternancia fija de 11 s"
		elif priority == axis:
			reason = "Prioridad V2I con transición"
		else:
			reason = "Balance de colas y espera"
		return
	if stage == "GREEN":
		var end_turn: bool = elapsed >= green_duration()
		if running_mode == "adaptive":
			var current: float = 0.0
			for approach in active:
				current += queues[APPROACHES.find(approach)]
			var other: float = 0.0
			for queue in queues:
				other += queue
			other -= current
			end_turn = end_turn or (elapsed >= 6.5 and other > current + 1.0)
			end_turn = end_turn or (elapsed >= 4.0 and current == 0.0 and other > 0.0)
			end_turn = end_turn or (elapsed >= 6.5 and not priority.is_empty() and priority != last_axis)
		if end_turn:
			stage = "YELLOW"
			elapsed = 0.0
			reason = "Fin de turno: amarillo"

func _priority_has_demand() -> bool:
	if not GROUPS.has(priority):
		return false
	for approach in GROUPS[priority]:
		if counts[APPROACHES.find(approach)] > 0.0:
			return true
	return false

func snapshot() -> Dictionary:
	return {
		"mode": mode, "running_mode": running_mode, "stage": stage,
		"active": active.duplicate(), "elapsed": elapsed,
		"counts": counts.duplicate(), "queues": queues.duplicate(),
		"sensor_age": sensor_age, "cursor": cursor, "last_axis": last_axis,
		"wait": wait.duplicate(), "priority": priority, "clearance": clearance,
		"fallback": fallback, "reason": reason,
	}

static func detect_approach(x: float, z: float, heading: int, inter_x: float, inter_z: float, depth: float = 55.0) -> int:
	# Original HTML headings: 0=south(+Z), 1=east(+X), 2=north(-Z), 3=west(-X).
	var dx: float = x - inter_x
	var dz: float = z - inter_z
	var stop: float = 15.4
	var far: float = stop + depth
	if heading == 0 and dx <= 0.0 and dx >= -12.0 and -dz >= stop and -dz <= far:
		return 0
	if heading == 3 and dz <= 0.0 and dz >= -12.0 and dx >= stop and dx <= far:
		return 1
	if heading == 2 and dx >= 0.0 and dx <= 12.0 and dz >= stop and dz <= far:
		return 2
	if heading == 1 and dz >= 0.0 and dz <= 12.0 and -dx >= stop and -dx <= far:
		return 3
	return -1
