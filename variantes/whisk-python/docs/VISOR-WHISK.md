# Visor Whisk3D incluido

## Revisión y contenido

El visor parte de Whisk3D Editor en la revisión
`f17ae905cf66c86b5d127aa16b90e66448ad5ada`. Se conserva el parche
[`whisk3d/integracion-fti.patch`](../whisk3d/integracion-fti.patch) para
reconstruir los ajustes locales.

El ejecutable incluido es una compilación de Windows de 64 bits con MSVC,
configuración Release y backend OpenGL utilizado en las pruebas. El código
de Whisk3D de esa revisión también incorpora opciones de otros backends.

| Elemento | Identificación |
| --- | --- |
| Fuente | Whisk3D Editor de Dante D. Leoncini |
| Commit base | `f17ae905cf66c86b5d127aa16b90e66448ad5ada` |
| Whisk3D Core | `40abb09c980b46538b8e269d15ce166fad01e878` |
| WhiskUI | `258f943ec996772fb2585be0ab7ca76e41bb70b5` |
| SDL2 | `b8b3f5ef2001cbe7c11f62d41a9bf47d4a2d8b07` |
| Binario | `whisk3d/whisk3d.exe` |
| SHA-256 del binario | `9c7528359a372cfae03cf36904cf16e2f66eedd518016ea3e3875707f8e120db` |

## Ajustes de la integración

- Vista adaptable al tamaño de ventana.
- Canal local para poses, luces, confirmaciones y entradas de usuario.
- Enlace de los controles nativos con las acciones de la simulación Python.
- Perfil gráfico alto con solicitud de MSAA hasta 8× y respaldos del driver.
- Nombres únicos para partes OBJ durante la importación.
- Manifiesto UTF-8 para corregir el arranque en rutas de Windows con tildes.

La simulación, el panel y el conector de servidor están en los módulos
Python de esta variante. Lua recibe las instantáneas y actualiza los recursos
de la escena.

## Reconstrucción

Instala las herramientas indicadas en las instrucciones del proyecto
Whisk3D para Windows. La compilación usada en este trabajo empleó MSVC,
CMake y Ninja.

Ejecuta los siguientes comandos desde una consola de desarrollo x64 de MSVC.
Sustituye la ruta del parche por la de esta variante.

```powershell
git clone --recurse-submodules https://github.com/Dante-Leoncini/Whisk3D-Editor.git whisk-fti
cd whisk-fti
git checkout f17ae905cf66c86b5d127aa16b90e66448ad5ada
git submodule update --init --recursive
git apply "RUTA/variantes/whisk-python/whisk3d/integracion-fti.patch"
cmake -S . -B build-fti -G Ninja -DCMAKE_BUILD_TYPE=Release -DW3D_PC_GLES2=OFF -DW3D_MULTIBACKEND=ON -DW3D_VULKAN=ON
cmake --build build-fti --target whisk3d
```

El resultado requiere la carpeta `res/` del visor. Conserva sus licencias
al copiarlo a `whisk3d/`. La aplicación espera ese directorio y sus recursos
junto al ejecutable del visor.

El parche se comprobó contra la revisión base. El hash identifica el
ejecutable que se probó; una recompilación puede producir otro hash por
versiones de herramientas y metadatos de compilación.

[Fuente de Whisk3D Editor](https://github.com/Dante-Leoncini/Whisk3D-Editor/tree/f17ae905cf66c86b5d127aa16b90e66448ad5ada).
