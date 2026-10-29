extends Node3D
## La vista observa el núcleo. No toma decisiones de tráfico ni modifica sus poses.
const TrafficWorld = preload("res://scripts/traffic_world.gd")
const FleetVisual = preload("res://scripts/stl_fleet.gd")

var world = TrafficWorld.new()
var car_nodes: Dictionary = {}
var lamps: Dictionary = {}
var status_label: Label
var queues_label: Label
var detail_label: Label
var pause_button: Button
var mode_select: OptionButton
var sensor_toggle: CheckButton
var priority_select: OptionButton
var camera: Camera3D
var paused: bool = false
var speed_steps: int = 1
var camera_yaw: float = 0.62
var camera_elevation: float = 0.88
var camera_distance: float = 153.0
var hud_clock: float = 0.0
var reference_panel: PanelContainer

func _ready() -> void:
	_build_environment()
	_build_roads()
	_build_signals()
	_build_hud()
	_sync_cars()
	_update_hud()
	_update_camera()

func _physics_process(delta: float) -> void:
	if not paused:
		for _substep in range(speed_steps):
			world.tick(delta)
		_sync_cars()

func _process(delta: float) -> void:
	hud_clock += delta
	if hud_clock >= 0.12:
		hud_clock = 0.0
		_update_hud()

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and (event.button_mask & (MOUSE_BUTTON_MASK_RIGHT | MOUSE_BUTTON_MASK_MIDDLE)):
		camera_yaw -= event.relative.x * 0.006
		camera_elevation = clampf(camera_elevation + event.relative.y * 0.004, 0.30, 1.48)
		_update_camera()
	elif event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			camera_distance = maxf(65.0, camera_distance * 0.9)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			camera_distance = minf(265.0, camera_distance / 0.9)
		_update_camera()
	elif event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_ESCAPE and reference_panel.visible:
			reference_panel.hide()
		elif event.keycode == KEY_SPACE:
			_toggle_pause()
		elif event.keycode == KEY_HOME:
			camera_yaw = 0.62
			camera_elevation = 0.88
			camera_distance = 153.0
			_update_camera()

func _update_camera() -> void:
	var horizontal: float = cos(camera_elevation) * camera_distance
	camera.position = Vector3(sin(camera_yaw) * horizontal, sin(camera_elevation) * camera_distance, cos(camera_yaw) * horizontal)
	camera.look_at(Vector3.ZERO)

func _material(color: Color, emission: float = 0.0) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.78
	if emission > 0.0:
		material.emission_enabled = true
		material.emission = color
		material.emission_energy_multiplier = emission
	return material

func _box(parent: Node3D, size: Vector3, at: Vector3, material: Material) -> MeshInstance3D:
	var mesh := BoxMesh.new()
	mesh.size = size
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	instance.material_override = material
	instance.position = at
	parent.add_child(instance)
	return instance

func _build_environment() -> void:
	camera = Camera3D.new()
	camera.far = 900.0
	camera.fov = 52.0
	camera.current = true
	add_child(camera)
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color("101c2a")
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color("c9dff1")
	environment.ambient_light_energy = 0.35
	environment.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	var holder := WorldEnvironment.new()
	holder.environment = environment
	add_child(holder)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-56.0, -32.0, 0.0)
	sun.light_color = Color("ffe5bc")
	sun.light_energy = 0.9
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 240.0
	add_child(sun)

func _build_roads() -> void:
	var ground := _material(Color("203e3d"))
	var asphalt := _material(Color("26313f"))
	var pavement := _material(Color("404f58"))
	var white := _material(Color("dbe8e6"))
	var yellow := _material(Color("e9ba54"))
	_box(self, Vector3(225, 0.3, 225), Vector3(0, -0.3, 0), ground)
	_box(self, Vector3(28, 0.15, 214), Vector3(0, -0.05, 0), asphalt)
	_box(self, Vector3(214, 0.15, 28), Vector3(0, -0.049, 0), asphalt)
	for sx in [-1, 1]:
		for sz in [-1, 1]:
			_box(self, Vector3(85, 0.25, 85), Vector3(sx * 59.0, 0.0, sz * 59.0), pavement)
	for side in [-1, 1]:
		for i in range(3, 19):
			var distance: float = float(i) * 5.5
			_box(self, Vector3(0.15, 0.025, 5.5), Vector3(side * 7.0, 0.04, side * distance), white)
			_box(self, Vector3(5.5, 0.025, 0.15), Vector3(side * distance, 0.04, side * 7.0), white)
		_box(self, Vector3(0.13, 0.028, 87), Vector3(side * 0.24, 0.045, side * 60.0), yellow)
		_box(self, Vector3(87, 0.028, 0.13), Vector3(side * 60.0, 0.045, side * 0.24), yellow)
		_box(self, Vector3(12, 0.03, 0.40), Vector3(-side * 6.9, 0.05, -side * 15.4), white)
		_box(self, Vector3(0.40, 0.03, 12), Vector3(side * 15.4, 0.05, -side * 6.9), white)
	# Áreas virtuales de conteo: sin cámara, serial ni dispositivos físicos.
	var sensor_material := _material(Color(0.14, 0.8, 0.68, 0.13))
	sensor_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_box(self, Vector3(5.5, 0.012, 55), Vector3(-3.5, 0.069, -42.9), sensor_material)
	_box(self, Vector3(5.5, 0.012, 55), Vector3(3.5, 0.069, 42.9), sensor_material)
	_box(self, Vector3(55, 0.012, 5.5), Vector3(42.9, 0.069, -3.5), sensor_material)
	_box(self, Vector3(55, 0.012, 5.5), Vector3(-42.9, 0.069, 3.5), sensor_material)
	for item in [["C1 · NORTE", Vector3(-12, 0.5, -31)], ["C2 · ESTE", Vector3(31, 0.5, -12)], ["C3 · SUR", Vector3(12, 0.5, 31)], ["C4 · OESTE", Vector3(-31, 0.5, 12)]]:
		var text := Label3D.new()
		text.text = item[0]
		text.position = item[1]
		text.font_size = 32
		text.pixel_size = 0.05
		text.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		text.modulate = Color("e5f3f3")
		add_child(text)

func _build_signals() -> void:
	var pole := _material(Color("87969c"))
	var housing := _material(Color("10161e"))
	var positions: Dictionary = {"N": Vector3(-10, 0, -17), "E": Vector3(17, 0, -10), "S": Vector3(10, 0, 17), "W": Vector3(-17, 0, 10)}
	for approach in positions:
		var signal_root := Node3D.new()
		signal_root.position = positions[approach]
		add_child(signal_root)
		_box(signal_root, Vector3(0.22, 4.2, 0.22), Vector3(0, 2.1, 0), pole)
		_box(signal_root, Vector3(0.85, 2.05, 0.65), Vector3(0, 4.2, 0), housing)
		var lights: Array = []
		for index in range(3):
			var bulb := MeshInstance3D.new()
			var sphere := SphereMesh.new()
			sphere.radius = 0.27
			sphere.height = 0.54
			sphere.radial_segments = 12
			sphere.rings = 6
			bulb.mesh = sphere
			# Esferas visibles desde la cámara libre, sin caras ocultas de un modelo.
			bulb.scale = Vector3(1, 1, 1.6)
			bulb.position = Vector3(0, 4.8 - index * 0.59, 0.35)
			signal_root.add_child(bulb)
			lights.append(bulb)
		lamps[approach] = lights

func _car_node(id: int) -> Node3D:
	var root: Node3D = FleetVisual.create_vehicle(id)
	add_child(root)
	return root

func _sync_cars() -> void:
	var alive: Dictionary = {}
	for vehicle in world.vehicles:
		var id: int = int(vehicle.id)
		alive[id] = true
		if not car_nodes.has(id):
			car_nodes[id] = _car_node(id)
			car_nodes[id].position = Vector3(vehicle.x, 0.0, vehicle.z)
			car_nodes[id].rotation.y = vehicle.yaw
			car_nodes[id].reset_physics_interpolation()
		else:
			car_nodes[id].position = Vector3(vehicle.x, 0.0, vehicle.z)
			car_nodes[id].rotation.y = vehicle.yaw
	for id in car_nodes.keys():
		if not alive.has(id):
			car_nodes[id].queue_free()
			car_nodes.erase(id)

func _panel_style(background: Color) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = background
	style.corner_radius_top_left = 14
	style.corner_radius_top_right = 14
	style.corner_radius_bottom_left = 14
	style.corner_radius_bottom_right = 14
	style.content_margin_left = 22
	style.content_margin_right = 22
	style.content_margin_top = 18
	style.content_margin_bottom = 18
	return style

func _label(text: String, size: int, color: Color) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", color)
	return label

func _build_hud() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	margin.add_theme_constant_override("margin_left", 24)
	margin.add_theme_constant_override("margin_right", 24)
	margin.add_theme_constant_override("margin_top", 22)
	layer.add_child(margin)
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", _panel_style(Color(0.035, 0.065, 0.10, 0.94)))
	margin.add_child(panel)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 12)
	panel.add_child(column)
	column.add_child(_label("FTI  /  LABORATORIO EN GODOT", 25, Color("e8f5f4")))
	column.add_child(_label("Semáforos y tráfico autónomo · flota STL: SUV, pickup y bus", 15, Color("9fbcc8")))
	var reference_button := Button.new()
	reference_button.text = "Ver plano del cruce"
	reference_button.pressed.connect(func(): reference_panel.show())
	column.add_child(reference_button)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 14)
	column.add_child(row)
	mode_select = OptionButton.new()
	for label in ["FTI · por demanda", "Adaptativo · colas", "Fijo · alternancia"]:
		mode_select.add_item(label)
	mode_select.custom_minimum_size.x = 220
	mode_select.item_selected.connect(func(index: int): world.set_mode(["fti", "adaptive", "fixed"][index]))
	row.add_child(mode_select)
	pause_button = Button.new()
	pause_button.text = "Pausar"
	pause_button.custom_minimum_size.x = 100
	pause_button.pressed.connect(_toggle_pause)
	row.add_child(pause_button)
	var reset_button := Button.new()
	reset_button.text = "Reiniciar"
	reset_button.pressed.connect(_reset_world)
	row.add_child(reset_button)
	var speed := OptionButton.new()
	for label in ["Tiempo ×1", "Tiempo ×2", "Tiempo ×4"]:
		speed.add_item(label)
	speed.item_selected.connect(func(index: int): speed_steps = [1, 2, 4][index])
	row.add_child(speed)
	sensor_toggle = CheckButton.new()
	sensor_toggle.text = "Sensores virtuales"
	sensor_toggle.button_pressed = true
	sensor_toggle.toggled.connect(func(enabled: bool): world.sensor_enabled = enabled)
	row.add_child(sensor_toggle)
	priority_select = OptionButton.new()
	for label in ["Sin prioridad V2I", "Prioridad N–S", "Prioridad E–O"]:
		priority_select.add_item(label)
	priority_select.item_selected.connect(func(index: int): world.controller.priority = ["", "NS", "EW"][index])
	row.add_child(priority_select)
	status_label = _label("", 17, Color("7fe3c4"))
	queues_label = _label("", 16, Color("dde7ef"))
	detail_label = _label("", 14, Color("9fbcc8"))
	column.add_child(status_label)
	column.add_child(queues_label)
	column.add_child(detail_label)
	var footer := Label.new()
	footer.text = "Arrastra con botón derecho para orbitar   ·   Rueda: zoom   ·   Inicio: cámara   ·   Espacio: pausa"
	footer.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	footer.offset_top = -38
	footer.offset_left = 24
	footer.offset_right = -24
	footer.add_theme_color_override("font_color", Color("d0e4e9"))
	layer.add_child(footer)
	_build_reference_panel(layer)

func _build_reference_panel(layer: CanvasLayer) -> void:
	reference_panel = PanelContainer.new()
	reference_panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	reference_panel.add_theme_stylebox_override("panel", _panel_style(Color("101c2a")))
	layer.add_child(reference_panel)
	var layout := VBoxContainer.new()
	reference_panel.add_child(layout)
	var close_button := Button.new()
	close_button.text = "Volver a la simulación · Esc"
	close_button.pressed.connect(func(): reference_panel.hide())
	layout.add_child(close_button)
	layout.add_child(_label("Plano de referencia · su geometría aún no sustituye los carriles de la simulación", 18, Color.WHITE))
	var picture := TextureRect.new()
	picture.texture = load("res://calle/Cruce_Calles.png")
	picture.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	picture.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	picture.size_flags_vertical = Control.SIZE_EXPAND_FILL
	layout.add_child(picture)
	reference_panel.hide()

func _toggle_pause() -> void:
	paused = not paused
	pause_button.text = "Continuar" if paused else "Pausar"

func _reset_world() -> void:
	world.reset()
	world.set_mode(["fti", "adaptive", "fixed"][mode_select.selected])
	world.sensor_enabled = sensor_toggle.button_pressed
	world.controller.priority = ["", "NS", "EW"][priority_select.selected]
	for node in car_nodes.values():
		node.queue_free()
	car_nodes.clear()
	_sync_cars()
	_update_hud()

func _update_hud() -> void:
	var controller = world.controller
	var active: String = ", ".join(controller.active) if not controller.active.is_empty() else "—"
	status_label.text = "T+%.1f s   |   %s   |   Accesos: %s   |   %s" % [world.simulation_time, controller.stage, active, "RESPALDO FIJO" if controller.fallback else controller.running_mode.to_upper()]
	queues_label.text = "Detecciones C1/N: %d   C2/E: %d   C3/S: %d   C4/O: %d   ·   Autos: %d" % [controller.counts[0], controller.counts[1], controller.counts[2], controller.counts[3], world.vehicles.size()]
	detail_label.text = controller.reason + "   ·   Reserva del cruce: un vehículo a la vez"
	var lit_colors: Array[Color] = [Color("ff4b53"), Color("ffd15c"), Color("5cf0a4")]
	for approach in lamps:
		var state: String = controller.light(approach)
		var active_index: int = 0 if state == "RED" else 1 if state == "YELLOW" else 2
		for index in range(3):
			var bulb: MeshInstance3D = lamps[approach][index]
			if bulb.get_meta("lit", -1) != int(index == active_index):
				bulb.material_override = _material(lit_colors[index] if index == active_index else lit_colors[index] * 0.12, 1.4 if index == active_index else 0.0)
				bulb.set_meta("lit", int(index == active_index))
