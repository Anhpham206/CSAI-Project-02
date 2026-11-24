"""
Mô hình bàn cờ (Board), thẻ nhân vật (Cell), ánh xạ tọa độ/biến và xử lý vùng manh mối
cho trò chơi Griductive Solver.

Quy ước tọa độ & biến (khớp 100% với Data Contract 1 và TV4 DeductiveAgent):
  - Cột đánh chữ cái từ trái sang phải: A, B, C, ...
  - Hàng đánh số từ trên xuống dưới: 1, 2, 3, ...
  - Mã biến nguyên thủy 1..N^2 theo thứ tự duyệt từng hàng (row-major order):
    Ví dụ 3x3: A1->1, B1->2, C1->3, A2->4, ..., C3->9.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any


CRIMINAL = "CRIMINAL"
INNOCENT = "INNOCENT"
UNKNOWN = "UNKNOWN"
INCONSISTENT = "INCONSISTENT"

VALID_STATUSES = (CRIMINAL, INNOCENT)


def _validate_size(size: int) -> None:
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0 or size > 26:
        raise ValueError(f"Kích thước bàn cờ không hợp lệ: {size!r} (yêu cầu 1 <= size <= 26)")


def coord_to_row_col(coord: str, size: int) -> tuple[int, int]:
    """
    Chuyển tọa độ ô (vd: 'A1', 'C2') sang chỉ số 0-indexed (row, col).

    Args:
        coord: Chuỗi tọa độ dạng '<Col><Row>', vd 'C2' (cột C, hàng 2).
        size: Kích thước cạnh N của bàn cờ N x N.

    Returns:
        Bộ (row_idx, col_idx) đánh số từ 0.
    """
    _validate_size(size)
    if not isinstance(coord, str):
        raise ValueError(f"Tọa độ phải là chuỗi, nhận được {type(coord).__name__}")

    cleaned = coord.strip().upper()
    if len(cleaned) < 2:
        raise ValueError(f"Tọa độ không hợp lệ: {coord!r}")

    col_char = cleaned[0]
    row_str = cleaned[1:]
    if not ("A" <= col_char <= "Z") or not row_str.isdigit():
        raise ValueError(f"Tọa độ không hợp lệ: {coord!r}")

    col_idx = ord(col_char) - ord("A")
    row_idx = int(row_str) - 1
    if not (0 <= col_idx < size and 0 <= row_idx < size):
        raise ValueError(f"Tọa độ {coord!r} nằm ngoài lưới {size}x{size}")

    return row_idx, col_idx


def row_col_to_coord(row: int, col: int, size: int) -> str:
    """Chuyển chỉ số 0-indexed (row, col) sang chuỗi tọa độ chuẩn (vd: (1, 2) -> 'C2')."""
    _validate_size(size)
    if (
        isinstance(row, bool)
        or isinstance(col, bool)
        or not isinstance(row, int)
        or not isinstance(col, int)
    ):
        raise ValueError(f"Chỉ số hàng/cột phải là số nguyên, nhận được ({row!r}, {col!r})")
    if not (0 <= row < size and 0 <= col < size):
        raise ValueError(f"Chỉ số ({row}, {col}) nằm ngoài lưới {size}x{size}")

    return f"{chr(ord('A') + col)}{row + 1}"


def normalize_coord(coord: str, size: int) -> str:
    """Chuẩn hóa tọa độ về dạng in hoa hợp lệ (vd: ' b2 ' -> 'B2')."""
    row, col = coord_to_row_col(coord, size)
    return row_col_to_coord(row, col, size)


def coord_to_var(coord: str, size: int) -> int:
    """
    Chuyển tọa độ ô (vd: 'A1', 'C2') sang mã biến nguyên thủy (1..N^2) theo row-major order.

    Khớp 100% với hàm coord_to_var của DeductiveAgent (TV4).
    """
    row_idx, col_idx = coord_to_row_col(coord, size)
    return row_idx * size + col_idx + 1


def var_to_coord(var_id: int, size: int) -> str:
    """
    Chuyển mã biến nguyên thủy (1..N^2) sang tọa độ ô (vd: 1 -> 'A1').

    Khớp 100% với hàm var_to_coord của DeductiveAgent (TV4).
    """
    _validate_size(size)
    if isinstance(var_id, bool) or not isinstance(var_id, int):
        raise ValueError(f"var_id phải là số nguyên, nhận được {var_id!r}")
    if not (1 <= var_id <= size * size):
        raise ValueError(f"var_id {var_id} nằm ngoài phạm vi 1..{size * size}")

    row_idx, col_idx = divmod(var_id - 1, size)
    return row_col_to_coord(row_idx, col_idx, size)


def iter_coords_row_major(size: int) -> list[str]:
    """Trả về toàn bộ tọa độ trên lưới N x N theo thứ tự row-major (A1, B1, ..., N_N)."""
    _validate_size(size)
    return [row_col_to_coord(r, c, size) for r in range(size) for c in range(size)]


def _sort_row_major(coords: set[str] | list[str], size: int) -> list[str]:
    return sorted(set(coords), key=lambda c: coord_to_var(c, size))


def _dedupe_preserve_order(coords: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for coord in coords:
        if coord not in seen:
            seen.add(coord)
            result.append(coord)
    return result


def _neighbors_of(coord: str, size: int) -> list[str]:
    row, col = coord_to_row_col(coord, size)
    result: list[str] = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            nr, nc = row + dr, col + dc
            if 0 <= nr < size and 0 <= nc < size:
                result.append(row_col_to_coord(nr, nc, size))
    return result


def resolve_region(region: dict[str, Any], size: int) -> list[str]:
    """
    Giải mã một đối tượng vùng (region dict) thành danh sách tọa độ các ô thuộc vùng đó.

    Hỗ trợ 4 vùng cơ bản:
      - ROW: {"kind": "ROW", "value": 1..N}
      - COLUMN / COL: {"kind": "COLUMN", "value": "A".. hoặc 1..N}
      - NEIGHBORS: {"kind": "NEIGHBORS", "center"|"target"|"cell": "B2"}
      - EXPLICIT: {"kind": "EXPLICIT", "cells": ["A1", "B2"]}

    Và các vùng mở rộng:
      - INTERSECTION: {"kind": "INTERSECTION", "regions": [r1, r2, ...]}
      - COMMON_NEIGHBORS: {"kind": "COMMON_NEIGHBORS", "targets": ["A1", "C1"]}
      - BOUNDARY: {"kind": "BOUNDARY"}
      - CORNERS: {"kind": "CORNERS"}
      - BETWEEN: {"kind": "BETWEEN", "targets": ["A1", "C1"]}
    """
    _validate_size(size)
    if not isinstance(region, dict):
        raise ValueError(f"Region phải là dict, nhận được {type(region).__name__}")

    raw_kind = region.get("kind")
    if not isinstance(raw_kind, str) or not raw_kind.strip():
        raise ValueError("Region thiếu trường 'kind' hợp lệ")

    kind = raw_kind.strip().upper()

    if kind == "ROW":
        value = region.get("value")
        if isinstance(value, str) and value.strip().isdigit():
            row_num = int(value.strip())
        elif not isinstance(value, bool) and isinstance(value, int):
            row_num = value
        else:
            raise ValueError(f"Giá trị ROW không hợp lệ: {value!r}")

        if not (1 <= row_num <= size):
            raise ValueError(f"Hàng {row_num} nằm ngoài phạm vi 1..{size}")
        row_idx = row_num - 1
        return [row_col_to_coord(row_idx, c, size) for c in range(size)]

    if kind in ("COLUMN", "COL"):
        value = region.get("value")
        if isinstance(value, str):
            cleaned = value.strip().upper()
            if len(cleaned) == 1 and "A" <= cleaned <= "Z":
                col_idx = ord(cleaned) - ord("A")
            elif cleaned.isdigit():
                col_idx = int(cleaned) - 1
            else:
                raise ValueError(f"Giá trị COLUMN không hợp lệ: {value!r}")
        elif not isinstance(value, bool) and isinstance(value, int):
            col_idx = value - 1
        else:
            raise ValueError(f"Giá trị COLUMN không hợp lệ: {value!r}")

        if not (0 <= col_idx < size):
            raise ValueError(f"Cột {value!r} nằm ngoài phạm vi lưới {size}x{size}")
        return [row_col_to_coord(r, col_idx, size) for r in range(size)]

    if kind == "NEIGHBORS":
        center = region.get("center") or region.get("target") or region.get("cell")
        if not isinstance(center, str):
            raise ValueError("Region NEIGHBORS cần trường 'center' (hoặc 'target'/'cell')")
        return _neighbors_of(center, size)

    if kind == "EXPLICIT":
        raw_cells = region.get("cells")
        if not isinstance(raw_cells, list):
            raise ValueError("Region EXPLICIT cần danh sách 'cells'")
        normalized = [normalize_coord(c, size) for c in raw_cells]
        return _dedupe_preserve_order(normalized)

    if kind == "INTERSECTION":
        sub_regions = region.get("regions")
        if not isinstance(sub_regions, list) or not sub_regions:
            raise ValueError("Region INTERSECTION cần danh sách 'regions' không rỗng")
        common: set[str] | None = None
        for sub in sub_regions:
            resolved = set(resolve_region(sub, size))
            common = resolved if common is None else (common & resolved)
        return _sort_row_major(common or set(), size)

    if kind == "COMMON_NEIGHBORS":
        targets = region.get("targets") or region.get("cells")
        if not isinstance(targets, list) or len(targets) < 2:
            raise ValueError("Region COMMON_NEIGHBORS cần ít nhất 2 tọa độ trong 'targets'")
        common_nb: set[str] | None = None
        for target in targets:
            nbs = set(_neighbors_of(target, size))
            common_nb = nbs if common_nb is None else (common_nb & nbs)
        return _sort_row_major(common_nb or set(), size)

    if kind == "BOUNDARY":
        boundary = [
            row_col_to_coord(r, c, size)
            for r in range(size)
            for c in range(size)
            if r in (0, size - 1) or c in (0, size - 1)
        ]
        return boundary

    if kind == "CORNERS":
        corner_coords = {
            row_col_to_coord(0, 0, size),
            row_col_to_coord(0, size - 1, size),
            row_col_to_coord(size - 1, 0, size),
            row_col_to_coord(size - 1, size - 1, size),
        }
        return _sort_row_major(corner_coords, size)

    if kind == "BETWEEN":
        targets = region.get("targets") or region.get("cells")
        if not isinstance(targets, list) or len(targets) != 2:
            raise ValueError("Region BETWEEN cần đúng 2 tọa độ trong 'targets'")
        r1, c1 = coord_to_row_col(targets[0], size)
        r2, c2 = coord_to_row_col(targets[1], size)
        dr = r2 - r1
        dc = c2 - c1
        if dr == 0 and dc == 0:
            return []
        if dr != 0 and dc != 0 and abs(dr) != abs(dc):
            raise ValueError(
                f"Hai ô {targets[0]!r} và {targets[1]!r} không cùng hàng, cột hoặc đường chéo"
            )
        step_r = 0 if dr == 0 else (1 if dr > 0 else -1)
        step_c = 0 if dc == 0 else (1 if dc > 0 else -1)
        steps = max(abs(dr), abs(dc))
        between_coords = [
            row_col_to_coord(r1 + i * step_r, c1 + i * step_c, size)
            for i in range(1, steps)
        ]
        return _sort_row_major(between_coords, size)

    raise ValueError(f"Loại vùng (region kind) không được hỗ trợ: {raw_kind!r}")


def resolve_clue_cells(clue: dict[str, Any], size: int) -> list[str]:
    """
    Trích xuất danh sách tọa độ duy nhất (có thứ tự) mà manh mối tham chiếu hoặc đếm tới.

    Hỗ trợ toàn bộ 6 mẫu cơ bản (FACT, SAME, DIFFERENT, EXACTLY, AT_LEAST, AT_MOST)
    và các mẫu mở rộng (PARITY, COMPARE, COMPOUND, CONNECTIVITY, đa vùng region1/region2/regions).
    """
    _validate_size(size)
    if not isinstance(clue, dict):
        raise ValueError(f"Clue phải là dict, nhận được {type(clue).__name__}")

    collected: list[str] = []

    if isinstance(clue.get("region"), dict):
        collected.extend(resolve_region(clue["region"], size))

    for key in ("region1", "region2"):
        if isinstance(clue.get(key), dict):
            collected.extend(resolve_region(clue[key], size))

    if isinstance(clue.get("regions"), list):
        for reg in clue["regions"]:
            if isinstance(reg, dict):
                collected.extend(resolve_region(reg, size))

    if isinstance(clue.get("target"), str):
        collected.append(normalize_coord(clue["target"], size))

    if isinstance(clue.get("targets"), list):
        for target in clue["targets"]:
            collected.append(normalize_coord(target, size))

    if isinstance(clue.get("cells"), list):
        for cell_coord in clue["cells"]:
            collected.append(normalize_coord(cell_coord, size))

    for sub_key in ("subclues", "clues"):
        if isinstance(clue.get(sub_key), list):
            for sub in clue[sub_key]:
                if isinstance(sub, dict):
                    collected.extend(resolve_clue_cells(sub, size))

    return _dedupe_preserve_order(collected)


def _format_region_desc(region: dict[str, Any] | None) -> str:
    if not isinstance(region, dict):
        return "the specified region"

    kind = str(region.get("kind", "")).strip().upper()
    if kind == "ROW":
        return f"row {region.get('value')}"
    if kind in ("COLUMN", "COL"):
        return f"column {str(region.get('value')).upper()}"
    if kind == "NEIGHBORS":
        center = region.get("center") or region.get("target") or region.get("cell")
        return f"neighbors of {str(center).upper()}"
    if kind == "EXPLICIT":
        cells = region.get("cells", [])
        return ", ".join(str(c).upper() for c in cells) if cells else "the selected cells"
    if kind == "INTERSECTION":
        sub_regions = region.get("regions", [])
        parts = [_format_region_desc(r) for r in sub_regions if isinstance(r, dict)]
        return "intersection of " + " and ".join(parts) if parts else "the region intersection"
    if kind == "COMMON_NEIGHBORS":
        targets = region.get("targets") or region.get("cells") or []
        return "common neighbors of " + " and ".join(str(t).upper() for t in targets)
    if kind == "BOUNDARY":
        return "the board boundary"
    if kind == "CORNERS":
        return "the board corners"
    if kind == "BETWEEN":
        targets = region.get("targets") or region.get("cells") or []
        if len(targets) == 2:
            return f"cells between {str(targets[0]).upper()} and {str(targets[1]).upper()}"
        return "cells between targets"
    return "the specified region"


def format_clue_text(clue: dict[str, Any]) -> str:
    """
    Trả về chuỗi mô tả dễ hiểu cho manh mối.
    Nếu clue['text'] có nội dung thì dùng trực tiếp; ngược lại tự sinh câu tiếng Anh chuẩn.
    """
    if not isinstance(clue, dict):
        return ""

    raw_text = clue.get("text")
    if isinstance(raw_text, str) and raw_text.strip():
        return raw_text.strip()

    clue_type = str(clue.get("type", "")).strip().upper()

    if clue_type == "FACT":
        target = str(clue.get("target", "?")).upper()
        status = str(clue.get("status", "UNKNOWN")).lower()
        return f"{target} is {status}."

    if clue_type == "SAME":
        targets = clue.get("targets", [])
        if len(targets) >= 2:
            return f"{str(targets[0]).upper()} and {str(targets[1]).upper()} have the same status."
        return "The specified people have the same status."

    if clue_type == "DIFFERENT":
        targets = clue.get("targets", [])
        if len(targets) >= 2:
            return f"{str(targets[0]).upper()} and {str(targets[1]).upper()} have different statuses."
        return "The specified people have different statuses."

    if clue_type == "EXACTLY":
        k = clue.get("k", 0)
        desc = _format_region_desc(clue.get("region"))
        if k == 0:
            return f"No criminals in {desc}."
        noun = "criminal" if k == 1 else "criminals"
        return f"Exactly {k} {noun} in {desc}."

    if clue_type == "AT_LEAST":
        k = clue.get("k", 0)
        desc = _format_region_desc(clue.get("region"))
        noun = "criminal" if k == 1 else "criminals"
        return f"At least {k} {noun} in {desc}."

    if clue_type == "AT_MOST":
        k = clue.get("k", 0)
        desc = _format_region_desc(clue.get("region"))
        noun = "criminal" if k == 1 else "criminals"
        return f"At most {k} {noun} in {desc}."

    if clue_type == "PARITY":
        parity = str(clue.get("parity", "EVEN")).lower()
        article = "An" if parity in ("even", "odd") else "A"
        desc = _format_region_desc(clue.get("region"))
        return f"{article} {parity} number of criminals in {desc}."

    if clue_type == "COMPARE":
        op = str(clue.get("op", "EQ")).strip().upper()
        r1 = _format_region_desc(clue.get("region1"))
        r2 = _format_region_desc(clue.get("region2"))
        op_phrase = {
            "GT": "has more criminals than",
            ">": "has more criminals than",
            "LT": "has fewer criminals than",
            "<": "has fewer criminals than",
            "EQ": "has the same number of criminals as",
            "==": "has the same number of criminals as",
            "GTE": "has at least as many criminals as",
            ">=": "has at least as many criminals as",
            "LTE": "has at most as many criminals as",
            "<=": "has at most as many criminals as",
            "NEQ": "has a different number of criminals than",
            "!=": "has a different number of criminals than",
        }.get(op, f"({op})")
        return f"{r1.capitalize()} {op_phrase} {r2}."

    if clue_type == "COMPOUND":
        op = str(clue.get("op") or clue.get("operator") or "AND").strip().upper()
        subclues = clue.get("subclues") or clue.get("clues") or []
        parts = [format_clue_text(sub).rstrip(".") for sub in subclues if isinstance(sub, dict)]
        joiner = " AND " if op == "AND" else f" {op} "
        return (joiner.join(parts) + ".") if parts else "Compound clue."

    if clue_type == "CONNECTIVITY":
        status = str(clue.get("status", CRIMINAL)).lower() + "s"
        desc = _format_region_desc(clue.get("region")) if clue.get("region") else "the board"
        return f"All {status} in {desc} are connected."

    return f"Clue ({clue_type or 'UNKNOWN'})."


@dataclass
class Cell:
    """
    Đại diện một ô/nhân vật nội bộ trên bàn cờ.
    Lưu ý: hidden_status và clue của ô úp là dữ liệu mật thuộc GameEngine.
    """

    coord: str
    name: str
    profession: str
    hidden_status: str
    clue: dict[str, Any] | None
    is_revealed: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        """
        Xuất bản sao công khai của ô.
        Tuyệt đối không lộ hidden_status hoặc clue khi is_revealed == False.
        """
        return {
            "coord": self.coord,
            "name": self.name,
            "profession": self.profession,
            "is_revealed": self.is_revealed,
            "status": self.hidden_status if self.is_revealed else None,
            "clue": copy.deepcopy(self.clue) if self.is_revealed else None,
        }


@dataclass
class Board:
    """Mô hình bàn cờ N x N với danh sách ô được lưu theo thứ tự row-major."""

    puzzle_id: str
    title: str
    size: int
    initial_revealed: list[str]
    cells: dict[str, Cell]

    def get_cell(self, coord: str) -> Cell:
        norm = normalize_coord(coord, self.size)
        return self.cells[norm]

    def coords(self) -> list[str]:
        return list(self.cells.keys())
