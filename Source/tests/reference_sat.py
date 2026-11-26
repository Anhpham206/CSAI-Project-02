"""SAT tham chiếu tối giản, chỉ dùng cho kiểm thử, không phải DPLLSolver của đồ án."""

from __future__ import annotations

from typing import Iterable, Mapping


def solve(clauses: Iterable[list[int]], assumptions: Mapping[int, bool] | None = None, num_vars: int | None = None) -> dict[int, bool] | None:
    """Tìm một mô hình bằng unit propagation + quay lui đệ quy."""
    data = [list(c) for c in clauses]; max_var = max((abs(x) for c in data for x in c), default=0); total = num_vars or max_var
    fixed = dict(assumptions or {})

    def search(assign: dict[int, bool]) -> dict[int, bool] | None:
        assign = dict(assign)
        changed = True
        while changed:
            changed = False
            for clause in data:
                values = [assign.get(abs(lit)) == (lit > 0) for lit in clause if abs(lit) in assign]
                if any(values): continue
                open_lits = [lit for lit in clause if abs(lit) not in assign]
                if not open_lits: return None
                if len(open_lits) == 1:
                    lit = open_lits[0]; var = abs(lit); value = lit > 0
                    if var in assign and assign[var] != value: return None
                    if var not in assign: assign[var] = value; changed = True
        var = next((v for v in range(1, total + 1) if v not in assign), None)
        if var is None: return assign
        for value in (False, True):
            result = search({**assign, var: value})
            if result is not None: return result
        return None

    return search(fixed)


def is_satisfiable(clauses: Iterable[list[int]], assumptions: Mapping[int, bool] | None = None, num_vars: int | None = None) -> bool:
    return solve(clauses, assumptions, num_vars) is not None
