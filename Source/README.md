# Hướng dẫn chạy mã nguồn (Source)

Thư mục này chứa toàn bộ mã nguồn của đồ án **Griductive Solver**.

## 1. Yêu cầu hệ thống
- Python 3.10 trở lên.
- Đã cài đặt các phụ thuộc ghi trong `requirements.txt`:
  ```bash
  pip install -r requirements.txt
  ```

## 2. Cách khởi chạy

### Chạy giao diện đồ họa (GUI)
Từ thư mục `Source`, thực thi lệnh:
```bash
python main.py
```
Giao diện cung cấp các tính năng:
- Chọn câu đố từ danh sách có sẵn (Load).
- Chơi thủ công bằng cách chọn ô và gán nhãn CRIMINAL hoặc INNOCENT.
- Yêu cầu gợi ý bước đi kế tiếp (Hint).
- Tự động suy luận hoàn tất ván đấu (Auto Solve).
- Làm mới trạng thái ván cờ (Restart).

### Chạy thử nghiệm đánh giá hiệu năng
Để thực hiện đo lường các trường hợp $3 \times 3$, $4 \times 4$ và $5 \times 5$:
```bash
python experiments/benchmark.py
```
Kết quả đo đạc (thời gian chạy, số bước quay lui, số mệnh đề sinh ra) sẽ được in ra màn hình hoặc ghi vào file log tương ứng.
