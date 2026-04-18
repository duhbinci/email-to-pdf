from __future__ import annotations

import asyncio
from pathlib import Path
from typing import BinaryIO

from email_to_pdf.adapters.parsers.eml import EmlParserAdapter
from email_to_pdf.adapters.parsers.msg import MsgParserAdapter
from email_to_pdf.adapters.renderer import BrowserPool, PlaywrightRendererAdapter
from email_to_pdf.adapters.sanitiser import Nh3SanitizerAdapter
from email_to_pdf.adapters.storage import LocalFsStorageAdapter
from email_to_pdf.domain.errors import InputReadError
from email_to_pdf.domain.models import ConversionResult
from email_to_pdf.domain.services.conversion_service import ConversionService
from email_to_pdf.infra.config import Settings
from email_to_pdf.infra.logging import setup_logging


class ConversionContext:
    """Long-lived conversion context: owns a started BrowserPool and a shared
    ConversionService. Start once at application boot, reuse across requests."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._pool: BrowserPool | None = None
        self._service: ConversionService | None = None

    async def start(self) -> None:
        if self._pool is not None:
            return
        setup_logging(self._settings.observability.log_level)
        self._pool = BrowserPool(self._settings.browser_pool)
        await self._pool.start()
        self._service = ConversionService(
            parsers=[EmlParserAdapter(), MsgParserAdapter()],
            renderer=PlaywrightRendererAdapter(self._pool),
            sanitizer=Nh3SanitizerAdapter(),
            storage=None,
            settings=self._settings,
        )

    async def stop(self) -> None:
        if self._pool is not None:
            await self._pool.stop()
            self._pool = None
            self._service = None

    async def convert(
        self,
        input: str | bytes | BinaryIO,
        output_path: str | Path | None = None,
        job_id: str | None = None,
    ) -> ConversionResult:
        if self._service is None:
            raise RuntimeError("ConversionContext not started")

        data = await _read_input_async(input)

        if output_path is not None:
            output_path = Path(output_path)
            storage = LocalFsStorageAdapter(output_path.parent)
            output_key: str | None = output_path.name
            self._service._storage = storage  # type: ignore[attr-defined]
        else:
            output_key = None

        return await self._service.convert(data, job_id=job_id, output_key=output_key)


async def convert(
    input: str | bytes | BinaryIO,
    output_path: str | Path | None = None,
    settings: Settings | None = None,
    job_id: str | None = None,
) -> ConversionResult:
    """One-shot convenience: spins up and tears down a BrowserPool per call.
    Prefer ConversionContext for long-running services."""
    ctx = ConversionContext(settings)
    await ctx.start()
    try:
        return await ctx.convert(input, output_path=output_path, job_id=job_id)
    finally:
        await ctx.stop()


async def _read_input_async(input: str | bytes | BinaryIO) -> bytes:
    if isinstance(input, bytes):
        return input
    if isinstance(input, str):
        try:
            return await asyncio.to_thread(Path(input).read_bytes)
        except OSError as exc:
            raise InputReadError(f"Cannot read file {input!r}: {exc}", cause=exc) from exc
    try:
        data = await asyncio.to_thread(input.read)
        if isinstance(data, str):
            return data.encode("utf-8")
        return data
    except OSError as exc:
        raise InputReadError(f"Cannot read from stream: {exc}", cause=exc) from exc
