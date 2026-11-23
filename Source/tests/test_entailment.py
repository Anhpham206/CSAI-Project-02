"""
Unit tests cho Nhiệm vụ 1:
Kiểm tra hàm hệ quả logic (KB AND NOT Ci, KB AND Ci) dùng MockSolver.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

# Thêm thư mục Source vào sys.path để import trực tiếp `agent`
SOURCE_DIR = Path(__file__).resolve().parent.parent
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from agent.deductive_agent import (
    VERDICT_CRIMINAL,
    VERDICT_INCONSISTENT,
    VERDICT_INNOCENT,
    VERDICT_UNKNOWN,
    DeductiveAgent,
    check_entailment,
    coord_to_var,
    is_kb_consistent,
    var_to_coord,
)
from agent.mock_solver import MockSolver


def test_entailment_direct_and_derived_criminal():
    """KB: A1 là Criminal, và SAME(A1, B1) => B1 chắc chắn là CRIMINAL."""
    # A1=1, B1=2; SAME(1, 2) <=> (-1 v 2) & (1 v -2)
    clauses = [[1], [-1, 2], [1, -2]]
    solver = MockSolver(total_vars=2)

    verdict, queries = check_entailment(clauses, var_id=2, solver=solver, target_coord="B1")

    assert verdict == VERDICT_CRIMINAL
    assert len(queries) == 2
    assert queries[0]["target_coord"] == "B1"
    assert queries[0]["assumed_verdict"] == VERDICT_INNOCENT
    assert queries[0]["result"] == "UNSAT"
    assert queries[1]["assumed_verdict"] == VERDICT_CRIMINAL
    assert queries[1]["result"] == "SAT"


def test_entailment_derived_innocent():
    """KB: A1 là Criminal, và DIFFERENT(A1, B1) => B1 chắc chắn là INNOCENT."""
    # DIFFERENT(1, 2) <=> (1 v 2) & (-1 v -2)
    clauses = [[1], [1, 2], [-1, -2]]
    solver = MockSolver(total_vars=2)

    verdict, queries = check_entailment(clauses, var_id=2, solver=solver, target_coord="B1")

    assert verdict == VERDICT_INNOCENT
    assert queries[0]["assumed_verdict"] == VERDICT_INNOCENT
    assert queries[0]["result"] == "SAT"
    assert queries[1]["assumed_verdict"] == VERDICT_CRIMINAL
    assert queries[1]["result"] == "UNSAT"


def test_entailment_unknown_when_both_sat():
    """KB: EXACTLY(1, {A1, B1}) => chưa đủ dữ kiện để kết luận A1 hay B1."""
    clauses = [[1, 2], [-1, -2]]
    solver = MockSolver(total_vars=2)

    verdict_a1, queries_a1 = check_entailment(clauses, var_id=1, solver=solver, target_coord="A1")
    verdict_b1, queries_b1 = check_entailment(clauses, var_id=2, solver=solver, target_coord="B1")

    assert verdict_a1 == VERDICT_UNKNOWN
    assert verdict_b1 == VERDICT_UNKNOWN
    assert [q["result"] for q in queries_a1] == ["SAT", "SAT"]
    assert [q["result"] for q in queries_b1] == ["SAT", "SAT"]


def test_entailment_inconsistent_kb():
    """KB mâu thuẫn: A1 vừa Criminal vừa Innocent => mọi truy vấn đều INCONSISTENT."""
    clauses = [[1], [-1]]
    solver = MockSolver(total_vars=2)

    consistent, model, _ = is_kb_consistent(clauses, solver)
    assert consistent is False
    assert model is None

    verdict, queries = check_entailment(clauses, var_id=2, solver=solver, target_coord="B1")
    assert verdict == VERDICT_INCONSISTENT
    assert [q["result"] for q in queries] == ["UNSAT", "UNSAT"]


def test_clauses_not_mutated_and_stats_contract():
    """Đảm bảo check_entailment không làm thay đổi clauses gốc và stats đúng Data Contract 2."""
    clauses = [[1], [-1, 2], [2, 3]]
    original_snapshot = copy.deepcopy(clauses)
    solver = MockSolver(total_vars=3)

    agent = DeductiveAgent(solver=solver)
    verdict, queries = agent.check_cell_entailment(clauses, var_id=2, target_coord="B1")

    assert verdict == VERDICT_CRIMINAL
    assert clauses == original_snapshot

    for query in queries:
        stats = query["stats"]
        assert set(stats.keys()) == {"decisions", "propagations", "backtracks", "runtime"}
        assert isinstance(stats["decisions"], int)
        assert isinstance(stats["propagations"], int)
        assert isinstance(stats["backtracks"], int)
        assert isinstance(stats["runtime"], float)


def test_small_3x3_mixed_deduction():
    """
    Lưới 3x3:
      - A1 (1) = Criminal
      - B1 (2) = Innocent
      - EXACTLY(1, Row 1 = {1, 2, 3}) => C1 (3) chắc chắn Innocent
      - SAME(A1=1, A2=4) => A2 (4) chắc chắn Criminal
      - B2 (5) không có ràng buộc => UNKNOWN
    """
    clauses = [
        [1],                # FACT: A1 = Criminal
        [-2],               # FACT: B1 = Innocent
        [1, 2, 3],          # AT_LEAST(1, {1, 2, 3})
        [-1, -2],           # AT_MOST(1, {1, 2, 3})
        [-1, -3],
        [-2, -3],
        [-1, 4], [1, -4],   # SAME(1, 4)
    ]
    solver = MockSolver(total_vars=9)
    agent = DeductiveAgent(solver=solver)

    v_c1, _ = agent.check_cell_entailment(clauses, coord_to_var("C1", 3), "C1")
    v_a2, _ = agent.check_cell_entailment(clauses, coord_to_var("A2", 3), "A2")
    v_b2, _ = agent.check_cell_entailment(clauses, coord_to_var("B2", 3), "B2")

    assert v_c1 == VERDICT_INNOCENT
    assert v_a2 == VERDICT_CRIMINAL
    assert v_b2 == VERDICT_UNKNOWN


def test_coord_var_mapping_row_major():
    """Kiểm tra quy ước đánh số row-major theo Data Contract 1."""
    assert coord_to_var("A1", 3) == 1
    assert coord_to_var("B1", 3) == 2
    assert coord_to_var("C1", 3) == 3
    assert coord_to_var("A2", 3) == 4
    assert coord_to_var("C3", 3) == 9

    assert var_to_coord(1, 3) == "A1"
    assert var_to_coord(4, 3) == "A2"
    assert var_to_coord(9, 3) == "C3"


def test_invalid_inputs_raise_value_error():
    solver = MockSolver(total_vars=3)
    with pytest.raises(ValueError):
        check_entailment([[1]], var_id=0, solver=solver)
    with pytest.raises(ValueError):
        check_entailment([[1]], var_id=-2, solver=solver)
    with pytest.raises(ValueError):
        coord_to_var("D1", 3)
    with pytest.raises(ValueError):
        DeductiveAgent(solver=None).check_cell_entailment([[1]], var_id=1)

