extends Control
var samples: Array = []
func _draw() -> void:
	var area := Rect2(Vector2(0, 10), Vector2(size.x, size.y - 20))
	draw_style_box(_background(), area)
	for line in range(1, 4):
		var y: float = area.position.y + area.size.y * line / 4.0
		draw_line(Vector2(0, y), Vector2(size.x, y), Color("293e50"))
	if samples.size() < 2: return
	var maximum: float = maxf(4.0, float(samples.max()))
	var points := PackedVector2Array()
	for index in range(samples.size()):
		points.append(Vector2(index * area.size.x / 59.0, area.end.y - float(samples[index]) / maximum * area.size.y))
	draw_polyline(points, Color("53dcb7"), 2.0, true)

func _background() -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = Color("0c1924")
	return style
