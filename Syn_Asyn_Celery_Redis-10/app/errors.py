class AgentServiceError(Exception):
    pass


class InvalidRequest(AgentServiceError):
    pass


class IdempotencyConflict(AgentServiceError):
    pass


class JobNotFound(AgentServiceError):
    pass


class InvalidTransition(AgentServiceError):
    pass


class TransientFailure(AgentServiceError):
    pass


class PermanentFailure(AgentServiceError):
    pass


class PolicyFailure(PermanentFailure):
    pass


class WorkerLost(AgentServiceError):
    pass


class MemoryRejected(AgentServiceError):
    pass
