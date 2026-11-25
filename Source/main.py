"""
Điểm khởi chạy chính của chương trình Griductive Solver.
Hỗ trợ hai chế độ hoạt động:
  - Mặc định (Web GUI): khởi chạy máy chủ Web cục bộ (HTML + http.server) và mở trình duyệt.
  - Dòng lệnh (`--cli`): chạy vòng lặp suy luận không đoán mò và in Deduction Trace chi tiết.

Có thể chạy từ thư mục gốc repo (`py Source/main.py`) hoặc từ bên trong `Source/` (`py main.py`).
"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path
import sys
from typing import Any


SOURCE_DIR = Path(__file__).resolve().parent
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from game import (  # noqa: E402
    CRIMINAL,
    FallbackLogicAdapter,
    GameEngine,
    INCONSISTENT,
    INNOCENT,
    UNKNOWN,
    format_clue_text,
)


DEFAULT_PUZZLE_PATH = SOURCE_DIR / "data" / "puzzles" / "sample_3x3.json"


def _find_class(module_names: tuple[str, ...], class_name: str) -> type[Any] | None:
    for mod_name in module_names:
        try:
            module = importlib.import_module(mod_name)
        except ImportError:
            continue
        candidate = getattr(module, class_name, None)
        if isinstance(candidate, type):
            return candidate
    return None


def _probe_real_pipeline(encoder: Any, solver: Any, agent: Any) -> bool:
    """Xác minh nhanh bộ TV2/TV3/TV4 đã hoàn thiện (không chỉ là stub NotImplementedError)."""
    if not (
        callable(getattr(encoder, "build_kb", None))
        and callable(getattr(solver, "solve", None))
        and callable(getattr(agent, "hint", None))
        and callable(getattr(agent, "step", None))
        and callable(getattr(agent, "solve_all", None))
    ):
        return False

    has_validator_api = callable(getattr(agent, "check_entailment", None)) or (
        callable(getattr(agent, "check_cell_entailment", None))
        and getattr(agent, "encoder", None) is not None
    )
    if not has_validator_api:
        return False

    # Kiểm thử nhanh trên một public_state 2x2 hợp lệ để đảm bảo không văng NotImplementedError
    probe_state = {
        "puzzle_id": "_probe",
        "title": "Probe",
        "size": 2,
        "is_solved": False,
        "revealed_count": 1,
        "total_cells": 4,
        "cells": {
            "A1": {"coord": "A1", "name": "A", "profession": "", "is_revealed": True, "status": INNOCENT, "clue": {"type": "FACT", "target": "B1", "status": CRIMINAL}},
            "B1": {"coord": "B1", "name": "B", "profession": "", "is_revealed": False, "status": None, "clue": None},
            "A2": {"coord": "A2", "name": "C", "profession": "", "is_revealed": False, "status": None, "clue": None},
            "B2": {"coord": "B2", "name": "D", "profession": "", "is_revealed": False, "status": None, "clue": None},
        },
        "revealed_cells": ["A1"],
        "unrevealed_cells": ["B1", "A2", "B2"],
        "known_verdicts": {"A1": INNOCENT},
        "revealed_clues": [
            {
                "owner_coord": "A1",
                "clue": {"type": "FACT", "target": "B1", "status": CRIMINAL},
            }
        ],
    }

    kb = encoder.build_kb(probe_state)
    if not isinstance(kb, dict) or "clauses" not in kb:
        return False
    suggestion = agent.hint(probe_state)
    if not isinstance(suggestion, dict) or suggestion.get("target_coord") != "B1":
        return False
    return True


def build_agent_and_validator(verbose: bool = False) -> tuple[Any, Any]:
    """
    Tự động phát hiện và kết nối bộ suy luận thật (CNFEncoder + DPLLSolver + DeductiveAgent)
    nếu các module TV2/TV3/TV4 đã được triển khai hoàn chỉnh; nếu chưa, tự động dùng
    `FallbackLogicAdapter` (giữ nguyên Data Contract 3).
    """
    encoder_cls = _find_class(("logic", "logic.cnf_encoder", "logic.encoder"), "CNFEncoder")
    solver_cls = _find_class(("solver", "solver.dpll", "solver.dpll_solver"), "DPLLSolver")
    agent_cls = _find_class(("agent", "agent.deductive_agent", "agent.agent"), "DeductiveAgent")

    if encoder_cls is not None and solver_cls is not None and agent_cls is not None:
        try:
            encoder = encoder_cls()
            solver = solver_cls()
            try:
                agent = agent_cls(encoder=encoder, solver=solver)
            except TypeError:
                agent = agent_cls(encoder, solver)

            if _probe_real_pipeline(encoder, solver, agent):
                reset_fn = getattr(agent, "reset", None)
                if callable(reset_fn):
                    reset_fn()
                if verbose:
                    print("[Logic Backend] Using CNFEncoder + DPLLSolver + DeductiveAgent.")
                return agent, agent
        except Exception:
            pass

    fallback = FallbackLogicAdapter()
    if verbose:
        print(
            "[Logic Backend] TV2/TV3/TV4 modules not yet complete; "
            "using FallbackLogicAdapter."
        )
    return fallback, fallback


def resolve_puzzle_path(raw_path: str | Path | None) -> Path:
    """Phân giải đường dẫn file puzzle tương thích khi chạy từ repo root hoặc từ Source/."""
    if raw_path is None:
        return DEFAULT_PUZZLE_PATH

    direct = Path(raw_path)
    if direct.is_file():
        return direct.resolve()

    from_source = SOURCE_DIR / raw_path
    if from_source.is_file():
        return from_source.resolve()

    return direct


def run_cli(puzzle_path: str | Path | None = None) -> int:
    """Chạy chế độ dòng lệnh (CLI): nạp puzzle, suy luận toàn bộ và in Deduction Trace."""
    resolved = resolve_puzzle_path(puzzle_path)
    agent, validator = build_agent_and_validator(verbose=True)

    try:
        engine = GameEngine(resolved, validator=validator)
    except Exception as exc:
        print(f"ERROR: Failed to load puzzle '{resolved}': {exc}", file=sys.stderr)
        return 1

    initial_state = engine.get_public_state()
    size = int(initial_state["size"])
    print("=" * 72)
    print(f"Puzzle   : {initial_state['title']} ({initial_state['puzzle_id']})")
    print(f"File     : {resolved}")
    print(f"Grid Size: {size}x{size} ({initial_state['total_cells']} cells)")
    print(f"Initial Revealed ({initial_state['revealed_count']}): "
          f"{', '.join(initial_state['revealed_cells']) or 'none'}")
    for coord in initial_state["revealed_cells"]:
        cell = initial_state["cells"][coord]
        clue_text = format_clue_text(cell["clue"]) if cell["clue"] else "-"
        print(f"  - {coord} ({cell['name']}): {cell['status']} | Clue: {clue_text}")
    print("-" * 72)

    traces = agent.solve_all(engine)
    total_sat_queries = 0

    for entry in traces:
        step_num = entry.get("step", "-")
        selected = entry.get("selected_coord") or "-"
        verdict = entry.get("verdict", UNKNOWN)
        active_clues = ", ".join(entry.get("active_clue_ids", [])) or "none"
        queries = entry.get("sat_queries", [])
        sat_count = len(queries)
        total_sat_queries += sat_count
        revealed_clue = entry.get("revealed_clue")
        new_clue_str = format_clue_text(revealed_clue) if revealed_clue else "-"

        print(
            f"Step {step_num}: Selected={selected} | Verdict={verdict} | "
            f"Active Clues=[{active_clues}] | SAT Queries={sat_count}"
        )
        if revealed_clue is not None:
            print(f"         New Clue: {new_clue_str}")

    final_state = engine.get_public_state()
    if final_state["is_solved"]:
        final_status = "SOLVED"
    elif traces and str(traces[-1].get("verdict", "")).upper() == INCONSISTENT:
        final_status = INCONSISTENT
    else:
        final_status = UNKNOWN

    print("-" * 72)
    print(f"STATUS: {final_status}")
    print(f"Revealed: {final_state['revealed_count']} / {final_state['total_cells']}")
    print(f"Total Steps: {len(traces)}")
    print(f"Total SAT Queries: {total_sat_queries}")
    print("=" * 72)
    return 0


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Griductive Solver — Propositional Logic & SAT Deduction (CSAI Project 2)"
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Run in command-line mode (CLI) instead of launching the Web GUI",
    )
    parser.add_argument(
        "--puzzle",
        type=str,
        default=None,
        help="Path to a puzzle JSON file (default: data/puzzles/sample_3x3.json)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host address to bind the Web GUI server (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the Web GUI server (default: 8000)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not automatically open the Web GUI in the default browser",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    if args.cli:
        return run_cli(args.puzzle)

    from gui import launch_app  # noqa: E402

    agent, _validator = build_agent_and_validator(verbose=False)
    puzzle_path = resolve_puzzle_path(args.puzzle) if args.puzzle is not None else None
    launch_app(
        puzzle_path=puzzle_path,
        agent=agent,
        host=args.host,
        port=args.port,
        open_browser=not args.no_browser,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
