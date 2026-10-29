extends SceneTree
var passed: int = 0
var failed: int = 0

func check(condition: bool, message: String) -> void:
	if condition: passed += 1
	else:
		failed += 1
		push_error("FAIL " + message)
	print("PASS " if condition else "FAIL ", message)

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var scene = load("res://scenes/main.tscn").instantiate()
	root.add_child(scene)
	scene.paused = true
	check(scene.world.junctions.size() == 9 and scene.car_nodes.size() == 36 and scene.lamps.size() == 36, "Vista conectada a nueve controladores y flota STL")
	for index in range(9): scene._select_cross(index)
	check(scene.world.selected == 8 and scene.cross_select.selected == 8, "Selector enfoca cualquiera de los nueve cruces")
	scene._set_camera_mode(2)
	check(scene.camera_distance > 600, "Vista general de toda la red")
	var zoom := InputEventMouseButton.new()
	zoom.button_index = MOUSE_BUTTON_WHEEL_DOWN
	zoom.pressed = true
	scene._unhandled_input(zoom)
	check(scene.camera_distance > 880, "Zoom general conserva su rango sin saltar a una cámara cercana")
	scene._set_buildings(false)
	check(scene.building_material.albedo_color.a == 1.0, "Edificios sólidos")
	scene._set_buildings(true)
	check(scene.building_material.albedo_color.a < 0.3, "Visibilidad a través de edificios")
	scene.collider_enabled = true
	scene._sync_cars()
	check(scene.car_nodes.values()[0].get_node("CollisionVolume").visible, "Diagnóstico muestra los volúmenes reales")
	scene.paused = false
	scene._open_inspector()
	var before: float = scene.world.simulation_time
	scene._physics_process(1.0 / 60.0)
	for index in range(3): scene._show_model(index)
	check(scene.paused and not scene.city_root.visible and not scene.top_panel.visible and scene.world.simulation_time == before, "Inspección de tres modelos pausa la red y oculta controles de reproducción")
	scene._close_inspector()
	check(not scene.paused and scene.city_root.visible and scene.camera.current, "Inspección restaura el estado de reproducción")
	scene.paused = true
	scene._open_inspector()
	scene._close_inspector()
	check(scene.paused, "Inspección preserva una pausa previa")
	scene._choose_scenario(1)
	check(scene.car_nodes.size() == 54, "Escenario hora punta actualiza la flota visual")
	scene._choose_scenario(3)
	check(scene.car_nodes.size() == 0, "Sin demanda elimina los vehículos de la escena")
	scene._choose_scenario(0)
	for _step in range(125): scene.world.tick(1.0 / 60.0)
	var csv_path := "res://.godot/demo-test.csv"
	var config_path := "res://.godot/demo-test.json"
	scene.export_kind = "csv"
	scene._save_export(csv_path)
	scene.export_kind = "json"
	scene._save_export(config_path)
	var csv: String = FileAccess.get_file_as_string(csv_path)
	var config: Variant = JSON.parse_string(FileAccess.get_file_as_string(config_path))
	check(csv.split("\n", false).size() == 19, "Exporta cabecera y 18 muestras de nueve cruces")
	check(csv.split("\n")[1].begins_with("1,1,"), "Las muestras CSV se fechan en segundos exactos")
	check(config is Dictionary and config.junctions == 9, "Exporta configuración JSON real")
	var before_comparison: String = JSON.stringify(scene.world.snapshot())
	await scene._run_comparison(0.5)
	check(scene.comparison_results.size() == 3, "Comparador ejecuta los tres modos con la misma flota")
	check(JSON.stringify(scene.world.snapshot()) == before_comparison and scene.paused, "Comparador conserva la red y su pausa")
	check(scene.comparison_csv().split("\n", false).size() == 4, "Comparación exportable con tres resultados")
	scene.set_deferred("comparison_cancel", true)
	await scene._run_comparison(2.0)
	check(not scene.comparing and scene.comparison_results.is_empty(), "Comparación cancelable")
	check(JSON.stringify(scene.world.snapshot()) == before_comparison and scene.paused, "Cancelar ensayo también conserva la simulación")
	scene.reference_panel.show()
	check(scene.reference_panel.visible, "Plano de referencia disponible")
	scene.queue_free()
	await process_frame
	print("DEMO_TESTS ", passed, " passed, ", failed, " failed")
	quit(0 if failed == 0 else 1)
