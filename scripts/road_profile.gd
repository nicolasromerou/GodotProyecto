extends RefCounted
## Perfil común al trazado de la referencia y al movimiento de los vehículos.
## Ejes: norte=-Z; frente de vehículo=+Z. Dos carriles de 3,5 m por sentido,
## con un carril interior activo en esta demo.
const Math = preload("res://scripts/traffic_math.gd")
const LANE_WIDTH: float = 3.5
const BASE_OFFSET: float = 1.75
const MEDIAN_WIDTH: float = 7.0
const STOP_LINE: float = 20.0
const TURN_ENTRY: float = 21.5
const CONFLICT_SIZE: float = 36.0
const RELEASE_DISTANCE: float = 30.0
var central: bool = false

func _init(is_central: bool = false) -> void:
	central = is_central

static func _smooth(t: float) -> float:
	return t * t * t * (10.0 + t * (-15.0 + 6.0 * t))

func north_extra(z: float) -> float:
	if not central: return 0.0
	if z < -65.0:
		return 3.5 * _smooth(clampf((105.0 + z) / 40.0, 0.0, 1.0))
	if z <= -TURN_ENTRY: return 3.5
	return 3.5 * (1.0 - _smooth(clampf((z + TURN_ENTRY) / (2.0 * TURN_ENTRY), 0.0, 1.0)))

func lane_offset(heading: int, longitudinal: float) -> float:
	var f: Vector2 = Math.forward(heading)
	return BASE_OFFSET + (north_extra(f.y * longitudinal) if heading % 2 == 0 else 0.0)

func point_for_straight(heading: int, longitudinal: float) -> Vector2:
	var f: Vector2 = Math.forward(heading)
	return f * longitudinal + Vector2(-f.y, f.x) * lane_offset(heading, longitudinal)

func pose_for_straight(heading: int, longitudinal: float) -> Dictionary:
	var point: Vector2 = point_for_straight(heading, longitudinal)
	var delta: Vector2 = point_for_straight(heading, longitudinal + 0.001) - point_for_straight(heading, longitudinal - 0.001)
	return {"x": point.x, "z": point.y, "yaw": atan2(delta.x, delta.y)}

func approach_offset(heading: int) -> float:
	return lane_offset(heading, -TURN_ENTRY)

func exit_offset(heading: int) -> float:
	return lane_offset(heading, TURN_ENTRY)

func turn_path(heading: int, turn: int) -> Dictionary:
	var next_heading: int = posmod(heading - turn, 4)
	return Math.make_turn_path(heading, turn, approach_offset(heading), TURN_ENTRY, exit_offset(next_heading))

func metadata() -> Dictionary:
	return {"reference": "calle/Cruce_Calles.png", "central_north_boulevard": central, "lane_width": LANE_WIDTH, "active_offset": BASE_OFFSET, "north_median_width": MEDIAN_WIDTH if central else 0.0, "stop_line": STOP_LINE, "turn_entry": TURN_ENTRY, "conflict_size": CONFLICT_SIZE}
