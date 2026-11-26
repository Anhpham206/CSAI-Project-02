# Bộ puzzle chuẩn của TV2

Các file JSON trong thư mục này đều được `GameEngine.load_from_file` đọc trực tiếp. Không đặt `manifest.json` hay file JSON phụ trợ ở đây vì GUI liệt kê mọi JSON trong thư mục.

| Puzzle | N | Kết quả mong đợi | Mục đích |
|---|---:|---|---|
| easy_3x3_01 | 3 | SOLVABLE | FACT |
| parity_3x3_02 | 3 | SOLVABLE | PARITY |
| compare_3x3_03 | 3 | SOLVABLE | COMPARE |
| regions_3x3_04 | 3 | SOLVABLE | BOUNDARY, CORNERS |
| compound_3x3_05 | 3 | SOLVABLE | COMPOUND AND |
| medium_4x4_01 | 4 | SOLVABLE | COMPARE |
| connectivity_4x4_02 | 4 | SOLVABLE | CONNECTIVITY ORTHOGONAL |
| regions_4x4_03 | 4 | SOLVABLE | BOUNDARY, CORNERS |
| ambiguous_4x4 | 4 | UNKNOWN | clue rỗng về ngữ nghĩa |
| stress_5x5_01 | 5 | SOLVABLE | vùng lớn, FACT |
| stress_5x5_02 | 5 | SOLVABLE | COMPOUND, stress |

Các puzzle mới được sinh tái lập bằng seed `20261125` trong `Source/tools/generate_puzzles.py`; bốn file mẫu còn lại là dữ liệu nền của TV1.
