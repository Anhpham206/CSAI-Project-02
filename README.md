# Đồ án 2: Griductive Solver

**Môn học:** Nhập môn Trí tuệ Nhân tạo (CSC14003)
**Trường:** Đại học Khoa học Tự nhiên – ĐHQG-HCM

---

## 1. Giới thiệu đề tài

Đồ án này tập trung vào việc hiện thực chương trình giải trò chơi suy luận dạng lưới mang tên **Griductive**. Trò chơi diễn ra trên một bảng kích thước $N \times N$ (thông thường là $3 \times 3$, $4 \times 4$ hoặc $5 \times 5$), trong đó mỗi ô là một nhân vật mang thân phận ẩn: **Tội phạm (Criminal)** hoặc **Vô tội (Innocent)** kèm theo một gợi ý (clue).

Nguyên tắc cốt lõi của bài toán là **không đoán mò (no-guess)**. Mọi kết luận về thân phận của nhân vật chỉ được chấp nhận khi nó là hệ quả logic tất yếu từ tập tri thức đã mở hiện tại. Khi một phán đoán đúng được chứng minh, thẻ của nhân vật đó sẽ được lật để bổ sung thêm gợi ý mới vào cơ sở tri thức (Knowledge Base).

Chương trình hướng tới các mục tiêu cụ thể:

- Tự động chuyển đổi các gợi ý từ ngôn ngữ cấu trúc sang dạng chuẩn tắc hội (CNF).
- Tự cài đặt thuật toán kiểm tra tính thỏa được của mệnh đề logic **DPLL (Davis-Putnam-Logemann-Loveland)** không dùng thư viện giải SAT bên ngoài.
- Xây dựng tác tử suy luận tự động (Deductive Logic Agent) để giải quyết từng bước bàn cờ.
- Xây dựng giao diện người dùng (GUI) cho phép người chơi thao tác thủ công, yêu cầu gợi ý hoặc kích hoạt chế độ tự động giải.

---

## 2. Kiến trúc hệ thống và Cấu trúc thư mục

Hệ thống được thiết kế theo hướng phân tách rành mạch hai vai trò độc lập theo đúng yêu cầu đề bài:

- **Game Engine:** Nắm giữ toàn bộ trạng thái gốc của ván cờ, bao gồm đáp án ẩn và các gợi ý chưa được lật. Đóng vai trò là trọng tài kiểm tra các phán đoán từ người chơi hoặc tác tử.
- **Logic Agent:** Chỉ tiếp nhận các thông tin công khai (các ô đã lật và gợi ý tương ứng). Tác tử không được phép đọc các nhãn ẩn để suy luận mà hoàn toàn dựa vào bộ giải SAT.

### Sơ đồ cấu trúc thư mục

```text
Project2/
├── docs/
│   └── AI - Project 2.pdf          # Đề bài và yêu cầu chi tiết đồ án
├── Source/
│   ├── main.py                     # Điểm khởi động chính của chương trình (GUI / CLI)
│   ├── requirements.txt            # Danh sách các thư viện phụ trợ
│   ├── README.md                   # Hướng dẫn chi tiết cách chạy mã nguồn
│   ├── game/                       # Quản lý trạng thái và luật chơi (Game Engine)
│   │   ├── __init__.py
│   │   ├── board.py                # Biểu diễn bảng cờ, tọa độ và nhân vật
│   │   └── engine.py               # Xử lý lật thẻ, kiểm tra phán quyết
│   ├── logic/                      # Biểu diễn tri thức và chuyển đổi CNF
│   │   ├── __init__.py
│   │   ├── clues.py                # Định nghĩa các mẫu gợi ý (FACT, SAME, EXACTLY, ...)
│   │   ├── encoder.py              # Bộ chuyển đổi gợi ý sang các mệnh đề CNF
│   │   └── evaluator.py            # Bộ đánh giá ngữ nghĩa trực tiếp cho từng gợi ý
│   ├── solver/                     # Bộ giải DPLL SAT Solver tự cài đặt
│   │   ├── __init__.py
│   │   └── dpll.py                 # Thuật toán DPLL: Unit propagation, Backtracking
│   ├── agent/                      # Tác tử suy luận tự động
│   │   ├── __init__.py
│   │   └── deductive_agent.py      # Vòng lặp suy luận, kiểm tra tính duy nhất, Hint
│   ├── gui/                        # Giao diện người dùng
│   │   ├── __init__.py
│   │   └── app.py                  # Giao diện đồ họa (hiển thị lưới, phán đoán, gợi ý)
│   ├── experiments/                # Kịch bản thực nghiệm và đánh giá
│   │   ├── __init__.py
│   │   └── benchmark.py            # Đo đạc thời gian, số bước quay lui, số mệnh đề
│   └── data/
│       └── puzzles/                # Chứa các file câu đố mẫu (3x3, 4x4, 5x5)
│           └── .gitkeep
├── .gitignore                      # Cấu hình bỏ qua các file tạm của Git
└── README.md                       # Tài liệu tổng quan dự án
```

---

## 3. Các thành phần logic chính

### 3.1. Biến mệnh đề

Mỗi nhân vật $i$ tại ô cờ được ánh xạ sang một biến Boolean duy nhất:

- $C_i = \text{True}$: Nhân vật $i$ là Tội phạm (Criminal).
- $C_i = \text{False}$: Nhân vật $i$ là Vô tội (Innocent).

Các biến phụ trợ (auxiliary variables) được sinh ra một cách nhất quán khi mã hóa các ràng buộc số lượng hoặc các gợi ý mở rộng, giữ tách biệt với các biến nguyên thủy $C_i$.

### 3.2. Mẫu gợi ý (Clue Templates)

Chương trình hỗ trợ 6 mẫu gợi ý cơ bản:

- `FACT`: Xác định trực tiếp trạng thái một người ($C_i$ hoặc $\neg C_i$).
- `SAME`: Hai người cùng trạng thái ($C_i \leftrightarrow C_j$).
- `DIFFERENT`: Hai người khác trạng thái ($C_i \oplus C_j$).
- `EXACTLY(k, R)`: Chính xác $k$ người trong vùng $R$ là Criminal ($\sum_{i \in R} C_i = k$).
- `AT_LEAST(k, R)`: Ít nhất $k$ người trong vùng $R$ là Criminal ($\sum_{i \in R} C_i \ge k$).
- `AT_MOST(k, R)`: Nhiều nhất $k$ người trong vùng $R$ là Criminal ($\sum_{i \in R} C_i \le k$).

Ngoài ra, nhóm dự kiến bổ sung thêm ít nhất 2 dạng gợi ý mở rộng theo yêu cầu (như ràng buộc tính chẵn lẻ `PARITY`, so sánh số lượng giữa hai vùng hoặc ràng buộc liên thông).

### 3.3. Cơ chế suy luận (Entailment via SAT)

Một gán trị thỏa mãn (satisfying assignment) chỉ là một trường hợp khả dĩ. Để đưa ra phán đoán chắc chắn tại bước $t$, cơ sở tri thức $KB_t$ phải kéo theo kết luận đó về mặt logic:

- $KB_t \models C_i \iff KB_t \land \neg C_i$ là **UNSAT** $\rightarrow$ Kết luận: **CRIMINAL**.
- $KB_t \models \neg C_i \iff KB_t \land C_i$ là **UNSAT** $\rightarrow$ Kết luận: **INNOCENT**.
- Nếu cả hai trường hợp đều **SAT** $\rightarrow$ Trạng thái: **UNKNOWN** (chưa đủ dữ liệu để chứng minh, không được đoán).
- Nếu $KB_t$ bản thân nó rơi vào trạng thái vô nghiệm $\rightarrow$ Báo lỗi **INCONSISTENT**.

Đối với thao tác của người chơi trên giao diện:

- Nếu phán đoán chưa thể chứng minh $\rightarrow$ Thông báo `NOT_PROVABLE`.
- Nếu phán đoán đi ngược lại với logic hiện tại $\rightarrow$ Thông báo `CONTRADICTED`.

---

## 4. Hướng dẫn cài đặt và sử dụng

### 4.1. Yêu cầu môi trường

- Python phiên bản từ 3.10 trở lên.
- Hệ điều hành: Windows, macOS hoặc Linux.

### 4.2. Cài đặt

1. Tải hoặc clone mã nguồn về máy:
   ```bash
   git clone https://github.com/Anhpham206/CSAI-Project-02.git
   cd CSAI-Project-02
   ```
2. Cài đặt các thư viện bổ trợ (nếu có):
   ```bash
   pip install -r Source/requirements.txt
   ```

### 4.3. Chạy chương trình

- **Khởi động giao diện người dùng:**
  ```bash
  python Source/main.py
  ```
- **Chạy ở chế độ dòng lệnh (CLI):**
  ```bash
  python Source/main.py --cli --puzzle Source/data/puzzles/sample_3x3.json
  ```
- **Chạy kiểm thử và thực nghiệm:**
  ```bash
  python Source/experiments/benchmark.py
  ```

---

## 5. Kế hoạch thực nghiệm và Đánh giá

Chương trình sẽ được thử nghiệm trên bộ câu đố chuẩn với các kích thước:

- Lưới $3 \times 3$ và $4 \times 4$ với độ phức tạp tăng dần.
- Lưới $5 \times 5$ phục vụ cho việc kiểm tra tải và giới hạn xử lý (stress test).

Các chỉ số được ghi nhận sau mỗi lượt giải gồm:

1. Số lượng biến nguyên thủy và biến phụ trợ được tạo ra.
2. Số lượng mệnh đề trong dạng chuẩn CNF.
3. Tổng số lượt gọi đến bộ giải SAT.
4. Số bước gán (decisions), số lượt lan truyền đơn vị (propagations) và số lần quay lui (backtracks).
5. Số bước suy luận (deduction steps) để hoàn thành bàn cờ.
6. Thời gian thực thi tổng thể (tính theo giây).

---

## 6. Phân công nhiệm vụ các thành viên

| STT | Thành viên        | MSSV | Module phụ trách chính                                                              | Công việc đi kèm (Báo cáo / Sản phẩm)                                                                            |
| :-: | :------------------ | :--: | :------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------- |
|  1  | **Trọng**    |      | **Game Engine & GUI** (`game/engine.py`, `gui/app.py`)                       | Quay & dựng Video Demo (5–10 phút); viết tài liệu `README.md`, `requirements.txt`                              |
|  2  | **Toàn**     |      | **CNF Encoder & Clue Extensions** (`logic/encoder.py`, `logic/evaluator.py`) | Xây dựng bộ dữ liệu câu đố mẫu ($3\times3, 4\times4, 5\times5$); viết phần dẫn xuất CNF trong báo cáo   |
|  3  | **Dũng**     |      | **DPLL SAT Solver** (`solver/dpll.py`)                                         | Cài đặt và tinh chỉnh thuật toán DPLL; viết phần mô tả thuật toán SAT trong báo cáo                       |
|  4  | **Đức**     |      | **Deductive Logic Agent** (`agent/deductive_agent.py`)                         | Xây dựng Deduction Trace, Uniqueness Check, Hint; viết phần Problem Formulation & Agent                              |
|  5  | **Đắc Anh** |      | **Benchmark & Experiment Pipeline** (`experiments/benchmark.py`)               | **Report Lead**: Tổng hợp và định dạng `Report.pdf`, vẽ biểu đồ thực nghiệm, phụ lục Generative AI |

### Chi tiết phân công công việc:

- **Trọng:** Thiết kế cấu trúc `GameEngine` bảo đảm tách biệt dữ liệu ẩn; xây dựng giao diện hiển thị lưới, ô chọn, highlight manh mối, các nút chức năng (Load, Restart, Hint, Auto Solve); thực hiện video demo thuyết minh và kiểm tra quyền truy cập link Google Drive.
- **Toàn:** Xây dựng bộ ánh xạ biến và bộ chuyển đổi CNF cho 6 mẫu gợi ý cơ bản cùng ít nhất 2 gợi ý mở rộng; cài đặt bộ đánh giá ngữ nghĩa trực tiếp (`SemanticEvaluator`) để kiểm tra chéo; chuẩn bị bộ câu đố kiểm thử đa dạng trường hợp.
- **Dũng:** Hiện thực thuật toán DPLL độc lập (Unit Propagation, Conflict Detection, Backtracking); đo đạc và ghi nhận các thông số decisions, propagations, backtracks, runtime; xây dựng các test case kiểm chứng tính đúng đắn cho bộ giải.
- **Đức:** Xây dựng tác tử suy luận không đoán mò dựa trên truy vấn SAT; xử lý chu trình suy diễn từng bước và xuất vết suy luận (`Deduction Trace`); hiện thực chức năng gợi ý bước đi (`Hint`) và kiểm tra tính duy nhất của nghiệm ván cờ (`Uniqueness Check`).
- **Đắc Anh:** Xây dựng kịch bản chạy thực nghiệm tự động ghi nhận 6 nhóm chỉ số trên các tập test; phân tích các trường hợp giới hạn hoặc quá thời gian; tổng hợp nội dung báo cáo thành file PDF hoàn chỉnh và tổng hợp tài liệu phụ lục sử dụng công cụ hỗ trợ.
