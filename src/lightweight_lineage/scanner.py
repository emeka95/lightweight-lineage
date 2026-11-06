"""Deterministic discovery of SQL files in a repository."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 300


class ScanTimeoutError(TimeoutError):
    """Raised when repository discovery exceeds its whole-scan deadline."""


@dataclass(frozen=True, slots=True)
class ScanDeadline:
    expires_at: float
    timeout_seconds: int

    @classmethod
    def start(cls, timeout_seconds: int) -> ScanDeadline:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        return cls(time.monotonic() + timeout_seconds, timeout_seconds)

    def check(self) -> None:
        if time.monotonic() >= self.expires_at:
            raise ScanTimeoutError(
                f"The {self.timeout_seconds}-second scan deadline was exceeded."
            )


def _sort_key(value: str) -> tuple[str, str]:
    return value.casefold(), value


def scan_repository(
    root: str | Path,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    deadline: ScanDeadline | None = None,
) -> tuple[str, ...]:
    """Return repository-relative POSIX paths for discovered .sql files.

    Directory traversal and results are sorted to make discovery deterministic.
    A timeout aborts the scan rather than returning a partial file list.
    """
    run_deadline = deadline or ScanDeadline.start(timeout_seconds)

    root_path = Path(root).resolve(strict=True)
    run_deadline.check()
    if not root_path.is_dir():
        raise NotADirectoryError(f"Scan source is not a directory: {root_path}")

    def raise_walk_error(error: OSError) -> None:
        raise error

    discovered: list[str] = []
    for current, directories, filenames in os.walk(
        root_path,
        topdown=True,
        onerror=raise_walk_error,
    ):
        run_deadline.check()
        directories.sort(key=_sort_key)
        filenames.sort(key=_sort_key)
        current_path = Path(current)

        for filename in filenames:
            run_deadline.check()
            if Path(filename).suffix.casefold() == ".sql":
                relative_path = (current_path / filename).relative_to(root_path)
                discovered.append(relative_path.as_posix())

    run_deadline.check()
    return tuple(sorted(discovered, key=_sort_key))


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "ScanDeadline",
    "ScanTimeoutError",
    "scan_repository",
]
