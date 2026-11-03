from __future__ import annotations

import copy
import json
import logging
from typing import Any

from playwright.async_api import Page

from q_webgis.configuration import (
    WEBGIS_BAADPLADS_UPDATE_URL,
    WEBGIS_TIMEOUT_MS,
)

logger = logging.getLogger(__name__)

DRIFTSTATUS_FRI = "1"
DRIFTSTATUS_UDLEJET = "3"

KENDTE_DRIFTSTATUS_LABELS = {
    DRIFTSTATUS_FRI: "Fri",
    DRIFTSTATUS_UDLEJET: "Udlejet",
}


async def aendr_baadplads_status(
    page: Page,
    ticket: str,
    baadplads: dict[str, Any],
    ny_driftstatus: int | str,
    *,
    timeout_ms: int = WEBGIS_TIMEOUT_MS,
) -> dict[str, Any]:
    """Ændrer driftstatus på én bådplads."""
    _valider_page(page)
    valideret_ticket = _valider_tekst(value=ticket, field_name="ticket")
    valideret_timeout = _valider_positivt_heltal(
        value=timeout_ms,
        field_name="timeout_ms",
    )
    valideret_status = _valider_driftstatus(ny_driftstatus)

    original_feature = _normaliser_baadplads_feature(baadplads)
    feature_til_opdatering = copy.deepcopy(original_feature)
    feature_til_opdatering["attributes"]["driftstatus"] = valideret_status

    oprindelige_attributter = original_feature["attributes"]
    attributter = feature_til_opdatering["attributes"]
    ogc_fid = attributter["ogc_fid"]
    tidligere_status = str(
        oprindelige_attributter.get("driftstatus", "")
    ).strip()
    status_label = KENDTE_DRIFTSTATUS_LABELS[valideret_status]

    identifikation = {
        "ogc_fid": ogc_fid,
        "havn": _hent_valgfri_attribut(attributter, "havn"),
        "straekning": _hent_valgfri_attribut(attributter, "straekning"),
        "plads": _hent_valgfri_attribut(attributter, "plads"),
    }

    if tidligere_status == valideret_status:
        logger.info(
            "Bådpladsen har allerede status %s. ogc_fid=%s, plads=%r.",
            status_label,
            ogc_fid,
            identifikation["plads"],
        )
        return {
            "success": True,
            "opdateret": False,
            "oversprunget": True,
            "aarsag": "Bådpladsen har allerede den ønskede status.",
            **identifikation,
            "tidligere_driftstatus": tidligere_status,
            "ny_driftstatus": valideret_status,
            "status_label": status_label,
            "http_status": None,
            "response_data": None,
        }

    logger.info(
        "Ændrer bådpladsstatus. ogc_fid=%s, havn=%r, plads=%r, fra=%r, til=%r (%s).",
        ogc_fid,
        identifikation["havn"],
        identifikation["plads"],
        tidligere_status,
        valideret_status,
        status_label,
    )

    request_payload = {"features": [feature_til_opdatering]}

    browser_resultat = await page.evaluate(
        """
        async ({url, ticket, requestPayload, timeoutMs}) => {
            const controller = new AbortController();
            const timeoutHandle = setTimeout(
                () => controller.abort(), timeoutMs
            );

            try {
                const response = await fetch(url, {
                    method: "PUT",
                    credentials: "include",
                    headers: {
                        "Accept": "application/json, text/javascript, */*; q=0.01",
                        "Content-Type": "application/json; charset=UTF-8",
                        "Ticket": ticket,
                        "X-Requested-With": "XMLHttpRequest"
                    },
                    body: JSON.stringify(requestPayload),
                    signal: controller.signal
                });

                return {
                    ok: response.ok,
                    status: response.status,
                    statusText: response.statusText,
                    contentType: response.headers.get("content-type") || "",
                    responseText: await response.text(),
                    finalUrl: response.url,
                    browserError: ""
                };
            } catch (error) {
                return {
                    ok: false,
                    status: 0,
                    statusText: "",
                    contentType: "",
                    responseText: "",
                    finalUrl: "",
                    browserError: error instanceof Error
                        ? error.name + ": " + error.message
                        : String(error)
                };
            } finally {
                clearTimeout(timeoutHandle);
            }
        }
        """,
        {
            "url": WEBGIS_BAADPLADS_UPDATE_URL,
            "ticket": valideret_ticket,
            "requestPayload": request_payload,
            "timeoutMs": valideret_timeout,
        },
    )

    resultat = _valider_fetch_resultat(browser_resultat)
    browser_error = str(resultat.get("browserError") or "").strip()
    if browser_error:
        raise RuntimeError(
            f"Browserfejl ved statusændring for ogc_fid={ogc_fid}: {browser_error}"
        )

    response_text = str(resultat.get("responseText") or "").strip()
    content_type = str(resultat.get("contentType") or "").strip()

    if not resultat["ok"]:
        raise RuntimeError(
            "WebGIS afviste statusændringen. "
            f"ogc_fid={ogc_fid}, HTTP={resultat['status']}, "
            f"statusbesked={resultat.get('statusText')!r}, "
            f"svar={_lav_sikkert_response_preview(response_text)}"
        )

    response_data = _parse_response(
        response_text=response_text,
        content_type=content_type,
    )

    return {
        "success": True,
        "opdateret": True,
        "oversprunget": False,
        "aarsag": None,
        **identifikation,
        "tidligere_driftstatus": tidligere_status,
        "ny_driftstatus": valideret_status,
        "status_label": status_label,
        "http_status": resultat["status"],
        "response_data": response_data,
    }


def _normaliser_baadplads_feature(
    baadplads: dict[str, Any],
) -> dict[str, Any]:
    """Omsætter en hentet bådpladsrække til SFS-featureformat."""
    if not isinstance(baadplads, dict):
        raise TypeError("baadplads skal være en dictionary.")

    eksisterende_attributter = baadplads.get("attributes")

    if isinstance(eksisterende_attributter, dict):
        feature = copy.deepcopy(baadplads)
        if not feature.get("wkt"):
            feature["wkt"] = feature.get("shape_wkt")
        if not feature.get("projection"):
            feature["projection"] = "EPSG:25832"
        if "hasattachments" not in feature:
            feature["hasattachments"] = False

        for metadatafelt in (
            "shape_wkt",
            "_name",
            "_class",
            "_pcolid",
        ):
            feature.pop(metadatafelt, None)
    else:
        wkt = baadplads.get("wkt") or baadplads.get("shape_wkt")
        envelope_fields = {
            "_name",
            "_class",
            "_pcolid",
            "shape_wkt",
            "wkt",
            "projection",
            "hasattachments",
        }
        attributter = {
            key: copy.deepcopy(value)
            for key, value in baadplads.items()
            if key not in envelope_fields
        }
        feature = {
            "wkt": wkt,
            "projection": baadplads.get("projection") or "EPSG:25832",
            "hasattachments": baadplads.get("hasattachments", False),
            "attributes": attributter,
        }

    _valider_baadplads_feature(feature)
    return feature


def _valider_baadplads_feature(feature: dict[str, Any]) -> None:
    wkt = feature.get("wkt")
    if not isinstance(wkt, str) or not wkt.strip():
        raise ValueError("Bådpladsen mangler wkt/shape_wkt.")

    projection = feature.get("projection")
    if not isinstance(projection, str) or not projection.strip():
        raise ValueError("Bådpladsen mangler projection.")

    if not isinstance(feature.get("hasattachments"), bool):
        raise TypeError("hasattachments skal være boolsk.")

    attributter = feature.get("attributes")
    if not isinstance(attributter, dict):
        raise TypeError("Bådpladsen mangler attributes.")
    if attributter.get("ogc_fid") is None:
        raise ValueError("Bådpladsen mangler ogc_fid.")
    if "driftstatus" not in attributter:
        raise ValueError("Bådpladsen mangler driftstatus.")


def _hent_valgfri_attribut(
    attributter: dict[str, Any],
    feltnavn: str,
) -> str | None:
    value = attributter.get(feltnavn)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _valider_driftstatus(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise TypeError("ny_driftstatus skal være et heltal eller tekst.")
    driftstatus = str(value).strip()
    if driftstatus not in KENDTE_DRIFTSTATUS_LABELS:
        raise ValueError(
            "Kun statuskode 1 (Fri) og 3 (Udlejet) er verificeret."
        )
    return driftstatus


def _valider_fetch_resultat(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError("Browserresultatet er ugyldigt.")
    status = value.get("status")
    if isinstance(status, bool) or not isinstance(status, int):
        raise RuntimeError("HTTP-status er ugyldig.")
    if not isinstance(value.get("ok"), bool):
        raise RuntimeError("ok-status er ugyldig.")
    return value


def _parse_response(*, response_text: str, content_type: str) -> Any:
    if not response_text:
        return None
    ligner_json = (
        "json" in content_type.casefold()
        or response_text.lstrip().startswith(("{", "["))
    )
    if not ligner_json:
        return response_text
    try:
        return json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"WebGIS returnerede ugyldigt JSON: {exc.msg}."
        ) from exc


def _valider_page(page: Page) -> None:
    if page is None:
        raise ValueError("page skal angives.")
    if page.is_closed():
        raise RuntimeError("WebGIS-siden er lukket.")


def _valider_tekst(*, value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} skal være tekst.")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} må ikke være tom.")
    return cleaned


def _valider_positivt_heltal(*, value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{field_name} må ikke være boolsk.")
    try:
        integer_value = int(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field_name} skal være et heltal.") from exc
    if integer_value <= 0:
        raise ValueError(f"{field_name} skal være større end 0.")
    return integer_value


def _lav_sikkert_response_preview(
    value: Any,
    maximum_length: int = 500,
) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return "<tomt svar>"
    if len(text) <= maximum_length:
        return text
    return text[:maximum_length] + "..."


__all__ = [
    "DRIFTSTATUS_FRI",
    "DRIFTSTATUS_UDLEJET",
    "aendr_baadplads_status",
]
