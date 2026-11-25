"""
Mock SAT Solver dùng để kiểm thử độc lập DeductiveAgent (Nhiệm vụ 1 & 2)
trước khi ghép nối với DPLLSolver thật của Thành viên 3.

Tuân thủ chính xác Data Contract 2:
  solve(cnf, assumptions=None) -> (is_sat, model, stats)
"""

from __future__ import annotations

import itertools
import time


class MockSolver:
    """
    Bộ giải SAT giả lập bằng duyệt bảng chân trị (brute-force) cho lưới nhỏ.
    Không dùng cho thực nghiệm hiệu năng, chỉ dùng cho unit test của Agent.
    """

    def __init__(self, total_vars: int) -> None:
        if total_vars < 0:
            raise ValueError(f"total_vars phải >= 0, nhận được {total_vars}")
        self.total_vars = total_vars

    def solve(
        self,
        cnf: list[list[int]],
        assumptions: list[int] | None = None,
    ) -> tuple[bool, dict[int, bool] | None, dict[str, int | float]]:
        """
        Giải công thức CNF kết hợp với danh sách giả định (assumptions).
        Không làm thay đổi (mutate) danh sách cnf đầu vào.
        """
        start_time = time.perf_counter()

        # Xác định tổng số biến cần duyệt
        max_var = self.total_vars
        for clause in cnf:
            for lit in clause:
                if lit == 0:
                    raise ValueError("Literal trong CNF không được bằng 0.")
                max_var = max(max_var, abs(lit))

        forced: dict[int, bool] = {}
        if assumptions:
            for lit in assumptions:
                if lit == 0:
                    raise ValueError("Literal trong assumptions không được bằng 0.")
                var = abs(lit)
                val = lit > 0
                max_var = max(max_var, var)
                if var in forced and forced[var] != val:
                    elapsed = time.perf_counter() - start_time
                    return (
                        False,
                        None,
                        {
                            "decisions": 0,
                            "propagations": len(assumptions),
                            "backtracks": 1,
                            "runtime": elapsed,
                        },
                    )
                forced[var] = val

        # Nếu CNF chứa mệnh đề rỗng [] thì chắc chắn UNSAT
        for clause in cnf:
            if len(clause) == 0:
                elapsed = time.perf_counter() - start_time
                return (
                    False,
                    None,
                    {
                        "decisions": 0,
                        "propagations": len(forced),
                        "backtracks": 1,
                        "runtime": elapsed,
                    },
                )

        free_vars = [v for v in range(1, max_var + 1) if v not in forced]
        decisions = 0
        backtracks = 0

        for combo in itertools.product((False, True), repeat=len(free_vars)):
            decisions += 1
            model = dict(forced)
            for var, val in zip(free_vars, combo):
                model[var] = val

            if self._is_satisfied(cnf, model):
                elapsed = time.perf_counter() - start_time
                return (
                    True,
                    model,
                    {
                        "decisions": decisions,
                        "propagations": len(forced),
                        "backtracks": backtracks,
                        "runtime": elapsed,
                    },
                )
            backtracks += 1

        elapsed = time.perf_counter() - start_time
        return (
            False,
            None,
            {
                "decisions": decisions,
                "propagations": len(forced),
                "backtracks": backtracks,
                "runtime": elapsed,
            },
        )

    @staticmethod
    def _is_satisfied(cnf: list[list[int]], model: dict[int, bool]) -> bool:
        for clause in cnf:
            clause_sat = False
            for lit in clause:
                var = abs(lit)
                val = model[var]
                if (lit > 0 and val) or (lit < 0 and not val):
                    clause_sat = True
                    break
            if not clause_sat:
                return False
        return True

