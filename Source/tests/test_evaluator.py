"""Kiểm thử đánh giá ngữ nghĩa độc lập với encoder."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from logic import SemanticEvaluator  # noqa: E402


class TestEvaluator(unittest.TestCase):
    def setUp(self) -> None:
        self.ev = SemanticEvaluator(3)
        self.assignment = {"A1": "CRIMINAL", "B1": "INNOCENT", "C1": False, "A2": True, "B2": False, "C2": False, "A3": False, "B3": False, "C3": False}

    def test_core_and_extended_clues(self) -> None:
        self.assertTrue(self.ev.evaluate({"type": "FACT", "target": "A1", "status": "CRIMINAL"}, self.assignment))
        self.assertTrue(self.ev.evaluate({"type": "SAME", "targets": ["B1", "C1"]}, self.assignment))
        self.assertTrue(self.ev.evaluate({"type": "DIFFERENT", "targets": ["A1", "B1"]}, self.assignment))
        self.assertTrue(self.ev.evaluate({"type": "EXACTLY", "k": 1, "region": {"kind": "ROW", "value": 1}}, self.assignment))
        self.assertTrue(self.ev.evaluate({"type": "PARITY", "parity": "EVEN", "region": {"kind": "COLUMN", "value": "C"}}, self.assignment))
        self.assertTrue(self.ev.evaluate({"type": "COMPARE", "op": "GT", "region1": {"kind": "ROW", "value": 1}, "region2": {"kind": "ROW", "value": 3}}, self.assignment))
        self.assertTrue(self.ev.evaluate({"type": "COMPOUND", "op": "AND", "subclues": [{"type": "FACT", "target": "A1", "status": "CRIMINAL"}, {"type": "FACT", "target": "B1", "status": "INNOCENT"}]}, self.assignment))

    def test_missing_assignment_is_explicit(self) -> None:
        with self.assertRaises(KeyError):
            self.ev.evaluate({"type": "FACT", "target": "A1", "status": "CRIMINAL"}, {})


if __name__ == "__main__":
    unittest.main()
