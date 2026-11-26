"""Kiểm thử đơn vị cho CNFEncoder của TV2."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from logic import CNFEncoder, ClueEncodingError  # noqa: E402


class TestEncoder(unittest.TestCase):
    def test_row_major_mapping_and_basic_clues(self) -> None:
        encoder = CNFEncoder()
        self.assertEqual(encoder.encode_clue({"type": "FACT", "target": "A1", "status": "CRIMINAL"}, 3)["clauses"], [[1]])
        self.assertEqual(encoder.encode_clue({"type": "SAME", "targets": ["B1", "A2"]}, 3)["clauses"], [[-2, 4], [2, -4]])
        self.assertEqual(encoder.encode_clue({"type": "DIFFERENT", "targets": ["B1", "A2"]}, 3)["clauses"], [[2, 4], [-2, -4]])

    def test_exactly_direct_and_counter(self) -> None:
        clue = {"type": "EXACTLY", "k": 1, "region": {"kind": "ROW", "value": 1}}
        direct = CNFEncoder("direct").encode_clue(clue, 3)
        self.assertEqual({tuple(c) for c in direct["clauses"]}, {(1, 2, 3), (-1, -2), (-1, -3), (-2, -3)})
        counter = CNFEncoder("counter").encode_clue(clue, 3)
        self.assertGreater(counter["num_aux_vars"], 0)
        self.assertTrue(all(0 not in c for c in counter["clauses"]))

    def test_validation_and_build_contract(self) -> None:
        with self.assertRaises(ClueEncodingError):
            CNFEncoder().encode_clue({"type": "EXACTLY", "k": 4, "region": {"kind": "ROW", "value": 1}}, 3)
        state = {"size": 2, "known_verdicts": {"A1": "INNOCENT"}, "revealed_clues": [{"owner_coord": "A1", "clue": {"type": "FACT", "target": "B1", "status": "CRIMINAL"}}], "cells": {}}
        kb = CNFEncoder().build_kb(state)
        self.assertEqual(set(kb), {"clauses", "num_primary_vars", "num_aux_vars", "num_clauses"})
        self.assertEqual(kb["clauses"], [[-1], [2]])


if __name__ == "__main__":
    unittest.main()
