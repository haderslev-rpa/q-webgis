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
from q_webgis.functionality.spatialanalyze import (
    hent_spatialanalyze_raekker,
    spatialanalyze,
)


# ------------------------------------------------------------
# WebGIS
# ------------------------------------------------------------

WEBGIS_BASE_URL = "https://webgis.intern.udcit.dk"
WEBGIS_URL = f"{WEBGIS_BASE_URL}/spatialmap?profile=maxi"
WEBGIS_HOSTNAME = (urlparse(WEBGIS_BASE_URL).hostname or "").casefold()
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
# Spatialanalyse
# ------------------------------------------------------------

DATASOURCE = "ds-byggesag_cases_matrikel"
COMMAND = "read-spatial"
SPATIAL_EXPRESSION = "this"
JSON_TYPES = "true"
OUTPUT_FORMAT = "json"
ERROR_CONTENT_TYPE = "json"
PROFILE = "maxi"
MAX_ROWS = 20_000


# ------------------------------------------------------------
# Verificerede koordinater fra UI-requestet
# ------------------------------------------------------------

MIN_X_WC = 471348.098304
MIN_Y_WC = 6096657.6526848
MAX_X_WC = 569651.901696
MAX_Y_WC = 6149342.3473152


# ------------------------------------------------------------
# Testindstillinger
# ------------------------------------------------------------

ANTAL_RAEKKER_TIL_VISNING = 5

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# Credentials
# ------------------------------------------------------------


def hent_webgis_http_credentials() -> dict[str, str]:
    """Henter WebGIS-login fra Automation Server.

    Output:
        Dictionary med username og password til BrowserSession.

    Sikkerhed:
        Loginoplysningerne bliver ikke logget eller udskrevet.
    """
    AutomationServer.from_environment()
    credential = Credential.get_credential(WEBGIS_CREDENTIAL_NAME)

    username = str(credential.username or "").strip()
    password = str(credential.password or "")

    if not username:
        raise ValueError(
            f"Credentialen {WEBGIS_CREDENTIAL_NAME!r} mangler username."
        )

    if not password:
        raise ValueError(
            f"Credentialen {WEBGIS_CREDENTIAL_NAME!r} mangler password."
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
) -> asyncio.Future:
    event_loop = asyncio.get_running_loop()
    session_id_future: asyncio.Future[str] = event_loop.create_future()

    async def kontroller_request(request: Request) -> None:
        if session_id_future.done():
            return

        request_hostname = (urlparse(request.url).hostname or "").casefold()

        if request_hostname != WEBGIS_HOSTNAME:
            return

        try:
            headers = await request.all_headers()
        except Exception as exc:
            logger.debug(
                "Headers kunne ikke læses fra et WebGIS-request: %s",
                exc,
            )
            return

        session_id = str(
            headers.get(SESSION_ID_HEADER_NAME, "") or ""
        ).strip()

        if not session_id or session_id_future.done():
            return

        logger.info("WebGIS Session-Id er fundet automatisk.")
        session_id_future.set_result(session_id)

    def log_listenerfejl(completed_task: asyncio.Task[None]) -> None:
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

    def ved_request(request: Request) -> None:
        task = asyncio.create_task(kontroller_request(request))
        task.add_done_callback(log_listenerfejl)

    page.on("request", ved_request)
    return session_id_future


async def vent_paa_session_id(
    session_id_future: asyncio.Future[str],
    timeout_seconds: int = SESSION_TIMEOUT_SECONDS,
) -> str:
    """Venter på Session-Id fra WebGIS' egne requests."""
    logger.info("Venter på WebGIS Session-Id.")

    try:
        session_id = await asyncio.wait_for(
            asyncio.shield(session_id_future),
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        raise RuntimeError(
            "WebGIS blev åbnet, men Session-Id blev ikke fundet "
            f"inden for {timeout_seconds} sekunder."
        ) from exc

    session_id = str(session_id or "").strip()

    if not session_id:
        raise RuntimeError(
            "WebGIS-listeneren returnerede en tom Session-Id."
        )

    return session_id


# ------------------------------------------------------------
# Åbn WebGIS
# ------------------------------------------------------------


async def launch_webgis(page: Page) -> Page:
    """Åbner WebGIS automatisk i den eksisterende browsersession."""
    logger.info("Åbner WebGIS automatisk.")

    response = await page.goto(
        WEBGIS_URL,
        wait_until="domcontentloaded",
        timeout=NAVIGATION_TIMEOUT_MS,
    )

    if response is None:
        raise RuntimeError(
            "Navigationen til WebGIS returnerede ikke et HTTP-svar."
        )

    logger.info("WebGIS returnerede HTTP-status %s.", response.status)

    if not response.ok:
        raise RuntimeError(
            "WebGIS afviste navigationen med "
            f"HTTP-status {response.status}."
        )

    logger.info("WebGIS er åbnet.")
    return page


# ------------------------------------------------------------
# JSESSIONID
# ------------------------------------------------------------


async def vent_paa_jsessionid(
    page: Page,
    timeout_seconds: int = SESSION_TIMEOUT_SECONDS,
) -> None:
    """Venter på JSESSIONID uden at returnere cookieindholdet."""
    logger.info("Venter på WebGIS-sessionens JSESSIONID.")

    event_loop = asyncio.get_running_loop()
    deadline = event_loop.time() + timeout_seconds

    while event_loop.time() < deadline:
        cookies = await page.context.cookies([WEBGIS_BASE_URL])

        har_jsessionid = any(
            str(cookie.get("name", "")).casefold()
            == JSESSIONID_COOKIE_NAME.casefold()
            and bool(cookie.get("value"))
            for cookie in cookies
        )

        if har_jsessionid:
            logger.info("WebGIS-sessionens JSESSIONID er fundet.")
            return

        await asyncio.sleep(0.5)

    raise RuntimeError(
        "WebGIS blev åbnet, men JSESSIONID blev ikke fundet "
        f"inden for {timeout_seconds} sekunder."
    )


# ------------------------------------------------------------
# Resultatkontrol
# ------------------------------------------------------------


def valider_analyseresultat(resultat: dict[str, Any]) -> None:
    """Kontrollerer spatialanalyze-resultatets grundstruktur."""
    if not isinstance(resultat, dict):
        raise TypeError(
            "spatialanalyze() skal returnere en dictionary."
        )

    if not resultat:
        raise AssertionError(
            "spatialanalyze() returnerede en tom dictionary."
        )


def valider_raekker(raekker: list[dict[str, Any]]) -> None:
    """Kontrollerer de konkrete spatialanalyse-rækker."""
    if not isinstance(raekker, list):
        raise TypeError(
            "hent_spatialanalyze_raekker() skal returnere en liste."
        )

    for index, raekke in enumerate(raekker, start=1):
        if not isinstance(raekke, dict):
            raise TypeError(
                "Alle spatialanalyse-rækker skal være dictionaries. "
                f"Række {index} er {type(raekke).__name__}."
            )


def find_rowcount(value: Any) -> int | None:
    """Finder rowcount rekursivt i analysesvaret."""
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if str(key).casefold() == "rowcount":
                try:
                    return int(nested_value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "Analysens rowcount kunne ikke konverteres "
                        "til et heltal."
                    ) from exc

        for nested_value in value.values():
            found_rowcount = find_rowcount(nested_value)
            if found_rowcount is not None:
                return found_rowcount

    elif isinstance(value, list):
        for nested_value in value:
            found_rowcount = find_rowcount(nested_value)
            if found_rowcount is not None:
                return found_rowcount

    return None


def valider_antal_raekker(
    resultat: dict[str, Any],
    raekker: list[dict[str, Any]],
) -> int | None:
    """Sammenligner analysens rowcount med de hentede rækker."""
    rowcount = find_rowcount(resultat)

    if rowcount is None:
        logger.warning(
            "Analysesvaret indeholder ikke et læsbart rowcount-felt."
        )
        return None

    if rowcount < 0:
        raise AssertionError(
            f"Analysens rowcount må ikke være negativ: {rowcount}."
        )

    if rowcount > MAX_ROWS:
        raise AssertionError(
            "Analysens rowcount er større end MAX_ROWS. "
            f"Rowcount: {rowcount}. MAX_ROWS: {MAX_ROWS}."
        )

    if len(raekker) != rowcount:
        raise AssertionError(
            "Antallet af hentede rækker svarer ikke til analysens "
            f"rowcount. Rowcount: {rowcount}. "
            f"Hentede rækker: {len(raekker)}."
        )

    logger.info(
        "Antal hentede rækker matcher rowcount: %s.",
        rowcount,
    )
    return rowcount


# ------------------------------------------------------------
# Terminaludskrift
# ------------------------------------------------------------


def udskriv_analyseoversigt(resultat: dict[str, Any]) -> None:
    """Udskriver spatialanalysens opsummering."""
    print()
    print("=" * 80)
    print("FULDAUTOMATISK SPATIALANALYSE GENNEMFØRT")
    print("=" * 80)
    print()
    pprint(resultat, width=120, sort_dicts=False)
    print()
    print("=" * 80)


def udskriv_foerste_raekker(
    raekker: list[dict[str, Any]],
    antal_raekker: int = ANTAL_RAEKKER_TIL_VISNING,
) -> None:
    """Udskriver et begrænset antal konkrete datarækker."""
    if isinstance(antal_raekker, bool) or not isinstance(
        antal_raekker,
        int,
    ):
        raise TypeError("antal_raekker skal være et heltal.")

    if antal_raekker <= 0:
        raise ValueError("antal_raekker skal være større end 0.")

    viste_raekker = raekker[:antal_raekker]

    print()
    print("=" * 80)
    print("FØRSTE RÆKKER FRA SPATIALANALYSEN")
    print("=" * 80)

    if not viste_raekker:
        print()
        print("WebGIS returnerede ingen læsbare datarækker.")
    else:
        for index, raekke in enumerate(viste_raekker, start=1):
            print()
            print(f"Række {index}")
            print("-" * 80)
            pprint(raekke, width=120, sort_dicts=False)

    print()
    print("Antal hentede rækker:", len(raekker))
    print("Antal viste rækker:", len(viste_raekker))
    print("=" * 80)


# ------------------------------------------------------------
# Fuldautomatisk integrationstest
# ------------------------------------------------------------


async def test_spatialanalyze_fuldautomatisk() -> None:
    """Kører hele WebGIS-flowet uden manuel brugerhandling."""
    load_dotenv()
    http_credentials = hent_webgis_http_credentials()

    session = BrowserSession(
        headless=HEADLESS,
        debug=DEBUG,
        http_credentials=http_credentials,
    )

    page: Page | None = None

    try:
        logger.info("=" * 70)
        logger.info("STARTER FULDAUTOMATISK WEBGIS-TEST")
        logger.info("Datasource: %s", DATASOURCE)
        logger.info("Maksimalt antal rækker: %s", MAX_ROWS)
        logger.info("=" * 70)

        await session.start()
        page = await session.new_page()

        # Listeneren skal være aktiv før navigationen.
        session_id_future = opret_session_id_listener(page)

        await launch_webgis(page)

        # Begge sessionselementer etableres under WebGIS-opstarten.
        _, session_id = await asyncio.gather(
            vent_paa_jsessionid(page),
            vent_paa_session_id(session_id_future),
        )

        logger.info("WebGIS-sessionen er klar.")
        logger.info("Starter spatialanalyse uden manuel handling.")

        resultat = await spatialanalyze(
            page=page,
            session_id=session_id,
            datasource=DATASOURCE,
            min_x_wc=MIN_X_WC,
            min_y_wc=MIN_Y_WC,
            max_x_wc=MAX_X_WC,
            max_y_wc=MAX_Y_WC,
            maxrows=MAX_ROWS,
            command=COMMAND,
            spatialexpression=SPATIAL_EXPRESSION,
            jsontypes=JSON_TYPES,
            outputformat=OUTPUT_FORMAT,
            error_content_type=ERROR_CONTENT_TYPE,
            profile=PROFILE,
        )

        valider_analyseresultat(resultat)
        udskriv_analyseoversigt(resultat)

        logger.info("Henter konkrete datarækker uden manuel handling.")

        raekker = await hent_spatialanalyze_raekker(
            page=page,
            session_id=session_id,
            maxrows=MAX_ROWS,
            jsontypes=JSON_TYPES,
            outputformat=OUTPUT_FORMAT,
            error_content_type=ERROR_CONTENT_TYPE,
        )

        valider_raekker(raekker)
        rowcount = valider_antal_raekker(
            resultat=resultat,
            raekker=raekker,
        )

        udskriv_foerste_raekker(
            raekker=raekker,
            antal_raekker=ANTAL_RAEKKER_TIL_VISNING,
        )

        logger.info("=" * 70)
        logger.info("DEN FULDAUTOMATISKE WEBGIS-TEST ER GENNEMFØRT")
        logger.info("Analysens rowcount: %s", rowcount)
        logger.info("Antal hentede rækker: %s", len(raekker))
        logger.info("=" * 70)

    except Exception:
        logger.exception("Den fuldautomatiske WebGIS-test fejlede.")

        if page is not None and not page.is_closed():
            try:
                await session.screenshot(
                    page,
                    "FEJL_webgis_fuldautomatisk",
                    always=True,
                )
            except Exception:
                logger.exception("Fejlscreenshot kunne ikke gemmes.")

        raise

    finally:
        logger.info("Lukker WebGIS-side og BrowserSession.")

        if page is not None and not page.is_closed():
            try:
                await session.close_page(page)
            except Exception:
                logger.exception("WebGIS-siden kunne ikke lukkes korrekt.")

        try:
            await session.close()
        except Exception:
            logger.exception("BrowserSession kunne ikke lukkes korrekt.")


# ------------------------------------------------------------
# Lokal start
# ------------------------------------------------------------


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("automation_server_client").setLevel(logging.WARNING)
    logging.getLogger("debugpy").setLevel(logging.WARNING)

    asyncio.run(test_spatialanalyze_fuldautomatisk())