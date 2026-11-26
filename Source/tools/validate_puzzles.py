"""
Công cụ kiểm tra toàn diện các file puzzle JSON cho thành viên nhóm.

Các bước xác thực cho mỗi file puzzle:
  1. Định dạng JSON & khớp `puzzle_id` với tên file.
  2. Kiểm tra schema bàn cờ, tọa độ, vùng và manh mối qua `GameEngine`.
  3. Kiểm tra thứ tự tên nhân vật theo bảng chữ cái (quy định mục 2.1).
  4. Kiểm tra ngữ nghĩa trực tiếp qua `SemanticEvaluator` (mọi manh mối có khớp `hidden_status` không).
  5. Mã hóa toàn bộ manh mối sang CNF qua `CNFEncoder` và thống kê biến/mệnh đề.
  6. Kiểm tra tính duy nhất của nghiệm (`UNIQUE` / `MULTIPLE_SOLUTIONS` / `NO_SOLUTION`) qua `DeductiveAgent.check_uniqueness` + `DPLLSolver`.
  7. Chạy giải tự động không đoán mò (`DeductiveAgent.solve_all`) từ `initial_revealed` để xác nhận có giải hết bàn cờ hay dừng ở `UNKNOWN` / `INCONSISTENT`.

Cách chạy:
  python Source/tools/validate_puzzles.py
  python Source/tools/validate_puzzles.py Source/data/puzzles/sample_3x3.json
"""

from __future__ import annotations

import argparse
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
    UNIQUENESS_NONE,
    UNIQUENESS_UNIQUE,
    VERDICT_INCONSISTENT,
    VERDICT_UNKNOWN,
    DeductiveAgent,
)
from game.engine import GameEngine  # noqa: E402
from logic.encoder import CNFEncoder  # noqa: E402
from logic.evaluator import SemanticEvaluator  # noqa: E402
from solver.dpll import DPLLSolver  # noqa: E402


DEFAULT_PUZZLES_DIR = SOURCE_DIR / "data" / "puzzles"


def _infer_expected_outcome(raw: dict[str, Any], path: Path) -> str:
    explicit = raw.get("expected_outcome")
    if isinstance(explicit, str) and explicit.strip():
        val = explicit.strip().upper()
        if val in {"SOLVABLE", "SOLVED"}:
            return "SOLVED"
        return val
    stem = path.stem.lower()
    if "ambiguous" in stem:
        return "UNKNOWN"
    if "inconsistent" in stem:
        return "INCONSISTENT"
    return "SOLVED"


def validate_puzzle_file(path: Path) -> dict[str, Any]:
    """Chạy đầy đủ 7 bước xác thực trên một file puzzle JSON."""
    issues: list[str] = []
    warnings: list[str] = []

    # 1. Đọc JSON & kiểm tra puzzle_id
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "file": path.name,
            "size": "-",
            "semantic": "ERR",
            "cnf": "-",
            "uniqueness": "ERR",
            "solve": "ERR",
            "time_s": 0.0,
            "ok": False,
            "issues": [f"Lỗi đọc JSON: {exc}"],
            "warnings": [],
        }

    if not isinstance(raw, dict):
        return {
            "file": path.name,
            "size": "-",
            "semantic": "ERR",
            "cnf": "-",
            "uniqueness": "ERR",
            "solve": "ERR",
            "time_s": 0.0,
            "ok": False,
            "issues": ["Nội dung JSON gốc phải là object (dict)."],
            "warnings": [],
        }

    puzzle_id = raw.get("puzzle_id")
    if puzzle_id != path.stem:
        issues.append(f"puzzle_id ({puzzle_id!r}) không khớp tên file ({path.stem!r}).")

    # 2. Kiểm tra schema qua GameEngine
    encoder = CNFEncoder()
    solver = DPLLSolver()
    agent = DeductiveAgent(encoder=encoder, solver=solver)

    try:
        engine = GameEngine(path, validator=agent)
    except Exception as exc:
        return {
            "file": path.name,
            "size": str(raw.get("size", "-")),
            "semantic": "ERR",
            "cnf": "-",
            "uniqueness": "ERR",
            "solve": "ERR",
            "time_s": 0.0,
            "ok": False,
            "issues": issues + [f"Lỗi schema GameEngine: {exc}"],
            "warnings": [],
        }

    size = engine.size
    expected = _infer_expected_outcome(raw, path)

    # 3. Kiểm tra thứ tự tên nhân vật (alphabetical display name)
    names = [str(cell.get("name", "")) for cell in raw.get("cells", [])]
    if names != sorted(names):
        warnings.append("Danh sách tên nhân vật chưa sắp xếp theo thứ tự bảng chữ cái.")

    # 4. Đánh giá ngữ nghĩa trực tiếp qua SemanticEvaluator
    assignment = {cell["coord"]: cell["hidden_status"] for cell in raw["cells"]}
    clues = [cell["clue"] for cell in raw["cells"] if cell.get("clue") is not None]
    try:
        semantic_ok = SemanticEvaluator(size).evaluate_all(clues, assignment)
    except Exception as exc:
        semantic_ok = False
        issues.append(f"Lỗi SemanticEvaluator: {exc}")

    if expected != "INCONSISTENT" and not semantic_ok:
        issues.append("Có manh mối không thỏa mãn hidden_status của puzzle.")
    elif expected == "INCONSISTENT" and semantic_ok:
        warnings.append("Puzzle đánh dấu INCONSISTENT nhưng toàn bộ manh mối vẫn thỏa hidden_status.")

    # 5. Mã hóa CNF cho toàn bộ tập manh mối
    initial_set = set(raw.get("initial_revealed", []))
    full_kb_state = {
        "size": size,
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

    cnf_summary = "-"
    uniq_status = "ERR"
    try:
        kb_data = encoder.build_kb(full_kb_state)
        cnf_summary = (
            f"P={kb_data['num_primary_vars']},A={kb_data['num_aux_vars']},C={kb_data['num_clauses']}"
        )

        # 6. Kiểm tra tính duy nhất của nghiệm (hỗ trợ cả 5x5)
        uniq_res = agent.check_uniqueness(kb_data)
        uniq_status = uniq_res["status"]
        if expected == "SOLVED" and uniq_status != UNIQUENESS_UNIQUE:
            issues.append(f"Màn chơi phải có nghiệm duy nhất (UNIQUE), nhưng thu được {uniq_status}.")
        elif expected == "UNKNOWN" and uniq_status == UNIQUENESS_NONE:
            issues.append("Màn chơi kỳ vọng UNKNOWN nhưng tập manh mối lại vô nghiệm (NO_SOLUTION).")
        elif expected == "INCONSISTENT" and uniq_status != UNIQUENESS_NONE:
            issues.append(f"Màn chơi kỳ vọng INCONSISTENT nhưng check_uniqueness trả về {uniq_status}.")
    except Exception as exc:
        issues.append(f"Lỗi mã hóa CNF / Uniqueness Check: {exc}")

    # 7. Chạy suy luận không đoán mò (No-Guess Solve) từ initial_revealed
    t0 = time.perf_counter()
    solve_status = "ERR"
    steps = 0
    revealed_final = 0
    total_cells = size * size
    try:
        trace = agent.solve_all(engine)
        steps = len(trace)
        final_state = engine.get_public_state()
        revealed_final = int(final_state["revealed_count"])
        if final_state["is_solved"]:
            solve_status = "SOLVED"
        elif trace and str(trace[-1].get("verdict", "")).upper() == VERDICT_INCONSISTENT:
            solve_status = VERDICT_INCONSISTENT
        else:
            solve_status = VERDICT_UNKNOWN

        if solve_status != expected:
            issues.append(
                f"Kết quả giải No-Guess là {solve_status} ({revealed_final}/{total_cells}), "
                f"không khớp kỳ vọng {expected}."
            )
    except Exception as exc:
        issues.append(f"Lỗi khi chạy DeductiveAgent.solve_all(): {exc}")
    elapsed = time.perf_counter() - t0

    return {
        "file": path.name,
        "size": f"{size}x{size}",
        "semantic": "PASS" if semantic_ok else "FAIL",
        "cnf": cnf_summary,
        "uniqueness": uniq_status,
        "solve": f"{solve_status} ({revealed_final}/{total_cells}, {steps}s)",
        "time_s": elapsed,
        "ok": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kiểm tra toàn diện các file puzzle JSON (schema, ngữ nghĩa, CNF, uniqueness, no-guess)."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Đường dẫn file hoặc thư mục puzzle cần kiểm tra (mặc định: Source/data/puzzles/*.json)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Coi các cảnh báo (ví dụ tên nhân vật chưa sắp theo bảng chữ cái) là lỗi.",
    )
    return parser.parse_args(argv)


def _collect_targets(raw_paths: list[str]) -> list[Path]:
    if not raw_paths:
        return sorted(DEFAULT_PUZZLES_DIR.glob("*.json"))
    targets: list[Path] = []
    for raw in raw_paths:
        p = Path(raw)
        if not p.exists():
            p = SOURCE_DIR / raw
        if p.is_dir():
            targets.extend(sorted(p.glob("*.json")))
        else:
            targets.append(p)
    return targets


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    targets = _collect_targets(args.paths)
    if not targets:
        print("Không tìm thấy file puzzle JSON nào để kiểm tra.")
        return 1

    results = [validate_puzzle_file(p) for p in targets]

    print("=" * 105)
    print(
        f"{'Puzzle':<22} | {'Size':^5} | {'Sem':^4} | {'CNF (P,A,C)':<18} | "
        f"{'Uniqueness':<18} | {'No-Guess Solve':<20} | {'Time':>6} | {'OK'}"
    )
    print("-" * 105)
    has_failure = False
    for r in results:
        ok = r["ok"] and (not args.strict or not r["warnings"])
        if not ok:
            has_failure = True
        status_label = "PASS" if ok else "FAIL"
        print(
            f"{r['file']:<22} | {r['size']:^5} | {r['semantic']:^4} | {r['cnf']:<18} | "
            f"{r['uniqueness']:<18} | {r['solve']:<20} | {r['time_s']:>5.3f}s | {status_label}"
        )
    print("=" * 105)

    for r in results:
        for w in r["warnings"]:
            print(f"[WARN] {r['file']}: {w}")
        for err in r["issues"]:
            print(f"[FAIL] {r['file']}: {err}")

    return 1 if has_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
