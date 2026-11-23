"""
Tác tử suy luận tự động (Deductive Logic Agent) cho trò chơi Griductive.

Module này cài đặt cơ chế kiểm tra hệ quả logic (Entailment via SAT)
theo đúng Data Contract 1, 2, 3 của nhóm.
"""

from __future__ import annotations

from typing import Any, Protocol


VERDICT_CRIMINAL = "CRIMINAL"
VERDICT_INNOCENT = "INNOCENT"
VERDICT_UNKNOWN = "UNKNOWN"
VERDICT_INCONSISTENT = "INCONSISTENT"


class SolverProtocol(Protocol):
    """Giao diện chuẩn của SAT Solver theo Data Contract 2."""

    def solve(
        self,
        cnf: list[list[int]],
        assumptions: list[int] | None = None,
    ) -> tuple[bool, dict[int, bool] | None, dict[str, int | float]]:
        ...


def coord_to_var(coord: str, board_size: int) -> int:
    """
    Chuyển tọa độ ô (vd: 'A1', 'C2') sang mã biến nguyên thủy (1..N^2)
    theo thứ tự duyệt từng hàng từ trái sang phải (row-major order).

    Ví dụ lưới 3x3: A1->1, B1->2, C1->3, A2->4, ..., C3->9.
    """
    if board_size <= 0:
        raise ValueError(f"board_size phải > 0, nhận được {board_size}")
    if len(coord) < 2:
        raise ValueError(f"Tọa độ không hợp lệ: {coord!r}")

    col_char = coord[0].upper()
    row_str = coord[1:]
    if not ("A" <= col_char <= "Z") or not row_str.isdigit():
        raise ValueError(f"Tọa độ không hợp lệ: {coord!r}")

    col_idx = ord(col_char) - ord("A")
    row_idx = int(row_str) - 1
    if not (0 <= col_idx < board_size and 0 <= row_idx < board_size):
        raise ValueError(
            f"Tọa độ {coord!r} nằm ngoài lưới {board_size}x{board_size}"
        )

    return row_idx * board_size + col_idx + 1


def var_to_coord(var_id: int, board_size: int) -> str:
    """Chuyển mã biến nguyên thủy (1..N^2) sang tọa độ ô (vd: 1 -> 'A1')."""
    if board_size <= 0:
        raise ValueError(f"board_size phải > 0, nhận được {board_size}")
    if not (1 <= var_id <= board_size * board_size):
        raise ValueError(
            f"var_id {var_id} nằm ngoài phạm vi 1..{board_size * board_size}"
        )

    zero_based = var_id - 1
    row_idx, col_idx = divmod(zero_based, board_size)
    return f"{chr(ord('A') + col_idx)}{row_idx + 1}"


def is_kb_consistent(
    clauses: list[list[int]],
    solver: SolverProtocol,
) -> tuple[bool, dict[int, bool] | None, dict[str, int | float]]:
    """Kiểm tra tính nhất quán (SAT/UNSAT) của bản thân cơ sở tri thức KB."""
    return solver.solve(clauses, assumptions=None)


def check_entailment(
    clauses: list[list[int]],
    var_id: int,
    solver: SolverProtocol,
    target_coord: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Kiểm tra hệ quả logic cho biến C_i (var_id) từ cơ sở tri thức KB (clauses).

    Thực hiện 2 truy vấn SAT bằng phản chứng (Refutation via SAT):
      1. KB AND NOT C_i (assumptions=[-var_id]) -> kiểm tra khả năng INNOCENT.
      2. KB AND C_i     (assumptions=[+var_id]) -> kiểm tra khả năng CRIMINAL.

    Returns:
        (verdict, sat_queries):
          - verdict thuộc {"CRIMINAL", "INNOCENT", "UNKNOWN", "INCONSISTENT"}.
          - sat_queries là danh sách các truy vấn theo chuẩn Data Contract 3.
    """
    if var_id <= 0:
        raise ValueError(f"var_id phải là số nguyên dương (>= 1), nhận được {var_id}")

    coord_label = target_coord if target_coord is not None else str(var_id)
    sat_queries: list[dict[str, Any]] = []

    # Truy vấn 1: Giả sử ô là INNOCENT (-var_id)
    sat_if_innocent, _, stats_innocent = solver.solve(clauses, assumptions=[-var_id])
    sat_queries.append(
        {
            "target_coord": coord_label,
            "assumed_verdict": VERDICT_INNOCENT,
            "result": "SAT" if sat_if_innocent else "UNSAT",
            "stats": stats_innocent,
        }
    )

    # Truy vấn 2: Giả sử ô là CRIMINAL (+var_id)
    sat_if_criminal, _, stats_criminal = solver.solve(clauses, assumptions=[var_id])
    sat_queries.append(
        {
            "target_coord": coord_label,
            "assumed_verdict": VERDICT_CRIMINAL,
            "result": "SAT" if sat_if_criminal else "UNSAT",
            "stats": stats_criminal,
        }
    )

    if not sat_if_innocent and not sat_if_criminal:
        verdict = VERDICT_INCONSISTENT
    elif not sat_if_innocent and sat_if_criminal:
        verdict = VERDICT_CRIMINAL
    elif sat_if_innocent and not sat_if_criminal:
        verdict = VERDICT_INNOCENT
    else:
        verdict = VERDICT_UNKNOWN

    return verdict, sat_queries


class DeductiveAgent:
    """
    Tác tử suy luận logic không đoán mò (Deductive Logic Agent).

    Giai đoạn 1 (Nhiệm vụ 1): cung cấp hàm kiểm tra hệ quả logic (Entailment).
    Các hàm vòng lặp suy luận (step, solve_all), hint và uniqueness check
    sẽ được bổ sung ở Nhiệm vụ 2.
    """

    def __init__(self, solver: SolverProtocol | None = None) -> None:
        self.solver = solver
        self.trace_history: list[dict[str, Any]] = []

    def check_cell_entailment(
        self,
        clauses: list[list[int]],
        var_id: int,
        target_coord: str | None = None,
        solver: SolverProtocol | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Kiểm tra hệ quả logic cho một ô cụ thể bằng solver của Agent."""
        active_solver = solver if solver is not None else self.solver
        if active_solver is None:
            raise ValueError("Chưa cung cấp SAT solver cho DeductiveAgent.")
        return check_entailment(
            clauses=clauses,
            var_id=var_id,
            solver=active_solver,
            target_coord=target_coord,
        )

