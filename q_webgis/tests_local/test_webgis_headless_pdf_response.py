from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

from automation_server_client import AutomationServer, Credential
from dotenv import load_dotenv
from playwright.async_api import Page, Response

import q_webgis.functionality.rapport as rapport_modul
from q_haderslev_vbo.playwright.browser_session import BrowserSession
from q_webgis.configuration import (
    WEBGIS_CREDENTIAL_NAME,
    WEBGIS_RAPPORT_TIMEOUT_MS,
    WEBGIS_URL,
)
from q_webgis.functionality.rapport import opret_webgis_rapport
from q_webgis.selectors import (
    RAPPORT_KNAP,
    RAPPORT_LOADING,
    VIS_RAPPORT_KNAP,
)

logger = logging.getLogger(__name__)

HEADLESS = True
DEBUG = True
TEST_TEMA = "byggesag"
TEST_RAPPORT_MAPPE = Path("tests_local_output")
TEST_RAPPORT_FILNAVN = "webgis_headless_pdf_response_test.pdf"

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

_PDF_URL_BY_PAGE: dict[int, str] = {}


async def _aabn_rapport_headless(
    page: Page,
    *,
    timeout_ms: int = WEBGIS_RAPPORT_TIMEOUT_MS,
) -> Page:
    """Åbner rapporten og opsnapper PDF-responsens URL fra netværket."""
    rapport_knap = page.locator(RAPPORT_KNAP).filter(
        has_text=re.compile(r"^\s*Rapport\s*$", re.IGNORECASE)
    ).first
    await rapport_knap.wait_for(state="visible", timeout=timeout_ms)

    logger.info("Åbner WebGIS-rapportdialogen.")
    await rapport_knap.click()
    await page.wait_for_timeout(1_000)

    vis_rapport_knap = page.locator(VIS_RAPPORT_KNAP).filter(
        has_text=re.compile(r"^\s*Vis rapport\s*$", re.IGNORECASE)
    ).first
    await vis_rapport_knap.wait_for(state="visible", timeout=timeout_ms)

    pdf_url_future: asyncio.Future[str] = (
        asyncio.get_running_loop().create_future()
    )

    def ved_response(response: Response) -> None:
        if pdf_url_future.done():
            return

        content_type = str(
            response.headers.get("content-type", "")
        ).casefold()
        content_disposition = str(
            response.headers.get("content-disposition", "")
        ).casefold()
        response_url = str(response.url or "").strip()

        er_pdf = (
            "application/pdf" in content_type
            or ".pdf" in response_url.casefold()
            or "filename=" in content_disposition
            and ".pdf" in content_disposition
        )

        if er_pdf and response_url:
            logger.info(
                "PDF-respons opsnappet: content-type=%s",
                content_type or "ukendt",
            )
            pdf_url_future.set_result(response_url)

    page.context.on("response", ved_response)

    logger.info("Bestiller den færdige PDF-rapport.")

    try:
        async with page.context.expect_page(
            timeout=timeout_ms,
        ) as ny_side_info:
            await vis_rapport_knap.click()

        rapport_side = await ny_side_info.value

        pdf_url = await asyncio.wait_for(
            asyncio.shield(pdf_url_future),
            timeout=timeout_ms / 1_000,
        )

        _PDF_URL_BY_PAGE[id(rapport_side)] = pdf_url
        logger.info("PDF-URL gemt fra netværksresponsen.")

        loading = page.locator(RAPPORT_LOADING).first
        if await loading.count() > 0:
            try:
                await loading.wait_for(
                    state="hidden",
                    timeout=timeout_ms,
                )
            except Exception:
                logger.debug(
                    "Rapport-loading kunne ikke længere findes."
                )

        return rapport_side
    finally:
        page.context.remove_listener("response", ved_response)


async def _gem_rapport_pdf_headless(
    webgis_side: Page,
    rapport_side: Page,
    destination: str | Path,
    *,
    timeout_ms: int = WEBGIS_RAPPORT_TIMEOUT_MS,
) -> Path:
    """Henter PDF'en direkte via browserkontekstens autentificerede request."""
    pdf_url = _PDF_URL_BY_PAGE.get(id(rapport_side), "").strip()
    if not pdf_url:
        raise RuntimeError(
            "Testen opsnappede ikke en PDF-URL for rapportfanen."
        )

    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Henter PDF-responsen gennem BrowserContexts request-klient."
    )
    response = await webgis_side.context.request.get(
        pdf_url,
        headers={"Accept": "application/pdf"},
        timeout=timeout_ms,
    )

    if not response.ok:
        response_text = await response.text()
        raise RuntimeError(
            "PDF-kaldet fejlede. "
            f"HTTP-status: {response.status}. "
            f"Svar: {response_text[:500]}"
        )

    pdf_bytes = await response.body()
    content_type = str(
        response.headers.get("content-type", "")
    ).strip()

    if not pdf_bytes.startswith(b"%PDF-"):
        raise RuntimeError(
            "WebGIS returnerede ikke en gyldig PDF. "
            f"Content-Type: {content_type!r}."
        )

    destination_path.write_bytes(pdf_bytes)

    if destination_path.stat().st_size == 0:
        raise RuntimeError("Den gemte PDF er tom.")

    logger.info(
        "PDF gemt: %s bytes.",
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
    rapport_modul.aabn_rapport = _aabn_rapport_headless
    rapport_modul.gem_rapport_pdf = _gem_rapport_pdf_headless

    output_path = TEST_RAPPORT_MAPPE / TEST_RAPPORT_FILNAVN
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

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
                    "FEJL_webgis_headless_pdf_response",
                    always=True,
                )
            except Exception:
                logger.exception("Fejlscreenshot kunne ikke gemmes.")
        raise
    finally:
        rapport_modul.aabn_rapport = original_aabn_rapport
        rapport_modul.gem_rapport_pdf = original_gem_rapport_pdf
        _PDF_URL_BY_PAGE.clear()

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
