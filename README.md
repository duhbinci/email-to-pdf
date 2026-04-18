# email-to-pdf

Convert `.eml` and `.msg` email files to PDF — via CLI, HTTP API, or Python library.

## Features

- Supports `.eml` (RFC 822) and `.msg` (Outlook) formats
- HTML sanitization before rendering
- Attachment extraction
- Configurable paper format (A4, Letter, Legal, A3)
- Structured JSON logging

## Installation

```bash
pip install git+https://github.com/kshitizwagle/email-to-pdf.git
```

After installing, download the Chromium browser that Playwright uses for rendering:

```bash
playwright install chromium --with-deps
```

To also install the web server components:

```bash
pip install "git+https://github.com/kshitizwagle/email-to-pdf.git#egg=email-to-pdf[server]"
```

## Requirements

- Python 3.14+
- Chromium (installed via the `playwright install` step above)

## Usage

### CLI

```bash
# Basic conversion
email-to-pdf email.eml

# Custom output path and paper format
email-to-pdf email.eml -o output.pdf --format Letter

# Extract attachments
email-to-pdf email.msg --extract-attachments ./attachments/
```

### Python library

```python
import asyncio
from email_to_pdf import convert

result = asyncio.run(convert("email.eml", output_path="output.pdf"))
print(f"Pages: {result.page_count}, Size: {result.output_size_bytes} bytes")
```

For high-throughput use, reuse a `ConversionContext` to share a browser pool across calls:

```python
from email_to_pdf import ConversionContext

ctx = ConversionContext()
await ctx.start()

result = await ctx.convert("email.eml", output_path="output.pdf")

await ctx.stop()
```

You can configure rendering, attachments, and more via `Settings`:

```python
from email_to_pdf import ConversionContext, Settings
from email_to_pdf.infra.config import RenderSettings

settings = Settings(render=RenderSettings(paper_format="Letter", scale=0.9))
ctx = ConversionContext(settings)
```

### Web UI / HTTP API

Requires the `server` extra (see installation above).

```bash
uvicorn main:app --reload
```

Open `http://localhost:8000` for the drag-and-drop web interface, or use the API:

```bash
# Upload and convert
curl -F file=@email.eml http://localhost:8000/convert
# {"token": "...", "filename": "email.pdf", "size": 12345}

# Download the PDF
curl -o output.pdf http://localhost:8000/download/<token>
```

### Docker

```bash
docker compose up
```

The service is available at `http://localhost:8000`.

## Development

```bash
git clone https://github.com/kshitizwagle/email-to-pdf.git
cd email-to-pdf
uv sync --dev
uv run playwright install chromium --with-deps
uv run pytest
```
