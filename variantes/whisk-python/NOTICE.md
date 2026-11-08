# Procedencia y licencias de la variante

## Whisk3D

El visor se basa en Whisk3D Editor de Dante D. Leoncini. Se incluyeron el
ejecutable de Windows, sus recursos y un parche de las modificaciones usadas
en esta integración. La revisión base y el proceso de reconstrucción están en
[docs/VISOR-WHISK.md](docs/VISOR-WHISK.md).

La licencia del editor, la del Core y los avisos de sus componentes se
conservan en [whisk3d/licencias/](whisk3d/licencias/). Esa carpeta incluye
Whisk3D Editor, Whisk3D Core, WhiskUI, SDL2 y Lua. Las licencias conservan los
avisos de sus respectivos titulares.

[Whisk3D Editor](https://github.com/Dante-Leoncini/Whisk3D-Editor) y
[ejemplos del autor](https://github.com/Dante-Leoncini/Whisk3D-Examples).

## Modelos y escena

Los STL se incorporaron desde los recursos aportados al proyecto.

| Recursos | Procedencia dentro del trabajo del proyecto |
| --- | --- |
| SUV, pickup compacta, bus urbano y moto | Catálogo `modelosBlec/` de la base del repositorio |
| Camaro, interceptor, cyber pickup, supercar, furgón, bus metropolitano y fastback | Flota histórica de siete STL suministrada para el simulador HTML |
| `Cruce_Calles.png` | Imagen de referencia suministrada para la calle |
| OBJ/MTL de flota | Conversiones de los STL mediante `escena/convertir_flota.py` |
| `vidrio.png` y `llanta.png` | Texturas procedurales generadas por el convertidor |
| `barrio.obj` y su material | Escena del cruce reconstruida a partir de la referencia del proyecto |
| `FTI.ico` | Icono original generado para el launcher |
| `Captura-*.png` | Capturas de comprobación de esta variante |

Los once STL se conservan en `modelos-originales/`. El catálogo
`flota.json` identifica los archivos y sus dimensiones de simulación.
El proceso de conversión puede repetirse desde los archivos incluidos.

La licencia y autoría de los modelos y de la referencia visual no están
especificadas en sus archivos originales. Este aviso registra su procedencia
y conserva los recursos del proyecto. La licencia MIT de Whisk3D corresponde
a sus componentes y no establece la licencia de esos recursos.

## Código y dependencias

El código Python y Lua de esta variante se incorpora al proyecto para su
desarrollo experimental. Este documento no asigna una licencia nueva al
conjunto del repositorio.

Las dependencias del servidor se instalan con
[`servidor/requirements.txt`](servidor/requirements.txt) y mantienen sus
licencias de distribución. El runtime de Microsoft Visual C++ requerido por
el visor se instala en Windows y se describe entre los requisitos de ejecución.
