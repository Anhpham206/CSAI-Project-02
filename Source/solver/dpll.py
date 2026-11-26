"""
Bộ giải SAT bằng thuật toán DPLL (Davis-Putnam-Logemann-Loveland).
"""

from __future__ import annotations

import sys
import time


class DPLLSolver:
    """
    Cài đặt thuật toán DPLL thuần Python:
    - Lan truyền đơn vị
    - Phát hiện xung đột
    - Chọn biến phân nhánh theo thứ tự tăng dần
    - Quay lui có hỗ trợ assumptions và thống kê số liệu
    """

    def __init__(self, total_vars: int = 0) -> None:
        if total_vars < 0:
            raise ValueError(f"total_vars phải >= 0, nhưng nhận được {total_vars}")
        self.total_vars = total_vars

    def solve(
        self,
        cnf: list[list[int]],
        assumptions: list[int] | None = None,
    ) -> tuple[bool, dict[int, bool] | None, dict[str, int | float]]:
        """
        Giải công thức CNF kèm danh sách giả định nếu có.
        Không làm thay đổi list cnf truyền vào.
        Trả về (is_sat, model, stats).
        """
        start_time = time.perf_counter()

        stats: dict[str, int | float] = {
            "decisions": 0,
            "propagations": 0,
            "backtracks": 0,
            "runtime": 0.0,
        }

        clauses, max_var, has_empty_clause = self._preprocess_cnf(cnf)
        if assumptions:
            for lit in assumptions:
                if lit == 0:
                    raise ValueError("Literal trong assumptions không được bằng 0.")
                max_var = max(max_var, abs(lit))

        # Nếu CNF có sẵn mệnh đề rỗng [] thì chắc chắn UNSAT ngay ở gốc (chưa rẽ nhánh)
        if has_empty_clause:
            stats["runtime"] = time.perf_counter() - start_time
            return False, None, stats

        assignment: dict[int, bool] = {}
        trail: list[int] = []  # Lưu thứ tự các biến đã gán để dễ hoàn tác khi quay lui

        # Gán trước các biến trong assumptions
        if assumptions:
            for lit in assumptions:
                var = abs(lit)
                val = lit > 0
                if var in assignment:
                    # Hai assumption mâu thuẫn nhau (vd: [1, -1]) -> xung đột ngay ở gốc
                    if assignment[var] != val:
                        stats["runtime"] = time.perf_counter() - start_time
                        return False, None, stats
                else:
                    assignment[var] = val
                    trail.append(var)
                    stats["propagations"] += 1

        ordered_vars = list(range(1, max_var + 1))

        # Nâng tạm giới hạn đệ quy nếu số biến lớn (vd: bàn 5x5 có nhiều biến phụ)
        old_limit = sys.getrecursionlimit()
        needed_limit = max_var + 500
        if needed_limit > old_limit:
            sys.setrecursionlimit(needed_limit)

        try:
            is_sat = self._dpll(clauses, assignment, trail, stats)
        finally:
            if needed_limit > old_limit:
                sys.setrecursionlimit(old_limit)

        stats["runtime"] = time.perf_counter() - start_time

        if not is_sat:
            return False, None, stats

        # Điền nốt giá trị mặc định (False) cho các biến tự do nếu chưa được gán
        complete_model = {var: assignment.get(var, False) for var in ordered_vars}
        return True, complete_model, stats

    def _preprocess_cnf(
        self, cnf: list[list[int]]
    ) -> tuple[list[tuple[int, ...]], int, bool]:
        """
        Lọc sơ bộ CNF: báo lỗi nếu có literal 0, bỏ literal trùng và bỏ mệnh đề luôn đúng (chứa cả x và -x).
        """
        max_var = self.total_vars
        processed: list[tuple[int, ...]] = []
        has_empty_clause = False

        for clause in cnf:
            if len(clause) == 0:
                has_empty_clause = True
                continue

            seen: set[int] = set()
            is_tautology = False
            deduped: list[int] = []

            for lit in clause:
                if lit == 0:
                    raise ValueError("Literal trong CNF không được bằng 0.")
                max_var = max(max_var, abs(lit))
                if -lit in seen:
                    is_tautology = True
                if lit not in seen:
                    seen.add(lit)
                    deduped.append(lit)

            if not is_tautology:
                processed.append(tuple(deduped))

        return processed, max_var, has_empty_clause

    def _unit_propagate(
        self,
        clauses: list[tuple[int, ...]],
        assignment: dict[int, bool],
        trail: list[int],
        stats: dict[str, int | float],
    ) -> tuple[bool, bool, int | None]:
        """
        Lặp lan truyền đơn vị cho đến khi không còn unit clause nào nữa.
        Trả về (ok, all_satisfied, next_var):
          - ok = False nếu bị xung đột.
          - all_satisfied = True nếu mọi mệnh đề đều đã đúng.
          - next_var: biến chưa gán nhỏ nhất nằm trong các mệnh đề chưa thỏa (để phân nhánh).
        """
        while True:
            changed = False
            all_satisfied = True
            next_var: int | None = None

            for clause in clauses:
                clause_sat = False
                unit_lit: int | None = None
                unassigned_count = 0
                clause_min_var: int | None = None

                for lit in clause:
                    var = abs(lit)
                    if var in assignment:
                        if assignment[var] == (lit > 0):
                            clause_sat = True
                            break
                    else:
                        unassigned_count += 1
                        if unassigned_count == 1:
                            unit_lit = lit
                        if clause_min_var is None or var < clause_min_var:
                            clause_min_var = var

                if clause_sat:
                    continue

                if unassigned_count == 0:
                    # Mọi literal trong mệnh đề đều sai -> xung đột
                    return False, False, None

                all_satisfied = False

                if unassigned_count == 1 and unit_lit is not None:
                    var = abs(unit_lit)
                    assignment[var] = unit_lit > 0
                    trail.append(var)
                    stats["propagations"] += 1
                    changed = True
                elif clause_min_var is not None:
                    if next_var is None or clause_min_var < next_var:
                        next_var = clause_min_var

            if not changed:
                return True, all_satisfied, next_var

    def _dpll(
        self,
        clauses: list[tuple[int, ...]],
        assignment: dict[int, bool],
        trail: list[int],
        stats: dict[str, int | float],
    ) -> bool:
        """Hàm đệ quy DPLL chính."""
        ok, all_satisfied, next_var = self._unit_propagate(clauses, assignment, trail, stats)
        if not ok:
            return False

        if all_satisfied or next_var is None:
            return True

        # Chọn 1 biến chưa gán nhỏ nhất trong các mệnh đề chưa thỏa để phân nhánh
        stats["decisions"] += 1

        # Thử gán lần lượt True rồi False
        for val in (True, False):
            saved_len = len(trail)
            assignment[next_var] = val
            trail.append(next_var)

            if self._dpll(clauses, assignment, trail, stats):
                return True

            # Nhánh thử bị xung đột -> hoàn tác các biến vừa gán để quay lui
            stats["backtracks"] += 1
            while len(trail) > saved_len:
                del assignment[trail.pop()]

        return False
