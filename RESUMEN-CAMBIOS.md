# Resumen de cambios

## Calle de referencia y demo del semáforo inteligente

La actualización reconstruye el cruce central tomando como base `calle/Cruce_Calles.png` y ajusta la circulación a esa geometría. La implementación está en el commit [`40c8239`](https://github.com/nicolasromerou/GodotProyecto/commit/40c8239c21df24e95687f50a76d98408089f864d).

### Diseño y entorno

- Avenida norte dividida, mediana ajardinada con sendero y árboles.
- Aceras elevadas, bordillos curvos, pasos de cebra, doble amarilla y separación de carriles.
- Edificios bajos con fachadas y cubiertas, jardines, estacionamientos, bancos y farolas.
- Nueva cámara inicial sobre I-5, edificios sólidos y diagnóstico oculto al arrancar.
- F1 alterna el panel; F2 permite presentar el diseño sin interfaz.

### Circulación y semáforos

- Rutas, giros, sensores y líneas de detención alineados con la nueva calle.
- Comprobación del bus de 9,4 × 2,5 m contra el asfalto, la mediana y los bordillos.
- Corrección de un bloqueo al confundir vehículos del sentido contrario con líderes del carril. Se conservan las reservas y las comprobaciones de separación.
- Se mantienen nueve cruces conectados, los modos FTI/adaptativo/fijo, respaldo por pérdida de sensores y prioridad V2I temporal.
- Continúan los escenarios de demanda, incidentes con recuperación, comparación de algoritmos, telemetría y exportación CSV/JSON.
- La flota circulante mantiene SUV, pickup y bus; sus dimensiones visuales coinciden con las del tráfico.

### Validación

- 36 comprobaciones del controlador, incluidos 14.400 estados comparados con JavaScript.
- 20 pruebas de tráfico unitario y 31 de red, incluidas continuidad, hora punta y progreso sostenido.
- 21 pruebas de interfaz, 13 de perfil vial y 14 de la escena de referencia.
- Pruebas de flota y 11 pruebas del ejecutor/protocolo MCP, con integración de las siete suites en Godot real.
- Capturas del renderizador revisadas visualmente.

### Ejecutar y alcance

Importa `project.godot` en **Godot 4.7.2** y pulsa **F5**. La reconstrucción adapta las dimensiones del plano a la demo; los edificios y las parcelas no son un levantamiento exacto. Hay dos carriles demarcados por sentido y uno activo para la circulación. La conducción manual, los peatones, los cambios de carril y las ruedas independientes siguen pendientes.

Detalles y capturas: [calle reconstruida](CALLE-DESDE-REFERENCIA.md) y [guía de la demo](DEMO-INTELIGENTE.md).
