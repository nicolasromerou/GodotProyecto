# Comprobaciones de la primera migración

Ejecutadas el 28 de octubre de 2026 con el ejecutable principal de **Godot 4.7.2 stable** instalado en este equipo.

- **Semáforos: 36 comprobaciones, 0 fallos.** Incluyen 14.400 instantáneas comparadas con la implementación JavaScript original: cuatro escenarios de 120 s a 30 Hz. Comprueban demanda, temporizadores, orden de servicio, ocupación, cambios de modo, prioridad, pérdida de sensores y recuperación.
- **Comportamiento vehicular: 20 pruebas, 0 fallos.** Comprueban frenado, trayectorias y tangentes, línea de detención, sensores, determinismo y serialización JSON. En 240 s de tráfico por modo: FTI 29 cruces y 18 giros; adaptativo 32 cruces y 20 giros; fijo 32 cruces y 21 giros. Sin solapamientos en esos escenarios. Mayor desplazamiento observado: 0,23334 m por paso de 1/60 s.
- **MCP: 10 pruebas del ejecutor, protocolo e integración aprobadas.** Arranque por stdio, inicialización, listado, validación de argumentos, importación, ejecución de las pruebas anteriores y simulaciones independientes. Verificado también el respaldo fijo con sensores desactivados. El ejecutor detecta errores en registros completos aunque la respuesta se recorte y exige marcadores de finalización exitosa de las suites.
- **Escena principal:** importación y ejecución headless sin errores GDScript. Captura real del renderizador de compatibilidad OpenGL en Intel UHD Graphics revisada visualmente.
- **Separación del proyecto inicial:** la validación del 28 de octubre se hizo sin modelos de la flota. La integración posterior de los tres STL y del PNG se documenta en `ACTUALIZACION-2026-10-29.md`. La versión HTML se conserva aparte.

Estas comprobaciones cubren el escenario simplificado de un cruce, un carril por sentido y doce autos iniciales. No constituyen una prueba de toda la ciudad ni de dinámica física de vehículos.

El entorno restringido bloqueó la lectura del almacén de certificados de Windows y produjo un aviso del motor. El proyecto no usa redes para funcionar. El puente conserva ese aviso y lo distingue de los errores de scripts; otros errores de Godot sí hacen fallar la validación. Las ejecuciones del puente usan una carpeta temporal para logs y cachés de usuario.

El puente MCP fue probado mediante su protocolo, pero **no se registró ni activó en la configuración del cliente**. El trabajo ya se puede ejecutar directamente con la terminal y Godot.

## Demo integrada del 29 de octubre de 2026

La versión actual incorpora la red conectada, escenarios y diagnóstico de HTML v3. La guía vigente y la validación de la red están en `DEMO-INTELIGENTE.md`. Los apartados anteriores documentan la validación inicial de la migración.
