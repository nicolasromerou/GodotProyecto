extends "res://scripts/main.gd"
## Vista de la demo. El núcleo de tráfico no depende de estos nodos.
const Network = preload("res://scripts/network_world.gd")
const Catalog = preload("res://scripts/fleet_catalog.gd")
const Chart = preload("res://scripts/demand_chart.gd")
var city_root: Node3D
var sensor_root: Node3D
var street_info: Dictionary = {}
var environment_info: Dictionary = {}
var fade_materials: Array = []
var building_material: StandardMaterial3D
var cross_select: OptionButton
var camera_select: OptionButton
var side_panel: PanelContainer
var top_panel: PanelContainer
var interface_layer: CanvasLayer
var inspector_side_was_visible: bool = true
var scenario_select: OptionButton
var sensor_labels: Array[Label] = []
var phase_bar: ProgressBar
var event_label: RichTextLabel
var metrics_label: Label
var notice_label: Label
var chart: Control
var time_scale: float = 1.0
var accumulator: float = 0.0
var camera_mode: int = 0
var follow_id: int = -1
var camera_target := Vector3.ZERO
var collider_enabled: bool = false
var zones_enabled: bool = false
var transparent_buildings: bool = false
var export_dialog: FileDialog
var export_kind: String = "csv"
var inspector_active: bool = false
var inspector_was_paused: bool = false
var studio: Node3D
var studio_camera: Camera3D
var studio_yaw: float = 0.5
var studio_distance: float = 15.0
var studio_select: OptionButton
var studio_panel: PanelContainer
var studio_model: Node3D
var comparing: bool = false
var comparison_cancel: bool = false
var comparison_results: Array = []
var comparison_label: Label
var comparison_panel: PanelContainer
var comparison_status: Label
var comparison_progress: ProgressBar
var scenario_names = ["Normal · 36 vehículos", "Hora punta Norte–Sur · 54", "Hora punta Este–Oeste · 54", "Sin demanda · todo rojo"]

func _ready() -> void:
	world = Network.new()
	_build_environment()
	camera.far = 1800.0
	camera.near = 1.0
	_build_city()
	_build_hud()
	_sync_cars()
	_select_cross(4)
	_update_hud()

func _build_environment() -> void:
	super._build_environment()
	camera.fov = 45.0
	for child in get_children():
		if child is WorldEnvironment:
			var sky_material := ProceduralSkyMaterial.new()
			sky_material.sky_top_color = Color("7597af")
			sky_material.sky_horizon_color = Color("cbd3cd")
			sky_material.ground_bottom_color = Color("7f8b78")
			sky_material.ground_horizon_color = Color("cbd3cd")
			var sky := Sky.new()
			sky.sky_material = sky_material
			child.environment.sky = sky
			child.environment.background_mode = Environment.BG_SKY
			child.environment.ambient_light_color = Color("dbe4eb")
			child.environment.ambient_light_energy = 0.27
			child.environment.ambient_light_sky_contribution = 0.0
		if child is DirectionalLight3D:
			child.rotation_degrees = Vector3(-54, -27, 0)
			child.light_color = Color("fff0d5")
			child.light_energy = 0.76
			child.directional_shadow_max_distance = 340

func _physics_process(delta: float) -> void:
	if not paused:
		accumulator += minf(delta, 0.2) * time_scale
		var steps: int = 0
		while accumulator + 0.0000001 >= 1.0 / 60.0 and steps < 12:
			world.tick(1.0 / 60.0)
			accumulator -= 1.0 / 60.0
			steps += 1
	_sync_cars()

func _process(delta: float) -> void:
	hud_clock += delta
	if hud_clock >= 0.15:
		hud_clock = 0.0
		_update_hud()
	if inspector_active:
		_update_studio_camera()
	else:
		var target := Vector3(world.centers[world.selected].x, 0, world.centers[world.selected].y - 8.0)
		if camera_mode == 2: target = Vector3.ZERO
		if camera_mode == 1:
			for car in world.vehicles:
				if int(car.id) == follow_id: target = Vector3(car.x, 0, car.z)
		camera_target = camera_target.lerp(target, 1.0 - exp(-delta * 7.0))
		_update_camera()

func _unhandled_input(event: InputEvent) -> void:
	if comparing:
		if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE: comparison_cancel = true
		return
	if inspector_active:
		if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE: _close_inspector()
		if event is InputEventMouseMotion and (event.button_mask & MOUSE_BUTTON_MASK_RIGHT): studio_yaw -= event.relative.x * 0.008
		if event is InputEventMouseButton and event.pressed:
			if event.button_index == MOUSE_BUTTON_WHEEL_UP: studio_distance = maxf(7, studio_distance * 0.9)
			if event.button_index == MOUSE_BUTTON_WHEEL_DOWN: studio_distance = minf(28, studio_distance / 0.9)
		return
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_HOME:
		_select_cross(world.selected)
		return
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_ESCAPE and reference_panel.visible: reference_panel.hide()
		elif event.keycode == KEY_SPACE: _toggle_pause()
		elif event.keycode == KEY_F1: side_panel.visible = not side_panel.visible
		elif event.keycode == KEY_F2: interface_layer.visible = not interface_layer.visible
	elif event is InputEventMouseMotion and (event.button_mask & (MOUSE_BUTTON_MASK_RIGHT | MOUSE_BUTTON_MASK_MIDDLE)):
		camera_yaw -= event.relative.x * 0.006
		camera_elevation = clampf(camera_elevation + event.relative.y * 0.004, 0.30, 1.48)
	elif event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP: camera_distance *= 0.9
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN: camera_distance /= 0.9
		camera_distance = clampf(camera_distance, 45.0, 1000.0)

func _update_camera() -> void:
	var horizontal: float = cos(camera_elevation) * camera_distance
	camera.position = camera_target + Vector3(sin(camera_yaw) * horizontal, sin(camera_elevation) * camera_distance, cos(camera_yaw) * horizontal)
	camera.look_at(camera_target)
	camera.h_offset = -camera_distance * 0.10 if side_panel == null or side_panel.visible else 0.0

func _batch(transforms: Array, material: Material) -> void:
	var mesh := BoxMesh.new()
	mesh.size = Vector3.ONE
	var batch := MultiMesh.new()
	batch.transform_format = MultiMesh.TRANSFORM_3D
	batch.mesh = mesh
	batch.instance_count = transforms.size()
	for i in range(transforms.size()): batch.set_instance_transform(i, transforms[i])
	var holder := MultiMeshInstance3D.new()
	holder.multimesh = batch
	holder.material_override = material
	city_root.add_child(holder)

func _mark(list: Array, size: Vector3, at: Vector3) -> void:
	list.append(Transform3D(Basis.IDENTITY.scaled(size), at))

func _build_city() -> void:
	city_root = Node3D.new()
	add_child(city_root)
	sensor_root = Node3D.new()
	city_root.add_child(sensor_root)
	building_material = _material(Color("bfc2bc"))
	street_info = preload("res://scripts/reference_street.gd").build(city_root, world.centers, building_material)
	var setting: Dictionary = preload("res://scripts/reference_environment.gd").build(city_root, world.centers, building_material, street_info.get("tree_positions", []))
	fade_materials = setting.get("fade_materials", [])
	environment_info = setting
	for index in range(9):
		_build_node_signals(index)
		var c: Vector2 = world.centers[index]
		var label := Label3D.new()
		label.text = "I-%d%s" % [index + 1, " · CENTRAL" if index == 4 else ""]
		label.position = Vector3(c.x - 16, 1.2, c.y + 23)
		label.font_size = 38
		label.pixel_size = 0.045
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.modulate = Color("e3eedf")
		city_root.add_child(label)
	_set_buildings(false)
	_update_zones()

func _build_node_signals(index: int) -> void:
	var c: Vector2 = world.centers[index]
	var positions = [Vector2(-12.7 if index == 4 else -9.2, -20), Vector2(20, -9.2), Vector2(9.2, 20), Vector2(-20, 9.2)]
	var pole := _material(Color("7a9196"))
	var housing := _material(Color("111d27"))
	for approach in range(4):
		var root := Node3D.new()
		root.position = Vector3(c.x + positions[approach].x, 0, c.y + positions[approach].y)
		city_root.add_child(root)
		_box(root, Vector3(0.22, 4.2, 0.22), Vector3(0, 2.1, 0), pole)
		_box(root, Vector3(0.85, 2.05, 0.65), Vector3(0, 4.2, 0), housing)
		var bulbs: Array = []
		for slot in range(3):
			var bulb := MeshInstance3D.new()
			var sphere := SphereMesh.new()
			sphere.radius = 0.29
			sphere.height = 0.58
			sphere.radial_segments = 8
			sphere.rings = 4
			bulb.mesh = sphere
			bulb.position = Vector3(0, 4.8 - slot * 0.59, 0.35)
			root.add_child(bulb)
			bulbs.append(bulb)
		lamps[index * 4 + approach] = bulbs

func _update_zones() -> void:
	if sensor_root == null: return
	for child in sensor_root.get_children():
		sensor_root.remove_child(child)
		child.queue_free()
	var c: Vector2 = world.centers[world.selected]
	var depth: float = world.detector_depth
	var junction = world.junctions[world.selected]
	for heading in range(4):
		var vertices := PackedVector3Array()
		for segment in range(20):
			var quad: Array[Vector3] = []
			for edge in [segment, segment + 1]:
				var pose: Dictionary = junction.straight_pose(heading, -junction.stop_line - depth * edge / 20.0)
				var lateral := Vector2(cos(float(pose.yaw)), -sin(float(pose.yaw))) * 1.55
				var point := Vector2(pose.x, pose.z) + c
				quad.append(Vector3(point.x - lateral.x, 0.09, point.y - lateral.y))
				quad.append(Vector3(point.x + lateral.x, 0.09, point.y + lateral.y))
			for vertex in [quad[0], quad[1], quad[2], quad[1], quad[3], quad[2]]: vertices.append(vertex)
		var arrays: Array = []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = vertices
		var mesh := ArrayMesh.new()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		var zone := MeshInstance3D.new()
		zone.mesh = mesh
		var material := _material(Color(0.08, 0.65, 0.53, 0.16))
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		material.cull_mode = BaseMaterial3D.CULL_DISABLED
		zone.material_override = material
		sensor_root.add_child(zone)
	sensor_root.visible = zones_enabled

func _car_node(id: int) -> Node3D:
	var root: Node3D = FleetVisual.create_vehicle(id)
	city_root.add_child(root)
	var spec: Dictionary = Catalog.for_id(id)
	var debug_material := _material(Color(0.2, 0.95, 0.9, 0.15))
	debug_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	var debug := _box(root, Vector3(spec.width, 1.7, spec.length), Vector3(0, 0.85, 0), debug_material)
	debug.name = "CollisionVolume"
	debug.visible = collider_enabled
	var warning := Label3D.new()
	warning.name = "IncidentMarker"
	warning.text = "!"
	warning.font_size = 72
	warning.pixel_size = 0.035
	warning.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	warning.position.y = 4.0
	warning.modulate = Color("ffc35c")
	warning.visible = false
	root.add_child(warning)
	return root

func _sync_cars() -> void:
	if city_root == null: return
	for vehicle in world.vehicles:
		var id: int = int(vehicle.id)
		if car_nodes.has(id) and car_nodes[id].position.distance_to(Vector3(vehicle.x, 0, vehicle.z)) > 50.0:
			car_nodes[id].position = Vector3(vehicle.x, 0, vehicle.z)
			car_nodes[id].reset_physics_interpolation()
	super._sync_cars()
	for vehicle in world.vehicles:
		var root: Node3D = car_nodes[int(vehicle.id)]
		root.get_node("CollisionVolume").visible = collider_enabled
		root.get_node("IncidentMarker").visible = float(vehicle.get("incident_remaining", 0.0)) > 0.0 and int(world.simulation_time / 0.35) % 2 == 0
		var visual: Node3D = root.get_child(0)
		visual.rotation.x = lerpf(visual.rotation.x, clampf(-float(vehicle.acceleration) * 0.004, -0.03, 0.03), 0.12)

func _section(parent: Node, title: String) -> VBoxContainer:
	var scroll := ScrollContainer.new()
	scroll.name = title
	parent.add_child(scroll)
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation", 10)
	scroll.add_child(column)
	return column

func _text(parent: Node, message: String, size: int = 15, color: Color = Color("b5ccd6")) -> Label:
	var label: Label = _label(message, size, color)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	parent.add_child(label)
	return label

func _button(parent: Node, title: String, callback: Callable) -> Button:
	var button := Button.new()
	button.text = title
	button.pressed.connect(callback)
	parent.add_child(button)
	return button

func _check(parent: Node, title: String, value: bool, callback: Callable) -> CheckButton:
	var check := CheckButton.new()
	check.text = title
	check.button_pressed = value
	check.toggled.connect(callback)
	parent.add_child(check)
	return check

func _build_hud() -> void:
	var layer := CanvasLayer.new()
	interface_layer = layer
	add_child(layer)
	var top := PanelContainer.new()
	top_panel = top
	layer.add_child(top)
	top.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	top.offset_left = 18
	top.offset_right = -18
	top.offset_top = 14
	top.offset_bottom = 96
	top.add_theme_stylebox_override("panel", _panel_style(Color("0b1925")))
	var top_row := HBoxContainer.new()
	top_row.add_theme_constant_override("separation", 14)
	top.add_child(top_row)
	var brand := VBoxContainer.new()
	brand.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top_row.add_child(brand)
	brand.add_child(_label("FTI  /  SEMÁFORO INTELIGENTE", 23, Color("e1f4ed")))
	metrics_label = _label("9 cruces conectados · 3 modelos STL", 14, Color("81cabf"))
	brand.add_child(metrics_label)
	pause_button = _button(top_row, "Pausar", _toggle_pause)
	_button(top_row, "Reiniciar", _reset_world)
	var speed := OptionButton.new()
	for title in ["×0,5", "×1", "×2", "×4"]: speed.add_item(title)
	speed.select(1)
	speed.item_selected.connect(func(index: int): time_scale = [0.5, 1.0, 2.0, 4.0][index])
	top_row.add_child(speed)
	_button(top_row, "Plano", func(): reference_panel.show())
	_button(top_row, "Panel", func(): side_panel.visible = not side_panel.visible)
	var panel := PanelContainer.new()
	side_panel = panel
	layer.add_child(panel)
	panel.set_anchors_and_offsets_preset(Control.PRESET_LEFT_WIDE)
	panel.offset_left = 18
	panel.offset_right = 342
	panel.offset_top = 112
	panel.offset_bottom = -44
	panel.add_theme_stylebox_override("panel", _panel_style(Color(0.035, 0.07, 0.105, 0.97)))
	var tabs := TabContainer.new()
	panel.add_child(tabs)
	var control: VBoxContainer = _section(tabs, "Control")
	_text(control, "CRUCE OBSERVADO", 13)
	cross_select = OptionButton.new()
	for index in range(9): cross_select.add_item("I-%d%s" % [index + 1, " · Centro" if index == 4 else ""])
	cross_select.select(4)
	cross_select.item_selected.connect(_select_cross)
	control.add_child(cross_select)
	mode_select = OptionButton.new()
	for title in ["FTI · demanda", "Adaptativo + V2I", "Ciclo fijo"]: mode_select.add_item(title)
	mode_select.item_selected.connect(func(index: int): world.set_mode(["fti", "adaptive", "fixed"][index]))
	control.add_child(mode_select)
	status_label = _text(control, "", 20, Color("7ce3bf"))
	phase_bar = ProgressBar.new()
	phase_bar.show_percentage = false
	phase_bar.custom_minimum_size.y = 8
	control.add_child(phase_bar)
	detail_label = _text(control, "", 13)
	for index in range(4): sensor_labels.append(_text(control, "", 15))
	queues_label = _text(control, "", 13)
	chart = Chart.new()
	chart.custom_minimum_size = Vector2(250, 85)
	control.add_child(chart)
	_text(control, "Demanda detectada · últimos 60 s", 12)
	sensor_toggle = _check(control, "Sensores de este cruce", true, func(enabled: bool): world.set_sensor(world.selected, enabled))
	_text(control, "Longitud de detección (25–85 m)", 13)
	var depth := HSlider.new()
	depth.min_value = 25
	depth.max_value = 85
	depth.step = 5
	depth.value = 55
	depth.value_changed.connect(func(value: float): world.set_depth(value); _update_zones())
	control.add_child(depth)
	_check(control, "Mostrar zonas", false, func(value: bool): zones_enabled = value; sensor_root.visible = value)
	var scenarios: VBoxContainer = _section(tabs, "Demo")
	_text(scenarios, "ESCENARIOS REPRODUCIBLES", 13)
	scenario_select = OptionButton.new()
	for title in scenario_names: scenario_select.add_item(title)
	scenario_select.item_selected.connect(_choose_scenario)
	scenarios.add_child(scenario_select)
	_text(scenarios, "Cambiar de escenario reinicia el reloj y las métricas. Cambiar de modo conserva el tráfico y respeta amarillo + despeje.", 14)
	_button(scenarios, "Fallar sensores de toda la red", func(): world.sensor_enabled = false; world.log_event("Red sin lecturas de sensores"))
	_button(scenarios, "Restaurar sensores de la red", func(): world.sensor_enabled = true; world.log_event("Lecturas de red restauradas"))
	_text(scenarios, "V2I · solicitud temporal al cruce observado. Opera en modo adaptativo; no fuerza un verde inmediato.", 14)
	_button(scenarios, "Prioridad Norte–Sur · 20 s", func(): world.request_priority("NS"))
	_button(scenarios, "Prioridad Este–Oeste · 20 s", func(): world.request_priority("EW"))
	_button(scenarios, "Cancelar prioridad", func(): world.request_priority(""))
	_button(scenarios, "Incidente · detención de 12 s", func(): world.incident())
	_text(scenarios, "FTI: 5 s de verde + 2 s amarillo. Fijo: 11 + 2,5 s. Todos los modos esperan al menos 1 s de despeje y que el cruce esté libre.", 14)
	var fleet: VBoxContainer = _section(tabs, "Vista")
	_text(fleet, "CÁMARA Y FLOTA", 13)
	var cameras := OptionButton.new()
	camera_select = cameras
	for title in ["Libre · cruce observado", "Seguir un vehículo", "Vista de toda la red"]: cameras.add_item(title)
	cameras.item_selected.connect(_set_camera_mode)
	fleet.add_child(cameras)
	_check(fleet, "Edificios transparentes", false, _set_buildings)
	_check(fleet, "Volúmenes de colisión", false, func(value: bool): collider_enabled = value)
	_text(fleet, "Flota actual: SUV, pickup y bus. Las dimensiones de cada malla coinciden con sus volúmenes de tráfico.", 14)
	_button(fleet, "Inspeccionar modelos", _open_inspector)
	_text(fleet, "Botón derecho: orbitar. Rueda: zoom. Inicio: centrar. Espacio: pausa. F1: panel. F2: presentación sin interfaz.", 14)
	var data: VBoxContainer = _section(tabs, "Datos")
	_text(data, "TELEMETRÍA · 9 CRUCES", 13)
	_button(data, "Guardar métricas CSV", func(): _ask_export("csv"))
	_button(data, "Guardar configuración JSON", func(): _ask_export("json"))
	_button(data, "Comparar 3 modos · 120 s", func(): _run_comparison())
	comparison_label = _text(data, "Ensayo aislado: misma flota inicial y escenario, sensores en línea. No modifica el estado de la demo.", 13)
	_button(data, "Guardar comparación CSV", func(): _ask_export("comparison"))
	_text(data, "Muestra cada segundo simulado. Retención: 30 min. La espera es el tiempo detenido acumulado medio de la flota activa.", 13)
	event_label = RichTextLabel.new()
	event_label.custom_minimum_size = Vector2(245, 340)
	event_label.add_theme_font_size_override("normal_font_size", 13)
	data.add_child(event_label)
	notice_label = Label.new()
	notice_label.add_theme_color_override("font_outline_color", Color("17242a"))
	notice_label.add_theme_constant_override("outline_size", 5)
	notice_label.text = "I-5 · Centro   |   9 cruces conectados · paso fijo 60 Hz"
	notice_label.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	notice_label.offset_left = 24
	notice_label.offset_top = -30
	layer.add_child(notice_label)
	_build_reference_panel(layer)
	_build_inspector(layer)
	_build_comparison_panel(layer)
	export_dialog = FileDialog.new()
	export_dialog.file_mode = FileDialog.FILE_MODE_SAVE_FILE
	export_dialog.access = FileDialog.ACCESS_FILESYSTEM
	export_dialog.file_selected.connect(_save_export)
	add_child(export_dialog)

func _select_cross(index: int) -> void:
	world.selected = index
	camera_mode = 0
	camera_distance = 139.0
	camera_yaw = 0.55
	camera_elevation = 1.06
	camera_target = Vector3(world.centers[index].x, 0, world.centers[index].y - 8.0)
	if cross_select != null: cross_select.select(index)
	if camera_select != null: camera_select.select(0)
	_update_zones()
	_update_camera()

func _choose_scenario(index: int) -> void:
	world.load_scenario(Network.SCENARIOS[index])
	accumulator = 0.0
	for root in car_nodes.values(): root.queue_free()
	car_nodes.clear()
	_sync_cars()
	_update_hud()

func _reset_world() -> void:
	_choose_scenario(scenario_select.selected)

func _set_camera_mode(value: int) -> void:
	camera_mode = value
	camera_distance = 880.0 if value == 2 else 65.0 if value == 1 else 139.0
	if value == 1:
		for car in world.vehicles:
			if int(car.junction) == world.selected:
				follow_id = int(car.id)
				break

func _set_buildings(value: bool) -> void:
	transparent_buildings = value
	building_material.albedo_color.a = 0.22 if value else 1.0
	building_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA if value else BaseMaterial3D.TRANSPARENCY_DISABLED
	for material in fade_materials:
		if material is StandardMaterial3D:
			material.albedo_color.a = 0.22 if value else 1.0
			material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA if value else BaseMaterial3D.TRANSPARENCY_DISABLED

func _update_hud() -> void:
	if status_label == null: return
	var c = world.controller
	var phase: String = "TODO ROJO" if c.stage == "ALL_RED" else "VERDE" if c.stage == "GREEN" else "AMARILLO"
	status_label.text = phase + " · " + "/".join(c.active)
	detail_label.text = c.reason
	if c.priority != "":
		detail_label.text += "\nV2I %s · %.0f s restantes" % [c.priority, maxf(0, world.priority_until[world.selected] - world.simulation_time)]
	var duration: float = c.green_duration() if c.stage == "GREEN" else c.yellow_duration() if c.stage == "YELLOW" else c.clearance
	phase_bar.value = minf(100, c.elapsed / duration * 100)
	var colors = {"RED": Color("ec7780"), "ALL_RED": Color("ec7780"), "YELLOW": Color("e9c768"), "GREEN": Color("70dfb6")}
	status_label.add_theme_color_override("font_color", colors[c.stage])
	for index in range(4):
		var approach: String = ["N", "E", "S", "W"][index]
		sensor_labels[index].text = "C%d · %s   %d veh · %d cola · %.0f s" % [index + 1, approach, c.counts[index], c.queues[index], c.wait[index]]
		sensor_labels[index].add_theme_color_override("font_color", colors[c.light(approach)])
	sensor_toggle.set_pressed_no_signal(world.junctions[world.selected].sensor_enabled)
	queues_label.text = "RESPALDO FIJO" if c.fallback else "Sensores en línea · %.0f m" % world.detector_depth if world.junctions[world.selected].sensor_enabled else "Sin señal · %.1f / 5 s" % c.sensor_age
	chart.samples = world.history[world.selected]
	chart.queue_redraw()
	var summary: Dictionary = world.metrics()
	metrics_label.text = "T+%.0f s   ·   %d vehículos   ·   %.0f km/h   ·   %d en cola   ·   %d cruces   ·   %d incidentes" % [world.simulation_time, summary.vehicles, summary.speed_kmh, summary.queued, summary.crossings, summary.incidents]
	event_label.text = "\n".join(world.events.slice(0, 30))
	for key in lamps:
		var node: int = int(key / 4)
		var approach: String = ["N", "E", "S", "W"][key % 4]
		var state: String = world.junctions[node].controller.light(approach)
		var slot: int = 0 if state == "RED" else 1 if state == "YELLOW" else 2
		for index in range(3):
			var bulb: MeshInstance3D = lamps[key][index]
			if bulb.get_meta("lit", -1) != int(index == slot):
				var color: Color = [Color("ff4b53"), Color("ffd15c"), Color("5cf0a4")][index]
				bulb.material_override = _material(color if index == slot else color * 0.12, 1.5 if index == slot else 0.0)
				bulb.set_meta("lit", int(index == slot))

func _ask_export(kind: String) -> void:
	if kind == "comparison" and comparison_results.is_empty():
		notice_label.text = "Ejecuta primero la comparación de modos."
		return
	export_kind = kind
	export_dialog.filters = PackedStringArray(["*.json ; Configuración JSON"] if kind == "json" else ["*.csv ; Métricas CSV"])
	export_dialog.current_file = "fti-comparacion.csv" if kind == "comparison" else "fti-metricas.csv" if kind == "csv" else "fti-configuracion.json"
	export_dialog.popup_centered_ratio(0.65)

func _save_export(path: String) -> void:
	var file = FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		notice_label.text = "No se pudo guardar el archivo. Selecciona otra carpeta."
		return
	file.store_string(comparison_csv() if export_kind == "comparison" else world.csv_text() if export_kind == "csv" else JSON.stringify(world.config(), "\t"))
	file.close()
	notice_label.text = "Guardado: " + path

func _build_comparison_panel(layer: CanvasLayer) -> void:
	comparison_panel = PanelContainer.new()
	layer.add_child(comparison_panel)
	comparison_panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	comparison_panel.add_theme_stylebox_override("panel", _panel_style(Color(0.025, 0.055, 0.085, 0.98)))
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 20)
	comparison_panel.add_child(column)
	_text(column, "COMPARACIÓN CONTROLADA", 25, Color("84e2c1"))
	comparison_status = _text(column, "", 20)
	_text(column, "Mismo escenario y flota para FTI, adaptativo y fijo. La red visible conserva su estado. Puedes cancelar con Esc.", 17)
	comparison_progress = ProgressBar.new()
	comparison_progress.show_percentage = true
	column.add_child(comparison_progress)
	_button(column, "Cancelar ensayo", func(): comparison_cancel = true)
	comparison_panel.hide()

func _run_comparison(seconds: float = 120.0) -> void:
	if comparing or inspector_active: return
	comparing = true
	comparison_cancel = false
	comparison_results.clear()
	var was_paused: bool = paused
	paused = true
	comparison_panel.show()
	var scenario_key: String = world.scenario
	var steps: int = roundi(clampf(seconds, 0.5, 120.0) * 60.0)
	var selected_modes: Array = ["fti", "adaptive", "fixed"]
	for index in range(3):
		var bench = Network.new()
		bench.set_mode(selected_modes[index])
		bench.set_depth(world.detector_depth)
		bench.load_scenario(scenario_key)
		for step in range(steps):
			if comparison_cancel: break
			bench.tick(1.0 / 60.0)
			if step % 30 == 0:
				comparison_status.text = "%s · %.0f / %.0f s · %s" % [selected_modes[index].to_upper(), bench.simulation_time, seconds, scenario_key]
				comparison_progress.value = (index + float(step) / steps) / 3.0 * 100.0
				await get_tree().process_frame
		if comparison_cancel: break
		var result: Dictionary = bench.metrics()
		result.mode = selected_modes[index]
		result.scenario = scenario_key
		result.seconds = seconds
		comparison_results.append(result)
	comparison_panel.hide()
	comparing = false
	paused = was_paused
	pause_button.text = "Continuar" if paused else "Pausar"
	if comparison_cancel:
		comparison_results.clear()
		comparison_label.text = "Ensayo cancelado. El estado de la red se conservó."
	else:
		var lines := PackedStringArray(["Resultado a %.0f s · %s" % [seconds, scenario_key]])
		for result in comparison_results:
			lines.append("%s: %d cruces · %.1f s detenido/veh · %.1f km/h" % [result.mode.to_upper(), result.crossings, result.mean_wait, result.speed_kmh])
		comparison_label.text = "\n".join(lines)

func comparison_csv() -> String:
	var lines := PackedStringArray(["modo,escenario,segundos,vehiculos,cruces,espera_acumulada_media_s,velocidad_final_media_kmh"])
	for result in comparison_results:
		lines.append("%s,%s,%s,%d,%d,%s,%s" % [result.mode, result.scenario, result.seconds, result.vehicles, result.crossings, result.mean_wait, result.speed_kmh])
	return "\n".join(lines) + "\n"

func _build_inspector(layer: CanvasLayer) -> void:
	studio = Node3D.new()
	studio.visible = false
	add_child(studio)
	_box(studio, Vector3(30, 0.1, 30), Vector3(0, -0.1, 0), _material(Color("233441")))
	studio_camera = Camera3D.new()
	studio_camera.fov = 45
	studio.add_child(studio_camera)
	studio_panel = PanelContainer.new()
	layer.add_child(studio_panel)
	studio_panel.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	studio_panel.offset_left = -380
	studio_panel.offset_right = -20
	studio_panel.offset_top = 120
	studio_panel.offset_bottom = 370
	studio_panel.add_theme_stylebox_override("panel", _panel_style(Color("0b1925")))
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 14)
	studio_panel.add_child(column)
	_text(column, "FLOTA · INSPECCIÓN 3D", 21)
	studio_select = OptionButton.new()
	for spec in Catalog.MODELS: studio_select.add_item(spec.key.to_upper())
	studio_select.item_selected.connect(_show_model)
	column.add_child(studio_select)
	_text(column, "STL original · material sólido\nBotón derecho: girar · rueda: zoom\nLa red permanece pausada durante la inspección.")
	_button(column, "Volver a la simulación · Esc", _close_inspector)
	studio_panel.hide()

func _open_inspector() -> void:
	if inspector_active: return
	inspector_was_paused = paused
	inspector_side_was_visible = side_panel.visible
	paused = true
	inspector_active = true
	top_panel.hide()
	side_panel.hide()
	city_root.hide()
	studio.show()
	studio_panel.show()
	studio_camera.current = true
	_show_model(studio_select.selected)

func _show_model(index: int) -> void:
	if studio_model != null:
		studio.remove_child(studio_model)
		studio_model.queue_free()
	studio_model = FleetVisual.create_vehicle(index + 1)
	studio.add_child(studio_model)
	_update_studio_camera()

func _update_studio_camera() -> void:
	studio_camera.position = Vector3(sin(studio_yaw) * studio_distance, studio_distance * 0.42, cos(studio_yaw) * studio_distance)
	studio_camera.look_at(Vector3(0, 1, 0))

func _close_inspector() -> void:
	if not inspector_active: return
	inspector_active = false
	paused = inspector_was_paused
	pause_button.text = "Continuar" if paused else "Pausar"
	studio.hide()
	studio_panel.hide()
	top_panel.show()
	side_panel.visible = inspector_side_was_visible
	city_root.show()
	camera.current = true
