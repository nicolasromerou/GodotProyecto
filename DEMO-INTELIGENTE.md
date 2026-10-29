# Demo funcional del semáforo inteligente

## Recorrido de presentación

1. Abre el proyecto y pulsa F5. La pestaña Control muestra el cruce central I-5. Observa los cuatro sensores, las colas, la espera y el cambio de fases. Los nueve cruces toman decisiones independientes y los autos pasan de uno a otro.
2. En Demo, elige hora punta Norte–Sur o Este–Oeste. El cambio reinicia la flota, el reloj y las métricas. Selecciona el modo adaptativo en Control para observar su reacción a las colas.
3. En Datos, ejecuta **Comparar 3 modos**. Es un ensayo aislado de 120 s por modo, con el mismo escenario, vehículos y rutas iniciales, sensores en línea y sin incidentes. La ciudad visible permanece pausada y conserva su estado. Puedes cancelar con Esc. El resultado y su CSV muestran cruces completados, espera detenida acumulada media y velocidad media al terminar; no se trata de una garantía general de mejora para cualquier demanda.
4. Desactiva los sensores del cruce observado. Las lecturas quedan retenidas y el estado indica su antigüedad. Tras 5 s el controlador solicita respaldo fijo mediante amarillo y despeje. Los otros ocho cruces siguen funcionando. Restaura las lecturas; vuelve al modo elegido con transición segura. También hay controles globales en Demo.
5. En modo adaptativo, solicita prioridad V2I por eje. Es una petición simulada al controlador, no un botón de verde forzado. Requiere demanda y respeta los intervalos de seguridad. Caduca a los 20 s o se puede cancelar.
6. Activa el incidente: un vehículo del cruce observado se detiene 12 s. Los demás conservan separación y luego el vehículo reanuda la circulación. Si ocupa el cruce, se retrasa el siguiente verde hasta despejarlo. No es una simulación de choque con daños.
7. En Vista, muestra las cajas de colisión, cambia a cámara de seguimiento o vista completa y alterna la transparencia de edificios. Abre el inspector para revisar los tres modelos STL. Al cerrarlo se restaura el estado de pausa previo.
8. Exporta las métricas CSV y la configuración JSON. Se toma una muestra por segundo y cruce; se conservan 30 minutos de muestras. El registro conserva los últimos 100 eventos y muestra los 30 más recientes.

## Integración respecto a HTML v3

| Función | Estado en Godot |
| --- | --- |
| Modos FTI, adaptativo y fijo | Integrados; se mantiene el controlador probado contra JavaScript. |
| Nueve cruces y circulación | Integrados con transferencia real entre sectores y consulta de vehículos vecinos. |
| Detección virtual, colas, zonas y fallo de sensores | Integrados por cruce y a nivel de red. |
| Prioridad V2I y despeje | Integrados como petición temporal simulada con transición segura. |
| Telemetría, historial, registro y exportación | Integrados; se añade comparación controlada de los tres modos. |
| Cámaras, transparencia y diagnóstico | Integrados. |
| Inspector de modelos y estado de pausa | Integrados para la nueva flota. |
| Modelos actuales | SUV, pickup y bus; las dimensiones de las mallas y del tráfico coinciden. |
| Conducción manual, peatones, cambios de carril y paradas | Pendientes; no forman parte del recorrido de esta demo. |
| Ruedas independientes, texturas UV y daños físicos | Pendientes; se conservan las mallas STL con materiales sólidos. |

## Seguridad y circulación

Cada vehículo pertenece a un único sector. Al cruzar el límite se transfiere su estado al siguiente cruce sin cambiar su posición global ni avanzar dos veces en un paso. Los sectores consultan las poses del vecino para anticipar el frenado. En el borde exterior se reutilizan los vehículos por la entrada opuesta cuando hay espacio; es una condición de borde de la simulación.

Cada cruce mantiene una reserva exclusiva. Antes de cambiar de eje se completa el amarillo y se espera al menos un segundo y a que el volumen del cruce esté libre. Los giros usan distancia de arco y los vehículos mantienen sus dimensiones de catálogo. Los STL originales no se modifican.

La espera mostrada en el CSV y el comparador es el tiempo detenido acumulado medio de los vehículos activos. La velocidad es la media instantánea de la flota al tomar la muestra. Los cruces completados son el total acumulado de la red. Cambiar el modo no reinicia esas métricas; cambiar de escenario sí lo hace.

## Validación

- Controlador: 36 comprobaciones, con 14.400 estados iguales a JavaScript.
- Tráfico unitario: 20 pruebas de frenado, rutas, seguridad y recuperación.
- Red: 31 pruebas; 120 s por modo con 36 vehículos, sin solapamientos observados ni verdes conflictivos en las comprobaciones. Comprueba además 120 s de hora punta por eje con 54 vehículos, y un obstáculo al otro lado del límite entre sectores. Conserva las identidades y prueba transferencias, sensores aislados, escenarios, prioridad temporal, recuperación e historial.
- Interfaz: 21 pruebas de selección, cámaras, visibilidad, inspector, escenarios, exportación y comparación/cancelación con conservación del estado.
- Perfil vial: 13 pruebas de rutas, bus sobre el asfalto, sensores y regresión de seguimiento.
- Diseño de referencia: 14 pruebas de geometría, entorno, transparencia y presentación.
- Flota: tres STL, tamaños, apoyo, caché de mallas y correspondencia con los volúmenes lógicos.
- MCP: 11 pruebas del ejecutor/protocolo e integración real de las siete suites. Las instantáneas de la red se leen completas aunque se recorten los registros.

Los ensayos no cubren todas las combinaciones posibles de demanda. Se conserva un modelo de circulación conservador con un carril por sentido y paso exclusivo por cruce.

## MCP

El puente sigue siendo opcional y no está registrado automáticamente en el cliente. `fti_simulate` admite `network: true` para devolver el estado de la red, además del cruce unitario:

```json
{"mode":"adaptive","seconds":30,"sensor_enabled":true,"network":true}
```

Las simulaciones MCP son procesos separados de la ventana abierta. `fti_run_tests` ejecuta controlador, tráfico, red, interfaz y flota. La suite completa puede tardar varios minutos. La configuración del cliente se explica en CONEXION-MCP.md.

## Calle reconstruida desde la imagen

La geometría, el entorno y los nuevos ensayos de bordillos/mediana se detallan en [CALLE-DESDE-REFERENCIA.md](CALLE-DESDE-REFERENCIA.md).
