"""
Unit tests cho Nhiệm vụ 2:
Kiểm thử toàn bộ nghiệp vụ của DeductiveAgent với MockSolver, MockEncoder
và MockGameEngine (thông qua PublicOnlyEngineProxy):
  - step() và solve_all() (Solved State, UNKNOWN, INCONSISTENT, thứ tự row-major)
  - Schema Deduction Trace theo Data Contract 3 + format_trace + get_summary_stats
  - hint(public_state) không làm thay đổi trạng thái ván cờ
  - check_uniqueness(kb_data) bao gồm ca chứa biến phụ trợ (> N^2)
  - evaluate_manual_move() phân biệt PROVABLE / NOT_PROVABLE / CONTRADICTED
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

SOURCE_DIR = Path(__file__).resolve().parent.parent
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from agent.deductive_agent import (
    MOVE_CONTRADICTED,
    MOVE_NOT_PROVABLE,
    MOVE_PROVABLE,
    UNIQUENESS_MULTIPLE,
    UNIQUENESS_NONE,
    UNIQUENESS_UNIQUE,
    VERDICT_CRIMINAL,
    VERDICT_INCONSISTENT,
    VERDICT_INNOCENT,
    VERDICT_SOLVED,
    VERDICT_UNKNOWN,
    DeductiveAgent,
    _extract_active_clue_ids,
    _extract_hidden_coords,
    _infer_board_size,
)
from agent.mock_env import MockEncoder, MockGameEngine, PublicOnlyEngineProxy
from agent.mock_solver import MockSolver


def _build_solvable_3x3_engine() -> MockGameEngine:
    """
    Tạo màn chơi 3x3 giải được hoàn toàn theo chuỗi suy luận không đoán mò.

    Đáp án thật:
      A1=CRIMINAL, B1=INNOCENT, C1=INNOCENT
      A2=CRIMINAL, B2=CRIMINAL, C2=INNOCENT
      A3=INNOCENT, B3=INNOCENT, C3=CRIMINAL
    """
    secret_roles = {
        "A1": VERDICT_CRIMINAL,
        "B1": VERDICT_INNOCENT,
        "C1": VERDICT_INNOCENT,
        "A2": VERDICT_CRIMINAL,
        "B2": VERDICT_CRIMINAL,
        "C2": VERDICT_INNOCENT,
        "A3": VERDICT_INNOCENT,
        "B3": VERDICT_INNOCENT,
        "C3": VERDICT_CRIMINAL,
    }
    secret_clues = {
        # Ban đầu chỉ mở A1 -> từ A1 suy ra ngay được B1 và C1 (vì A1 đã là 1 Criminal)
        "A1": {"type": "EXACTLY", "k": 1, "targets": ["A1", "B1", "C1"]},
        # Khi lật B1 -> lộ manh mối suy ra A2 = Criminal (cùng phe A1)
        "B1": {"type": "SAME", "targets": ["A1", "A2"]},
        # Khi lật C1 -> lộ manh mối suy ra C2 = Innocent (cùng phe C1)
        "C1": {"type": "SAME", "targets": ["C1", "C2"]},
        # Khi lật A2 -> lộ manh mối suy ra B2 = Criminal (vì C2 = Innocent, hàng 2 cần 2 Criminal)
        "A2": {"type": "EXACTLY", "k": 2, "targets": ["A2", "B2", "C2"]},
        # Khi lật B2 -> lộ manh mối suy ra A3 = Innocent (khác phe A2)
        "B2": {"type": "DIFFERENT", "targets": ["A2", "A3"]},
        # Khi lật C2 -> lộ manh mối suy ra C3 = Criminal (khác phe C2)
        "C2": {"type": "DIFFERENT", "targets": ["C2", "C3"]},
        # Khi lật A3 -> lộ manh mối suy ra B3 = Innocent (hàng 3 có đúng 1 Criminal là C3)
        "A3": {"type": "EXACTLY", "k": 1, "targets": ["A3", "B3", "C3"]},
        "B3": None,
        "C3": None,
    }
    return MockGameEngine(
        board_size=3,
        secret_roles=secret_roles,
        secret_clues=secret_clues,
        initial_revealed=["A1"],
    )


def test_solve_all_3x3_via_public_only_proxy_and_trace_contract():
    """
    Chạy solve_all() qua PublicOnlyEngineProxy để chứng minh Agent chỉ dùng
    thông tin công khai, giải hết 8 ô úp theo đúng thứ tự row-major và xuất
    Deduction Trace khớp 100% Data Contract 3.
    """
    raw_engine = _build_solvable_3x3_engine()
    proxy = PublicOnlyEngineProxy(raw_engine)

    agent = DeductiveAgent(encoder=MockEncoder(), solver_factory=MockSolver)
    trace = agent.solve_all(proxy)

    # Giải hết 8 ô còn lại (A1 đã mở sẵn)
    assert len(trace) == 8
    assert proxy.get_public_state()["hidden_coords"] == []

    # Bước 1: cả B1 và C1 đều chứng minh được, phải chọn B1 trước theo row-major
    assert trace[0]["step"] == 1
    assert trace[0]["active_clue_ids"] == ["A1"]
    assert trace[0]["selected_coord"] == "B1"
    assert trace[0]["verdict"] == VERDICT_INNOCENT
    assert trace[0]["revealed_clue"] == {"type": "SAME", "targets": ["A1", "A2"]}

    # Kiểm tra schema Data Contract 3 trên từng bản ghi trace
    expected_keys = {
        "step",
        "active_clue_ids",
        "sat_queries",
        "selected_coord",
        "verdict",
        "revealed_clue",
    }
    for idx, rec in enumerate(trace, start=1):
        assert set(rec.keys()) == expected_keys
        assert rec["step"] == idx
        assert rec["verdict"] in (VERDICT_CRIMINAL, VERDICT_INNOCENT)
        assert len(rec["sat_queries"]) >= 2
        for q in rec["sat_queries"]:
            assert set(q.keys()) == {"target_coord", "assumed_verdict", "result", "stats"}
            assert q["result"] in ("SAT", "UNSAT")
            assert set(q["stats"].keys()) == {
                "decisions",
                "propagations",
                "backtracks",
                "runtime",
            }

    # Kiểm tra tiện ích format_trace và get_summary_stats
    formatted = agent.format_trace()
    assert "Step 1:" in formatted
    assert "B1 -> INNOCENT" in formatted

    stats = agent.get_summary_stats()
    assert stats["total_steps"] == 8
    assert stats["deduction_steps"] == 8
    assert stats["sat_calls"] >= 16
    assert stats["runtime"] >= 0.0


def test_agent_accepts_game_engine_public_state_schema():
    """Agent đọc được đúng tên trường mà GameEngine/Web GUI công khai."""
    public_state = {
        "size": 2,
        "revealed_cells": ["A1"],
        "unrevealed_cells": ["B2", "A2", "B1"],
        "revealed_clues": [
            {"owner_coord": "A1", "clue": {"type": "FACT", "status": "CRIMINAL"}},
            {"owner_coord": "B1", "clue": None},
        ],
    }

    assert _infer_board_size(public_state) == 2
    assert _extract_hidden_coords(public_state, 2) == ["B1", "A2", "B2"]
    assert _extract_active_clue_ids(public_state, 2) == ["A1"]


def test_reset_is_compatible_with_game_engine_and_gui():
    agent = DeductiveAgent()
    agent.trace_history.append({"step": 1})

    agent.reset()

    assert agent.trace_history == []


def test_solve_all_stops_cleanly_on_unknown_board():
    """Màn chơi mơ hồ (thiếu dữ kiện): solve_all phải dừng ngay và báo UNKNOWN."""
    engine = MockGameEngine(
        board_size=2,
        secret_roles={
            "A1": VERDICT_CRIMINAL,
            "B1": VERDICT_INNOCENT,
            "A2": VERDICT_INNOCENT,
            "B2": VERDICT_CRIMINAL,
        },
        secret_clues={
            # Chỉ biết {A2, B2} có đúng 1 Criminal -> không suy ra được ô nào
            "A1": {"type": "EXACTLY", "k": 1, "targets": ["A2", "B2"]},
            "B1": None,
            "A2": None,
            "B2": None,
        },
        initial_revealed=["A1"],
    )

    agent = DeductiveAgent(encoder=MockEncoder(), solver_factory=MockSolver)
    trace = agent.solve_all(PublicOnlyEngineProxy(engine))

    assert len(trace) == 1
    assert trace[0]["selected_coord"] is None
    assert trace[0]["verdict"] == VERDICT_UNKNOWN
    assert trace[0]["revealed_clue"] is None
    # Đã quét đủ 3 ô úp (B1, A2, B2), mỗi ô 2 truy vấn SAT
    assert len(trace[0]["sat_queries"]) == 6


def test_step_and_solve_all_detect_inconsistent_kb():
    """Màn chơi chứa manh mối mâu thuẫn: phát hiện ngay INCONSISTENT và dừng sạch."""
    engine = MockGameEngine(
        board_size=2,
        secret_roles={
            "A1": VERDICT_CRIMINAL,
            "B1": VERDICT_INNOCENT,
            "A2": VERDICT_INNOCENT,
            "B2": VERDICT_CRIMINAL,
        },
        secret_clues={
            # A1 là Criminal nhưng manh mối lại nói A1 là Innocent -> mâu thuẫn!
            "A1": {"type": "FACT", "target": "A1", "verdict": VERDICT_INNOCENT},
            "B1": None,
            "A2": None,
            "B2": None,
        },
        initial_revealed=["A1"],
    )

    agent = DeductiveAgent(encoder=MockEncoder(), solver_factory=MockSolver)
    trace = agent.solve_all(PublicOnlyEngineProxy(engine))

    assert len(trace) == 1
    assert trace[0]["selected_coord"] is None
    assert trace[0]["verdict"] == VERDICT_INCONSISTENT
    assert trace[0]["revealed_clue"] is None


def test_step_on_already_solved_board():
    """Gọi step() khi bàn cờ không còn ô úp trả về SOLVED và không crash."""
    engine = MockGameEngine(
        board_size=2,
        secret_roles={
            "A1": VERDICT_CRIMINAL,
            "B1": VERDICT_INNOCENT,
            "A2": VERDICT_INNOCENT,
            "B2": VERDICT_CRIMINAL,
        },
        secret_clues={"A1": None, "B1": None, "A2": None, "B2": None},
        initial_revealed=["A1", "B1", "A2", "B2"],
    )

    agent = DeductiveAgent(encoder=MockEncoder(), solver_factory=MockSolver)
    result = agent.step(PublicOnlyEngineProxy(engine))
    assert result["verdict"] == VERDICT_SOLVED
    assert result["selected_coord"] is None


def test_hint_returns_first_row_major_move_without_mutating_state():
    """hint() trả về đúng định dạng Data Contract 3 và không làm đổi public_state."""
    engine = _build_solvable_3x3_engine()
    public_state = engine.get_public_state()
    snapshot = copy.deepcopy(public_state)

    agent = DeductiveAgent(encoder=MockEncoder(), solver_factory=MockSolver)
    suggestion = agent.hint(public_state)

    assert public_state == snapshot
    assert suggestion == {
        "target_coord": "B1",
        "verdict": VERDICT_INNOCENT,
        "active_clue_ids": ["A1"],
    }


def test_hint_returns_none_on_unknown_and_inconsistent_on_contradiction():
    agent = DeductiveAgent(encoder=MockEncoder(), solver_factory=MockSolver)

    unknown_state = {
        "board_size": 2,
        "revealed_cells": {
            "A1": {
                "verdict": VERDICT_CRIMINAL,
                "clue": {"type": "EXACTLY", "k": 1, "targets": ["A2", "B2"]},
            }
        },
        "hidden_coords": ["B1", "A2", "B2"],
        "active_clue_ids": ["A1"],
    }
    assert agent.hint(unknown_state) is None

    inconsistent_state = {
        "board_size": 2,
        "revealed_cells": {
            "A1": {
                "verdict": VERDICT_CRIMINAL,
                "clue": {"type": "FACT", "target": "A1", "verdict": VERDICT_INNOCENT},
            }
        },
        "hidden_coords": ["B1", "A2", "B2"],
        "active_clue_ids": ["A1"],
    }
    inconsistent_hint = agent.hint(inconsistent_state)
    assert inconsistent_hint == {
        "target_coord": None,
        "verdict": VERDICT_INCONSISTENT,
        "active_clue_ids": ["A1"],
    }


def test_check_uniqueness_unique_multiple_and_no_solution():
    agent = DeductiveAgent(solver_factory=MockSolver)

    # 1. Nghiệm duy nhất trên lưới 2x2 (4 biến chính)
    kb_unique = {
        "clauses": [[1], [-2], [-3], [4]],
        "num_primary_vars": 4,
        "num_aux_vars": 0,
        "num_clauses": 4,
    }
    clauses_snapshot = copy.deepcopy(kb_unique["clauses"])
    res_unique = agent.check_uniqueness(kb_unique)
    assert res_unique["status"] == UNIQUENESS_UNIQUE
    assert res_unique["is_unique"] is True
    assert res_unique["model_1"] == {1: True, 2: False, 3: False, 4: True}
    assert res_unique["model_2"] is None
    assert kb_unique["clauses"] == clauses_snapshot

    # 2. Nhiều nghiệm (biến 4 tự do)
    kb_multi = {
        "clauses": [[1], [-2], [-3]],
        "num_primary_vars": 4,
        "num_aux_vars": 0,
        "num_clauses": 3,
    }
    res_multi = agent.check_uniqueness(kb_multi)
    assert res_multi["status"] == UNIQUENESS_MULTIPLE
    assert res_multi["is_unique"] is False
    assert res_multi["model_1"] is not None
    assert res_multi["model_2"] is not None
    assert res_multi["model_1"][4] != res_multi["model_2"][4]

    # 3. Vô nghiệm (INCONSISTENT)
    kb_unsat = {
        "clauses": [[1], [-1]],
        "num_primary_vars": 4,
        "num_aux_vars": 0,
        "num_clauses": 2,
    }
    res_unsat = agent.check_uniqueness(kb_unsat)
    assert res_unsat["status"] == UNIQUENESS_NONE
    assert res_unsat["is_unique"] is False
    assert res_unsat["model_1"] is None


def test_check_uniqueness_ignores_auxiliary_variables_in_blocking_clause():
    """
    Ca kiểm thử bắt buộc của Nhiệm vụ 2:
    Lưới 2x2 (biến chính 1..4) có ĐÚNG 1 nghiệm bàn cờ duy nhất, nhưng có
    2 biến phụ trợ (5, 6) có thể nhận nhiều giá trị khác nhau (vd: 5 v 6).
    Blocking clause chỉ chứa 1..4 nên check_uniqueness PHẢI kết luận UNIQUE,
    không được báo sai thành MULTIPLE_SOLUTIONS.
    """
    kb_with_aux = {
        "clauses": [
            [1],
            [-2],
            [-3],
            [4],
            [5, 6],  # Biến phụ 5 và 6 có tới 3 tổ hợp thỏa mãn (T/F, F/T, T/T)
        ],
        "num_primary_vars": 4,
        "num_aux_vars": 2,
        "num_clauses": 5,
    }
    agent = DeductiveAgent(solver_factory=MockSolver)
    result = agent.check_uniqueness(kb_with_aux)

    assert result["status"] == UNIQUENESS_UNIQUE
    assert result["is_unique"] is True
    assert result["model_2"] is None


def test_evaluate_manual_move_provable_contradicted_and_not_provable():
    """Hỗ trợ GameEngine phân biệt PROVABLE / CONTRADICTED / NOT_PROVABLE."""
    agent = DeductiveAgent(encoder=MockEncoder(), solver_factory=MockSolver)
    public_state = {
        "board_size": 2,
        "revealed_cells": {
            "A1": {
                "verdict": VERDICT_CRIMINAL,
                "clue": {"type": "DIFFERENT", "targets": ["A1", "B1"]},
            }
        },
        "hidden_coords": ["B1", "A2", "B2"],
        "active_clue_ids": ["A1"],
    }

    # B1 chắc chắn là INNOCENT
    assert agent.evaluate_manual_move(public_state, "B1", VERDICT_INNOCENT) == MOVE_PROVABLE
    assert agent.evaluate_manual_move(public_state, "B1", VERDICT_CRIMINAL) == MOVE_CONTRADICTED

    # A2 chưa có manh mối nào -> cả hai phán đoán đều NOT_PROVABLE
    assert agent.evaluate_manual_move(public_state, "A2", VERDICT_CRIMINAL) == MOVE_NOT_PROVABLE
    assert agent.evaluate_manual_move(public_state, "A2", VERDICT_INNOCENT) == MOVE_NOT_PROVABLE

