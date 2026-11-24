"""
Bộ giải suy luận dự phòng độc lập (FallbackLogicAdapter) cho trò chơi Griductive.

Thiết kế tuân thủ nghiêm ngặt kiến trúc tách biệt 2 lớp:
  - CHỈ nhận `public_state: dict` (trạng thái công khai) làm đầu vào.
  - TUYỆT ĐỐI KHÔNG truy cập thuộc tính ẩn (`_board`, `hidden_status`, manh mối chưa lật)
    của GameEngine.
  - Sử dụng bộ giải quay lui kết hợp lan truyền ràng buộc (constraint-propagating
    backtracking solver) thuần Python trên N^2 biến mệnh đề, hỗ trợ 6 mẫu manh mối cốt lõi
    (FACT, SAME, DIFFERENT, EXACTLY, AT_LEAST, AT_MOST) cùng các mẫu mở rộng
    (PARITY, COMPARE, COMPOUND, CONNECTIVITY).
  - Xuất kết quả đúng chuẩn Data Contract 2 & Data Contract 3 để GUI và GameEngine
    vận hành hoàn chỉnh trước khi ghép nối với CNFEncoder (TV2), DPLLSolver (TV3)
    và DeductiveAgent (TV4).
"""

from __future__ import annotations

from collections import deque
import time
from typing import Any

from .board import (
    CRIMINAL,
    INCONSISTENT,
    INNOCENT,
    UNKNOWN,
    coord_to_row_col,
    coord_to_var,
    iter_coords_row_major,
    normalize_coord,
    resolve_clue_cells,
    resolve_region,
    var_to_coord,
)


class _Constraint:
    """Biểu diễn nội bộ gọn nhẹ cho một ràng buộc logic trên tập biến 1..N^2."""

    __slots__ = ("kind", "data")

    def __init__(self, kind: str, data: dict[str, Any]) -> None:
        self.kind = kind
        self.data = data


class FallbackLogicAdapter:
    """
    Tác tử suy luận thuần Python dự phòng tuân theo giao diện DeductiveAgent (Data Contract 3).

    Hoạt động độc lập chỉ dựa trên `public_state` từ GameEngine.
    """

    def __init__(self) -> None:
        self.step_counter: int = 0
        self.trace_history: list[dict[str, Any]] = []

    def reset(self) -> None:
        """Đặt lại bộ đếm bước và lịch sử suy diễn."""
        self.step_counter = 0
        self.trace_history = []

    # ------------------------------------------------------------------
    # Biên dịch public_state -> danh sách ràng buộc & lời giải thuần Python
    # ------------------------------------------------------------------

    def _compile_clue(self, clue: dict[str, Any], size: int) -> list[_Constraint]:
        if not isinstance(clue, dict):
            raise ValueError(f"Clue không hợp lệ: {clue!r}")

        clue_type = str(clue.get("type", "")).strip().upper()

        if clue_type == "FACT":
            target = clue.get("target")
            if not isinstance(target, str):
                cells = resolve_clue_cells(clue, size)
                if len(cells) != 1:
                    raise ValueError(f"Clue FACT cần đúng 1 target: {clue!r}")
                target = cells[0]
            status = str(clue.get("status", "")).strip().upper()
            if status not in (CRIMINAL, INNOCENT):
                raise ValueError(f"Trạng thái FACT không hợp lệ: {status!r}")
            var_id = coord_to_var(target, size)
            return [_Constraint("FACT", {"var": var_id, "value": status == CRIMINAL})]

        if clue_type == "SAME":
            targets = clue.get("targets")
            if not isinstance(targets, list) or len(targets) < 2:
                targets = resolve_clue_cells(clue, size)
            if len(targets) < 2:
                raise ValueError(f"Clue SAME cần ít nhất 2 target: {clue!r}")
            vars_list = [coord_to_var(c, size) for c in targets]
            constraints: list[_Constraint] = []
            for idx in range(len(vars_list) - 1):
                constraints.append(
                    _Constraint("SAME", {"v1": vars_list[idx], "v2": vars_list[idx + 1]})
                )
            return constraints

        if clue_type == "DIFFERENT":
            targets = clue.get("targets")
            if not isinstance(targets, list) or len(targets) != 2:
                targets = resolve_clue_cells(clue, size)
            if len(targets) != 2:
                raise ValueError(f"Clue DIFFERENT cần đúng 2 target: {clue!r}")
            v1 = coord_to_var(targets[0], size)
            v2 = coord_to_var(targets[1], size)
            return [_Constraint("DIFFERENT", {"v1": v1, "v2": v2})]

        if clue_type in ("EXACTLY", "AT_LEAST", "AT_MOST"):
            if "k" not in clue or isinstance(clue["k"], bool) or not isinstance(clue["k"], int):
                raise ValueError(f"Clue {clue_type} thiếu số nguyên k: {clue!r}")
            region = clue.get("region")
            coords = (
                resolve_region(region, size)
                if isinstance(region, dict)
                else resolve_clue_cells(clue, size)
            )
            vars_list = list(dict.fromkeys(coord_to_var(c, size) for c in coords))
            return [_Constraint(clue_type, {"vars": vars_list, "k": clue["k"]})]

        if clue_type == "PARITY":
            parity = str(clue.get("parity", "")).strip().upper()
            if parity not in ("EVEN", "ODD"):
                raise ValueError(f"Giá trị PARITY không hợp lệ: {parity!r}")
            region = clue.get("region")
            coords = (
                resolve_region(region, size)
                if isinstance(region, dict)
                else resolve_clue_cells(clue, size)
            )
            vars_list = list(dict.fromkeys(coord_to_var(c, size) for c in coords))
            return [_Constraint("PARITY", {"vars": vars_list, "target_mod": 0 if parity == "EVEN" else 1})]

        if clue_type == "COMPARE":
            r1 = clue.get("region1")
            r2 = clue.get("region2")
            if not isinstance(r1, dict) or not isinstance(r2, dict):
                regions = clue.get("regions")
                if isinstance(regions, list) and len(regions) == 2:
                    r1, r2 = regions[0], regions[1]
                else:
                    raise ValueError(f"Clue COMPARE cần region1 và region2: {clue!r}")
            op_raw = str(clue.get("op", "EQ")).strip().upper()
            op_map = {
                "GT": "GT", ">": "GT",
                "LT": "LT", "<": "LT",
                "EQ": "EQ", "==": "EQ",
                "GTE": "GTE", ">=": "GTE",
                "LTE": "LTE", "<=": "LTE",
                "NEQ": "NEQ", "!=": "NEQ",
            }
            if op_raw not in op_map:
                raise ValueError(f"Toán tử COMPARE không hợp lệ: {op_raw!r}")
            v1_list = list(dict.fromkeys(coord_to_var(c, size) for c in resolve_region(r1, size)))
            v2_list = list(dict.fromkeys(coord_to_var(c, size) for c in resolve_region(r2, size)))
            return [_Constraint("COMPARE", {"vars1": v1_list, "vars2": v2_list, "op": op_map[op_raw]})]

        if clue_type == "COMPOUND":
            op = str(clue.get("op") or clue.get("operator") or "AND").strip().upper()
            subclues = clue.get("subclues") or clue.get("clues")
            if not isinstance(subclues, list) or not subclues:
                raise ValueError(f"Clue COMPOUND cần danh sách subclues không rỗng: {clue!r}")
            if op == "AND":
                merged: list[_Constraint] = []
                for sub in subclues:
                    merged.extend(self._compile_clue(sub, size))
                return merged
            if op == "OR":
                branches = [self._compile_clue(sub, size) for sub in subclues]
                return [_Constraint("OR", {"branches": branches})]
            raise ValueError(f"Toán tử COMPOUND không được hỗ trợ: {op!r}")

        if clue_type == "CONNECTIVITY":
            region = clue.get("region")
            coords = (
                resolve_region(region, size)
                if isinstance(region, dict)
                else iter_coords_row_major(size)
            )
            vars_list = list(dict.fromkeys(coord_to_var(c, size) for c in coords))
            target_status = str(clue.get("status", CRIMINAL)).strip().upper()
            if target_status not in (CRIMINAL, INNOCENT):
                raise ValueError(f"Trạng thái CONNECTIVITY không hợp lệ: {target_status!r}")
            adjacency = str(clue.get("adjacency", "ORTHOGONAL")).strip().upper()
            return [
                _Constraint(
                    "CONNECTIVITY",
                    {
                        "vars": vars_list,
                        "target_val": target_status == CRIMINAL,
                        "size": size,
                        "diagonal": adjacency in ("EIGHT", "KING", "DIAGONAL", "ALL"),
                    },
                )
            ]

        raise ValueError(f"Loại manh mối chưa được hỗ trợ bởi FallbackLogicAdapter: {clue_type!r}")

    def _build_constraints(self, public_state: dict[str, Any]) -> tuple[int, list[_Constraint], dict[int, bool]]:
        size = int(public_state["size"])
        initial_assignment: dict[int, bool] = {}
        constraints: list[_Constraint] = []

        # 1. Nạp các nhãn đã biết từ các ô đã mở (known_verdicts)
        known_verdicts = public_state.get("known_verdicts", {})
        for coord, status in known_verdicts.items():
            var_id = coord_to_var(coord, size)
            val = str(status).strip().upper() == CRIMINAL
            if var_id in initial_assignment and initial_assignment[var_id] != val:
                constraints.append(_Constraint("FALSE", {}))
            else:
                initial_assignment[var_id] = val

        # 2. Nạp toàn bộ manh mối đã lật mở (revealed_clues)
        for entry in public_state.get("revealed_clues", []):
            clue = entry.get("clue") if isinstance(entry, dict) else None
            if clue is not None:
                constraints.extend(self._compile_clue(clue, size))

        return size, constraints, initial_assignment

    @staticmethod
    def _is_connected(vars_list: list[int], assignment: dict[int, bool], target_val: bool, size: int, diagonal: bool) -> bool:
        selected = [v for v in vars_list if assignment[v] == target_val]
        if len(selected) <= 1:
            return True
        pos_map = {v: coord_to_row_col(var_to_coord(v, size), size) for v in selected}
        selected_set = set(selected)
        visited: set[int] = {selected[0]}
        queue: deque[int] = deque([selected[0]])
        while queue:
            cur = queue.popleft()
            r1, c1 = pos_map[cur]
            for nxt in selected_set - visited:
                r2, c2 = pos_map[nxt]
                dr, dc = abs(r1 - r2), abs(c1 - c2)
                is_adj = (max(dr, dc) == 1) if diagonal else (dr + dc == 1)
                if is_adj:
                    visited.add(nxt)
                    queue.append(nxt)
        return len(visited) == len(selected)

    def _propagate_single(
        self,
        constraint: _Constraint,
        assignment: dict[int, bool],
        propagated: list[tuple[int, bool]],
    ) -> bool:
        """
        Kiểm tra 1 ràng buộc trên phép gán bán phần `assignment`.
        Trả về False nếu xung đột, True nếu nhất quán (và bổ sung suy diễn bắt buộc vào `propagated`).
        """
        kind = constraint.kind
        data = constraint.data

        if kind == "FALSE":
            return False

        if kind == "FACT":
            var_id = data["var"]
            val = data["value"]
            if var_id in assignment:
                return assignment[var_id] == val
            propagated.append((var_id, val))
            return True

        if kind == "SAME":
            v1, v2 = data["v1"], data["v2"]
            in1, in2 = v1 in assignment, v2 in assignment
            if in1 and in2:
                return assignment[v1] == assignment[v2]
            if in1 and not in2:
                propagated.append((v2, assignment[v1]))
            elif in2 and not in1:
                propagated.append((v1, assignment[v2]))
            return True

        if kind == "DIFFERENT":
            v1, v2 = data["v1"], data["v2"]
            in1, in2 = v1 in assignment, v2 in assignment
            if in1 and in2:
                return assignment[v1] != assignment[v2]
            if in1 and not in2:
                propagated.append((v2, not assignment[v1]))
            elif in2 and not in1:
                propagated.append((v1, not assignment[v2]))
            return True

        if kind in ("EXACTLY", "AT_LEAST", "AT_MOST"):
            vars_list: list[int] = data["vars"]
            k: int = data["k"]
            true_count = 0
            unassigned: list[int] = []
            for v in vars_list:
                if v in assignment:
                    if assignment[v]:
                        true_count += 1
                else:
                    unassigned.append(v)
            max_true = true_count + len(unassigned)

            if kind == "EXACTLY":
                if true_count > k or max_true < k:
                    return False
                if unassigned:
                    if true_count == k:
                        for u in unassigned:
                            propagated.append((u, False))
                    elif max_true == k:
                        for u in unassigned:
                            propagated.append((u, True))
                return True

            if kind == "AT_LEAST":
                if max_true < k:
                    return False
                if unassigned and max_true == k:
                    for u in unassigned:
                        propagated.append((u, True))
                return True

            if kind == "AT_MOST":
                if true_count > k:
                    return False
                if unassigned and true_count == k:
                    for u in unassigned:
                        propagated.append((u, False))
                return True

        if kind == "PARITY":
            vars_list = data["vars"]
            target_mod: int = data["target_mod"]
            true_count = 0
            unassigned = []
            for v in vars_list:
                if v in assignment:
                    if assignment[v]:
                        true_count += 1
                else:
                    unassigned.append(v)
            if not unassigned:
                return (true_count % 2) == target_mod
            if len(unassigned) == 1:
                needed_val = (true_count % 2) != target_mod
                propagated.append((unassigned[0], needed_val))
            return True

        if kind == "COMPARE":
            vars1: list[int] = data["vars1"]
            vars2: list[int] = data["vars2"]
            op: str = data["op"]
            t1 = sum(1 for v in vars1 if assignment.get(v) is True)
            u1 = sum(1 for v in vars1 if v not in assignment)
            t2 = sum(1 for v in vars2 if assignment.get(v) is True)
            u2 = sum(1 for v in vars2 if v not in assignment)
            lo1, hi1 = t1, t1 + u1
            lo2, hi2 = t2, t2 + u2

            if op == "GT":
                return hi1 > lo2
            if op == "LT":
                return lo1 < hi2
            if op == "EQ":
                return not (hi1 < lo2 or lo1 > hi2)
            if op == "GTE":
                return hi1 >= lo2
            if op == "LTE":
                return lo1 <= hi2
            if op == "NEQ":
                if u1 == 0 and u2 == 0:
                    return lo1 != lo2
                return True

        if kind == "OR":
            branches: list[list[_Constraint]] = data["branches"]
            any_viable = False
            for branch in branches:
                branch_ok = True
                for sub_c in branch:
                    if not self._propagate_single(sub_c, assignment, []):
                        branch_ok = False
                        break
                if branch_ok:
                    any_viable = True
                    break
            return any_viable

        if kind == "CONNECTIVITY":
            vars_list = data["vars"]
            if all(v in assignment for v in vars_list):
                return self._is_connected(
                    vars_list,
                    assignment,
                    data["target_val"],
                    data["size"],
                    data["diagonal"],
                )
            return True

        raise ValueError(f"Ràng buộc nội bộ không xác định: {kind!r}")

    def _propagate_all(
        self,
        constraints: list[_Constraint],
        assignment: dict[int, bool],
        stats: dict[str, int | float],
    ) -> bool:
        """Lặp lan truyền ràng buộc cho tới điểm bất động hoặc phát hiện xung đột."""
        changed = True
        while changed:
            changed = False
            for constraint in constraints:
                inferred: list[tuple[int, bool]] = []
                if not self._propagate_single(constraint, assignment, inferred):
                    return False
                for var_id, val in inferred:
                    if var_id in assignment:
                        if assignment[var_id] != val:
                            return False
                    else:
                        assignment[var_id] = val
                        stats["propagations"] = int(stats["propagations"]) + 1
                        changed = True
        return True

    def _solve_constraints(
        self,
        total_vars: int,
        constraints: list[_Constraint],
        base_assignment: dict[int, bool],
        assumptions: list[int] | None = None,
    ) -> tuple[bool, dict[int, bool] | None, dict[str, int | float]]:
        """
        Giải tìm một phép gán thỏa mãn toàn bộ ràng buộc kèm danh sách giả định (assumptions).
        Trả về đúng định dạng Data Contract 2: (is_sat, model, stats).
        """
        start = time.perf_counter()
        stats: dict[str, int | float] = {
            "decisions": 0,
            "propagations": 0,
            "backtracks": 0,
            "runtime": 0.0,
        }

        assignment = dict(base_assignment)
        if assumptions:
            for lit in assumptions:
                var_id = abs(lit)
                val = lit > 0
                if var_id in assignment and assignment[var_id] != val:
                    stats["runtime"] = time.perf_counter() - start
                    return False, None, stats
                assignment[var_id] = val

        all_vars = list(range(1, total_vars + 1))

        def backtrack(cur_assign: dict[int, bool]) -> dict[int, bool] | None:
            if not self._propagate_all(constraints, cur_assign, stats):
                return None

            # Chọn biến chưa gán đầu tiên theo thứ tự xác định 1..N^2
            next_var: int | None = None
            for v in all_vars:
                if v not in cur_assign:
                    next_var = v
                    break

            if next_var is None:
                return cur_assign

            stats["decisions"] = int(stats["decisions"]) + 1
            for try_val in (False, True):
                branch_assign = dict(cur_assign)
                branch_assign[next_var] = try_val
                result = backtrack(branch_assign)
                if result is not None:
                    return result
                stats["backtracks"] = int(stats["backtracks"]) + 1

            return None

        model = backtrack(assignment)
        stats["runtime"] = time.perf_counter() - start
        return (model is not None), model, stats

    # ------------------------------------------------------------------
    # API công khai chuẩn Data Contract 3
    # ------------------------------------------------------------------

    @staticmethod
    def _active_clue_ids(public_state: dict[str, Any]) -> list[str]:
        return [
            entry["owner_coord"]
            for entry in public_state.get("revealed_clues", [])
            if isinstance(entry, dict) and entry.get("clue") is not None
        ]

    def is_consistent(
        self, public_state: dict[str, Any]
    ) -> tuple[bool, dict[int, bool] | None, dict[str, int | float]]:
        """Kiểm tra tính nhất quán của cơ sở tri thức công khai KB_t hiện tại."""
        size, constraints, base_assignment = self._build_constraints(public_state)
        return self._solve_constraints(size * size, constraints, base_assignment, assumptions=None)

    def check_entailment(
        self, public_state: dict[str, Any], target_coord: str
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        Kiểm tra hệ quả logic (Entailment via SAT) cho ô `target_coord` chỉ từ `public_state`.

        Returns:
            (verdict, sat_queries):
              - verdict in {"CRIMINAL", "INNOCENT", "UNKNOWN", "INCONSISTENT"}
              - sat_queries theo chuẩn Data Contract 3.
        """
        size, constraints, base_assignment = self._build_constraints(public_state)
        norm_coord = normalize_coord(target_coord, size)
        var_id = coord_to_var(norm_coord, size)
        total_vars = size * size

        sat_queries: list[dict[str, Any]] = []

        # Truy vấn 1: giả sử INNOCENT (-var_id)
        sat_if_innocent, _, stats_innocent = self._solve_constraints(
            total_vars, constraints, base_assignment, assumptions=[-var_id]
        )
        sat_queries.append(
            {
                "target_coord": norm_coord,
                "assumed_verdict": INNOCENT,
                "result": "SAT" if sat_if_innocent else "UNSAT",
                "stats": stats_innocent,
            }
        )

        # Truy vấn 2: giả sử CRIMINAL (+var_id)
        sat_if_criminal, _, stats_criminal = self._solve_constraints(
            total_vars, constraints, base_assignment, assumptions=[var_id]
        )
        sat_queries.append(
            {
                "target_coord": norm_coord,
                "assumed_verdict": CRIMINAL,
                "result": "SAT" if sat_if_criminal else "UNSAT",
                "stats": stats_criminal,
            }
        )

        if not sat_if_innocent and not sat_if_criminal:
            verdict = INCONSISTENT
        elif not sat_if_innocent and sat_if_criminal:
            verdict = CRIMINAL
        elif sat_if_innocent and not sat_if_criminal:
            verdict = INNOCENT
        else:
            verdict = UNKNOWN

        return verdict, sat_queries

    def hint(self, public_state: dict[str, Any]) -> dict[str, Any] | None:
        """
        Tìm 1 nước đi chắc chắn tiếp theo (duyệt row-major) mà không sửa trạng thái trò chơi.

        Returns:
            - {"target_coord": coord, "verdict": "CRIMINAL"|"INNOCENT", "active_clue_ids": [...]}
              khi tìm thấy ô bị ép buộc đầu tiên.
            - {"target_coord": None, "verdict": "INCONSISTENT", "active_clue_ids": [...]}
              nếu bản thân KB_t vô nghiệm (UNSAT).
            - None nếu không có ô úp nào bị ép buộc (UNKNOWN hoặc bàn cờ đã giải xong).
        """
        size = int(public_state["size"])
        active_clue_ids = self._active_clue_ids(public_state)

        is_sat, _, _ = self.is_consistent(public_state)
        if not is_sat:
            return {
                "target_coord": None,
                "verdict": INCONSISTENT,
                "active_clue_ids": active_clue_ids,
            }

        unrevealed = sorted(
            public_state.get("unrevealed_cells", []),
            key=lambda c: coord_to_var(c, size),
        )
        for coord in unrevealed:
            verdict, _ = self.check_entailment(public_state, coord)
            if verdict == INCONSISTENT:
                return {
                    "target_coord": None,
                    "verdict": INCONSISTENT,
                    "active_clue_ids": active_clue_ids,
                }
            if verdict in (CRIMINAL, INNOCENT):
                return {
                    "target_coord": coord,
                    "verdict": verdict,
                    "active_clue_ids": active_clue_ids,
                }

        return None

    def step(self, game_engine: Any) -> dict[str, Any]:
        """
        Thực hiện 1 bước suy diễn theo Data Contract 3:
          1. Lấy public_state = game_engine.get_public_state().
          2. Kiểm tra tính nhất quán KB_t và quét các ô úp theo thứ tự row-major.
          3. Nếu có ô bị ép buộc -> gọi game_engine.submit_verdict(coord, verdict).
          4. Lưu và trả về bản ghi Deduction Trace.
        """
        public_state = game_engine.get_public_state()
        size = int(public_state["size"])
        active_clue_ids = self._active_clue_ids(public_state)
        self.step_counter += 1
        sat_queries: list[dict[str, Any]] = []

        # Bước kiểm tra nhất quán bản thân KB_t
        is_sat, _, stats_kb = self.is_consistent(public_state)
        if not is_sat:
            sat_queries.append(
                {
                    "target_coord": "KB",
                    "assumed_verdict": "CONSISTENT",
                    "result": "UNSAT",
                    "stats": stats_kb,
                }
            )
            trace = {
                "step": self.step_counter,
                "active_clue_ids": active_clue_ids,
                "sat_queries": sat_queries,
                "selected_coord": None,
                "verdict": INCONSISTENT,
                "revealed_clue": None,
            }
            self.trace_history.append(trace)
            return trace

        unrevealed = sorted(
            public_state.get("unrevealed_cells", []),
            key=lambda c: coord_to_var(c, size),
        )

        for coord in unrevealed:
            verdict, cell_queries = self.check_entailment(public_state, coord)
            sat_queries.extend(cell_queries)

            if verdict == INCONSISTENT:
                trace = {
                    "step": self.step_counter,
                    "active_clue_ids": active_clue_ids,
                    "sat_queries": sat_queries,
                    "selected_coord": None,
                    "verdict": INCONSISTENT,
                    "revealed_clue": None,
                }
                self.trace_history.append(trace)
                return trace

            if verdict in (CRIMINAL, INNOCENT):
                result = game_engine.submit_verdict(coord, verdict)
                if result.get("accepted"):
                    trace = {
                        "step": self.step_counter,
                        "active_clue_ids": active_clue_ids,
                        "sat_queries": sat_queries,
                        "selected_coord": coord,
                        "verdict": verdict,
                        "revealed_clue": result.get("revealed_clue"),
                    }
                else:
                    trace = {
                        "step": self.step_counter,
                        "active_clue_ids": active_clue_ids,
                        "sat_queries": sat_queries,
                        "selected_coord": None,
                        "verdict": str(result.get("code", INCONSISTENT)),
                        "revealed_clue": None,
                    }
                self.trace_history.append(trace)
                return trace

        trace = {
            "step": self.step_counter,
            "active_clue_ids": active_clue_ids,
            "sat_queries": sat_queries,
            "selected_coord": None,
            "verdict": UNKNOWN,
            "revealed_clue": None,
        }
        self.trace_history.append(trace)
        return trace

    def solve_all(self, game_engine: Any) -> list[dict[str, Any]]:
        """Lặp gọi step(game_engine) cho tới khi bàn cờ được giải xong hoặc rơi vào UNKNOWN/INCONSISTENT."""
        traces: list[dict[str, Any]] = []
        while not game_engine.is_solved():
            trace = self.step(game_engine)
            traces.append(trace)
            if trace["verdict"] in (UNKNOWN, INCONSISTENT) or trace["selected_coord"] is None:
                break
        return traces
