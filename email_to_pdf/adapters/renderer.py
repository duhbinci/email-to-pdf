from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from email_to_pdf.domain.errors import BrowserCrashError, RenderTimeoutError
from email_to_pdf.infra.config import BrowserPoolSettings, RenderSettings
from email_to_pdf.infra.logging import get_logger

logger = get_logger(__name__)

_HARDENED_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-sync",
    "--no-first-run",
]


class BrowserPool:
    def __init__(self, settings: BrowserPoolSettings | None = None) -> None:
        self._settings = settings or BrowserPoolSettings()
        self._semaphore: asyncio.Semaphore | None = None
        self._playwright = None
        self._playwright_ctx = None
        self._browser = None

    async def start(self) -> None:
        from playwright.async_api import async_playwright

        self._semaphore = asyncio.Semaphore(self._settings.max_browsers)
        self._playwright_ctx = async_playwright()
        self._playwright = await self._playwright_ctx.__aenter__()

        launch_args = list(_HARDENED_ARGS) + list(self._settings.launch_args)
        self._browser = await self._playwright.chromium.launch(args=launch_args)
        logger.info("browser_pool_started", max_browsers=self._settings.max_browsers)

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright_ctx:
            await self._playwright_ctx.__aexit__(None, None, None)
        logger.info("browser_pool_stopped")

    async def __aenter__(self) -> "BrowserPool":
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.stop()

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[object, None]:
        if self._semaphore is None or self._browser is None:
            raise BrowserCrashError("Browser pool has not been started")

        async with self._semaphore:
            context = await self._browser.new_context(
                java_script_enabled=False, offline=True
            )
            try:
                yield context
            finally:
                await context.close()


class PlaywrightRendererAdapter:
    def __init__(self, pool: BrowserPool) -> None:
        self._pool = pool

    @retry(
        retry=retry_if_exception_type(BrowserCrashError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def render(self, html: str, settings: RenderSettings) -> bytes:
        try:
            async with self._pool.acquire() as context:
                return await self._do_render(context, html, settings)
        except RenderTimeoutError, BrowserCrashError:
            raise
        except Exception as exc:
            raise BrowserCrashError(f"Render failed: {exc}", cause=exc) from exc

    async def _do_render(
        self, context: object, html: str, settings: RenderSettings
    ) -> bytes:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import TimeoutError as PlaywrightTimeout

        page = await context.new_page()  # type: ignore[attr-defined]

        async def block_requests(route: object) -> None:
            url = route.request.url  # type: ignore[attr-defined]
            if (
                url.startswith("data:")
                or url.startswith("file:")
                or url.startswith("about:")
            ):
                await route.continue_()  # type: ignore[attr-defined]
            else:
                await route.abort()  # type: ignore[attr-defined]

        await page.route("**/*", block_requests)

        if not settings.allow_scripts:
            await page.add_init_script(
                "Object.defineProperty(document, 'scripts', {get: function() { return []; }});"
            )

        try:
            await page.set_content(html, wait_until="domcontentloaded")

            try:
                await page.wait_for_load_state(
                    "networkidle", timeout=settings.timeout_ms
                )
            except PlaywrightTimeout:
                pass

            await page.emulate_media(media="print")

            pdf_bytes = await page.pdf(
                format=settings.paper_format,
                print_background=settings.print_background,
                margin={
                    "top": f"{settings.margin_top_mm}mm",
                    "bottom": f"{settings.margin_bottom_mm}mm",
                    "left": f"{settings.margin_left_mm}mm",
                    "right": f"{settings.margin_right_mm}mm",
                },
                scale=settings.scale,
            )
            return pdf_bytes

        except PlaywrightTimeout as exc:
            raise RenderTimeoutError(
                f"Render timed out after {settings.timeout_ms}ms", cause=exc
            ) from exc
        except PlaywrightError as exc:
            if "timeout" in str(exc).lower():
                raise RenderTimeoutError(str(exc), cause=exc) from exc
            raise BrowserCrashError(str(exc), cause=exc) from exc
        finally:
            await page.close()
