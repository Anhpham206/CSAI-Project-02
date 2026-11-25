"""
Bộ test kiểm tra DPLLSolver theo YÊU CẦU được giao cho Thành viên 3.

Nguyên tắc viết test:
  - Test được suy ra từ đề bài và quy ước của nhóm, KHÔNG suy ra từ code hiện tại.
  - Chỉ kiểm tra hành vi quan sát được từ bên ngoài (kết quả, model, stats),
    không phụ thuộc vào cách cài đặt bên trong (thứ tự chọn biến cụ thể, thử True
    hay False trước, cách đếm chi tiết...). Một bộ giải DPLL đúng bất kỳ đều phải pass.
  - Test nào fail nghĩa là code chưa đạt yêu cầu tương ứng, cần sửa code chứ không sửa test.

Nguồn yêu cầu:
  [PDF 4.3]  Đề bài mục 4.3 - DPLL SAT Solver (6 yêu cầu tối thiểu + assumptions).
  [PDF 3.4]  Đề bài mục 3.4 - Kiểm tra hệ quả logic bằng KB ^ ~C và KB ^ C.
  [PDF 4]    Đề bài mục 4 - Phải tự cài thuật toán chính, không dùng thư viện giải sẵn.
  [NHÓM]     Phân công trên Google Docs / README: module độc lập với luật game, nhận
             list[list[int]], hỗ trợ assumptions, bộ đếm cho MỖI lần gọi.
  [HĐ2]      Data Contract 2 (dùng chung với Agent của TV4):
             solve(cnf, assumptions=None) -> (is_sat, model, stats).
  [KẾ HOẠCH] Google Sheets ngày 3: tối ưu tốc độ DPLL trên màn 4x4 và 5x5.

Bảng đối chiếu yêu cầu -> nhóm test:
  Y1  Lan truyền đơn vị                       [PDF 4.3 - 1]
  Y2  Phát hiện xung đột                      [PDF 4.3 - 2]
  Y3  Chọn biến tất định                      [PDF 4.3 - 3]
  Y4  Phân nhánh đệ quy và quay lui           [PDF 4.3 - 4]
  Y5  Trả về SAT + nghiệm đầy đủ hoặc UNSAT   [PDF 4.3 - 5]
  Y6  Ghi nhận decisions/propagations/backtracks/runtime  [PDF 4.3 - 6], [NHÓM]
  Y7  Hỗ trợ assumptions                      [PDF 4.3], [NHÓM], [HĐ2]
  Y8  Đúng chuẩn giao tiếp với Agent          [HĐ2], [PDF 3.4]
  Y9  Tự cài đặt, độc lập luật game           [PDF 4], [NHÓM]
  Y10 Đúng đắn trên mọi CNF (so với vét cạn)  [PDF 4.3 - 5]
  Y11 Chạy được trên KB thực tế cỡ 4x4, 5x5   [KẾ HOẠCH], [PDF 4.5]

Chạy (đứng trong thư mục CSAI-Project-02):
  python -m unittest Source/tests/test_dpll_requirements.py -v
"""

from __future__ import annotations

import ast
import itertools
import os
import random
import subprocess
import sys
import time
import unittest
from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parent.parent
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from solver import DPLLSolver


# ======================================================================
# Hàm hỗ trợ (viết độc lập, không dùng lại bất kỳ hàm nào của dpll.py)
# ======================================================================

COUNTER_KEYS = ("decisions", "propagations", "backtracks")


def variables_of(cnf: list[list[int]], assumptions: list[int] | None = None) -> set[int]:
    """Tập các biến xuất hiện trong CNF và assumptions."""
    result = {abs(lit) for clause in cnf for lit in clause}
    result |= {abs(lit) for lit in (assumptions or [])}
    return result


def satisfies(cnf: list[list[int]], model: dict[int, bool]) -> bool:
    """Model có làm mọi mệnh đề đều đúng không (model phải có đủ biến)."""
    return all(any(model[abs(lit)] == (lit > 0) for lit in clause) for clause in cnf)


def brute_force_is_sat(cnf: list[list[int]], assumptions: list[int] | None = None) -> bool:
    """Đáp án chuẩn: thử hết bảng chân trị."""
    full = cnf + [[lit] for lit in (assumptions or [])]
    var_list = sorted(variables_of(full))
    for values in itertools.product((False, True), repeat=len(var_list)):
        model = dict(zip(var_list, values))
        if satisfies(full, model):
            return True
    return False


def random_cnf(rng: random.Random, num_vars: int, num_clauses: int,
               min_len: int = 1, max_len: int = 3) -> list[list[int]]:
    cnf = []
    for _ in range(num_clauses):
        size = rng.randint(min_len, min(max_len, num_vars))
        chosen = rng.sample(range(1, num_vars + 1), size)
        cnf.append([v if rng.random() < 0.5 else -v for v in chosen])
    return cnf


def unique_model_cnf(target: dict[int, bool]) -> list[list[int]]:
    """
    Tạo CNF có DUY NHẤT 1 nghiệm là `target`: chặn mọi phép gán khác.
    Mỗi mệnh đề dài đúng n literal nên ban đầu không có unit clause nào,
    solver bắt buộc phải phân nhánh (và quay lui) mới tìm ra nghiệm.
    """
    var_list = sorted(target)
    cnf = []
    for values in itertools.product((False, True), repeat=len(var_list)):
        assignment = dict(zip(var_list, values))
        if assignment != target:
            cnf.append([-v if assignment[v] else v for v in var_list])
    return cnf


def all_assignments_blocked_cnf(num_vars: int) -> list[list[int]]:
    """CNF chặn hết 2^n phép gán -> chắc chắn UNSAT, không có unit clause ban đầu."""
    var_list = list(range(1, num_vars + 1))
    return [[-v if val else v for v, val in zip(var_list, values)]
            for values in itertools.product((False, True), repeat=num_vars)]


def pigeonhole_cnf(pigeons: int, holes: int) -> list[list[int]]:
    """Bài toán chuồng bồ câu, UNSAT khi pigeons > holes."""
    def var(p: int, h: int) -> int:
        return p * holes + h + 1
    cnf = [[var(p, h) for h in range(holes)] for p in range(pigeons)]
    for h in range(holes):
        for p1, p2 in itertools.combinations(range(pigeons), 2):
            cnf.append([-var(p1, h), -var(p2, h)])
    return cnf


def exactly_k_cnf(cells: list[int], k: int) -> list[list[int]]:
    """Mã hóa tổ hợp EXACTLY(k, cells) (cách mã hóa được đề bài cho phép ở mục 3.3)."""
    n = len(cells)
    clauses = [[-v for v in combo] for combo in itertools.combinations(cells, k + 1)]
    clauses += [list(combo) for combo in itertools.combinations(cells, n - k + 1)]
    return clauses


def neighbors(var: int, n: int) -> list[int]:
    row, col = divmod(var - 1, n)
    result = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            r, c = row + dr, col + dc
            if (dr, dc) != (0, 0) and 0 <= r < n and 0 <= c < n:
                result.append(r * n + c + 1)
    return result


def classify(solver: DPLLSolver, kb: list[list[int]], var: int) -> str:
    """Phân loại ô đúng như mục 3.4 của đề bài."""
    if not solver.solve(kb)[0]:
        return "INCONSISTENT"
    sat_if_innocent = solver.solve(kb, assumptions=[-var])[0]
    sat_if_criminal = solver.solve(kb, assumptions=[var])[0]
    if not sat_if_innocent:
        return "CRIMINAL"
    if not sat_if_criminal:
        return "INNOCENT"
    return "UNKNOWN"


def counters(stats: dict) -> tuple:
    return tuple(stats[key] for key in COUNTER_KEYS)


class SolverTestCase(unittest.TestCase):
    """Lớp cha: mỗi lần gọi solver đều kiểm tra luôn tính hợp lệ của kết quả."""

    def solve(self, cnf, assumptions=None, solver=None):
        solver = solver or DPLLSolver()
        if assumptions is None:
            result = solver.solve(cnf)
        else:
            result = solver.solve(cnf, assumptions=assumptions)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)
        is_sat, model, stats = result
        self.assertIsInstance(is_sat, bool)
        if is_sat:
            self.assertIsInstance(model, dict)
            missing = variables_of(cnf, assumptions) - set(model)
            self.assertFalse(missing, f"Model thiếu giá trị cho các biến {sorted(missing)}")
            self.assertTrue(satisfies(cnf, model), "Solver báo SAT nhưng model không thỏa CNF")
            for lit in assumptions or []:
                self.assertEqual(model[abs(lit)], lit > 0, f"Model vi phạm assumption {lit}")
        else:
            self.assertIsNone(model, "UNSAT thì model phải là None")
        return is_sat, model, stats


# ======================================================================
# Y1. Lan truyền đơn vị
# ======================================================================

class TestY1UnitPropagation(SolverTestCase):
    def test_chain_is_solved_without_any_decision(self) -> None:
        # x1 đúng, x1 -> x2 -> ... -> x50: chỉ cần lan truyền là ra nghiệm
        n = 50
        cnf = [[1]] + [[-i, i + 1] for i in range(1, n)]
        is_sat, model, stats = self.solve(cnf)
        self.assertTrue(is_sat)
        self.assertTrue(all(model[i] for i in range(1, n + 1)))
        self.assertEqual(stats["decisions"], 0, "Có unit propagation thì không cần phân nhánh")
        self.assertGreaterEqual(stats["propagations"], n - 1)

    def test_propagation_is_applied_after_each_decision(self) -> None:
        # x1 <-> x2 <-> ... <-> x20, không có unit clause ban đầu.
        # Quyết định 1 biến bất kỳ thì lan truyền phải ép được 19 biến còn lại
        # => đúng 1 decision là đủ, dù chọn biến nào hay gán giá trị nào trước.
        n = 20
        cnf = []
        for i in range(1, n):
            cnf += [[-i, i + 1], [i, -(i + 1)]]
        is_sat, model, stats = self.solve(cnf)
        self.assertTrue(is_sat)
        self.assertEqual(len({model[i] for i in range(1, n + 1)}), 1)
        self.assertEqual(stats["decisions"], 1)
        self.assertGreaterEqual(stats["propagations"], n - 1)

    def test_unsat_found_by_propagation_alone(self) -> None:
        cnf = [[1], [-1, 2], [-2, 3], [-3, -1]]
        is_sat, _, stats = self.solve(cnf)
        self.assertFalse(is_sat)
        self.assertEqual(stats["decisions"], 0)


# ======================================================================
# Y2. Phát hiện xung đột
# ======================================================================

class TestY2ConflictDetection(SolverTestCase):
    def test_conflict_detected_before_branching(self) -> None:
        # [1] và [-1] mâu thuẫn ngay; các biến 2..40 không liên quan.
        # Phát hiện xung đột đúng lúc thì không được phân nhánh vào các biến thừa.
        cnf = [[1], [-1]] + [[i, i + 1] for i in range(2, 40)]
        is_sat, _, stats = self.solve(cnf)
        self.assertFalse(is_sat)
        self.assertEqual(stats["decisions"], 0)

    def _check_early_conflict(self, bad_var: int, num_vars: int) -> None:
        # Gán bad_var = True sẽ lập tức xung đột (ép x và ~x cùng lúc).
        # Nếu chỉ kiểm tra xung đột khi đã gán đủ mọi biến thì sẽ duyệt ~2^num_vars nhánh.
        helper = num_vars + 1
        cnf = [[-bad_var, helper], [-bad_var, -helper]]
        others = [v for v in range(1, num_vars + 1) if v != bad_var]
        cnf += [[others[i], others[i + 1]] for i in range(0, len(others) - 1, 2)]
        is_sat, model, stats = self.solve(cnf)
        self.assertTrue(is_sat)
        self.assertFalse(model[bad_var])
        self.assertLessEqual(stats["decisions"], 2 * (num_vars + 1))
        self.assertLessEqual(stats["backtracks"], num_vars + 1)

    def test_early_conflict_small_index(self) -> None:
        self._check_early_conflict(bad_var=1, num_vars=40)

    def test_early_conflict_large_index(self) -> None:
        self._check_early_conflict(bad_var=40, num_vars=40)

    def test_empty_clause_means_unsat(self) -> None:
        is_sat, _, _ = self.solve([[1, 2], []])
        self.assertFalse(is_sat)

    def test_classic_unsat_formulas(self) -> None:
        for name, cnf in [
            ("mọi tổ hợp 2 biến bị chặn", [[1, 2], [1, -2], [-1, 2], [-1, -2]]),
            ("chặn hết 2^4 phép gán", all_assignments_blocked_cnf(4)),
            ("chuồng bồ câu 4 -> 3", pigeonhole_cnf(4, 3)),
            ("chuồng bồ câu 5 -> 4", pigeonhole_cnf(5, 4)),
        ]:
            with self.subTest(name):
                self.assertFalse(self.solve(cnf)[0])


# ======================================================================
# Y3. Chọn biến tất định
# ======================================================================

DETERMINISM_SCRIPT = r"""
import random, sys
sys.path.insert(0, sys.argv[1])
from solver import DPLLSolver
rng = random.Random(99)
out = []
for _ in range(30):
    n = rng.randint(5, 15)
    cnf = []
    for _ in range(rng.randint(5, 60)):
        vs = rng.sample(range(1, n + 1), rng.randint(1, 3))
        cnf.append([v if rng.random() < 0.5 else -v for v in vs])
    s, m, st = DPLLSolver().solve(cnf)
    out.append((s, sorted(m.items()) if m else None,
                st["decisions"], st["propagations"], st["backtracks"]))
print(repr(out))
"""


class TestY3DeterministicSelection(SolverTestCase):
    def test_repeated_calls_give_identical_result(self) -> None:
        rng = random.Random(2026)
        for case in range(30):
            cnf = random_cnf(rng, rng.randint(5, 15), rng.randint(5, 60))
            first = self.solve(cnf)
            for _ in range(3):
                again = self.solve(cnf)
                with self.subTest(case=case):
                    self.assertEqual(again[0], first[0])
                    self.assertEqual(again[1], first[1])
                    self.assertEqual(counters(again[2]), counters(first[2]))

    def test_same_result_across_separate_python_processes(self) -> None:
        # Chạy ở 2 tiến trình với PYTHONHASHSEED khác nhau: nếu solver chọn biến
        # dựa vào thứ tự duyệt set/dict không ổn định thì kết quả sẽ khác nhau.
        outputs = []
        for seed in ("0", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            proc = subprocess.run(
                [sys.executable, "-c", DETERMINISM_SCRIPT, str(SOURCE_DIR)],
                capture_output=True, text=True, env=env, timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            outputs.append(proc.stdout)
        self.assertEqual(outputs[0], outputs[1])


# ======================================================================
# Y4. Phân nhánh đệ quy và quay lui
# ======================================================================

class TestY4BranchingAndBacktracking(SolverTestCase):
    def test_finds_the_only_model_wherever_it_is(self) -> None:
        # Nghiệm duy nhất có thể nằm ở bất kỳ nhánh nào của cây tìm kiếm,
        # nên solver chỉ tìm ra được nếu thật sự quay lui và thử nhánh còn lại.
        n = 7
        rng = random.Random(5)
        targets = [
            {v: True for v in range(1, n + 1)},
            {v: False for v in range(1, n + 1)},
            {v: v % 2 == 0 for v in range(1, n + 1)},
        ] + [{v: rng.random() < 0.5 for v in range(1, n + 1)} for _ in range(10)]

        backtracks = []
        for idx, target in enumerate(targets):
            with self.subTest(target=idx):
                is_sat, model, stats = self.solve(unique_model_cnf(target))
                self.assertTrue(is_sat)
                self.assertEqual({v: model[v] for v in target}, target)
                self.assertGreaterEqual(stats["decisions"], 1)
                backtracks.append(stats["backtracks"])

        # Toàn True và toàn False nằm ở 2 đầu cây: dù thử giá trị nào trước,
        # ít nhất 1 trong 2 trường hợp bắt buộc phải quay lui.
        self.assertGreaterEqual(max(backtracks[0], backtracks[1]), 1)

    def test_unsat_requires_exploring_both_branches(self) -> None:
        is_sat, _, stats = self.solve(all_assignments_blocked_cnf(5))
        self.assertFalse(is_sat)
        self.assertGreaterEqual(stats["decisions"], 1)
        self.assertGreaterEqual(stats["backtracks"], 1)

    def test_deep_search_with_many_variables(self) -> None:
        # KB 5x5 khi mã hóa đếm bằng biến phụ (sequential counter...) có thể lên
        # tới hàng nghìn biến. Solver đệ quy không được crash vì quá sâu.
        n = 1500
        cnf = [[i, i + 1] for i in range(1, n, 2)]
        try:
            is_sat, _, _ = self.solve(cnf)
        except RecursionError:
            self.fail("Solver bị RecursionError trên công thức 1500 biến")
        self.assertTrue(is_sat)


# ======================================================================
# Y5. Trả về SAT + nghiệm đầy đủ, hoặc UNSAT
# ======================================================================

class TestY5Result(SolverTestCase):
    def test_sat_model_assigns_every_variable(self) -> None:
        cnf = [[1, -7], [3, 9], [-9, 12]]
        is_sat, model, _ = self.solve(cnf)
        self.assertTrue(is_sat)
        self.assertTrue(all(isinstance(v, bool) for v in model.values()))

    def test_unsat_has_no_model(self) -> None:
        is_sat, model, _ = self.solve([[1], [-1]])
        self.assertIs(is_sat, False)
        self.assertIsNone(model)

    def test_empty_formula_is_sat(self) -> None:
        self.assertTrue(self.solve([])[0])

    def test_unusual_but_valid_clauses(self) -> None:
        # Encoder có thể sinh literal trùng hoặc mệnh đề luôn đúng; solver vẫn phải đúng
        for cnf, expected in [
            ([[1, 1, 1]], True),
            ([[1, -1]], True),
            ([[1, -1], [2], [-2]], False),
            ([[2, 2], [-2, -2]], False),
            ([[5, -5, 3], [-3, -3], [3, 4]], True),
        ]:
            with self.subTest(cnf=cnf):
                self.assertEqual(self.solve(cnf)[0], expected)


# ======================================================================
# Y6. Ghi nhận decisions, propagations, backtracks, runtime
# ======================================================================

class TestY6Statistics(SolverTestCase):
    def test_all_four_statistics_present_with_correct_types(self) -> None:
        for cnf in ([[1, 2]], [[1], [-1]], pigeonhole_cnf(4, 3), []):
            with self.subTest(cnf=cnf[:3]):
                _, _, stats = self.solve(cnf)
                self.assertIsInstance(stats, dict)
                for key in COUNTER_KEYS:
                    self.assertIn(key, stats)
                    self.assertIsInstance(stats[key], int)
                    self.assertNotIsInstance(stats[key], bool)
                    self.assertGreaterEqual(stats[key], 0)
                self.assertIn("runtime", stats)
                self.assertIsInstance(stats["runtime"], float)
                self.assertGreaterEqual(stats["runtime"], 0.0)

    def test_statistics_are_per_call_not_accumulated(self) -> None:
        solver = DPLLSolver()
        cnf = pigeonhole_cnf(4, 3)
        first = self.solve(cnf, solver=solver)[2]
        self.solve(pigeonhole_cnf(5, 4), solver=solver)
        again = self.solve(cnf, solver=solver)[2]
        self.assertEqual(counters(first), counters(again))

    def test_counters_reflect_the_search(self) -> None:
        # Không cần đoán, không xung đột -> 0 decision, 0 backtrack
        _, _, easy = self.solve([[1], [-1, 2], [-2, 3]])
        self.assertEqual(easy["decisions"], 0)
        self.assertEqual(easy["backtracks"], 0)
        self.assertGreaterEqual(easy["propagations"], 2)

        # Bài khó phải có cả decision lẫn backtrack
        _, _, hard = self.solve(pigeonhole_cnf(5, 4))
        self.assertGreater(hard["decisions"], 0)
        self.assertGreater(hard["backtracks"], 0)
        self.assertGreater(hard["propagations"], 0)

    def test_runtime_is_measured_in_seconds(self) -> None:
        start = time.perf_counter()
        _, _, stats = self.solve(pigeonhole_cnf(6, 5))
        elapsed = time.perf_counter() - start
        self.assertGreater(stats["runtime"], 0.0)
        self.assertLessEqual(stats["runtime"], elapsed + 1e-3)
        # Không được là mili giây hay nano giây
        self.assertGreater(stats["runtime"], elapsed * 0.3)


# ======================================================================
# Y7. Hỗ trợ assumptions
# ======================================================================

class TestY7Assumptions(SolverTestCase):
    def test_assumptions_equal_adding_temporary_unit_clauses(self) -> None:
        # Đề bài: solver có thể nhận assumptions hoặc giải KB + unit clause tạm.
        # Hai cách phải cho cùng kết quả SAT/UNSAT (và khớp vét cạn).
        rng = random.Random(11)
        for case in range(200):
            n = rng.randint(2, 9)
            cnf = random_cnf(rng, n, rng.randint(1, 30))
            picked = rng.sample(range(1, n + 1), rng.randint(1, min(3, n)))
            assumptions = [v if rng.random() < 0.5 else -v for v in picked]
            with self.subTest(case=case, cnf=cnf, assumptions=assumptions):
                with_assumptions = self.solve(cnf, assumptions=assumptions)[0]
                with_units = self.solve(cnf + [[lit] for lit in assumptions])[0]
                expected = brute_force_is_sat(cnf, assumptions)
                self.assertEqual(with_assumptions, expected)
                self.assertEqual(with_units, expected)

    def test_contradicting_assumptions_are_unsat(self) -> None:
        self.assertFalse(self.solve([[1, 2]], assumptions=[2, -2])[0])

    def test_assumptions_on_variables_not_in_cnf(self) -> None:
        is_sat, model, _ = self.solve([[1, 2]], assumptions=[-9])
        self.assertTrue(is_sat)
        self.assertFalse(model[9])

    def test_none_and_empty_assumptions(self) -> None:
        cnf = [[1, -2], [2, 3], [-1, -3]]
        self.assertEqual(self.solve(cnf)[0], self.solve(cnf, assumptions=[])[0])
        self.assertEqual(self.solve(cnf)[0], self.solve(cnf, assumptions=None)[0])


# ======================================================================
# Y8. Đúng chuẩn giao tiếp với Agent (Data Contract 2 + mục 3.4)
# ======================================================================

class TestY8AgentContract(SolverTestCase):
    def test_signature(self) -> None:
        solver = DPLLSolver()
        self.solve([[1, 2]], solver=solver)
        result = solver.solve(cnf=[[1, 2]], assumptions=[1])
        self.assertEqual(len(result), 3)

    def test_input_is_not_modified(self) -> None:
        # Agent dùng lại cùng 1 KB cho rất nhiều truy vấn, solver không được sửa KB
        cnf = [[1, 2, 2], [-1, 3], [-2, -3], [1, -1], [4]]
        assumptions = [-3, 2]
        cnf_copy = [list(c) for c in cnf]
        assumptions_copy = list(assumptions)
        DPLLSolver().solve(cnf, assumptions=assumptions)
        self.assertEqual(cnf, cnf_copy)
        self.assertEqual(assumptions, assumptions_copy)

    def test_no_state_leaks_between_queries(self) -> None:
        # Một instance dùng cho nhiều truy vấn phải cho kết quả giống instance mới
        rng = random.Random(3)
        shared = DPLLSolver()
        for case in range(60):
            cnf = random_cnf(rng, 8, rng.randint(3, 30))
            assumptions = rng.choice([None, [1], [-1], [2, -3]])
            with self.subTest(case=case):
                a = self.solve(cnf, assumptions, solver=shared)
                b = self.solve(cnf, assumptions, solver=DPLLSolver())
                self.assertEqual(a[0], b[0])
                self.assertEqual(a[1], b[1])
                self.assertEqual(counters(a[2]), counters(b[2]))

    def test_example_in_section_3_4(self) -> None:
        kb = [[1, 2], [-1, 2]]  # A = 1, B = 2
        solver = DPLLSolver()
        self.assertEqual(classify(solver, kb, 2), "CRIMINAL")
        self.assertEqual(classify(solver, kb, 1), "UNKNOWN")

    def test_innocent_and_inconsistent(self) -> None:
        solver = DPLLSolver()
        self.assertEqual(classify(solver, [[-1, -2], [2]], 1), "INNOCENT")
        self.assertEqual(classify(solver, [[1], [-1, 2], [-2, -1]], 3), "INCONSISTENT")


# ======================================================================
# Y9. Tự cài đặt, không dùng thư viện SAT, độc lập với luật game
# ======================================================================

class TestY9SelfImplemented(unittest.TestCase):
    FORBIDDEN = {"pysat", "pycosat", "z3", "ortools", "pyeda", "sympy", "pycryptosat", "satpy"}
    GAME_MODULES = {"game", "logic", "agent", "gui", "experiments"}

    def _imported_modules(self) -> set[str]:
        names = set()
        for path in (SOURCE_DIR / "solver").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names |= {alias.name.split(".")[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names.add(node.module.split(".")[0])
        return names

    def test_no_external_sat_library(self) -> None:
        imported = self._imported_modules()
        self.assertFalse(imported & self.FORBIDDEN, f"Dùng thư viện SAT ngoài: {imported & self.FORBIDDEN}")
        non_stdlib = imported - set(sys.stdlib_module_names)
        self.assertFalse(non_stdlib, f"Solver import thư viện ngoài: {non_stdlib}")

    def test_independent_from_game_rules(self) -> None:
        imported = self._imported_modules()
        self.assertFalse(imported & self.GAME_MODULES,
                         f"Solver không được phụ thuộc module game: {imported & self.GAME_MODULES}")


# ======================================================================
# Y10. Đúng đắn trên CNF bất kỳ (so với vét cạn)
# ======================================================================

class TestY10CrossCheck(SolverTestCase):
    def test_random_mixed_length_cnf(self) -> None:
        rng = random.Random(42)
        for case in range(300):
            cnf = random_cnf(rng, rng.randint(1, 9), rng.randint(1, 35))
            with self.subTest(case=case, cnf=cnf):
                self.assertEqual(self.solve(cnf)[0], brute_force_is_sat(cnf))

    def test_random_3sat_near_phase_transition(self) -> None:
        # Tỉ lệ mệnh đề/biến ~ 4.26 là vùng khó nhất, khoảng một nửa SAT, một nửa UNSAT
        rng = random.Random(426)
        results = []
        for case in range(120):
            n = rng.randint(6, 10)
            cnf = random_cnf(rng, n, round(4.26 * n), min_len=3, max_len=3)
            expected = brute_force_is_sat(cnf)
            results.append(expected)
            with self.subTest(case=case):
                self.assertEqual(self.solve(cnf)[0], expected)
        self.assertTrue(any(results) and not all(results), "Bộ dữ liệu phải có cả SAT và UNSAT")


# ======================================================================
# Y11. Chạy được trên KB thực tế cỡ 4x4 và 5x5
# ======================================================================

class TestY11RealisticBoards(SolverTestCase):
    # Ngưỡng thời gian cho TOÀN BỘ quá trình tự giải 1 màn (nhóm có thể chỉnh)
    TIME_LIMIT = {4: 5.0, 5: 20.0}

    def _auto_solve(self, n: int, seed: int) -> None:
        """
        Mô phỏng Agent tự giải 1 màn n x n:
          - Đáp án ẩn ngẫu nhiên, mỗi ô có clue EXACTLY(số Criminal hàng xóm).
          - Ban đầu mở 2 ô + clue số Criminal của từng hàng.
          - Mỗi bước hỏi solver KB ^ ~C và KB ^ C cho mọi ô chưa mở, mở ô bị ép đầu tiên.
        Kiểm tra:
          - Mọi kết luận của solver phải khớp đáp án ẩn (vì đáp án ẩn là 1 model của KB).
          - KB không bao giờ bị báo UNSAT sai.
          - Tổng thời gian nằm trong ngưỡng.
        """
        rng = random.Random(seed)
        size = n * n
        hidden = {v: rng.random() < 0.4 for v in range(1, size + 1)}

        def cell_clue(v: int) -> list[list[int]]:
            region = neighbors(v, n)
            return exactly_k_cnf(region, sum(hidden[u] for u in region))

        kb: list[list[int]] = []
        for r in range(n):
            row = [r * n + c + 1 for c in range(n)]
            kb += exactly_k_cnf(row, sum(hidden[u] for u in row))
        known = set(rng.sample(range(1, size + 1), 2))
        for v in known:
            kb.append([v] if hidden[v] else [-v])
            kb += cell_clue(v)

        solver = DPLLSolver()
        start = time.perf_counter()
        while len(known) < size:
            forced = None
            for v in range(1, size + 1):
                if v in known:
                    continue
                sat_if_innocent = self.solve(kb, [-v], solver)[0]
                sat_if_criminal = self.solve(kb, [v], solver)[0]
                truth_sat = sat_if_criminal if hidden[v] else sat_if_innocent
                self.assertTrue(truth_sat, f"Solver báo UNSAT sai ở ô {v}")
                if not sat_if_innocent or not sat_if_criminal:
                    verdict = not sat_if_innocent
                    self.assertEqual(verdict, hidden[v], f"Solver kết luận sai ở ô {v}")
                    forced = forced or v
            if forced is None:
                break
            known.add(forced)
            kb.append([forced] if hidden[forced] else [-forced])
            kb += cell_clue(forced)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, self.TIME_LIMIT[n],
                        f"Tự giải màn {n}x{n} mất {elapsed:.2f}s, vượt ngưỡng {self.TIME_LIMIT[n]}s")

    def test_auto_solve_4x4_boards(self) -> None:
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                self._auto_solve(4, seed)

    def test_auto_solve_5x5_boards(self) -> None:
        for seed in (1, 2):
            with self.subTest(seed=seed):
                self._auto_solve(5, seed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
