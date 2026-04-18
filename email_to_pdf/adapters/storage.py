from __future__ import annotations

import asyncio
from pathlib import Path

from email_to_pdf.domain.errors import PathTraversalError, WritePermissionError
from email_to_pdf.infra.logging import get_logger

logger = get_logger(__name__)


class LocalFsStorageAdapter:
    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir).resolve()
        self._base.mkdir(parents=True, exist_ok=True)

    async def write(self, key: str, data: bytes) -> str:
        dest = self._resolve_safe(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            await asyncio.to_thread(dest.write_bytes, data)
        except PermissionError as exc:
            raise WritePermissionError(
                f"Cannot write to {dest}: {exc}", cause=exc
            ) from exc
        except OSError as exc:
            raise WritePermissionError(
                f"OS error writing {dest}: {exc}", cause=exc
            ) from exc
        logger.info("storage_write", path=str(dest), size=len(data))
        return str(dest)

    async def read(self, key: str) -> bytes:
        dest = self._resolve_safe(key)
        try:
            return await asyncio.to_thread(dest.read_bytes)
        except PermissionError as exc:
            raise WritePermissionError(
                f"Cannot read {dest}: {exc}", cause=exc
            ) from exc
        except FileNotFoundError as exc:
            raise WritePermissionError(
                f"File not found: {dest}", cause=exc
            ) from exc

    def _resolve_safe(self, key: str) -> Path:
        clean_key = key.lstrip("/").lstrip("\\")
        candidate = (self._base / clean_key).resolve()
        try:
            candidate.relative_to(self._base)
        except ValueError as exc:
            raise PathTraversalError(
                f"Path traversal detected: {key!r} resolves outside base directory",
                cause=exc,
            ) from exc
        return candidate
