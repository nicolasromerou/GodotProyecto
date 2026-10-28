extends RefCounted
## Núcleo sin nodos visuales: un cruce, un carril por sentido y autos de prueba.
## La reserva exclusiva es deliberadamente conservadora para esta primera migración.
const Controller = preload("res://scripts/traffic_controller.gd")
const Math = preload("res://scripts/traffic_math.gd")
const APPROACH_FOR_HEADING := ["N", "W", "S", "E"]
const SENSOR_INDEX_FOR_HEADING := [0, 3, 2, 1]
const STOP_LINE: float = 15.4
const LANE_OFFSET: float = 3.5
const WORLD_LIMIT: float = 105.0

var controller = Controller.new()
var vehicles: Array = []
var simulation_time: float = 0.0
var sensor_enabled: bool = true
var auto_spawn: bool = true
var reservation: int = -1
var next_id: int = 1
var pending_spawns: Array = []
var statistics: Dictionary = {}

func _init(populate: bool = true) -> void:
	reset(populate)

func reset(populate: bool = true) -> void:
	var selected_mode: String = controller.mode
	controller = Controller.new(selected_mode)
	vehicles.clear()
	pending_spawns.clear()
	simulation_time = 0.0
	sensor_enabled = true
	auto_spawn = populate
	reservation = -1
	next_id = 1
	statistics = {"turns": 0, "crossings": 0, "departures": 0, "spawned": 0, "blocked_moves": 0, "max_step": 0.0}
	if populate:
		for distance: float in [35.0, 53.0, 71.0]:
			for heading in range(4):
				var turn: int = [0, 1, -1, 0, 1][next_id % 5]
				create_vehicle(heading, distance, turn)

func set_mode(mode: String) -> bool:
	if mode not in ["fti", "adaptive", "fixed"]:
		return false
	controller.mode = mode
	return true

func create_vehicle(heading: int, distance: float, planned_turn: int = 0) -> Dictionary:
	heading = posmod(heading, 4)
	var f: Vector2 = Math.forward(heading)
	var point: Vector2 = -f * distance + Vector2(-f.y, f.x) * LANE_OFFSET
	var vehicle: Dictionary = {"id": next_id, "x": point.x, "z": point.y, "yaw": Math.yaw_for(heading), "heading": heading, "origin_heading": heading, "length": 4.8, "width": 2.0, "speed": 0.0, "acceleration": 0.0, "desired_speed": 12.0 + float(next_id % 3), "planned_turn": clampi(planned_turn, -1, 1), "turning": false, "turn_path": {}, "turn_distance": 0.0, "committed": false, "cleared": false, "braking": true, "wheel_distance": 0.0, "steering_angle": 0.0}
	for other: Dictionary in vehicles:
		if Math.overlap(vehicle, other, 2.0):
			return {}
	vehicles.append(vehicle)
	next_id += 1
	statistics.spawned += 1
	return vehicle

func _distance_to_center(vehicle: Dictionary) -> float:
	return -Vector2(float(vehicle.x), float(vehicle.z)).dot(Math.forward(int(vehicle.heading)))

func is_occupied() -> bool:
	var center: Dictionary = {"x": 0.0, "z": 0.0, "yaw": 0.0, "length": 28.0, "width": 28.0}
	for vehicle: Dictionary in vehicles:
		if Math.overlap(vehicle, center):
			return true
	return false

func _sense() -> void:
	var counts: Array = [0, 0, 0, 0]
	var queues: Array = [0, 0, 0, 0]
	for vehicle: Dictionary in vehicles:
		if vehicle.cleared or vehicle.turning:
			continue
		var distance: float = _distance_to_center(vehicle)
		if distance >= STOP_LINE and distance <= STOP_LINE + 55.0:
			var index: int = SENSOR_INDEX_FOR_HEADING[int(vehicle.heading)]
			counts[index] += 1
			if float(vehicle.speed) < 2.0:
				queues[index] += 1
	controller.sense(counts, queues)

func _leader(vehicle: Dictionary) -> Dictionary:
	var f := Vector2(sin(float(vehicle.yaw)), cos(float(vehicle.yaw)))
	var r := Vector2(f.y, -f.x)
	var gap: float = INF
	var leader_speed: float = float(vehicle.desired_speed)
	for other: Dictionary in vehicles:
		if other.id == vehicle.id:
			continue
		var delta := Vector2(float(other.x) - float(vehicle.x), float(other.z) - float(vehicle.z))
		var longitudinal: float = delta.dot(f)
		if longitudinal > 0.0 and longitudinal < 85.0 and absf(delta.dot(r)) < float(vehicle.width) * 0.5 + Math.projected_half(other, r) + 0.35:
			var candidate: float = longitudinal - float(vehicle.length) * 0.5 - Math.projected_half(other, f)
			if candidate < gap:
				gap = candidate
				leader_speed = maxf(0.0, float(other.speed) * cos(float(other.yaw) - float(vehicle.yaw)))
	return {"gap": gap, "speed": leader_speed}

func _exit_blocked(vehicle: Dictionary) -> bool:
	var next_heading: int = posmod(int(vehicle.heading) - int(vehicle.planned_turn), 4)
	var f: Vector2 = Math.forward(next_heading)
	var point: Vector2 = f * 25.0 + Vector2(-f.y, f.x) * LANE_OFFSET
	var target: Dictionary = {"x": point.x, "z": point.y, "yaw": Math.yaw_for(next_heading), "length": 14.0, "width": 2.5}
	for other: Dictionary in vehicles:
		if other.id != vehicle.id and Math.overlap(target, other):
			return true
	return false

func tick(dt: float) -> void:
	if dt <= 0.0 or dt > 0.1:
		return # El llamante entrega pasos fijos; rechaza saltos que invalidan el frenado.
	simulation_time += dt
	if sensor_enabled:
		_sense()
	controller.step(dt, is_occupied())
	for vehicle: Dictionary in vehicles:
		if int(vehicle.id) == reservation and bool(vehicle.cleared) and _distance_to_center(vehicle) < -24.0:
			reservation = -1
	for vehicle: Dictionary in vehicles:
		_update_vehicle(vehicle, dt)
	var departed: Array = []
	for vehicle: Dictionary in vehicles:
		if bool(vehicle.cleared) and _distance_to_center(vehicle) < -WORLD_LIMIT:
			departed.append(vehicle)
	for vehicle: Dictionary in departed:
		vehicles.erase(vehicle)
		statistics.departures += 1
		if reservation == int(vehicle.id):
			reservation = -1
		if auto_spawn:
			pending_spawns.append(int(vehicle.origin_heading))
	if auto_spawn:
		var remaining: Array = []
		for heading: int in pending_spawns:
			var turn: int = [0, 1, -1, 0, 1][next_id % 5]
			if create_vehicle(heading, 100.0, turn).is_empty():
				remaining.append(heading)
		pending_spawns = remaining

func _update_vehicle(vehicle: Dictionary, dt: float) -> void:
	var previous := Vector2(float(vehicle.x), float(vehicle.z))
	var leader: Dictionary = _leader(vehicle)
	var gap: float = float(leader.gap)
	var leader_speed: float = float(leader.speed)
	var desired: float = float(vehicle.desired_speed)
	var distance: float = _distance_to_center(vehicle)
	if vehicle.turning:
		desired = 5.0 if int(vehicle.planned_turn) == 1 else 7.0 if int(vehicle.planned_turn) == -1 else desired
	elif not vehicle.cleared:
		var front_gap: float = distance - STOP_LINE - float(vehicle.length) * 0.5
		var light: String = controller.light(APPROACH_FOR_HEADING[int(vehicle.heading)])
		var stop_for_light: bool = light == "RED" or (light == "YELLOW" and front_gap > maxf(1.0, float(vehicle.speed) * float(vehicle.speed) / 14.0))
		if not bool(vehicle.committed):
			if stop_for_light and reservation == int(vehicle.id):
				reservation = -1
			if not stop_for_light and reservation == -1 and front_gap < 12.0 and not is_occupied() and not _exit_blocked(vehicle):
				reservation = int(vehicle.id)
			var blocked: bool = stop_for_light or reservation != int(vehicle.id) or _exit_blocked(vehicle)
			if blocked and front_gap < gap:
				gap = front_gap
				leader_speed = 0.0
		if int(vehicle.planned_turn) != 0 and distance < 45.0:
			desired = minf(desired, 5.0 if int(vehicle.planned_turn) == 1 else 7.0)
	var motion: Dictionary = Math.follow_speed(float(vehicle.speed), desired, gap, leader_speed, dt)
	var candidate: Dictionary = vehicle.duplicate()
	if vehicle.turning:
		candidate.turn_distance = minf(float(vehicle.turn_path.length), float(vehicle.turn_distance) + float(motion.distance))
		var pose: Dictionary = Math.path_pose(vehicle.turn_path, float(candidate.turn_distance))
		candidate.x = pose.x
		candidate.z = pose.z
		candidate.yaw = pose.yaw
	elif not vehicle.cleared and distance >= 16.5 and distance - float(motion.distance) < 16.5 and reservation == int(vehicle.id):
		candidate.turning = true
		candidate.turn_path = Math.make_turn_path(int(vehicle.heading), int(vehicle.planned_turn), LANE_OFFSET)
		candidate.turn_distance = maxf(0.0, float(motion.distance) - (distance - 16.5))
		var pose: Dictionary = Math.path_pose(candidate.turn_path, float(candidate.turn_distance))
		candidate.x = pose.x
		candidate.z = pose.z
		candidate.yaw = pose.yaw
		candidate.committed = true
		if int(vehicle.planned_turn) != 0:
			statistics.turns += 1
	else:
		var f: Vector2 = Math.forward(int(vehicle.heading))
		candidate.x = float(vehicle.x) + f.x * float(motion.distance)
		candidate.z = float(vehicle.z) + f.y * float(motion.distance)
		if not bool(vehicle.cleared) and reservation == int(vehicle.id) and distance - float(motion.distance) < STOP_LINE + float(vehicle.length) * 0.5:
			candidate.committed = true
	# No sustituye el seguimiento: última barrera SAT contra un avance que invada otro auto.
	for other: Dictionary in vehicles:
		if other.id != vehicle.id and Math.overlap(candidate, other, 0.1):
			vehicle.acceleration = -float(vehicle.speed) / dt
			vehicle.speed = 0.0
			vehicle.braking = true
			statistics.blocked_moves += 1
			return
	var old_yaw: float = float(vehicle.yaw)
	for key: String in ["x", "z", "yaw", "turning", "turn_path", "turn_distance", "committed"]:
		vehicle[key] = candidate[key]
	vehicle.speed = motion.speed
	vehicle.acceleration = motion.acceleration
	vehicle.braking = float(motion.acceleration) < -1.0 or float(motion.speed) < 0.2
	vehicle.wheel_distance += float(motion.distance)
	vehicle.steering_angle = clampf(wrapf(float(vehicle.yaw) - old_yaw, -PI, PI) / maxf(0.01, float(motion.distance)) * float(vehicle.length) * 0.55, -0.48, 0.48)
	if bool(vehicle.turning) and float(vehicle.turn_distance) >= float(vehicle.turn_path.length) - 0.0000001:
		vehicle.heading = vehicle.turn_path.next_heading
		vehicle.yaw = Math.yaw_for(int(vehicle.heading))
		vehicle.turning = false
		vehicle.cleared = true
		vehicle.steering_angle = 0.0
		statistics.crossings += 1
	statistics.max_step = maxf(float(statistics.max_step), previous.distance_to(Vector2(float(vehicle.x), float(vehicle.z))))

func snapshot() -> Dictionary:
	var cars: Array = []
	for vehicle: Dictionary in vehicles:
		var copy: Dictionary = vehicle.duplicate()
		copy.erase("turn_path")
		cars.append(copy)
	return {"simulation_time": simulation_time, "sensor_enabled": sensor_enabled, "reservation": reservation, "occupied": is_occupied(), "controller": controller.snapshot(), "vehicles": cars, "statistics": statistics.duplicate()}
