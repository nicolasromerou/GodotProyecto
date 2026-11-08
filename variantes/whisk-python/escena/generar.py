"""Genera los nodos Whisk3D y las señales alrededor del barrio exportado."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
APPROACHES = {
    "N": (-11.7, -20, 0),
    "E": (20, -8.1, -90),
    "S": (8.1, 20, 180),
    "W": (-20, 8.1, 90),
}


def signal():
    # En el formato legado de Whisk el campo z representa la altura.
    nodes = []
    for key, (x, z, yaw) in APPROACHES.items():
        nodes.append(f'        Wavefront {{ name: "Poste{key}" filePath: poste.obj x: {x} y: {z} z: 0 rz: {yaw} }}')
        for color, height in (("Rojo", 4.3), ("Amarillo", 3.85), ("Verde", 3.4)):
            nodes.append(f'        Wavefront {{ name: "{key}{color}" filePath: foco.obj x: {x} y: {z} z: {height} }}')
    return nodes


def boxes(name, color, shapes):
    vertices = []
    faces = []
    for (x, y, z), (width, height, depth) in shapes:
        start = len(vertices) + 1
        vertices.extend(
            (x + dx * width / 2, y + dy * height / 2, z + dz * depth / 2)
            for dx, dy, dz in ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                               (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1))
        )
        faces.extend(tuple(start + i for i in face) for face in
                     ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                      (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)))
    lines = [f"mtllib {name}.mtl", f"o {name}", *("v %.4f %.4f %.4f" % v for v in vertices),
             f"usemtl {name}", *("f %d %d %d %d" % f for f in faces)]
    (HERE / f"{name}.obj").write_text("\n".join(lines) + "\n", encoding="ascii")
    (HERE / f"{name}.mtl").write_text(f"newmtl {name}\nKa {color}\nKd {color}\nNoLight\n", encoding="ascii")


def main():
    boxes("poste", "0.14 0.16 0.18", [((0, 1.65, 0), (.20, 3.3, .20)), ((0, 3.85, 0), (.57, 1.52, .57))])
    boxes("foco", "1.0 1.0 1.0", [((0, 0, 0), (.39, .35, .64)), ((0, 0, 0), (.64, .35, .39))])
    nodes = ['        Wavefront { name: "Barrio" filePath: barrio.obj script: "control.lua" noEditable: true }']
    nodes.extend(signal())
    fleet = json.loads((HERE.parent / "flota.json").read_text(encoding="utf-8"))
    nodes.append("        Biblioteca {")
    for item in fleet:
        model = item["key"]
        nodes.append(f'            Prefab {{ name: "fti_{model}" '
                     f'Wavefront {{ filePath: {model}.obj visible: false estatico: false noEditable: true }} }}')
    nodes.append("        }")
    for item in fleet:
        model = item["key"]
        nodes.append(f'        Clon {{ prefab: "fti_{model}" name: "fti_base_{model}" }}')
    scene = """Whisk3D {
    version: 20251127
    Escena {
        limpiarPantalla: true
        background: "0.54, 0.71, 0.80, 1.0"
        Camera { name: "Camara" target: "Barrio" x: 58 y: 69 z: 104 fov: 55 near: 3 far: 400 }
        Light { name: "Sol" x: 20 y: -35 z: 75 r: 1 g: 1 b: 1 }
%s
    }
    Layout {
        ViewportRow {
            Viewport3D { orthographic: false ViewFromCameraActive: true showOverlays: false showFloor: false view: MaterialPreview nearClip: 2 farClip: 400 }
        }
    }
}
""" % "\n".join(nodes)
    (HERE / "FTI_Cruce_I5.w3d").write_text(scene, encoding="ascii")


if __name__ == "__main__":
    main()
