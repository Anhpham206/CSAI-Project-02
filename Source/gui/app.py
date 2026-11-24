"""
Giao diện Web cục bộ (HTML + Python Standard-Library HTTP Server) cho Griductive Solver.

Tuân thủ kiến trúc tách biệt 2 lớp tuyệt đối:
  - Server và toàn bộ REST API chỉ phục vụ trạng thái công khai (`engine.get_public_state()`),
    tô sáng vùng manh mối của thẻ đã mở (`engine.get_clue_highlight_cells()`), gợi ý
    (`agent.hint(public_state)`), và bước suy diễn (`agent.step(engine)`).
  - Tuyệt đối không bao giờ trả về `hidden_status` hay manh mối của các ô chưa lật.
  - Không phụ thuộc thư viện web ngoài (chỉ dùng `http.server.ThreadingHTTPServer` có sẵn).
"""

from __future__ import annotations

import copy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from typing import Any
from urllib.parse import parse_qs, urlparse
import webbrowser

from game import (
    CODE_ACCEPTED,
    CODE_INCONSISTENT,
    CRIMINAL,
    FallbackLogicAdapter,
    GameEngine,
    INCONSISTENT,
    INNOCENT,
    UNKNOWN,
    format_clue_text,
    normalize_coord,
)


STATUS_PLAYING = "PLAYING"
STATUS_SOLVED = "SOLVED"

GUI_DIR = Path(__file__).resolve().parent
INDEX_HTML_PATH = GUI_DIR / "index.html"
SOURCE_DIR = GUI_DIR.parent
DEFAULT_PUZZLES_DIR = SOURCE_DIR / "data" / "puzzles"
DEFAULT_SAMPLE_PUZZLE = DEFAULT_PUZZLES_DIR / "sample_3x3.json"


def _detect_backend_name(agent: Any) -> str:
    cls_name = type(agent).__name__
    if cls_name == "FallbackLogicAdapter":
        return "FallbackLogicAdapter"
    if hasattr(agent, "encoder") and hasattr(agent, "solver"):
        return f"{cls_name} ({type(agent.solver).__name__})"
    return cls_name


class GriductiveWebSession:
    """
    Bộ điều phối phiên chơi Web an toàn đa luồng (thread-safe).

    Nắm giữ `GameEngine`, tác tử suy luận `agent`, lịch sử `trace_history` và một `threading.Lock`
    để đồng bộ mọi thao tác API.
    """

    def __init__(
        self,
        puzzle_path: str | Path | None = None,
        agent: Any = None,
        engine: GameEngine | None = None,
        puzzles_dir: str | Path | None = None,
    ) -> None:
        self.lock = threading.Lock()
        self.agent: Any = agent if agent is not None else FallbackLogicAdapter()
        self.engine: GameEngine = (
            engine if engine is not None else GameEngine(validator=self.agent)
        )
        if engine is not None and agent is not None:
            self.engine.set_validator(self.agent)

        self.puzzles_dir: Path = (
            Path(puzzles_dir).resolve()
            if puzzles_dir is not None
            else DEFAULT_PUZZLES_DIR.resolve()
        )
        self.current_puzzle_path: Path | None = None
        self.trace_history: list[dict[str, Any]] = []
        self.game_status: str = STATUS_PLAYING
        self.backend_name: str = _detect_backend_name(self.agent)

        initial_path = self._resolve_initial_puzzle(puzzle_path)
        if initial_path is not None:
            self.load_puzzle(path=initial_path)
        elif self._engine_has_board():
            state = self.engine.get_public_state()
            self.game_status = STATUS_SOLVED if state["is_solved"] else STATUS_PLAYING

    @staticmethod
    def _resolve_initial_puzzle(puzzle_path: str | Path | None) -> Path | None:
        if puzzle_path is not None:
            return Path(puzzle_path)
        if DEFAULT_SAMPLE_PUZZLE.is_file():
            return DEFAULT_SAMPLE_PUZZLE
        return None

    def _engine_has_board(self) -> bool:
        try:
            self.engine.get_public_state()
            return True
        except RuntimeError:
            return False

    def _reset_agent(self) -> None:
        reset_fn = getattr(self.agent, "reset", None)
        if callable(reset_fn):
            reset_fn()

    @staticmethod
    def _active_clue_ids(public_state: dict[str, Any]) -> list[str]:
        return [
            entry["owner_coord"]
            for entry in public_state.get("revealed_clues", [])
            if isinstance(entry, dict) and entry.get("clue") is not None
        ]

    # ------------------------------------------------------------------
    # Các nghiệp vụ API (luôn bảo vệ bằng self.lock)
    # ------------------------------------------------------------------

    def get_state_payload(self) -> dict[str, Any]:
        with self.lock:
            public_state = (
                self.engine.get_public_state() if self._engine_has_board() else None
            )
            if public_state is not None and public_state["is_solved"]:
                self.game_status = STATUS_SOLVED
            return {
                "public_state": public_state,
                "trace_history": copy.deepcopy(self.trace_history),
                "backend": self.backend_name,
                "puzzles_dir": str(self.puzzles_dir),
                "game_status": self.game_status,
            }

    def list_puzzles(self) -> dict[str, Any]:
        """Liệt kê metadata của các file *.json trong `puzzles_dir` (không lộ đáp án ẩn)."""
        puzzles: list[dict[str, Any]] = []
        if self.puzzles_dir.is_dir():
            for json_file in sorted(self.puzzles_dir.glob("*.json")):
                try:
                    with json_file.open("r", encoding="utf-8") as handle:
                        raw = json.load(handle)
                    if not isinstance(raw, dict):
                        continue
                    size = raw.get("size")
                    puzzle_id = str(raw.get("puzzle_id") or json_file.stem)
                    title = str(raw.get("title") or puzzle_id)
                    puzzles.append(
                        {
                            "filename": json_file.name,
                            "puzzle_id": puzzle_id,
                            "title": title,
                            "size": size,
                        }
                    )
                except Exception:
                    continue
        return {
            "puzzles": puzzles,
            "puzzles_dir": str(self.puzzles_dir),
        }

    def load_puzzle(
        self,
        filename: str | None = None,
        path: str | Path | None = None,
        puzzle_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.lock:
            if puzzle_data is not None:
                if not isinstance(puzzle_data, dict):
                    raise ValueError("'puzzle_data' must be a JSON object.")
                self.engine.load_from_dict(puzzle_data)
                self.current_puzzle_path = None
            elif filename is not None:
                if not isinstance(filename, str) or not filename.strip():
                    raise ValueError("'filename' must be a non-empty string.")
                clean_name = Path(filename.strip()).name
                if clean_name != filename.strip() or not clean_name.lower().endswith(".json"):
                    raise ValueError(f"Invalid puzzle filename: {filename!r}")
                candidate = (self.puzzles_dir / clean_name).resolve()
                base_dir = self.puzzles_dir.resolve()
                if base_dir not in candidate.parents:
                    raise ValueError(f"Puzzle filename escapes puzzles directory: {filename!r}")
                if not candidate.is_file():
                    raise FileNotFoundError(f"Puzzle file not found: {clean_name}")
                self.engine.load_from_file(candidate)
                self.current_puzzle_path = candidate
            elif path is not None:
                target = Path(path).resolve()
                if not target.is_file():
                    raise FileNotFoundError(f"Puzzle file not found: {target}")
                self.engine.load_from_file(target)
                self.current_puzzle_path = target
            else:
                raise ValueError(
                    "Provide one of 'filename', 'path', or 'puzzle_data' to load a puzzle."
                )

            self._reset_agent()
            self.trace_history = []
            public_state = self.engine.get_public_state()
            self.game_status = (
                STATUS_SOLVED if public_state["is_solved"] else STATUS_PLAYING
            )
            return {
                "public_state": public_state,
                "trace_history": [],
                "backend": self.backend_name,
                "puzzles_dir": str(self.puzzles_dir),
                "game_status": self.game_status,
            }

    def restart(self) -> dict[str, Any]:
        with self.lock:
            self.engine.restart()
            self._reset_agent()
            self.trace_history = []
            public_state = self.engine.get_public_state()
            self.game_status = (
                STATUS_SOLVED if public_state["is_solved"] else STATUS_PLAYING
            )
            return {
                "public_state": public_state,
                "trace_history": [],
                "game_status": self.game_status,
            }

    def submit_verdict(self, coord: str, verdict: str) -> dict[str, Any]:
        with self.lock:
            before_state = self.engine.get_public_state()
            active_clues = self._active_clue_ids(before_state)

            result = self.engine.submit_verdict(coord, verdict)
            code = str(result.get("code", ""))

            if code == CODE_ACCEPTED:
                accepted_coord = str(result["coord"])
                accepted_verdict = str(result["verdict"])
                revealed_clue = result.get("revealed_clue")
                sat_queries = [
                    {
                        "target_coord": accepted_coord,
                        "assumed_verdict": INNOCENT,
                        "result": "UNSAT" if accepted_verdict == CRIMINAL else "SAT",
                    },
                    {
                        "target_coord": accepted_coord,
                        "assumed_verdict": CRIMINAL,
                        "result": "SAT" if accepted_verdict == CRIMINAL else "UNSAT",
                    },
                ]
                self.trace_history.append(
                    {
                        "step": len(self.trace_history) + 1,
                        "source": "MANUAL",
                        "active_clue_ids": active_clues,
                        "sat_queries": sat_queries,
                        "selected_coord": accepted_coord,
                        "verdict": accepted_verdict,
                        "revealed_clue": copy.deepcopy(revealed_clue),
                        "revealed_clue_text": (
                            format_clue_text(revealed_clue)
                            if isinstance(revealed_clue, dict)
                            else ""
                        ),
                    }
                )
                self.game_status = (
                    STATUS_SOLVED if result.get("is_solved") else STATUS_PLAYING
                )
            elif code == CODE_INCONSISTENT:
                self.game_status = INCONSISTENT

            public_state = self.engine.get_public_state()
            return {
                "result": result,
                "public_state": public_state,
                "trace_history": copy.deepcopy(self.trace_history),
                "game_status": self.game_status,
            }

    def get_highlight(self, coord: str) -> dict[str, Any]:
        with self.lock:
            norm_coord = normalize_coord(coord, self.engine.size)
            cells = self.engine.get_clue_highlight_cells(norm_coord)
            return {
                "coord": norm_coord,
                "cells": cells,
            }

    def request_hint(self) -> dict[str, Any]:
        with self.lock:
            public_state = self.engine.get_public_state()
            if public_state["is_solved"]:
                self.game_status = STATUS_SOLVED
                return {
                    "hint": None,
                    "public_state": public_state,
                    "game_status": self.game_status,
                }

            suggestion = self.agent.hint(public_state)
            if suggestion is None:
                self.game_status = UNKNOWN
            elif (
                str(suggestion.get("verdict", "")).strip().upper() == INCONSISTENT
                or suggestion.get("target_coord") is None
            ):
                self.game_status = INCONSISTENT
            else:
                self.game_status = STATUS_PLAYING

            return {
                "hint": suggestion,
                "public_state": public_state,
                "game_status": self.game_status,
            }

    def step_auto(self) -> dict[str, Any]:
        with self.lock:
            if self.engine.is_solved():
                self.game_status = STATUS_SOLVED
                return {
                    "trace": None,
                    "public_state": self.engine.get_public_state(),
                    "trace_history": copy.deepcopy(self.trace_history),
                    "game_status": self.game_status,
                }

            raw_trace = self.agent.step(self.engine)
            trace = copy.deepcopy(raw_trace)
            step_num = len(self.trace_history) + 1
            trace["step"] = step_num

            revealed_clue = trace.get("revealed_clue")
            history_entry = copy.deepcopy(trace)
            history_entry["source"] = "AUTO"
            history_entry["revealed_clue_text"] = (
                format_clue_text(revealed_clue) if isinstance(revealed_clue, dict) else ""
            )
            self.trace_history.append(history_entry)

            public_state = self.engine.get_public_state()
            verdict = str(trace.get("verdict", UNKNOWN)).strip().upper()
            if public_state["is_solved"]:
                self.game_status = STATUS_SOLVED
            elif verdict == INCONSISTENT:
                self.game_status = INCONSISTENT
            elif verdict == UNKNOWN or trace.get("selected_coord") is None:
                self.game_status = UNKNOWN
            else:
                self.game_status = STATUS_PLAYING

            return {
                "trace": trace,
                "public_state": public_state,
                "trace_history": copy.deepcopy(self.trace_history),
                "game_status": self.game_status,
            }


class _GriductiveRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler phục vụ trang `index.html` và REST JSON API."""

    server: "GriductiveWebServer"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        if not getattr(self.server, "quiet", True):
            super().log_message(format, *args)

    def _send_bytes(
        self,
        body: bytes,
        content_type: str,
        status: int = HTTPStatus.OK,
        cache_control: str = "no-store",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(
            encoded,
            content_type="application/json; charset=utf-8",
            status=status,
        )

    def _read_json_body(self) -> dict[str, Any]:
        length_header = self.headers.get("Content-Length")
        if not length_header:
            return {}
        try:
            length = int(length_header)
        except ValueError as exc:
            raise ValueError("Invalid Content-Length header.") from exc
        if length <= 0:
            return {}
        raw_bytes = self.rfile.read(length)
        try:
            parsed = json.loads(raw_bytes.decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"Malformed JSON request body: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("JSON request body must be an object.")
        return parsed

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path

        try:
            if route in ("/", "/index.html"):
                html_path = self.server.html_path
                if not html_path.is_file():
                    self._send_json(
                        {"error": f"UI template not found: {html_path.name}"},
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                    return
                content = html_path.read_bytes()
                self._send_bytes(
                    content,
                    content_type="text/html; charset=utf-8",
                    status=HTTPStatus.OK,
                )
                return

            if route == "/api/state":
                self._send_json(self.server.session.get_state_payload())
                return

            if route == "/api/puzzles":
                self._send_json(self.server.session.list_puzzles())
                return

            if route == "/api/highlight":
                params = parse_qs(parsed.query)
                coord_list = params.get("coord")
                if not coord_list or not coord_list[0].strip():
                    self._send_json(
                        {"error": "Missing required query parameter 'coord'."},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return
                self._send_json(self.server.session.get_highlight(coord_list[0]))
                return

            self._send_json(
                {"error": f"Endpoint not found: {route}"},
                status=HTTPStatus.NOT_FOUND,
            )
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except FileNotFoundError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
        except RuntimeError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json(
                {"error": f"Internal server error: {exc}"},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path

        try:
            body = self._read_json_body()

            if route == "/api/load":
                payload = self.server.session.load_puzzle(
                    filename=body.get("filename"),
                    path=body.get("path"),
                    puzzle_data=body.get("puzzle_data"),
                )
                self._send_json(payload)
                return

            if route == "/api/restart":
                self._send_json(self.server.session.restart())
                return

            if route == "/api/verdict":
                coord = body.get("coord")
                verdict = body.get("verdict")
                if not isinstance(coord, str) or not isinstance(verdict, str):
                    self._send_json(
                        {"error": "Request body requires string fields 'coord' and 'verdict'."},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return
                self._send_json(self.server.session.submit_verdict(coord, verdict))
                return

            if route == "/api/hint":
                self._send_json(self.server.session.request_hint())
                return

            if route == "/api/step":
                self._send_json(self.server.session.step_auto())
                return

            self._send_json(
                {"error": f"Endpoint not found: {route}"},
                status=HTTPStatus.NOT_FOUND,
            )
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except FileNotFoundError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
        except RuntimeError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json(
                {"error": f"Internal server error: {exc}"},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )


class GriductiveWebServer(ThreadingHTTPServer):
    """HTTP Server đa luồng lưu phiên `GriductiveWebSession` và đường dẫn `index.html`."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        session: GriductiveWebSession,
        html_path: Path = INDEX_HTML_PATH,
        quiet: bool = True,
    ) -> None:
        self.session = session
        self.html_path = Path(html_path)
        self.quiet = quiet
        super().__init__(server_address, _GriductiveRequestHandler)

    @property
    def host(self) -> str:
        return str(self.server_address[0])

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    @property
    def url(self) -> str:
        display_host = "127.0.0.1" if self.host in ("0.0.0.0", "") else self.host
        return f"http://{display_host}:{self.port}"


def create_app_server(
    host: str = "127.0.0.1",
    port: int = 0,
    puzzle_path: str | Path | None = None,
    agent: Any = None,
    engine: GameEngine | None = None,
    puzzles_dir: str | Path | None = None,
    quiet: bool = True,
) -> GriductiveWebServer:
    """Khởi tạo đối tượng `GriductiveWebServer` sẵn sàng chạy hoặc kiểm thử tự động."""
    session = GriductiveWebSession(
        puzzle_path=puzzle_path,
        agent=agent,
        engine=engine,
        puzzles_dir=puzzles_dir,
    )
    return GriductiveWebServer(
        server_address=(host, port),
        session=session,
        html_path=INDEX_HTML_PATH,
        quiet=quiet,
    )


def launch_app(
    puzzle_path: str | Path | None = None,
    agent: Any = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    open_browser: bool = True,
) -> None:
    """
    Khởi động Web GUI cục bộ của Griductive Solver và mở trình duyệt mặc định.

    Nếu cổng chỉ định đang bận, tự động chuyển sang một cổng trống ngẫu nhiên và thông báo rõ.
    Nhấn Ctrl+C để dừng server an toàn.
    """
    try:
        server = create_app_server(
            host=host,
            port=port,
            puzzle_path=puzzle_path,
            agent=agent,
            quiet=True,
        )
    except OSError as exc:
        if port == 0:
            raise
        print(
            f"[Griductive Web] Port {port} is busy ({exc}); binding to an available port instead..."
        )
        server = create_app_server(
            host=host,
            port=0,
            puzzle_path=puzzle_path,
            agent=agent,
            quiet=True,
        )

    url = server.url
    print("=" * 68)
    print("Griductive Solver — Web Interface")
    print(f"URL     : {url}")
    print(f"Backend : {server.session.backend_name}")
    print("Press Ctrl+C to stop the server.")
    print("=" * 68)

    browser_timer: threading.Timer | None = None
    if open_browser:
        browser_timer = threading.Timer(0.25, webbrowser.open, args=(url,))
        browser_timer.daemon = True
        browser_timer.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Griductive Web] Server stopped.")
    finally:
        if browser_timer is not None:
            browser_timer.cancel()
        server.server_close()
