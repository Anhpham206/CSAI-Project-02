"""Đánh giá ngữ nghĩa trực tiếp, độc lập với bộ mã hóa CNF."""

from __future__ import annotations

from itertools import product
from typing import Any, Iterable, Iterator, Mapping

from game.board import CRIMINAL, INNOCENT, coord_to_var, iter_coords_row_major, resolve_region


class SemanticEvaluator:
    """Đánh giá mệnh đề bằng phép đếm Python và duyệt BFS."""

    def __init__(self, size: int) -> None:
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0: raise ValueError("size không hợp lệ")
        self.size = size

    def _value(self, assignment: Mapping[Any, Any], coord: str) -> bool:
        var = coord_to_var(coord, self.size)
        value = assignment.get(var, assignment.get(coord))
        if value is None: raise KeyError(f"Thiếu phép gán cho ô {coord}")
        if isinstance(value, str):
            if value.upper() == CRIMINAL: return True
            if value.upper() == INNOCENT: return False
            raise ValueError(f"Trạng thái không hợp lệ cho {coord}: {value!r}")
        if isinstance(value, bool): return value
        raise ValueError(f"Giá trị phép gán không hợp lệ cho {coord}: {value!r}")

    def _region(self, region: dict[str, Any] | None) -> list[str]:
        if region is None: return iter_coords_row_major(self.size)
        return resolve_region(region, self.size)

    def count_criminals(self, region: dict[str, Any], assignment: Mapping[Any, Any]) -> int:
        return sum(self._value(assignment, c) for c in self._region(region))

    def evaluate(self, clue: dict[str, Any], assignment: Mapping[Any, Any]) -> bool:
        typ = str(clue.get("type", "")).upper()
        if typ == "FACT":
            targets = clue.get("target") or (clue.get("targets") or [])[0]
            value = self._value(assignment, str(targets).upper()); expected = str(clue["status"]).upper() == CRIMINAL
            return value == expected
        if typ == "SAME" or typ == "DIFFERENT":
            values = [self._value(assignment, str(c).upper()) for c in clue["targets"]]
            result = all(x == values[0] for x in values[1:])
            return result if typ == "SAME" else not result
        if typ in {"EXACTLY", "AT_LEAST", "AT_MOST"}:
            count = self.count_criminals(clue["region"], assignment); k = clue["k"]
            return count == k if typ == "EXACTLY" else count >= k if typ == "AT_LEAST" else count <= k
        if typ == "PARITY":
            return self.count_criminals(clue["region"], assignment) % 2 == (1 if str(clue["parity"]).upper() == "ODD" else 0)
        if typ == "COMPARE":
            a = self.count_criminals(clue["region1"], assignment); b = self.count_criminals(clue["region2"], assignment); op = str(clue["op"]).upper()
            return {"GT": a > b, ">": a > b, "LT": a < b, "<": a < b, "EQ": a == b, "==": a == b, "GTE": a >= b, ">=": a >= b, "LTE": a <= b, "<=": a <= b, "NEQ": a != b, "!=": a != b}[op]
        if typ == "COMPOUND":
            values = [self.evaluate(sub, assignment) for sub in clue.get("subclues", clue.get("clues", []))]
            return all(values) if str(clue.get("op", clue.get("operator"))).upper() == "AND" else any(values)
        if typ == "CONNECTIVITY":
            coords = self._region(clue.get("region")); wanted = str(clue.get("status", CRIMINAL)).upper() == CRIMINAL
            active = {c for c in coords if self._value(assignment, c) == wanted}
            if len(active) <= 1: return True
            seen = {next(iter(active))}; stack = list(seen); adjacency = str(clue.get("adjacency", "ORTHOGONAL")).upper()
            positions = {c: divmod(coord_to_var(c, self.size) - 1, self.size) for c in coords}
            while stack:
                cur = stack.pop(); r, c = positions[cur]
                for other in active - seen:
                    rr, cc = positions[other]; dr, dc = abs(r - rr), abs(c - cc)
                    linked = dr + dc == 1 if adjacency == "ORTHOGONAL" else max(dr, dc) == 1 if adjacency in {"EIGHT", "KING", "ALL"} else dr == dc == 1
                    if linked: seen.add(other); stack.append(other)
            return seen == active
        raise ValueError(f"Loại clue không được hỗ trợ: {typ}")

    def evaluate_all(self, clues: Iterable[dict[str, Any]], assignment: Mapping[Any, Any]) -> bool:
        return all(self.evaluate(clue, assignment) for clue in clues)

    def enumerate_models(self, clues: Iterable[dict[str, Any]], fixed: Mapping[Any, Any] | None = None, limit: int | None = None) -> Iterator[dict[int, bool]]:
        if self.size > 4 and limit is None and not fixed: raise ValueError("enumerate_models chỉ cho phép N <= 4 nếu không giới hạn")
        fixed = fixed or {}; normalized: dict[int, bool] = {}
        for key, value in fixed.items():
            var = key if isinstance(key, int) else coord_to_var(str(key), self.size)
            normalized[var] = value if isinstance(value, bool) else str(value).upper() == CRIMINAL
        clue_list = list(clues); count = 0
        for bits in product((False, True), repeat=self.size * self.size):
            assignment = {i + 1: bit for i, bit in enumerate(bits)}
            if any(assignment.get(k) != v for k, v in normalized.items()): continue
            if self.evaluate_all(clue_list, assignment):
                yield assignment; count += 1
                if limit is not None and count >= limit: return

    def count_models(self, clues: Iterable[dict[str, Any]], fixed: Mapping[Any, Any] | None = None, limit: int | None = None) -> int:
        return sum(1 for _ in self.enumerate_models(clues, fixed, limit))
