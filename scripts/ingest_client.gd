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
## Espera tras un fallo recuperable. Se duplica con cada fallo seguido hasta el tope y
## vuelve al mínimo con el primer envío correcto.
const RETRY_MS: int = 5000
const RETRY_MAX_MS: int = 60000
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
var _consecutive_failures: int = 0

func _ready() -> void:
	_request = HTTPRequest.new()
	_request.timeout = 10.0
	# Sin redirecciones: seguir una podría reenviar la cabecera con el token a otro host.
	# Una respuesta 3xx detiene el envío (ver decide()).
	_request.max_redirects = 0
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
	# http solo se acepta hacia este mismo equipo. Se compara el host completo: con
	# begins_with, "http://localhost.evil.com" también pasaba.
	var local: bool = _url.begins_with("http://") and url_host(_url) in ["localhost", "127.0.0.1"]
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
		_fail_and_wait(0)
		status = "Envío a la web: no se pudo iniciar la conexión; se reintenta en %d s." % int(retry_delay_ms(_consecutive_failures, 0) / 1000)
		push_warning("Ingesta: HTTPRequest.request() devolvió el error %d." % error)
		return
	_in_flight = true

## Host de una URL, sin esquema, puerto ni ruta y en minúsculas. Devuelve "" si antes de
## la ruta aparece "@" (http://localhost@evil.com: el host real es el de después) o "?",
## "#" o "\": HTTPRequest solo corta en "/", así que no se valida algo distinto de lo
## que Godot usaría para conectarse.
static func url_host(url: String) -> String:
	var inicio: int = url.find("://")
	var resto: String = url.substr(inicio + 3) if inicio >= 0 else url
	var barra: int = resto.find("/")
	var autoridad: String = resto if barra < 0 else resto.left(barra)
	for prohibido: String in ["@", "?", "#", "\\"]:
		if autoridad.contains(prohibido): return ""
	return autoridad.get_slice(":", 0).to_lower()

## Qué hacer con la respuesta de la web. Es pura para poder probarla sin red.
##   confirm  200: el lote quedó guardado.
##   shrink   413: el lote pesa demasiado.
##   discard  400/422: el contenido es inválido; repetirlo daría el mismo error.
##   stop     la configuración está mal (token, cruce o dirección): reintentar no sirve.
##   retry    todo lo demás: sin red, la web caída o un rechazo del borde de Vercel.
## Un 401 o 403 solo detiene el envío si lo respondió nuestra ruta, que siempre manda
## un JSON con "error". Si viene sin ese JSON lo puso el borde de Vercel (protección
## contra bots o límite de tráfico) y se pasa con el tiempo, así que se reintenta.
static func decide(result: int, code: int, body: String) -> String:
	if result != HTTPRequest.RESULT_SUCCESS: return "retry"
	if code == 200: return "confirm"
	if code == 413: return "shrink"
	# La web nunca redirige la ingesta: un 3xx indica una INGESTA_URL equivocada (por
	# ejemplo, http donde corresponde https) y reintentar no lo arregla.
	if code >= 300 and code < 400: return "stop"
	if code == 400 or code == 422: return "discard"
	if code == 404 or code == 405: return "stop"
	if code == 401 or code == 403:
		# JSON.new().parse y no JSON.parse_string: un cuerpo HTML del borde de Vercel no
		# es JSON, y parse_string dejaría un error falso en godot.log en cada intento.
		var json := JSON.new()
		return "stop" if json.parse(body) == OK and json.data is Dictionary and json.data.has("error") else "retry"
	return "retry"

## Espera antes del siguiente intento: 5, 10, 20, 40 y 60 s como máximo. Si la web
## pide un plazo con Retry-After, se respeta.
static func retry_delay_ms(failures: int, retry_after_s: int) -> int:
	var backoff: int = mini(RETRY_MS * (1 << clampi(failures - 1, 0, 4)), RETRY_MAX_MS)
	return maxi(backoff, retry_after_s * 1000)

static func header(headers: PackedStringArray, name: String) -> String:
	for line: String in headers:
		if line.to_lower().begins_with(name.to_lower() + ":"):
			return line.substr(name.length() + 1).strip_edges()
	return ""

func _fail_and_wait(retry_after_s: int) -> void:
	failed_batches += 1
	_consecutive_failures += 1
	_next_send_ms = Time.get_ticks_msec() + retry_delay_ms(_consecutive_failures, retry_after_s)

func _on_completed(result: int, code: int, headers: PackedStringArray, body: PackedByteArray) -> void:
	_in_flight = false
	var text: String = body.get_string_from_utf8()
	var action: String = decide(result, code, text)
	if action != "confirm":
		# Queda en godot.log (user://logs) para diagnosticar después. Las cabeceras
		# x-vercel-* dicen si el rechazo vino del borde de Vercel y no de nuestra ruta.
		push_warning("Ingesta: resultado %d, código %d, acción %s, x-vercel-mitigated=%s, x-vercel-error=%s, cuerpo=%s" % [
			result, code, action, header(headers, "x-vercel-mitigated"), header(headers, "x-vercel-error"), text.left(120).replace("\n", " ")])
	var queued: int = batcher.pending_events.size() + batcher.pending_counts.size()
	match action:
		"confirm":
			batcher.confirm()
			sent_batches += 1
			_consecutive_failures = 0
			status = "Envío a la web activo · %d lotes guardados · %d en cola." % [sent_batches, batcher.pending_events.size() + batcher.pending_counts.size()]
		"shrink":
			batcher.shrink()
			status = "Envío a la web: lote demasiado grande; se divide."
		"discard":
			batcher.discard()
			failed_batches += 1
			status = "Envío a la web: un lote fue rechazado (código %d) y se descartó." % code
		"stop":
			# Token, cruce o dirección equivocados: se detiene hasta corregir la
			# configuración y reiniciar. La cola se conserva.
			batcher.retry()
			_stopped = true
			status = "Envío a la web detenido (código %d): revisa INGESTA_URL e INGESTA_TOKEN y reinicia la maqueta." % code
			_save_queue()
		_:
			batcher.retry()
			_fail_and_wait(header(headers, "retry-after").to_int())
			var reason: String = "sin conexión" if result != HTTPRequest.RESULT_SUCCESS else "la web respondió %d" % code
			status = "Envío a la web: %s · %d registros en cola · reintento en %d s." % [reason, queued, int(maxi(_next_send_ms - Time.get_ticks_msec(), 0) / 1000)]

func _save_queue() -> void:
	var size: int = batcher.pending_events.size() + batcher.pending_counts.size()
	if size == _saved_size: return
	if batcher.save(queue_path):
		_saved_size = size

func _exit_tree() -> void:
	if enabled:
		batcher.retry()
		_save_queue()
