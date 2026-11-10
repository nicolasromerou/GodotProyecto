extends RefCounted
## Arma los lotes que Godot envía a POST /api/ingesta de la web (H3 del backlog).
## No usa nodos ni red: solo observa un cruce y guarda lo pendiente, así se prueba
## sin abrir la ventana. El contrato está en webControl/docs/api-ingesta.md.
##
## Qué produce:
##   estado  -> el latido: la foto del controlador en este instante.
##   eventos -> un registro por cada cambio de etapa, con el motivo si se cortó un verde.
##   conteos -> vehículos que cruzaron la línea de detención, por minuto, acceso y tipo.
## Eventos y conteos quedan en una cola hasta que la web confirma que los guardó (RNF5).

const APPROACHES := ["N", "E", "S", "W"]
const VEHICLE_TYPES := ["auto", "camioneta", "bus"]
const CUT_REASONS := ["sin_demanda", "verde_maximo", "tiempo_fijo", "balance_colas", "prioridad", "cambio_modo"]
## La web acepta fechas de hasta 7 días atrás; lo más antiguo ya no se puede entregar.
const MAX_AGE_SECONDS: float = 7.0 * 86400.0
## Tope de la cola en memoria y en disco. A un cambio de etapa por segundo son unas
## 5 horas sin conexión; pasado el tope se descarta lo más antiguo.
const MAX_PENDING: int = 20000
## Elementos por lote. La web admite 2000 de cada uno y 512 KB; 500 deja margen.
const DEFAULT_BATCH_SIZE: int = 500

var junction_id: String = "maqueta-01"
var batch_size: int = DEFAULT_BATCH_SIZE
var pending_events: Array = []
var pending_counts: Array = []
## Cuántos elementos del frente de cada cola viajan en el lote en curso.
var sent_events: int = 0
var sent_counts: int = 0
var dropped: int = 0

var _junction: RefCounted = null
var _last_signature: String = ""
var _last_event_ms: int = 0
var _seen_counts: Dictionary = {}
## Conteos del minuto en curso: "acceso|tipo" -> cantidad. Se envían al cerrar el minuto.
var _bucket: Dictionary = {}
var _bucket_minute: int = -1

## Fecha ISO 8601 en UTC con milisegundos, como exige el contrato.
static func iso(unix_ms: int) -> String:
	return "%s.%03dZ" % [Time.get_datetime_string_from_unix_time(int(unix_ms / 1000)), unix_ms % 1000]

## La web no conoce la fase peatonal (los peatones quedaron fuera del alcance). Para los
## vehículos esa fase es un todo rojo, y así se informa.
static func web_stage(stage: String) -> String:
	return "ALL_RED" if stage == "WALK" else stage

## Deja de seguir al cruce anterior sin perder lo que está en cola. Se llama cuando el
## envío se suspende: al reanudar no se inventan eventos ni conteos del tramo no observado.
func detach() -> void:
	_junction = null

## Mira el cruce una vez por cuadro. `unix_ms` es el reloj real del equipo.
func observe(junction: RefCounted, unix_ms: int) -> void:
	var controller = junction.controller
	var stage: String = web_stage(controller.stage)
	var active: Array = [] if controller.stage == "WALK" else controller.active.duplicate()
	var signature: String = stage + "|" + ",".join(PackedStringArray(active))
	if junction != _junction:
		# Cruce nuevo (arranque, cambio de escenario o reanudación): se toma como punto
		# de partida. Lo que haya pasado antes no se observó y no se informa.
		_junction = junction
		_last_signature = signature
		_seen_counts = junction.stop_line_counts.duplicate()
	if signature != _last_signature:
		_last_signature = signature
		# El par cruce + fecha identifica al evento en la web: dos eventos no pueden
		# compartir milisegundo o el segundo se descartaría como duplicado.
		_last_event_ms = maxi(unix_ms, _last_event_ms + 1)
		var cut: Variant = null
		if stage == "YELLOW" and controller.cut_reason in CUT_REASONS:
			cut = controller.cut_reason
		pending_events.append({"ocurrido_en": iso(_last_event_ms), "stage": stage, "active": active, "running_mode": controller.running_mode, "fallback": controller.fallback, "motivo": cut})
	var minute: int = int(unix_ms / 60000)
	if minute != _bucket_minute:
		_close_bucket()
		_bucket_minute = minute
	for key: String in junction.stop_line_counts:
		var delta: int = int(junction.stop_line_counts[key]) - int(_seen_counts.get(key, 0))
		if delta > 0:
			_bucket[key] = int(_bucket.get(key, 0)) + delta
		_seen_counts[key] = int(junction.stop_line_counts[key])
	_trim()

## Pasa a la cola los conteos del minuto que terminó. Un minuto solo se envía cerrado,
## porque la web reemplaza el valor si recibe el mismo minuto dos veces.
func _close_bucket() -> void:
	if _bucket_minute >= 0:
		for key: String in _bucket:
			var parts: PackedStringArray = key.split("|")
			if parts.size() != 2 or parts[0] not in APPROACHES or parts[1] not in VEHICLE_TYPES:
				continue
			var minute_text: String = iso(_bucket_minute * 60000)
			# Un mismo minuto, acceso y tipo no puede ir dos veces en un lote: la base
			# de datos rechazaría el lote completo. Si ya está en cola, se suma.
			var merged: bool = false
			for index in range(pending_counts.size() - 1, sent_counts - 1, -1):
				var queued: Dictionary = pending_counts[index]
				if String(queued.minuto) < minute_text: break
				if queued.minuto == minute_text and queued.acceso == parts[0] and queued.tipo == parts[1]:
					queued.cantidad = mini(int(queued.cantidad) + int(_bucket[key]), 1000)
					merged = true
					break
			if not merged:
				pending_counts.append({"minuto": minute_text, "acceso": parts[0], "tipo": parts[1], "cantidad": mini(int(_bucket[key]), 1000)})
	_bucket = {}
	_bucket_minute = -1

func _trim() -> void:
	while pending_events.size() - sent_events > MAX_PENDING:
		pending_events.remove_at(sent_events)
		dropped += 1
	while pending_counts.size() - sent_counts > MAX_PENDING:
		pending_counts.remove_at(sent_counts)
		dropped += 1

func has_pending() -> bool:
	return not pending_events.is_empty() or not pending_counts.is_empty()

## El latido con los nombres de FTITrafficController.snapshot(), más reportado_en.
func state(junction: RefCounted, unix_ms: int) -> Dictionary:
	var controller = junction.controller
	var counts: Array = []
	for value in controller.counts:
		counts.append(clampi(roundi(float(value)), 0, 500))
	return {
		"reportado_en": iso(unix_ms),
		"mode": controller.mode,
		"running_mode": controller.running_mode,
		"stage": web_stage(controller.stage),
		"active": [] if controller.stage == "WALK" else controller.active.duplicate(),
		"counts": counts,
		"sensor_age": clampf(float(controller.sensor_age), 0.0, 86400.0),
		"fallback": controller.fallback,
		"reason": String(controller.reason).left(120),
	}

## Lote siguiente. Marca qué parte de la cola viaja; después hay que llamar a
## confirm(), discard() o retry() según lo que responda la web.
func next_batch(junction: RefCounted, unix_ms: int) -> Dictionary:
	_drop_expired(unix_ms)
	sent_events = mini(batch_size, pending_events.size())
	sent_counts = mini(batch_size, pending_counts.size())
	return {
		"cruce_id": junction_id,
		"estado": state(junction, unix_ms),
		"eventos": pending_events.slice(0, sent_events),
		"conteos": pending_counts.slice(0, sent_counts),
	}

func _drop_expired(unix_ms: int) -> void:
	var limit: String = iso(unix_ms - int(MAX_AGE_SECONDS * 1000.0) + 60000)
	# Las fechas ISO en UTC con el mismo formato se ordenan igual que el texto.
	while not pending_events.is_empty() and String(pending_events[0].ocurrido_en) < limit:
		pending_events.pop_front()
		dropped += 1
	while not pending_counts.is_empty() and String(pending_counts[0].minuto) < limit:
		pending_counts.pop_front()
		dropped += 1

## 200: la web guardó el lote; sale de la cola.
func confirm() -> void:
	pending_events = pending_events.slice(sent_events)
	pending_counts = pending_counts.slice(sent_counts)
	sent_events = 0
	sent_counts = 0
	batch_size = DEFAULT_BATCH_SIZE

## 400: el lote es inválido y reintentarlo daría el mismo error; se descarta.
func discard() -> void:
	dropped += sent_events + sent_counts
	confirm()

## 502 o sin red: el lote se conserva y se reintenta.
func retry() -> void:
	sent_events = 0
	sent_counts = 0

## 413: el lote pesa demasiado; el siguiente lleva la mitad.
func shrink() -> void:
	batch_size = maxi(1, int(maxi(sent_events, sent_counts) / 2))
	retry()

## Guarda la cola para no perderla si la maqueta se cierra sin conexión (RNF5).
func save(path: String) -> bool:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return false
	file.store_string(JSON.stringify({"cruce_id": junction_id, "eventos": pending_events, "conteos": pending_counts}))
	file.close()
	return true

## Recupera la cola guardada. Ignora el archivo si es de otro cruce o no es válido.
func load_queue(path: String) -> bool:
	if not FileAccess.file_exists(path):
		return false
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not data is Dictionary or data.get("cruce_id") != junction_id:
		return false
	if not data.get("eventos") is Array or not data.get("conteos") is Array:
		return false
	for item in data.eventos:
		if item is Dictionary and item.get("ocurrido_en") is String:
			pending_events.append(item)
	for item in data.conteos:
		if item is Dictionary and item.get("minuto") is String:
			# JSON devuelve los números como float; la web exige un entero.
			item.cantidad = int(item.get("cantidad", 0))
			pending_counts.append(item)
	return true
