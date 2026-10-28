# Laboratorio FTI en Godot

Primera migración de la lógica del simulador HTML a **Godot 4 / GDScript**, validada en Godot 4.7.2. Incluye un cruce y autos de formas simples para comprobar el comportamiento antes de trasladar la ciudad y la flota.

## Abrir y ejecutar

1. En Godot, elige **Importar** y selecciona `project.godot` de esta carpeta.
2. Abre el proyecto y pulsa **F5**. No necesitas instalar librerías Python ni importar modelos.
3. Selecciona **FTI**, **Adaptativo** o **Fijo** en la barra superior. Los cambios esperan el amarillo y el despeje correspondiente.
4. Desactiva **Sensores virtuales** para comprobar el respaldo fijo tras cinco segundos de pérdida de lecturas. Al reactivarlos, vuelve al modo elegido mediante una transición segura.

También puedes ejecutar `abrir-godot.ps1` en PowerShell. Usa `GODOT_PATH` o el parámetro `-GodotPath` si el motor está en otra ubicación.

Arrastra con el botón derecho para orbitar, usa la rueda para acercarte, **Inicio** para volver a la cámara inicial y **Espacio** para pausar. Los botones de tiempo ×2 y ×4 ejecutan más pasos de 1/60 s, sin agrandar el paso de física.

## Lógica trasladada

| Módulo | Comportamiento |
| --- | --- |
| `scripts/traffic_controller.gd` | FTI por demanda: C1 → C2 → C3 → C4, omite entradas vacías, verde 5 s y amarillo 2 s. Sin demanda mantiene todo rojo. |
| El mismo controlador | Fijo por ejes: verde 11 s y amarillo 2,5 s. Adaptativo: equilibrio de colas, espera y prioridad V2I. |
| Seguridad del controlador | Rojo de despeje mínimo de 1 s; no habilita un nuevo verde mientras el cruce esté ocupado. Respaldo fijo al perder sensores durante 5 s. |
| `scripts/traffic_world.gd` | Conteo virtual, formación de colas, frenado ante semáforos y autos, decisión de cruce, salida libre y reposición de tráfico por las entradas. |
| `scripts/traffic_math.gd` | Fórmula de seguimiento, volúmenes orientados SAT y trayectorias cúbicas con distancia de arco para giros suaves. |
| `scripts/main.gd` | Vista 3D, cámara y controles. Observa el núcleo y permite cambiar sus ajustes. |

El núcleo es independiente de los nodos gráficos. Sus unidades son metros y segundos. Se mantiene la convención del HTML: yaw 0 apunta a +Z; los cuatro accesos se ordenan N, E, S, W.

Este primer escenario usa **un carril por sentido y reserva exclusiva de un vehículo dentro del cruce**. Es una regla conservadora para validar la migración. Las luces de un eje pueden mostrar verde simultáneamente, pero la reserva ordena el paso de los autos. No pretende reproducir todavía la capacidad de las nueve intersecciones del HTML.

## Alcance pendiente

Los modelos STL, sus texturas, edificios, peatones, paradas de bus, cambios de carril, conducción manual, choques con daños y la ciudad de nueve cruces no se incluyen en esta etapa. Los autos visibles son cajas de prueba. El tráfico usa el núcleo cinemático portado y comprobaciones SAT; todavía no utiliza la dinámica de `VehicleBody3D` ni pretende simular suspensión o fuerzas de neumáticos.

El HTML y el paquete visual v3 permanecen separados. Para continuar, conviene ampliar primero la red y las reservas por trayectorias; después, conectar escenas visuales de vehículos al estado del núcleo.

## Conexión y pruebas

Podemos trabajar mediante archivos y la línea de comandos oficial de Godot. También se incluye un **puente MCP local opcional**: consulta [CONEXION-MCP.md](CONEXION-MCP.md). Está preparado y probado; su registro en el cliente es un paso aparte y no se ha realizado automáticamente.

Desde esta carpeta, con Godot disponible en `PATH`:

```sh
godot --headless --path . --script res://tests/test_controller.gd
godot --headless --path . --script res://tests/test_world.gd
python tools/test_mcp.py --integration
```

Si Godot no está en `PATH`, define `GODOT_PATH` con la ruta del ejecutable principal. En PowerShell puedes usar `& $env:GODOT_PATH` en lugar de `godot`. El puente MCP también admite `--godot RUTA`.

Las pruebas de semáforos incluyen una traza de **14.400 estados del JavaScript original** para comprobar la equivalencia de la traducción. La referencia se incluye en `tests/reference/`; se puede regenerar con `node tests/generate_reference.mjs`. No hace falta Node para ejecutar el proyecto.

Consulta `COMPROBACIONES.md` para los resultados y sus límites.

## Documentación oficial

- [Godot: ejecución y pruebas desde la terminal](https://docs.godotengine.org/en/stable/tutorials/editor/command_line_tutorial.html).
- [Godot: paso de física e interpolación](https://docs.godotengine.org/en/stable/tutorials/physics/interpolation/physics_interpolation_introduction.html).
- [Godot: WebSocketPeer](https://docs.godotengine.org/en/stable/classes/class_websocketpeer.html), una opción para controles en vivo si más adelante se necesita un panel HTML.

La lógica queda en Godot. Python se usa únicamente en el puente de automatización; el HTML no es necesario para esta base.
