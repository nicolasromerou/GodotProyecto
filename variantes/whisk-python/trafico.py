"""Red de nueve cruces. Python resuelve sensores, movimiento y colisiones."""
from collections import deque
from dataclasses import dataclass
from math import cos, floor, hypot, inf, sin
from pathlib import Path
import json

from geometria import (
    FORWARD, LANE_WIDTH, STOP_LINE, TURN_ENTRY, YAW, Body, Route,
    follow_speed, lane_offset, overlap, route, straight_pose,
)
from semaforos import Controller

TICKS_PER_SECOND = 30
STEP = 1 / TICKS_PER_SECOND
SPACING = 210.0
WORLD_LIMIT = SPACING / 2
CELL_SIZE = 18.0
QUEUE_SPEED = 14 / 3.6
SENSOR_INDEX = (0, 3, 2, 1)
APPROACH_FOR_HEADING = ("N", "W", "S", "E")
TURNS = (0, 1, 0, -1, 0)
SCENARIO_COUNTS = {"normal": 36, "moderate": 90, "peak_ns": 180, "peak_ew": 180, "saturation": 324, "empty": 0}
MANUAL_MAX = 36
MODELS = json.loads(Path(__file__).with_name("flota.json").read_text(encoding="utf-8"))
MAX_RADIUS = max(hypot(model["length"], model["width"]) / 2 for model in MODELS)
CONFLICT = Body.box(0, 0, 0, 36, 36)


@dataclass(slots=True)
class Neighbor(Body):
    id: int
    heading: int
    lane: int
    planned_turn: int
    speed: float = 0.0


@dataclass(slots=True)
class Vehicle(Neighbor):
    model: str = ""
    desired_speed: float = 0.0
    radius: float = 0.0
    path: Route | None = None
    path_distance: float = 0.0
    committed: bool = False
    cleared: bool = False
    hops: int = 0
    waiting: float = 0.0

    def longitudinal(self):
        fx, fz = FORWARD[self.heading]
        return self.x * fx + self.z * fz

    def set_pose(self, pose):
        self.x, self.z, self.yaw = pose
        self.fx, self.fz = sin(self.yaw), cos(self.yaw)


class Junction:
    def __init__(self, index, mode):
        self.central = index == 4
        self.controller = Controller(mode)
        self.sensor_enabled = True
        self.vehicles = []
        self.external = []
        self.cells = {}
        self.reservation = None
        self.next_id = index * 10000 + 1
        self.crossings = 0
        self.turns = 0
        self.blocked = 0
        self.priority_until = 0.0

    def spawn(self, heading, distance, planned_turn, lane=0):
        vehicle_id = self.next_id
        spec = MODELS[(vehicle_id - 1) % len(MODELS)]
        x, z, yaw = straight_pose(self.central, heading, -distance, lane)
        car = Vehicle(x, z, yaw, spec["length"] / 2, spec["width"] / 2, sin(yaw), cos(yaw),
                      vehicle_id, heading, lane, planned_turn, model=spec["key"],
                      desired_speed=12 + vehicle_id % 3, radius=hypot(spec["length"], spec["width"]) / 2)
        if any(overlap(car, other, 2.0 if lane == other.lane else .25) for other in self.vehicles):
            raise RuntimeError(f"No hay espacio para crear el vehículo {vehicle_id}.")
        self.vehicles.append(car)
        self.next_id += 1

    def occupied(self):
        for car in self.vehicles:
            if car.committed and not car.cleared:
                return True
            if abs(car.x) <= 18 + car.radius and abs(car.z) <= 18 + car.radius and overlap(car, CONFLICT):
                return True
        return False

    def sense(self):
        counts, queues = [0] * 4, [0] * 4
        for car in self.vehicles:
            if car.cleared or car.path is not None:
                continue
            distance = -car.longitudinal()
            if not STOP_LINE <= distance <= STOP_LINE + 55:
                continue
            fx, fz = FORWARD[car.heading]
            lateral = -car.x * fz + car.z * fx
            if abs(lateral - lane_offset(self.central, car.heading, -distance, car.lane)) <= LANE_WIDTH / 2:
                index = SENSOR_INDEX[car.heading]
                counts[index] += 1
                queues[index] += car.speed < QUEUE_SPEED
        self.controller.sense(counts, queues)

    def _index(self):
        self.cells.clear()
        for car in self.vehicles + self.external:
            cell = (floor(car.x / CELL_SIZE), floor(car.z / CELL_SIZE))
            self.cells.setdefault(cell, []).append(car)

    def _nearby(self, x, z, end_x, end_z, padding):
        left = floor((min(x, end_x) - padding) / CELL_SIZE)
        right = floor((max(x, end_x) + padding) / CELL_SIZE)
        top = floor((min(z, end_z) - padding) / CELL_SIZE)
        bottom = floor((max(z, end_z) + padding) / CELL_SIZE)
        result = []
        for cell_x in range(left, right + 1):
            for cell_z in range(top, bottom + 1):
                result.extend(self.cells.get((cell_x, cell_z), ()))
        return result

    def _leader(self, car):
        fx, fz = car.fx, car.fz
        gap, speed = inf, car.desired_speed
        lateral_limit = car.half_width + MAX_RADIUS + .35
        candidates = self._nearby(car.x, car.z, car.x + fx * 85, car.z + fz * 85, lateral_limit + .65)
        for other in candidates:
            if other.id == car.id:
                continue
            if other.heading == car.heading and other.lane != car.lane and other.planned_turn == car.planned_turn == 0:
                continue
            dx, dz = other.x - car.x, other.z - car.z
            longitudinal = dx * fx + dz * fz
            if not 0 < longitudinal < 85:
                continue
            lateral = abs(dx * fz - dz * fx)
            if lateral >= lateral_limit:
                continue
            parallel = fx * other.fx + fz * other.fz
            if parallel <= .2:
                continue
            cross = abs(fz * other.fx - fx * other.fz)
            if lateral < car.half_width + other.half_length * cross + other.half_width * parallel + .35:
                candidate = longitudinal - car.half_length - other.half_length * parallel - other.half_width * cross
                if candidate < gap:
                    gap, speed = candidate, other.speed * parallel
        return gap, speed

    def _exit_blocked(self, car):
        heading = (car.heading - car.planned_turn) % 4
        target = _exit_box(self.central, heading, car.lane)
        return any(other.id != car.id and overlap(target, other)
                   for other in self._nearby(target.x, target.z, target.x, target.z, 7.7 + MAX_RADIUS))

    def step(self, dt, hold_boundary=False):
        if self.sensor_enabled:
            self.sense()
        self.controller.step(dt, self.occupied())
        for car in self.vehicles:
            if car.id == self.reservation and car.cleared and car.longitudinal() > 30:
                self.reservation = None
                break
        self._index()
        departed = []
        for car in self.vehicles:
            if not (hold_boundary and car.cleared and car.longitudinal() > WORLD_LIMIT):
                self._move(car, dt)
            if car.cleared and car.longitudinal() > WORLD_LIMIT:
                departed.append(car)
        if departed:
            ids = {car.id for car in departed}
            self.vehicles = [car for car in self.vehicles if car.id not in ids]
            if self.reservation in ids:
                self.reservation = None
        return departed

    def _move(self, car, dt):
        if car.speed < .5:
            car.waiting += dt
        distance = -car.longitudinal()
        gap, leader_speed = self._leader(car)
        desired = car.desired_speed
        turning = car.planned_turn != 0
        if turning and (car.path is not None or (not car.cleared and distance < 45)):
            desired = min(desired, 5.0 if car.planned_turn == 1 else 7.0)
        if car.path is None and not car.cleared and not car.committed:
            front_gap = distance - STOP_LINE - car.half_length
            light = self.controller.light(APPROACH_FOR_HEADING[car.heading])
            stop = light == "RED" or (light == "YELLOW" and front_gap > car.speed ** 2 / 14)
            if stop and self.reservation == car.id:
                self.reservation = None
            if (turning and not stop and self.reservation is None and front_gap < min(12.0, gap)
                    and not self.occupied() and not self._exit_blocked(car)):
                self.reservation = car.id
            can_enter = self.reservation == car.id if turning else self.reservation is None
            if front_gap < gap and (stop or not can_enter or self._exit_blocked(car)):
                gap, leader_speed = front_gap, 0.0

        speed, advance = follow_speed(car.speed, desired, gap, leader_speed, dt)
        if advance <= 0:
            car.speed = speed
            return

        path, traveled, committed = car.path, car.path_distance, car.committed
        if path is not None:
            traveled = min(path.length, traveled + advance)
            pose = path.pose(traveled)
        else:
            can_enter = self.reservation == car.id if turning else self.reservation is None
            if not car.cleared and can_enter and distance >= TURN_ENTRY > distance - advance:
                path = route(self.central, car.heading, car.planned_turn, car.lane)
                traveled = advance - (distance - TURN_ENTRY)
                pose, committed = path.pose(traveled), True
            else:
                pose = straight_pose(self.central, car.heading, -distance + advance, car.lane)
                if not car.cleared and can_enter and distance - advance < STOP_LINE + car.half_length:
                    committed = True

        x, z, yaw = pose
        candidate = Body(x, z, yaw, car.half_length, car.half_width, sin(yaw), cos(yaw))
        padding = car.radius + MAX_RADIUS + .5 + 15 * dt
        if any(other.id != car.id and overlap(candidate, other, .1)
               for other in self._nearby(x, z, x, z, padding)):
            car.speed = 0.0
            self.blocked += 1
            return

        if car.path is None and path is not None and turning:
            self.turns += 1
        car.x, car.z, car.yaw, car.fx, car.fz = x, z, yaw, candidate.fx, candidate.fz
        car.speed, car.path, car.path_distance, car.committed = speed, path, traveled, committed
        if path is not None and traveled >= path.length - 1e-7:
            car.heading = path.heading
            car.set_pose((car.x, car.z, YAW[car.heading]))
            car.path, car.cleared = None, True
            self.crossings += 1


_EXIT_BOXES = {}


def _exit_box(central, heading, lane):
    key = (central, heading, lane)
    if key not in _EXIT_BOXES:
        _EXIT_BOXES[key] = Body.box(*straight_pose(central, heading, TURN_ENTRY + 8.5, lane), 14, 2.5)
    return _EXIT_BOXES[key]


class TrafficNetwork:
    def __init__(self, scenario="normal"):
        self.mode = "adaptive" if scenario == "saturation" else "fti"
        self.centers = [((column - 1) * SPACING, (row - 1) * SPACING)
                        for row in range(3) for column in range(3)]
        self.neighbors = []
        for index, (x, z) in enumerate(self.centers):
            neighbors = []
            for fx, fz in FORWARD:
                column, row = index % 3 + fx, index // 3 + fz
                if 0 <= column < 3 and 0 <= row < 3:
                    target = row * 3 + column
                    tx, tz = self.centers[target]
                    neighbors.append((target, x - tx, z - tz))
            self.neighbors.append(neighbors)
        self.load(scenario)

    @property
    def time(self):
        return self.steps * STEP

    @property
    def central(self):
        return self.junctions[4]

    @property
    def recent_crossings(self):
        return self.crossing_history[-1] - self.crossing_history[0]

    def load(self, scenario, manual_count=None):
        if not isinstance(scenario, str) or (scenario != "manual" and scenario not in SCENARIO_COUNTS):
            raise ValueError("Escenario no reconocido.")
        junctions = [Junction(index, self.mode) for index in range(9)]
        if scenario == "manual":
            if type(manual_count) is not int or not 0 <= manual_count <= MANUAL_MAX:
                raise ValueError(f"Ingresa un número entero de 0 a {MANUAL_MAX} vehículos.")
            for number in range(manual_count):
                slot, approach = divmod(number, 8)
                lane, heading = divmod(approach, 4)
                turn = 0 if lane else TURNS[(4 + heading + slot) % len(TURNS)]
                junctions[4].spawn(heading, 28 + lane * 3 + slot * 13, turn, lane)
            expected_count = manual_count
        else:
            expected_count = SCENARIO_COUNTS[scenario]
            manual_count = None
        if scenario not in ("empty", "manual"):
            peak = scenario != "normal"
            for index, junction in enumerate(junctions):
                for heading in range(4):
                    primary = heading % 2 == (1 if scenario == "peak_ew" else 0)
                    quantity = (6 if primary else 4) if peak else 1
                    if scenario == "moderate":
                        quantity = 2 + (heading % 2 == index % 2)
                    for slot in range(quantity):
                        distance = 28 + slot * 13 if peak else 36
                        junction.spawn(heading, distance, TURNS[(index + heading + slot) % len(TURNS)])
                    if scenario == "saturation":
                        for slot in range(quantity - 1):
                            junction.spawn(heading, 31 + slot * 13, 0, lane=1)
        if sum(len(junction.vehicles) for junction in junctions) != expected_count:
            raise RuntimeError("La flota inicial no coincide con la demanda.")
        self.scenario, self.manual_count, self.junctions = scenario, manual_count, junctions
        self.steps, self.transfers = 0, 0
        self.crossing_history = deque([0], maxlen=60 * TICKS_PER_SECOND + 1)

    def set_mode(self, mode):
        self.mode = mode
        for junction in self.junctions:
            junction.controller.mode = mode

    def _external_vehicles(self):
        for junction in self.junctions:
            junction.external.clear()
        for index, junction in enumerate(self.junctions):
            for target, dx, dz in self.neighbors[index]:
                local = self.junctions[target].external
                for car in junction.vehicles:
                    x, z = car.x + dx, car.z + dz
                    if abs(x) < 195 and abs(z) < 195:
                        local.append(Neighbor(x, z, car.yaw, car.half_length, car.half_width, car.fx, car.fz,
                                              car.id, car.heading, car.lane, car.planned_turn, car.speed))

    def tick(self):
        self.steps += 1
        manual = self.manual_count is not None
        if not manual:
            self._external_vehicles()
        departed = []
        for index, junction in enumerate(self.junctions):
            if junction.priority_until and self.time >= junction.priority_until:
                junction.priority_until = 0
                junction.controller.priority = ""
            departed.extend((index, car) for car in junction.step(STEP, hold_boundary=manual))
        for index, car in departed:
            arrived = self._reenter(car) if manual else self._transfer(index, car)
            if not arrived:
                car.speed = 0
                self.junctions[index].vehicles.append(car)
        self.crossing_history.append(sum(junction.crossings for junction in self.junctions))

    def _transfer(self, index, car):
        fx, fz = FORWARD[car.heading]
        row, column = index // 3 + fz, index % 3 + fx
        target = row % 3 * 3 + column % 3
        destination = self.junctions[target]
        if not (0 <= row < 3 and 0 <= column < 3):
            pose = straight_pose(destination.central, car.heading, -104.8, car.lane)
        else:
            x, z = self.centers[index]
            tx, tz = self.centers[target]
            pose = car.x + x - tx, car.z + z - tz, car.yaw
        return self._arrive(destination, car, pose, car.heading, car.lane)

    def _reenter(self, car):
        # Conserva la flota en I-5. Prueba primero el mismo carril por el
        # extremo opuesto y, si está ocupado, otras entradas disponibles.
        for offset in range(4):
            heading = (car.heading + offset) % 4
            for lane in (car.lane, 1 - car.lane):
                pose = straight_pose(True, heading, -104.8, lane)
                if self._arrive(self.central, car, pose, heading, lane):
                    return True
        return False

    def _arrive(self, destination, car, pose, heading, lane):
        candidate = Body(*pose, car.half_length, car.half_width, sin(pose[2]), cos(pose[2]))
        if any(overlap(candidate, other, 2.0 if lane == other.lane else .25)
               for other in destination.vehicles):
            return False
        car.set_pose(pose)
        car.heading, car.lane = heading, lane
        car.cleared = car.committed = False
        car.path = None
        car.hops += 1
        car.planned_turn = 0 if car.lane == 1 else TURNS[(car.id + car.hops) % len(TURNS)]
        destination.vehicles.append(car)
        self.transfers += 1
        return True

    def metrics(self):
        vehicles = [car for junction in self.junctions for car in junction.vehicles]
        size = len(vehicles)
        return {"vehicles": size, "queued": sum(car.speed < QUEUE_SPEED for car in vehicles),
                "crossings": sum(junction.crossings for junction in self.junctions),
                "transfers": self.transfers, "turns": sum(junction.turns for junction in self.junctions),
                "blocked_moves": sum(junction.blocked for junction in self.junctions),
                "speed_kmh": 3.6 * sum(car.speed for car in vehicles) / max(1, size),
                "mean_wait": sum(car.waiting for car in vehicles) / max(1, size)}

    def planning(self):
        nodes = []
        for index, junction in enumerate(self.junctions):
            row, column = divmod(index, 3)
            targets = ((row + 1) % 3 * 3 + column, row * 3 + (column - 1) % 3,
                       (row - 1) % 3 * 3 + column, row * 3 + (column + 1) % 3)
            controller = junction.controller
            nodes.append({"id": index + 1, "counts": controller.counts, "queues": controller.queues,
                          "wait": controller.wait, "previous_axis": controller.last_axis,
                          "sensors_online": junction.sensor_enabled, "fallback": controller.fallback,
                          "downstream_queues": [self.junctions[target].controller.queues[i]
                                                for i, target in enumerate(targets)]})
        return {"junctions": nodes}
