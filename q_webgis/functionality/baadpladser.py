from __future__ import annotations

import logging
from typing import Any

from playwright.async_api import Page

from q_webgis.configuration import (
    WEBGIS_MAXROWS,
    WEBGIS_TIMEOUT_MS,
)
from q_webgis.functionality.spatialanalyze import (
    hent_spatialanalyze_raekker,
)


logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# Bådpladsindstillinger
# ------------------------------------------------------------

BAADPLADS_MAXROWS = WEBGIS_MAXROWS
BAADPLADS_JSONTYPES = "true"
BAADPLADS_OUTPUTFORMAT = "json"
BAADPLADS_ERROR_CONTENT_TYPE = "json"


# ------------------------------------------------------------
# START: hent_baadpladser
# ------------------------------------------------------------

async def hent_baadpladser(
    page: Page,
    session_id: str,
    *,
    maxrows: int = BAADPLADS_MAXROWS,
    timeout_ms: int = WEBGIS_TIMEOUT_MS,
) -> list[dict[str, Any]]:
    """
    Henter alle bådpladser fra den seneste spatialanalyse i den
    aktuelle WebGIS-session.

    Funktionen starter ikke selv spatialanalysen. Analysen for
    ds-baadplads skal være gennemført først med samme Page,
    JSESSIONID og Session-Id.

    Parametre:
        page:
            Den åbne og autentificerede WebGIS-side.

        session_id:
            Session-Id opsnappet fra WebGIS' egne requests.

        maxrows:
            Maksimalt antal rækker, WebGIS må returnere.

        timeout_ms:
            Maksimal ventetid for requestet i millisekunder.

    Output:
        En liste med alle returnerede bådpladsrækker.

        Hver række returneres uændret fra den eksisterende
        hent_spatialanalyze_raekker()-funktion.

    Fejl:
        RuntimeError hvis WebGIS-siden er lukket, eller hvis
        resultatet rammer maxrows og derfor kan være afkortet.
    """
    _valider_page(
        page
    )

    valideret_session_id = _valider_tekst(
        value=session_id,
        field_name="session_id",
    )

    valideret_maxrows = _valider_positivt_heltal(
        value=maxrows,
        field_name="maxrows",
    )

    valideret_timeout_ms = _valider_positivt_heltal(
        value=timeout_ms,
        field_name="timeout_ms",
    )

    logger.info(
        "Henter op til %s bådpladser fra den seneste "
        "WebGIS-spatialanalyse.",
        valideret_maxrows,
    )

    baadpladser = await hent_spatialanalyze_raekker(
        page=page,
        session_id=valideret_session_id,
        maxrows=valideret_maxrows,
        jsontypes=BAADPLADS_JSONTYPES,
        outputformat=BAADPLADS_OUTPUTFORMAT,
        error_content_type=(
            BAADPLADS_ERROR_CONTENT_TYPE
        ),
        timeout_ms=valideret_timeout_ms,
    )

    _valider_baadpladsraekker(
        baadpladser
    )

    if len(baadpladser) >= valideret_maxrows:
        raise RuntimeError(
            "WebGIS returnerede det maksimalt tilladte "
            "antal bådpladser. Resultatet kan derfor være "
            "afkortet. "
            f"Antal rækker: {len(baadpladser)}. "
            f"Maxrows: {valideret_maxrows}."
        )

    logger.info(
        "WebGIS returnerede %s bådpladser.",
        len(baadpladser),
    )

    return baadpladser


# ------------------------------------------------------------
# SLUT: hent_baadpladser
# ------------------------------------------------------------


# ------------------------------------------------------------
# Validering
# ------------------------------------------------------------

def _valider_baadpladsraekker(
    baadpladser: Any,
) -> None:
    """Kontrollerer, at resultatet er en liste af dictionaries."""
    if not isinstance(
        baadpladser,
        list,
    ):
        raise TypeError(
            "hent_spatialanalyze_raekker() skal "
            "returnere en liste."
        )

    for index, baadplads in enumerate(
        baadpladser,
        start=1,
    ):
        if not isinstance(
            baadplads,
            dict,
        ):
            raise TypeError(
                "Alle bådpladsrækker skal være "
                "dictionaries. "
                f"Række {index} har typen "
                f"{type(baadplads).__name__}."
            )


def _valider_page(
    page: Page,
) -> None:
    """Kontrollerer, at Playwright-siden kan anvendes."""
    if page is None:
        raise ValueError(
            "page skal angives."
        )

    if page.is_closed():
        raise RuntimeError(
            "WebGIS-siden er lukket og kan ikke "
            "bruges til at hente bådpladser."
        )


def _valider_tekst(
    *,
    value: Any,
    field_name: str,
) -> str:
    """Returnerer en obligatorisk, trimmet tekstværdi."""
    if not isinstance(
        value,
        str,
    ):
        raise TypeError(
            f"{field_name} skal være tekst."
        )

    cleaned_value = value.strip()

    if not cleaned_value:
        raise ValueError(
            f"{field_name} må ikke være tom."
        )

    return cleaned_value


def _valider_positivt_heltal(
    *,
    value: Any,
    field_name: str,
) -> int:
    """Returnerer værdien som et positivt heltal."""
    if isinstance(
        value,
        bool,
    ):
        raise TypeError(
            f"{field_name} må ikke være boolsk."
        )

    try:
        integer_value = int(
            value
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise TypeError(
            f"{field_name} skal være et heltal."
        ) from exc

    if integer_value <= 0:
        raise ValueError(
            f"{field_name} skal være større end 0."
        )

    return integer_value


__all__ = [
    "BAADPLADS_MAXROWS",
    "hent_baadpladser",
]
