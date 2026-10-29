extends SceneTree
## Captura real del motor. Requiere renderizador, no --headless.
func _initialize() -> void:
	call_deferred("_capture")

func _capture() -> void:
	var scene = load("res://scenes/main.tscn").instantiate()
	root.add_child(scene)
	current_scene = scene
	scene._toggle_pause()
	for _tick in range(1200):
		scene.world.tick(1.0 / 60.0)
	for argument in OS.get_cmdline_user_args():
		if argument == "view=network":
			scene._set_camera_mode(2)
			scene.camera_target = Vector3.ZERO
			scene._update_camera()
		elif argument == "view=inspector":
			scene._open_inspector()
	scene._sync_cars()
	scene._update_hud()
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw
	var destination: String = "res://vista-previa.png"
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("output="):
			destination = argument.substr(7)
	var image: Image = root.get_texture().get_image()
	if image == null or image.is_empty():
		printerr("CAPTURE_FAIL: el renderizador no produjo una imagen")
		quit(1)
		return
	var error: Error = image.save_png(destination)
	print("CAPTURE_OK: " + destination if error == OK else "CAPTURE_FAIL: " + str(error))
	quit(0 if error == OK else 1)
