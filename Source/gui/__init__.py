"""
Module giao diện Web (HTML + HTTP Server chuẩn Python) cho Griductive Solver.
Hiển thị lưới ô cờ N x N, tô sáng vùng manh mối, cung cấp các nút Load, Restart, Hint,
Auto Solve / Stop và nhật ký Deduction Trace thông qua trình duyệt web.
"""

from .app import (
    GriductiveWebServer,
    GriductiveWebSession,
    create_app_server,
    launch_app,
)

__all__ = [
    "GriductiveWebSession",
    "GriductiveWebServer",
    "create_app_server",
    "launch_app",
]
