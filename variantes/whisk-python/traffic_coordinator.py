#!/usr/bin/env python3
"""Planificador local y determinista de prioridades semafóricas."""
from __future__ import annotations

import argparse
import json
import math
from typing import Any

APPROACHES = {"NS": (0, 2), "EW": (1, 3)}


def _readings(value: Any, name: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(f"{name} debe contener cuatro lecturas")
    readings: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"{name} solo admite números")
        number = float(item)
        if not math.isfinite(number) or number < 0:
            raise ValueError(f"{name} debe contener números finitos no negativos")
        readings.append(number)
    return readings


def plan(payload: dict[str, Any]) -> dict[str, Any]:
    """Choose one compatible axis per sensor-healthy junction."""
    if not isinstance(payload, dict):
        raise ValueError("La entrada debe ser un objeto JSON")
    junctions = payload.get("junctions")
    if not isinstance(junctions, list) or len(junctions) != 9:
        raise ValueError("Se requieren exactamente nueve cruces")
    decisions: list[dict[str, Any]] = []
    seen: set[int] = set()
    for junction in junctions:
        if not isinstance(junction, dict):
            raise ValueError("Cada cruce debe ser un objeto")
        junction_id = junction.get("id")
        if isinstance(junction_id, bool) or not isinstance(junction_id, int) or not 1 <= junction_id <= 9:
            raise ValueError("Identificador de cruce fuera de rango")
        if junction_id in seen:
            raise ValueError("Identificador de cruce duplicado")
        seen.add(junction_id)
        counts = _readings(junction.get("counts"), "counts")
        queues = _readings(junction.get("queues"), "queues")
        waits = _readings(junction.get("wait"), "wait")
        downstream = _readings(junction.get("downstream_queues", [0, 0, 0, 0]), "downstream_queues")
        previous = junction.get("previous_axis", "")
        if previous not in ("", "NS", "EW"):
            raise ValueError("previous_axis debe ser NS, EW o vacío")
        if not isinstance(junction.get("sensors_online"), bool) or not isinstance(junction.get("fallback"), bool):
            raise ValueError("El estado de sensores debe ser booleano")
        if not junction["sensors_online"] or junction["fallback"]:
            decisions.append({"id": junction_id, "priority": "", "reason": "sensores fuera de servicio"})
            continue

        scores: dict[str, float] = {}
        for axis, approaches in APPROACHES.items():
            score = sum(
                2.0 * counts[index]
                + 4.0 * queues[index]
                + 0.15 * waits[index]
                - 2.0 * downstream[index]
                for index in approaches
            )
            scores[axis] = max(0.0, score)
        best = max(scores, key=scores.get)
        if previous in scores and scores[previous] > 0 and scores[previous] >= scores[best] * 0.9:
            best = previous
        priority = best if scores[best] > 0 else ""
        decisions.append({
            "id": junction_id,
            "priority": priority,
            "reason": "balance de colas, espera y congestión aguas abajo",
            "scores": {axis: round(score, 2) for axis, score in scores.items()},
        })
    if seen != set(range(1, 10)):
        raise ValueError("Faltan cruces de la red")
    return {"decisions": decisions}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", required=True, help="Instantánea resumida de las nueve intersecciones")
    args = parser.parse_args()
    try:
        payload = json.loads(args.input_json)
        if not isinstance(payload, dict):
            raise ValueError("La entrada debe ser un objeto JSON")
        print(json.dumps(plan(payload), separators=(",", ":"), allow_nan=False))
    except (json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
