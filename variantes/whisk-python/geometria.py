"""Geometría compartida por la simulación de carriles, curvas y colisiones."""
from bisect import bisect_left
from dataclasses import dataclass
from functools import lru_cache
from math import atan2, cos, hypot, isfinite, pi, sin, sqrt

FORWARD = ((0, 1), (1, 0), (0, -1), (-1, 0))
YAW = (0.0, pi / 2, pi, -pi / 2)
STOP_LINE = 20.0
TURN_ENTRY = 21.5
LANE_WIDTH = 3.5


def _smooth(value):
    t = min(1.0, max(0.0, value))
    return t * t * t * (10 + t * (-15 + 6 * t))


def lane_offset(central, heading, longitudinal, lane):
    offset = 1.75 + LANE_WIDTH * lane
    if not central or heading % 2:
        return offset
    z = FORWARD[heading][1] * longitudinal
    if z < -65:
        return offset + 3.5 * _smooth((105 + z) / 40)
    if z <= -TURN_ENTRY:
        return offset + 3.5
    return offset + 3.5 * (1 - _smooth((z + TURN_ENTRY) / (2 * TURN_ENTRY)))


def straight_pose(central, heading, longitudinal, lane):
    fx, fz = FORWARD[heading]
    offset = lane_offset(central, heading, longitudinal, lane)
    yaw = YAW[heading]
    if central and not heading % 2:
        change = lane_offset(central, heading, longitudinal + .001, lane) - lane_offset(
            central, heading, longitudinal - .001, lane)
        yaw = atan2(-fz * change, fz * .002)
    return fx * longitudinal - fz * offset, fz * longitudinal + fx * offset, yaw


def follow_speed(speed, desired, gap, leader_speed, dt):
    target = desired
    if isfinite(gap):
        target = min(target, max(0.0, sqrt(leader_speed ** 2 + 14 * max(0.0, gap - 1.4) + 39.69) - 6.3))
        target = min(target, max(0.0, (gap - 1.4) / 1.2 + leader_speed * .35))
    acceleration = min(3.0, max(-7.0, (target - speed) * 1.8))
    next_speed = max(0.0, speed + acceleration * dt)
    distance = (speed + next_speed) * .5 * dt
    if isfinite(gap) and distance > max(0.0, gap - .2):
        distance = max(0.0, gap - .2)
        next_speed = min(next_speed, distance / dt)
    return next_speed, distance


@dataclass(slots=True)
class Body:
    x: float
    z: float
    yaw: float
    half_length: float
    half_width: float
    fx: float
    fz: float

    @classmethod
    def box(cls, x, z, yaw, length, width):
        return cls(x, z, yaw, length * .5, width * .5, sin(yaw), cos(yaw))


def overlap(a, b, margin=0.0):
    """Prueba los cuatro ejes separadores de dos rectángulos orientados."""
    dx, dz = b.x - a.x, b.z - a.z
    bound = a.half_length + a.half_width + b.half_length + b.half_width + margin
    if abs(dx) > bound or abs(dz) > bound or dx * dx + dz * dz > bound * bound:
        return False
    parallel = abs(a.fx * b.fx + a.fz * b.fz)
    cross = abs(a.fz * b.fx - a.fx * b.fz)
    clearance = margin - 1e-8
    return (
        abs(dx * a.fx + dz * a.fz) < a.half_length + b.half_length * parallel + b.half_width * cross + clearance
        and abs(dx * a.fz - dz * a.fx) < a.half_width + b.half_length * cross + b.half_width * parallel + clearance
        and abs(dx * b.fx + dz * b.fz) < b.half_length + a.half_length * parallel + a.half_width * cross + clearance
        and abs(dx * b.fz - dz * b.fx) < b.half_width + a.half_length * cross + a.half_width * parallel + clearance
    )


def _cubic(points, t):
    u = 1 - t
    ax, az, bx, bz, cx, cz, dx, dz = points
    x = ax * u ** 3 + bx * 3 * u * u * t + cx * 3 * u * t * t + dx * t ** 3
    z = az * u ** 3 + bz * 3 * u * u * t + cz * 3 * u * t * t + dz * t ** 3
    vx = (bx - ax) * u * u + (cx - bx) * 2 * u * t + (dx - cx) * t * t
    vz = (bz - az) * u * u + (cz - bz) * 2 * u * t + (dz - cz) * t * t
    return x, z, atan2(vx, vz)


@dataclass(frozen=True, slots=True)
class Route:
    points: tuple
    lengths: tuple
    heading: int

    @property
    def length(self):
        return self.lengths[-1]

    def pose(self, distance):
        index = max(1, bisect_left(self.lengths, distance))
        low, high = self.lengths[index - 1:index + 1]
        return _cubic(self.points, (index - 1 + (distance - low) / (high - low)) / 80)


@lru_cache(maxsize=None)
def route(central, heading, turn, lane):
    target = (heading - turn) % 4
    ax, az, _ = straight_pose(central, heading, -TURN_ENTRY, lane)
    dx, dz, _ = straight_pose(central, target, TURN_ENTRY, lane)
    fx, fz = FORWARD[heading]
    gx, gz = FORWARD[target]
    offset = (lane_offset(central, heading, -TURN_ENTRY, lane) + lane_offset(central, target, TURN_ENTRY, lane)) / 2
    radius = TURN_ENTRY - offset if turn == 1 else TURN_ENTRY + offset
    k = .55228475 * radius if turn else TURN_ENTRY * 2 / 3
    points = (ax, az, ax + fx * k, az + fz * k, dx - gx * k, dz - gz * k, dx, dz)
    lengths = [0.0]
    x, z = ax, az
    for index in range(1, 81):
        next_x, next_z, _ = _cubic(points, index / 80)
        lengths.append(lengths[-1] + hypot(next_x - x, next_z - z))
        x, z = next_x, next_z
    return Route(points, tuple(lengths), target)
