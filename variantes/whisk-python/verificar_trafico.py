"""Ensayo reproducible de circulación sin abrir el visor."""
import argparse
from math import hypot
import time

from geometria import STOP_LINE, Body, overlap, straight_pose
from semaforos import Controller, MODES
from simulacion import Simulation
from trafico import MANUAL_MAX, SCENARIO_COUNTS, STEP, TICKS_PER_SECOND, WORLD_LIMIT, TrafficNetwork


def verify_priority():
    controller = Controller("adaptive")
    controller.priority = "NS"
    for _ in range(1440):
        controller.sense([18, 3, 18, 3])
        controller.step(STEP)
        if controller.light("E") == "GREEN":
            return
    raise AssertionError("Una prioridad persistente bloqueó el eje secundario.")


def verify_phases_and_metrics():
    controller = Controller("adaptive")
    controller.sense([4, 1, 4, 1], [4, 0, 4, 0])
    controller.wait[1] = 31.0
    controller.step(controller.clearance)
    assert controller.light("E") == "GREEN", "Se ignoró el eje con demanda y espera prolongada."

    controller = Controller("adaptive")
    controller.sense([4, 0, 4, 0])
    controller.step(controller.clearance)
    for _ in range(4 * TICKS_PER_SECOND + 1):
        controller.sense([4, 0, 4, 0])
        controller.step(STEP)
    assert controller.stage == "GREEN"
    assert controller.request_pedestrian()
    controller.step(STEP)
    assert controller.stage == "YELLOW", "La solicitud peatonal esperó todo el turno verde."
    for _ in range(4 * TICKS_PER_SECOND):
        controller.step(STEP, occupied=True)
    assert controller.stage == "ALL_RED" and controller.pedestrian_pending
    controller.step(STEP, occupied=False)
    assert controller.stage == "WALK"
    assert all(controller.light(side) == "RED" for side in "NESW")

    junction = TrafficNetwork("empty").central
    junction.spawn(0, 28, 0)
    car = junction.vehicles[0]
    car.set_pose(straight_pose(True, 0, -(STOP_LINE + car.half_length + .5), 0))
    junction.controller.stage, junction.controller.active = "YELLOW", ["N"]
    junction.step(STEP)
    assert car.speed == 0, "Un auto detenido inició la marcha en amarillo."

    network = TrafficNetwork("empty")
    network.central.crossings += 1
    network.tick()
    assert network.recent_crossings == 1, "El cruce no apareció en el mismo paso."
    for _ in range(60 * TICKS_PER_SECOND - 1):
        network.tick()
    assert network.recent_crossings == 1
    network.tick()
    assert network.recent_crossings == 0, "El cruce persistió fuera de la ventana de 60 s."


def verify_frame(network, previous=None):
    poses, positions = [], {}
    for (x, z), junction in zip(network.centers, network.junctions):
        controller = junction.controller
        ns = any(controller.light(side) == "GREEN" for side in "NS")
        ew = any(controller.light(side) == "GREEN" for side in "EW")
        if ns and ew:
            raise AssertionError(f"Verdes incompatibles en t={network.time:.3f}")
        if controller.stage == "WALK" and any(controller.light(side) != "RED" for side in "NESW"):
            raise AssertionError(f"Semáforo vehicular abierto durante el paso peatonal en t={network.time:.3f}")
        for car in junction.vehicles:
            if car.id in positions:
                raise AssertionError(f"Vehículo duplicado: {car.id}")
            wx, wz = car.x + x, car.z + z
            positions[car.id] = wx, wz
            poses.append((Body(wx, wz, car.yaw, car.half_length, car.half_width, car.fx, car.fz), car.id))
            if previous is not None:
                old_x, old_z = previous[car.id]
                dx, dz = wx - old_x, wz - old_z
                distance = hypot(dx, dz)
                # Un reingreso por el borde se comprueba como una aparición.
                if .001 < distance < 3 and dx * car.fx + dz * car.fz < .95 * distance:
                    raise AssertionError(f"Rumbo contrario al movimiento del vehículo {car.id} en t={network.time:.3f}")
            if car.lane == 1 and car.planned_turn:
                raise AssertionError(f"Giro en el carril exterior: {car.id}")
    expected = SCENARIO_COUNTS[network.scenario] if network.manual_count is None else network.manual_count
    if len(positions) != expected:
        raise AssertionError("Cambió la cantidad de vehículos en la red.")
    poses.sort(key=lambda item: item[0].x)
    for index, (a, first) in enumerate(poses):
        for next_index in range(index + 1, len(poses)):
            b, second = poses[next_index]
            if b.x - a.x > 12:
                break
            if abs(b.z - a.z) < 12 and overlap(a, b):
                raise AssertionError(f"Solapamiento {first}/{second} en t={network.time:.3f}")
    return positions


def verify_load(scenario, mode):
    network = TrafficNetwork(scenario)
    network.set_mode(mode)
    network.load(scenario)
    max_central = midpoint = 0
    previous = verify_frame(network)
    start = time.perf_counter()
    for step in range(1, 3601):
        network.tick()
        if step == 1800:
            midpoint = network.metrics()["crossings"]
        if step % 5 == 0:
            previous = verify_frame(network, previous)
            max_central = max(max_central, len(network.central.vehicles))
    metrics = network.metrics()
    second_minute = metrics["crossings"] - midpoint
    minimum = 125 if scenario == "saturation" and mode == "adaptive" else 40 if scenario == "normal" else 60
    minimum_transfers = 80 if scenario == "normal" else 100
    if second_minute < minimum or metrics["transfers"] < minimum_transfers:
        raise AssertionError(f"Flujo insuficiente: {metrics}")
    print(f"TRAFICO_OK {scenario} {mode}: {metrics['vehicles']} vehículos, {metrics['crossings']} cruces, "
          f"{metrics['transfers']} transferencias, {second_minute} cruces en el segundo minuto, "
          f"máximo I-5 {max_central}, {time.perf_counter() - start:.2f} s de cómputo con verificaciones.")


def verify_manual(count, mode):
    simulation = Simulation("normal", paused=True)
    simulation.control("mode", mode)
    simulation.control("manual_count", count)
    simulation.control("reset")
    network = simulation.network
    state = simulation.snapshot(0, "")
    assert state["scenario"] == "manual" and state["manual_count"] == count
    ids = {car.id for car in network.central.vehicles}
    assert len(ids) == count
    previous = verify_frame(network)
    midpoint = 0
    for step in range(1, 7201):
        network.tick()
        if step == 3600:
            midpoint = network.central.crossings
        if step % 5 == 0:
            previous = verify_frame(network, previous)
            assert {car.id for car in network.central.vehicles} == ids
            assert all(abs(car.x) < WORLD_LIMIT + 1 and abs(car.z) < WORLD_LIMIT + 1
                       for car in network.central.vehicles)
    metrics = network.metrics()
    if count:
        assert metrics["crossings"] > midpoint and metrics["transfers"] > 0, metrics
    print(f"MANUAL_OK {mode}: {count} vehículos en I-5 durante 240 s, "
          f"{metrics['crossings']} cruces, {metrics['transfers']} reincorporaciones.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=("normal", "moderate", "peak_ns", "peak_ew", "saturation", "manual"))
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("--autos", type=int, help=f"Cantidad para manual, entre 0 y {MANUAL_MAX}")
    args = parser.parse_args()
    verify_priority()
    verify_phases_and_metrics()
    if args.scenario == "manual":
        if args.autos is None or not 0 <= args.autos <= MANUAL_MAX:
            parser.error(f"El modo manual requiere --autos con un entero de 0 a {MANUAL_MAX}.")
        verify_manual(args.autos, args.mode)
    else:
        if args.autos is not None:
            parser.error("--autos requiere el escenario manual.")
        verify_load(args.scenario, args.mode)
