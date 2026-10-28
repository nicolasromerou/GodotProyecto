extends SceneTree
## Run: Godot --headless --path PROJECT --script res://tests/test_controller.gd
## Optional JS reference trace: -- --parity-fixture=absolute/path.json

const Controller = preload("res://scripts/traffic_controller.gd")
var checks: int = 0
var failures: int = 0

func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error("FAIL: " + message)

func run_for(controller: RefCounted, seconds: float, readings: Variant = [0, 0, 0, 0], occupied: bool = false) -> void:
	for _i in range(roundi(seconds * 30.0)):
		if readings != null:
			controller.sense(readings)
		controller.step(1.0 / 30.0, occupied)

func _initialize() -> void:
	var c = Controller.new()
	run_for(c, 25.0)
	check(c.stage == "ALL_RED" and c.active.is_empty(), "FTI without demand stays all red")
	c = Controller.new()
	run_for(c, 1.1, [0, 3, 0, 0])
	check(c.stage == "GREEN" and c.active == ["E"], "FTI skips empty approaches")
	c = Controller.new()
	run_for(c, 1.1, [1, 1, 1, 1])
	c.elapsed = 0.0
	run_for(c, 4.9, [1, 1, 1, 1])
	check(c.stage == "GREEN", "FTI green lasts five seconds")
	run_for(c, 0.2, [1, 1, 1, 1])
	check(c.stage == "YELLOW", "FTI transitions to yellow")
	c.elapsed = 0.0
	run_for(c, 1.9, [1, 1, 1, 1])
	check(c.stage == "YELLOW", "FTI yellow lasts two seconds")
	run_for(c, 0.2, [1, 1, 1, 1])
	check(c.stage == "ALL_RED", "Yellow transitions to all red")
	run_for(c, 0.9, [1, 1, 1, 1])
	check(c.stage == "ALL_RED", "Minimum all-red clearance")
	run_for(c, 0.2, [1, 1, 1, 1])
	check(c.active == ["E"], "FTI advances to next approach")
	c = Controller.new()
	var served: Array = []
	var last: String = ""
	var exclusive: bool = true
	for _i in range(1100):
		c.sense([1, 1, 1, 1])
		c.step(1.0 / 30.0)
		if c.stage == "GREEN" and c.active[0] != last:
			served.append(c.active[0])
			last = c.active[0]
		exclusive = exclusive and c.active.size() <= 1
	check(served.slice(0, 4) == Controller.APPROACHES and exclusive, "C1/C2/C3/C4 round robin, exclusive green")
	c = Controller.new()
	run_for(c, 20.0, [1, 1, 1, 1], true)
	check(c.stage == "ALL_RED", "Occupied junction blocks new green")
	run_for(c, 0.1, [1, 1, 1, 1])
	check(c.stage == "GREEN", "Empty junction releases green after clearance")
	c = Controller.new()
	run_for(c, 1.1, [1, 0, 0, 0])
	run_for(c, 4.9, null)
	check(not c.fallback, "No early sensor fallback")
	run_for(c, 0.2, null)
	check(c.fallback, "Sensor timeout after five seconds")
	run_for(c, 4.0, null)
	check(c.running_mode == "fixed", "Timeout selects fixed backup safely")
	c = Controller.new()
	run_for(c, 12.0, null)
	run_for(c, 0.1, [1, 0, 0, 0])
	check(c.stage == "YELLOW", "Sensor recovery finishes yellow first")
	run_for(c, 5.0, [1, 0, 0, 0])
	check(c.running_mode == "fti" and c.active == ["N"], "Sensor recovery returns to selected mode")
	c = Controller.new("fixed")
	run_for(c, 1.1)
	check(c.stage == "GREEN" and c.active == ["N", "S"], "Fixed mode serves axis without demand")
	c = Controller.new()
	run_for(c, 1.1, [1, 1, 1, 1])
	c.mode = "adaptive"
	run_for(c, 0.1, [1, 1, 1, 1])
	check(c.stage == "YELLOW" and c.active == ["N"], "Mode change keeps original yellow approaches")
	run_for(c, 4.0, [1, 1, 1, 1])
	check(c.running_mode == "adaptive" and c.active.size() == 2, "Adaptive starts after yellow and clearance")
	c = Controller.new("adaptive")
	c.priority = "NS"
	run_for(c, 1.1, [2, 2, 0, 0])
	check(c.active == ["N", "S"], "V2I priority with demand")
	c.priority = "EW"
	run_for(c, 7.0, [2, 2, 0, 0])
	check(c.stage == "YELLOW", "V2I does not skip yellow")
	run_for(c, 4.0, [2, 2, 0, 0])
	check(c.active == ["E", "W"], "V2I selects other axis after clearance")
	check(Controller.detect_approach(-3, -35, 0, 0, 0) == 0, "Sensor north")
	check(Controller.detect_approach(35, -3, 3, 0, 0) == 1, "Sensor east")
	check(Controller.detect_approach(3, 35, 2, 0, 0) == 2, "Sensor south")
	check(Controller.detect_approach(-35, 3, 1, 0, 0) == 3, "Sensor west")
	check(Controller.detect_approach(3, 35, 0, 0, 0) == -1, "Exclude outgoing cars")
	check(Controller.detect_approach(-3, -14, 0, 0, 0) == -1, "Exclude interior")
	check(Controller.detect_approach(-20, -35, 0, 0, 0) == -1, "Exclude outside lanes")
	check(Controller.detect_approach(-3, -100, 0, 0, 0) == -1, "Exclude beyond depth")
	_test_long_run()
	var fixture_path: String = "res://tests/reference_controller.json"
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--parity-fixture="):
			fixture_path = argument.trim_prefix("--parity-fixture=")
	if FileAccess.file_exists(fixture_path):
		_test_reference(fixture_path)
	print("Controller: %d checks; %d failures" % [checks, failures])
	quit(0 if failures == 0 else 1)

func _test_long_run() -> void:
	for selected_mode in ["fti", "adaptive", "fixed"]:
		var c = Controller.new(selected_mode)
		var safe: bool = true
		for i in range(18000):
			if i % 900 < 650:
				c.sense([i % 3, floori(i / 60.0) % 4, 1, 2])
			c.priority = "EW" if i % 1300 < 100 else ""
			c.step(1.0 / 30.0, i % 400 < 10)
			var ns: bool = c.light("N") == "GREEN" or c.light("S") == "GREEN"
			var ew: bool = c.light("E") == "GREEN" or c.light("W") == "GREEN"
			safe = safe and not (ns and ew) and ["GREEN", "YELLOW", "ALL_RED"].has(c.stage)
			if c.running_mode == "fti":
				safe = safe and c.active.size() <= 1
		check(safe, "Long-run phase exclusion in " + selected_mode)

func _test_reference(path: String) -> void:
	# Fixture: [{initial_mode, steps:[{dt,counts?,queues?,mode?,priority?,occupied?,expected}]}]
	# expected contains any snapshot() keys. Numeric values tolerate 1e-7.
	var file = FileAccess.open(path, FileAccess.READ)
	check(file != null, "Reference fixture opens")
	if file == null:
		return
	var scenarios: Variant = JSON.parse_string(file.get_as_text())
	check(scenarios is Array, "Reference fixture is array")
	if not scenarios is Array:
		return
	var matched: bool = true
	var steps_checked: int = 0
	for scenario in scenarios:
		var c = Controller.new(scenario.get("initial_mode", "fti"))
		for entry in scenario.steps:
			if entry.has("mode"):
				c.mode = entry.mode
			if entry.has("priority"):
				c.priority = "" if entry.priority == null else entry.priority
			if entry.get("counts") != null:
				c.sense(entry.counts, entry.get("queues"))
			c.step(float(entry.dt), entry.get("occupied", false))
			if not _same(c.snapshot(), entry.expected):
				push_error("Reference mismatch at scenario %s step %d" % [scenario.get("initial_mode", "fti"), steps_checked])
				matched = false
				break
			steps_checked += 1
	check(matched and steps_checked > 0, "JS parity over %d reference steps" % steps_checked)
	print("JS controller parity: %d snapshots; %s" % [steps_checked, "PASS" if matched and steps_checked > 0 else "FAIL"])

func _same(actual: Variant, expected: Variant) -> bool:
	if expected is Dictionary:
		if not actual is Dictionary:
			return false
		for key in expected:
			if not actual.has(key) or not _same(actual[key], expected[key]):
				return false
		return true
	if expected is Array:
		if not actual is Array or actual.size() != expected.size():
			return false
		for i in range(expected.size()):
			if not _same(actual[i], expected[i]):
				return false
		return true
	if (expected is float or expected is int) and (actual is float or actual is int):
		return absf(float(actual) - float(expected)) < 0.0000001
	return actual == expected
