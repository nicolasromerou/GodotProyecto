# FTI · Simulación con Python y Whisk3D

**Variante experimental en desarrollo.** El alcance y el trabajo pendiente
están en [Estado y pendientes](docs/ESTADO-Y-PENDIENTES.md).

Python simula nueve cruces, mide demanda a partir de las posiciones de los
autos y resuelve semáforos, giros, separación y colisiones. Whisk3D dibuja el
cruce central I-5, interpola el movimiento y controla el renderizado y la
cámara. El paso de simulación de 30 Hz es independiente de la resolución y
del antialiasing del visor.

## Abrir en Windows

1. Extrae la carpeta completa en Windows de 64 bits. Necesitas Python 3.10 o
   superior con Tkinter, OpenGL y el runtime de Microsoft Visual C++ de 64 bits.
2. Abre **INICIAR-FTI.pyw** con doble clic. Aparece el launcher para elegir
   demanda, estrategia, calidad y servicios de la sesión. Pulsa **Iniciar
   sesión**. El launcher y el panel usan la biblioteca estándar de Python.
   También puedes abrirlo con `python launcher.py`.
3. Espera a que el panel diga «Visor conectado». El lanzador abre un canal
   de memoria compartida en Windows entre Python y el visor incluido. Whisk3D
   recibe y confirma la escena y envía sus controles por ese canal local.
4. Si Whisk3D se cierra o deja de responder, usa **Recuperar visor** en el
   encabezado. El visor recibe el escenario y la cámara actuales al volver a
   conectar. El menú **Sesión** permite abrir una sesión nueva y acceder a
   exportaciones y registros. Al cerrar se guarda el historial y el estado.
5. Las preferencias, los registros y las exportaciones se guardan en
   `%LOCALAPPDATA%\FTI`. Cada sesión tiene su carpeta de diagnóstico. El panel
   ofrece **Abrir registros** en **Datos**. Para usar otra carpeta al desarrollar,
   define `FTI_DATA_DIR`.

## Perfil gráfico

El perfil **alta**, activo al iniciar, solicita antialiasing MSAA 8×. Si el
controlador gráfico rechaza ese contexto, Whisk3D intenta 4× y 2× antes de
usar el respaldo sin antialiasing. El valor efectivo queda en
el registro `whisk3d.log` de la sesión. Elige **Estándar** en el launcher para
usar ese perfil. Maximiza la ventana para aprovechar la resolución de tu
pantalla. La opción `python launcher.py --directo` inicia con tus preferencias.

## Demanda y control del cruce

El movimiento comienza cuando Whisk3D confirma la primera imagen. La demo abre
en **Saturación**. Pulsa otro perfil en **Demanda de tráfico** para aplicarlo.
La vista 3D muestra I-5 y los contadores del panel separan el cruce de la red.

| Perfil | Autos en la red | Autos iniciales en I-5 |
| --- | ---: | ---: |
| Normal | 36 | 4 |
| Moderado | 90 | 10 |
| Punta N–S | 180 | 20 |
| Punta E–O | 180 | 20 |
| Saturación | 324 | 36 |

Pulsa **Manual**, ingresa de 0 a 36 autos y aplica la cantidad. El modo
manual dedica esa cantidad al cruce I-5. Los vehículos vuelven a entrar
por los extremos. El zoom y el ángulo determinan qué parte del cruce ves.
Los botones **Tráfico**, **Cámara** y **Pruebas** llevan a esas secciones
del panel.

- En **Estrategia de semáforos** puedes alternar entre FTI, Adaptativo, Fijo y
  Coordinado. El panel distingue la selección de la estrategia en uso durante
  el despeje de fase. Coordinado calcula prioridades para toda la red.
- Lee los semáforos y la cola por acceso en el centro del panel. La cola
  detectada usa los sensores del cruce y el indicador de red cuenta vehículos
  a menos de 14 km/h. **Cruces últimos 60 s** cuenta pasos completados durante
  el último minuto de simulación.
- **Pausar** cambia a **Reanudar** al detener el reloj. En **Pruebas del cruce**
  puedes solicitar paso peatonal o probar la conmutación por fallo de sensores.
  La solicitud peatonal respeta el mínimo de verde y el despeje del cruce.
  Durante el paso peatonal, los cuatro semáforos vehiculares se mantienen rojos.
- **Avanzar un paso** ejecuta 1/30 s con el tráfico pausado para revisar
  movimientos y cambios de fase.

## Datos e integración

En **Datos** puedes pausar el registro, exportar el historial a CSV o JSON y
guardar una instantánea completa. El historial conserva hasta 3600 muestras,
con una muestra por segundo de simulación. La instantánea contiene los nueve
cruces y los vehículos de la red, con posición, velocidad y tiempo detenido.

La **API local** ofrece consultas HTTP con un token propio de la sesión.
**Copiar URL** entrega la ruta de estado y **Copiar token** el valor para el
encabezado `Authorization: Bearer`. Las rutas disponibles son
`/api/v1/health`, `/api/v1/state`, `/api/v1/metrics`,
`/api/v1/vehicles` y `/api/v1/history`.

En **Servidor de visualización** introduce la URL y el token del servidor y
pulsa **Conectar servidor**. El envío funciona en segundo plano y el panel
muestra las entregas confirmadas o el último error. La aplicación publica la
última instantánea aproximadamente cada segundo de reloj. Si se interrumpe la
red, reintenta con la instantánea más reciente. El token remoto dura la sesión.

El servicio de servidor guarda estado e historial en SQLite y expone una API
versionada para visualizadores externos. Su configuración y arranque están en
[servidor/LEEME.md](servidor/LEEME.md).

| Archivo | Responsabilidad |
| --- | --- |
| `datos.py` | Contrato JSON, muestreo y exportación |
| `api_local.py` | Consultas locales de lectura |
| `conector.py` | Publicación al servidor y reintentos |
| `servidor/app.py` | Recepción y consultas de la API de servidor |
| `servidor/almacen.py` | Persistencia y deduplicación |
| `configuracion.py` | Preferencias y ubicaciones de datos |
| `launcher.py` | Preparación y ciclo de las sesiones |

El esquema se identifica con `schema_version: "1.0"`. Puedes añadir campos
a la instantánea en `Relay._publish_data` y adaptar visualizadores y consultas
sin modificar las reglas de circulación. El servidor funciona con Python
independientemente del visor 3D. La guía de consumo está en [API.md](API.md).

## Ajustar la vista

Arrastra los bordes de la ventana de Whisk3D o usa Maximizar. El visor
reencuadra la escena según el espacio disponible. La rueda, las flechas y el
arrastre con el botón central actualizan los controles de cámara del panel.

El panel y el visor se pueden redimensionar por separado. En una ventana
estrecha, el panel reorganiza las tarjetas en dos columnas y permite
desplazarse con la rueda o la barra lateral. En **Cámara de Whisk3D**
puedes elegir **Barrio completo**, **Cruce de cerca**, **Avenida y mediana**
o **Vista cenital**. Ajusta **Giro** para orbitar 360° alrededor de I-5 e
**Inclinación** para variar la altura de la mirada entre 12° y 87°.
**Zoom** se comparte con la rueda del visor. La cámara se puede ajustar
también con el tráfico en pausa.

## Controles compartidos

La barra de Whisk3D muestra **Pausa/Reanudar** y **Reiniciar** para la misma
simulación que controla el panel. El título del visor muestra el escenario,
la estrategia en uso y el estado que ya recibió. Cuando el visor está
conectado, el panel espera esa confirmación antes de dar por aplicado un cambio.

| En Whisk3D | Acción |
| --- | --- |
| Espacio o Esc | Pausar o reanudar el tráfico |
| R | Reiniciar el escenario |
| 1 a 4 | Barrio, cruce, avenida y cenital |
| Flechas, botón central y rueda | Giro, inclinación y zoom |
| S / P | Simular o restaurar sensores / solicitar paso peatonal |
| F5 a F8 | Estrategias FTI, adaptativa, fija y coordinada |
| F9 a F12 | Perfiles Normal, Punta N–S, Punta E–O y Saturación |

## Fuente y archivos

- `escena/FTI_Cruce_I5.w3d` abre el visor editable en el formato de texto legado
  de Whisk3D. `control.lua` recibe las poses y muestra luces e interpolación
  visual. Descarta tramas incompletas y conserva la última escena válida hasta
  que se reanuda el enlace.
- `escena/barrio.obj` contiene el trazado de I-5 basado en `Cruce_Calles.png`.
  Los recursos de escena están incluidos. `python escena/generar.py` rearma
  el proyecto Whisk3D a partir de esos recursos.
- `modelos-originales/` contiene los 11 STL. Incluye el SUV, la pickup
  compacta, el bus urbano, la moto y los siete vehículos de la flota
  histórica. Los dos buses tienen mallas distintas.
- `flota.json` define escala, color y eje frontal de cada vehículo. Todos se
  orientan al eje local +Z al exportar. El convertidor corrige las caras de las
  ruedas históricas que apuntaban hacia dentro y mantiene las posiciones de sus
  vértices. Los materiales separan carrocería, goma, llantas, cristales y luces.
  La flota comparte dos texturas pequeñas para cristales y llantas.
  Ejecuta `python escena/convertir_flota.py` y `python escena/generar.py`
  para regenerar las mallas y la escena.
- Whisk3D mantiene una plantilla por modelo y reutiliza las instancias que
  necesita el cruce. `Captura-flota.png` muestra las once mallas.
- `trafico.py` resuelve el movimiento y extrae las lecturas de los sensores
  virtuales. `geometria.py` contiene el perfil de carriles y la prueba de
  colisión SAT. `semaforos.py` ejecuta las fases y `traffic_coordinator.py`
  calcula las prioridades de la estrategia coordinada.
- `simulacion.py` mantiene el reloj y aplica comandos. `panel.py` y Whisk3D
  comparten las acciones mediante `canal_local.py`.
- Las licencias del ejecutable y sus componentes están en `whisk3d/licencias/`.
  El ejecutable incluido se compiló con `whisk3d/integracion-fti.patch`. El
  lanzador activa la vista adaptable y entrega a Whisk3D el nombre de un canal
  válido solo para esa sesión.
  La separación entre escena, Lua y recursos sigue los ejemplos del autor.
  [Fuente del visor Whisk3D](https://github.com/Dante-Leoncini/Whisk3D-Editor/tree/f17ae905cf66c86b5d127aa16b90e66448ad5ada) y
  [ejemplos oficiales](https://github.com/Dante-Leoncini/Whisk3D-Examples).

## Comprobaciones

`python verificar_datos.py` verifica el registro, los archivos y la API local.
`python launcher.py --diagnostico resultado.json` comprueba recursos, datos y
el enlace real con Whisk3D, y guarda el resultado de diagnóstico.

Ejecuta `python verificar_flota.py` para comprobar las caras STL, la orientación
de las tapas de rueda, los índices UV, las texturas y los faros de cada modelo.

Ejecuta `python verificar.py --render --arranque --panel` con la demo
cerrada. Comprueba el rechazo de comandos inválidos, pausa, coordinación,
paso peatonal y respaldo fijo. El arnés del editor introduce una trama
incompleta, comprueba que se mantenga la última escena y verifica que vuelvan
a aceptarse tramas válidas. También verifica el reencuadre a 1200 × 650 y
520 × 740, el giro en seis orientaciones y la carga de los once modelos.
La opción `--arranque` abre el visor por la ruta normal y envía
entradas a su ventana. Comprueba la pausa en ambos sentidos, dos pulsaciones
consecutivas, el reinicio, el zoom y el giro, los sensores, el paso peatonal,
los cinco perfiles de demanda, el modo manual con 0, 17 y 36 autos, la
estrategia coordinada y la reapertura del visor.
La opción `--panel` prueba los botones de Tk con el visor conectado, incluido
el modo manual en una ventana de 350 px. Añade `--calidad normal` para probar
el perfil gráfico estándar.

| Escenario y estrategia | Cruces en 120 s | Transferencias | Cruces en el segundo minuto |
| --- | ---: | ---: | ---: |
| Saturación, adaptativo | 404 | 368 | 203 |
| Saturación, fijo | 417 | 379 | 226 |
| Punta E–O, FTI | 153 | 144 | 78 |

Saturación registró hasta 44 vehículos simultáneos en I-5. El ensayo Python
muestrea la separación, las fases, la dirección de marcha, las identidades y
los giros en el carril exterior cada 1/6 de segundo. El visor confirma los 36
vehículos iniciales con los 11 modelos.

Para repetir el ensayo de carga, usa `python verificar_trafico.py saturation adaptive`.
Para los demás escenarios y estrategias puedes usar `saturation fixed` o
`peak_ew fti`.
El ensayo `python verificar_trafico.py manual adaptive --autos 17` comprueba
el modo manual durante cuatro minutos simulados.
