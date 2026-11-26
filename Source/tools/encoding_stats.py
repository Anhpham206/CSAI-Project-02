"""In thống kê kích thước CNF cho từng puzzle và chế độ mã hóa."""

from __future__ import annotations
import json, sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from game.engine import GameEngine
from logic import CNFEncoder

def main() -> None:
    print("| puzzle | mode | primary | aux | clauses |\n|---|---|---:|---:|---:|")
    for path in sorted((Path(__file__).resolve().parents[1] / "data" / "puzzles").glob("*.json")):
        state = GameEngine(path).get_public_state()
        for mode in ("direct", "counter", "auto"):
            kb = CNFEncoder(mode).build_kb(state); print(f"| {path.stem} | {mode} | {kb['num_primary_vars']} | {kb['num_aux_vars']} | {kb['num_clauses']} |")

if __name__ == "__main__": main()
