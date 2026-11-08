"""Convierte los STL originales a mallas +Z con materiales de carretera."""
from collections import defaultdict
import json
import math
from pathlib import Path
import struct
import zlib

SCENE = Path(__file__).resolve().parent
PACKAGE = SCENE.parent
CLEARANCE = .055
DECAL_DEPTH = .009

# Franjas de cristal lateral (extremos de Z y altura), en proporciones del STL.
WINDOWS = {
    "suv": (.22, .70, .63, .83, 2),
    "pickup": (.38, .68, .60, .79, 1),
    "bus": (.08, .95, .54, .78, 5),
    "camaro": (.36, .67, .71, .88, 2),
    "interceptor": (.36, .67, .68, .84, 2),
    "cyber": (.38, .73, .65, .85, 2),
    "supercar": (.39, .68, .70, .87, 2),
    "furgon": (.65, .83, .55, .72, 1),
    "metrobus": (.08, .95, .53, .77, 5),
    "muscle": (.33, .64, .71, .87, 2),
}
WINDSHIELD = {
    # Franja vertical y profundidad del parabrisas. El límite de profundidad
    # excluye el capó y el scoop del fastback, que se superponen vistos de frente.
    "suv": (.67, .86, .50, .74), "pickup": (.62, .82, .50, .73), "bus": (.50, .78, .89, 1.01),
    "camaro": (.713, .87, .55, .73), "interceptor": (.618, .81, .55, .73), "cyber": (.69, .90, .55, .82),
    "supercar": (.665, .85, .54, .73), "furgon": (.58, .78, .75, .92), "metrobus": (.51, .75, .89, 1.01),
    "muscle": (.69, .85, .55, .75),
}
MATERIALS = {
    "goma": (.08, .09, .10),
    "llanta": (.57, .62, .67),
    "bajos": (.21, .23, .26),
    "cristal": (.42, .54, .62),
    "faro": (.95, .92, .73),
    "piloto": (.68, .09, .12),
    "franja": (.78, .83, .78),
    "azul": (.18, .47, .85),
}


def normal(a, b, c):
    ux, uy, uz = (q - p for p, q in zip(a, b))
    vx, vy, vz = (q - p for p, q in zip(a, c))
    direction = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    magnitude = math.hypot(*direction)
    return tuple(v / magnitude for v in direction) if magnitude else (0., 1., 0.)


def original(model):
    path = PACKAGE / "modelos-originales" / model["stl"]
    data = path.read_bytes()
    if len(data) < 84:
        raise ValueError(f"STL incompleto: {path.name}")
    count, = struct.unpack_from("<I", data, 80)
    if not count or len(data) != 84 + count * 50:
        raise ValueError(f"STL binario inválido: {path.name}")

    front = model["front_x"]
    if front not in (-1, 1):
        raise ValueError(f"Eje frontal inválido: {path.name}")
    indices, triangles = {}, []
    for record in struct.iter_unpack("<12fH", data[84:]):
        # Rotación con determinante +1: mantiene el orden de caras del STL.
        corners = [(front * record[i + 1], record[i + 2], front * record[i]) for i in (3, 6, 9)]
        if not all(math.isfinite(v) for point in corners for v in point):
            raise ValueError(f"Coordenada inválida: {path.name}")
        triangles.append(tuple(indices.setdefault(point, len(indices)) for point in corners))

    limits = [(min(axis), max(axis)) for axis in zip(*indices)]
    (x0, x1), (y0, y1), (z0, z1) = limits
    if not (x1 > x0 and y1 > y0 and z1 > z0):
        raise ValueError(f"Dimensiones inválidas: {path.name}")
    height = (y1 - y0) * model["length"] / (z1 - z0)
    normalized = [((x - x0) / (x1 - x0), (y - y0) / (y1 - y0), (z - z0) / (z1 - z0))
                  for x, y, z in indices]
    return normalized, triangles, height


def components(points, triangles):
    parent = list(range(len(points)))

    def root(index):
        while index != parent[index]:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for a, b, c in triangles:
        first = root(a)
        parent[root(b)] = first
        parent[root(c)] = first
    bounds = {}
    for index, point in enumerate(points):
        key = root(index)
        low, high = bounds.setdefault(key, (list(point), list(point)))
        for axis, value in enumerate(point):
            low[axis] = min(low[axis], value)
            high[axis] = max(high[axis], value)
    return [bounds[root(a)] for a, _, _ in triangles]


def is_wheel(model, bounds):
    low, high = bounds
    motorbike = model == "moto"
    outer = high[0] < .31 or low[0] > .69
    on_axle = low[2] < .31 or high[2] > .68
    wheel = high[1] < (.52 if motorbike else .66) and low[1] < .085 and high[1] - low[1] > .23 and high[2] - low[2] < .32
    return wheel and on_axle and (motorbike or outer)


def surface(model, point, direction, bounds):
    x, y, z = point
    low, high = bounds
    if is_wheel(model, bounds):
        center_y, center_z = (low[1] + high[1]) / 2, (low[2] + high[2]) / 2
        radius = math.hypot((y - center_y) / (high[1] - low[1]), (z - center_z) / (high[2] - low[2]))
        return "llanta" if abs(direction[0]) > .76 and radius < .38 else "goma"
    if model == "moto":
        if .19 < z < .50 and y > .65 and .32 < x < .68:
            return "bajos"
        if y < .32 and .26 < z < .72:
            return "llanta"
    if model == "interceptor" and low[1] > .86:
        return "azul" if x > .5 else "piloto"
    if y < .20 and abs(direction[1]) < .8:
        return "bajos"
    return "carroceria"


class Surface:
    """Proyecta detalles pequeños sobre la superficie original del modelo."""
    def __init__(self, points, faces, axis):
        self.axis = axis
        self.uv_axes = tuple(i for i in range(3) if i != axis)
        u, v = self.uv_axes
        self.triangles = []
        self.cells = defaultdict(list)
        for a, b, c in faces:
            p, q, r = points[a], points[b], points[c]
            ux, uy, vx, vy = q[u] - p[u], q[v] - p[v], r[u] - p[u], r[v] - p[v]
            determinant = ux * vy - uy * vx
            if abs(determinant) > 1e-10:
                limits = (min(p[u], q[u], r[u]), max(p[u], q[u], r[u]),
                          min(p[v], q[v], r[v]), max(p[v], q[v], r[v]))
                self.triangles.append(((p, q, r), limits))
                ray = p[u], p[v], p[axis], ux, uy, vx, vy, 1 / determinant, q[axis] - p[axis], r[axis] - p[axis]
                left, right, bottom, top = (int(32 * bound) for bound in limits)
                for i in range(left, right + 1):
                    for j in range(bottom, top + 1):
                        self.cells[i, j].append(ray)

    def depth(self, u, v, side, allowed):
        outer = None
        for pu, pv, depth, ux, uy, vx, vy, inv, q, r in self.cells.get((int(32 * u), int(32 * v)), ()):
            x, y = u - pu, v - pv
            b, c = (x * vy - y * vx) * inv, (ux * y - uy * x) * inv
            if b >= -1e-7 and c >= -1e-7 and b + c <= 1.0000001:
                candidate = depth + b * q + c * r
                if allowed[0] <= candidate <= allowed[1] and (outer is None or side * candidate > side * outer):
                    outer = candidate
        return outer


def clip(polygon, axis, limit, side):
    """Recorta una cara contra un plano y conserva su posición sobre la malla."""
    clipped = []
    for a, b in zip(polygon[-1:] + polygon[:-1], polygon):
        da, db = side * (a[axis] - limit), side * (b[axis] - limit)
        if (da < 0) != (db < 0):
            t = da / (da - db)
            clipped.append(tuple(x + (y - x) * t for x, y in zip(a, b)))
        if db >= 0:
            clipped.append(b)
    return clipped


def paint(target, material, world, surface, side, rect, allowed):
    """Recorta el detalle a partir de las caras exteriores ya existentes."""
    lo, hi, bottom, top = rect
    axis = surface.axis
    u, v = surface.uv_axes
    decals, area = [], 0.0
    for source, (left, right, down, up) in surface.triangles:
        if right <= lo or left >= hi or up <= bottom or down >= top:
            continue
        polygon = list(source)
        for dim, boundary, sign in ((u, lo, 1), (u, hi, -1), (v, bottom, 1), (v, top, -1),
                                    (axis, allowed[0], 1), (axis, allowed[1], -1)):
            polygon = clip(polygon, dim, boundary, sign)
        if len(polygon) < 3:
            continue
        midpoint = tuple(sum(point[i] for point in polygon) / len(polygon) for i in range(3))
        depth = surface.depth(midpoint[u], midpoint[v], side, allowed)
        if depth is None or abs(depth - midpoint[axis]) > .003:
            continue
        corners = []
        for point in polygon:
            coords = list(world(point))
            coords[axis] += side * DECAL_DEPTH
            corners.append((tuple(coords), ((point[u] - lo) / (hi - lo), (point[v] - bottom) / (top - bottom))))
        for i in range(1, len(polygon) - 1):
            a, b, c = polygon[0], polygon[i], polygon[i + 1]
            projected = abs((b[u] - a[u]) * (c[v] - a[v]) - (c[u] - a[u]) * (b[v] - a[v])) / 2
            if projected <= 1e-9:
                continue
            face = corners[0], corners[i], corners[i + 1]
            if normal(*(point for point, _ in face))[axis] * side < 0:
                face = face[0], face[2], face[1]
            decals.append(face)
            area += projected
    if area < (hi - lo) * (top - bottom) * .45:
        return False
    target[material].extend(decals)
    return True


def details(target, model, points, faces, world):
    key = model["key"]
    ends = Surface(points, faces, 2)
    pairs = ((.48, .085),) if key == "moto" else ((.25, .105), (.75, .105))
    for side, material, allowed in ((1, "faro", (.86, 1.01)), (-1, "piloto", (-.01, .15))):
        for center, half in pairs:
            for y in ((.73, .66, .58) if key == "moto" else (.44, .36, .52, .27, .22)):
                if paint(target, material, world, ends, side, (center-half, center+half, y-.037, y+.037), allowed):
                    break

    if key == "moto":
        return
    sides = Surface(points, faces, 0)
    rear, front, bottom, top, count = WINDOWS[key]
    for side, allowed in ((-1, (-.01, .42)), (1, (.58, 1.01))):
        for i in range(count):
            spacing = (front - rear) / count
            z = rear + i * spacing
            paint(target, "cristal", world, sides, side,
                  (bottom, top, z + spacing * .08, z + spacing * .92), allowed)
        if key in ("bus", "metrobus", "furgon"):
            band = .49 if key == "furgon" else .43
            paint(target, "franja", world, sides, side, (band, band + .045, .10, .91), allowed)
    bottom, top, near, far = WINDSHIELD[key]
    paint(target, "cristal", world, ends, 1, (.23, .77, bottom, top), (near, far))
    if key in ("bus", "metrobus"):
        paint(target, "cristal", world, ends, -1, (.24, .76, bottom, top), (-.01, .29))


def texture(size, pixel):
    pixels = bytearray()
    for y in range(size):
        pixels.append(0)
        for x in range(size):
            pixels.extend(pixel(x, y))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(pixels, 9)) + chunk(b"IEND", b"")


def glass_pixel(x, y):
    light = round(24 * (1 - y / 31))
    reflection = max(0, 8 - abs(x - y - 6)) * 2
    return 26 + light + reflection, 43 + light + reflection, 55 + light + reflection


def wheel_pixel(x, y):
    dx, dy = (x - 31.5) / 31.5, (y - 31.5) / 31.5
    radius = math.hypot(dx, dy)
    angle = math.atan2(dy, dx)
    if radius < .14 or .53 < radius < .61:
        value = 132
    elif radius < .55:
        value = 111 if abs(math.sin(angle * 2.5)) < .24 else 46
    elif .72 < radius < .77 or .89 < radius < .92:
        value = 45
    else:
        value = 29
    shade = round(max(-7, min(7, -dy * 12)))
    return value + shade, value + shade + 3, value + shade + 6


def convert(model):
    points, faces, height = original(model)
    key = model["key"]

    def world(point):
        x, y, z = point
        return (x - .5) * model["width"], CLEARANCE + y * height, (z - .5) * model["length"]

    vertices = [world(point) for point in points]
    groups = defaultdict(list)
    uvs, detail_vertices = {}, {}

    def uv_index(uv):
        value = tuple(round(v, 5) for v in uv)
        return uvs.setdefault(value, len(uvs))

    for face, bounds in zip(faces, components(points, faces)):
        low, high = bounds
        xyz = [points[i] for i in face]
        midpoint = tuple(sum(p[axis] for p in xyz) / 3 for axis in range(3))
        direction = normal(*(vertices[i] for i in face))
        if model["front_x"] < 0 and is_wheel(key, bounds) and abs(direction[0]) > .98:
            # Los STL low-poly traen las tapas de la rueda con las caras hacia
            # dentro. Corrige el winding sin mover ningún vértice de la rueda.
            side = midpoint[0] - (low[0] + high[0]) / 2
            if direction[0] * side < 0:
                face = face[0], face[2], face[1]
                direction = tuple(-v for v in direction)
            uv = tuple(uv_index(((points[i][2] - low[2]) / (high[2] - low[2]),
                                 (points[i][1] - low[1]) / (high[1] - low[1]))) for i in face)
            groups["cubierta"].append((face, direction, uv))
            continue
        material = surface(key, midpoint, direction, bounds)
        groups[material].append((face, direction, ()))

    decals = defaultdict(list)
    details(decals, model, points, faces, world)
    for material, triangles in decals.items():
        for corners in triangles:
            face = []
            for point, _ in corners:
                value = tuple(round(v, 7) for v in point)
                if value not in detail_vertices:
                    detail_vertices[value] = len(vertices)
                    vertices.append(value)
                face.append(detail_vertices[value])
            uv = tuple(uv_index(tex) for _, tex in corners)
            groups[material].append((face, normal(*(p for p, _ in corners)), uv))

    normals = {}
    for records in groups.values():
        for _, direction, _ in records:
            value = tuple(round(v, 6) for v in direction)
            normals.setdefault(value, len(normals) + 1)
    with (SCENE / f"{key}.obj").open("w", encoding="ascii", newline="\n") as out:
        out.write(f"mtllib {key}.mtl\no {key}\n")
        for vertex in vertices:
            out.write("v %.7f %.7f %.7f\n" % vertex)
        for u, v in uvs:
            out.write(f"vt {u:.5f} {v:.5f}\n")
        for direction in normals:
            out.write("vn %.6f %.6f %.6f\n" % direction)
        for material, records in groups.items():
            out.write(f"usemtl {key}_{material}\n")
            for face, direction, uv in records:
                index = normals[tuple(round(v, 6) for v in direction)]
                tex = [str(i + 1) for i in uv] if uv else [""] * 3
                out.write("f " + " ".join(f"{i + 1}/{t}/{index}" for i, t in zip(face, tex)) + "\n")

    with (SCENE / f"{key}.mtl").open("w", encoding="ascii", newline="\n") as out:
        for material in groups:
            rgb = (1, 1, 1) if material == "cubierta" else model["color"] if material == "carroceria" else MATERIALS[material]
            color = " ".join(f"{c:.3f}" for c in rgb)
            shine = "0.03 0.03 0.03" if material == "cristal" else "0.15 0.15 0.15"
            out.write(f"newmtl {key}_{material}\nKa {color}\nKd {color}\nKs {shine}\nNs 22\n")
            if material == "cristal":
                out.write("map_Kd vidrio.png\n")
            elif material == "cubierta":
                out.write("map_Kd llanta.png\n")
            elif material in ("faro", "piloto", "azul"):
                out.write("NoLight\n")
    print(f"{key}: {len(faces)} caras originales, {sum(map(len, decals.values()))} detalles, "
          f"{', '.join(groups)}")


if __name__ == "__main__":
    (SCENE / "vidrio.png").write_bytes(texture(32, glass_pixel))
    (SCENE / "llanta.png").write_bytes(texture(64, wheel_pixel))
    for model in json.loads((PACKAGE / "flota.json").read_text(encoding="utf-8")):
        convert(model)
