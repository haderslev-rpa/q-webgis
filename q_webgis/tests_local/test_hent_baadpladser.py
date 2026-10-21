from __future__ import annotations

import asyncio
import logging
from pprint import pprint
from typing import Any
from urllib.parse import urlparse

from automation_server_client import (
    AutomationServer,
    Credential,
)
from dotenv import load_dotenv
from playwright.async_api import (
    Page,
    Request,
)

from q_haderslev_vbo.playwright.browser_session import (
    BrowserSession,
)
from q_webgis.functionality.baadpladser import (
    hent_baadpladser,
)


# ------------------------------------------------------------
# WebGIS
# ------------------------------------------------------------

WEBGIS_BASE_URL = "https://webgis.intern.udcit.dk"

WEBGIS_URL = (
    f"{WEBGIS_BASE_URL}/spatialmap?profile=maxi"
)

WEBGIS_HOSTNAME = (
    urlparse(WEBGIS_BASE_URL).hostname or ""
).casefold()

WEBGIS_CREDENTIAL_NAME = "DIRXOAS"

JSESSIONID_COOKIE_NAME = "JSESSIONID"
SESSION_ID_HEADER_NAME = "session-id"

NAVIGATION_TIMEOUT_MS = 60_000
SESSION_TIMEOUT_SECONDS = 60


# ------------------------------------------------------------
# Browserindstillinger
# ------------------------------------------------------------

HEADLESS = True
DEBUG = True


# ------------------------------------------------------------
# Testindstillinger
# ------------------------------------------------------------

ANTAL_BAADPLADSER_TIL_VISNING = 5


logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# Credentials
# ------------------------------------------------------------

def hent_webgis_http_credentials() -> dict[str, str]:
    """
    Henter WebGIS-login fra Automation Server.

    Output:
        Dictionary med username og password, som kan sendes
        direkte til BrowserSession.

    Sikkerhed:
        Credentialens username og password bliver ikke logget.
    """
    AutomationServer.from_environment()

    credential = Credential.get_credential(
        WEBGIS_CREDENTIAL_NAME
    )

    username = str(
        credential.username or ""
    ).strip()

    password = str(
        credential.password or ""
    )

    if not username:
        raise ValueError(
            f"Credentialen {WEBGIS_CREDENTIAL_NAME!r} "
            "mangler username."
        )

    if not password:
        raise ValueError(
            f"Credentialen {WEBGIS_CREDENTIAL_NAME!r} "
            "mangler password."
        )

    logger.info(
        "WebGIS HTTP-credentialen %r er hentet.",
        WEBGIS_CREDENTIAL_NAME,
    )

    return {
        "username": username,
        "password": password,
    }


# ------------------------------------------------------------
# Session-Id-listener
# ------------------------------------------------------------

def opret_session_id_listener(
    page: Page,
) -> asyncio.Future[str]:
    """
    Opretter en listener før navigationen.

    Listeneren undersøger WebGIS' egne requests og returnerer
    den første ikke-tomme Session-Id-header.
    """
    event_loop = asyncio.get_running_loop()

    session_id_future: asyncio.Future[str] = (
        event_loop.create_future()
    )

    async def kontroller_request(
        request: Request,
    ) -> None:
        if session_id_future.done():
            return

        request_hostname = (
            urlparse(request.url).hostname or ""
        ).casefold()

        if request_hostname != WEBGIS_HOSTNAME:
            return

        try:
            headers = await request.all_headers()
        except Exception as exc:
            logger.debug(
                "Headers kunne ikke læses fra et "
                "WebGIS-request: %s",
                exc,
            )
            return

        session_id = str(
            headers.get(
                SESSION_ID_HEADER_NAME,
                "",
            )
            or ""
        ).strip()

        if not session_id:
            return

        if session_id_future.done():
            return

        logger.info(
            "WebGIS Session-Id er fundet automatisk."
        )

        session_id_future.set_result(
            session_id
        )

    def log_listenerfejl(
        completed_task: asyncio.Task[None],
    ) -> None:
        if completed_task.cancelled():
            return

        try:
            exception = completed_task.exception()
        except asyncio.CancelledError:
            return

        if exception is not None:
            logger.error(
                "Fejl i Session-Id-listeneren: %s",
                exception,
                exc_info=(
                    type(exception),
                    exception,
                    exception.__traceback__,
                ),
            )

    def ved_request(
        request: Request,
    ) -> None:
        task = asyncio.create_task(
            kontroller_request(request)
        )

        task.add_done_callback(
            log_listenerfejl
        )

    page.on(
        "request",
        ved_request,
    )

    return session_id_future


async def vent_paa_session_id(
    session_id_future: asyncio.Future[str],
    timeout_seconds: int = SESSION_TIMEOUT_SECONDS,
) -> str:
    """
    Venter på Session-Id fra WebGIS' egne requests.

    Output:
        Den fundne Session-Id.

    Sikkerhed:
        Session-Id bliver ikke logget.
    """
    logger.info(
        "Venter på WebGIS Session-Id."
    )

    try:
        session_id = await asyncio.wait_for(
            asyncio.shield(
                session_id_future
            ),
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        raise RuntimeError(
            "WebGIS blev åbnet, men Session-Id blev "
            f"ikke fundet inden for {timeout_seconds} "
            "sekunder."
        ) from exc

    session_id = str(
        session_id or ""
    ).strip()

    if not session_id:
        raise RuntimeError(
            "WebGIS-listeneren returnerede en tom "
            "Session-Id."
        )

    return session_id


# ------------------------------------------------------------
# Åbn WebGIS
# ------------------------------------------------------------

async def launch_webgis(
    page: Page,
) -> Page:
    """
    Åbner WebGIS i den eksisterende autentificerede session.

    Output:
        Den samme Playwright-side efter navigationen.
    """
    logger.info(
        "Åbner WebGIS automatisk."
    )

    response = await page.goto(
        WEBGIS_URL,
        wait_until="domcontentloaded",
        timeout=NAVIGATION_TIMEOUT_MS,
    )

    if response is None:
        raise RuntimeError(
            "Navigationen til WebGIS returnerede "
            "ikke et HTTP-svar."
        )

    logger.info(
        "WebGIS returnerede HTTP-status %s.",
        response.status,
    )

    if not response.ok:
        raise RuntimeError(
            "WebGIS afviste navigationen med "
            f"HTTP-status {response.status}."
        )

    logger.info(
        "WebGIS er åbnet."
    )

    return page


# ------------------------------------------------------------
# JSESSIONID
# ------------------------------------------------------------

async def vent_paa_jsessionid(
    page: Page,
    timeout_seconds: int = SESSION_TIMEOUT_SECONDS,
) -> None:
    """
    Venter på, at WebGIS har oprettet en JSESSIONID-cookie.

    Sikkerhed:
        Cookieværdien bliver ikke returneret eller logget.
    """
    logger.info(
        "Venter på WebGIS-sessionens JSESSIONID."
    )

    event_loop = asyncio.get_running_loop()
    deadline = event_loop.time() + timeout_seconds

    while event_loop.time() < deadline:
        cookies = await page.context.cookies(
            [WEBGIS_BASE_URL]
        )

        har_jsessionid = any(
            str(
                cookie.get("name", "")
            ).casefold()
            == JSESSIONID_COOKIE_NAME.casefold()
            and bool(
                cookie.get("value")
            )
            for cookie in cookies
        )

        if har_jsessionid:
            logger.info(
                "WebGIS-sessionens JSESSIONID er fundet."
            )
            return

        await asyncio.sleep(0.5)

    raise RuntimeError(
        "WebGIS blev åbnet, men JSESSIONID blev "
        f"ikke fundet inden for {timeout_seconds} "
        "sekunder."
    )


# ------------------------------------------------------------
# Resultatkontrol
# ------------------------------------------------------------

def valider_baadpladser(
    baadpladser: list[dict[str, Any]],
) -> None:
    """
    Kontrollerer bådpladsresultatets grundstruktur.

    Funktionen accepterer en tom liste, fordi et gyldigt
    WebGIS-kald godt kan returnere nul resultater.
    """
    if not isinstance(baadpladser, list):
        raise TypeError(
            "hent_baadpladser() skal returnere "
            "en liste."
        )

    for index, baadplads in enumerate(
        baadpladser,
        start=1,
    ):
        if not isinstance(baadplads, dict):
            raise TypeError(
                "Alle bådpladsrækker skal være "
                "dictionaries. "
                f"Række {index} er "
                f"{type(baadplads).__name__}."
            )


# ------------------------------------------------------------
# Terminaludskrift
# ------------------------------------------------------------

def udskriv_baadpladser(
    baadpladser: list[dict[str, Any]],
    antal_til_visning: int = ANTAL_BAADPLADSER_TIL_VISNING,
) -> None:
    """
    Udskriver et begrænset antal bådpladser i terminalen.
    """
    if isinstance(
        antal_til_visning,
        bool,
    ) or not isinstance(
        antal_til_visning,
        int,
    ):
        raise TypeError(
            "antal_til_visning skal være et heltal."
        )

    if antal_til_visning <= 0:
        raise ValueError(
            "antal_til_visning skal være større end 0."
        )

    viste_baadpladser = (
        baadpladser[:antal_til_visning]
    )

    print()
    print("=" * 80)
    print("BÅDPLADSER HENTET FRA WEBGIS")
    print("=" * 80)

    if not viste_baadpladser:
        print()
        print(
            "WebGIS returnerede ingen bådpladsrækker."
        )
    else:
        for index, baadplads in enumerate(
            viste_baadpladser,
            start=1,
        ):
            print()
            print(f"Bådplads {index}")
            print("-" * 80)

            pprint(
                baadplads,
                width=120,
                sort_dicts=False,
            )

    print()
    print(
        "Antal hentede bådpladser:",
        len(baadpladser),
    )
    print(
        "Antal viste bådpladser:",
        len(viste_baadpladser),
    )
    print("=" * 80)


# ------------------------------------------------------------
# Fuldautomatisk integrationstest
# ------------------------------------------------------------

async def test_hent_baadpladser_fuldautomatisk() -> None:
    """
    Starter WebGIS og henter bådpladser uden manuel handling.

    BrowserSession får HTTP-loginoplysningerne, før browseren
    startes. Dermed undgås ERR_INVALID_AUTH_CREDENTIALS.
    """
    load_dotenv()

    http_credentials = (
        hent_webgis_http_credentials()
    )

    session = BrowserSession(
        headless=HEADLESS,
        debug=DEBUG,
        http_credentials=http_credentials,
    )

    page: Page | None = None

    try:
        logger.info("=" * 70)
        logger.info(
            "STARTER FULDAUTOMATISK BÅDPLADS-TEST"
        )
        logger.info(
            "Endpoint: spatialanalyze-get-stored-data"
        )
        logger.info("=" * 70)

        await session.start()

        page = await session.new_page()

        # Listeneren skal oprettes før navigationen,
        # ellers kan det første Session-Id-request blive overset.
        session_id_future = (
            opret_session_id_listener(page)
        )

        await launch_webgis(page)

        # JSESSIONID og Session-Id etableres under
        # WebGIS-opstarten.
        _, session_id = await asyncio.gather(
            vent_paa_jsessionid(page),
            vent_paa_session_id(
                session_id_future
            ),
        )

        # Session-Id bruges ikke direkte af testfunktionen,
        # men kontrollen dokumenterer, at WebGIS-sessionen
        # er etableret korrekt.
        if not session_id:
            raise RuntimeError(
                "WebGIS-sessionen mangler Session-Id."
            )

        logger.info(
            "WebGIS-sessionen er klar."
        )

        logger.info(
            "Henter bådpladser uden manuel handling."
        )

        baadpladser = await hent_baadpladser(
            page=page,
            session_id=session_id,
        )

        valider_baadpladser(
            baadpladser
        )

        udskriv_baadpladser(
            baadpladser=baadpladser,
            antal_til_visning=(
                ANTAL_BAADPLADSER_TIL_VISNING
            ),
        )

        logger.info("=" * 70)
        logger.info(
            "DEN FULDAUTOMATISKE BÅDPLADS-TEST "
            "ER GENNEMFØRT"
        )
        logger.info(
            "Antal hentede bådpladser: %s",
            len(baadpladser),
        )
        logger.info("=" * 70)

    except Exception:
        logger.exception(
            "Den fuldautomatiske bådplads-test "
            "fejlede."
        )

        if (
            page is not None
            and not page.is_closed()
        ):
            try:
                await session.screenshot(
                    page,
                    "FEJL_webgis_baadpladser",
                    always=True,
                )
            except Exception:
                logger.exception(
                    "Fejlscreenshot kunne ikke gemmes."
                )

        raise

    finally:
        logger.info(
            "Lukker WebGIS-side og BrowserSession."
        )

        if (
            page is not None
            and not page.is_closed()
        ):
            try:
                await session.close_page(
                    page
                )
            except Exception:
                logger.exception(
                    "WebGIS-siden kunne ikke "
                    "lukkes korrekt."
                )

        try:
            await session.close()
        except Exception:
            logger.exception(
                "BrowserSession kunne ikke "
                "lukkes korrekt."
            )


# ------------------------------------------------------------
# Lokal start
# ------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s [%(levelname)s] "
            "%(name)s: %(message)s"
        ),
        force=True,
    )

    logging.getLogger(
        "httpx"
    ).setLevel(logging.WARNING)

    logging.getLogger(
        "httpcore"
    ).setLevel(logging.WARNING)

    logging.getLogger(
        "automation_server_client"
    ).setLevel(logging.WARNING)

    logging.getLogger(
        "debugpy"
    ).setLevel(logging.WARNING)

    asyncio.run(
        test_hent_baadpladser_fuldautomatisk()
    )