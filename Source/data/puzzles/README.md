# Bộ puzzle trong `Source/data/puzzles/`

Các file JSON trong thư mục này được `GameEngine.load_from_file` đọc trực tiếp. Không đặt `manifest.json` hay file JSON phụ trợ ở đây vì GUI liệt kê mọi file `.json` trong thư mục.

## Danh sách puzzle hiện có
- `sample_3x3.json`: Màn $3\times3$ giải được hoàn toàn bằng suy luận không đoán mò (chứa đủ 6 loại manh mối cơ bản).
- `sample_4x4.json`: Màn $4\times4$ giải được hoàn toàn bằng suy luận không đoán mò.
- `ambiguous_3x3.json`: Màn $3\times3$ mơ hồ (nhiều nghiệm) để kiểm tra trạng thái `UNKNOWN`.
- `inconsistent_3x3.json`: Màn $3\times3$ mâu thuẫn để kiểm tra trạng thái `INCONSISTENT`.

## Tự kiểm tra khi thêm puzzle mới
Chạy công cụ kiểm tra toàn diện (schema, ngữ nghĩa, CNF, uniqueness và khả năng giải không đoán mò):

```bash
python Source/tools/validate_puzzles.py
# Hoặc kiểm tra riêng 1 file mới tạo:
python Source/tools/validate_puzzles.py Source/data/puzzles/<ten_file>.json
```
