# Hướng dẫn chạy mã nguồn (Source)

Thư mục này chứa toàn bộ mã nguồn của đồ án **Griductive Solver** (suy luận logic mệnh đề không đoán mò với SAT & giao diện Web HTML).

## 1. Yêu cầu hệ thống & Cài đặt môi trường
- Python **3.10 trở lên** (Windows có thể dùng `py` hoặc `python`).
- Giao diện Web sử dụng máy chủ **`http.server`** tích hợp sẵn trong Python standard library và tệp **`Source/gui/index.html`** tự chứa hoàn toàn (không cần cài đặt Flask/FastAPI hay kết nối CDN ngoài, chạy tốt cả khi offline).
- Tạo môi trường ảo (khuyến nghị) và cài các phụ thuộc phục vụ kiểm thử / thực nghiệm:

```bash
# Tạo & kích hoạt virtual environment (từ thư mục gốc repo hoặc Source/)
python -m venv .venv

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

# Linux / macOS
source .venv/bin/activate

# Cài đặt phụ thuộc
pip install -r Source/requirements.txt
# (hoặc `pip install -r requirements.txt` nếu đang đứng trong thư mục Source/)
```

## 2. Chạy giao diện Web (Web GUI)

Có thể khởi chạy từ **thư mục gốc repo** hoặc từ **thư mục `Source/`**:

```bash
# Từ thư mục gốc repo (CSAI-Project-02/)
python Source/main.py
# Windows: py Source/main.py

# Hoặc từ bên trong thư mục Source/
cd Source
python main.py
# Windows: py main.py
```

Lệnh trên sẽ khởi động máy chủ Web cục bộ tại `http://127.0.0.1:8000` (nếu cổng `8000` đang bận sẽ tự động chọn cổng trống khác và in URL ra terminal) và tự động mở trình duyệt mặc định. Nhấn `Ctrl+C` trong terminal để dừng máy chủ.

Các tùy chọn dòng lệnh cho Web GUI:
```bash
# Nạp sẵn một file câu đố cụ thể khi mở Web GUI
python Source/main.py --puzzle Source/data/puzzles/sample_4x4.json
# hoặc từ Source/:
python main.py --puzzle data/puzzles/sample_4x4.json

# Đổi cổng lắng nghe hoặc không tự động mở trình duyệt
python main.py --port 8080 --no-browser
python main.py --host 127.0.0.1 --port 8080
```

> Mặc định khi không truyền `--puzzle`, ứng dụng sẽ tự động nạp `data/puzzles/sample_3x3.json` để có thể chơi ngay.

### Các chức năng trên Web GUI
- **Load**: mở hộp thoại danh sách các câu đố sẵn có trong `Source/data/puzzles/` và cho phép tải lên bất kỳ tệp `.json` nào từ máy tính (`<input type="file" accept=".json">`).
- **Restart**: đưa bàn cờ về đúng trạng thái mở ban đầu (`initial_revealed`), xóa tô sáng và nhật ký suy diễn.
- **Hint**: gọi `POST /api/hint` (`agent.hint(public_state)`) để gợi ý 1 nước đi bị ép buộc chắc chắn (phát sáng vàng ô đích và làm nổi bật các manh mối kích hoạt) mà tuyệt đối không đọc đáp án ẩn; báo rõ `UNKNOWN` hoặc `INCONSISTENT` nếu không có nước đi chắc chắn.
- **Auto Solve / Stop**: lặp gọi `POST /api/step` mỗi ~400ms để quan sát từng thẻ lật dần trực quan và cập nhật Deduction Trace theo thời gian thực cho đến khi `SOLVED`, `UNKNOWN`, `INCONSISTENT` hoặc người dùng nhấn **Stop**.
- **Chơi thủ công (Luật Không Đoán Mò)**:
  - Nhấn vào thẻ đang úp để chọn (viền indigo), sau đó nhấn **Call CRIMINAL** (`C`) hoặc **Call INNOCENT** (`I`).
  - Banner phản hồi phân biệt rõ 4 trạng thái: `ACCEPTED`, `NOT_PROVABLE` (chưa chứng minh được — không cho phép đoán mò), `CONTRADICTED` (mâu thuẫn với manh mối hiện tại), và `INCONSISTENT` (tập manh mối tự mâu thuẫn).
- **Tô sáng vùng manh mối**: nhấn vào bất kỳ thẻ đã mở nào để gọi `GET /api/highlight?coord=...` và tô sáng xanh dương toàn bộ các ô được manh mối tham chiếu (nhấn lại hoặc nhấn **Clear Highlight** / `Esc` để tắt).
- **Deduction Trace / Move Log**: hiển thị đầy đủ lịch sử từng bước (`Step #`, `Coord`, `Verdict`, `Active Clues`, tóm tắt truy vấn SAT `KB ∧ ¬C_i` / `KB ∧ C_i`, và manh mối mới vừa lật).

## 3. Chạy chế độ dòng lệnh (CLI)

Chạy suy luận tự động không đoán mò và in chi tiết Deduction Trace ra terminal:

```bash
# Từ thư mục gốc repo:
python Source/main.py --cli --puzzle Source/data/puzzles/sample_3x3.json
python Source/main.py --cli --puzzle Source/data/puzzles/sample_4x4.json
python Source/main.py --cli --puzzle Source/data/puzzles/ambiguous_3x3.json
python Source/main.py --cli --puzzle Source/data/puzzles/inconsistent_3x3.json

# Hoặc từ bên trong thư mục Source/:
python main.py --cli --puzzle data/puzzles/sample_3x3.json
```

(Trên Windows có thể thay `python` bằng `py`.)

## 4. Chạy bộ kiểm thử tự động (Unit Tests)

```bash
# Từ thư mục gốc repo (CSAI-Project-02/):
python -m unittest discover -s Source/tests -v
# Windows: py -m unittest discover -s Source/tests -v

# Hoặc từ bên trong thư mục Source/:
python -m unittest discover -s tests -v

# Hoặc dùng pytest:
pytest Source/tests -v
```

## 5. Chạy thử nghiệm đánh giá hiệu năng (Benchmark)
Sau khi hoàn tất module thực nghiệm:
```bash
python Source/experiments/benchmark.py
```
