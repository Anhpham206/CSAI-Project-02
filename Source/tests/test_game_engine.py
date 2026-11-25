"""
Unit tests cho Phase 1 (Board, GameEngine, FallbackLogicAdapter và Sample Puzzles).
Tương thích cả `py -m unittest discover -s Source/tests -v` lẫn `pytest`.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest


SOURCE_DIR = Path(__file__).resolve().parents[1]
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from game import (  # noqa: E402
    CODE_ACCEPTED,
    CODE_ALREADY_REVEALED,
    CODE_CONTRADICTED,
    CODE_INCONSISTENT,
    CODE_INVALID,
    CODE_NOT_PROVABLE,
    CRIMINAL,
    FallbackLogicAdapter,
    GameEngine,
    INCONSISTENT,
    INNOCENT,
    UNKNOWN,
    coord_to_row_col,
    coord_to_var,
    format_clue_text,
    iter_coords_row_major,
    resolve_clue_cells,
    resolve_region,
    row_col_to_coord,
    var_to_coord,
)


PUZZLES_DIR = SOURCE_DIR / "data" / "puzzles"
SAMPLE_3X3 = PUZZLES_DIR / "sample_3x3.json"
SAMPLE_4X4 = PUZZLES_DIR / "sample_4x4.json"
AMBIGUOUS_3X3 = PUZZLES_DIR / "ambiguous_3x3.json"
INCONSISTENT_3X3 = PUZZLES_DIR / "inconsistent_3x3.json"


class TestBoardAndRegions(unittest.TestCase):
    """Kiểm tra ánh xạ tọa độ/biến (khớp TV4) và giải mã vùng manh mối."""

    def test_coord_var_parity_with_tv4(self) -> None:
        # Khớp chính xác ví dụ TV4 trên lưới 3x3: A1->1, B1->2, C1->3, A2->4, ..., C3->9
        expected_3x3 = [
            ("A1", 1), ("B1", 2), ("C1", 3),
            ("A2", 4), ("B2", 5), ("C2", 6),
            ("A3", 7), ("B3", 8), ("C3", 9),
        ]
        for coord, var_id in expected_3x3:
            self.assertEqual(coord_to_var(coord, 3), var_id)
            self.assertEqual(coord_to_var(coord.lower(), 3), var_id)
            self.assertEqual(var_to_coord(var_id, 3), coord)

        # Kiểm tra song ánh trên 4x4 và 5x5 theo row-major
        for size in (4, 5):
            coords = iter_coords_row_major(size)
            self.assertEqual(len(coords), size * size)
            for idx, coord in enumerate(coords, start=1):
                self.assertEqual(coord_to_var(coord, size), idx)
                self.assertEqual(var_to_coord(idx, size), coord)
                r, c = coord_to_row_col(coord, size)
                self.assertEqual(row_col_to_coord(r, c, size), coord)

        # Kiểm tra ngoại lệ đầu vào không hợp lệ
        with self.assertRaises(ValueError):
            coord_to_var("D1", 3)
        with self.assertRaises(ValueError):
            coord_to_var("A0", 3)
        with self.assertRaises(ValueError):
            coord_to_var("A4", 3)
        with self.assertRaises(ValueError):
            var_to_coord(0, 3)
        with self.assertRaises(ValueError):
            var_to_coord(10, 3)

    def test_resolve_core_regions(self) -> None:
        self.assertEqual(resolve_region({"kind": "ROW", "value": 2}, 3), ["A2", "B2", "C2"])
        self.assertEqual(resolve_region({"kind": "COLUMN", "value": "C"}, 3), ["C1", "C2", "C3"])
        self.assertEqual(resolve_region({"kind": "COL", "value": 2}, 3), ["B1", "B2", "B3"])

        # NEIGHBORS: góc, cạnh và giữa lưới (không tính tâm)
        self.assertEqual(
            resolve_region({"kind": "NEIGHBORS", "center": "A1"}, 3),
            ["B1", "A2", "B2"],
        )
        self.assertEqual(
            resolve_region({"kind": "NEIGHBORS", "target": "B1"}, 3),
            ["A1", "C1", "A2", "B2", "C2"],
        )
        self.assertEqual(
            resolve_region({"kind": "NEIGHBORS", "cell": "B2"}, 3),
            ["A1", "B1", "C1", "A2", "C2", "A3", "B3", "C3"],
        )
        self.assertEqual(
            resolve_region({"kind": "EXPLICIT", "cells": ["c2", "A1", "C2"]}, 3),
            ["C2", "A1"],
        )

    def test_resolve_extension_regions(self) -> None:
        # INTERSECTION
        inter = resolve_region(
            {
                "kind": "INTERSECTION",
                "regions": [
                    {"kind": "ROW", "value": 2},
                    {"kind": "COLUMN", "value": "B"},
                ],
            },
            4,
        )
        self.assertEqual(inter, ["B2"])

        # COMMON_NEIGHBORS
        common = resolve_region(
            {"kind": "COMMON_NEIGHBORS", "targets": ["A1", "C1"]},
            3,
        )
        self.assertEqual(common, ["B1", "B2"])

        # BOUNDARY & CORNERS
        self.assertEqual(
            resolve_region({"kind": "BOUNDARY"}, 3),
            ["A1", "B1", "C1", "A2", "C2", "A3", "B3", "C3"],
        )
        self.assertEqual(
            resolve_region({"kind": "CORNERS"}, 4),
            ["A1", "D1", "A4", "D4"],
        )

        # BETWEEN (hàng, cột, đường chéo)
        self.assertEqual(
            resolve_region({"kind": "BETWEEN", "targets": ["A1", "D1"]}, 4),
            ["B1", "C1"],
        )
        self.assertEqual(
            resolve_region({"kind": "BETWEEN", "targets": ["A1", "A4"]}, 4),
            ["A2", "A3"],
        )
        self.assertEqual(
            resolve_region({"kind": "BETWEEN", "targets": ["A1", "D4"]}, 4),
            ["B2", "C3"],
        )

    def test_resolve_clue_cells_and_format_text(self) -> None:
        compare_clue = {
            "type": "COMPARE",
            "op": "GT",
            "region1": {"kind": "ROW", "value": 1},
            "region2": {"kind": "COLUMN", "value": "C"},
        }
        self.assertEqual(
            resolve_clue_cells(compare_clue, 3),
            ["A1", "B1", "C1", "C2", "C3"],
        )
        self.assertIn("more criminals than", format_clue_text(compare_clue).lower())

        compound_clue = {
            "type": "COMPOUND",
            "op": "AND",
            "subclues": [
                {"type": "FACT", "target": "A1", "status": "INNOCENT"},
                {"type": "PARITY", "parity": "ODD", "region": {"kind": "ROW", "value": 3}},
            ],
        }
        self.assertEqual(resolve_clue_cells(compound_clue, 3), ["A1", "A3", "B3", "C3"])
        self.assertIn("AND", format_clue_text(compound_clue))

        # Giữ nguyên text nếu đã có
        self.assertEqual(
            format_clue_text({"type": "FACT", "target": "A1", "status": "CRIMINAL", "text": "Custom text."}),
            "Custom text.",
        )


class TestGameEngineIsolationAndNoGuess(unittest.TestCase):
    """Kiểm tra kiến trúc tách biệt 2 lớp, luật No-Guess và hành vi GameEngine."""

    def test_public_state_never_leaks_hidden_info(self) -> None:
        engine = GameEngine(SAMPLE_3X3)
        state = engine.get_public_state()

        self.assertEqual(state["size"], 3)
        self.assertEqual(state["revealed_cells"], ["A1", "B2"])
        self.assertEqual(state["revealed_count"], 2)
        self.assertEqual(state["total_cells"], 9)
        self.assertFalse(state["is_solved"])

        # Tuyệt đối không có khóa hidden_status trong bất kỳ ô công khai nào
        for coord, cell_info in state["cells"].items():
            self.assertNotIn("hidden_status", cell_info)
            if coord in ("A1", "B2"):
                self.assertTrue(cell_info["is_revealed"])
                self.assertIn(cell_info["status"], (CRIMINAL, INNOCENT))
                self.assertIsNotNone(cell_info["clue"])
            else:
                self.assertFalse(cell_info["is_revealed"])
                self.assertIsNone(cell_info["status"])
                self.assertIsNone(cell_info["clue"])

        self.assertEqual(set(state["known_verdicts"].keys()), {"A1", "B2"})
        self.assertEqual(
            [c["owner_coord"] for c in state["revealed_clues"]],
            ["A1", "B2"],
        )

        # Sửa đổi dict trả về không làm biến đổi trạng thái bên trong Engine
        state["cells"]["A1"]["status"] = CRIMINAL
        state["revealed_clues"].clear()
        fresh = engine.get_public_state()
        self.assertEqual(fresh["cells"]["A1"]["status"], INNOCENT)
        self.assertEqual(len(fresh["revealed_clues"]), 2)

        # Sau khi mở thêm 1 ô hợp lệ, các ô úp còn lại vẫn hoàn toàn kín
        res = engine.submit_verdict("B1", CRIMINAL)
        self.assertTrue(res["accepted"])
        after_state = engine.get_public_state()
        self.assertEqual(after_state["revealed_cells"], ["A1", "B1", "B2"])
        for coord in after_state["unrevealed_cells"]:
            self.assertIsNone(after_state["cells"][coord]["status"])
            self.assertIsNone(after_state["cells"][coord]["clue"])

    def test_clue_highlight_respects_hidden_isolation(self) -> None:
        engine = GameEngine(SAMPLE_3X3)
        # Ô đã mở -> trả đúng danh sách ô highlight
        self.assertEqual(engine.get_clue_highlight_cells("A1"), ["B1"])
        self.assertEqual(engine.get_clue_highlight_cells("B2"), ["A1", "B1", "C1"])
        # Ô chưa mở -> tuyệt đối trả rỗng [] để không lộ manh mối ẩn
        self.assertEqual(engine.get_clue_highlight_cells("B1"), [])
        self.assertEqual(engine.get_clue_highlight_cells("A3"), [])

        # Sau khi lật B1 -> mới được phép highlight manh mối của B1
        engine.submit_verdict("B1", CRIMINAL)
        self.assertEqual(engine.get_clue_highlight_cells("B1"), ["B1", "A2"])

    def test_not_provable_rejects_even_true_hidden_status(self) -> None:
        engine = GameEngine(SAMPLE_3X3)
        # Trong sample_3x3.json, A2 thực sự là CRIMINAL trong đáp án ẩn,
        # nhưng ở KB_0 (chỉ có A1 và B2) chưa hề chứng minh được A2!
        res = engine.submit_verdict("A2", CRIMINAL)
        self.assertFalse(res["accepted"])
        self.assertEqual(res["code"], CODE_NOT_PROVABLE)
        self.assertEqual(res["forced_verdict"], UNKNOWN)
        self.assertIsNone(res["revealed_clue"])
        self.assertIn("A2", engine.get_public_state()["unrevealed_cells"])

        # Gửi INNOCENT cho A2 cũng phải bị từ chối với NOT_PROVABLE
        res_other = engine.submit_verdict("A2", INNOCENT)
        self.assertFalse(res_other["accepted"])
        self.assertEqual(res_other["code"], CODE_NOT_PROVABLE)

    def test_contradicted_rejection_and_accepted_flip_and_restart(self) -> None:
        engine = GameEngine(SAMPLE_3X3)

        # B1 bị ép buộc là CRIMINAL từ manh mối A1; gửi INNOCENT -> CONTRADICTED
        bad = engine.submit_verdict("B1", INNOCENT)
        self.assertFalse(bad["accepted"])
        self.assertEqual(bad["code"], CODE_CONTRADICTED)
        self.assertEqual(bad["forced_verdict"], CRIMINAL)
        self.assertIsNone(bad["revealed_clue"])
        self.assertIn("B1", engine.get_public_state()["unrevealed_cells"])

        # Gửi đúng CRIMINAL -> ACCEPTED, lật thẻ và mở khóa suy luận A2
        good = engine.submit_verdict("B1", CRIMINAL)
        self.assertTrue(good["accepted"])
        self.assertEqual(good["code"], CODE_ACCEPTED)
        self.assertIsNotNone(good["revealed_clue"])
        self.assertEqual(good["revealed_clue"]["type"], "SAME")
        self.assertIn("B1", engine.get_public_state()["revealed_cells"])

        # Nộp lại cho ô đã mở -> ALREADY_REVEALED
        dup = engine.submit_verdict("B1", CRIMINAL)
        self.assertFalse(dup["accepted"])
        self.assertEqual(dup["code"], CODE_ALREADY_REVEALED)
        self.assertIsNone(dup["revealed_clue"])

        # Tọa độ hoặc nhãn không hợp lệ -> INVALID
        self.assertEqual(engine.submit_verdict("Z9", CRIMINAL)["code"], CODE_INVALID)
        self.assertEqual(engine.submit_verdict("C1", "MAYBE")["code"], CODE_INVALID)

        # Restart đưa bàn cờ về đúng initial_revealed
        engine.restart()
        restarted = engine.get_public_state()
        self.assertEqual(restarted["revealed_cells"], ["A1", "B2"])
        self.assertEqual(len(engine.move_history), 0)
        self.assertFalse(engine.is_solved())

    def test_corrupted_puzzle_mismatch_detected_as_inconsistent(self) -> None:
        with SAMPLE_3X3.open("r", encoding="utf-8") as handle:
            corrupted = json.load(handle)
        # Cố tình đảo ngược đáp án ẩn của B1 thành INNOCENT trong khi A1 khẳng định B1 là CRIMINAL
        for cell in corrupted["cells"]:
            if cell["coord"] == "B1":
                cell["hidden_status"] = INNOCENT

        engine = GameEngine()
        engine.load_from_dict(corrupted)
        res = engine.submit_verdict("B1", CRIMINAL)
        self.assertFalse(res["accepted"])
        self.assertEqual(res["code"], CODE_INCONSISTENT)
        self.assertIsNone(res["revealed_clue"])
        self.assertIn("B1", engine.get_public_state()["unrevealed_cells"])

    def test_schema_validation_rejects_malformed_puzzles(self) -> None:
        with SAMPLE_3X3.open("r", encoding="utf-8") as handle:
            base = json.load(handle)

        # Kích thước sai
        bad_size = copy.deepcopy(base)
        bad_size["size"] = 1
        with self.assertRaises(ValueError):
            GameEngine().load_from_dict(bad_size)

        # Thiếu ô
        missing_cell = copy.deepcopy(base)
        missing_cell["cells"].pop()
        with self.assertRaises(ValueError):
            GameEngine().load_from_dict(missing_cell)

        # hidden_status sai
        bad_status = copy.deepcopy(base)
        bad_status["cells"][0]["hidden_status"] = "SUSPECT"
        with self.assertRaises(ValueError):
            GameEngine().load_from_dict(bad_status)

        # initial_revealed ngoài lưới
        bad_init = copy.deepcopy(base)
        bad_init["initial_revealed"] = ["Z9"]
        with self.assertRaises(ValueError):
            GameEngine().load_from_dict(bad_init)


class TestFallbackAgentAndSamplePuzzles(unittest.TestCase):
    """Kiểm tra giải tự động không đoán mò trên toàn bộ bộ puzzle mẫu."""

    def _assert_valid_trace(self, traces: list[dict]) -> None:
        self.assertGreater(len(traces), 0)
        for idx, entry in enumerate(traces, start=1):
            self.assertEqual(entry["step"], idx)
            self.assertIsInstance(entry["active_clue_ids"], list)
            self.assertIsInstance(entry["sat_queries"], list)
            self.assertGreater(len(entry["sat_queries"]), 0)
            for query in entry["sat_queries"]:
                self.assertIn("target_coord", query)
                self.assertIn("assumed_verdict", query)
                self.assertIn(query["result"], ("SAT", "UNSAT"))
                stats = query["stats"]
                for stat_key in ("decisions", "propagations", "backtracks", "runtime"):
                    self.assertIn(stat_key, stats)

    def test_sample_3x3_covers_all_core_types_and_solves_without_guessing(self) -> None:
        with SAMPLE_3X3.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)

        clue_types = {c["clue"]["type"] for c in raw["cells"]}
        region_kinds = {c["clue"]["region"]["kind"] for c in raw["cells"]}
        self.assertEqual(
            clue_types,
            {"FACT", "SAME", "DIFFERENT", "EXACTLY", "AT_LEAST", "AT_MOST"},
        )
        self.assertEqual(
            region_kinds,
            {"ROW", "COLUMN", "NEIGHBORS", "EXPLICIT"},
        )

        agent = FallbackLogicAdapter()
        engine = GameEngine(SAMPLE_3X3, validator=agent)

        # Kiểm tra hint() không thay đổi trạng thái bàn cờ
        before = engine.get_public_state()
        suggestion = agent.hint(before)
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion["target_coord"], "B1")
        self.assertEqual(suggestion["verdict"], CRIMINAL)
        self.assertEqual(suggestion["active_clue_ids"], ["A1", "B2"])
        self.assertEqual(engine.get_public_state(), before)

        traces = agent.solve_all(engine)
        self.assertTrue(engine.is_solved())
        self.assertEqual(len(traces), 7)  # 9 ô - 2 ô mở sẵn = 7 bước
        self._assert_valid_trace(traces)
        for entry in traces:
            self.assertIn(entry["verdict"], (CRIMINAL, INNOCENT))
            self.assertIsNotNone(entry["selected_coord"])
            self.assertIsNotNone(entry["revealed_clue"])

        # Khi đã giải xong, hint() trả về None
        self.assertIsNone(agent.hint(engine.get_public_state()))

    def test_sample_4x4_solves_completely_without_guessing(self) -> None:
        agent = FallbackLogicAdapter()
        engine = GameEngine(SAMPLE_4X4, validator=agent)
        traces = agent.solve_all(engine)

        self.assertTrue(engine.is_solved())
        self.assertEqual(len(traces), 13)  # 16 ô - 3 ô mở sẵn = 13 bước
        self._assert_valid_trace(traces)

    def test_ambiguous_3x3_stops_with_unknown(self) -> None:
        agent = FallbackLogicAdapter()
        engine = GameEngine(AMBIGUOUS_3X3, validator=agent)

        self.assertIsNone(agent.hint(engine.get_public_state()))

        # Dù B1 thực tế là CRIMINAL, vẫn bị từ chối với NOT_PROVABLE
        res = engine.submit_verdict("B1", CRIMINAL)
        self.assertFalse(res["accepted"])
        self.assertEqual(res["code"], CODE_NOT_PROVABLE)

        traces = agent.solve_all(engine)
        self.assertFalse(engine.is_solved())
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0]["verdict"], UNKNOWN)
        self.assertIsNone(traces[0]["selected_coord"])
        self._assert_valid_trace(traces)

    def test_inconsistent_3x3_reports_inconsistent(self) -> None:
        agent = FallbackLogicAdapter()
        engine = GameEngine(INCONSISTENT_3X3, validator=agent)

        hint_result = agent.hint(engine.get_public_state())
        self.assertIsNotNone(hint_result)
        self.assertIsNone(hint_result["target_coord"])
        self.assertEqual(hint_result["verdict"], INCONSISTENT)
        self.assertEqual(hint_result["active_clue_ids"], ["A1", "B1"])

        res = engine.submit_verdict("C1", CRIMINAL)
        self.assertFalse(res["accepted"])
        self.assertEqual(res["code"], CODE_INCONSISTENT)

        traces = agent.solve_all(engine)
        self.assertFalse(engine.is_solved())
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0]["verdict"], INCONSISTENT)
        self.assertIsNone(traces[0]["selected_coord"])
        self._assert_valid_trace(traces)

    def test_extension_clues_parity_and_compare(self) -> None:
        agent = FallbackLogicAdapter()
        # Lưới 2x2: A1=INNOCENT, B1=CRIMINAL, A2=INNOCENT, B2=CRIMINAL
        # Row 1 có 1 criminal; PARITY EVEN trên Row 1 + B2? Không, dùng:
        # A1 (INNOCENT) đã mở -> PARITY ODD trên ROW 1 => ép buộc B1 = CRIMINAL!
        # B1 (CRIMINAL) đã mở -> COMPARE GT giữa ROW 2 và COLUMN A (A1=I, B1=C)
        # Với ROW 2 (A2+B2) > COL A (A1+A2) => A2+B2 > 0+A2 => B2 > 0 => ép buộc B2 = CRIMINAL!
        public_state = {
            "puzzle_id": "ext_test",
            "title": "Extension Test",
            "size": 2,
            "is_solved": False,
            "revealed_count": 1,
            "total_cells": 4,
            "revealed_cells": ["A1"],
            "unrevealed_cells": ["B1", "A2", "B2"],
            "known_verdicts": {"A1": INNOCENT},
            "revealed_clues": [
                {
                    "owner_coord": "A1",
                    "clue": {
                        "type": "PARITY",
                        "parity": "ODD",
                        "region": {"kind": "ROW", "value": 1},
                    },
                },
                {
                    "owner_coord": "A1",
                    "clue": {
                        "type": "COMPARE",
                        "op": "GT",
                        "region1": {"kind": "ROW", "value": 2},
                        "region2": {"kind": "COLUMN", "value": "A"},
                    },
                },
            ],
        }

        verdict_b1, _ = agent.check_entailment(public_state, "B1")
        verdict_b2, _ = agent.check_entailment(public_state, "B2")
        verdict_a2, _ = agent.check_entailment(public_state, "A2")
        self.assertEqual(verdict_b1, CRIMINAL)
        self.assertEqual(verdict_b2, CRIMINAL)
        self.assertEqual(verdict_a2, UNKNOWN)

    def test_custom_validator_injection(self) -> None:
        calls: list[tuple[dict, str]] = []

        def fake_validator(public_state: dict, coord: str) -> str:
            calls.append((public_state, coord))
            # Xác minh validator nhận public_state sạch
            for info in public_state["cells"].values():
                if not info["is_revealed"]:
                    assert info["status"] is None
                    assert info["clue"] is None
            return CRIMINAL if coord == "B1" else UNKNOWN

        engine = GameEngine(SAMPLE_3X3)
        engine.set_validator(fake_validator)

        self.assertEqual(engine.submit_verdict("A2", CRIMINAL)["code"], CODE_NOT_PROVABLE)
        self.assertEqual(engine.submit_verdict("B1", INNOCENT)["code"], CODE_CONTRADICTED)
        self.assertEqual(engine.submit_verdict("B1", CRIMINAL)["code"], CODE_ACCEPTED)
        self.assertEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
