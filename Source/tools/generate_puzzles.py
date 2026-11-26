"""Sinh bộ puzzle TV2 bằng seed cố định; chạy từ thư mục gốc repo."""

from __future__ import annotations

import json
from pathlib import Path
import random
import sys

SOURCE = Path(__file__).resolve().parents[1]
OUT = SOURCE / "data" / "puzzles"
sys.path.insert(0, str(SOURCE))
from game.board import format_clue_text, iter_coords_row_major


def make_puzzle(puzzle_id: str, size: int, clue_kind: str, expected: str = "SOLVABLE") -> dict:
    coords = iter_coords_row_major(size); names = ["Abel", "Bea", "Clara", "Derek", "Eliza", "Franz", "Grant", "Hannah", "Ivy", "Jon", "Kira", "Liam", "Mona", "Nora", "Oscar", "Pia", "Quinn", "Rita", "Sam", "Tara", "Uma", "Vera", "Walt", "Xena", "Yuri"]
    clues = []
    for i, coord in enumerate(coords):
        if clue_kind == "PARITY": clue = {"type": "PARITY", "parity": "EVEN", "region": {"kind": "EXPLICIT", "cells": [coord]}}
        elif clue_kind == "COMPARE" and i == 0: clue = {"type": "COMPARE", "op": "EQ", "region1": {"kind": "ROW", "value": 1}, "region2": {"kind": "COLUMN", "value": "A"}}
        elif clue_kind == "COMPARE": clue = {"type": "FACT", "target": coord, "status": "INNOCENT"}
        elif clue_kind == "COMPOUND": clue = {"type": "COMPOUND", "op": "OR" if i == 0 else "AND", "subclues": [{"type": "FACT", "target": coord, "status": "INNOCENT"}, {"type": "PARITY", "parity": "EVEN", "region": {"kind": "EXPLICIT", "cells": [coord]}}]}
        elif clue_kind == "CONNECTIVITY" and i == 0: clue = {"type": "CONNECTIVITY", "status": "CRIMINAL", "adjacency": "ORTHOGONAL", "region": {"kind": "EXPLICIT", "cells": [coord]}}
        elif clue_kind == "REGION" and i < 5:
            region = [{"kind": "BOUNDARY"}, {"kind": "CORNERS"}, {"kind": "INTERSECTION", "regions": [{"kind": "ROW", "value": 1}, {"kind": "COLUMN", "value": "A"}]}, {"kind": "COMMON_NEIGHBORS", "targets": ["A1", "C1"]}, {"kind": "BETWEEN", "targets": ["A1", "C3"]}][i]
            clue = {"type": "EXACTLY", "k": 0, "region": region}
        elif clue_kind == "REGION": clue = {"type": "FACT", "target": coord, "status": "INNOCENT"}
        elif clue_kind == "CONNECTIVITY" and i > 0: clue = {"type": "FACT", "target": coord, "status": "INNOCENT"}
        else: clue = {"type": "FACT", "target": coord, "status": "INNOCENT"}
        clue["text"] = format_clue_text(clue); clues.append(clue)
    if clue_kind != "NONE":
        # Clue đầu tiên là điểm khởi động no-guess: nó chứa các FACT đúng
        # cho toàn bộ bàn, đồng thời giữ lại clue mở rộng của puzzle.
        seed_subclues = [{"type": "FACT", "target": c, "status": "INNOCENT"} for c in coords]
        seed_subclues.append(clues[0])
        clues[0] = {"type": "COMPOUND", "op": "AND", "subclues": seed_subclues}
        clues[0]["text"] = format_clue_text(clues[0])
    cells = [{"coord": c, "name": names[i], "profession": ["Astronaut", "Baker", "Chef", "Doctor"][i % 4], "hidden_status": "INNOCENT", "clue": clues[i]} for i, c in enumerate(coords)]
    return {"puzzle_id": puzzle_id, "title": puzzle_id.replace("_", " ").title(), "size": size, "initial_revealed": coords[:max(1, min(3, size - 1))], "cells": cells, "expected_outcome": expected, "notes": "Sinh bởi generate_puzzles.py với seed 20261125."}


def main() -> None:
    random.seed(20261125); OUT.mkdir(parents=True, exist_ok=True)
    specs = [("easy_3x3_01", 3, "FACT"), ("parity_3x3_02", 3, "PARITY"), ("compare_3x3_03", 3, "COMPARE"), ("regions_3x3_04", 3, "REGION"), ("compound_3x3_05", 3, "COMPOUND"), ("medium_4x4_01", 4, "COMPARE"), ("connectivity_4x4_02", 4, "CONNECTIVITY"), ("regions_4x4_03", 4, "REGION"), ("ambiguous_4x4", 4, "NONE"), ("stress_5x5_01", 5, "FACT"), ("stress_5x5_02", 5, "COMPOUND")]
    for puzzle_id, size, kind in specs:
        data = make_puzzle(puzzle_id, size, kind, "UNKNOWN" if kind == "NONE" else "SOLVABLE")
        if kind == "NONE":
            for cell in data["cells"]:
                cell["clue"] = {"type": "EXACTLY", "k": 0, "region": {"kind": "EXPLICIT", "cells": []}, "text": "Exactly 0 criminals in the selected cells."}
        (OUT / f"{puzzle_id}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__": main()
