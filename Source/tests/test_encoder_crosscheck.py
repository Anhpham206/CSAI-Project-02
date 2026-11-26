"""Cross-check nhỏ giữa encoder CNF, SAT tham chiếu và evaluator."""

from __future__ import annotations

from itertools import product
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from logic import CNFEncoder, SemanticEvaluator  # noqa: E402
from reference_sat import is_satisfiable  # noqa: E402


class TestEncoderCrosscheck(unittest.TestCase):
    def _check(self, clue: dict) -> None:
        evaluator = SemanticEvaluator(3)
        for mode in ("direct", "counter"):
            encoded = CNFEncoder(mode).encode_clue(clue, 3)
            for bits in product((False, True), repeat=9):
                assignment = {i + 1: value for i, value in enumerate(bits)}
                sat = is_satisfiable(encoded["clauses"], assignment, 9 + encoded["num_aux_vars"])
                self.assertEqual(sat, evaluator.evaluate(clue, assignment), (clue, mode, bits))

    def test_count_parity_and_compare(self) -> None:
        self._check({"type": "EXACTLY", "k": 1, "region": {"kind": "ROW", "value": 1}})
        self._check({"type": "PARITY", "parity": "ODD", "region": {"kind": "ROW", "value": 1}})
        self._check({"type": "COMPARE", "op": "EQ", "region1": {"kind": "ROW", "value": 1}, "region2": {"kind": "COLUMN", "value": "A"}})


if __name__ == "__main__":
    unittest.main()
