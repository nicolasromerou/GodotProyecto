# Comprobaciones de la variante

Ejecuta los comandos desde `variantes/whisk-python/`. Los ensayos del visor
abren sus propias ventanas y el panel de prueba.

## Biblioteca estándar y datos

```powershell
python verificar_flota.py
python verificar_datos.py
python verificar_conector.py
```

El verificador de flota comprueba los once STL convertidos, las posiciones
de sus vértices, la orientación de las tapas de rueda, los índices y los
materiales. Los verificadores de datos ejercitan el muestreo, los archivos
atómicos, la autenticación y los reintentos del conector.

## Servidor

```powershell
python -m venv .venv-servidor
& .venv-servidor/Scripts/python.exe -m pip install -r servidor/requirements.txt
& .venv-servidor/Scripts/python.exe verificar_servidor.py
```

En Linux, usa `.venv-servidor/bin/python`. Los ensayos levantan un servidor
HTTP de prueba y comprueban recepción, consultas, concurrencia, rollback,
reinicio, persistencia y deduplicación. También comprueban que el token de
lectura pueda consultar y reciba rechazo al intentar enviar datos.

## Interfaz y enlace nativo

```powershell
python verificar.py --render --arranque --panel
python launcher.py --diagnostico resultado.json
```

El primer comando comprueba tramas, recuperación de paquetes inválidos,
reencuadre, orientación, texturas y once modelos. Luego envía entradas al
visor y prueba los controles del panel, escenarios y reapertura.

El diagnóstico abre la ruta real de arranque, consulta la API local y exige
una confirmación de Whisk3D. El resultado incluye la ruta de los registros.

## Circulación

```powershell
python verificar_trafico.py saturation adaptive
python verificar_trafico.py saturation fixed
python verificar_trafico.py peak_ew fti
python verificar_trafico.py manual adaptive --autos 36
```

Los ensayos de perfiles cubren 120 s simulados. El manual comprueba 240 s
con la cantidad seleccionada. Se verifica población, identidades, dirección
de avance, luces incompatibles y separación por SAT cada 1/6 s.

## Resultados registrados

Las comprobaciones locales se realizaron con Python 3.14.5 y el visor de
Windows incluido. Corresponden a esta revisión experimental.

| Ensayo | Resultado |
| --- | --- |
| Flota | Once modelos, materiales y UV válidos; tapas de rueda corregidas |
| Datos y API local | Siete pruebas aprobadas |
| Conector | Cuatro pruebas aprobadas |
| API de servidor | Seis pruebas aprobadas |
| Arnés Whisk3D | 55 comandos aprobados |
| Panel y controles | Perfiles, manual, estrategia, sensores, peatones, cámaras y recuperación aprobados |
| Launcher | Arranque .pyw sin consola, recursos, API y visor confirmados |
| Integración completa | Emisor de Windows, 324 vehículos, nueve cruces, cambio de escenario y persistencia SQLite comprobados |

| Perfil | Cruces en 120 s | Transferencias | Cruces en el segundo minuto |
| --- | ---: | ---: | ---: |
| Saturación adaptativa | 404 | 368 | 203 |
| Saturación fija | 417 | 379 | 226 |
| Punta E–O FTI | 153 | 144 | 78 |

Saturación adaptativa registró hasta 44 vehículos simultáneos en I-5.
Los 324 corresponden al conjunto de la red. Estos resultados son mediciones
de escenarios concretos y pueden cambiar al modificar modelos o reglas.

## Registros

Los registros y las exportaciones se guardan bajo `%LOCALAPPDATA%\FTI`.
`FTI_DATA_DIR` permite usar otra carpeta al desarrollar. Cada sesión
mantiene su carpeta de diagnóstico. Los tests pueden generar imágenes
en `escena/`; esas salidas quedan excluidas del repositorio.
