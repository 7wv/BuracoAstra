"""Editable defaults. Each interface also offers these options before a hand."""

from dataclasses import dataclass

USE_JOKERS = False
REQUIRE_CLEAN_CANASTRA_TO_GO_OUT = True
VULNERABILITY_THRESHOLD = 1500
VULNERABILITY_MINIMUM_MELD = 75
ALLOW_A_TO_K_CLEAN_CANASTRA = False
ALLOW_A_TO_A_CLEAN_CANASTRA = False
NO_PROGRESS_TURN_LIMIT = 12


@dataclass(frozen=True)
class Rules:
    use_jokers: bool = USE_JOKERS
    require_clean_canastra_to_go_out: bool = REQUIRE_CLEAN_CANASTRA_TO_GO_OUT
    vulnerability_threshold: int = VULNERABILITY_THRESHOLD
    vulnerability_minimum_meld: int = VULNERABILITY_MINIMUM_MELD
    allow_a_to_k_clean_canastra: bool = ALLOW_A_TO_K_CLEAN_CANASTRA
    allow_a_to_a_clean_canastra: bool = ALLOW_A_TO_A_CLEAN_CANASTRA
    no_progress_turn_limit: int = NO_PROGRESS_TURN_LIMIT

    def __post_init__(self):
        for name in ("use_jokers", "require_clean_canastra_to_go_out",
                     "allow_a_to_k_clean_canastra", "allow_a_to_a_clean_canastra"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be yes or no.")
        for name in ("vulnerability_threshold", "vulnerability_minimum_meld",
                     "no_progress_turn_limit"):
            value = getattr(self, name)
            if type(value) is not int or value < (1 if name == "no_progress_turn_limit" else 0):
                raise ValueError(f"{name} must be a {'positive' if name == 'no_progress_turn_limit' else 'nonnegative'} integer.")
