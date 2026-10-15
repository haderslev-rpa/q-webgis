from __future__ import annotations

import logging
from typing import Any

from playwright.async_api import Page


logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# WebGIS endpoint
# ------------------------------------------------------------

SPATIALANALYZE_URL = (
    "https://webgis.intern.udcit.dk/"
    "spatialmap?page=spatialanalyze"
)

DEFAULT_TIMEOUT_MS = 60_000


# ------------------------------------------------------------
# Spatialanalyze
# ------------------------------------------------------------


async def spatialanalyze(
    page: Page,
    session_id: str,
    datasource: str,
    min_x_wc: float,
    min_y_wc: float,
    max_x_wc: float,
    max_y_wc: float,
    maxrows: int,
    *,
    command: str,
    spatialexpression: str,
    jsontypes: str,
    outputformat: str,
    error_content_type: str,
    profile: str = "maxi",
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> dict[str, Any]:
    """Udfører WebGIS spatialanalyze i den åbne browser.

    Kaldet sendes som application/x-www-form-urlencoded gennem
    browserens egen fetch-funktion. Derfor genbruges browserens
    eksisterende HTTP-login og JSESSIONID.

    Parametre:
        page:
            Den allerede åbnede og autentificerede WebGIS-side.

        session_id:
            Session-Id opsnappet fra WebGIS' egne requests.

        datasource:
            WebGIS-datasourcen, eksempelvis
            "ds-byggesag_cases_matrikel".

        min_x_wc, min_y_wc, max_x_wc, max_y_wc:
            Koordinaterne til analyseområdet.

        maxrows:
            Maksimalt antal resultatrækker.

        command:
            Den præcise command-værdi fra Request 21.

        spatialexpression:
            Den præcise spatialexpression-værdi fra Request 21.

        jsontypes:
            Den præcise jsontypes-værdi fra Request 21.

        outputformat:
            Den præcise outputformat-værdi fra Request 21.

        error_content_type:
            Den præcise værdi for jdaf.error.contenttype
            fra Request 21.

        profile:
            WebGIS-profil. Standarden er "maxi".

        timeout_ms:
            Maksimal ventetid for browserkaldet.

    Output:
        WebGIS-svaret som en dictionary.

    Sikkerhed:
        Session-Id, cookies og formularindhold logges ikke.
    """
    _valider_page(page)

    session_id = _valider_tekst(
        value=session_id,
        field_name="session_id",
    )

    datasource = _valider_tekst(
        value=datasource,
        field_name="datasource",
    )

    command = _valider_tekst(
        value=command,
        field_name="command",
    )

    spatialexpression = _valider_tekst(
        value=spatialexpression,
        field_name="spatialexpression",
    )

    jsontypes = _valider_tekst(
        value=jsontypes,
        field_name="jsontypes",
    )

    outputformat = _valider_tekst(
        value=outputformat,
        field_name="outputformat",
    )

    error_content_type = _valider_tekst(
        value=error_content_type,
        field_name="error_content_type",
    )

    profile = _valider_tekst(
        value=profile,
        field_name="profile",
    )

    maxrows = _valider_positivt_heltal(
        value=maxrows,
        field_name="maxrows",
    )

    timeout_ms = _valider_positivt_heltal(
        value=timeout_ms,
        field_name="timeout_ms",
    )

    koordinater = _valider_koordinater(
        min_x_wc=min_x_wc,
        min_y_wc=min_y_wc,
        max_x_wc=max_x_wc,
        max_y_wc=max_y_wc,
    )

    formular_data = {
        "page": "spatialanalyze",
        "profile": profile,
        "command": command,
        "datasource": datasource,
        "spatialexpression": spatialexpression,
        "min_x_wc": str(koordinater["min_x_wc"]),
        "min_y_wc": str(koordinater["min_y_wc"]),
        "max_x_wc": str(koordinater["max_x_wc"]),
        "max_y_wc": str(koordinater["max_y_wc"]),
        "maxrows": str(maxrows),
        "outputformat": outputformat,
        "jsontypes": jsontypes,
        "jdaf.error.contenttype": error_content_type,
    }

    logger.info(
        "Starter WebGIS spatialanalyze for datasource=%s, "
        "maxrows=%s.",
        datasource,
        maxrows,
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
            "url": SPATIALANALYZE_URL,
            "sessionId": session_id,
            "formValues": formular_data,
            "timeoutMs": timeout_ms,
        },
    )

    fetch_resultat = _valider_fetch_resultat(
        browser_resultat
    )

    status = fetch_resultat["status"]

    browser_error = str(
        fetch_resultat.get("browserError")
        or ""
    ).strip()

    if browser_error:
        raise RuntimeError(
            "WebGIS spatialanalyze kunne ikke udføres "
            "i browseren. "
            f"Browserfejl: {browser_error}"
        )

    if not fetch_resultat["ok"]:
        response_preview = _lav_sikkert_response_preview(
            fetch_resultat.get("responseText")
        )

        raise RuntimeError(
            "WebGIS spatialanalyze fejlede med "
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
            "WebGIS spatialanalyze returnerede "
            "et tomt svar."
        )

    resultat = await _parse_json_i_browser(
        page=page,
        response_text=response_text,
    )

    if not isinstance(resultat, dict):
        raise RuntimeError(
            "WebGIS spatialanalyze returnerede JSON, "
            "men resultatet var ikke en dictionary. "
            f"Modtog: {type(resultat).__name__}."
        )

    logger.info(
        "WebGIS spatialanalyze blev gennemført med "
        "HTTP-status %s.",
        status,
    )

    return resultat


# ------------------------------------------------------------
# JSON
# ------------------------------------------------------------


async def _parse_json_i_browser(
    page: Page,
    response_text: str,
) -> Any:
    """Parser WebGIS-svaret som JSON.

    Output:
        Den parsede JSON-værdi.
    """
    parse_resultat = await page.evaluate(
        """
        (responseText) => {
            try {
                return {
                    parsed: true,
                    value: JSON.parse(responseText)
                };
            } catch (error) {
                return {
                    parsed: false,
                    error: (
                        error instanceof Error
                            ? error.message
                            : String(error)
                    )
                };
            }
        }
        """,
        response_text,
    )

    if not isinstance(parse_resultat, dict):
        raise RuntimeError(
            "WebGIS-svaret kunne ikke kontrolleres "
            "som JSON."
        )

    if not parse_resultat.get("parsed"):
        response_preview = (
            _lav_sikkert_response_preview(
                response_text
            )
        )

        raise RuntimeError(
            "WebGIS spatialanalyze returnerede ikke "
            "gyldig JSON. "
            f"JSON-fejl: "
            f"{parse_resultat.get('error')!s}. "
            f"Svareksempel: {response_preview}"
        )

    return parse_resultat.get("value")


# ------------------------------------------------------------
# Validering af fetch-resultat
# ------------------------------------------------------------


def _valider_fetch_resultat(
    value: Any,
) -> dict[str, Any]:
    """Validerer resultatet fra browserens fetch-kald."""
    if not isinstance(value, dict):
        raise RuntimeError(
            "WebGIS spatialanalyze returnerede et "
            "ugyldigt browserresultat."
        )

    status = value.get("status")

    if isinstance(status, bool):
        raise RuntimeError(
            "WebGIS spatialanalyze returnerede en "
            "ugyldig HTTP-status."
        )

    if not isinstance(status, int):
        raise RuntimeError(
            "WebGIS spatialanalyze returnerede ikke "
            "en numerisk HTTP-status."
        )

    if not isinstance(value.get("ok"), bool):
        raise RuntimeError(
            "WebGIS spatialanalyze returnerede ikke "
            "en gyldig ok-status."
        )

    return value


# ------------------------------------------------------------
# Inputvalidering
# ------------------------------------------------------------


def _valider_page(
    page: Page,
) -> None:
    """Kontrollerer, at browsersiden kan bruges."""
    if page is None:
        raise ValueError(
            "page skal angives."
        )

    if page.is_closed():
        raise RuntimeError(
            "WebGIS-siden er lukket og kan ikke "
            "bruges til spatialanalyze."
        )


def _valider_tekst(
    *,
    value: Any,
    field_name: str,
) -> str:
    """Returnerer en obligatorisk, trimmet tekstværdi."""
    if not isinstance(value, str):
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
    if isinstance(value, bool):
        raise TypeError(
            f"{field_name} må ikke være boolsk."
        )

    try:
        integer_value = int(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"{field_name} skal være et heltal."
        ) from exc

    if integer_value <= 0:
        raise ValueError(
            f"{field_name} skal være større end 0."
        )

    return integer_value


def _valider_koordinat(
    *,
    value: Any,
    field_name: str,
) -> float:
    """Returnerer en koordinat som float."""
    if isinstance(value, bool):
        raise TypeError(
            f"{field_name} må ikke være boolsk."
        )

    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"{field_name} skal være et tal."
        ) from exc


def _valider_koordinater(
    *,
    min_x_wc: Any,
    min_y_wc: Any,
    max_x_wc: Any,
    max_y_wc: Any,
) -> dict[str, float]:
    """Validerer spatialanalysens koordinater."""
    koordinater = {
        "min_x_wc": _valider_koordinat(
            value=min_x_wc,
            field_name="min_x_wc",
        ),
        "min_y_wc": _valider_koordinat(
            value=min_y_wc,
            field_name="min_y_wc",
        ),
        "max_x_wc": _valider_koordinat(
            value=max_x_wc,
            field_name="max_x_wc",
        ),
        "max_y_wc": _valider_koordinat(
            value=max_y_wc,
            field_name="max_y_wc",
        ),
    }

    if (
        koordinater["min_x_wc"]
        >= koordinater["max_x_wc"]
    ):
        raise ValueError(
            "min_x_wc skal være mindre end max_x_wc."
        )

    if (
        koordinater["min_y_wc"]
        >= koordinater["max_y_wc"]
    ):
        raise ValueError(
            "min_y_wc skal være mindre end max_y_wc."
        )

    return koordinater


# ------------------------------------------------------------
# Fejlpreview
# ------------------------------------------------------------


def _lav_sikkert_response_preview(
    value: Any,
    maximum_length: int = 500,
) -> str:
    """Laver et begrænset preview af et fejlsvar.

    Previewet bruges kun til fejlsøgning. Session-Id og cookies
    ligger ikke i response-bodyen og bliver ikke tilføjet her.
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

# ------------------------------------------------------------
# START: hent_spatialanalyze_raekker
# ------------------------------------------------------------


SPATIALANALYZE_STORED_DATA_URL = (
    "https://webgis.intern.udcit.dk/"
    "spatialmap?page=spatialanalyze-get-stored-data"
)


async def hent_spatialanalyze_raekker(
    page: Page,
    session_id: str,
    *,
    maxrows: int,
    jsontypes: str,
    outputformat: str,
    error_content_type: str,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> list[dict[str, Any]]:
    """Henter rækkerne fra den seneste spatialanalyse.

    Funktionen skal kaldes umiddelbart efter spatialanalyze(),
    mens den samme WebGIS-side og Session-Id stadig er aktive.

    Output:
        Liste med de konkrete WebGIS-rækker som dictionaries.

    Sikkerhed:
        Session-Id og formularværdier bliver ikke skrevet i loggen.
    """
    _valider_page(page)

    session_id = _valider_tekst(
        value=session_id,
        field_name="session_id",
    )

    jsontypes = _valider_tekst(
        value=jsontypes,
        field_name="jsontypes",
    )

    outputformat = _valider_tekst(
        value=outputformat,
        field_name="outputformat",
    )

    error_content_type = _valider_tekst(
        value=error_content_type,
        field_name="error_content_type",
    )

    maxrows = _valider_positivt_heltal(
        value=maxrows,
        field_name="maxrows",
    )

    timeout_ms = _valider_positivt_heltal(
        value=timeout_ms,
        field_name="timeout_ms",
    )

    formular_data = {
        "page": "spatialanalyze-get-stored-data",
        "maxrows": str(maxrows),
        "outputformat": outputformat,
        "jsontypes": jsontypes,
        "jdaf.error.contenttype": error_content_type,
    }

    logger.info(
        "Henter op til %s rækker fra den seneste "
        "WebGIS-spatialanalyse.",
        maxrows,
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
                            "X-Requested-With": "XMLHttpRequest"
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
                    responseText: responseText
                };
            } catch (error) {
                return {
                    ok: false,
                    status: 0,
                    statusText: "",
                    contentType: "",
                    responseText: "",
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
            "url": SPATIALANALYZE_STORED_DATA_URL,
            "sessionId": session_id,
            "formValues": formular_data,
            "timeoutMs": timeout_ms,
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
            "WebGIS-rækkerne kunne ikke hentes "
            "i browseren. "
            f"Browserfejl: {browser_error}"
        )

    status = fetch_resultat["status"]

    if not fetch_resultat["ok"]:
        response_preview = (
            _lav_sikkert_response_preview(
                fetch_resultat.get(
                    "responseText"
                )
            )
        )

        raise RuntimeError(
            "Hentning af WebGIS-rækker fejlede med "
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
            "hentning af spatialanalyse-rækker."
        )

    resultat = await _parse_json_i_browser(
        page=page,
        response_text=response_text,
    )

    raekker = _find_datarækker(
        resultat
    )

    logger.info(
        "WebGIS returnerede %s læsbare datarækker.",
        len(raekker),
    )

    return raekker


def _find_datarækker(
    value: Any,
) -> list[dict[str, Any]]:
    """Finder den mest sandsynlige liste med datarækker.

    WebGIS kan pakke rækkerne ind i forskellige JSON-strukturer.
    Funktionen gennemgår derfor dictionaries og lister rekursivt.

    Output:
        Den største liste med dictionaries, som ligner datarækker.
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
                and not _er_metadata_raekke(element)
            ]

            if dictionary_rows:
                kandidater.append(
                    dictionary_rows
                )

            for element in current_value:
                besoeg(element)

            return

        if isinstance(
            current_value,
            dict,
        ):
            for nested_value in (
                current_value.values()
            ):
                besoeg(nested_value)

    besoeg(value)

    if not kandidater:
        if (
            isinstance(value, dict)
            and not _er_metadata_raekke(value)
        ):
            return [value]

        return []

    return max(
        kandidater,
        key=len,
    )


def _er_metadata_raekke(
    row: dict[str, Any],
) -> bool:
    """Kontrollerer om en række kun ligner WebGIS-metadata."""
    if not isinstance(row, dict):
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

    return bool(keys) and keys.issubset(
        metadata_keys
    )


# ------------------------------------------------------------
# SLUT: hent_spatialanalyze_raekker
# ------------------------------------------------------------


__all__ = [
    "SPATIALANALYZE_URL",
    "SPATIALANALYZE_STORED_DATA_URL",
    "hent_spatialanalyze_raekker",
    "spatialanalyze",
]