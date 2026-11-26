"""
Unit test cho bộ giải DPLLSolver.
Chạy lệnh: python -m unittest Source/tests/test_dpll.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parent.parent
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from solver import DPLLSolver


def is_model_valid(cnf: list[list[int]], model: dict[int, bool]) -> bool:
    """Kiểm tra model có làm mọi mệnh đề trong CNF đều đúng hay không."""
    for clause in cnf:
        if not any(
            (lit > 0 and model[abs(lit)]) or (lit < 0 and not model[abs(lit)])
            for lit in clause
        ):
            return False
    return True


class TestDPLLSolver(unittest.TestCase):
    def setUp(self) -> None:
        self.solver = DPLLSolver()

    def test_empty_cnf_is_sat(self) -> None:
        solver = DPLLSolver(total_vars=3)
        is_sat, model, stats = solver.solve([])
        self.assertTrue(is_sat)
        self.assertIsNotNone(model)
        self.assertEqual(set(model.keys()), {1, 2, 3})
        self.assertIn("runtime", stats)

    def test_empty_clause_is_unsat(self) -> None:
        is_sat, model, stats = self.solver.solve([[1, 2], []])
        self.assertFalse(is_sat)
        self.assertIsNone(model)
        self.assertEqual(stats["decisions"], 0)
        self.assertEqual(stats["backtracks"], 0)

    def test_unit_propagation_chain(self) -> None:
        # Lan truyền dây chuyền: x1=T -> x2=T -> x3=F -> x4=T, không cần phân nhánh
        cnf = [[1], [-1, 2], [-2, -3], [3, 4]]
        is_sat, model, stats = self.solver.solve(cnf)
        self.assertTrue(is_sat)
        self.assertIsNotNone(model)
        self.assertTrue(is_model_valid(cnf, model))
        self.assertEqual(model, {1: True, 2: True, 3: False, 4: True})
        self.assertEqual(stats["decisions"], 0)
        self.assertEqual(stats["propagations"], 4)
        self.assertEqual(stats["backtracks"], 0)

    def test_branching_and_backtracking_unsat(self) -> None:
        # Thử hết mọi tổ hợp của (1, 2) đều xung đột
        cnf = [[1, 2], [1, -2], [-1, 2], [-1, -2]]
        is_sat, model, stats = self.solver.solve(cnf)
        self.assertFalse(is_sat)
        self.assertIsNone(model)
        self.assertGreaterEqual(stats["decisions"], 1)
        self.assertGreaterEqual(stats["backtracks"], 1)

    def test_backtracking_finds_sat_on_second_branch(self) -> None:
        # Nhánh x1=True bị xung đột nên phải quay lui sang x1=False
        cnf = [[-1, 2], [-1, -2], [1, 3]]
        is_sat, model, stats = self.solver.solve(cnf)
        self.assertTrue(is_sat)
        self.assertIsNotNone(model)
        self.assertTrue(is_model_valid(cnf, model))
        self.assertFalse(model[1])
        self.assertTrue(model[3])
        self.assertGreaterEqual(stats["backtracks"], 1)

    def test_assumptions_entailment_example_from_pdf(self) -> None:
        # Ví dụ mục 3.4 trong đề: KB = (A v B) ^ (~A v B) => B chắc chắn True (A=1, B=2)
        kb = [[1, 2], [-1, 2]]

        # Giả sử B=False => KB ^ ~B phải UNSAT
        sat_not_b, model_not_b, _ = self.solver.solve(kb, assumptions=[-2])
        self.assertFalse(sat_not_b)
        self.assertIsNone(model_not_b)

        # Giả sử B=True => KB ^ B phải SAT
        sat_b, model_b, _ = self.solver.solve(kb, assumptions=[2])
        self.assertTrue(sat_b)
        self.assertTrue(is_model_valid(kb, model_b))

        # A vẫn chưa xác định được vì cả 2 giả sử đều SAT
        sat_a, _, _ = self.solver.solve(kb, assumptions=[1])
        sat_not_a, _, _ = self.solver.solve(kb, assumptions=[-1])
        self.assertTrue(sat_a)
        self.assertTrue(sat_not_a)

    def test_conflicting_assumptions_is_unsat(self) -> None:
        is_sat, model, stats = self.solver.solve([[1, 2]], assumptions=[1, -1])
        self.assertFalse(is_sat)
        self.assertIsNone(model)
        self.assertEqual(stats["decisions"], 0)
        self.assertEqual(stats["backtracks"], 0)

    def test_tautology_and_duplicate_literals(self) -> None:
        cnf = [[1, -1, 2], [1, 1, 2], [-2]]
        is_sat, model, _ = self.solver.solve(cnf)
        self.assertTrue(is_sat)
        self.assertIsNotNone(model)
        self.assertTrue(is_model_valid(cnf, model))
        self.assertTrue(model[1])
        self.assertFalse(model[2])

    def test_does_not_mutate_input_cnf_or_assumptions(self) -> None:
        cnf = [[1, 2], [-1, 3], [-2, -3]]
        assumptions = [1]
        cnf_snapshot = [list(c) for c in cnf]
        assumptions_snapshot = list(assumptions)

        self.solver.solve(cnf, assumptions=assumptions)

        self.assertEqual(cnf, cnf_snapshot)
        self.assertEqual(assumptions, assumptions_snapshot)

    def test_invalid_zero_literal_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.solver.solve([[1, 0]])
        with self.assertRaises(ValueError):
            self.solver.solve([[1, 2]], assumptions=[0])

    def test_stats_keys_and_types(self) -> None:
        is_sat, model, stats = self.solver.solve([[1, 2], [-1, 2]])
        self.assertTrue(is_sat)
        self.assertIsNotNone(model)
        for key in ("decisions", "propagations", "backtracks"):
            self.assertIn(key, stats)
            self.assertIsInstance(stats[key], int)
        self.assertIn("runtime", stats)
        self.assertIsInstance(stats["runtime"], float)
        self.assertGreaterEqual(stats["runtime"], 0.0)


if __name__ == "__main__":
    unittest.main()
