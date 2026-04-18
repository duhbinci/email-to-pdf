import asyncio
import os
import tempfile
import uuid
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from email_to_pdf.api import ConversionContext
from email_to_pdf.infra.config import Settings
from email_to_pdf.infra.logging import get_logger, set_request_id

_PDF_CACHE: dict[str, tuple[str, str]] = {}
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ctx = ConversionContext(Settings())
    await ctx.start()
    app.state.ctx = ctx
    try:
        yield
    finally:
        await ctx.stop()


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    set_request_id(uuid.uuid4().hex)
    return await call_next(request)


@app.get("/", response_class=HTMLResponse)
async def index():
    return _HTML


@app.post("/convert")
async def convert_email(file: UploadFile = File(...)):
    data = await file.read()
    logger.info("convert_received", bytes=len(data), filename=file.filename)
    if not data:
        raise HTTPException(400, "Empty file")

    ctx: ConversionContext = app.state.ctx
    try:
        result = await ctx.convert(data)
    except Exception as exc:
        logger.error("convert_failed", exc_type=type(exc).__name__, error=str(exc))
        raise HTTPException(422, f"{type(exc).__name__}: {exc}")

    pdf_size = len(result.pdf_bytes)
    logger.info(
        "convert_complete",
        pdf_size=pdf_size,
        job_id=result.job_id,
        warnings=len(result.warnings),
        stages=result.stage_durations_ms,
    )
    if pdf_size == 0:
        raise HTTPException(500, "Conversion produced empty PDF (renderer failure)")

    stem = file.filename.rsplit(".", 1)[0] if file.filename else "email"
    tmp_path = await asyncio.to_thread(_write_tmp_pdf, result.pdf_bytes)
    on_disk = await asyncio.to_thread(os.path.getsize, tmp_path)
    logger.info("convert_written", bytes=on_disk, path=tmp_path)

    token = uuid.uuid4().hex
    _PDF_CACHE[token] = (tmp_path, f"{stem}.pdf")
    return JSONResponse({"token": token, "filename": f"{stem}.pdf", "size": pdf_size})


@app.get("/download/{token}")
async def download_pdf(token: str, background: BackgroundTasks):
    entry = _PDF_CACHE.pop(token, None)
    if entry is None:
        raise HTTPException(404, "Not found")
    path, filename = entry
    size = await asyncio.to_thread(os.path.getsize, path)
    logger.info("download_served", path=path, bytes=size, filename=filename)
    background.add_task(_safe_unlink, path)
    return FileResponse(path, media_type="application/pdf", filename=filename)


def _write_tmp_pdf(data: bytes) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        tmp.write(data)
    finally:
        tmp.close()
    return tmp.name


def _safe_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Email to PDF</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="min-h-screen bg-gray-50 flex items-center justify-center p-6">
  <div class="bg-white rounded-2xl shadow-md w-full max-w-md p-8">
    <h1 class="text-2xl font-semibold text-gray-800 mb-1">Email to PDF</h1>
    <p class="text-sm text-gray-500 mb-6">Upload an <code class="bg-gray-100 px-1 rounded">.eml</code> or <code class="bg-gray-100 px-1 rounded">.msg</code> file to convert it. Unsupported formats will be rejected.</p>

    <label
      id="drop-zone"
      class="flex flex-col items-center justify-center border-2 border-dashed border-gray-300 rounded-xl p-8 cursor-pointer hover:border-blue-400 hover:bg-blue-50 transition-colors"
    >
      <svg class="w-10 h-10 text-gray-400 mb-3" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"/>
      </svg>
      <span id="drop-label" class="text-sm text-gray-500">Drop file here or <span class="text-blue-500 font-medium">browse</span></span>
      <input id="file-input" type="file" class="hidden">
    </label>

    <div id="error-box" class="hidden mt-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3"></div>

    <button
      id="convert-btn"
      disabled
      class="mt-5 w-full py-2.5 rounded-xl text-sm font-medium transition-colors
             bg-blue-500 text-white hover:bg-blue-600
             disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed"
    >
      Convert to PDF
    </button>

    <div id="progress" class="hidden mt-4 flex items-center gap-2 text-sm text-gray-500">
      <svg class="animate-spin w-4 h-4 text-blue-500" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
      </svg>
      Converting…
    </div>
  </div>

  <script>
    const input = document.getElementById('file-input');
    const zone  = document.getElementById('drop-zone');
    const label = document.getElementById('drop-label');
    const btn   = document.getElementById('convert-btn');
    const prog  = document.getElementById('progress');
    const errBox = document.getElementById('error-box');

    let selectedFile = null;

    function setFile(file) {
      if (!file) return;
      selectedFile = file;
      label.textContent = file.name;
      btn.disabled = false;
      errBox.classList.add('hidden');
    }

    input.addEventListener('change', () => setFile(input.files[0]));

    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('border-blue-400','bg-blue-50'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('border-blue-400','bg-blue-50'));
    zone.addEventListener('drop', e => {
      e.preventDefault();
      zone.classList.remove('border-blue-400','bg-blue-50');
      setFile(e.dataTransfer.files[0]);
    });

    btn.addEventListener('click', async () => {
      if (!selectedFile) return;
      btn.disabled = true;
      prog.classList.remove('hidden');
      errBox.classList.add('hidden');

      try {
        const fd = new FormData();
        fd.append('file', selectedFile);

        const res = await fetch('/convert', { method: 'POST', body: fd });

        if (!res.ok) {
          const detail = await res.json().catch(() => ({ detail: res.statusText }));
          throw new Error(detail.detail || res.statusText);
        }

        const { token } = await res.json();
        window.location.assign('/download/' + token);
      } catch (err) {
        errBox.textContent = err.message;
        errBox.classList.remove('hidden');
      } finally {
        btn.disabled = false;
        prog.classList.add('hidden');
      }
    });
  </script>
</body>
</html>"""
