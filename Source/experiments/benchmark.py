"""
Kịch bản chạy thực nghiệm (benchmark) tự động cho toàn bộ bộ puzzle Griductive.

Ghi nhận đầy đủ 6 nhóm chỉ số theo yêu cầu mục 4.5 của đề bài:
  1. Số lượng biến nguyên thủy (primary) và biến phụ trợ (auxiliary).
  2. Số lượng mệnh đề CNF.
  3. Tổng số lần gọi SAT solver.
  4. Tổng số decisions, propagations và backtracks.
  5. Số bước suy diễn (deduction steps) và số ô đã mở.
  6. Thời gian thực thi (solver runtime và tổng runtime toàn màn chơi).

Mặc định xuất kết quả ra `Source/data/csv/benchmark_results.csv`.
"""

from __future__ import annotations

import argparse
import csv
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FuturesTimeoutError
import json
from pathlib import Path
import sys
import time
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SOURCE_DIR = Path(__file__).resolve().parents[1]
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from agent.deductive_agent import (  # noqa: E402
    VERDICT_INCONSISTENT,
    DeductiveAgent,
)
from game.engine import GameEngine  # noqa: E402
from logic.encoder import CNFEncoder  # noqa: E402
from solver.dpll import DPLLSolver  # noqa: E402


DEFAULT_PUZZLES_DIR = SOURCE_DIR / "data" / "puzzles"
DEFAULT_CSV_PATH = SOURCE_DIR / "data" / "csv" / "benchmark_results.csv"

CSV_FIELDNAMES = [
    "puzzle_id",
    "size",
    "encoding_mode",
    "outcome",
    "uniqueness",
    "initial_revealed",
    "revealed_cells",
    "total_cells",
    "deduction_steps",
    "num_primary_vars",
    "num_aux_vars",
    "total_vars",
    "num_clauses",
    "max_step_aux_vars",
    "max_step_clauses",
    "sat_calls",
    "decisions",
    "propagations",
    "backtracks",
    "solver_runtime_s",
    "total_runtime_s",
    "error_message",
]


def _build_full_kb_state(raw: dict[str, Any]) -> dict[str, Any]:
    initial_set = set(raw.get("initial_revealed", []))
    return {
        "size": int(raw["size"]),
        "known_verdicts": {
            cell["coord"]: cell["hidden_status"]
            for cell in raw["cells"]
            if cell["coord"] in initial_set
        },
        "revealed_clues": [
            {"owner_coord": cell["coord"], "clue": cell["clue"]}
            for cell in raw["cells"]
        ],
    }


def _evaluate_single_puzzle(puzzle_path_str: str, encoding_mode: str) -> dict[str, Any]:
    """Chạy benchmark trên 1 file puzzle và trả về dictionary kết quả chuẩn hóa."""
    path = Path(puzzle_path_str)
    row: dict[str, Any] = {
        "puzzle_id": path.stem,
        "size": 0,
        "encoding_mode": encoding_mode,
        "outcome": "ERROR",
        "uniqueness": "ERR",
        "initial_revealed": 0,
        "revealed_cells": 0,
        "total_cells": 0,
        "deduction_steps": 0,
        "num_primary_vars": 0,
        "num_aux_vars": 0,
        "total_vars": 0,
        "num_clauses": 0,
        "max_step_aux_vars": 0,
        "max_step_clauses": 0,
        "sat_calls": 0,
        "decisions": 0,
        "propagations": 0,
        "backtracks": 0,
        "solver_runtime_s": 0.0,
        "total_runtime_s": 0.0,
        "error_message": "",
    }

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        size = int(raw["size"])
        row["puzzle_id"] = str(raw.get("puzzle_id") or path.stem)
        row["size"] = size
        row["total_cells"] = size * size
        row["initial_revealed"] = len(raw.get("initial_revealed", []))

        encoder = CNFEncoder(encoding_mode=encoding_mode)
        solver = DPLLSolver()
        agent = DeductiveAgent(encoder=encoder, solver=solver)
        engine = GameEngine(path, validator=agent)

        # Theo dõi kích thước KB lớn nhất qua các bước suy diễn
        peak_aux = 0
        peak_clauses = 0
        orig_build_kb = encoder.build_kb

        def tracked_build_kb(public_state: dict[str, Any]) -> dict[str, Any]:
            nonlocal peak_aux, peak_clauses
            kb = orig_build_kb(public_state)
            peak_aux = max(peak_aux, int(kb.get("num_aux_vars", 0)))
            peak_clauses = max(peak_clauses, int(kb.get("num_clauses", 0)))
            return kb

        encoder.build_kb = tracked_build_kb  # type: ignore[method-assign]

        t0 = time.perf_counter()
        trace = agent.solve_all(engine)
        total_runtime = time.perf_counter() - t0

        encoder.build_kb = orig_build_kb  # type: ignore[method-assign]

        final_state = engine.get_public_state()
        revealed_count = int(final_state["revealed_count"])
        if final_state["is_solved"]:
            outcome = "SOLVED"
        elif trace and str(trace[-1].get("verdict", "")).upper() == VERDICT_INCONSISTENT:
            outcome = VERDICT_INCONSISTENT
        else:
            outcome = "UNKNOWN"

        sat_calls = 0
        decisions = 0
        propagations = 0
        backtracks = 0
        solver_runtime = 0.0
        for step_rec in trace:
            queries = step_rec.get("sat_queries", [])
            sat_calls += len(queries)
            for q in queries:
                st = q.get("stats", {})
                decisions += int(st.get("decisions", 0))
                propagations += int(st.get("propagations", 0))
                backtracks += int(st.get("backtracks", 0))
                solver_runtime += float(st.get("runtime", 0.0))

        full_kb = orig_build_kb(_build_full_kb_state(raw))
        uniq_res = agent.check_uniqueness(full_kb)

        num_primary = int(full_kb["num_primary_vars"])
        num_aux = int(full_kb["num_aux_vars"])
        num_clauses = int(full_kb["num_clauses"])

        row.update(
            {
                "outcome": outcome,
                "uniqueness": uniq_res["status"],
                "revealed_cells": revealed_count,
                "deduction_steps": len(trace),
                "num_primary_vars": num_primary,
                "num_aux_vars": num_aux,
                "total_vars": num_primary + num_aux,
                "num_clauses": num_clauses,
                "max_step_aux_vars": peak_aux,
                "max_step_clauses": peak_clauses,
                "sat_calls": sat_calls,
                "decisions": decisions,
                "propagations": propagations,
                "backtracks": backtracks,
                "solver_runtime_s": round(solver_runtime, 6),
                "total_runtime_s": round(total_runtime, 6),
            }
        )
    except Exception as exc:
        row["outcome"] = "ERROR"
        row["error_message"] = str(exc)

    return row


def run_benchmark(
    puzzles_dir: Path = DEFAULT_PUZZLES_DIR,
    output_csv: Path = DEFAULT_CSV_PATH,
    encoding_mode: str = "auto",
    timeout_s: float = 60.0,
) -> list[dict[str, Any]]:
    """Chạy benchmark toàn bộ các file JSON trong `puzzles_dir` và xuất CSV."""
    puzzle_files = sorted(puzzles_dir.glob("*.json"))
    results: list[dict[str, Any]] = []

    if timeout_s > 0:
        with ProcessPoolExecutor(max_workers=1) as executor:
            for path in puzzle_files:
                future = executor.submit(_evaluate_single_puzzle, str(path), encoding_mode)
                try:
                    row = future.result(timeout=timeout_s)
                except FuturesTimeoutError:
                    row = {
                        "puzzle_id": path.stem,
                        "size": 0,
                        "encoding_mode": encoding_mode,
                        "outcome": "TIMEOUT",
                        "uniqueness": "TIMEOUT",
                        "initial_revealed": 0,
                        "revealed_cells": 0,
                        "total_cells": 0,
                        "deduction_steps": 0,
                        "num_primary_vars": 0,
                        "num_aux_vars": 0,
                        "total_vars": 0,
                        "num_clauses": 0,
                        "max_step_aux_vars": 0,
                        "max_step_clauses": 0,
                        "sat_calls": 0,
                        "decisions": 0,
                        "propagations": 0,
                        "backtracks": 0,
                        "solver_runtime_s": round(timeout_s, 6),
                        "total_runtime_s": round(timeout_s, 6),
                        "error_message": f"Quá thời gian giới hạn ({timeout_s}s).",
                    }
                results.append(row)
    else:
        for path in puzzle_files:
            results.append(_evaluate_single_puzzle(str(path), encoding_mode))

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)

    return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Chạy benchmark hệ thống Griductive Solver và xuất kết quả CSV."
    )
    parser.add_argument(
        "--puzzles-dir",
        type=Path,
        default=DEFAULT_PUZZLES_DIR,
        help="Thư mục chứa các file puzzle JSON (mặc định: Source/data/puzzles)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help="Đường dẫn file CSV kết quả (mặc định: Source/data/csv/benchmark_results.csv)",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "direct", "counter"),
        default="auto",
        help="Chế độ mã hóa CNF (mặc định: auto)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Giới hạn thời gian (giây) cho mỗi puzzle, <= 0 để tắt (mặc định: 60s)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results = run_benchmark(
        puzzles_dir=args.puzzles_dir,
        output_csv=args.output,
        encoding_mode=args.mode,
        timeout_s=args.timeout,
    )
    if not results:
        print(f"Không tìm thấy puzzle JSON nào trong {args.puzzles_dir}")
        return 1

    print("=" * 118)
    print(
        f"{'Puzzle':<20} | {'N':^3} | {'Outcome':<12} | {'Uniqueness':<18} | "
        f"{'Vars(P+A)':<10} | {'Clauses':>7} | {'SAT':>4} | {'Dec':>4} | {'Prop':>5} | "
        f"{'BT':>3} | {'Steps':>5} | {'Time(s)':>8}"
    )
    print("-" * 118)
    for r in results:
        vars_str = f"{r['num_primary_vars']}+{r['num_aux_vars']}"
        print(
            f"{r['puzzle_id']:<20} | {r['size']:^3} | {r['outcome']:<12} | {r['uniqueness']:<18} | "
            f"{vars_str:<10} | {r['num_clauses']:>7} | {r['sat_calls']:>4} | {r['decisions']:>4} | "
            f"{r['propagations']:>5} | {r['backtracks']:>3} | {r['deduction_steps']:>5} | {r['total_runtime_s']:>8.5f}"
        )
    print("=" * 118)
    print(f"Đã xuất kết quả benchmark ({len(results)} puzzles) tới: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
