extends RefCounted
## Cinemática trasladada de traffic-physics.mjs. Metros, segundos, radianes.

static func follow_speed(speed: float, desired: float, gap: float, leader_speed: float, dt: float, accel: float = 3.0, brake: float = 7.0) -> Dictionary:
	var target: float = desired
	if is_finite(gap):
		var braking_buffer: float = brake * 0.9
		target = minf(target, maxf(0.0, sqrt(maxf(0.0, leader_speed * leader_speed + 2.0 * brake * maxf(0.0, gap - 1.4) + braking_buffer * braking_buffer)) - braking_buffer))
		target = minf(target, maxf(0.0, (gap - 1.4) / 1.2 + leader_speed * 0.35))
	var acceleration: float = clampf((target - speed) * 1.8, -brake, accel)
	var next_speed: float = maxf(0.0, speed + acceleration * dt)
	var distance: float = (speed + next_speed) * 0.5 * dt
	if is_finite(gap) and distance > maxf(0.0, gap - 0.2):
		distance = maxf(0.0, gap - 0.2)
		next_speed = minf(next_speed, distance / maxf(dt, 0.000001))
	return {"speed": next_speed, "distance": distance, "acceleration": (next_speed - speed) / maxf(dt, 0.000001)}

static func forward(heading: int) -> Vector2:
	return [Vector2(0, 1), Vector2(1, 0), Vector2(0, -1), Vector2(-1, 0)][posmod(heading, 4)]

static func yaw_for(heading: int) -> float:
	return [0.0, PI / 2.0, PI, -PI / 2.0][posmod(heading, 4)]

static func projected_half(pose: Dictionary, axis: Vector2) -> float:
	var f := Vector2(sin(float(pose.yaw)), cos(float(pose.yaw)))
	var r := Vector2(f.y, -f.x)
	return float(pose.length) * 0.5 * absf(f.dot(axis)) + float(pose.width) * 0.5 * absf(r.dot(axis))

static func overlap(a: Dictionary, b: Dictionary, margin: float = 0.0) -> bool:
	var delta := Vector2(float(b.x) - float(a.x), float(b.z) - float(a.z))
	var bound: float = (float(a.length) + float(a.width) + float(b.length) + float(b.width)) * 0.5 + margin
	if absf(delta.x) > bound or absf(delta.y) > bound or delta.length_squared() > bound * bound:
		return false
	var af := Vector2(sin(float(a.yaw)), cos(float(a.yaw)))
	var bf := Vector2(sin(float(b.yaw)), cos(float(b.yaw)))
	for axis: Vector2 in [af, Vector2(af.y, -af.x), bf, Vector2(bf.y, -bf.x)]:
		if projected_half(a, axis) + projected_half(b, axis) + margin - absf(delta.dot(axis)) <= 0.00000001:
			return false
	return true

static func cubic_point(points: Array, t: float) -> Dictionary:
	var u: float = 1.0 - t
	var point: Vector2 = points[0] * u * u * u + points[1] * 3.0 * u * u * t + points[2] * 3.0 * u * t * t + points[3] * t * t * t
	var derivative: Vector2 = (points[1] - points[0]) * 3.0 * u * u + (points[2] - points[1]) * 6.0 * u * t + (points[3] - points[2]) * 3.0 * t * t
	return {"x": point.x, "z": point.y, "yaw": atan2(derivative.x, derivative.y)}

static func make_turn_path(heading: int, turn: int, offset: float = 3.5, entry: float = 16.5) -> Dictionary:
	var next_heading: int = posmod(heading - turn, 4)
	var f: Vector2 = forward(heading)
	var g: Vector2 = forward(next_heading)
	var start: Vector2 = -f * entry + Vector2(-f.y, f.x) * offset
	var finish: Vector2 = g * entry + Vector2(-g.y, g.x) * offset
	var radius: float = entry - offset if turn == 1 else entry + offset
	var k: float = 0.55228475 * radius if turn != 0 else entry * 2.0 / 3.0
	var points: Array = [start, start + f * k, finish - g * k, finish]
	var length: float = 0.0
	var previous: Vector2 = start
	var samples: Array = [{"t": 0.0, "s": 0.0}]
	for i in range(1, 81):
		var t: float = float(i) / 80.0
		var pose: Dictionary = cubic_point(points, t)
		var current := Vector2(float(pose.x), float(pose.z))
		length += current.distance_to(previous)
		samples.append({"t": t, "s": length})
		previous = current
	return {"points": points, "samples": samples, "length": length, "next_heading": next_heading, "heading": heading, "turn": turn}

static func path_pose(path: Dictionary, distance: float) -> Dictionary:
	var s: float = clampf(distance, 0.0, float(path.length))
	var samples: Array = path.samples
	var low: int = 0
	var high: int = samples.size() - 1
	while high - low > 1:
		var middle: int = (low + high) / 2
		if float(samples[middle].s) < s:
			low = middle
		else:
			high = middle
	var a: Dictionary = samples[low]
	var b: Dictionary = samples[high]
	var t: float = float(a.t) + (float(b.t) - float(a.t)) * (s - float(a.s)) / maxf(0.00000001, float(b.s) - float(a.s))
	return cubic_point(path.points, t)
