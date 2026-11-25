"""
Bộ máy trò chơi Griductive (GameEngine) với kiến trúc tách biệt 2 lớp tuyệt đối.

Quy tắc sống còn:
  - GameEngine giữ toàn bộ trạng thái nội bộ (đáp án ẩn `hidden_status` và các manh mối
    của ô chưa lật) trong các thuộc tính private (`_board`, `_revealed_coords`).
  - `get_public_state()` chỉ trả về bản sao dữ liệu công khai (ô chưa lật luôn có
    `status=None` và `clue=None`).
  - `submit_verdict(coord, verdict)` áp dụng Luật Vàng Không Đoán Mò (No-Guess Rule):
    CHỈ căn cứ vào kết quả kiểm tra hệ quả logic (entailment) trên `public_state` để
    phân biệt `NOT_PROVABLE`, `CONTRADICTED`, `INCONSISTENT` và `ACCEPTED` — tuyệt đối
    không nhìn trộm `hidden_status` để quyết định chấp nhận hay từ chối.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .board import (
    Board,
    CRIMINAL,
    Cell,
    INCONSISTENT,
    INNOCENT,
    UNKNOWN,
    VALID_STATUSES,
    coord_to_var,
    iter_coords_row_major,
    normalize_coord,
    resolve_clue_cells,
)
from .fallback_agent import FallbackLogicAdapter


CODE_ACCEPTED = "ACCEPTED"
CODE_NOT_PROVABLE = "NOT_PROVABLE"
CODE_CONTRADICTED = "CONTRADICTED"
CODE_INCONSISTENT = "INCONSISTENT"
CODE_ALREADY_REVEALED = "ALREADY_REVEALED"
CODE_INVALID = "INVALID"


class GameEngine:
    """
    Quản lý vòng đời màn chơi Griductive, kiểm chứng dữ liệu JSON và luật No-Guess.
    """

    def __init__(
        self,
        puzzle_path: str | Path | None = None,
        validator: Any = None,
    ) -> None:
        self._board: Board | None = None
        self._revealed_coords: set[str] = set()
        self._move_history: list[dict[str, Any]] = []
        self._validator: Any = validator if validator is not None else FallbackLogicAdapter()

        if puzzle_path is not None:
            self.load_from_file(puzzle_path)

    # ------------------------------------------------------------------
    # Quản lý validator & nạp puzzle
    # ------------------------------------------------------------------

    def set_validator(self, validator: Any) -> None:
        """Gắn bộ kiểm tra hệ quả logic (DeductiveAgent thật hoặc FallbackLogicAdapter)."""
        self._validator = validator if validator is not None else FallbackLogicAdapter()

    @property
    def validator(self) -> Any:
        """Trả về bộ kiểm tra hệ quả logic hiện tại."""
        return self._validator

    def load_from_file(self, path: str | Path) -> None:
        """Nạp màn chơi từ tệp JSON và kiểm tra hợp lệ toàn bộ schema."""
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(f"Không tìm thấy tệp puzzle: {file_path}")
        with file_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        self.load_from_dict(data)

    def load_from_dict(self, data: dict[str, Any]) -> None:
        """
        Nạp màn chơi từ dictionary theo Data Contract 0 kèm kiểm tra schema chặt chẽ.

        Kiểm tra:
          - size là số nguyên trong [2, 26].
          - cells có đúng size * size phần tử với tọa độ phủ kín toàn bộ lưới N x N.
          - hidden_status thuộc {"CRIMINAL", "INNOCENT"}.
          - initial_revealed là danh sách tọa độ hợp lệ trên lưới.
          - Mỗi ô đều có cấu trúc `clue` hợp lệ (dict có 'type' và vùng/tọa độ hợp lệ).
        """
        if not isinstance(data, dict):
            raise ValueError("Dữ liệu puzzle phải là JSON object (dict).")

        size = data.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or not (2 <= size <= 26):
            raise ValueError(f"Trường 'size' phải là số nguyên trong [2, 26], nhận được {size!r}")

        puzzle_id = data.get("puzzle_id")
        if not isinstance(puzzle_id, str) or not puzzle_id.strip():
            raise ValueError("Trường 'puzzle_id' phải là chuỗi không rỗng.")
        puzzle_id = puzzle_id.strip()

        raw_title = data.get("title")
        if raw_title is None:
            title = puzzle_id
        elif isinstance(raw_title, str) and raw_title.strip():
            title = raw_title.strip()
        else:
            raise ValueError("Trường 'title' nếu có phải là chuỗi không rỗng.")

        raw_cells = data.get("cells")
        if not isinstance(raw_cells, list):
            raise ValueError("Trường 'cells' phải là danh sách (list).")

        expected_total = size * size
        if len(raw_cells) != expected_total:
            raise ValueError(
                f"Lưới {size}x{size} yêu cầu đúng {expected_total} ô, nhận được {len(raw_cells)}."
            )

        parsed_cells: dict[str, Cell] = {}
        for idx, raw_cell in enumerate(raw_cells):
            if not isinstance(raw_cell, dict):
                raise ValueError(f"Phần tử cells[{idx}] phải là dict.")

            raw_coord = raw_cell.get("coord")
            norm_coord = normalize_coord(raw_coord, size)
            if norm_coord in parsed_cells:
                raise ValueError(f"Tọa độ bị trùng lặp trong 'cells': {norm_coord}")

            name = raw_cell.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"Ô {norm_coord} thiếu tên nhân vật 'name' hợp lệ.")

            profession = raw_cell.get("profession", "")
            if not isinstance(profession, str):
                raise ValueError(f"Ô {norm_coord} có 'profession' không phải chuỗi.")

            raw_status = raw_cell.get("hidden_status")
            if not isinstance(raw_status, str):
                raise ValueError(f"Ô {norm_coord} thiếu 'hidden_status' hợp lệ.")
            hidden_status = raw_status.strip().upper()
            if hidden_status not in VALID_STATUSES:
                raise ValueError(
                    f"Ô {norm_coord} có 'hidden_status' không hợp lệ: {raw_status!r} "
                    f"(chỉ chấp nhận {VALID_STATUSES})."
                )

            if "clue" not in raw_cell or not isinstance(raw_cell["clue"], dict):
                raise ValueError(f"Ô {norm_coord} phải có đối tượng 'clue' dạng dict.")

            clue = copy.deepcopy(raw_cell["clue"])
            clue_type = clue.get("type")
            if not isinstance(clue_type, str) or not clue_type.strip():
                raise ValueError(f"Manh mối tại ô {norm_coord} thiếu trường 'type' hợp lệ.")

            # Kiểm tra sớm vùng và tọa độ tham chiếu trong clue
            resolve_clue_cells(clue, size)

            parsed_cells[norm_coord] = Cell(
                coord=norm_coord,
                name=name.strip(),
                profession=profession.strip(),
                hidden_status=hidden_status,
                clue=clue,
                is_revealed=False,
            )

        expected_coords = iter_coords_row_major(size)
        if set(parsed_cells.keys()) != set(expected_coords):
            missing = [c for c in expected_coords if c not in parsed_cells]
            raise ValueError(f"Danh sách ô không phủ kín lưới {size}x{size}, thiếu: {missing}")

        raw_initial = data.get("initial_revealed")
        if not isinstance(raw_initial, list):
            raise ValueError("Trường 'initial_revealed' phải là danh sách tọa độ (list).")

        initial_set: set[str] = set()
        for raw_coord in raw_initial:
            initial_set.add(normalize_coord(raw_coord, size))
        initial_revealed = sorted(initial_set, key=lambda c: coord_to_var(c, size))

        # Sắp xếp dict cells cố định theo thứ tự row-major
        ordered_cells: dict[str, Cell] = {}
        for coord in expected_coords:
            cell = parsed_cells[coord]
            cell.is_revealed = coord in initial_set
            ordered_cells[coord] = cell

        self._board = Board(
            puzzle_id=puzzle_id,
            title=title,
            size=size,
            initial_revealed=initial_revealed,
            cells=ordered_cells,
        )
        self._revealed_coords = set(initial_revealed)
        self._move_history = []
        self._reset_validator()

    def _ensure_loaded(self) -> Board:
        if self._board is None:
            raise RuntimeError("Chưa nạp puzzle nào vào GameEngine.")
        return self._board

    def _reset_validator(self) -> None:
        reset_fn = getattr(self._validator, "reset", None)
        if callable(reset_fn):
            reset_fn()

    def restart(self) -> None:
        """Đưa bàn cờ về đúng trạng thái mở ban đầu (`initial_revealed`) và xóa lịch sử."""
        board = self._ensure_loaded()
        initial_set = set(board.initial_revealed)
        for coord, cell in board.cells.items():
            cell.is_revealed = coord in initial_set
        self._revealed_coords = set(board.initial_revealed)
        self._move_history = []
        self._reset_validator()

    # ------------------------------------------------------------------
    # API công khai (Zero hidden-state leakage)
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        return self._ensure_loaded().size

    @property
    def puzzle_id(self) -> str:
        return self._ensure_loaded().puzzle_id

    @property
    def title(self) -> str:
        return self._ensure_loaded().title

    @property
    def move_history(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._move_history)

    def is_solved(self) -> bool:
        """Trả về True khi toàn bộ N^2 thẻ trên bàn cờ đều đã được lật mở."""
        if self._board is None:
            return False
        return len(self._revealed_coords) == self._board.size * self._board.size

    def get_public_state(self) -> dict[str, Any]:
        """
        Trả về bản sao trạng thái công khai của bàn cờ theo Data Contract 0.

        Bảo đảm tách biệt 2 lớp:
          - Không có bất kỳ khóa `hidden_status` nào.
          - Mọi ô có `is_revealed == False` đều có `status = None` và `clue = None`.
          - `revealed_clues` và `known_verdicts` chỉ chứa thông tin của các ô đã mở.
        """
        board = self._ensure_loaded()
        public_cells: dict[str, dict[str, Any]] = {}
        revealed_cells: list[str] = []
        unrevealed_cells: list[str] = []
        revealed_clues: list[dict[str, Any]] = []
        known_verdicts: dict[str, str] = {}

        for coord, cell in board.cells.items():
            public_cells[coord] = cell.to_public_dict()
            if cell.is_revealed:
                revealed_cells.append(coord)
                known_verdicts[coord] = cell.hidden_status
                if cell.clue is not None:
                    revealed_clues.append(
                        {
                            "owner_coord": coord,
                            "clue": copy.deepcopy(cell.clue),
                        }
                    )
            else:
                unrevealed_cells.append(coord)

        return {
            "puzzle_id": board.puzzle_id,
            "title": board.title,
            "size": board.size,
            "is_solved": self.is_solved(),
            "revealed_count": len(revealed_cells),
            "total_cells": board.size * board.size,
            "cells": public_cells,
            "revealed_cells": revealed_cells,
            "unrevealed_cells": unrevealed_cells,
            "revealed_clues": revealed_clues,
            "known_verdicts": known_verdicts,
        }

    def get_clue_highlight_cells(self, coord: str) -> list[str]:
        """
        Trả về danh sách tọa độ các ô được manh mối tại `coord` tham chiếu/đếm để GUI tô sáng.

        Nếu thẻ tại `coord` vẫn đang úp, trả về danh sách rỗng `[]` để tuyệt đối không
        làm lộ cấu trúc manh mối ẩn.
        """
        board = self._ensure_loaded()
        norm_coord = normalize_coord(coord, board.size)
        if norm_coord not in self._revealed_coords:
            return []
        cell = board.cells[norm_coord]
        if cell.clue is None:
            return []
        return resolve_clue_cells(cell.clue, board.size)

    # ------------------------------------------------------------------
    # Kiểm chứng nước đi theo Luật Không Đoán Mò (No-Guess Rule)
    # ------------------------------------------------------------------

    def _evaluate_entailment(self, public_state: dict[str, Any], coord: str) -> str:
        """
        Ủy quyền kiểm tra hệ quả logic cho validator chỉ với `public_state`.
        Hỗ trợ linh hoạt:
          1. Đối tượng có `check_entailment(public_state, coord)` -> `(verdict, queries)` hoặc `verdict`.
          2. DeductiveAgent (TV4) gắn kèm `encoder` (`encoder.build_kb` + `check_cell_entailment`).
          3. Callable `validator(public_state, coord)`.
        """
        validator = self._validator
        if validator is None:
            raise RuntimeError("Không có bộ kiểm tra hệ quả logic (validator) nào được cấu hình.")

        if hasattr(validator, "check_entailment") and callable(validator.check_entailment):
            raw = validator.check_entailment(public_state, coord)
            verdict = raw[0] if isinstance(raw, tuple) else raw
            return str(verdict).strip().upper()

        if (
            hasattr(validator, "check_cell_entailment")
            and callable(validator.check_cell_entailment)
            and hasattr(validator, "encoder")
            and validator.encoder is not None
        ):
            kb_data = validator.encoder.build_kb(public_state)
            var_id = coord_to_var(coord, int(public_state["size"]))
            raw = validator.check_cell_entailment(
                clauses=kb_data["clauses"],
                var_id=var_id,
                target_coord=coord,
            )
            verdict = raw[0] if isinstance(raw, tuple) else raw
            return str(verdict).strip().upper()

        if callable(validator):
            raw = validator(public_state, coord)
            verdict = raw[0] if isinstance(raw, tuple) else raw
            return str(verdict).strip().upper()

        raise TypeError(
            f"Validator {type(validator).__name__} không hỗ trợ check_entailment(public_state, coord)."
        )

    def submit_verdict(self, coord: str, verdict: str) -> dict[str, Any]:
        """
        Xử lý phán quyết CRIMINAL hoặc INNOCENT cho một ô trên bàn cờ.

        Luồng No-Guess:
          1. Kiểm tra định dạng tọa độ & nhãn -> INVALID nếu sai.
          2. Nếu ô đã mở -> ALREADY_REVEALED.
          3. Hỏi validator bằng `public_state` hiện tại (KHÔNG đọc đáp án ẩn!):
             - forced == UNKNOWN      -> từ chối với NOT_PROVABLE (kể cả đoán trùng đáp án ẩn!).
             - forced == INCONSISTENT -> từ chối với INCONSISTENT.
             - forced != verdict      -> từ chối với CONTRADICTED.
             - forced == verdict      -> kiểm tra chéo với hidden_status; nếu lệch -> INCONSISTENT;
                                         nếu khớp -> lật thẻ và trả về ACCEPTED + revealed_clue.
        """
        board = self._ensure_loaded()

        try:
            norm_coord = normalize_coord(coord, board.size)
        except ValueError as exc:
            return {
                "accepted": False,
                "code": CODE_INVALID,
                "coord": coord,
                "verdict": verdict,
                "forced_verdict": None,
                "revealed_clue": None,
                "is_solved": self.is_solved(),
                "message": str(exc),
            }

        if not isinstance(verdict, str) or verdict.strip().upper() not in VALID_STATUSES:
            return {
                "accepted": False,
                "code": CODE_INVALID,
                "coord": norm_coord,
                "verdict": verdict,
                "forced_verdict": None,
                "revealed_clue": None,
                "is_solved": self.is_solved(),
                "message": f"Phán quyết không hợp lệ: {verdict!r} (chỉ chấp nhận {VALID_STATUSES}).",
            }
        norm_verdict = verdict.strip().upper()

        cell = board.cells[norm_coord]
        if norm_coord in self._revealed_coords:
            return {
                "accepted": False,
                "code": CODE_ALREADY_REVEALED,
                "coord": norm_coord,
                "verdict": norm_verdict,
                "forced_verdict": cell.hidden_status,
                "revealed_clue": None,
                "is_solved": self.is_solved(),
                "message": f"Cell {norm_coord} ({cell.name}) is already revealed.",
            }

        public_state = self.get_public_state()
        forced_verdict = self._evaluate_entailment(public_state, norm_coord)

        if forced_verdict == UNKNOWN:
            return {
                "accepted": False,
                "code": CODE_NOT_PROVABLE,
                "coord": norm_coord,
                "verdict": norm_verdict,
                "forced_verdict": UNKNOWN,
                "revealed_clue": None,
                "is_solved": self.is_solved(),
                "message": (
                    f"{norm_coord} ({cell.name}) cannot be logically proven from the current "
                    f"revealed clues (no guessing allowed)."
                ),
            }

        if forced_verdict == INCONSISTENT:
            return {
                "accepted": False,
                "code": CODE_INCONSISTENT,
                "coord": norm_coord,
                "verdict": norm_verdict,
                "forced_verdict": INCONSISTENT,
                "revealed_clue": None,
                "is_solved": self.is_solved(),
                "message": "Current revealed clues are mutually inconsistent (UNSAT).",
            }

        if forced_verdict not in VALID_STATUSES:
            return {
                "accepted": False,
                "code": CODE_INVALID,
                "coord": norm_coord,
                "verdict": norm_verdict,
                "forced_verdict": forced_verdict,
                "revealed_clue": None,
                "is_solved": self.is_solved(),
                "message": f"Validator trả về kết quả không hợp lệ: {forced_verdict!r}.",
            }

        if forced_verdict != norm_verdict:
            return {
                "accepted": False,
                "code": CODE_CONTRADICTED,
                "coord": norm_coord,
                "verdict": norm_verdict,
                "forced_verdict": forced_verdict,
                "revealed_clue": None,
                "is_solved": self.is_solved(),
                "message": (
                    f"Calling {norm_coord} ({cell.name}) {norm_verdict} contradicts "
                    f"the current revealed clues."
                ),
            }

        # Kiểm tra chéo an toàn với đáp án ẩn (chỉ sau khi logic đã chứng minh chắc chắn)
        if cell.hidden_status != norm_verdict:
            return {
                "accepted": False,
                "code": CODE_INCONSISTENT,
                "coord": norm_coord,
                "verdict": norm_verdict,
                "forced_verdict": forced_verdict,
                "revealed_clue": None,
                "is_solved": self.is_solved(),
                "message": (
                    f"Puzzle inconsistency detected at {norm_coord}: logically forced "
                    f"{forced_verdict} does not match stored puzzle solution."
                ),
            }

        cell.is_revealed = True
        self._revealed_coords.add(norm_coord)
        revealed_clue = copy.deepcopy(cell.clue)
        solved_now = self.is_solved()

        response = {
            "accepted": True,
            "code": CODE_ACCEPTED,
            "coord": norm_coord,
            "verdict": norm_verdict,
            "forced_verdict": forced_verdict,
            "revealed_clue": revealed_clue,
            "is_solved": solved_now,
            "message": f"{norm_coord} ({cell.name}) confirmed as {norm_verdict}.",
        }
        self._move_history.append(
            {
                "coord": norm_coord,
                "verdict": norm_verdict,
                "code": CODE_ACCEPTED,
            }
        )
        return response
