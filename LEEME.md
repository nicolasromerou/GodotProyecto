# Demo del semáforo inteligente en Godot

La guía vigente está en [README.md](README.md). El recorrido de presentación y el detalle de la integración con HTML v3 están en [DEMO-INTELIGENTE.md](DEMO-INTELIGENTE.md).

## Inicio rápido

Importa `project.godot` en Godot 4.7.2 y pulsa F5. No necesitas descargar modelos ni instalar Python para usar la demo. La escena incluye nueve cruces conectados y los STL de SUV, pickup y bus.

- **Control:** cruce observado, modo FTI/adaptativo/fijo, fases, sensores, colas, espera y zonas de detección.
- **Demo:** demanda normal, hora punta por eje, ausencia de demanda, fallo/restauración de sensores, V2I temporal e incidente con recuperación.
- **Vista:** cámara libre, seguimiento, red completa, edificios transparentes, volúmenes de colisión e inspector de flota.
- **Datos:** eventos, CSV de métricas, configuración JSON y comparación controlada de los tres modos.

Botón derecho para orbitar, rueda para zoom, Inicio para centrar y Espacio para pausar. F1 alterna el panel y F2 muestra la presentación sin interfaz. Esc cierra el plano/inspector o cancela el ensayo de comparación.

Cambiar el escenario reinicia el tráfico y sus métricas. Cambiar el modo mantiene el escenario y espera la transición segura. La comparación se ejecuta en una red separada y conserva el estado de la demo.

## Reglas

FTI atiende C1/N, C2/E, C3/S y C4/O en orden, omitiendo accesos vacíos: 5 s de verde y 2 s de amarillo. Sin demanda mantiene todo rojo. El modo fijo alterna ejes con 11 s de verde y 2,5 s amarillo. El adaptativo usa colas, espera y solicitudes V2I.

Los cambios pasan por amarillo y al menos un segundo de despeje, y esperan que el cruce esté libre. Al perder lecturas durante cinco segundos se solicita respaldo fijo; la restauración permite volver al modo elegido con transición segura.

La circulación usa un carril activo por sentido y reserva exclusiva por cruce. Es cinemática con comprobaciones SAT, sin dinámica de suspensión. La calzada actual reconstruye los rasgos del plano PNG; el visor permite compararlo. La conducción manual, peatones, cambios de carril, paradas y animación separada de ruedas se mantienen pendientes.

## Recursos y desarrollo

Los archivos STL originales se conservan en `modelosBlec/`. El catálogo `scripts/fleet_catalog.gd` comparte medidas entre la vista y la lógica. Para incorporar futuros modelos, añade su STL binario y una entrada de catálogo, y verifica tamaño y orientación.

El [puente MCP](CONEXION-MCP.md) requiere Python 3.10 o posterior y es opcional. Permite validar, ejecutar las siete suites y consultar simulaciones independientes. No controla una ventana del editor abierta ni se registra automáticamente en el cliente.
