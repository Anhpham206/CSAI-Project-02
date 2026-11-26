"""Kiểm thử schema và ngữ nghĩa của toàn bộ bộ puzzle TV2."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from game.engine import GameEngine  # noqa: E402
from logic import CNFEncoder, SemanticEvaluator  # noqa: E402
from reference_sat import is_satisfiable  # noqa: E402


PUZZLES = Path(__file__).resolve().parents[1] / "data" / "puzzles"


class TestPuzzleDataset(unittest.TestCase):
    def test_dataset_loads_and_clues_match_hidden_status(self) -> None:
        files = sorted(PUZZLES.glob("*.json"))
        self.assertGreaterEqual(len(files), 10)
        sizes = {json.loads(path.read_text(encoding="utf-8"))["size"] for path in files}
        self.assertTrue({3, 4, 5}.issubset(sizes))
        for path in files:
            raw = json.loads(path.read_text(encoding="utf-8")); self.assertEqual(raw["puzzle_id"], path.stem)
            GameEngine(path)
            assignment = {cell["coord"]: cell["hidden_status"] for cell in raw["cells"]}
            clues = [cell["clue"] for cell in raw["cells"] if cell["clue"] is not None]
            actual = SemanticEvaluator(raw["size"]).evaluate_all(clues, assignment)
            if raw["puzzle_id"] == "inconsistent_3x3":
                self.assertFalse(actual, path.name)
            else:
                self.assertTrue(actual, path.name)
            public = {
                "size": raw["size"],
                "known_verdicts": {c["coord"]: c["hidden_status"] for c in raw["cells"] if c["coord"] in set(raw.get("initial_revealed", []))},
                "revealed_clues": [{"owner_coord": c["coord"], "clue": c["clue"]} for c in raw["cells"]],
            }
            kb = CNFEncoder().build_kb(public)
            primary = {i + 1: assignment[coord] == "CRIMINAL" for i, coord in enumerate(sorted(assignment, key=lambda c: next((j + 1 for j, x in enumerate(raw["cells"]) if x["coord"] == c), 0)))}
            self.assertEqual(is_satisfiable(kb["clauses"], primary, kb["num_primary_vars"] + kb["num_aux_vars"]), actual, path.name)

    def test_required_outcomes_and_clue_families_exist(self) -> None:
        raws = [json.loads(path.read_text(encoding="utf-8")) for path in PUZZLES.glob("*.json")]
        self.assertTrue(any(x.get("expected_outcome") == "UNKNOWN" for x in raws))
        self.assertTrue(any(x["puzzle_id"] == "inconsistent_3x3" for x in raws))
        self.assertGreaterEqual(sum(x["size"] == 5 for x in raws), 2)
        types: set[str] = set()
        def collect(clue: dict) -> None:
            types.add(clue["type"])
            for sub in clue.get("subclues", clue.get("clues", [])):
                collect(sub)
        for puzzle in raws:
            for cell in puzzle["cells"]:
                if cell.get("clue"):
                    collect(cell["clue"])
        self.assertTrue({"FACT", "SAME", "DIFFERENT", "EXACTLY", "AT_LEAST", "AT_MOST", "PARITY", "COMPARE", "COMPOUND", "CONNECTIVITY"}.issubset(types))

    def test_main_cli_runs_for_every_puzzle(self) -> None:
        root = PUZZLES.parents[2]
        for path in sorted(PUZZLES.glob("*.json")):
            completed = subprocess.run([sys.executable, str(root / "Source" / "main.py"), "--cli", "--puzzle", str(path)], cwd=root, capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 0, (path.name, completed.stderr))
            self.assertIn("STATUS:", completed.stdout, path.name)


if __name__ == "__main__":
    unittest.main()
