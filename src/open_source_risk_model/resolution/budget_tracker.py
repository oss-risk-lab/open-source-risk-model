import time
from dataclasses import dataclass, field


@dataclass
class BudgetConfig:
    global_budget: int = 200
    per_ecosystem: dict[str, int] = field(default_factory=dict)
    min_delay_ms: int = 100


class BudgetTracker:
    def __init__(self, config: BudgetConfig):
        self.config = config
        self._global_used: int = 0
        self._per_ecosystem_used: dict[str, int] = {}
        self._last_call_time: dict[str, float] = {}

    def can_make_call(self, ecosystem: str) -> bool:
        if ecosystem in self.config.per_ecosystem:
            eco_used = self._per_ecosystem_used.get(ecosystem, 0)
            if eco_used >= self.config.per_ecosystem[ecosystem]:
                return False
        else:
            if self._global_used >= self.config.global_budget:
                return False
        return True

    def record_call(self, ecosystem: str) -> None:
        self._global_used += 1
        self._per_ecosystem_used[ecosystem] = (
            self._per_ecosystem_used.get(ecosystem, 0) + 1
        )

    def wait_if_needed(self, ecosystem: str) -> None:
        last = self._last_call_time.get(ecosystem, 0)
        elapsed_ms = (time.monotonic() - last) * 1000
        if elapsed_ms < self.config.min_delay_ms:
            time.sleep((self.config.min_delay_ms - elapsed_ms) / 1000)
        self._last_call_time[ecosystem] = time.monotonic()

    @property
    def api_calls_made(self) -> int:
        return self._global_used
