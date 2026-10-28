extends SceneTree
## Headless snapshot runner, not the GUI's live world.
const World = preload("res://scripts/traffic_world.gd")

func _initialize() -> void:
	var mode := "fti"
	var seconds := 30.0
	var sensor_enabled := true
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("mode="):
			mode = arg.trim_prefix("mode=")
		elif arg.begins_with("seconds="):
			seconds = arg.trim_prefix("seconds=").to_float()
		elif arg.begins_with("sensor_enabled="):
			sensor_enabled = arg.trim_prefix("sensor_enabled=") == "true"
	if mode not in ["fti", "adaptive", "fixed"] or not is_finite(seconds) or seconds < 0.0 or seconds > 120.0:
		push_error("Argumentos de simulación fuera de rango")
		quit(2)
		return
	var world = World.new()
	world.reset()
	world.set_mode(mode)
	world.sensor_enabled = sensor_enabled
	var steps := int(round(seconds * 60.0))
	for _step in range(steps):
		world.tick(1.0 / 60.0)
	print("FTI_JSON:" + JSON.stringify(world.snapshot()))
	quit(0)
