import json
import math
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class Rules:
    min_price: float = 5
    min_avg_volume: int = 500_000
    min_avg_dollar_volume: int = 10_000_000
    breakout_days: int = 55
    min_volume_ratio: float = 1.5
    max_pivot_extension: float = .05
    max_sma50_extension: float = .15
    rs_days: int = 63
    min_history: int = 220
    history_sessions: int = 260
    near_pivot_distance: float = .03
    liquidity_days: int = 50
    settlement_minutes: int = 30
    max_data_error_fraction: float = .10
    research_limit: int = 5

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid rule: {field.name}")
            if field.type is int and not isinstance(value, int):
                raise ValueError(f"Rule must be an integer: {field.name}")
        for name in ("breakout_days", "rs_days", "liquidity_days", "min_history", "history_sessions"):
            if getattr(self, name) < 1:
                raise ValueError(f"Rule must be positive: {name}")
        required = max(200, self.breakout_days + 1, self.rs_days + 1, self.liquidity_days + 1)
        if self.min_history < required or self.history_sessions < self.min_history:
            raise ValueError("History must support all configured windows and SMA200")
        if self.max_data_error_fraction > 1 or self.near_pivot_distance >= 1:
            raise ValueError("Invalid fraction")
        if self.research_limit > 20:
            raise ValueError("Research limit is capped at 20 to bound API requests")

    @classmethod
    def load(cls, path=None):
        path = Path(path) if path else Path(__file__).resolve().parents[1] / "config.json"
        return cls(**json.loads(path.read_text()))
