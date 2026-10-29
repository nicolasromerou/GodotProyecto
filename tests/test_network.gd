extends SceneTree
const Network = preload("res://scripts/network_world.gd")
const Math = preload("res://scripts/traffic_math.gd")
var passed: int = 0
var failed: int = 0

func check(value: bool, label: String) -> void:
	if value: passed += 1
	else:
		failed += 1
		push_error("FAIL " + label)
	print("PASS " if value else "FAIL ", label)

func safe(net) -> bool:
	for i in range(net.vehicles.size()):
		for j in range(i + 1, net.vehicles.size()):
			if Math.overlap(net.vehicles[i], net.vehicles[j]): return false
	for junction in net.junctions:
		var c = junction.controller
		var ns: bool = c.light("N") == "GREEN" or c.light("S") == "GREEN"
		var ew: bool = c.light("E") == "GREEN" or c.light("W") == "GREEN"
		if ns and ew: return false
	return true

func advance(net, seconds: float) -> void:
	for _i in range(roundi(seconds * 60)): net.tick(1.0 / 60.0)

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var net = Network.new()
	check(net.junctions.size() == 9 and net.vehicles.size() == 36, "Nueve cruces conectados y flota inicial de 36")
	for mode in ["fti", "adaptive", "fixed"]:
		net.load_scenario("normal")
		net.set_mode(mode)
		var ids: Dictionary = {}
		for car in net.vehicles: ids[int(car.id)] = true
		var valid: bool = true
		for step in range(7200):
			net.tick(1.0 / 60.0)
			if step % 10 == 0 and not safe(net):
				valid = false
				break
		check(valid, mode + ": 120 s sin solapamientos ni verdes conflictivos")
		var conserved: bool = net.vehicles.size() == 36
		var distinct: Dictionary = {}
		for car in net.vehicles:
			conserved = conserved and ids.has(int(car.id))
			distinct[int(car.id)] = true
		check(conserved and distinct.size() == 36, mode + ": conserva identidades sin duplicar ni perder vehículos")
		check(net.transfers > 10 and net.metrics().crossings > 20, mode + ": tráfico pasa entre cruces")
		check(net.rows.size() == 1080 and net.history[4].size() == 60, mode + ": muestreo por segundo y 60 s de historial")
		print("NETWORK_METRICS ", mode, " ", JSON.stringify(net.metrics()))
	net.load_scenario("empty")
	net.set_mode("fti")
	advance(net, 6)
	var all_red: bool = true
	for junction in net.junctions: all_red = all_red and junction.controller.stage == "ALL_RED"
	check(all_red and net.vehicles.is_empty(), "Sin demanda: los nueve cruces en rojo")
	net.load_scenario("peak_ns")
	check(net.vehicles.size() == 54 and safe(net), "Demanda asimétrica N–S con flota separada")
	net.set_mode("adaptive")
	net.set_sensor(4, false)
	advance(net, 15)
	check(net.junctions[4].controller.fallback and not net.junctions[3].controller.fallback, "Fallo aislado no afecta a los otros ocho cruces")
	check(net.junctions[4].controller.running_mode == "fixed", "Fallo entra en respaldo fijo con transición")
	net.set_sensor(4, true)
	advance(net, 20)
	check(not net.controller.fallback and net.controller.running_mode == "adaptive", "Restauración vuelve al modo solicitado")
	net.request_priority("EW")
	check(net.controller.priority == "EW", "Solicitud V2I se registra")
	advance(net, 21)
	check(net.controller.priority == "", "Prioridad caduca y no monopoliza el cruce")
	net.set_depth(200)
	check(net.detector_depth == 85.0 and net.junctions[0].detector_depth == 85.0, "Zonas configurables respetan límites")
	check(net.incident(), "Escenario de detención temporal disponible")
	advance(net, 13)
	check(net.metrics().incidents == 0, "Incidente se recupera sin teletransportar autos")
	check(net.csv_text().split("\n")[0].begins_with("tiempo_s,cruce") and JSON.parse_string(JSON.stringify(net.snapshot())) is Dictionary, "CSV y estado JSON válidos")
	check(not net.set_mode("bad") and not net.load_scenario("bad"), "Rechaza configuraciones desconocidas")
	for scenario in ["peak_ns", "peak_ew"]:
		net.load_scenario(scenario)
		net.set_mode("adaptive")
		var valid: bool = true
		for step in range(7200):
			net.tick(1.0 / 60.0)
			if step % 10 == 0 and not safe(net):
				valid = false
				break
		check(valid and net.vehicles.size() == 54 and net.transfers > 20, scenario + ": hora punta 120 s, transferencias y separación")
	net.load_scenario("empty")
	var rear: Dictionary = net.junctions[4].create_vehicle(1, -100.0)
	rear.cleared = true
	rear.speed = 14.0
	var front: Dictionary = net.junctions[5].create_vehicle(1, 99.0)
	front.incident_remaining = 5.0
	var boundary_safe: bool = true
	for _step in range(420):
		net.tick(1.0 / 60.0)
		boundary_safe = boundary_safe and safe(net)
	check(boundary_safe and net.vehicles.size() == 2, "Anticipa un vehículo detenido al otro lado del límite entre sectores")
	print("NETWORK_TESTS ", passed, " passed, ", failed, " failed")
	quit(0 if failed == 0 else 1)
