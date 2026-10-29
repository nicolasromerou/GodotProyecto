extends SceneTree
const Fleet = preload("res://scripts/stl_fleet.gd")
const Catalog = preload("res://scripts/fleet_catalog.gd")
var failures: int = 0

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	for spec in Catalog.MODELS:
		var mesh: ArrayMesh = Fleet.mesh_for(spec)
		if mesh == null:
			failures += 1
			continue
		var bounds: AABB = mesh.get_aabb()
		if absf(bounds.size.x - float(spec.width)) > 0.001 or absf(bounds.size.z - float(spec.length)) > 0.001 or absf(bounds.position.y) > 0.001:
			push_error("Escala o apoyo incorrecto: " + spec.key)
			failures += 1
		if Fleet.mesh_for(spec) != mesh:
			failures += 1
		print("FLEET ", spec.key, " ", bounds.size)
	var scene = load("res://scenes/main.tscn").instantiate()
	root.add_child(scene)
	scene.paused = true
	if scene.car_nodes.size() != 36 or scene.reference_panel.visible:
		failures += 1
	var picture: TextureRect = scene.reference_panel.get_child(0).get_child(2)
	if picture.texture == null:
		push_error("El plano PNG no se ha importado o no se puede cargar")
		failures += 1
	scene.reference_panel.show()
	if not scene.reference_panel.visible:
		failures += 1
	scene.reference_panel.hide()
	for vehicle in scene.world.vehicles:
		var visual: Node3D = scene.car_nodes[int(vehicle.id)]
		var mesh: MeshInstance3D = visual.get_child(0)
		var size: Vector3 = mesh.mesh.get_aabb().size
		if absf(size.x - float(vehicle.width)) > 0.001 or absf(size.z - float(vehicle.length)) > 0.001:
			failures += 1
	scene.queue_free()
	await process_frame
	print("FLEET_TESTS 3 modelos y escena; ", failures, " fallos")
	quit(0 if failures == 0 else 1)
