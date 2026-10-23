class InvestigationError(RuntimeError):
    code = "investigation_failed"
    retryable = False


class PlanValidationError(InvestigationError):
    code = "invalid_plan"


class UnsupportedMetricError(InvestigationError):
    code = "unsupported_metric"


class RequiredDataError(InvestigationError):
    code = "missing_required_data"


class ExecutionLimitError(InvestigationError):
    code = "execution_limit_exceeded"


class ToolExecutionError(InvestigationError):
    code = "tool_execution_failed"


class TransientInvestigationError(InvestigationError):
    code = "transient_failure"
    retryable = True
