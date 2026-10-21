from __future__ import annotations

import json
import logging
from typing import Any

from playwright.async_api import Page


logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# WebGIS endpoint
# ------------------------------------------------------------

WEBGIS_STORED_DATA_URL = (
    "https://webgis.intern.udcit.dk/"
    "spatialmap?page=spatialanalyze-get-stored-data"
)

DEFAULT_TIMEOUT_MS = 60_000


# ------------------------------------------------------------
# START: hent_baadpladser
# ------------------------------------------------------------

async def hent_baadpladser(
    page: Page,
    session_id: str,
    *,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> list[dict[str, Any]]:
    """
    Henter gemte bådpladsdata fra den aktuelle WebGIS-session.

    Kaldet udføres med browserens egen fetch-funktion. Dermed
    genbruges browserens HTTP-login og JSESSIONID.

    Parametre:
        page:
            Den allerede åbnede og autentificerede WebGIS-side.

        session_id:
            Session-Id opsnappet fra WebGIS' egne requests.

        timeout_ms:
            Maksimal ventetid for browserkaldet i millisekunder.

    Output:
        Liste med de konkrete bådpladsrækker som dictionaries.

    Sikkerhed:
        Session-Id, cookies og formularindhold logges ikke.
    """
    _valider_page(page)

    valideret_session_id = _valider_tekst(
        value=session_id,
        field_name="session_id",
    )

    valideret_timeout_ms = _valider_positivt_heltal(
        value=timeout_ms,
        field_name="timeout_ms",
    )

    # Payloaden gengiver den verificerede request.
    formular_data = {
        "page": "spatialanalyze-get-stored-data",
    }

    logger.info(
        "Henter gemte bådpladsdata fra WebGIS."
    )

    browser_resultat = await page.evaluate(
        """
        async ({
            url,
            sessionId,
            formValues,
            timeoutMs
        }) => {
            const controller = new AbortController();

            const timeoutHandle = setTimeout(
                () => controller.abort(),
                timeoutMs
            );

            try {
                const formBody = new URLSearchParams();

                for (
                    const [fieldName, fieldValue]
                    of Object.entries(formValues)
                ) {
                    formBody.append(
                        fieldName,
                        String(fieldValue)
                    );
                }

                const response = await fetch(
                    url,
                    {
                        method: "POST",
                        credentials: "include",
                        headers: {
                            "Accept": (
                                "application/json, "
                                + "text/javascript, "
                                + "*/*; q=0.01"
                            ),
                            "Content-Type": (
                                "application/"
                                + "x-www-form-urlencoded; "
                                + "charset=UTF-8"
                            ),
                            "Session-Id": sessionId,
                            "X-Requested-With": (
                                "XMLHttpRequest"
                            )
                        },
                        body: formBody.toString(),
                        signal: controller.signal
                    }
                );

                const responseText =
                    await response.text();

                return {
                    ok: response.ok,
                    status: response.status,
                    statusText: response.statusText,
                    contentType: (
                        response.headers.get(
                            "content-type"
                        ) || ""
                    ),
                    responseText: responseText,
                    finalUrl: response.url
                };
            } catch (error) {
                return {
                    ok: false,
                    status: 0,
                    statusText: "",
                    contentType: "",
                    responseText: "",
                    finalUrl: "",
                    browserError: (
                        error instanceof Error
                            ? (
                                error.name
                                + ": "
                                + error.message
                            )
                            : String(error)
                    )
                };
            } finally {
                clearTimeout(timeoutHandle);
            }
        }
        """,
        {
            "url": WEBGIS_STORED_DATA_URL,
            "sessionId": valideret_session_id,
            "formValues": formular_data,
            "timeoutMs": valideret_timeout_ms,
        },
    )

    fetch_resultat = _valider_fetch_resultat(
        browser_resultat
    )

    browser_error = str(
        fetch_resultat.get("browserError")
        or ""
    ).strip()

    if browser_error:
        raise RuntimeError(
            "WebGIS-kaldet til bådpladser kunne ikke "
            "udføres i browseren. "
            f"Browserfejl: {browser_error}"
        )

    status = fetch_resultat["status"]

    if not fetch_resultat["ok"]:
        response_preview = _lav_sikkert_response_preview(
            fetch_resultat.get("responseText")
        )

        raise RuntimeError(
            "WebGIS-kaldet til bådpladser fejlede med "
            f"HTTP-status {status}. "
            f"Statusbesked: "
            f"{fetch_resultat.get('statusText')!s}. "
            f"Svareksempel: {response_preview}"
        )

    response_text = str(
        fetch_resultat.get("responseText")
        or ""
    ).strip()

    if not response_text:
        raise RuntimeError(
            "WebGIS returnerede et tomt svar ved "
            "hentning af bådpladser."
        )

    response_data = _parse_json(
        response_text
    )

    baadpladser = _udtraek_baadpladser(
        response_data
    )

    logger.info(
        "WebGIS returnerede %s læsbare bådpladsrækker.",
        len(baadpladser),
    )

    return baadpladser


# ------------------------------------------------------------
# SLUT: hent_baadpladser
# ------------------------------------------------------------


# ------------------------------------------------------------
# JSON
# ------------------------------------------------------------

def _parse_json(
    response_text: str,
) -> Any:
    """
    Parser WebGIS-svaret som JSON.

    Output:
        Den parsede JSON-værdi.
    """
    try:
        return json.loads(
            response_text
        )
    except json.JSONDecodeError as exc:
        response_preview = _lav_sikkert_response_preview(
            response_text
        )

        raise RuntimeError(
            "WebGIS returnerede ikke gyldigt JSON ved "
            "hentning af bådpladser. "
            f"JSON-fejl: {exc.msg}. "
            f"Svareksempel: {response_preview}"
        ) from exc


# ------------------------------------------------------------
# Resultatstruktur
# ------------------------------------------------------------

def _udtraek_baadpladser(
    response_data: Any,
) -> list[dict[str, Any]]:
    """
    Finder den mest sandsynlige liste med bådpladsrækker.

    Funktionen undersøger WebGIS-svaret rekursivt, fordi
    datarækker kan være pakket ind i dictionaries og lister.

    Output:
        Den største liste med dictionaries, som ikke kun
        indeholder kendte metadatafelter.
    """
    kandidater: list[
        list[dict[str, Any]]
    ] = []

    def besoeg(
        current_value: Any,
    ) -> None:
        if isinstance(
            current_value,
            list,
        ):
            dictionary_rows = [
                element
                for element in current_value
                if isinstance(element, dict)
                and not _er_metadata_raekke(
                    element
                )
            ]

            if dictionary_rows:
                kandidater.append(
                    dictionary_rows
                )

            for element in current_value:
                besoeg(
                    element
                )

            return

        if isinstance(
            current_value,
            dict,
        ):
            for nested_value in (
                current_value.values()
            ):
                besoeg(
                    nested_value
                )

    besoeg(
        response_data
    )

    if not kandidater:
        if (
            isinstance(response_data, dict)
            and not _er_metadata_raekke(
                response_data
            )
        ):
            return [
                response_data
            ]

        return []

    return max(
        kandidater,
        key=len,
    )


def _er_metadata_raekke(
    row: dict[str, Any],
) -> bool:
    """
    Kontrollerer, om en dictionary kun ligner WebGIS-metadata.
    """
    if not isinstance(
        row,
        dict,
    ):
        return True

    keys = {
        str(key).casefold()
        for key in row
    }

    metadata_keys = {
        "_name",
        "_class",
        "_pcolid",
        "rowcount",
        "xmin",
        "ymin",
        "xmax",
        "ymax",
    }

    return (
        bool(keys)
        and keys.issubset(
            metadata_keys
        )
    )


# ------------------------------------------------------------
# Validering
# ------------------------------------------------------------

def _valider_fetch_resultat(
    value: Any,
) -> dict[str, Any]:
    """
    Validerer resultatet fra browserens fetch-kald.

    Output:
        Det validerede resultat som dictionary.
    """
    if not isinstance(
        value,
        dict,
    ):
        raise RuntimeError(
            "WebGIS-kaldet til bådpladser returnerede "
            "et ugyldigt browserresultat."
        )

    status = value.get(
        "status"
    )

    if isinstance(
        status,
        bool,
    ):
        raise RuntimeError(
            "WebGIS-kaldet til bådpladser returnerede "
            "en ugyldig HTTP-status."
        )

    if not isinstance(
        status,
        int,
    ):
        raise RuntimeError(
            "WebGIS-kaldet til bådpladser returnerede "
            "ikke en numerisk HTTP-status."
        )

    if not isinstance(
        value.get("ok"),
        bool,
    ):
        raise RuntimeError(
            "WebGIS-kaldet til bådpladser returnerede "
            "ikke en gyldig ok-status."
        )

    return value


def _valider_page(
    page: Page,
) -> None:
    """
    Kontrollerer, at WebGIS-siden kan bruges.
    """
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
    """
    Returnerer en obligatorisk, trimmet tekstværdi.
    """
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
    """
    Returnerer værdien som et positivt heltal.
    """
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


# ------------------------------------------------------------
# Fejlpreview
# ------------------------------------------------------------

def _lav_sikkert_response_preview(
    value: Any,
    maximum_length: int = 500,
) -> str:
    """
    Laver et begrænset preview af WebGIS-svaret.

    Session-Id og cookies ligger ikke i response-bodyen
    og bliver ikke tilføjet til previewet.
    """
    text = " ".join(
        str(value or "").split()
    )

    if not text:
        return "<tomt svar>"

    if len(text) <= maximum_length:
        return text

    return (
        text[:maximum_length]
        + "..."
    )


__all__ = [
    "WEBGIS_STORED_DATA_URL",
    "hent_baadpladser",
]