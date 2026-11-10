extends Node
## Envía los datos del cruce a la web. El tráfico no depende de este nodo: si la web
## no responde, la simulación sigue igual y lo pendiente espera en la cola (RNF5).
## La respuesta de la web solo dice si guardó el lote; nunca trae órdenes (S1).
##
## Configuración, por variables de entorno o por un archivo .env junto a project.godot
## (ignorado por git; plantilla en .env.example):
##   INGESTA_URL    dirección completa, por ejemplo https://mi-web/api/ingesta
##   INGESTA_TOKEN  token que entrega quien administra la web
##   INGESTA_CRUCE  opcional; por defecto maqueta-01

const Batcher = preload("res://scripts/ingest_batcher.gd")
const HEARTBEAT_MS: int = 1000
const RETRY_MS: int = 5000
const SAVE_MS: int = 5000

var batcher = Batcher.new()
var enabled: bool = false
## Mensaje para la interfaz. Nunca incluye el token.
var status: String = "Envío a la web sin configurar."
var sent_batches: int = 0
var failed_batches: int = 0
## Archivo donde se guarda la cola pendiente entre ejecuciones.
var queue_path: String = "user://ingesta_cola.json"

var _url: String = ""
var _token: String = ""
var _request: HTTPRequest
var _in_flight: bool = false
var _next_send_ms: int = 0
var _next_save_ms: int = 0
var _saved_size: int = -1
var _stopped: bool = false

func _ready() -> void:
	_request = HTTPRequest.new()
	_request.timeout = 10.0
	add_child(_request)
	_request.request_completed.connect(_on_completed)
	configure(_read_settings())

## Lee primero el entorno y después el archivo .env. Devuelve solo las tres claves.
func _read_settings() -> Dictionary:
	var settings: Dictionary = {}
	var path: String = "res://.env"
	if FileAccess.file_exists(path):
		for line: String in FileAccess.get_file_as_string(path).split("\n"):
			var clean: String = line.strip_edges()
			var cut: int = clean.find("=")
			if clean.begins_with("#") or cut < 1: continue
			settings[clean.left(cut).strip_edges()] = clean.substr(cut + 1).strip_edges().trim_prefix("\"").trim_suffix("\"")
	for key: String in ["INGESTA_URL", "INGESTA_TOKEN", "INGESTA_CRUCE"]:
		if not OS.get_environment(key).is_empty():
			settings[key] = OS.get_environment(key)
	return settings

## `allow_headless` existe para verificar el envío desde un script sin ventana.
func configure(settings: Dictionary, allow_headless: bool = false) -> void:
	enabled = false
	_stopped = false
	_url = String(settings.get("INGESTA_URL", ""))
	_token = String(settings.get("INGESTA_TOKEN", ""))
	batcher.junction_id = String(settings.get("INGESTA_CRUCE", "maqueta-01"))
	if _url.is_empty() or _token.is_empty():
		status = "Envío a la web sin configurar (faltan INGESTA_URL e INGESTA_TOKEN)."
		return
	# Las pruebas automáticas abren la escena sin ventana: no deben escribir en la web.
	if DisplayServer.get_name() == "headless" and not allow_headless:
		status = "Envío a la web desactivado en modo sin ventana."
		return
	# El token viaja en una cabecera. Sin TLS cualquiera en la red lo leería, así que
	# http solo se acepta hacia este mismo equipo.
	var local: bool = _url.begins_with("http://localhost") or _url.begins_with("http://127.0.0.1")
	if not _url.begins_with("https://") and not local:
		status = "Envío a la web desactivado: INGESTA_URL debe usar https."
		return
	enabled = true
	status = "Envío a la web listo."
	if batcher.load_queue(queue_path):
		status = "Envío a la web listo · %d registros recuperados de la cola." % (batcher.pending_events.size() + batcher.pending_counts.size())

## Se llama una vez por cuadro. `allowed` es falso cuando la simulación no corre a ×1:
## las fechas usan el reloj real, y a otra velocidad los conteos por minuto no serían
## comparables con el resto.
func update(junction: RefCounted, allowed: bool) -> void:
	if not enabled or _stopped: return
	var now_ms: int = int(Time.get_unix_time_from_system() * 1000.0)
	if not allowed:
		batcher.detach()
		status = "Envío a la web en pausa: solo se informa a velocidad ×1."
		return
	var events_before: int = batcher.pending_events.size()
	batcher.observe(junction, now_ms)
	var ticks: int = Time.get_ticks_msec()
	# Un cambio de etapa se envía de inmediato; el latido, una vez por segundo.
	if not _in_flight and (ticks >= _next_send_ms or batcher.pending_events.size() > events_before):
		_send(junction, now_ms)
	if ticks >= _next_save_ms:
		_next_save_ms = ticks + SAVE_MS
		_save_queue()

func _send(junction: RefCounted, now_ms: int) -> void:
	var batch: Dictionary = batcher.next_batch(junction, now_ms)
	var headers := PackedStringArray(["Content-Type: application/json", "Authorization: Bearer " + _token])
	var error: Error = _request.request(_url, headers, HTTPClient.METHOD_POST, JSON.stringify(batch))
	_next_send_ms = Time.get_ticks_msec() + HEARTBEAT_MS
	if error != OK:
		batcher.retry()
		failed_batches += 1
		_next_send_ms = Time.get_ticks_msec() + RETRY_MS
		status = "Envío a la web: no se pudo iniciar la conexión; se reintenta."
		return
	_in_flight = true

func _on_completed(result: int, code: int, _headers: PackedStringArray, _body: PackedByteArray) -> void:
	_in_flight = false
	var queued: int = batcher.pending_events.size() + batcher.pending_counts.size()
	if result != HTTPRequest.RESULT_SUCCESS or code >= 500:
		# Sin conexión o la web no pudo guardar: el lote sigue en la cola.
		batcher.retry()
		failed_batches += 1
		_next_send_ms = Time.get_ticks_msec() + RETRY_MS
		status = "Envío a la web sin conexión · %d registros en cola." % queued
	elif code == 200:
		batcher.confirm()
		sent_batches += 1
		status = "Envío a la web activo · %d lotes guardados · %d en cola." % [sent_batches, batcher.pending_events.size() + batcher.pending_counts.size()]
	elif code == 413:
		batcher.shrink()
		status = "Envío a la web: lote demasiado grande; se divide."
	elif code == 401 or code == 403:
		# El token o el cruce no corresponden: reintentar no lo arregla. Se detiene
		# hasta que alguien corrija la configuración; la cola no se pierde.
		batcher.retry()
		_stopped = true
		status = "Envío a la web detenido: la web rechazó el token o el cruce (código %d). Revisa la configuración." % code
		_save_queue()
	else:
		# 400 u otro rechazo del contenido: repetir el mismo lote daría el mismo error.
		batcher.discard()
		failed_batches += 1
		status = "Envío a la web: un lote fue rechazado (código %d) y se descartó." % code
		push_warning("Ingesta: la web rechazó un lote con código %d." % code)

func _save_queue() -> void:
	var size: int = batcher.pending_events.size() + batcher.pending_counts.size()
	if size == _saved_size: return
	if batcher.save(queue_path):
		_saved_size = size

func _exit_tree() -> void:
	if enabled:
		batcher.retry()
		_save_queue()
