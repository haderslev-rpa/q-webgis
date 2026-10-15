from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from automation_server_client import (
    AutomationServer,
    Credential,
)
from dotenv import load_dotenv
from playwright.async_api import Page

from q_haderslev_vbo.playwright.browser_session import (
    BrowserSession,
)
from q_webgis.configuration import (
    WEBGIS_CREDENTIAL_NAME,
    WEBGIS_URL,
)
from q_webgis.functionality.rapport import (
    opret_webgis_rapport,
)


logger = logging.getLogger(__name__)


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


def hent_webgis_http_credentials() -> dict[str, str]:
    """
    Henter WebGIS HTTP-login fra Automation Server.

    Output:
        Dictionary med username og password.
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


async def test_webgis_rapport() -> None:
    """
    Tester det komplette WebGIS-rapportflow.

    Rapportfunktionen tager trinscreenshots gennem den modtagne
    BrowserSession. Testen tager desuden et afsluttende screenshot
    og et fejlscreenshot, hvis fejlen sker uden for rapportflowet.

    Output:
        Gemmer PDF'en i tests_local_output/webgis_byggesag.pdf.
    """

    load_dotenv()

    http_credentials = (
        hent_webgis_http_credentials()
    )

    session = BrowserSession(
        headless=False,
        debug=True,
        http_credentials=http_credentials,
    )

    page: Page | None = None

    try:
        logger.info(
            "Starter BrowserSession."
        )

        await session.start()

        page = await session.new_page()

        logger.info(
            "Åbner WebGIS."
        )

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

        if not response.ok:
            raise RuntimeError(
                "WebGIS returnerede HTTP-status "
                f"{response.status}."
            )

        rapportsti = await opret_webgis_rapport(
            page=page,
            session=session,
            wkt=WKT,
            tema="byggesag",
            rapportmappe=Path(
                "tests_local_output"
            ),
            filnavn="webgis_byggesag.pdf",
            vaelg_jordstykker_byggesag=True,
        )

        if not rapportsti.exists():
            raise AssertionError(
                "PDF-rapporten blev ikke fundet "
                "efter WebGIS-flowet."
            )

        if rapportsti.stat().st_size == 0:
            raise AssertionError(
                "PDF-rapporten er tom."
            )

        if not rapportsti.read_bytes().startswith(
            b"%PDF-"
        ):
            raise AssertionError(
                "Rapportfilen har ikke en gyldig "
                "PDF-signatur."
            )

        await session.screenshot(
            page,
            "STEP_07_webgis_rapporttest_faerdig",
            always=True,
        )

        logger.info(
            "WebGIS-rapporttesten er gennemført."
        )

        logger.info(
            "Rapport: %s",
            rapportsti.resolve(),
        )

    except Exception:
        logger.exception(
            "WebGIS-rapporttesten fejlede."
        )

        if (
            page is not None
            and not page.is_closed()
        ):
            try:
                await session.screenshot(
                    page,
                    "FEJL_webgis_rapporttest",
                    always=True,
                )
            except Exception:
                logger.exception(
                    "Fejlscreenshot kunne ikke gemmes."
                )

        raise

    finally:
        logger.info(
            "Lukker WebGIS og BrowserSession."
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
                    "WebGIS-siden kunne ikke lukkes."
                )

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

    logging.getLogger(
        "httpx"
    ).setLevel(logging.WARNING)

    logging.getLogger(
        "httpcore"
    ).setLevel(logging.WARNING)

    logging.getLogger(
        "automation_server_client"
    ).setLevel(logging.WARNING)

    asyncio.run(
        test_webgis_rapport()
    )