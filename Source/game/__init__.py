"""
Module quản lý trạng thái trò chơi (Game Engine) cho Griductive Solver.
Nắm giữ bảng chơi hoàn chỉnh, đáp án ẩn và các manh mối chưa lật theo kiến trúc 2 lớp.
"""

from .board import (
    Board,
    CRIMINAL,
    Cell,
    INCONSISTENT,
    INNOCENT,
    UNKNOWN,
    VALID_STATUSES,
    coord_to_row_col,
    coord_to_var,
    format_clue_text,
    iter_coords_row_major,
    normalize_coord,
    resolve_clue_cells,
    resolve_region,
    row_col_to_coord,
    var_to_coord,
)
from .engine import (
    CODE_ACCEPTED,
    CODE_ALREADY_REVEALED,
    CODE_CONTRADICTED,
    CODE_INCONSISTENT,
    CODE_INVALID,
    CODE_NOT_PROVABLE,
    GameEngine,
)
from .fallback_agent import FallbackLogicAdapter

__all__ = [
    "Board",
    "Cell",
    "GameEngine",
    "FallbackLogicAdapter",
    "CRIMINAL",
    "INNOCENT",
    "UNKNOWN",
    "INCONSISTENT",
    "VALID_STATUSES",
    "CODE_ACCEPTED",
    "CODE_ALREADY_REVEALED",
    "CODE_CONTRADICTED",
    "CODE_INCONSISTENT",
    "CODE_INVALID",
    "CODE_NOT_PROVABLE",
    "coord_to_row_col",
    "row_col_to_coord",
    "coord_to_var",
    "var_to_coord",
    "normalize_coord",
    "iter_coords_row_major",
    "resolve_region",
    "resolve_clue_cells",
    "format_clue_text",
]
