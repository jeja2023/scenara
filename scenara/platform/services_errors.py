"""Exceptions shared by run service API and execution internals."""

from scenara.platform.pipeline import ExecutionInterrupted


class ResourceNotFound(RuntimeError):
    pass


class InvalidTransition(RuntimeError):
    pass


class ExecutionStopped(ExecutionInterrupted):
    pass


__all__ = ["ExecutionStopped", "InvalidTransition", "ResourceNotFound"]
