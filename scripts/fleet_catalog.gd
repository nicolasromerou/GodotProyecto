extends RefCounted
## Dimensiones compartidas por la vista y los volúmenes de tráfico (metros).
## `tipo` es la categoría con que la web cuenta cada modelo (docs/api-ingesta.md de
## webControl): auto, camioneta o bus.
const MODELS = [
	{"key": "suv", "tipo": "auto", "path": "res://modelosBlec/suv-compacto-blanco.stl", "length": 4.6, "width": 2.15, "color": Color("e5e7e8")},
	{"key": "pickup", "tipo": "camioneta", "path": "res://modelosBlec/pickup-compacta.stl", "length": 5.1, "width": 2.2, "color": Color("bd6f48")},
	{"key": "bus", "tipo": "bus", "path": "res://modelosBlec/bus-urbano.stl", "length": 9.4, "width": 2.5, "color": Color("519daf")},
]

static func for_id(id: int) -> Dictionary:
	return MODELS[posmod(id - 1, MODELS.size())]

## Modelo por nombre; si el nombre no existe devuelve el primero del catálogo.
static func for_key(key: String) -> Dictionary:
	for spec: Dictionary in MODELS:
		if spec.key == key:
			return spec
	return MODELS[0]
