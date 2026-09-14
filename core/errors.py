"""Framework-neutral errors raised by storage backends.

main.py registers an exception handler that renders these exactly like
FastAPI's HTTPException responses ({"detail": ...} with the same status
code), so callers need no per-site wrapping while core/ stays framework-free.
"""


class StorageError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)
