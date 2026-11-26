"""Kiểm tra schema, clue và số mô hình của các puzzle TV2."""

from __future__ import annotations
import json, sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from game.engine import GameEngine
from logic import CNFEncoder, SemanticEvaluator

def main() -> int:
    directory = Path(__file__).resolve().parents[1] / "data" / "puzzles"; failed = False
    print("| id | size | models (<=4) | expected |")
    print("|---|---:|---:|---|")
    for path in sorted(directory.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8")); engine = GameEngine(path); state = engine.get_public_state()
            initial = set(raw.get("initial_revealed", []))
            full = {"size": raw["size"], "known_verdicts": {c["coord"]: c["hidden_status"] for c in raw["cells"] if c["coord"] in initial}, "revealed_clues": [{"owner_coord": c["coord"], "clue": c["clue"]} for c in raw["cells"]]}
            clues = [c["clue"] for c in full["revealed_clues"]]
            models = SemanticEvaluator(state["size"]).count_models(clues, full["known_verdicts"]) if state["size"] <= 4 else -1
            kb = CNFEncoder().build_kb(full); print(f"| {raw['puzzle_id']} | {state['size']} | {models} | {raw.get('expected_outcome', '-') } |")
            failed |= raw["puzzle_id"] != path.stem
            hidden = {c["coord"]: c["hidden_status"] == "CRIMINAL" for c in raw["cells"]}
            failed |= not SemanticEvaluator(state["size"]).evaluate_all(clues, hidden)
            if not kb["num_clauses"] >= 0: failed = True
        except Exception as exc:
            print(f"| {path.stem} | ERROR | {exc} | - |"); failed = True
    return 1 if failed else 0

if __name__ == "__main__": raise SystemExit(main())
