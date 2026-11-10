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
9. En Demo, introduce cantidades para Norte, Este, Sur y Oeste del cruce observado. **Aplicar demanda y activar Python** intenta agregar esos vehículos y activa la coordinación; el aviso muestra cuántos cabían. La calle tiene capacidad física finita, por lo que un acceso lleno rechaza los adicionales. Usa **Solicitar cruce peatonal seguro** para una fase exclusiva de seis segundos, después del amarillo y el despeje.
10. El coordinador Python actualiza prioridades en los nueve cruces cada 2,5 s simulados. Recibe conteos, colas, esperas, estado de sensores y colas aguas abajo; las prioridades son solicitudes al modo adaptativo, no verdes forzados. Sentidos opuestos compatibles reciben verde juntos y los vehículos rectos atraviesan el cruce en paralelo. Los giros conservan una reserva exclusiva para prevenir choques; no se habilitan simultáneamente ejes que se cruzan. Detener el coordinador restaura el modo previo. Requiere Python 3 en PATH o la variable `PYTHON`.

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
| Movimiento/animación de peatones, conducción manual, cambios de carril y paradas | Pendientes; las solicitudes peatonales sí tienen una fase protegida. |
| Ruedas independientes, texturas UV y daños físicos | Pendientes; se conservan las mallas STL con materiales sólidos. |

## Seguridad y circulación

Cada vehículo pertenece a un único sector. Al cruzar el límite se transfiere su estado al siguiente cruce sin cambiar su posición global ni avanzar dos veces en un paso. Los sectores consultan las poses del vecino para anticipar el frenado. En el borde exterior se reutilizan los vehículos por la entrada opuesta cuando hay espacio; es una condición de borde de la simulación.

Los vehículos rectos de sentidos opuestos compatibles comparten el verde y pueden ocupar el cruce simultáneamente en carriles separados. Los giros usan una reserva exclusiva y distancia de arco. Antes de cambiar de eje se completa el amarillo y se espera al menos un segundo y a que el volumen del cruce esté libre. Los vehículos mantienen sus dimensiones de catálogo. Los STL originales no se modifican.

Las solicitudes peatonales reciben una fase exclusiva de seis segundos: todos los accesos vehiculares permanecen rojos. La fase solo empieza después del amarillo, el intervalo de despeje y la confirmación de cruce libre; después se conserva otro intervalo de despeje antes de dar paso a vehículos. La demo simula la solicitud y la señal, no el movimiento de peatones.

El coordinador Python es un planificador determinista local basado en sensores simulados; no usa aprendizaje automático, Internet ni hardware de tráfico real. Si Python falla, el coordinador se detiene, se informa el error y se restaura el modo previo.

La espera mostrada en el CSV y el comparador es el tiempo detenido acumulado medio de los vehículos activos. La velocidad es la media instantánea de la flota al tomar la muestra. Los cruces completados son el total acumulado de la red. Cambiar el modo no reinicia esas métricas; cambiar de escenario sí lo hace.

## Validación

- Controlador: paridad con 14.400 estados de JavaScript y pruebas adicionales de solicitud peatonal, exclusión vehicular y despeje.
- Tráfico unitario: 20 pruebas de frenado, rutas, seguridad y recuperación.
- Tráfico y red: pruebas de flujos rectos opuestos simultáneos sin solapamientos, además de 120 s por modo con 36 vehículos, hora punta por eje, inserción por calle, solicitudes peatonales, obstáculos entre sectores, identidades, sensores, prioridad temporal e historial.
- Interfaz: pruebas de selección, cámaras, inspector, escenarios, entrada de demanda por calle, activación automática de Python, llamada peatonal, exportación y comparación/cancelación.
- Perfil vial: 13 pruebas de rutas, bus sobre el asfalto, sensores y regresión de seguimiento.
- Diseño de referencia: 14 pruebas de geometría, entorno, transparencia y presentación.
- Flota: tres STL, tamaños, apoyo, caché de mallas y correspondencia con los volúmenes lógicos.
- MCP: 11 pruebas del ejecutor/protocolo e integración real de las ocho suites. Las instantáneas de la red se leen completas aunque se recorten los registros.
- Coordinador Python: seis pruebas de colas, espera, bloqueo aguas abajo, estabilidad de eje, sensores fallidos y entradas inválidas.

Los ensayos no cubren todas las combinaciones posibles de demanda. Se conserva un modelo de circulación conservador con un carril por sentido y paso exclusivo por cruce.

## MCP

El puente sigue siendo opcional y no está registrado automáticamente en el cliente. `fti_simulate` admite `network: true` para devolver el estado de la red, además del cruce unitario:

```json
{"mode":"adaptive","seconds":30,"sensor_enabled":true,"network":true}
```

Las simulaciones MCP son procesos separados de la ventana abierta. `fti_run_tests` ejecuta controlador, tráfico, red, interfaz y flota. La suite completa puede tardar varios minutos. La configuración del cliente se explica en CONEXION-MCP.md.

## Calle reconstruida desde la imagen

La geometría, el entorno y los nuevos ensayos de bordillos/mediana se detallan en [CALLE-DESDE-REFERENCIA.md](CALLE-DESDE-REFERENCIA.md).
