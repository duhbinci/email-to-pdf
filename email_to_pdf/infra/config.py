from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class RenderSettings(BaseModel):
    paper_format: Literal["A4", "Letter", "Legal", "A3"] = "A4"
    scale: float = Field(1.0, ge=0.1, le=2.0)
    timeout_ms: int = 30_000
    print_background: bool = True
    allow_scripts: bool = False
    margin_top_mm: int = 10
    margin_bottom_mm: int = 10
    margin_left_mm: int = 10
    margin_right_mm: int = 10


class BrowserPoolSettings(BaseModel):
    max_browsers: int = Field(default_factory=lambda: os.cpu_count() or 4)
    launch_args: list[str] = []


class AttachmentSettings(BaseModel):
    extract: bool = False
    extract_directory: Path | None = None
    max_embed_size_bytes: int = 10 * 1024 * 1024
    max_count: int = 100
    append_manifest: bool = True


class StorageSettings(BaseModel):
    backend: Literal["local", "s3"] = "local"
    s3_bucket: str | None = None
    s3_prefix: str = ""


class ObservabilitySettings(BaseModel):
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    metrics_backend: Literal["noop", "prometheus", "otlp"] = "noop"
    otlp_endpoint: str | None = None
    sentry_dsn: str | None = None


class Settings(BaseModel):
    render: RenderSettings = Field(default_factory=RenderSettings)
    browser_pool: BrowserPoolSettings = Field(default_factory=BrowserPoolSettings)
    attachments: AttachmentSettings = Field(default_factory=AttachmentSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    max_html_size_bytes: int = 50 * 1024 * 1024
    max_body_size_bytes: int = 20 * 1024 * 1024
    max_attachment_size_bytes: int = 50 * 1024 * 1024
