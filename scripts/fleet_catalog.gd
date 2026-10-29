extends RefCounted
## Dimensiones compartidas por la vista y los volúmenes de tráfico (metros).
const MODELS = [
	{"key": "suv", "path": "res://modelosBlec/suv-compacto-blanco.stl", "length": 4.6, "width": 2.15, "color": Color("e5e7e8")},
	{"key": "pickup", "path": "res://modelosBlec/pickup-compacta.stl", "length": 5.1, "width": 2.2, "color": Color("bd6f48")},
	{"key": "bus", "path": "res://modelosBlec/bus-urbano.stl", "length": 9.4, "width": 2.5, "color": Color("519daf")},
]

static func for_id(id: int) -> Dictionary:
	return MODELS[posmod(id - 1, MODELS.size())]
