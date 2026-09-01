from __future__ import annotations


class ScenaraError(RuntimeError):
    def __init__(
        self, status_code: int, code: str, message: str, request_id: str | None = None
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.request_id = request_id
        super().__init__(message)


__all__ = ["ScenaraError"]
