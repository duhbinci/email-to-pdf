from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from email_to_pdf.infra.config import AttachmentSettings, RenderSettings, Settings

app = typer.Typer(name="email-to-pdf", help="Convert EML/MSG email files to PDF.")


@app.command()
def convert(
    input_path: Annotated[Path, typer.Argument(help="Path to the input .eml or .msg file")],
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Output PDF path (default: <input>.pdf)"),
    ] = None,
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="Paper format: A4, Letter, Legal, A3"),
    ] = "A4",
    extract_attachments: Annotated[
        Optional[Path],
        typer.Option("--extract-attachments", help="Directory to extract attachments into"),
    ] = None,
) -> None:
    if not input_path.exists():
        typer.echo(f"Error: Input file does not exist: {input_path}", err=True)
        raise typer.Exit(1)

    if format not in ("A4", "Letter", "Legal", "A3"):
        typer.echo(f"Error: Invalid format {format!r}. Must be one of: A4, Letter, Legal, A3", err=True)
        raise typer.Exit(1)

    if output is None:
        output = input_path.with_suffix(".pdf")

    render_settings = RenderSettings(paper_format=format)  # type: ignore[arg-type]
    attachment_settings = AttachmentSettings()
    if extract_attachments:
        attachment_settings = AttachmentSettings(
            extract=True,
            extract_directory=extract_attachments,
        )

    settings = Settings(
        render=render_settings,
        attachments=attachment_settings,
    )

    async def _run() -> None:
        from email_to_pdf.api import convert as api_convert

        try:
            result = await api_convert(
                input=str(input_path),
                output_path=output,
                settings=settings,
            )
            typer.echo(f"Converted: {output}")
            typer.echo(f"  Job ID:     {result.job_id}")
            typer.echo(f"  Pages:      {result.page_count}")
            typer.echo(f"  Size:       {result.output_size_bytes:,} bytes")
            if result.warnings:
                typer.echo(f"  Warnings:   {len(result.warnings)}")
                for w in result.warnings:
                    typer.echo(f"    - {w}", err=True)
            if result.extracted_attachments:
                typer.echo(f"  Attachments extracted: {len(result.extracted_attachments)}")
                for path in result.extracted_attachments:
                    typer.echo(f"    {path}")
        except Exception as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1)

    asyncio.run(_run())


def main() -> None:
    app()


if __name__ == "__main__":
    main()
