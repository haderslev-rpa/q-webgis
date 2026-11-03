from __future__ import annotations

import asyncio
import logging
from pprint import pprint
from typing import Any
from urllib.parse import urlparse

from automation_server_client import AutomationServer, Credential
from dotenv import load_dotenv
from playwright.async_api import Page, Request

from q_haderslev_vbo.playwright.browser_session import BrowserSession
from q_webgis.configuration import (
    WEBGIS_CREDENTIAL_NAME,
    WEBGIS_TIMEOUT_MS,
    WEBGIS_URL,
)
from q_webgis.functionality.baadpladser import hent_baadpladser

logger = logging.getLogger(__name__)

HEADLESS = False
DEBUG = True
WEBGIS_BASE_URL = "https://webgis.intern.udcit.dk"
WEBGIS_HOSTNAME = (urlparse(WEBGIS_BASE_URL).hostname or "").casefold()
SESSION_ID_HEADER_NAME = "session-id"
SESSION_TIMEOUT_SECONDS = 300
ANTAL_RAEKKER_TIL_VISNING = 5


def hent_webgis_http_credentials() -> dict[str, str]:
    AutomationServer.from_environment()
    credential = Credential.get_credential(WEBGIS_CREDENTIAL_NAME)
    username = str(credential.username or "").strip()
    password = str(credential.password or "")
    if not username or not password:
        raise ValueError(
            f"Credentialen {WEBGIS_CREDENTIAL_NAME!r} er ufuldstændig."
        )
    return {"username": username, "password": password}


def opret_session_id_listener(page: Page) -> asyncio.Future[str]:
    loop = asyncio.get_running_loop()
    future: asyncio.Future[str] = loop.create_future()

    async def kontroller_request(request: Request) -> None:
        if future.done():
            return
        if (urlparse(request.url).hostname or "").casefold() != WEBGIS_HOSTNAME:
            return
        try:
            headers = await request.all_headers()
        except Exception:
            return
        session_id = str(headers.get(SESSION_ID_HEADER_NAME, "") or "").strip()
        if session_id and not future.done():
            logger.info("WebGIS Session-Id er fundet.")
            future.set_result(session_id)

    page.on(
        "request",
        lambda request: asyncio.create_task(kontroller_request(request)),
    )
    return future


async def launch_webgis(page: Page) -> None:
    response = await page.goto(
        WEBGIS_URL,
        wait_until="domcontentloaded",
        timeout=WEBGIS_TIMEOUT_MS,
    )
    if response is None or not response.ok:
        raise RuntimeError("WebGIS kunne ikke åbnes korrekt.")


async def vent_paa_session_id(future: asyncio.Future[str]) -> str:
    try:
        return await asyncio.wait_for(
            asyncio.shield(future),
            timeout=SESSION_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise RuntimeError("Session-Id blev ikke fundet.") from exc


def udskriv_baadpladser_sikkert(
    baadpladser: list[dict[str, Any]],
) -> None:
    viste = baadpladser[:ANTAL_RAEKKER_TIL_VISNING]
    print()
    print("=" * 80)
    print("BÅDPLADSER HENTET FRA WEBGIS")
    print("=" * 80)

    for index, baadplads in enumerate(viste, start=1):
        sikker_visning = {
            "ogc_fid": baadplads.get("ogc_fid"),
            "havn": baadplads.get("havn"),
            "straekning": baadplads.get("straekning"),
            "plads": baadplads.get("plads"),
            "driftstatus": baadplads.get("driftstatus"),
            "status_label": baadplads.get("status_label"),
            "har_shape_wkt": bool(baadplads.get("shape_wkt")),
        }
        print()
        print(f"Bådplads {index}")
        print("-" * 80)
        pprint(sikker_visning, width=120, sort_dicts=False)

    print()
    print("Antal hentede bådpladser:", len(baadpladser))
    print("Antal viste bådpladser:", len(viste))
    print("=" * 80)


async def test_hent_baadpladser() -> None:
    load_dotenv()
    session = BrowserSession(
        headless=HEADLESS,
        debug=DEBUG,
        http_credentials=hent_webgis_http_credentials(),
    )
    page: Page | None = None

    try:
        await session.start()
        page = await session.new_page()
        session_future = opret_session_id_listener(page)
        await launch_webgis(page)

        print()
        print("Åbn bådpladstabellen i WebGIS og vent, til alle rækker vises.")
        await asyncio.to_thread(input, "Tryk Enter, når tabellen er klar: ")

        session_id = await vent_paa_session_id(session_future)
        baadpladser = await hent_baadpladser(
            page=page,
            session_id=session_id,
        )
        udskriv_baadpladser_sikkert(baadpladser)
    except Exception:
        logger.exception("Testen af hent_baadpladser() fejlede.")
        if page is not None and not page.is_closed():
            try:
                await session.screenshot(page, "FEJL_hent_baadpladser", always=True)
            except Exception:
                logger.exception("Fejlscreenshot kunne ikke gemmes.")
        raise
    finally:
        if page is not None and not page.is_closed():
            await session.close_page(page)
        await session.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )
    asyncio.run(test_hent_baadpladser())
