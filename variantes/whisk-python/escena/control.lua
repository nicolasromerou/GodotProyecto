-- Whisk3D dibuja e interpola las instantáneas del simulador Python.
local approaches = {"N", "E", "S", "W"}
local colors = {"Rojo", "Amarillo", "Verde"}
local selected = {RED=1, YELLOW=2, GREEN=3}
local on = {{1,.08,.03}, {1,.74,.02}, {.09,1,.24}}
local off = {{.20,.03,.03}, {.18,.12,.02}, {.02,.16,.04}}
local cars, lamps, poses, lamp_state = {}, {}, {}, {}
local since_frame, since_poll, blend_duration, epoch, sequence
local rendered, stale, paused, camera, pending_ack, title
local view, azimuth, elevation, zoom = "barrio", 40, 49, 100
local fitted_view, last_aspect, last_azimuth, last_elevation, last_zoom = nil, 0, 0, 0, 0
-- Distancia y apertura base. La orientación se puede cambiar desde Python.
local views = {barrio={138,55}, cruce={75,55}, avenida={132,53}, cenital={148,60}}
local scenarios = {normal="Normal", moderate="Moderado", peak_ns="Punta N-S", peak_ew="Punta E-O",
                   saturation="Saturación", manual="Manual", empty="Sin tráfico"}
local modes = {fti="FTI", adaptive="Adaptativo", fixed="Fijo", python="Coordinado", fallback="Respaldo fijo"}

local function frame_camera()
  local width, height = resolucion()
  if width < 1 or height < 1 then return false end
  local aspect = width / height
  if view == fitted_view and azimuth == last_azimuth and elevation == last_elevation
     and zoom == last_zoom and math.abs(aspect - last_aspect) < .004 then return true end
  local p = views[view]
  -- En vertical combina distancia y apertura para conservar el cruce a la vista.
  local scale = math.sqrt(math.min(3.2, math.max(1, 1.25 / aspect)))
  local yaw, pitch = math.rad(azimuth), math.rad(elevation)
  local distance = p[1] * scale
  local ground = distance * math.cos(pitch)
  setPosicion(camera, ground * math.sin(yaw), distance * math.sin(pitch), ground * math.cos(yaw))
  setLente(camera, math.deg(2 * math.atan(math.tan(math.rad(p[2] / 2)) * scale * 100 / zoom)))
  fitted_view, last_aspect, last_azimuth, last_elevation, last_zoom = view, aspect, azimuth, elevation, zoom
  setCompartido("fti_vista", view)
  setCompartido("fti_angulo", azimuth)
  return true
end

local function lights(values)
  for _, approach in ipairs(approaches) do
    local signal = values[approach]
    if signal ~= lamp_state[approach] then
      for i, obj in ipairs(lamps[approach]) do
        local tint = selected[signal] == i and on[i] or off[i]
        setTinte(obj, tint[1], tint[2], tint[3])
      end
      lamp_state[approach] = signal
    end
  end
end

local function draw_pose(obj, pose, blend)
  local a, b = pose.start, pose.target
  local x, z, yaw = b.x, b.z, b.yaw
  if blend < 1 and a ~= b then
    local turn = (b.yaw - a.yaw + math.pi) % (2 * math.pi) - math.pi
    x, z, yaw = a.x+(b.x-a.x)*blend, a.z+(b.z-a.z)*blend, a.yaw+turn*blend
  end
  local previous = pose.display
  if not previous or x ~= previous.x or z ~= previous.z then setPosicion(obj, x, 0, z) end
  if not previous or yaw ~= previous.yaw then setRotacion(obj, 0, math.deg(yaw), 0) end
  if not previous or x ~= previous.x or z ~= previous.z or yaw ~= previous.yaw then
    pose.display = {x=x, z=z, yaw=yaw}
  end
end

local function fields(line)
  local result = {}
  for word in string.gmatch(line or "", "%S+") do result[#result + 1] = word end
  return result
end

local function integer(value, minimum, maximum)
  local n = math.tointeger(tonumber(value))
  if n and n >= minimum and (not maximum or n <= maximum) then return n end
end

local function read_snapshot(payload)
  local rows = string.gmatch(payload, "[^\n]+")
  local header = fields(rows())
  local serial, generation, time = integer(header[2], 1), integer(header[3], 0), tonumber(header[4])
  local yaw, pitch, quantity = tonumber(header[6]), tonumber(header[7]), integer(header[12], 0, 72)
  local command, zoom_percent = integer(header[13], 0), integer(header[15], 60, 175)
  local is_paused, scenario, mode, sensors = header[14], header[16], header[17], header[18]
  if #header ~= 18 or header[1] ~= "FTI2" or not serial or serial <= sequence
     or not generation or not time or not (time >= 0 and time < math.huge) or not views[header[5]]
     or not yaw or yaw < 0 or yaw > 360 or not pitch or pitch < 12 or pitch > 87
     or not command or not zoom_percent
     or (is_paused ~= "0" and is_paused ~= "1") or (sensors ~= "0" and sensors ~= "1")
     or not scenarios[scenario] or not modes[mode] or not quantity then return end
  local signals, rows_validated, ids, slots, models = {}, {}, {}, {}, {}
  for i, side in ipairs(approaches) do
    if not selected[header[7 + i]] then return end
    signals[side] = header[7 + i]
  end
  for _=1,quantity do
    local row = fields(rows())
    local id, slot = integer(row[1], 1), integer(row[3], 1, 72)
    local x, z, heading = tonumber(row[4]), tonumber(row[5]), tonumber(row[6])
    if #row ~= 6 or not id or ids[id] or not slot or not x or not z or not heading
       or math.abs(x) > 150 or math.abs(z) > 150 or math.abs(heading) > 4 then return end
    local model = row[2]
    local base = cars[model] and cars[model][1] or buscar("fti_base_" .. model)
    local key = model .. ":" .. slot
    if not base or slots[key] then return end
    ids[id], slots[key], models[model] = true, true, base
    rows_validated[#rows_validated + 1] = {id=id, model=model, slot=slot, x=x, z=z, yaw=heading}
  end
  if rows() then return end

  -- La escena carga una malla por modelo. Solo añadimos las instancias que
  -- llegan a I-5 y las reutilizamos si la mezcla de tráfico cambia.
  local frame, model_count = {}, 0
  for model, base in pairs(models) do
    cars[model] = cars[model] or {base}
    model_count = model_count + 1
  end
  for _, car in ipairs(rows_validated) do
    local pool = cars[car.model]
    local obj = pool[car.slot] or instanciar("fti_" .. car.model)
    if not obj then return end
    pool[car.slot], frame[obj] = obj, car
  end
  local changed_epoch = epoch ~= generation
  paused = is_paused == "1"
  blend_duration = math.max(.033, math.min(.1, since_frame))
  for obj, car in pairs(frame) do
    local last = poses[obj]
    local previous = not paused and not stale and not changed_epoch and last and last.id == car.id and last.display or car
    -- Los reingresos cambian de posición sin atravesar el barrio en la imagen.
    if math.abs(previous.x-car.x) > 30 or math.abs(previous.z-car.z) > 30 then
      previous = car
    end
    poses[obj] = {id=car.id, start=previous, target=car, display=last and last.display}
    if not last then setVisible(obj, true) end
  end
  for obj in pairs(poses) do
    if not frame[obj] then
      setVisible(obj, false)
      poses[obj] = nil
    end
  end
  since_frame, rendered, stale, epoch, sequence = 0, true, false, generation, serial
  view, azimuth, elevation, zoom = header[5], yaw, pitch, zoom_percent
  lights(signals)
  pending_ack = string.format("FTI2 %d %d %d %s %.2f %.2f %d %d %s %s %s %s %s %s %s %s", serial, generation,
                              quantity, view, yaw, pitch, zoom, command, is_paused, sensors, scenario, mode,
                              signals.N, signals.E, signals.S, signals.W)
  title = string.format("FTI I-5 | %s | %s | %s | %d en escena%s", scenarios[scenario], modes[mode],
                        paused and "En pausa" or "En marcha", quantity, sensors == "0" and " | Sin sensores" or "")
  setCompartido("fti_estado", "PYTHON")
  setCompartido("fti_time", time)
  setCompartido("fti_vehiculos", quantity)
  setCompartido("fti_modelos", model_count)
end

function inicio()
  poses, lamp_state = {}, {}
  since_frame, since_poll, blend_duration, epoch, sequence = 2, 0, .05, nil, 0
  rendered, stale, paused = false, false, true
  fitted_view, pending_ack, title = nil, nil, nil
  camera = assert(buscar("Camara"), "Falta la cámara de I-5")
  for _, pool in pairs(cars) do
    for _, obj in pairs(pool) do
      setVisible(obj, false)
    end
  end
  for _, approach in ipairs(approaches) do
    lamps[approach] = {}
    for i, color in ipairs(colors) do
      lamps[approach][i] = assert(buscar(approach .. color), "Falta semáforo " .. approach)
    end
  end
  lights({N="RED", E="RED", S="RED", W="RED"})
  setCompartido("fti_estado", "ESPERANDO")
end

function actualizar(dt)
  since_frame = since_frame + dt
  since_poll = since_poll + dt
  if ftiLeer and since_poll >= .032 then
    since_poll = 0
    local payload = ftiLeer()
    if payload then read_snapshot(payload) end
  end
  local camera_ready = frame_camera()
  if rendered and not stale and since_frame > 2 then
    stale, pending_ack = true, nil
    setCompartido("fti_estado", "SIN_ENLACE")
    if ftiConfirmar then ftiConfirmar("", paused, "FTI I-5 | Sin datos recientes") end
  end
  local blend = math.min(1, since_frame / blend_duration)
  for obj, pose in pairs(poses) do
    draw_pose(obj, pose, blend)
  end
  if camera_ready and pending_ack and ftiConfirmar and ftiConfirmar(pending_ack, paused, title) then pending_ack = nil end
end
