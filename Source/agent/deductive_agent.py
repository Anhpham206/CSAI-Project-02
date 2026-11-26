"""
Tác tử suy luận tự động (Deductive Logic Agent) cho trò chơi Griductive.

Module này cài đặt:
- Nhiệm vụ 1: Cơ chế kiểm tra hệ quả logic (Entailment via SAT).
- Nhiệm vụ 2: Vòng lặp suy luận không đoán mò (step, solve_all),
  Deduction Trace, hàm gợi ý (hint), kiểm tra nghiệm duy nhất (check_uniqueness),
  và tổng hợp thống kê cho benchmark.

Tuân thủ đầy đủ Data Contract 1, 2, 3 của nhóm.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Protocol


VERDICT_CRIMINAL = "CRIMINAL"
VERDICT_INNOCENT = "INNOCENT"
VERDICT_UNKNOWN = "UNKNOWN"
VERDICT_INCONSISTENT = "INCONSISTENT"
VERDICT_SOLVED = "SOLVED"

MOVE_PROVABLE = "PROVABLE"
MOVE_NOT_PROVABLE = "NOT_PROVABLE"
MOVE_CONTRADICTED = "CONTRADICTED"

UNIQUENESS_UNIQUE = "UNIQUE"
UNIQUENESS_MULTIPLE = "MULTIPLE_SOLUTIONS"
UNIQUENESS_NONE = "NO_SOLUTION"


class SolverProtocol(Protocol):
    """Giao diện chuẩn của SAT Solver theo Data Contract 2."""

    def solve(
        self,
        cnf: list[list[int]],
        assumptions: list[int] | None = None,
    ) -> tuple[bool, dict[int, bool] | None, dict[str, int | float]]:
        ...


class EncoderProtocol(Protocol):
    """Giao diện chuẩn của CNFEncoder theo Data Contract 1."""

    def build_kb(self, public_state: dict[str, Any]) -> dict[str, Any]:
        ...


class GameEngineProtocol(Protocol):
    """
    Giao diện công khai tối thiểu của GameEngine theo Data Contract 3.
    DeductiveAgent chỉ được phép gọi đúng 2 phương thức này.
    """

    def get_public_state(self) -> dict[str, Any]:
        ...

    def submit_verdict(self, selected_coord: str, verdict: str) -> dict[str, Any]:
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


def _infer_board_size(
    public_state: dict[str, Any],
    num_primary_vars: int | None = None,
) -> int:
    """Suy ra kích thước lưới N từ public_state hoặc num_primary_vars."""
    state_size = public_state.get("board_size", public_state.get("size"))
    if state_size is not None:
        board_size = int(state_size)
        if board_size <= 0:
            raise ValueError(f"board_size không hợp lệ: {board_size}")
        return board_size

    if num_primary_vars is not None and num_primary_vars > 0:
        side = math.isqrt(num_primary_vars)
        if side * side == num_primary_vars:
            return side

    raise ValueError(
        "Không xác định được board_size từ public_state hoặc num_primary_vars."
    )


def _extract_hidden_coords(
    public_state: dict[str, Any],
    board_size: int,
) -> list[str]:
    """Lấy danh sách tọa độ các ô còn úp, sắp xếp chuẩn theo thứ tự row-major."""
    raw_hidden = public_state.get("hidden_coords")
    if raw_hidden is not None:
        coords = list(raw_hidden)
    else:
        unrevealed = public_state.get("unrevealed_cells")
        if unrevealed is not None:
            coords = list(unrevealed)
            return sorted(coords, key=lambda c: coord_to_var(c, board_size))

        revealed = public_state.get("revealed_cells", {})
        if isinstance(revealed, list):
            revealed_coords = set(revealed)
        elif isinstance(revealed, dict):
            revealed_coords = set(revealed)
        else:
            raise TypeError("revealed_cells phải là dict hoặc list tọa độ.")
        all_coords = [
            var_to_coord(var_id, board_size)
            for var_id in range(1, board_size * board_size + 1)
        ]
        coords = [c for c in all_coords if c not in revealed_coords]

    return sorted(coords, key=lambda c: coord_to_var(c, board_size))


def _extract_active_clue_ids(
    public_state: dict[str, Any],
    board_size: int,
) -> list[str]:
    """Lấy danh sách tọa độ các ô đã lật đang có manh mối hoạt động (row-major)."""
    if "active_clue_ids" in public_state and public_state["active_clue_ids"] is not None:
        return sorted(
            list(public_state["active_clue_ids"]),
            key=lambda c: coord_to_var(c, board_size),
        )

    revealed_clues = public_state.get("revealed_clues")
    if revealed_clues is not None:
        active = [
            entry["owner_coord"]
            for entry in revealed_clues
            if isinstance(entry, dict)
            and entry.get("clue") is not None
            and isinstance(entry.get("owner_coord"), str)
        ]
        return sorted(active, key=lambda c: coord_to_var(c, board_size))

    revealed = public_state.get("revealed_cells", {})
    if isinstance(revealed, list):
        cells = public_state.get("cells", {})
        if not isinstance(cells, dict):
            raise TypeError("cells phải là dict khi revealed_cells là list.")
        active = [
            coord
            for coord in revealed
            if isinstance(cells.get(coord), dict)
            and cells[coord].get("clue") is not None
        ]
        return sorted(active, key=lambda c: coord_to_var(c, board_size))
    if not isinstance(revealed, dict):
        raise TypeError("revealed_cells phải là dict hoặc list tọa độ.")

    active = [
        coord
        for coord, cell_info in revealed.items()
        if isinstance(cell_info, dict) and cell_info.get("clue") is not None
    ]
    return sorted(active, key=lambda c: coord_to_var(c, board_size))


class DeductiveAgent:
    """
    Tác tử suy luận logic không đoán mò (Deductive Logic Agent).

    Chỉ tiếp nhận thông tin công khai (`public_state`) thông qua `EncoderProtocol`
    và `GameEngineProtocol`, tuyệt đối không đọc đáp án ẩn.
    """

    def __init__(
        self,
        solver: SolverProtocol | None = None,
        encoder: EncoderProtocol | None = None,
        solver_factory: Callable[[int], SolverProtocol] | None = None,
    ) -> None:
        self.solver = solver
        self.encoder = encoder
        self.solver_factory = solver_factory
        self.trace_history: list[dict[str, Any]] = []

    def reset_trace(self) -> None:
        """Xóa lịch sử suy luận để bắt đầu một màn chơi mới."""
        self.trace_history = []

    def reset(self) -> None:
        """Tương thích giao diện reset mà GameEngine và Web GUI sử dụng."""
        self.reset_trace()

    def _resolve_encoder(
        self,
        encoder: EncoderProtocol | None = None,
    ) -> EncoderProtocol:
        active_encoder = encoder if encoder is not None else self.encoder
        if active_encoder is None:
            raise ValueError("Chưa cung cấp CNFEncoder cho DeductiveAgent.")
        return active_encoder

    def _resolve_solver(
        self,
        total_vars: int,
        solver: SolverProtocol | None = None,
    ) -> SolverProtocol:
        if solver is not None:
            return solver
        if self.solver_factory is not None:
            return self.solver_factory(total_vars)
        if self.solver is not None:
            return self.solver
        raise ValueError(
            "Chưa cung cấp SAT solver hoặc solver_factory cho DeductiveAgent."
        )

    def check_cell_entailment(
        self,
        clauses: list[list[int]],
        var_id: int,
        target_coord: str | None = None,
        solver: SolverProtocol | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Kiểm tra hệ quả logic cho một ô cụ thể bằng solver của Agent."""
        active_solver = self._resolve_solver(total_vars=var_id, solver=solver)
        return check_entailment(
            clauses=clauses,
            var_id=var_id,
            solver=active_solver,
            target_coord=target_coord,
        )

    def check_uniqueness(
        self,
        kb_data: dict[str, Any],
        solver: SolverProtocol | None = None,
    ) -> dict[str, Any]:
        """
        Kiểm tra tính duy nhất của nghiệm toàn màn chơi bằng blocking clause.

        Lưu ý quan trọng: Blocking clause CHỈ chứa các biến nguyên thủy (1..N^2),
        tuyệt đối không đưa biến phụ trợ (> N^2) vào để tránh báo sai nhiều nghiệm.
        """
        clauses: list[list[int]] = kb_data["clauses"]
        num_primary_vars: int = int(kb_data["num_primary_vars"])
        num_aux_vars: int = int(kb_data.get("num_aux_vars", 0))
        if num_primary_vars <= 0:
            raise ValueError(
                f"num_primary_vars phải > 0, nhận được {num_primary_vars}"
            )

        total_vars = num_primary_vars + num_aux_vars
        active_solver = self._resolve_solver(total_vars=total_vars, solver=solver)

        # Lần gọi 1: tìm nghiệm đầu tiên M1
        is_sat, model_1, stats_1 = active_solver.solve(clauses, assumptions=None)
        if not is_sat or model_1 is None:
            return {
                "status": UNIQUENESS_NONE,
                "is_unique": False,
                "model_1": None,
                "model_2": None,
                "stats": [stats_1],
            }

        # Tạo blocking clause chỉ trên tập biến nguyên thủy 1..num_primary_vars
        vars_in_clauses = {abs(lit) for clause in clauses for lit in clause}
        completed_model_1 = dict(model_1)
        blocking_clause: list[int] = []
        for var_id in range(1, num_primary_vars + 1):
            if var_id not in completed_model_1:
                if var_id in vars_in_clauses:
                    raise KeyError(
                        f"Nghiệm model_1 thiếu giá trị cho biến nguyên thủy {var_id}."
                    )
                # Biến tự do không xuất hiện trong CNF (vd khi solver dùng total_vars=0):
                # gán mặc định False cho M1 để blocking clause ép tìm nghiệm khác (+var_id).
                completed_model_1[var_id] = False
            blocking_clause.append(-var_id if completed_model_1[var_id] else var_id)

        # Lần gọi 2: không mutate `clauses` gốc, tạo danh sách mới có thêm blocking_clause
        has_second, model_2, stats_2 = active_solver.solve(
            clauses + [blocking_clause],
            assumptions=None,
        )

        if not has_second:
            return {
                "status": UNIQUENESS_UNIQUE,
                "is_unique": True,
                "model_1": completed_model_1,
                "model_2": None,
                "stats": [stats_1, stats_2],
            }

        completed_model_2 = dict(model_2) if model_2 is not None else None
        if completed_model_2 is not None:
            for var_id in range(1, num_primary_vars + 1):
                completed_model_2.setdefault(var_id, False)

        return {
            "status": UNIQUENESS_MULTIPLE,
            "is_unique": False,
            "model_1": completed_model_1,
            "model_2": completed_model_2,
            "stats": [stats_1, stats_2],
        }

    def hint(
        self,
        public_state: dict[str, Any],
        encoder: EncoderProtocol | None = None,
        solver: SolverProtocol | None = None,
    ) -> dict[str, Any] | None:
        """
        Tìm nước đi suy luận chắc chắn đầu tiên theo thứ tự row-major order.

        Chỉ nhận `public_state`, tuyệt đối không chạm vào `game_engine`
        và không làm thay đổi trạng thái ván cờ.
        """
        active_encoder = self._resolve_encoder(encoder)
        kb_data = active_encoder.build_kb(public_state)
        clauses: list[list[int]] = kb_data["clauses"]
        num_primary_vars = int(kb_data["num_primary_vars"])
        num_aux_vars = int(kb_data.get("num_aux_vars", 0))

        board_size = _infer_board_size(public_state, num_primary_vars)
        active_clue_ids = _extract_active_clue_ids(public_state, board_size)
        hidden_coords = _extract_hidden_coords(public_state, board_size)

        active_solver = self._resolve_solver(
            total_vars=num_primary_vars + num_aux_vars,
            solver=solver,
        )

        # Kiểm tra tính nhất quán của KB trước khi quét từng ô
        consistent, _, _ = is_kb_consistent(clauses, active_solver)
        if not consistent:
            return {
                "target_coord": None,
                "verdict": VERDICT_INCONSISTENT,
                "active_clue_ids": active_clue_ids,
            }

        for coord in hidden_coords:
            var_id = coord_to_var(coord, board_size)
            verdict, _ = check_entailment(
                clauses=clauses,
                var_id=var_id,
                solver=active_solver,
                target_coord=coord,
            )
            if verdict in (VERDICT_CRIMINAL, VERDICT_INNOCENT):
                return {
                    "target_coord": coord,
                    "verdict": verdict,
                    "active_clue_ids": active_clue_ids,
                }
            if verdict == VERDICT_INCONSISTENT:
                return {
                    "target_coord": None,
                    "verdict": VERDICT_INCONSISTENT,
                    "active_clue_ids": active_clue_ids,
                }

        return None

    def evaluate_manual_move(
        self,
        public_state: dict[str, Any],
        target_coord: str,
        proposed_verdict: str,
        encoder: EncoderProtocol | None = None,
        solver: SolverProtocol | None = None,
    ) -> str:
        """
        Kiểm tra phán đoán thủ công của người chơi dựa hoàn toàn vào KB công khai.

        Trả về:
          - PROVABLE: KB chứng minh được phán đoán này.
          - CONTRADICTED: KB chứng minh điều ngược lại.
          - NOT_PROVABLE: Chưa đủ chứng cứ (cả 2 khả năng đều SAT).
          - INCONSISTENT: KB hiện tại đã mâu thuẫn.
        """
        normalized = proposed_verdict.upper()
        if normalized not in (VERDICT_CRIMINAL, VERDICT_INNOCENT):
            raise ValueError(
                f"proposed_verdict phải là CRIMINAL hoặc INNOCENT, nhận được {proposed_verdict!r}"
            )

        active_encoder = self._resolve_encoder(encoder)
        kb_data = active_encoder.build_kb(public_state)
        clauses: list[list[int]] = kb_data["clauses"]
        num_primary_vars = int(kb_data["num_primary_vars"])
        num_aux_vars = int(kb_data.get("num_aux_vars", 0))
        board_size = _infer_board_size(public_state, num_primary_vars)

        active_solver = self._resolve_solver(
            total_vars=num_primary_vars + num_aux_vars,
            solver=solver,
        )

        consistent, _, _ = is_kb_consistent(clauses, active_solver)
        if not consistent:
            return VERDICT_INCONSISTENT

        var_id = coord_to_var(target_coord, board_size)
        entailed_verdict, _ = check_entailment(
            clauses=clauses,
            var_id=var_id,
            solver=active_solver,
            target_coord=target_coord,
        )

        if entailed_verdict == VERDICT_INCONSISTENT:
            return VERDICT_INCONSISTENT
        if entailed_verdict == VERDICT_UNKNOWN:
            return MOVE_NOT_PROVABLE
        if entailed_verdict == normalized:
            return MOVE_PROVABLE
        return MOVE_CONTRADICTED

    def step(
        self,
        game_engine: GameEngineProtocol,
        encoder: EncoderProtocol | None = None,
        solver: SolverProtocol | None = None,
    ) -> dict[str, Any]:
        """
        Thực hiện đúng 1 bước suy luận không đoán mò theo Data Contract 3.

        Quy trình:
          1. Lấy `public_state` từ `game_engine.get_public_state()`.
          2. Gọi `encoder.build_kb(public_state)`.
          3. Kiểm tra nhất quán KB (`solver.solve(clauses)`).
          4. Quét các ô còn úp theo thứ tự cố định row-major; dừng ngay tại ô đầu tiên
             chứng minh được (`CRIMINAL` hoặc `INNOCENT`).
          5. Gọi `game_engine.submit_verdict(selected_coord, verdict)` để lật thẻ và
             nhận `revealed_clue`.
          6. Lưu bản ghi vào `self.trace_history` và trả về.
        """
        active_encoder = self._resolve_encoder(encoder)
        step_num = len(self.trace_history) + 1

        public_state = game_engine.get_public_state()
        kb_data = active_encoder.build_kb(public_state)
        clauses: list[list[int]] = kb_data["clauses"]
        num_primary_vars = int(kb_data["num_primary_vars"])
        num_aux_vars = int(kb_data.get("num_aux_vars", 0))

        board_size = _infer_board_size(public_state, num_primary_vars)
        active_clue_ids = _extract_active_clue_ids(public_state, board_size)
        hidden_coords = _extract_hidden_coords(public_state, board_size)

        active_solver = self._resolve_solver(
            total_vars=num_primary_vars + num_aux_vars,
            solver=solver,
        )

        # Kiểm tra tính nhất quán của KB ở đầu bước
        consistent, _, stats_kb = is_kb_consistent(clauses, active_solver)
        if not consistent:
            record = {
                "step": step_num,
                "active_clue_ids": active_clue_ids,
                "sat_queries": [
                    {
                        "target_coord": None,
                        "assumed_verdict": "KB_CONSISTENCY",
                        "result": "UNSAT",
                        "stats": stats_kb,
                    }
                ],
                "selected_coord": None,
                "verdict": VERDICT_INCONSISTENT,
                "revealed_clue": None,
            }
            self.trace_history.append(record)
            return record

        # Nếu không còn ô úp nào -> bàn cờ đã giải xong
        if not hidden_coords:
            return {
                "step": step_num,
                "active_clue_ids": active_clue_ids,
                "sat_queries": [],
                "selected_coord": None,
                "verdict": VERDICT_SOLVED,
                "revealed_clue": None,
            }

        sat_queries: list[dict[str, Any]] = []
        selected_coord: str | None = None
        selected_verdict: str = VERDICT_UNKNOWN

        for coord in hidden_coords:
            var_id = coord_to_var(coord, board_size)
            verdict, cell_queries = check_entailment(
                clauses=clauses,
                var_id=var_id,
                solver=active_solver,
                target_coord=coord,
            )
            sat_queries.extend(cell_queries)

            if verdict == VERDICT_INCONSISTENT:
                selected_coord = None
                selected_verdict = VERDICT_INCONSISTENT
                break

            if verdict in (VERDICT_CRIMINAL, VERDICT_INNOCENT):
                selected_coord = coord
                selected_verdict = verdict
                break

        if selected_coord is None:
            record = {
                "step": step_num,
                "active_clue_ids": active_clue_ids,
                "sat_queries": sat_queries,
                "selected_coord": None,
                "verdict": selected_verdict,
                "revealed_clue": None,
            }
            self.trace_history.append(record)
            return record

        submit_result = game_engine.submit_verdict(selected_coord, selected_verdict)
        revealed_clue = (
            submit_result.get("revealed_clue")
            if isinstance(submit_result, dict)
            else None
        )

        record = {
            "step": step_num,
            "active_clue_ids": active_clue_ids,
            "sat_queries": sat_queries,
            "selected_coord": selected_coord,
            "verdict": selected_verdict,
            "revealed_clue": revealed_clue,
        }
        self.trace_history.append(record)
        return record

    def solve_all(
        self,
        game_engine: GameEngineProtocol,
        encoder: EncoderProtocol | None = None,
        solver: SolverProtocol | None = None,
    ) -> list[dict[str, Any]]:
        """
        Gọi lặp `step(game_engine)` cho đến khi giải hết các ô úp (Solved State)
        hoặc gặp trạng thái dừng (`UNKNOWN` / `INCONSISTENT`).
        """
        self.reset_trace()
        active_encoder = self._resolve_encoder(encoder)

        while True:
            public_state = game_engine.get_public_state()
            kb_preview = active_encoder.build_kb(public_state)
            board_size = _infer_board_size(
                public_state,
                int(kb_preview["num_primary_vars"]),
            )
            hidden_coords = _extract_hidden_coords(public_state, board_size)
            if not hidden_coords:
                break

            record = self.step(
                game_engine=game_engine,
                encoder=active_encoder,
                solver=solver,
            )
            if record["verdict"] in (
                VERDICT_UNKNOWN,
                VERDICT_INCONSISTENT,
                VERDICT_SOLVED,
            ):
                break

        return list(self.trace_history)

    def format_trace(self, trace: list[dict[str, Any]] | None = None) -> str:
        """Định dạng Deduction Trace thành chuỗi dễ đọc cho console và báo cáo."""
        records = self.trace_history if trace is None else trace
        if not records:
            return "(Deduction Trace rỗng)"

        lines: list[str] = []
        for rec in records:
            step = rec["step"]
            active_clues = ", ".join(rec["active_clue_ids"]) or "(không có)"
            queries = rec["sat_queries"]
            unsat_proofs = [
                f"{q['target_coord']}!={q['assumed_verdict']}"
                for q in queries
                if q["result"] == "UNSAT" and q["target_coord"] is not None
            ]
            proof_str = ", ".join(unsat_proofs) if unsat_proofs else "không có"
            selected = rec["selected_coord"] or "-"
            verdict = rec["verdict"]
            revealed = rec["revealed_clue"]

            lines.append(
                f"Step {step}: Active=[{active_clues}] | "
                f"SAT queries={len(queries)} (UNSAT: {proof_str}) | "
                f"Decision={selected} -> {verdict} | "
                f"Revealed={revealed}"
            )
        return "\n".join(lines)

    def get_summary_stats(
        self,
        trace: list[dict[str, Any]] | None = None,
    ) -> dict[str, int | float]:
        """Tổng hợp chỉ số thực nghiệm từ Deduction Trace cho module benchmark (TV5)."""
        records = self.trace_history if trace is None else trace
        deduction_steps = 0
        sat_calls = 0
        decisions = 0
        propagations = 0
        backtracks = 0
        runtime = 0.0

        for rec in records:
            if rec["selected_coord"] is not None and rec["verdict"] in (
                VERDICT_CRIMINAL,
                VERDICT_INNOCENT,
            ):
                deduction_steps += 1

            for query in rec["sat_queries"]:
                sat_calls += 1
                stats = query.get("stats", {})
                decisions += int(stats.get("decisions", 0))
                propagations += int(stats.get("propagations", 0))
                backtracks += int(stats.get("backtracks", 0))
                runtime += float(stats.get("runtime", 0.0))

        return {
            "total_steps": len(records),
            "deduction_steps": deduction_steps,
            "sat_calls": sat_calls,
            "decisions": decisions,
            "propagations": propagations,
            "backtracks": backtracks,
            "runtime": runtime,
        }
