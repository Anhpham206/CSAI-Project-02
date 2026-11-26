"""Mã hóa các manh mối Griductive thành CNF, không dùng thư viện SAT ngoài."""

from __future__ import annotations

from itertools import combinations, product
from math import comb
from typing import Any

from game.board import CRIMINAL, INNOCENT, coord_to_var, resolve_clue_cells, resolve_region


class ClueEncodingError(ValueError):
    """Lỗi tham số hoặc cấu trúc manh mối không thể mã hóa."""


class _Builder:
    def __init__(self, clauses: list[list[int]], next_aux: int) -> None:
        self.clauses, self.next_aux = clauses, next_aux

    def var(self) -> int:
        value = self.next_aux; self.next_aux += 1; return value

    def clause(self, *lits: int | bool) -> None:
        values: list[int] = []; seen: set[int] = set()
        for lit in lits:
            if lit is True: return
            if lit is False or lit == 0: continue
            assert isinstance(lit, int)
            if -lit in seen: return
            if lit not in seen: seen.add(lit); values.append(lit)
        if values: self.clauses.append(values)

    def xor(self, a: int, b: int, out: int) -> None:
        self.clause(-a, -b, -out); self.clause(a, b, -out)
        self.clause(a, -b, out); self.clause(-a, b, out)


class CNFEncoder:
    """Chuyển KB công khai của trò chơi thành CNF xác định hoàn toàn."""

    _COUNT_TYPES = {"EXACTLY", "AT_LEAST", "AT_MOST"}
    _OPS = {"GT", "LT", "EQ", "GTE", "LTE", "NEQ", ">", "<", "==", ">=", "<=", "!="}

    def __init__(self, encoding_mode: str = "auto", direct_limit: int = 300) -> None:
        if encoding_mode not in {"auto", "direct", "counter"}:
            raise ValueError("encoding_mode phải là auto, direct hoặc counter")
        if isinstance(direct_limit, bool) or not isinstance(direct_limit, int) or direct_limit < 0:
            raise ValueError("direct_limit phải là số nguyên không âm")
        self.encoding_mode, self.direct_limit = encoding_mode, direct_limit
        self.last_report: dict[str, Any] = {}

    @staticmethod
    def _type(clue: dict[str, Any]) -> str: return str(clue.get("type", "")).strip().upper()

    @staticmethod
    def _status(value: Any) -> bool:
        value = str(value).strip().upper()
        if value == CRIMINAL: return True
        if value == INNOCENT: return False
        raise ClueEncodingError(f"status không hợp lệ: {value!r}")

    @staticmethod
    def _neg(value: int | bool) -> int | bool:
        if value == 0:
            return True
        return (not value) if isinstance(value, bool) else -value

    def _region(self, clue: dict[str, Any], key: str, size: int) -> list[int]:
        region = clue.get(key)
        if not isinstance(region, dict): raise ClueEncodingError(f"{self._type(clue)} thiếu {key}")
        try: return [coord_to_var(c, size) for c in resolve_region(region, size)]
        except ValueError as exc: raise ClueEncodingError(f"{clue.get('owner_coord', '?')} {self._type(clue)}: {exc}") from exc

    def _targets(self, clue: dict[str, Any], size: int, exact: int | None = None) -> list[int]:
        raw = clue.get("targets")
        if raw is None and isinstance(clue.get("target"), str): raw = [clue["target"]]
        if raw is None: raw = resolve_clue_cells(clue, size)
        if not isinstance(raw, list): raise ClueEncodingError(f"{self._type(clue)} thiếu targets")
        try: result = list(dict.fromkeys(coord_to_var(str(c), size) for c in raw))
        except ValueError as exc: raise ClueEncodingError(f"{clue.get('owner_coord', '?')} {self._type(clue)}: {exc}") from exc
        if exact is not None and len(result) != exact: raise ClueEncodingError(f"{self._type(clue)} cần đúng {exact} targets")
        return result

    def validate_clue(self, clue: dict[str, Any], size: int) -> None:
        if not isinstance(clue, dict): raise ClueEncodingError("clue phải là dict")
        typ = self._type(clue)
        if typ not in {"FACT", "SAME", "DIFFERENT", "EXACTLY", "AT_LEAST", "AT_MOST", "PARITY", "COMPARE", "COMPOUND", "CONNECTIVITY"}:
            raise ClueEncodingError(f"{clue.get('owner_coord', '?')} {typ}: type không hợp lệ")
        if typ == "FACT": self._status(clue.get("status")); self._targets(clue, size, 1)
        elif typ == "SAME":
            if len(self._targets(clue, size)) < 2: raise ClueEncodingError("SAME cần ít nhất 2 targets")
        elif typ == "DIFFERENT": self._targets(clue, size, 2)
        elif typ in self._COUNT_TYPES:
            region = self._region(clue, "region", size); k = clue.get("k")
            if isinstance(k, bool) or not isinstance(k, int) or not 0 <= k <= len(region): raise ClueEncodingError(f"{typ}: k ngoài [0, |R|]")
        elif typ == "PARITY":
            self._region(clue, "region", size)
            if str(clue.get("parity", "")).upper() not in {"EVEN", "ODD"}: raise ClueEncodingError("PARITY: parity không hợp lệ")
        elif typ == "COMPARE":
            self._region(clue, "region1", size); self._region(clue, "region2", size)
            if str(clue.get("op", "")).upper() not in self._OPS: raise ClueEncodingError("COMPARE: op không hợp lệ")
        elif typ == "COMPOUND":
            subs = clue.get("subclues", clue.get("clues")); op = str(clue.get("op", clue.get("operator", ""))).upper()
            if op not in {"AND", "OR"} or not isinstance(subs, list) or not subs: raise ClueEncodingError("COMPOUND không hợp lệ")
            for sub in subs: self.validate_clue(sub, size)
        else:
            region = self._region(clue, "region", size) if clue.get("region") else list(range(1, size * size + 1))
            if len(region) > 12: raise ClueEncodingError("CONNECTIVITY region too large (maximum 12 cells)")
            self._status(clue.get("status", CRIMINAL))
            if str(clue.get("adjacency", "ORTHOGONAL")).upper() not in {"ORTHOGONAL", "EIGHT", "KING", "DIAGONAL", "ALL"}: raise ClueEncodingError("CONNECTIVITY adjacency không hợp lệ")

    def _counter(self, lits: list[int], upto: int, b: _Builder) -> list[int]:
        """Bộ đếm đơn phân đầy đủ: c[j] đúng khi có ít nhất j literal đúng."""
        rows: list[list[int | bool]] = [[True] + [False] * upto]
        for i, x in enumerate(lits, 1):
            row = [True] + [b.var() for _ in range(min(i, upto))]; rows.append(row)
            for j in range(1, len(row)):
                s, prev = row[j], rows[i - 1][j] if j < len(rows[i - 1]) else False
                pp = rows[i - 1][j - 1]
                b.clause(self._neg(prev), s); b.clause(self._neg(x), self._neg(pp), s); b.clause(-s, prev, x); b.clause(-s, prev, pp)
        return [int(rows[-1][j]) for j in range(1, len(rows[-1]))]

    def _count(self, lits: list[int], typ: str, k: int, b: _Builder) -> str:
        n = len(lits)
        if (typ == "AT_LEAST" and k == 0) or (typ == "AT_MOST" and k == n):
            return "trivial"
        estimate = (comb(n, k + 1) if k < n else 0) + (comb(n, n - k + 1) if k > 0 else 0)
        mode = self.encoding_mode if self.encoding_mode != "auto" else ("direct" if estimate <= self.direct_limit else "counter")
        if mode == "direct":
            if typ in {"AT_MOST", "EXACTLY"} and k < n:
                for group in combinations(lits, k + 1): b.clause(*(-x for x in group))
            if typ in {"AT_LEAST", "EXACTLY"} and k > 0:
                for group in combinations(lits, n - k + 1): b.clause(*group)
            return "trivial" if estimate == 0 else "direct"
        cs = self._counter(lits, min(n, k + 1), b)
        if typ in {"AT_LEAST", "EXACTLY"} and k > 0: b.clause(cs[k - 1])
        if typ in {"AT_MOST", "EXACTLY"} and k + 1 <= n: b.clause(-cs[k])
        return "counter"

    def encode_clue(self, clue: dict[str, Any], size: int, aux_start: int | None = None) -> dict[str, Any]:
        self.validate_clue(clue, size); start = size * size + 1 if aux_start is None else aux_start; b = _Builder([], start); typ = self._type(clue)
        if typ == "FACT":
            v = self._targets(clue, size, 1)[0]; b.clause(v if self._status(clue["status"]) else -v); mode = "direct"
        elif typ == "SAME":
            ts = self._targets(clue, size)
            for a, z in zip(ts, ts[1:]): b.clause(-a, z); b.clause(a, -z)
            mode = "direct"
        elif typ == "DIFFERENT":
            a, z = self._targets(clue, size, 2); b.clause(a, z); b.clause(-a, -z); mode = "direct"
        elif typ in self._COUNT_TYPES: mode = self._count(self._region(clue, "region", size), typ, clue["k"], b)
        elif typ == "PARITY": mode = self._parity(clue, size, b)
        elif typ == "COMPARE": mode = self._compare(clue, size, b)
        elif typ == "COMPOUND": mode = self._compound(clue, size, b)
        else: mode = self._connectivity(clue, size, b)
        return {"clauses": b.clauses, "num_aux_vars": b.next_aux - start, "mode": mode}

    def _parity(self, clue: dict[str, Any], size: int, b: _Builder) -> str:
        lits = self._region(clue, "region", size); odd = str(clue["parity"]).upper() == "ODD"
        if self.encoding_mode != "counter" and len(lits) <= 6:
            for bits in product((False, True), repeat=len(lits)):
                if sum(bits) % 2 != int(odd): b.clause(*(-v if bit else v for v, bit in zip(lits, bits)))
            return "direct"
        if not lits:
            if odd: raise ClueEncodingError("PARITY ODD trên vùng rỗng là không thể biểu diễn")
            return "trivial"
        prev = lits[0]
        for x in lits[1:]: out = b.var(); b.xor(prev, x, out); prev = out
        b.clause(prev if odd else -prev); return "counter"

    def _compare(self, clue: dict[str, Any], size: int, b: _Builder) -> str:
        left = self._counter(self._region(clue, "region1", size), size * size, b); right = self._counter(self._region(clue, "region2", size), size * size, b); op = str(clue["op"]).upper()
        if op in {"GTE", ">="}: self._ge(left, right, b)
        elif op in {"LTE", "<="}: self._ge(right, left, b)
        elif op in {"EQ", "=="}: self._ge(left, right, b); self._ge(right, left, b)
        elif op in {"GT", ">"}: self._gt(left, right, b)
        elif op in {"LT", "<"}: self._gt(right, left, b)
        else:
            ds = []
            for j in range(max(len(left), len(right))):
                x = left[j] if j < len(left) else False; y = right[j] if j < len(right) else False; d = b.var(); ds.append(d)
                if x is False and y is False: b.clause(-d)
                elif x is False: b.clause(-d, y); b.clause(d, -y)
                elif y is False: b.clause(-d, x); b.clause(d, -x)
                else: b.clause(-d, x, y); b.clause(-d, -x, -y); b.clause(d, x, -y); b.clause(d, -x, y)
            b.clause(*ds)
        return "counter"

    @staticmethod
    def _ge(left: list[int], right: list[int], b: _Builder) -> None:
        for j, y in enumerate(right): b.clause(-y, left[j] if j < len(left) else False)

    @staticmethod
    def _gt(left: list[int], right: list[int], b: _Builder) -> None:
        b.clause(left[0] if left else False)
        for j, y in enumerate(right): b.clause(-y, left[j + 1] if j + 1 < len(left) else False)

    def _compound(self, clue: dict[str, Any], size: int, b: _Builder) -> str:
        subs = clue.get("subclues", clue.get("clues", [])); op = str(clue.get("op", clue.get("operator"))).upper(); encoded = []
        for sub in subs:
            item = self.encode_clue(sub, size, b.next_aux); b.next_aux += item["num_aux_vars"]; encoded.append(item)
        if op == "AND":
            for item in encoded: b.clauses.extend(item["clauses"])
            return "compound"
        meaningful = [x for x in encoded if x["clauses"]]
        if not meaningful: return "trivial"
        selectors = [b.var() for _ in meaningful]
        for selector, item in zip(selectors, meaningful):
            for clause in item["clauses"]: b.clause(*clause, -selector)
        b.clause(*selectors); return "compound"

    def _connectivity(self, clue: dict[str, Any], size: int, b: _Builder) -> str:
        from game.board import coord_to_row_col
        coords = resolve_region(clue["region"], size) if clue.get("region") else [f"{chr(65+c)}{r+1}" for r in range(size) for c in range(size)]
        vars_ = [coord_to_var(c, size) for c in coords]; status = self._status(clue.get("status", CRIMINAL)); adj = str(clue.get("adjacency", "ORTHOGONAL")).upper()
        positions = {v: coord_to_row_col(c, size) for v, c in zip(vars_, coords)}
        for bits in product((False, True), repeat=len(vars_)):
            active = {v for v, bit in zip(vars_, bits) if bit == status}
            if len(active) <= 1: continue
            seen = {next(iter(active))}; stack = list(seen)
            while stack:
                cur = stack.pop(); r, c = positions[cur]
                for other in active - seen:
                    rr, cc = positions[other]; dr, dc = abs(r-rr), abs(c-cc)
                    linked = (dr + dc == 1) if adj == "ORTHOGONAL" else (max(dr, dc) == 1 if adj in {"EIGHT", "KING", "ALL"} else dr == dc == 1)
                    if linked: seen.add(other); stack.append(other)
            if seen != active: b.clause(*(-v if bit else v for v, bit in zip(vars_, bits)))
        return "direct"

    def build_kb(self, public_state: dict[str, Any]) -> dict[str, Any]:
        size = public_state["size"]; known = dict(public_state.get("known_verdicts", {}))
        if not known:
            for coord, cell in public_state.get("cells", {}).items():
                if cell.get("is_revealed") and cell.get("status") in {CRIMINAL, INNOCENT}: known[coord] = cell["status"]
        clauses: list[list[int]] = []; reports = []; next_aux = size * size + 1
        for coord in sorted(known, key=lambda x: coord_to_var(x, size)):
            clauses.append([coord_to_var(coord, size) if known[coord] == CRIMINAL else -coord_to_var(coord, size)])
        for entry in sorted(public_state.get("revealed_clues", []), key=lambda x: coord_to_var(x["owner_coord"], size)):
            clue = dict(entry["clue"]); clue["owner_coord"] = entry["owner_coord"]; item = self.encode_clue(clue, size, next_aux); next_aux += item["num_aux_vars"]; clauses.extend(item["clauses"])
            reports.append({"owner": entry["owner_coord"], "type": self._type(clue), "mode": item["mode"], "aux_vars": item["num_aux_vars"], "clauses": len(item["clauses"])})
        clean: list[list[int]] = []; seen: set[tuple[int, ...]] = set()
        for clause in clauses:
            clause = list(dict.fromkeys(clause))
            if any(-x in clause for x in clause) or not clause: continue
            key = tuple(clause)
            if key not in seen: seen.add(key); clean.append(clause)
        self.last_report = {"per_clue": reports, "known_units": len(known), "totals": {"primary": size * size, "aux": next_aux - size * size - 1, "clauses": len(clean)}}
        return {"clauses": clean, "num_primary_vars": size * size, "num_aux_vars": next_aux - size * size - 1, "num_clauses": len(clean)}
