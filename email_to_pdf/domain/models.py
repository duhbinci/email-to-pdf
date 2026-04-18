from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class Address:
    display_name: str
    addr_spec: str


@dataclass(frozen=True)
class Attachment:
    content_id: str | None
    filename: str
    content_type: str
    data: bytes
    size: int
    is_inline: bool


@dataclass(frozen=True)
class ParsedEmail:
    message_id: str | None
    subject: str
    from_: Address
    to: list[Address]
    cc: list[Address]
    bcc: list[Address]
    date: datetime | None
    html_body: str | None
    text_body: str | None
    attachments: list[Attachment]
    raw_headers: dict[str, list[str]]
    input_format: Literal["eml", "msg"]


@dataclass(frozen=True)
class ConversionResult:
    job_id: str
    input_hash: str
    pdf_bytes: bytes
    page_count: int
    output_size_bytes: int
    extracted_attachments: list[str]
    warnings: list[str]
    stage_durations_ms: dict[str, float]
