from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from automation_server_client import AutomationServer, Credential
from dotenv import load_dotenv
from playwright.async_api import Download, Page

import q_webgis.functionality.rapport as rapport_modul
from q_haderslev_vbo.playwright.browser_session import BrowserSession
from q_webgis.configuration import (
    WEBGIS_CREDENTIAL_NAME,
    WEBGIS_RAPPORT_TIMEOUT_MS,
    WEBGIS_URL,
)
from q_webgis.functionality.rapport import opret_webgis_rapport
from q_webgis.selectors import RAPPORT_KNAP, VIS_RAPPORT_KNAP

logger = logging.getLogger(__name__)

HEADLESS = True
DEBUG = True
TEST_TEMA = "byggesag"
TEST_RAPPORT_MAPPE = Path("tests_local_output")
TEST_RAPPORT_FILNAVN = "webgis_headless_download_test.pdf"

WKT = (
    "POLYGON ((524591.45 6113854.699, "
    "524588.22 6113838.982, "
    "524558.971 6113844.437, "
    "524558.544 6113836.443, "
    "524557.653 6113819.77, "
    "524556.57 6113816.689, "
    "524560.29 6113815.464, "
    "524575.06 6113810.597, "
    "524585.919 6113804.171, "
    "524659.366 6113785.442, "
    "524664.069 6113783.751, "
    "524647.589 6113869.29, "
    "524643.366 6113868.592, "
    "524629.546 6113865.559, "
    "524619.458 6113863.345, "
    "524615.062 6113862.379, "
    "524612.841 6113862.269, "
    "524608.514 6113861.773, "
    "524592.124 6113857.977, "
    "524591.45 6113854.699))"
)

_DOWNLOADS_BY_PAGE: dict[int, Download] = {}


async def _aabn_rapport_med_download(
    page: Page,
    *,
    timeout_ms: int = WEBGIS_RAPPORT_TIMEOUT_MS,
) -> Page:
    """Klikker Vis rapport og fanger den faktiske Playwright-download."""
    rapport_knap = page.locator(RAPPORT_KNAP).filter(
        has_text=re.compile(r"^\s*Rapport\s*$", re.IGNORECASE)
    ).first
    await rapport_knap.wait_for(state="visible", timeout=timeout_ms)
    await rapport_knap.click()
    await page.wait_for_timeout(1_000)

    vis_rapport_knap = page.locator(VIS_RAPPORT_KNAP).filter(
        has_text=re.compile(r"^\s*Vis rapport\s*$", re.IGNORECASE)
    ).first
    await vis_rapport_knap.wait_for(state="visible", timeout=timeout_ms)

    loop = asyncio.get_running_loop()
    download_future: asyncio.Future[Download] = loop.create_future()

    def ved_download(download: Download) -> None:
        if not download_future.done():
            download_future.set_result(download)

    def ved_ny_side(ny_side: Page) -> None:
        ny_side.on("download", ved_download)

    page.on("download", ved_download)
    page.context.on("page", ved_ny_side)

    logger.info("Bestiller rapporten og venter på download-event.")

    try:
        async with page.context.expect_page(timeout=timeout_ms) as popup_info:
            await vis_rapport_knap.click()

        rapport_side = await popup_info.value
        rapport_side.on("download", ved_download)

        download = await asyncio.wait_for(
            asyncio.shield(download_future),
            timeout=timeout_ms / 1_000,
        )

        fejl = await download.failure()
        if fejl:
            raise RuntimeError(f"WebGIS-download fejlede: {fejl}")

        _DOWNLOADS_BY_PAGE[id(rapport_side)] = download

        logger.info(
            "Download-event modtaget. Foreslået filnavn: %s",
            download.suggested_filename,
        )
        return rapport_side
    finally:
        page.remove_listener("download", ved_download)
        page.context.remove_listener("page", ved_ny_side)


async def _gem_downloadet_rapport(
    webgis_side: Page,
    rapport_side: Page,
    destination: str | Path,
    *,
    timeout_ms: int = WEBGIS_RAPPORT_TIMEOUT_MS,
) -> Path:
    """Gemmer den allerede modtagne download uden et nyt HTTP-kald."""
    del webgis_side, timeout_ms

    download = _DOWNLOADS_BY_PAGE.pop(id(rapport_side), None)
    if download is None:
        raise RuntimeError("Der blev ikke registreret en rapport-download.")

    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.unlink(missing_ok=True)

    await download.save_as(str(destination_path))

    if not destination_path.is_file():
        raise RuntimeError("Den downloadede PDF blev ikke gemt.")
    if destination_path.stat().st_size == 0:
        raise RuntimeError("Den downloadede PDF er tom.")
    if not destination_path.read_bytes().startswith(b"%PDF-"):
        raise RuntimeError("Den downloadede fil er ikke en gyldig PDF.")

    logger.info(
        "PDF gemt direkte fra download-event: %s bytes.",
        destination_path.stat().st_size,
    )
    return destination_path


def _hent_credentials() -> dict[str, str]:
    AutomationServer.from_environment()
    credential = Credential.get_credential(WEBGIS_CREDENTIAL_NAME)
    username = str(credential.username or "").strip()
    password = str(credential.password or "")

    if not username or not password:
        raise RuntimeError(
            f"Credentialen {WEBGIS_CREDENTIAL_NAME!r} er ufuldstændig."
        )

    return {"username": username, "password": password}


async def main() -> None:
    load_dotenv()

    original_aabn_rapport = rapport_modul.aabn_rapport
    original_gem_rapport_pdf = rapport_modul.gem_rapport_pdf
    rapport_modul.aabn_rapport = _aabn_rapport_med_download
    rapport_modul.gem_rapport_pdf = _gem_downloadet_rapport

    output_path = TEST_RAPPORT_MAPPE / TEST_RAPPORT_FILNAVN
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)

    session = BrowserSession(
        headless=HEADLESS,
        debug=DEBUG,
        http_credentials=_hent_credentials(),
    )
    page: Page | None = None

    try:
        await session.start()
        page = await session.new_page()

        logger.info("Åbner WebGIS headless=%s.", HEADLESS)
        response = await page.goto(
            WEBGIS_URL,
            wait_until="domcontentloaded",
            timeout=60_000,
        )

        if response is None or not response.ok:
            status = response.status if response is not None else "intet svar"
            raise RuntimeError(
                f"WebGIS kunne ikke åbnes. HTTP-status: {status}."
            )

        gemt_sti = await opret_webgis_rapport(
            page=page,
            session=session,
            wkt=WKT,
            tema=TEST_TEMA,
            rapportmappe=TEST_RAPPORT_MAPPE,
            filnavn=TEST_RAPPORT_FILNAVN,
            vaelg_jordstykker_byggesag=True,
            timeout_ms=60_000,
            rapport_timeout_ms=WEBGIS_RAPPORT_TIMEOUT_MS,
        )

        gemt_sti = Path(gemt_sti)
        if not gemt_sti.is_file():
            raise AssertionError(f"PDF mangler: {gemt_sti.resolve()}")
        if not gemt_sti.read_bytes().startswith(b"%PDF-"):
            raise AssertionError("Den gemte fil er ikke en PDF.")

        logger.info("TEST BESTÅET.")
        logger.info("Rapport: %s", gemt_sti.resolve())
    except Exception:
        logger.exception("TEST FEJLEDE.")
        if page is not None and not page.is_closed():
            try:
                await session.screenshot(
                    page,
                    "FEJL_webgis_headless_download",
                    always=True,
                )
            except Exception:
                logger.exception("Fejlscreenshot kunne ikke gemmes.")
        raise
    finally:
        rapport_modul.aabn_rapport = original_aabn_rapport
        rapport_modul.gem_rapport_pdf = original_gem_rapport_pdf
        _DOWNLOADS_BY_PAGE.clear()

        if page is not None and not page.is_closed():
            try:
                await session.close_page(page)
            except Exception:
                logger.exception("WebGIS-siden kunne ikke lukkes.")
        await session.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("automation_server_client").setLevel(logging.WARNING)
    asyncio.run(main())
