from dataclasses import asdict, dataclass
from time import monotonic

from app.config import settings
from app.investigations.errors import ExecutionLimitError


@dataclass
class ExecutionUsage:
    plan_steps: int = 0
    model_calls: int = 0
    retrieval_calls: int = 0
    elapsed_seconds: float = 0


class ExecutionBudget:
    def __init__(self) -> None:
        self.started = monotonic()
        self.usage = ExecutionUsage()

    def _check_time(self) -> None:
        self.usage.elapsed_seconds = round(monotonic() - self.started, 3)
        if self.usage.elapsed_seconds > settings.investigation_max_runtime_seconds:
            raise ExecutionLimitError("Investigation runtime limit exceeded")

    def consume_step(self) -> None:
        self._check_time()
        self.usage.plan_steps += 1
        if self.usage.plan_steps > settings.investigation_max_steps:
            raise ExecutionLimitError("Investigation step limit exceeded")

    def consume_model(self) -> None:
        self._check_time()
        self.usage.model_calls += 1
        if self.usage.model_calls > settings.investigation_max_model_calls:
            raise ExecutionLimitError("Investigation model-call limit exceeded")

    def consume_retrieval(self) -> None:
        self._check_time()
        self.usage.retrieval_calls += 1
        if self.usage.retrieval_calls > settings.investigation_max_retrieval_calls:
            raise ExecutionLimitError("Investigation retrieval-call limit exceeded")

    def snapshot(self) -> dict:
        self._check_time()
        return asdict(self.usage)
