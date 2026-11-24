"""
Unit & integration tests cho Phase 2 (Web GUI + CLI):
  - Chế độ CLI (`Source/main.py --cli --puzzle ...`) trên cả 4 puzzle mẫu.
  - Giao diện Web (`GriductiveWebServer` + `index.html`) chạy trên luồng nền với cổng động (`port=0`)
    và kiểm thử đầy đủ qua `urllib.request`:
      * Phục vụ `GET /` và `GET /index.html` đầy đủ các nút điều khiển & endpoint API.
      * Kiểm tra tách biệt 2 lớp tuyệt đối: `/api/state` không bao giờ lộ `hidden_status` hay manh mối ẩn.
      * Luật No-Guess (`NOT_PROVABLE`, `CONTRADICTED`, `ACCEPTED`).
      * Tô sáng vùng manh mối (`GET /api/highlight`), gợi ý (`POST /api/hint`),
        tự động giải từng bước (`POST /api/step`), khởi động lại (`POST /api/restart`),
        nạp câu đố từ danh sách hoặc upload JSON (`POST /api/load`) với 3x3, 4x4, 5x5,
        `ambiguous_3x3.json` (`UNKNOWN`) và `inconsistent_3x3.json` (`INCONSISTENT`).
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from urllib import error as urllib_error
from urllib import request as urllib_request


SOURCE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SOURCE_DIR.parent
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from game import (  # noqa: E402
    CODE_ACCEPTED,
    CODE_CONTRADICTED,
    CODE_NOT_PROVABLE,
    CRIMINAL,
    INCONSISTENT,
    INNOCENT,
    UNKNOWN,
    iter_coords_row_major,
)
from gui import GriductiveWebServer, create_app_server  # noqa: E402


MAIN_PY = SOURCE_DIR / "main.py"
PUZZLES_DIR = SOURCE_DIR / "data" / "puzzles"
SAMPLE_3X3 = PUZZLES_DIR / "sample_3x3.json"
SAMPLE_4X4 = PUZZLES_DIR / "sample_4x4.json"
AMBIGUOUS_3X3 = PUZZLES_DIR / "ambiguous_3x3.json"
INCONSISTENT_3X3 = PUZZLES_DIR / "inconsistent_3x3.json"


class TestCLIEntryPoint(unittest.TestCase):
    """Kiểm thử điểm khởi chạy CLI `main.py --cli` trên các bộ câu đố mẫu."""

    def _run_cli(
        self, args: list[str], cwd: Path = REPO_ROOT
    ) -> subprocess.CompletedProcess[str]:
        script = MAIN_PY if cwd == REPO_ROOT else Path("main.py")
        cmd = [sys.executable, str(script), *args]
        return subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_sample_3x3_solved_from_repo_root(self) -> None:
        proc = self._run_cli(["--cli", "--puzzle", str(SAMPLE_3X3)], cwd=REPO_ROOT)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("STATUS: SOLVED", proc.stdout)
        self.assertIn("Revealed: 9 / 9", proc.stdout)
        self.assertIn("Total Steps: 7", proc.stdout)
        self.assertIn("Step 1:", proc.stdout)

    def test_cli_sample_4x4_solved_from_source_dir(self) -> None:
        proc = self._run_cli(
            ["--cli", "--puzzle", "data/puzzles/sample_4x4.json"],
            cwd=SOURCE_DIR,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("STATUS: SOLVED", proc.stdout)
        self.assertIn("Revealed: 16 / 16", proc.stdout)
        self.assertIn("Total Steps: 13", proc.stdout)

    def test_cli_ambiguous_3x3_reports_unknown(self) -> None:
        proc = self._run_cli(["--cli", "--puzzle", str(AMBIGUOUS_3X3)], cwd=REPO_ROOT)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("STATUS: UNKNOWN", proc.stdout)
        self.assertIn("Revealed: 1 / 9", proc.stdout)

    def test_cli_inconsistent_3x3_reports_inconsistent(self) -> None:
        proc = self._run_cli(["--cli", "--puzzle", str(INCONSISTENT_3X3)], cwd=REPO_ROOT)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("STATUS: INCONSISTENT", proc.stdout)
        self.assertIn("Revealed: 2 / 9", proc.stdout)

    def test_cli_default_puzzle_and_missing_file_error(self) -> None:
        default_proc = self._run_cli(["--cli"], cwd=REPO_ROOT)
        self.assertEqual(default_proc.returncode, 0, msg=default_proc.stderr)
        self.assertIn("STATUS: SOLVED", default_proc.stdout)

        missing_proc = self._run_cli(
            ["--cli", "--puzzle", "data/puzzles/does_not_exist.json"],
            cwd=SOURCE_DIR,
        )
        self.assertNotEqual(missing_proc.returncode, 0)
        self.assertIn("ERROR:", missing_proc.stderr)


class TestWebGUI(unittest.TestCase):
    """Kiểm thử toàn diện Web GUI (HTML + REST API) qua HTTP thực tế."""

    server: GriductiveWebServer
    thread: threading.Thread
    base_url: str

    def setUp(self) -> None:
        self.server = create_app_server(
            host="127.0.0.1",
            port=0,
            puzzle_path=SAMPLE_3X3,
            quiet=True,
        )
        self.base_url = self.server.url
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.05},
            daemon=True,
        )
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5.0)

    def _http_get_text(self, path: str) -> tuple[int, str, str]:
        with urllib_request.urlopen(f"{self.base_url}{path}", timeout=5) as resp:
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read().decode("utf-8")
            return resp.status, content_type, body

    def _http_json(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> tuple[int, dict[str, object], str]:
        data = None
        headers: dict[str, str] = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib_request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib_request.urlopen(req, timeout=5) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, json.loads(raw), raw
        except urllib_error.HTTPError as exc:
            try:
                raw = exc.read().decode("utf-8")
                return exc.code, json.loads(raw), raw
            finally:
                exc.close()

    def test_serves_index_html_with_expected_controls(self) -> None:
        for route in ("/", "/index.html"):
            status, content_type, html = self._http_get_text(route)
            self.assertEqual(status, 200)
            self.assertIn("text/html", content_type)
            self.assertIn("<!DOCTYPE html>", html)
            for token in (
                "Load",
                "Restart",
                "Hint",
                "Auto Solve",
                "Stop",
                "Call CRIMINAL",
                "Call INNOCENT",
                "Deduction Trace",
                "/api/state",
                "/api/puzzles",
                "/api/verdict",
                "/api/highlight",
                "/api/hint",
                "/api/step",
                "/api/restart",
                "/api/load",
                'type="file"',
            ):
                self.assertIn(token, html, msg=f"Missing {token!r} in {route}")

    def test_api_state_never_leaks_hidden_status_or_unrevealed_clues(self) -> None:
        status, data, raw_json = self._http_json("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertNotIn("hidden_status", raw_json)

        # Kiểm tra toàn bộ câu manh mối của các ô chưa lật trong sample_3x3.json không xuất hiện
        raw_puzzle = json.loads(SAMPLE_3X3.read_text(encoding="utf-8"))
        initial_revealed = set(raw_puzzle["initial_revealed"])
        for cell in raw_puzzle["cells"]:
            if cell["coord"] not in initial_revealed:
                self.assertNotIn(cell["clue"]["text"], raw_json)

        public_state = data["public_state"]
        self.assertEqual(public_state["puzzle_id"], "sample_3x3")
        self.assertEqual(public_state["revealed_count"], 2)
        self.assertEqual(public_state["total_cells"], 9)
        self.assertEqual(public_state["cells"]["A1"]["status"], INNOCENT)
        self.assertIsNotNone(public_state["cells"]["A1"]["clue"])
        self.assertIsNone(public_state["cells"]["B1"]["status"])
        self.assertIsNone(public_state["cells"]["B1"]["clue"])

    def test_api_puzzles_lists_sample_puzzles_safely(self) -> None:
        status, data, raw_json = self._http_json("GET", "/api/puzzles")
        self.assertEqual(status, 200)
        self.assertNotIn("hidden_status", raw_json)

        filenames = {item["filename"] for item in data["puzzles"]}
        self.assertTrue(
            {
                "sample_3x3.json",
                "sample_4x4.json",
                "ambiguous_3x3.json",
                "inconsistent_3x3.json",
            }.issubset(filenames)
        )

    def test_verdict_not_provable_contradicted_accepted_and_restart(self) -> None:
        # 1. A2 thực chất là CRIMINAL nhưng chưa chứng minh được -> NOT_PROVABLE
        st1, d1, _ = self._http_json(
            "POST", "/api/verdict", {"coord": "A2", "verdict": CRIMINAL}
        )
        self.assertEqual(st1, 200)
        self.assertFalse(d1["result"]["accepted"])
        self.assertEqual(d1["result"]["code"], CODE_NOT_PROVABLE)
        self.assertEqual(d1["public_state"]["revealed_count"], 2)
        self.assertFalse(d1["public_state"]["cells"]["A2"]["is_revealed"])

        # 2. B1 bị ép buộc CRIMINAL nhưng đoán INNOCENT -> CONTRADICTED
        st2, d2, _ = self._http_json(
            "POST", "/api/verdict", {"coord": "B1", "verdict": INNOCENT}
        )
        self.assertEqual(st2, 200)
        self.assertFalse(d2["result"]["accepted"])
        self.assertEqual(d2["result"]["code"], CODE_CONTRADICTED)
        self.assertEqual(d2["public_state"]["revealed_count"], 2)

        # 3. B1 = CRIMINAL -> ACCEPTED, lật thẻ và tiết lộ manh mối của B1
        st3, d3, _ = self._http_json(
            "POST", "/api/verdict", {"coord": "B1", "verdict": CRIMINAL}
        )
        self.assertEqual(st3, 200)
        self.assertTrue(d3["result"]["accepted"])
        self.assertEqual(d3["result"]["code"], CODE_ACCEPTED)
        self.assertEqual(d3["public_state"]["revealed_count"], 3)
        self.assertTrue(d3["public_state"]["cells"]["B1"]["is_revealed"])
        self.assertEqual(d3["public_state"]["cells"]["B1"]["status"], CRIMINAL)
        self.assertIn("Derek (A2)", d3["public_state"]["cells"]["B1"]["clue"]["text"])
        self.assertEqual(len(d3["trace_history"]), 1)

        # 4. Restart -> quay lại đúng initial_revealed (A1, B2) và xóa trace_history
        st4, d4, _ = self._http_json("POST", "/api/restart")
        self.assertEqual(st4, 200)
        self.assertEqual(d4["public_state"]["revealed_cells"], ["A1", "B2"])
        self.assertEqual(d4["public_state"]["revealed_count"], 2)
        self.assertFalse(d4["public_state"]["cells"]["B1"]["is_revealed"])
        self.assertEqual(d4["trace_history"], [])

    def test_highlight_returns_empty_for_unrevealed_and_exact_region_for_revealed(self) -> None:
        # Ô chưa mở -> [] (tuyệt đối không lộ manh mối ẩn)
        st_hidden, d_hidden, _ = self._http_json("GET", "/api/highlight?coord=B1")
        self.assertEqual(st_hidden, 200)
        self.assertEqual(d_hidden["coord"], "B1")
        self.assertEqual(d_hidden["cells"], [])

        # Ô đã mở B2 (Row 1 -> A1, B1, C1)
        st_b2, d_b2, _ = self._http_json("GET", "/api/highlight?coord=B2")
        self.assertEqual(st_b2, 200)
        self.assertEqual(d_b2["coord"], "B2")
        self.assertEqual(d_b2["cells"], ["A1", "B1", "C1"])

        # Ô đã mở A1 (FACT B1 -> ["B1"])
        st_a1, d_a1, _ = self._http_json("GET", "/api/highlight?coord=a1")
        self.assertEqual(st_a1, 200)
        self.assertEqual(d_a1["coord"], "A1")
        self.assertEqual(d_a1["cells"], ["B1"])

    def test_hint_and_step_loop_solve_sample_3x3(self) -> None:
        # Hint trả về nước đi chắc chắn B1 = CRIMINAL mà không lật thẻ
        st_hint, d_hint, raw_hint = self._http_json("POST", "/api/hint")
        self.assertEqual(st_hint, 200)
        self.assertNotIn("hidden_status", raw_hint)
        self.assertIsNotNone(d_hint["hint"])
        self.assertEqual(d_hint["hint"]["target_coord"], "B1")
        self.assertEqual(d_hint["hint"]["verdict"], CRIMINAL)
        self.assertEqual(d_hint["hint"]["active_clue_ids"], ["A1", "B2"])
        self.assertEqual(d_hint["public_state"]["revealed_count"], 2)

        # Vòng lặp /api/step giải hoàn toàn sample_3x3.json trong 7 bước
        steps = 0
        last_state = d_hint["public_state"]
        while not last_state["is_solved"] and steps < 20:
            st_step, d_step, raw_step = self._http_json("POST", "/api/step")
            self.assertEqual(st_step, 200)
            self.assertNotIn("hidden_status", raw_step)
            self.assertIsNotNone(d_step["trace"])
            self.assertIn(d_step["trace"]["verdict"], (CRIMINAL, INNOCENT))
            last_state = d_step["public_state"]
            steps += 1

        self.assertTrue(last_state["is_solved"])
        self.assertEqual(steps, 7)
        self.assertEqual(last_state["revealed_count"], 9)

        _, final_state_payload, _ = self._http_json("GET", "/api/state")
        self.assertEqual(final_state_payload["game_status"], "SOLVED")
        self.assertEqual(len(final_state_payload["trace_history"]), 7)

    def test_load_4x4_ambiguous_inconsistent_uploaded_5x5_and_reject_traversal(self) -> None:
        # 1. Nạp sample_4x4.json theo filename
        st_4x4, d_4x4, _ = self._http_json(
            "POST", "/api/load", {"filename": "sample_4x4.json"}
        )
        self.assertEqual(st_4x4, 200)
        self.assertEqual(d_4x4["public_state"]["size"], 4)
        self.assertEqual(d_4x4["public_state"]["total_cells"], 16)
        self.assertEqual(d_4x4["game_status"], "PLAYING")

        # 2. Nạp ambiguous_3x3.json -> UNKNOWN
        st_amb, d_amb, _ = self._http_json(
            "POST", "/api/load", {"filename": "ambiguous_3x3.json"}
        )
        self.assertEqual(st_amb, 200)
        self.assertEqual(d_amb["public_state"]["puzzle_id"], "ambiguous_3x3")

        _, hint_amb, _ = self._http_json("POST", "/api/hint")
        self.assertIsNone(hint_amb["hint"])
        self.assertEqual(hint_amb["game_status"], UNKNOWN)

        _, step_amb, _ = self._http_json("POST", "/api/step")
        self.assertEqual(step_amb["trace"]["verdict"], UNKNOWN)
        self.assertIsNone(step_amb["trace"]["selected_coord"])
        self.assertEqual(step_amb["game_status"], UNKNOWN)

        # 3. Nạp inconsistent_3x3.json -> INCONSISTENT
        st_inc, d_inc, _ = self._http_json(
            "POST", "/api/load", {"filename": "inconsistent_3x3.json"}
        )
        self.assertEqual(st_inc, 200)
        self.assertEqual(d_inc["public_state"]["puzzle_id"], "inconsistent_3x3")

        _, hint_inc, _ = self._http_json("POST", "/api/hint")
        self.assertIsNotNone(hint_inc["hint"])
        self.assertEqual(hint_inc["hint"]["verdict"], INCONSISTENT)
        self.assertEqual(hint_inc["game_status"], INCONSISTENT)

        _, step_inc, _ = self._http_json("POST", "/api/step")
        self.assertEqual(step_inc["trace"]["verdict"], INCONSISTENT)
        self.assertEqual(step_inc["game_status"], INCONSISTENT)

        # 4. Upload trực tiếp dữ liệu puzzle 5x5 qua puzzle_data
        coords_5x5 = iter_coords_row_major(5)
        puzzle_5x5 = {
            "puzzle_id": "web_test_5x5",
            "title": "Web GUI 5x5 Upload",
            "size": 5,
            "initial_revealed": ["A1"],
            "cells": [
                {
                    "coord": coord,
                    "name": f"Suspect {idx}",
                    "profession": "Analyst",
                    "hidden_status": INNOCENT,
                    "clue": {
                        "type": "AT_MOST",
                        "k": 5,
                        "region": {"kind": "ROW", "value": ((idx - 1) // 5) + 1},
                        "text": f"At most 5 criminals in row {((idx - 1) // 5) + 1}.",
                    },
                }
                for idx, coord in enumerate(coords_5x5, start=1)
            ],
        }
        st_5x5, d_5x5, raw_5x5 = self._http_json(
            "POST", "/api/load", {"puzzle_data": puzzle_5x5}
        )
        self.assertEqual(st_5x5, 200)
        self.assertNotIn("hidden_status", raw_5x5)
        self.assertEqual(d_5x5["public_state"]["size"], 5)
        self.assertEqual(d_5x5["public_state"]["total_cells"], 25)
        self.assertIn("E5", d_5x5["public_state"]["cells"])

        # 5. Ngăn path traversal trong filename
        st_bad, d_bad, _ = self._http_json(
            "POST", "/api/load", {"filename": "../../main.py"}
        )
        self.assertEqual(st_bad, 400)
        self.assertIn("error", d_bad)


if __name__ == "__main__":
    unittest.main()
