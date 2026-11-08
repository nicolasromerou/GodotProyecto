"""Audita las mallas, los materiales y la orientación de la flota."""
from collections import Counter
import json
from math import isfinite
from pathlib import Path

from escena.convertir_flota import CLEARANCE, DECAL_DEPTH, components, is_wheel, original

ROOT = Path(__file__).resolve().parent
SCENE = ROOT / "escena"


def inspect(model):
    key = model["key"]
    points, triangles, height = original(model)
    expected = Counter(triangles)
    wheels = {tuple(sorted(face)): bounds for face, bounds in zip(triangles, components(points, triangles))
              if model["front_x"] < 0 and is_wheel(key, bounds)}
    vertices, uvs, normals = [], [], []
    base, materials = Counter(), Counter()
    marks = {"faro": [], "piloto": []}
    material = ""
    for row in (SCENE / f"{key}.obj").read_text(encoding="ascii").splitlines():
        kind, *fields = row.split()
        if kind in ("v", "vt", "vn"):
            values = tuple(map(float, fields))
            assert all(map(isfinite, values)), key
            if kind == "v":
                vertices.append(values)
            elif kind == "vt":
                assert len(values) == 2 and all(0 <= v <= 1 for v in values), key
                uvs.append(values)
            else:
                assert abs(sum(v * v for v in values) - 1) < .001, key
                normals.append(values)
        elif kind == "usemtl":
            material = fields[0].removeprefix(key + "_")
        elif kind == "f":
            face = [part.split("/") for part in fields]
            assert len(face) == 3 and material
            indices = tuple(int(v) - 1 for v, _, _ in face)
            assert all(0 <= v < len(vertices) and 0 < int(n) <= len(normals)
                       for v, (_, _, n) in zip(indices, face)), key
            materials[material] += 1
            if max(indices) < len(points):
                assert material != "cristal", key
                if material == "cubierta":
                    low, high = wheels[tuple(sorted(indices))]
                    center = sum(points[i][0] for i in indices) / 3
                    side = center - (low[0] + high[0]) / 2
                    assert all(normals[int(n) - 1][0] * side > 0 for _, _, n in face), key
                    assert all(0 < int(t) <= len(uvs) for _, t, _ in face), key
                    if not expected[indices]:
                        indices = indices[0], indices[2], indices[1]
                base[indices] += 1
            else:
                assert min(indices) >= len(points), key
                assert all(0 < int(t) <= len(uvs) for _, t, _ in face), key
                if material in marks:
                    marks[material].extend(vertices[i][2] for i in indices)

    assert base == expected, f"{key}: la malla STL cambió de topología"
    for (x, y, z), (mx, my, mz) in zip(points, vertices):
        assert abs(mx - (x - .5) * model["width"]) <= 1e-6, key
        assert abs(my - (CLEARANCE + y * height)) <= 1e-6, key
        assert abs(mz - (z - .5) * model["length"]) <= 1e-6, key
    assert all(abs(x) <= model["width"] / 2 + DECAL_DEPTH + .001
               and abs(z) <= model["length"] / 2 + DECAL_DEPTH + .001
               and CLEARANCE - .001 <= y <= CLEARANCE + height + .001
               for x, y, z in vertices), f"{key}: detalle fuera de la malla"

    required = {"carroceria", "goma", "faro", "piloto",
                "cubierta" if model["front_x"] < 0 else "llanta"}
    if key != "moto":
        required.add("cristal")
    assert required <= materials.keys(), (key, required - materials.keys())
    assert marks["faro"] and min(marks["faro"]) > model["length"] * .32, key
    assert marks["piloto"] and max(marks["piloto"]) < -model["length"] * .32, key
    definitions = (SCENE / f"{key}.mtl").read_text(encoding="ascii").splitlines()
    assert set(line.removeprefix(f"newmtl {key}_") for line in definitions if line.startswith("newmtl ")) == materials.keys(), key
    if key != "moto":
        assert "map_Kd vidrio.png" in definitions, key
    if model["front_x"] < 0:
        assert "map_Kd llanta.png" in definitions, key
    assert sum(materials.values()) - len(triangles) <= 1100, f"{key}: presupuesto de detalle"
    print(f"{key}: {len(triangles)} caras STL, {len(materials)} materiales, morro +Z")


def main():
    for asset in ("vidrio.png", "llanta.png"):
        assert (SCENE / asset).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    fleet = json.loads((ROOT / "flota.json").read_text(encoding="utf-8"))
    keys = {model["key"] for model in fleet}
    assert len(keys) == len(fleet) == 11
    for model in fleet:
        inspect(model)
    print("FLOTA_OK: 11 mallas, topología original, UV, neumáticos, llantas y luces orientadas.")


if __name__ == "__main__":
    main()
