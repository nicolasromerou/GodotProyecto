# Servicio de datos FTI

**Módulo experimental en desarrollo.** El despliegue en un servidor real y su
configuración HTTPS forman parte del trabajo de integración pendiente.

Este módulo recibe las instantáneas de la aplicación de Windows y permite
consultarlas desde otros programas. Se ejecuta con Python 3.10 o superior en
Linux o Windows. Conserva el estado más reciente y un historial acotado en
SQLite, con una muestra por segundo de simulación.

## Instalar y ejecutar

Ejecuta los comandos desde la carpeta que contiene datos.py y servidor/.
Para desplegar solo la API, copia esos dos elementos al servidor.

~~~sh
python -m venv .venv
.venv/bin/python -m pip install -r servidor/requirements.txt
export FTI_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export FTI_READ_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
.venv/bin/python -m servidor --host 127.0.0.1 --port 8000 --database datos/fti.sqlite3
~~~

En PowerShell, usa el ejecutable del entorno y configura la misma variable.

~~~powershell
python -m venv .venv
& .venv/Scripts/python.exe -m pip install -r servidor/requirements.txt
$env:FTI_API_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:FTI_READ_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
& .venv/Scripts/python.exe -m servidor --host 127.0.0.1 --port 8000 --database datos/fti.sqlite3
~~~

Configura esa dirección y ese token en la aplicación emisora. El token requiere
al menos 24 caracteres ASCII. El argumento --host 0.0.0.0 permite recibir
conexiones desde otros equipos. Para publicarlo en Internet, conecta el servicio
a una dirección HTTPS mediante el proxy inverso del servidor y conserva el
archivo SQLite en un volumen persistente. La documentación interactiva está en
/docs.

La aplicación de Windows envía datos con FTI_API_TOKEN. Entrega FTI_READ_TOKEN
al panel web o al programa que consulta datos. El token de lectura permite
consultas GET. Ambos valores deben ser distintos y tener al menos 24 caracteres
ASCII. Si omites FTI_READ_TOKEN, las consultas también usan FTI_API_TOKEN.

El servicio usa un proceso Uvicorn. El argumento --history 3600 conserva las
últimas 3600 muestras. También puedes elegir el archivo SQLite con FTI_DATA_DB.
Al reiniciar se recuperan el estado, el historial y las secuencias de entrega.

## Consultar los datos

Todos los recursos de datos requieren el encabezado Authorization con el valor
Bearer seguido de un espacio y el token. Las respuestas usan el esquema 1.0.

| Método y recurso | Información |
| --- | --- |
| GET /api/v1/health | Estado del servicio, accesible sin token |
| GET /api/v1/state | Instantánea completa con sesión, reloj, cruces y visor |
| GET /api/v1/metrics | Métricas generales y contexto del escenario |
| GET /api/v1/vehicles | Vehículos de la red, con identificador y pose |
| GET /api/v1/history?limit=100 | Últimas muestras de antigua a reciente |
| POST /api/v1/ingest | Recepción autenticada de una instantánea |

Las posiciones de la red usan metros. El giro yaw usa radianes y el reloj usa
segundos de simulación. speed_kmh usa kilómetros por hora. wait_seconds y
mean_wait usan segundos. junction identifica el cruce de cada vehículo.
La instantánea incluye las unidades que transmite la aplicación.

~~~python
import json
import os
from urllib.request import Request, urlopen

request = Request(
    "http://127.0.0.1:8000/api/v1/metrics",
    headers={"Authorization": "Bearer " + os.environ["FTI_READ_TOKEN"]},
)
with urlopen(request, timeout=5) as response:
    metrics = json.load(response)
print(metrics)
~~~

Para consultar desde una web, configura FTI_CORS_ORIGINS con sus orígenes exactos,
separados por coma, por ejemplo https://panel.ejemplo.cl,http://localhost:3000.
El servidor habilita consultas GET y los encabezados Authorization y
Content-Type para esos orígenes. El token se entrega mediante el encabezado
de autorización.

## Enviar instantáneas

El emisor envía el objeto que devuelve Telemetry.snapshot() y añade
delivery_sequence, un entero creciente dentro de su sesión. El cuerpo usa
Content-Type application/json y admite hasta 2 MiB. Una entrega nueva responde
con accepted true, el identificador de sesión, el ciclo epoch y el tiempo de
simulación. Una entrega repetida o fuera de orden responde con accepted true y
duplicate true, y conserva el estado ya recibido. Ese control se mantiene al
reiniciar el servidor.

La instantánea conserva el session_id y sampled_at del emisor. Dentro de
simulation se reciben los indicadores generales, las poses en cars para I-5,
network_vehicles para toda la red y junctions para los cruces.

Las respuestas 401, 413, 415 y 422 indican respectivamente problemas de token,
tamaño, tipo de contenido o datos. Antes de recibir la primera instantánea,
las consultas de estado responden 503. Un fallo de almacenamiento también
responde 503 y deja la transacción sin aplicar.

## Verificar

~~~sh
.venv/bin/python verificar_servidor.py
~~~

El ensayo abre un servidor HTTP local, comprueba autenticación y validación,
envía datos concurrentes y prueba el historial acotado. Reinicia el servicio
para comprobar la persistencia y el rechazo de entregas antiguas. También
simula un fallo de escritura para comprobar que el estado anterior se conserva.

Las versiones se fijaron y comprobaron con las publicaciones oficiales.
[FastAPI en PyPI](https://pypi.org/project/fastapi/),
[Uvicorn en PyPI](https://pypi.org/project/uvicorn/) y
[configuración de Uvicorn](https://uvicorn.dev/settings/).
