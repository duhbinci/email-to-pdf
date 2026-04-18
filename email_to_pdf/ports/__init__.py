from __future__ import annotations

from typing import Protocol, runtime_checkable

from email_to_pdf.domain.models import ParsedEmail
from email_to_pdf.infra.config import RenderSettings


@runtime_checkable
class EmailParserPort(Protocol):
    def can_parse(self, data: bytes) -> bool: ...
    def parse(self, data: bytes) -> ParsedEmail: ...


@runtime_checkable
class HtmlRendererPort(Protocol):
    async def render(self, html: str, settings: RenderSettings) -> bytes: ...


@runtime_checkable
class StoragePort(Protocol):
    async def write(self, key: str, data: bytes) -> str: ...
    async def read(self, key: str) -> bytes: ...


@runtime_checkable
class SanitizerPort(Protocol):
    def sanitise(self, html: str) -> str: ...
