"""
Các lớp giả lập (MockEncoder, MockGameEngine, PublicOnlyEngineProxy)
phục vụ kiểm thử độc lập DeductiveAgent ở Nhiệm vụ 2 trước khi ghép nối
với các module thật của TV1 (GameEngine) và TV2 (CNFEncoder).
"""

from __future__ import annotations

import copy
import itertools
from typing import Any

from agent.deductive_agent import (
    VERDICT_CRIMINAL,
    VERDICT_INNOCENT,
    GameEngineProtocol,
    coord_to_var,
    var_to_coord,
)


class MockEncoder:
    """
    Bộ mã hóa CNF giả lập tuân thủ Data Contract 1.

    Hỗ trợ các loại manh mối cơ bản để viết unit test đa dạng cho Agent:
      - {"type": "FACT", "target": "B1", "verdict": "CRIMINAL" | "INNOCENT"}
      - {"type": "SAME", "targets": ["A1", "B1"]}
      - {"type": "DIFFERENT", "targets": ["A1", "B1"]}
      - {"type": "EXACTLY", "k": int, "targets": list[str]}
      - {"type": "AT_LEAST", "k": int, "targets": list[str]}
      - {"type": "AT_MOST", "k": int, "targets": list[str]}
      - {"type": "RAW_CNF", "clauses": list[list[int]], "aux_vars": int}
        (hữu ích để test các ca chứa biến phụ trợ > N^2)
    """

    def build_kb(self, public_state: dict[str, Any]) -> dict[str, Any]:
        board_size = int(public_state["board_size"])
        num_primary_vars = board_size * board_size
        clauses: list[list[int]] = []
        num_aux_vars = 0

        revealed_cells: dict[str, dict[str, Any]] = public_state.get(
            "revealed_cells", {}
        )

        # 1. Nạp các mệnh đề đơn vị (facts) của những ô đã lật
        for coord in sorted(revealed_cells.keys(), key=lambda c: coord_to_var(c, board_size)):
            cell = revealed_cells[coord]
            var_id = coord_to_var(coord, board_size)
            verdict = cell["verdict"]
            if verdict == VERDICT_CRIMINAL:
                clauses.append([var_id])
            elif verdict == VERDICT_INNOCENT:
                clauses.append([-var_id])
            else:
                raise ValueError(f"Verdict không hợp lệ tại {coord}: {verdict!r}")

        # 2. Nạp CNF cho từng manh mối đang mở
        for coord in sorted(revealed_cells.keys(), key=lambda c: coord_to_var(c, board_size)):
            clue = revealed_cells[coord].get("clue")
            if clue is None:
                continue
            clue_clauses, added_aux = self._encode_clue(
                clue, board_size, num_primary_vars + num_aux_vars
            )
            clauses.extend(clue_clauses)
            num_aux_vars += added_aux

        return {
            "clauses": clauses,
            "num_primary_vars": num_primary_vars,
            "num_aux_vars": num_aux_vars,
            "num_clauses": len(clauses),
        }

    def _encode_clue(
        self,
        clue: dict[str, Any],
        board_size: int,
        current_max_var: int,
    ) -> tuple[list[list[int]], int]:
        clue_type = clue["type"].upper()

        if clue_type == "FACT":
            v = coord_to_var(clue["target"], board_size)
            lit = v if clue["verdict"] == VERDICT_CRIMINAL else -v
            return [[lit]], 0

        if clue_type == "SAME":
            v1 = coord_to_var(clue["targets"][0], board_size)
            v2 = coord_to_var(clue["targets"][1], board_size)
            return [[-v1, v2], [v1, -v2]], 0

        if clue_type == "DIFFERENT":
            v1 = coord_to_var(clue["targets"][0], board_size)
            v2 = coord_to_var(clue["targets"][1], board_size)
            return [[v1, v2], [-v1, -v2]], 0

        if clue_type in ("EXACTLY", "AT_LEAST", "AT_MOST"):
            k = int(clue["k"])
            vars_in_scope = [coord_to_var(c, board_size) for c in clue["targets"]]
            n = len(vars_in_scope)
            result: list[list[int]] = []

            if clue_type in ("AT_LEAST", "EXACTLY"):
                if k > n:
                    return [[]], 0
                if k > 0:
                    # Ít nhất k biến đúng <=> mọi tập con kích thước (n - k + 1) có ít nhất 1 biến đúng
                    for subset in itertools.combinations(vars_in_scope, n - k + 1):
                        result.append(list(subset))

            if clue_type in ("AT_MOST", "EXACTLY"):
                if k < 0:
                    return [[]], 0
                if k < n:
                    # Nhiều nhất k biến đúng <=> mọi tập con kích thước (k + 1) có ít nhất 1 biến sai
                    for subset in itertools.combinations(vars_in_scope, k + 1):
                        result.append([-v for v in subset])

            return result, 0

        if clue_type == "RAW_CNF":
            raw_clauses = [list(c) for c in clue["clauses"]]
            aux_count = int(clue.get("aux_vars", 0))
            if aux_count == 0:
                max_seen = max((abs(lit) for c in raw_clauses for lit in c), default=0)
                aux_count = max(0, max_seen - current_max_var)
            return raw_clauses, aux_count

        raise ValueError(f"MockEncoder chưa hỗ trợ loại manh mối: {clue_type!r}")


class MockGameEngine:
    """
    GameEngine giả lập tuân thủ tách biệt dữ liệu ẩn theo Data Contract 3.

    Nắm giữ đáp án thật (`_secret_roles`) và toàn bộ manh mối (`_secret_clues`),
    chỉ phơi bày trạng thái công khai qua `get_public_state()` và nhận phán quyết
    qua `submit_verdict(selected_coord, verdict)`.
    """

    def __init__(
        self,
        board_size: int,
        secret_roles: dict[str, str],
        secret_clues: dict[str, dict[str, Any] | None],
        initial_revealed: list[str],
    ) -> None:
        self.board_size = board_size
        self._secret_roles = dict(secret_roles)
        self._secret_clues = copy.deepcopy(secret_clues)
        self._revealed: set[str] = set(initial_revealed)

    def get_public_state(self) -> dict[str, Any]:
        all_coords = [
            var_to_coord(v, self.board_size)
            for v in range(1, self.board_size * self.board_size + 1)
        ]
        revealed_cells: dict[str, dict[str, Any]] = {}
        active_clue_ids: list[str] = []
        hidden_coords: list[str] = []

        for coord in all_coords:
            if coord in self._revealed:
                clue = copy.deepcopy(self._secret_clues.get(coord))
                revealed_cells[coord] = {
                    "verdict": self._secret_roles[coord],
                    "clue": clue,
                }
                if clue is not None:
                    active_clue_ids.append(coord)
            else:
                hidden_coords.append(coord)

        return {
            "board_size": self.board_size,
            "revealed_cells": revealed_cells,
            "hidden_coords": hidden_coords,
            "active_clue_ids": active_clue_ids,
        }

    def submit_verdict(self, selected_coord: str, verdict: str) -> dict[str, Any]:
        if selected_coord in self._revealed:
            return {
                "accepted": False,
                "status": "ALREADY_REVEALED",
                "revealed_clue": None,
            }
        if self._secret_roles[selected_coord] != verdict:
            return {
                "accepted": False,
                "status": "CONTRADICTED",
                "revealed_clue": None,
            }

        self._revealed.add(selected_coord)
        return {
            "accepted": True,
            "status": "ACCEPTED",
            "revealed_clue": copy.deepcopy(self._secret_clues.get(selected_coord)),
        }


class PublicOnlyEngineProxy:
    """
    Lớp bọc cô lập tuyệt đối: chỉ phơi bày duy nhất 2 phương thức công khai
    của GameEngineProtocol, không chứa bất kỳ thuộc tính đáp án ẩn nào.
    """

    def __init__(self, engine: GameEngineProtocol) -> None:
        self._get_public_state = engine.get_public_state
        self._submit_verdict = engine.submit_verdict

    def get_public_state(self) -> dict[str, Any]:
        return self._get_public_state()

    def submit_verdict(self, selected_coord: str, verdict: str) -> dict[str, Any]:
        return self._submit_verdict(selected_coord, verdict)

