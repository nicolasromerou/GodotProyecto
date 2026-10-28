# Conexión local con Godot

El proyecto funciona directamente en Godot. Se puede desarrollar editando sus archivos y ejecutando el motor por línea de comandos para importar, detectar errores y correr pruebas.

Se incluye además un servidor MCP **opcional**, escrito con la biblioteca estándar de Python 3.10 o posterior. Usa `stdio`: el cliente inicia el servidor y ambos intercambian JSON-RPC por entrada/salida estándar. No abre puertos ni requiere servicios externos. Registrar el servidor en un cliente es un paso aparte.

## Herramientas disponibles

| Herramienta | Resultado |
| --- | --- |
| `fti_project_info` | Ruta de este proyecto, ejecutable detectado y alcance del puente. |
| `fti_validate` | Importación con Godot headless y comprobación de errores. Puede generar `.godot`. |
| `fti_run_tests` | Ejecuta las pruebas de semáforos y tráfico y comprueba su finalización. |
| `fti_simulate` | Ejecuta una simulación sin ventana de entre 0 y 120 s y devuelve su estado JSON. |

Ejemplo de argumentos para `fti_simulate`:

```json
{"mode":"adaptive","seconds":30,"sensor_enabled":true}
```

Cada simulación comienza con el escenario inicial y avanza con pasos de 1/60 s. Es independiente de la ventana gráfica abierta. El puente no controla la escena remota del editor ni ofrece edición arbitraria de archivos o importación de modelos. Una integración futura de controles en vivo podría usar un `EditorPlugin` con órdenes concretas.

## Configurar un cliente MCP

1. Instala Python 3.10 o posterior y Godot 4.7.2.
2. Localiza `tools/mcp_server.py` dentro de tu copia del repositorio.
3. Configura el cliente para ejecutar Python con la ruta absoluta del script como argumento. Indica el motor mediante `GODOT_PATH` o `--godot`.

Ejemplo en PowerShell; sustituye las rutas por las de tu equipo:

```powershell
python 'C:/ruta/GodotProyecto/tools/mcp_server.py' --godot 'C:/ruta/Godot_v4.7.2-stable_win64.exe'
```

En Linux o macOS se aplica el mismo formato, con la ruta del ejecutable correspondiente. No hay paquetes Python adicionales que instalar.

`tools/mcp-config.example.json` muestra el formato genérico de los clientes que aceptan `mcpServers`. Actualiza sus rutas antes de usarlo; no lo pegues en una configuración que requiera otro formato. Si Python no está en `PATH`, usa también su ruta absoluta.

El puente busca primero `--godot`, después `GODOT_PATH`, ejecutables de Godot en el Escritorio y finalmente `godot`/`godot4` en `PATH`. Usa el ejecutable principal del motor. El proyecto queda fijado a la carpeta que contiene el puente.

## Probar sin registrar MCP

Desde la raíz del repositorio:

```sh
python tools/test_mcp.py
python tools/test_mcp.py --integration
```

El segundo comando ejecuta también el motor real. Puedes consultar un estado directamente:

```sh
godot --headless --path . --script res://tools/simulate.gd -- mode=adaptive seconds=30 sensor_enabled=true
```

La línea `FTI_JSON:` contiene el estado. El puente separa los registros de Godot de las respuestas JSON-RPC. Las ejecuciones tienen límites de tiempo y los registros devueltos se recortan; la detección de errores examina la salida completa.

## Referencias

- [Godot: línea de comandos](https://docs.godotengine.org/en/stable/tutorials/editor/command_line_tutorial.html).
- [MCP: transporte stdio](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports).
- [MCP: inicialización](https://modelcontextprotocol.io/specification/2025-03-26/basic/lifecycle).
- [MCP: herramientas](https://modelcontextprotocol.io/specification/2025-03-26/server/tools).

El puente implementa el subconjunto de herramientas MCP `2025-03-26` y `2024-11-05`; no implementa recursos, prompts, acceso remoto ni un panel de edición de escenas.
