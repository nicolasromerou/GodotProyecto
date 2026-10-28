# GodotProyecto

Laboratorio de **semáforos autónomos y comportamiento vehicular en Godot 4.7.2**. Primera migración de la lógica FTI desde el simulador HTML a GDScript, con una vista 3D de prueba independiente del núcleo.

## Ejecutar

1. Clona o descarga este repositorio.
2. En Godot, selecciona **Importar**, abre `project.godot` y pulsa **F5**.
3. Cambia entre FTI, adaptativo y fijo desde la barra superior. Desactiva los sensores virtuales para comprobar el respaldo fijo tras cinco segundos sin lecturas.

El proyecto se ejecuta sin Python, Node, modelos externos ni conexión a Internet. Python **3.10 o posterior** solo se necesita para las herramientas MCP y sus pruebas; Node solo para regenerar la referencia de JavaScript.

**Cámara:** botón derecho para orbitar, rueda para zoom e Inicio para restablecer. **Simulación:** Espacio para pausar; controles de tiempo ×1, ×2 y ×4.

## Funciones

- **FTI por demanda:** C1 → C2 → C3 → C4, omite accesos vacíos, verde de 5 s, amarillo de 2 s y todo rojo sin demanda.
- **Fijo y adaptativo:** alternancia por ejes, equilibrio de colas y prioridad V2I con transiciones seguras.
- **Despeje y respaldo:** mínimo de 1 s en rojo y comprobación de ocupación antes de un nuevo verde; respaldo fijo al perder sensores durante 5 s.
- **Autos:** seguimiento y frenado, respeto de semáforos, giros cúbicos por distancia de arco, comprobaciones SAT y reposición segura por las entradas.
- **Paso fijo de 60 Hz** e interpolación visual. Núcleo independiente de las mallas.

Esta etapa contiene **un cruce, un carril por sentido y doce autos iniciales de formas simples**. Usa una reserva conservadora de un vehículo a la vez dentro del cruce. Todavía no incluye modelos de la flota, texturas, edificios, peatones, paradas de bus, cambios de carril, conducción manual ni la ciudad completa.

## Comprobar la lógica

Con el ejecutable `godot` en `PATH`, desde la raíz:

```sh
godot --headless --path . --script res://tests/test_controller.gd
godot --headless --path . --script res://tests/test_world.gd
python tools/test_mcp.py
```

Para probar además la conexión MCP con el motor real:

```sh
python tools/test_mcp.py --integration
```

Si Godot no está en `PATH`, define `GODOT_PATH` con la ruta del ejecutable principal. En PowerShell, los comandos directos pueden usar `& $env:GODOT_PATH`.

La validación inicial incluye **14.400 estados comparados con el controlador JavaScript original**, 36 comprobaciones de semáforos y 20 pruebas de tráfico. En los escenarios de 240 s por modo no se detectaron solapamientos. Consulta [COMPROBACIONES.md](COMPROBACIONES.md) para el alcance y los límites.

## Estructura y conexión

| Ruta | Función |
| --- | --- |
| `scripts/traffic_controller.gd` | Fases, modos, sensores y prioridad de semáforos. |
| `scripts/traffic_world.gd` | Autos, colas, decisiones de cruce y tráfico. |
| `scripts/traffic_math.gd` | Frenado, trayectorias y volúmenes orientados. |
| `scripts/main.gd` | Vista 3D y controles de prueba. |
| `tests/` | Pruebas GDScript y referencia reproducible del JavaScript. |
| `tools/` | Puente MCP local opcional y simulaciones headless. |

El [puente MCP](CONEXION-MCP.md) usa Python estándar y transporte `stdio`. Puede consultar este proyecto, validar, ejecutar pruebas y devolver estados JSON. Sus simulaciones son procesos independientes; no controla una ventana del editor abierta. La configuración del cliente es opcional y se realiza por separado.

Más detalles en [LEEME.md](LEEME.md).
