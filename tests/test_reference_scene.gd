extends SceneTree
const Street = preload("res://scripts/reference_street.gd")
var passed: int = 0
var failed: int = 0

func check(value: bool, label: String) -> void:
	if value: passed += 1
	else:
		failed += 1
		push_error("FAIL " + label)
	print("PASS " if value else "FAIL ", label)

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var scene = load("res://scenes/main.tscn").instantiate()
	root.add_child(scene)
	scene.paused = true
	check(scene.street_info.reference_path == "res://calle/Cruce_Calles.png", "La escena usa el trazado reconstruido desde la imagen del usuario")
	check(scene.street_info.road_width == 14.0 and scene.street_info.north_boulevard_width == 21.0, "Calzadas y bulevar de la referencia diferenciados")
	check(scene.street_info.curb_radius == 6.0 and scene.street_info.curb_instances > 100, "Bordillos de esquinas curvos construidos en 3D")
	check(scene.street_info.tree_positions.size() == 5 and not Street.is_asphalt(Vector2(0, -35), true), "Mediana ajardinada protegida de la circulación")
	check(Street.is_asphalt(Vector2(-5.25, -35), true) and Street.is_asphalt(Vector2(5.25, -35), true), "Carriles de ambos lados de la mediana sobre asfalto")
	check(scene.environment_info.counts.buildings >= 72 and scene.environment_info.counts.trees >= 77, "Entorno con fachadas y arbolado")
	check(scene.environment_info.counts.parked_cars >= 72 and scene.environment_info.counts.parking_spaces >= 288, "Estacionamientos y mobiliario incorporados")
	check(not scene.transparent_buildings and not scene.zones_enabled, "Presentación inicial con arquitectura sólida y sin zonas de diagnóstico superpuestas")
	var aligned: bool = true
	for junction in scene.world.junctions:
		aligned = aligned and absf(junction.stop_line - scene.street_info.stop_line_distance) < 0.001
	check(aligned, "Semáforos y tráfico usan la línea de detención del nuevo trazado")
	scene.world.selected = 4
	scene.zones_enabled = true
	scene.world.set_depth(85)
	scene._update_zones()
	check(scene.sensor_root.get_child_count() == 4 and scene.sensor_root.visible, "Cuatro zonas siguen el perfil de carril y su longitud configurable")
	scene._set_buildings(true)
	var faded: bool = true
	for material in scene.fade_materials: faded = faded and material.albedo_color.a < 0.3
	check(faded, "La transparencia afecta también ventanas y cubiertas")
	scene._set_buildings(false)
	check(scene.building_material.albedo_color.a == 1.0, "El acabado sólido se restaura")
	var presentation := InputEventKey.new()
	presentation.keycode = KEY_F2
	presentation.pressed = true
	scene._unhandled_input(presentation)
	check(not scene.interface_layer.visible, "Modo presentación muestra el diseño sin taparlo con paneles")
	scene._unhandled_input(presentation)
	check(scene.interface_layer.visible, "La interfaz vuelve al salir de presentación")
	scene.queue_free()
	await process_frame
	print("REFERENCE_SCENE_TESTS ", passed, " passed, ", failed, " failed")
	quit(0 if failed == 0 else 1)
