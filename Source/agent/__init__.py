"""Module tác tử suy luận tự động (Deductive Logic Agent)."""

from agent.deductive_agent import (
    VERDICT_CRIMINAL,
    VERDICT_INCONSISTENT,
    VERDICT_INNOCENT,
    VERDICT_UNKNOWN,
    DeductiveAgent,
    SolverProtocol,
    check_entailment,
    coord_to_var,
    is_kb_consistent,
    var_to_coord,
)

__all__ = [
    "VERDICT_CRIMINAL",
    "VERDICT_INNOCENT",
    "VERDICT_UNKNOWN",
    "VERDICT_INCONSISTENT",
    "SolverProtocol",
    "DeductiveAgent",
    "check_entailment",
    "is_kb_consistent",
    "coord_to_var",
    "var_to_coord",
]
