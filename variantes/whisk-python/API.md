# Consultar y ampliar los datos de FTI

Esta integración forma parte de la variante experimental con Whisk3D y
Python. El contrato versionado permite continuar el desarrollo del módulo.

La aplicación de Windows publica instantáneas con un contrato JSON versionado.
Los visualizadores pueden consultar la API local durante una sesión o la API
del servidor que recibe las entregas de esa sesión.

## Leer desde otro programa

Activa la API en **Datos**, copia su dirección y el token. La URL copiada por
el panel termina en `/state`. Para consultar otros recursos, usa la misma
base `/api/v1`.

Este ejemplo usa la biblioteca estándar de Python. Define `FTI_API_URL` con
la base de la API y `FTI_READ_TOKEN` con el token de la sesión o del servidor.

```python
import json
import os
from urllib.request import Request, urlopen

base = os.environ["FTI_API_URL"].rstrip("/")
token = os.environ["FTI_READ_TOKEN"]
request = Request(base + "/vehicles", headers={
    "Authorization": "Bearer " + token,
})
with urlopen(request, timeout=5) as response:
    vehicles = json.load(response)

print(vehicles["count"])
for vehicle in vehicles["items"]:
    print(vehicle["id"], vehicle["junction"], vehicle["speed_kmh"])
```

| Ruta GET | Contenido |
| --- | --- |
| `/api/v1/health` | Disponibilidad del servicio |
| `/api/v1/state` | Instantánea de simulación y estado del visor |
| `/api/v1/metrics` | Métricas de red y del cruce I-5 |
| `/api/v1/vehicles` | Vehículos de los nueve cruces |
| `/api/v1/history?limit=60` | Últimas 60 muestras registradas |

Las rutas de datos requieren `Authorization: Bearer TOKEN`. El endpoint de
salud está disponible para comprobar el servicio. La API local usa el token
de la sesión. En el servidor, configura `FTI_API_TOKEN` para el emisor y un
`FTI_READ_TOKEN` distinto para el visualizador. El segundo permite consultar
los datos y no autoriza a enviarlos.

## Contrato de estado

`/state` devuelve un objeto con estos campos.

| Campo | Significado |
| --- | --- |
| `schema_version` | Versión del contrato, actualmente `1.0` |
| `session_id` | Identificador de la ejecución de Windows |
| `sampled_at` | Momento de captura en UTC, con zona horaria |
| `simulation.time` | Segundos del reloj de simulación |
| `simulation.epoch` | Aumenta al reiniciar o cargar otro escenario |
| `simulation.cars` | Poses de los vehículos del cruce I-5 |
| `simulation.network_vehicles` | Información de todos los vehículos de la red |
| `simulation.junctions` | Controladores, sensores y luces de los nueve cruces |
| `simulation.metrics` | Colas, pasos completados, velocidades y esperas |
| `simulation.units` | Unidades y convención espacial |
| `viewer` | Conexión, cantidad dibujada y cámara |

`viewer.connected` indica que el visor responde. `viewer.synchronized` indica
que confirmó el ciclo y los comandos de la instantánea actual. Los campos
`viewer.epoch` y `viewer.command` permiten comprobar esa confirmación.

Las posiciones se expresan en metros respecto del centro de I-5, X hacia el
este y Z hacia el sur. El rumbo se expresa en radianes desde +Z hacia +X.
Cada vehículo incluye `junction`, `local_x`, `local_z`, `speed_kmh`,
`wait_seconds`, `lane` y `turn`, además de su identidad y pose. El campo
`approach` identifica el acceso asociado al rumbo.

El contador de pasos completados suma los nueve cruces. La población de
Saturación es de 324 vehículos en la red. La cantidad que dibuja el visor
corresponde al cruce I-5.

## Publicar en el servidor

Inicia el servicio siguiendo [servidor/LEEME.md](servidor/LEEME.md). En el
panel de Windows introduce la dirección de su API y su token en **Servidor de
visualización** y pulsa **Conectar servidor**. Se admiten una dirección raíz,
la base `/api/v1` o la ruta completa `/api/v1/ingest`.

El conector usa HTTPS para destinos remotos. Para una prueba en el mismo
equipo, puedes usar `http://127.0.0.1:8000`. Envía aproximadamente una vez por
segundo de reloj y reintenta las averías de red con espera creciente. Conserva
la instantánea más reciente para mantener acotado el trabajo pendiente.

El servidor recibe `POST /api/v1/ingest` y publica el mismo contrato de lectura.
Las entregas incluyen `delivery_sequence` para evitar que una repetición o un
envío antiguo reemplacen el estado confirmado. SQLite conserva la última
instantánea y un historial acotado. El estado recibido contiene `sampled_at`
para que un visualizador distinga una sesión actual de una sesión desconectada.

## Modificar el módulo

- Añade información a `Relay._publish_data` en `iniciar.py` para ampliar
  `simulation`. La lógica de circulación permanece en sus módulos.
- Modifica `datos.HISTORY_FIELDS` y `Telemetry._row` cuando necesites nuevas
  columnas en el historial y las exportaciones.
- Ajusta `conector.ServerConnector` para otra frecuencia o transporte.
- Añade consultas en `servidor/app.py` y adapta persistencia en
  `servidor/almacen.py`. El servidor importa el módulo de datos y funciona
  independientemente de Tk, la memoria compartida de Windows y Whisk3D.
- Cambia la versión del esquema si alteras el significado o eliminas campos
  que consumen otros programas. Los campos nuevos dentro de `simulation`
  permiten extender el contrato.

El receptor admite instantáneas de hasta 2 MiB y aplica límites de estructura.
El historial predeterminado conserva 3600 muestras. Cada muestra corresponde
a un segundo simulado observado. Tras una desconexión se retoma el estado
actual y el historial local se puede exportar por separado.

## Diagnóstico

`python verificar_datos.py` comprueba la API local, los archivos y el muestreo.
`python verificar_conector.py` comprueba el transporte y los reintentos.
`python launcher.py --diagnostico resultado.json` verifica recursos, API local
y la confirmación real del visor. Los registros se guardan bajo la carpeta de
datos de FTI y se abren desde el panel.
