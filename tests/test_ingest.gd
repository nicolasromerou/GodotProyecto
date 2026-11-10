extends SceneTree
## Ejecutar: Godot --headless --path PROYECTO --script res://tests/test_ingest.gd
## Cubre lo que conecta la maqueta con la web: motivo de cada corte de verde (RF3),
## conteo por acceso y tipo (RF1, RNF4), lotes y cola local (RNF5) y la demanda abierta.
const Controller = preload("res://scripts/traffic_controller.gd")
const World = preload("res://scripts/traffic_world.gd")
const Network = preload("res://scripts/network_world.gd")
const Batcher = preload("res://scripts/ingest_batcher.gd")
const Math = preload("res://scripts/traffic_math.gd")
var passed: int = 0
var failed: int = 0

func check(value: bool, label: String) -> void:
	if value: passed += 1
	else:
		failed += 1
		push_error("FAIL " + label)
	print("PASS " if value else "FAIL ", label)

## Avanza el controlador con lecturas fijas hasta que corta un verde y devuelve el motivo.
func cut_after(controller: RefCounted, readings: Array, limit: float = 40.0) -> String:
	var was_green: bool = controller.stage == "GREEN"
	for _i in range(roundi(limit * 30.0)):
		controller.sense(readings)
		controller.step(1.0 / 30.0)
		if controller.stage == "GREEN": was_green = true
		if was_green and controller.stage == "YELLOW": return controller.cut_reason
	return ""

## Lleva un controlador adaptativo hasta un verde Norte–Sur recién iniciado.
func green_ns(readings: Array) -> RefCounted:
	var controller = Controller.new("adaptive")
	for _i in range(60):
		controller.sense(readings)
		controller.step(1.0 / 30.0)
	return controller

func safe(net) -> bool:
	for i in range(net.vehicles.size()):
		for j in range(i + 1, net.vehicles.size()):
			if Math.overlap(net.vehicles[i], net.vehicles[j]): return false
	return true

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	# --- Motivos de corte -------------------------------------------------------
	check(cut_after(Controller.new("fti"), [1, 1, 1, 1]) == "tiempo_fijo", "FTI corta por tiempo fijo")
	check(cut_after(Controller.new("fixed"), [1, 1, 1, 1]) == "tiempo_fijo", "Ciclo fijo corta por tiempo fijo")
	check(cut_after(Controller.new("adaptive"), [2, 2, 2, 2]) == "verde_maximo", "Adaptativo con colas parejas corta por verde máximo")
	var c = green_ns([1, 0, 1, 0])
	check(c.stage == "GREEN" and c.active == ["N", "S"], "Preparación: verde Norte–Sur")
	check(cut_after(c, [0, 2, 0, 0]) == "sin_demanda", "Verde vacío con demanda en el otro eje corta por falta de demanda")
	c = green_ns([1, 0, 1, 0])
	check(cut_after(c, [1, 3, 0, 2]) == "balance_colas", "Cola mayor en el otro eje corta por balance de colas")
	c = green_ns([1, 0, 1, 0])
	c.priority = "EW"
	check(cut_after(c, [1, 1, 1, 0]) == "prioridad", "Prioridad con demanda en su eje corta por prioridad")
	c = green_ns([1, 0, 1, 0])
	c.mode = "fixed"
	check(cut_after(c, [1, 0, 1, 0]) == "cambio_modo", "Cambiar de modo con el verde activo corta por cambio de modo")
	c = green_ns([1, 0, 1, 0])
	c.priority = "EW"
	var kept_green: bool = true
	for _i in range(roundi(12.0 * 30.0)):
		c.sense([1, 0, 1, 0])
		c.step(1.0 / 30.0)
		kept_green = kept_green and c.stage == "GREEN"
	check(kept_green, "Prioridad V2I sin vehículos en su eje no corta el verde en uso")

	# --- Conteo en la línea de detención -----------------------------------------
	var world = World.new(false)
	world.set_mode("adaptive")
	world.create_vehicle(0, 40.0, 0, "bus")
	world.create_vehicle(2, 40.0, 0, "pickup")
	world.create_vehicle(2, 60.0, 0, "suv")
	for _step in range(1800): world.tick(1.0 / 60.0)
	check(world.stop_line_counts == {"N|bus": 1, "S|camioneta": 1, "S|auto": 1}, "Cuenta por acceso y tipo al cruzar la línea de detención")
	check(int(world.statistics.stop_line_crossings) == int(world.statistics.crossings), "El conteo coincide con los cruces completados")

	var net = Network.new()
	net.load_scenario("peak_ns")
	net.set_mode("adaptive")
	for _step in range(7200): net.tick(1.0 / 60.0)
	var counted: int = 0
	var crossed: int = 0
	var inside: int = 0
	for junction in net.junctions:
		counted += int(junction.statistics.stop_line_crossings)
		crossed += int(junction.statistics.crossings)
		for vehicle in junction.vehicles:
			if bool(vehicle.get("counted", false)) and not bool(vehicle.cleared): inside += 1
	check(counted == crossed + inside and counted > 100, "En la red, cada paso por un cruce se cuenta una sola vez (RNF4)")

	# --- Lotes y cola local ------------------------------------------------------
	check(Batcher.iso(1793481303250) == "2026-10-31T21:15:03.250Z", "Fechas en ISO 8601 UTC con milisegundos")
	net.load_scenario("normal")
	net.set_mode("adaptive")
	var batcher = Batcher.new()
	var junction = net.junctions[4]
	var clock: int = 1793481300000
	for step in range(7200):
		net.tick(1.0 / 60.0)
		clock += 16 if step % 3 else 18
		batcher.observe(junction, clock)
	var kinds_ok: bool = not batcher.pending_events.is_empty()
	var cuts: int = 0
	var previous: String = ""
	var ordered: bool = true
	for event in batcher.pending_events:
		kinds_ok = kinds_ok and event.stage in ["GREEN", "YELLOW", "ALL_RED"] and event.running_mode == "adaptive"
		kinds_ok = kinds_ok and (event.motivo == null or (event.stage == "YELLOW" and event.motivo in Batcher.CUT_REASONS))
		if event.stage == "YELLOW":
			kinds_ok = kinds_ok and event.motivo != null
			cuts += 1
		ordered = ordered and String(event.ocurrido_en) > previous
		previous = event.ocurrido_en
	check(kinds_ok and cuts > 3, "Cada cambio de etapa es un evento y todo paso a amarillo lleva su motivo")
	check(ordered, "Ningún evento repite fecha: cruce y fecha identifican al evento")
	var total_counted: int = 0
	var minutes_ok: bool = batcher.pending_counts.size() > 0
	for row in batcher.pending_counts:
		total_counted += int(row.cantidad)
		minutes_ok = minutes_ok and String(row.minuto).ends_with(":00.000Z") and row.acceso in ["N", "E", "S", "W"] and row.tipo in ["auto", "camioneta", "bus"]
	check(minutes_ok, "Los conteos van por minuto cerrado, acceso y tipo")
	check(total_counted > 0 and total_counted <= int(junction.statistics.stop_line_crossings), "Los conteos en cola no superan lo que cruzó la línea")
	var state: Dictionary = batcher.state(junction, clock)
	check(state.keys() == ["reportado_en", "mode", "running_mode", "stage", "active", "counts", "sensor_age", "fallback", "reason"] and state.counts.size() == 4 and typeof(state.counts[0]) == TYPE_INT, "El latido lleva los campos del contrato")
	var events_before: int = batcher.pending_events.size()
	batcher.batch_size = 5
	var batch: Dictionary = batcher.next_batch(junction, clock)
	check(batch.cruce_id == "maqueta-01" and batch.eventos.size() == 5 and batch.has("estado") and batch.has("conteos"), "El lote respeta el tamaño máximo y nombra al cruce")
	batcher.retry()
	check(batcher.pending_events.size() == events_before, "Sin conexión, el lote se conserva en la cola")
	batcher.batch_size = 5
	batcher.next_batch(junction, clock)
	batcher.confirm()
	check(batcher.pending_events.size() == events_before - 5, "Un lote guardado sale de la cola")
	batcher.next_batch(junction, clock + 8 * 86400000)
	check(batcher.pending_events.is_empty() and batcher.pending_counts.is_empty(), "Lo que supera los 7 días que acepta la web se descarta")

	# Fase peatonal: para la web es un todo rojo y no genera eventos propios.
	net.load_scenario("empty")
	net.set_mode("adaptive")
	batcher = Batcher.new()
	junction = net.junctions[4]
	batcher.observe(junction, clock)
	net.request_pedestrian(4)
	var only_known: bool = true
	for step in range(600):
		net.tick(1.0 / 60.0)
		clock += 17
		batcher.observe(junction, clock)
		only_known = only_known and batcher.state(junction, clock).stage in ["GREEN", "YELLOW", "ALL_RED"]
	for event in batcher.pending_events: only_known = only_known and event.stage in ["GREEN", "YELLOW", "ALL_RED"]
	check(only_known, "La fase peatonal se informa como todo rojo")

	# Guardar y recuperar la cola.
	var path := "user://test-ingesta-cola.json"
	batcher = Batcher.new()
	batcher.pending_events = [{"ocurrido_en": "2026-11-01T02:35:03.250Z", "stage": "YELLOW", "active": ["N", "S"], "running_mode": "adaptive", "fallback": false, "motivo": "sin_demanda"}]
	batcher.pending_counts = [{"minuto": "2026-11-01T02:35:00.000Z", "acceso": "N", "tipo": "auto", "cantidad": 7}]
	var saved: bool = batcher.save(path)
	var restored = Batcher.new()
	var loaded: bool = restored.load_queue(path)
	check(saved and loaded and restored.pending_events == batcher.pending_events and restored.pending_counts.size() == 1 and typeof(restored.pending_counts[0].cantidad) == TYPE_INT and restored.pending_counts[0].cantidad == 7, "La cola se guarda y se recupera sin pérdidas")
	var other = Batcher.new()
	other.junction_id = "otro-cruce"
	check(not other.load_queue(path) and other.pending_events.is_empty(), "No carga la cola de otro cruce")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(path))

	# --- Demanda abierta ---------------------------------------------------------
	var first = Network.new()
	first.load_scenario("open")
	first.set_mode("adaptive")
	var second = Network.new()
	second.load_scenario("open")
	second.set_mode("adaptive")
	var open_safe: bool = true
	for step in range(10800):
		first.tick(1.0 / 60.0)
		second.tick(1.0 / 60.0)
		if step % 10 == 0: open_safe = open_safe and safe(first)
	var summary: Dictionary = first.metrics()
	check(open_safe and int(summary.blocked_moves) == 0, "Demanda abierta: 180 s sin solapamientos ni bloqueos")
	check(int(summary.arrivals) > 20 and int(summary.exits) > 20 and first.wraps == 0, "Los vehículos entran y salen por el borde; nadie da la vuelta")
	check(first.vehicles.size() == 36 + int(summary.arrivals) - int(summary.exits), "La flota es la inicial más llegadas menos salidas")
	check(JSON.stringify(first.snapshot()) == JSON.stringify(second.snapshot()), "La misma semilla reproduce la misma demanda")
	var types: Dictionary = {}
	for junction_open in first.junctions:
		for key in junction_open.stop_line_counts: types[String(key).get_slice("|", 1)] = true
	check(types.has("auto") and types.has("camioneta") and types.has("bus"), "La demanda abierta mezcla los tres tipos de vehículo")
	var quiet = Network.new()
	quiet.demand_multiplier = 0.0
	quiet.load_scenario("open")
	for _step in range(3600): quiet.tick(1.0 / 60.0)
	check(quiet.arrivals == 0, "Con multiplicador cero no llegan vehículos nuevos")
	var other_seed = Network.new()
	other_seed.demand_seed = 7
	other_seed.load_scenario("open")
	other_seed.set_mode("adaptive")
	for _step in range(10800): other_seed.tick(1.0 / 60.0)
	check(JSON.stringify(other_seed.snapshot()) != JSON.stringify(first.snapshot()), "Otra semilla produce otra demanda")
	print("OPEN_METRICS ", JSON.stringify(summary))
	print("INGEST_TESTS ", passed, " passed, ", failed, " failed")
	quit(0 if failed == 0 else 1)
