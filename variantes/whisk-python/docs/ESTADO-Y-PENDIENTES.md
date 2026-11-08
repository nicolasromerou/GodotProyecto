# Estado experimental y trabajo pendiente

Esta variante está en desarrollo. El launcher y las integraciones permiten
probar la aplicación y recoger datos. La validación registrada corresponde
a escenarios reproducibles en el equipo de desarrollo.

## Funciones disponibles

| Área | Estado comprobado |
| --- | --- |
| Inicio | Launcher .pyw con preferencias, servicios opcionales y diagnóstico visible |
| Interfaz | Panel redimensionable, navegación y controles verificados a 350 px con escalado de 100 a 200 % |
| Red | Nueve cruces y transferencias con identidad de vehículos |
| Semáforos | FTI, adaptativo, fijo y coordinación de prioridades |
| Fases protegidas | Amarillo, despeje y paso peatonal con los semáforos vehiculares en rojo |
| Sensores | Lecturas virtuales, simulación de fallo y respaldo fijo |
| Demanda | Normal 36, Moderado 90, Punta N–S 180, Punta E–O 180 y Saturación 324 en la red |
| Manual | De 0 a 36 vehículos asignados a I-5 |
| Flota | Once modelos con orientación, ruedas, materiales y texturas revisados |
| Cámara | Vistas predefinidas, giro, inclinación, zoom y adaptación de ventana |
| Recuperación | Reapertura del visor con el estado y la cámara de la sesión |
| Depuración | Pausa, reinicio y avance exacto de un paso |
| Datos | Historial acotado, CSV/JSON e instantánea de red |
| API local | Consultas autenticadas de estado, métricas, vehículos e historial |
| Conector | Publicación HTTP en segundo plano con espera creciente y última instantánea |
| Servidor | Recepción y consultas con FastAPI, SQLite, secuencias y token de lectura opcional |

## Alcance actual

- Python calcula nueve cruces. Whisk3D muestra I-5 y su entorno.
- La población de Saturación es de 324 vehículos en la red. I-5 parte con
  36 y su cantidad varía al recibir y transferir autos.
- El modo manual mantiene entre 0 y 36 vehículos en I-5 mediante reingresos
  por los extremos del cruce.
- La circulación es cinemática. Se comprueban separaciones y colisiones
  mediante rectángulos orientados y SAT.
- El runtime de escritorio usa memoria compartida de Windows. El servidor
  de datos se puede ejecutar por separado en Linux o Windows.
- El historial conserva por defecto 3600 muestras. Tras una desconexión, el
  conector retoma la instantánea actual y el historial local se puede exportar.
- El servidor expone el último estado recibido. La fecha `sampled_at`
  permite a un consumidor detectar que una sesión dejó de publicar.
- Los STL, su catálogo, sus conversiones y el visor de Windows están incluidos.
  Se necesita Python con Tkinter y las dependencias gráficas indicadas.
- El campo de versión del software identifica la revisión del código. El
  estado de esta rama continúa siendo experimental.

## Trabajo por completar

| Prioridad | Trabajo | Punto de partida |
| --- | --- | --- |
| Alta | Medir rendimiento y estabilidad en más equipos, resoluciones y controladores | Pruebas de visor y registros de sesión |
| Alta | Configurar el servidor real, HTTPS, servicio de arranque y volumen persistente | `servidor/` y su guía de despliegue |
| Alta | Definir retención y copias de respaldo según el uso previsto | `servidor/almacen.py` |
| Media | Ampliar la escena visible a más cruces y medir su coste | `escena/`, catálogo y enlace visual |
| Media | Añadir análisis y visualizadores externos sobre el contrato versionado | `datos.py`, `API.md` y API de servidor |
| Media | Uniformar progresivamente el detalle de los modelos y sus materiales | `flota.json` y convertidor STL |
| Media | Ampliar situaciones de tráfico y ensayos prolongados | `trafico.py`, `geometria.py` y verificadores |
| Media | Automatizar una matriz de pruebas en integración continua | Verificadores de datos, servidor y visor |
| Futura | Incorporar cambios de carril, paradas de bus y conducción más compleja | Reglas de tráfico y geometría |
| Futura | Añadir animación independiente de ruedas, suspensión y peatones visibles | Recursos y control visual |
| Futura | Evaluar otros sistemas de escritorio para el enlace nativo | `canal_local.py` y visor |

Las prioridades orientan el trabajo futuro. Las funciones de esa tabla no
se consideran implementadas por figurar aquí.

## Criterios de las pruebas

Las comprobaciones automáticas verifican estados concretos, la dirección de
marcha, la población, el muestreo y las transferencias. Los ensayos de tráfico
revisan la separación cada 1/6 s. Las inspecciones de los modelos revisan su
topología original, la corrección del winding, los índices UV y las texturas.
Las capturas ayudan a revisar el acabado en el motor.

La ausencia de solapamientos en las muestras de un ensayo acota lo comprobado.
La coordinación es una heurística de demanda y congestión. Se necesitan
más mediciones y escenarios antes de establecer garantías de operación.
Los pasos de repetición están en [PRUEBAS.md](PRUEBAS.md).
