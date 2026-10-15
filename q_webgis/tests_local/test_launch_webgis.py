import asyncio
import logging

from automation_server_client import AutomationServer, Credential
from dotenv import load_dotenv
from playwright.async_api import Page

from q_haderslev_vbo.playwright.browser_session import BrowserSession


WEBGIS_URL = (
    "https://webgis.intern.udcit.dk/"
    "spatialmap?profile=maxi"
)

WEBGIS_CREDENTIAL_NAME = "DIRXOAS"
JSESSIONID_COOKIE_NAME = "JSESSIONID"
COOKIE_TIMEOUT_SECONDS = 30

logger = logging.getLogger(__name__)


def hent_webgis_http_credentials() -> dict[str, str]:
    """Henter WebGIS-login fra Automation Server.

    Output:
        Dictionary med username og password, som kan sendes direkte
        til BrowserSession(http_credentials=...).

    Sikkerhed:
        Brugernavn og adgangskode bliver ikke udskrevet.
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

    return {
        "username": username,
        "password": password,
    }


async def vent_paa_jsessionid(
    page: Page,
    timeout_seconds: int = COOKIE_TIMEOUT_SECONDS,
) -> bool:
    """Venter på JSESSIONID i den aktuelle browserkontekst.

    Output:
        True, når JSESSIONID findes.

    Sikkerhed:
        Cookieværdien bliver aldrig udskrevet eller returneret.
    """
    antal_forsog = timeout_seconds * 2

    for _ in range(antal_forsog):
        cookies = await page.context.cookies(
            [WEBGIS_URL]
        )

        har_jsessionid = any(
            cookie.get("name", "").casefold()
            == JSESSIONID_COOKIE_NAME.casefold()
            and bool(cookie.get("value"))
            for cookie in cookies
        )

        if har_jsessionid:
            logger.info(
                "WebGIS-sessionens JSESSIONID er fundet."
            )
            return True

        await asyncio.sleep(0.5)

    raise RuntimeError(
        "WebGIS blev åbnet, men JSESSIONID blev ikke "
        f"fundet inden for {timeout_seconds} sekunder."
    )


async def udskriv_cookie_navne(
    page: Page,
) -> None:
    """Udskriver cookienavne uden at vise cookieindhold."""
    cookies = await page.context.cookies(
        [WEBGIS_URL]
    )

    cookie_names = sorted(
        {
            str(cookie.get("name", "")).strip()
            for cookie in cookies
            if cookie.get("name")
        }
    )

    logger.info(
        "Cookienavne efter WebGIS-login: %s",
        cookie_names,
    )


async def test_launch_webgis() -> None:
    """Tester HTTP-login, navigation og JSESSIONID."""
    load_dotenv()

    http_credentials = hent_webgis_http_credentials()

    session = BrowserSession(
        headless=False,
        debug=True,
        http_credentials=http_credentials,
    )

    page = None

    try:
        logger.info(
            "Starter browser med HTTP-credentials "
            "fra credentialen %s.",
            WEBGIS_CREDENTIAL_NAME,
        )

        await session.start()
        page = await session.new_page()

        logger.info("Åbner WebGIS.")

        response = await page.goto(
            WEBGIS_URL,
            wait_until="domcontentloaded",
            timeout=60_000,
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
            "WebGIS er åbnet på adressen: %s",
            page.url,
        )

        await vent_paa_jsessionid(page)
        await udskriv_cookie_navne(page)

        logger.info(
            "Launch-test bestået. "
            "Browseren holdes åben i 10 sekunder."
        )

        await asyncio.sleep(10)

    except Exception:
        if (
            page is not None
            and not page.is_closed()
        ):
            await session.screenshot(
                page,
                "FEJL_launch_webgis",
                always=True,
            )

        raise

    finally:
        if (
            page is not None
            and not page.is_closed()
        ):
            await session.close_page(page)

        await session.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s [%(levelname)s] "
            "%(name)s: %(message)s"
        ),
        force=True,
    )

    asyncio.run(test_launch_webgis())