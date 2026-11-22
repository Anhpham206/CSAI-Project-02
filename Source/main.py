"""
Điểm khởi chạy chính của chương trình Griductive Solver.
Cho phép khởi động giao diện đồ họa (GUI) hoặc chạy các chế độ thử nghiệm qua dòng lệnh.
"""

import sys
import argparse


def parse_arguments():
    parser = argparse.ArgumentParser(description="Chương trình giải trò chơi Griductive - Đồ án 2 AI")
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Chạy ở chế độ dòng lệnh (CLI) thay vì mở giao diện đồ họa"
    )
    parser.add_argument(
        "--puzzle",
        type=str,
        default=None,
        help="Đường dẫn file câu đố muốn tải sẵn (vd: data/puzzles/sample_3x3.json)"
    )
    return parser.parse_args()


def main():
    args = parse_arguments()
    if args.cli:
        print("Đang khởi động chế độ dòng lệnh...")
        # Dự kiến kết nối với DeductiveLogicAgent và GameEngine ở đây
    else:
        print("Đang khởi động giao diện đồ họa (GUI)...")
        # Dự kiến gọi hàm khởi chạy giao diện từ module gui


if __name__ == "__main__":
    main()
