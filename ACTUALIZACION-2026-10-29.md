# Integración de los recursos de GitHub

Se descargó `main` hasta `6f00718`, que incorpora los commits de modelos STL y el plano PNG. Los archivos originales se conservan en `modelosBlec/` y `calle/`.

- SUV blanco: 4,6 × 2,15 m; pickup: 5,1 × 2,2 m; bus: 9,4 × 2,5 m.
- El catálogo de dimensiones es compartido entre la vista y la lógica, para evitar que el bus use una colisión de automóvil pequeño.
- Las mallas STL se leen en Godot, se centran, se apoyan sobre el suelo y se orientan a +Z. Se comparten entre instancias. No se altera el archivo original ni se requieren convertidores externos.
- Los materiales son colores sólidos. Los STL recibidos no traen mapas UV ni texturas de color.
- **Ver plano del cruce** abre la imagen PNG dentro de la aplicación. Es una referencia consultable; su disposición vial todavía no sustituye las rutas del cruce de prueba. **Esc** cierra el plano.

## Verificación

Pasaron las 36 comprobaciones de semáforos, incluida la comparación de 14.400 estados JavaScript, las 20 pruebas de tráfico y las 10 pruebas del ejecutor/MCP con Godot real. La flota mixta sigue completando cruces en los tres modos sin solapamientos en los escenarios comprobados de 240 s.

`tests/test_fleet.gd` verifica los tres STL, sus dimensiones, apoyo y reutilización de mallas, la coincidencia con los volúmenes de tráfico y la apertura del panel de referencia. Terminó con cero fallos. También se revisó una captura del renderizador real de Godot.

El núcleo conserva un cruce y un carril por sentido, con reserva exclusiva. No se han incorporado animaciones independientes de ruedas ni dinámica de suspensión.

La integración posterior de las funciones de HTML v3 se documenta en [DEMO-INTELIGENTE.md](DEMO-INTELIGENTE.md). La escena actual usa nueve cruces conectados.
