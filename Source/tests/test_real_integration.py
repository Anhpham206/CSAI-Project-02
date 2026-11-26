"""Integration tests for CNFEncoder + DPLLSolver + DeductiveAgent + GameEngine."""

from __future__ import annotations

from pathlib import Path
import unittest

from agent.deductive_agent import (
    VERDICT_INCONSISTENT,
    VERDICT_UNKNOWN,
)
from agent.deductive_agent import DeductiveAgent
from game.engine import GameEngine
from logic.encoder import CNFEncoder
from solver.dpll import DPLLSolver


PUZZLES_DIR = Path(__file__).resolve().parents[1] / "data" / "puzzles"


class TestRealDeductivePipeline(unittest.TestCase):
    def _build_agent(self) -> DeductiveAgent:
        return DeductiveAgent(
            encoder=CNFEncoder(),
            solver=DPLLSolver(),
        )

    def test_real_pipeline_solves_3x3_and_4x4(self) -> None:
        cases = (
            ("sample_3x3.json", 9, 7),
            ("sample_4x4.json", 16, 13),
        )
        for filename, total_cells, expected_steps in cases:
            with self.subTest(filename=filename):
                agent = self._build_agent()
                engine = GameEngine(PUZZLES_DIR / filename, validator=agent)

                trace = agent.solve_all(engine)

                self.assertTrue(engine.is_solved())
                self.assertEqual(engine.get_public_state()["revealed_count"], total_cells)
                self.assertEqual(len(trace), expected_steps)
                self.assertTrue(all(record["selected_coord"] for record in trace))

    def test_real_pipeline_handles_unknown(self) -> None:
        agent = self._build_agent()
        engine = GameEngine(PUZZLES_DIR / "ambiguous_3x3.json", validator=agent)

        trace = agent.solve_all(engine)

        self.assertFalse(engine.is_solved())
        self.assertEqual(len(trace), 1)
        self.assertEqual(trace[0]["verdict"], VERDICT_UNKNOWN)
        self.assertIsNone(trace[0]["selected_coord"])

    def test_real_pipeline_handles_inconsistent(self) -> None:
        agent = self._build_agent()
        engine = GameEngine(PUZZLES_DIR / "inconsistent_3x3.json", validator=agent)

        trace = agent.solve_all(engine)

        self.assertFalse(engine.is_solved())
        self.assertEqual(len(trace), 1)
        self.assertEqual(trace[0]["verdict"], VERDICT_INCONSISTENT)
        self.assertIsNone(trace[0]["selected_coord"])

    def test_real_pipeline_solves_5x5_stress_puzzle(self) -> None:
        agent = self._build_agent()
        engine = GameEngine(PUZZLES_DIR / "stress_5x5_01.json", validator=agent)

        trace = agent.solve_all(engine)

        self.assertTrue(engine.is_solved())
        self.assertEqual(engine.get_public_state()["revealed_count"], 25)
        self.assertEqual(len(trace), 22)


if __name__ == "__main__":
    unittest.main()
