from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import (
    Download,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from q_haderslev_vbo.playwright.browser_session import (
    BrowserSession,
)

from q_webgis.configuration import (
    WEBGIS_RAPPORT_FILNAVN,
    WEBGIS_RAPPORT_MAPPE,
    WEBGIS_RAPPORT_TIMEOUT_MS,
    WEBGIS_SELECTOR_ACTION_WAIT_MS,
    WEBGIS_STANDARD_TEMA,
    WEBGIS_TILLADTE_TEMAER,
    WEBGIS_TIMEOUT_MS,
)
from q_webgis.selectors import (
    GLOBALT_SOEGEFELT,
    HVAD_GAELDER_FOR_KNAP,
    HVAD_GAELDER_FOR_MENU,
    INDSAET_WKT_KNAP,
    TEMAER_RESULTAT,
    KONFLIKTSOEGNING_DROPDOWN,
    KONFLIKTSOEGNING_LOADING,
    KONFLIKTSOEGNING_STATUS,
    KONFLIKTSOEGNING_UDFOER_KNAP,
    RAPPORT_KNAP,
    RAPPORT_LOADING,
    VIS_RAPPORT_KNAP,
    WKT_OK_KNAP,
    WKT_TEKSTFELT,
)


logger = logging.getLogger(__name__)


# Downloadobjektet knyttes midlertidigt til rapportfanen.
# Det fjernes igen, så en senere rapport aldrig kan genbruge downloadet.
_RAPPORT_DOWNLOADS: dict[int, Download] = {}


#
#VIRKER KUN MED HEADLESS=TRUE
#

# ------------------------------------------------------------
# Offentlig hovedfunktion
# ------------------------------------------------------------

# ------------------------------------------------------------
# START: opret_webgis_rapport
# ------------------------------------------------------------

async def opret_webgis_rapport(
    page: Page,
    session: BrowserSession,
    wkt: str,
    *,
    tema: str = WEBGIS_STANDARD_TEMA,
    rapportmappe: str | Path = WEBGIS_RAPPORT_MAPPE,
    filnavn: str = WEBGIS_RAPPORT_FILNAVN,
    vaelg_jordstykker_byggesag: bool = True,
    timeout_ms: int = WEBGIS_TIMEOUT_MS,
    rapport_timeout_ms: int = WEBGIS_RAPPORT_TIMEOUT_MS,
) -> Path:
    """
    Udfører hele WebGIS-flowet og gemmer rapporten som PDF.

    BrowserSession modtages fra testen eller den kaldende proces.
    Funktionen opretter eller lukker ikke selve BrowserSession.

    Flow:
        1. Tager screenshot af WebGIS-startsiden.
        2. Vælger eventuelt temaet "Jordstykker - Byggesag".
        3. Åbner "Hvad gælder for" og indsætter WKT.
        4. Vælger og udfører konfliktsøgningen.
        5. Venter på status "Færdig".
        6. Åbner rapportdialogen.
        7. Klikker "Vis rapport".
        8. Gemmer PDF'en direkte fra browserens download-event.
        9. Tager screenshots efter hvert hovedtrin.

    Output:
        Path til den gemte PDF-fil.
    """

    _valider_page(
        page
    )

    if session is None:
        raise ValueError(
            "session skal angives."
        )

    valideret_wkt = _valider_wkt(
        wkt
    )

    valideret_tema = _valider_tema(
        tema
    )

    valideret_filnavn = _valider_pdf_filnavn(
        filnavn
    )

    destination = _opret_rapportsti(
        rapportmappe=rapportmappe,
        filnavn=valideret_filnavn,
    )

    rapport_side: Page | None = None

    try:
        logger.info(
            "Starter WebGIS-rapport for konfliktsøgning=%s.",
            valideret_tema,
        )

        await _tag_screenshot(
            session=session,
            page=page,
            navn="STEP_01_webgis_start",
        )

        if vaelg_jordstykker_byggesag:
            await vaelg_jordstykker_byggesag_i_webgis(
                page=page,
                timeout_ms=timeout_ms,
            )

            await _tag_screenshot(
                session=session,
                page=page,
                navn="STEP_02_jordstykker_byggesag_valgt",
            )

        await indsaet_wkt_i_webgis(
            page=page,
            wkt=valideret_wkt,
            timeout_ms=timeout_ms,
        )

        await _tag_screenshot(
            session=session,
            page=page,
            navn="STEP_03_wkt_indsaet",
        )

        await udfoer_konfliktsoegning(
            page=page,
            tema=valideret_tema,
            timeout_ms=rapport_timeout_ms,
        )

        await _tag_screenshot(
            session=session,
            page=page,
            navn="STEP_04_konfliktsoegning_faerdig",
        )

        rapport_side = await aabn_rapport(
            page=page,
            timeout_ms=rapport_timeout_ms,
        )

        await _tag_screenshot(
            session=session,
            page=rapport_side,
            navn="STEP_05_rapport_aabnet",
        )


        pdf_sti = await gem_rapport_pdf(
            webgis_side=page,
            rapport_side=rapport_side,
            destination=destination,
            timeout_ms=rapport_timeout_ms,
        )

        await _tag_screenshot(
            session=session,
            page=rapport_side,
            navn="STEP_06_pdf_rapport_gemt",
        )

        logger.info(
            "WebGIS-rapporten er gemt: %s",
            pdf_sti,
        )

        return pdf_sti

    except Exception:
        logger.exception(
            "WebGIS-rapportflowet fejlede."
        )

        screenshot_side = (
            rapport_side
            if (
                rapport_side is not None
                and not rapport_side.is_closed()
            )
            else page
        )

        await _tag_screenshot(
            session=session,
            page=screenshot_side,
            navn="FEJL_webgis_rapport",
        )

        raise

    finally:
        if rapport_side is not None:
            _RAPPORT_DOWNLOADS.pop(
                id(rapport_side),
                None,
            )

        if (
            rapport_side is not None
            and rapport_side != page
            and not rapport_side.is_closed()
        ):
            await rapport_side.close()

# ------------------------------------------------------------
# SLUT: opret_webgis_rapport
# ------------------------------------------------------------

# ------------------------------------------------------------
# Global temasøgning
# ------------------------------------------------------------

# ------------------------------------------------------------
# START: vaelg_jordstykker_byggesag_i_webgis
# ------------------------------------------------------------

async def vaelg_jordstykker_byggesag_i_webgis(
    page: Page,
    *,
    timeout_ms: int = WEBGIS_TIMEOUT_MS,
) -> None:
    """
    Søger efter temaet "Jordstykker - Byggesag".

    Efter søgeteksten er indsat, klikkes der igen i søgefeltet.
    Derefter klikkes der på søgeresultatgruppen "Temaer".

    Output:
        Funktionen returnerer ikke data.
        Temaresultatet bliver åbnet i WebGIS.
    """

    soegning = "Jordstykker - Byggesag"

    logger.info(
        "Søger efter temaet %s.",
        soegning,
    )

    soegefelt = page.locator(
        GLOBALT_SOEGEFELT
    ).first

    await _vent_paa_synlig(
        soegefelt,
        navn="globalt søgefelt",
        timeout_ms=timeout_ms,
    )

    await soegefelt.click()

    await _vent_mellem_selector_actions(
        page
    )

    await soegefelt.fill(
        soegning
    )

    await _vent_mellem_selector_actions(
        page
    )

    logger.info(
        "Søgeteksten er indsat. "
        "Klikker i søgefeltet igen."
    )

    await soegefelt.click()

    await _vent_mellem_selector_actions(
        page
    )

    tema_resultat = page.locator(
        TEMAER_RESULTAT
    ).first

    await _vent_paa_synlig(
        tema_resultat,
        navn='søgeresultatgruppen "Temaer"',
        timeout_ms=timeout_ms,
    )

    logger.info(
        'Søgeresultatgruppen "Temaer" er synlig. '
        "Klikker på resultatet."
    )

    await tema_resultat.click()

    await _vent_mellem_selector_actions(
        page
    )

    logger.info(
        'Søgeresultatgruppen "Temaer" er valgt '
        'efter søgning efter %s.',
        soegning,
    )

# ------------------------------------------------------------
# SLUT: vaelg_jordstykker_byggesag_i_webgis
# ------------------------------------------------------------

# ------------------------------------------------------------
# Arbejdsgeometri og WKT
# ------------------------------------------------------------

async def indsaet_wkt_i_webgis(
    page: Page,
    wkt: str,
    *,
    timeout_ms: int = WEBGIS_TIMEOUT_MS,
) -> None:
    """
    Åbner arbejdsgeometrien og indsætter WKT.

    Output:
        Funktionen returnerer ikke data. Geometrien indsættes i kortet.
    """

    valideret_wkt = _valider_wkt(wkt)

    logger.info(
        "Åbner WebGIS-arbejdsgeometrien."
    )

    arbejdsgeometri = page.locator(
        HVAD_GAELDER_FOR_MENU
    ).first

    await _vent_paa_synlig(
        arbejdsgeometri,
        navn="Hvad gælder for-menu",
        timeout_ms=timeout_ms,
    )

    # Klik på linket inde i li-elementet, hvis det findes.
    arbejdsgeometri_link = arbejdsgeometri.locator(
        'a[title="Hvad gælder for"]'
    )

    if await arbejdsgeometri_link.count() > 0:
        await arbejdsgeometri_link.click()

        await _vent_mellem_selector_actions(
            page
        )
    else:
        await arbejdsgeometri.click()

        await _vent_mellem_selector_actions(
            page
        )

    wkt_knap = page.locator(
        INDSAET_WKT_KNAP
    ).first

    await _vent_paa_synlig(
        wkt_knap,
        navn="Indsæt WKT i kortet",
        timeout_ms=timeout_ms,
    )

    await wkt_knap.click()

    await _vent_mellem_selector_actions(
        page
    )

    wkt_felt = page.locator(
        WKT_TEKSTFELT
    ).first

    await _vent_paa_synlig(
        wkt_felt,
        navn="WKT-tekstfelt",
        timeout_ms=timeout_ms,
    )

    await wkt_felt.fill(
        valideret_wkt
    )

    await _vent_mellem_selector_actions(
        page
    )

    if await wkt_felt.input_value() != valideret_wkt:
        raise RuntimeError(
            "WKT-tekstfeltet indeholder ikke den forventede WKT."
        )

    ok_knap = page.locator(
        WKT_OK_KNAP
    ).first

    await _vent_paa_aktiv(
        ok_knap,
        navn="OK-knappen til WKT",
        timeout_ms=timeout_ms,
    )

    await ok_knap.click()

    await _vent_mellem_selector_actions(
        page
    )

    hvad_gaelder_for = page.locator(
        HVAD_GAELDER_FOR_KNAP
    ).first

    await _vent_paa_aktiv(
        hvad_gaelder_for,
        navn="Hvad gælder for-knappen",
        timeout_ms=timeout_ms,
    )

    logger.info(
        "WKT er indsat i WebGIS."
    )


# ------------------------------------------------------------
# Konfliktsøgning
# ------------------------------------------------------------

async def udfoer_konfliktsoegning(
    page: Page,
    *,
    tema: str,
    timeout_ms: int = WEBGIS_RAPPORT_TIMEOUT_MS,
) -> None:
    """
    Vælger en konfliktsøgning og venter på WebGIS-status "Færdig".
    """

    valideret_tema = _valider_tema(tema)

    hvad_gaelder_for = page.locator(
        HVAD_GAELDER_FOR_KNAP
    ).first

    await _vent_paa_aktiv(
        hvad_gaelder_for,
        navn="Hvad gælder for-knappen",
        timeout_ms=timeout_ms,
    )

    logger.info(
        "Åbner konfliktsøgningen."
    )

    await hvad_gaelder_for.click()

    await _vent_mellem_selector_actions(
        page
    )

    dropdown = page.locator(
        KONFLIKTSOEGNING_DROPDOWN
    ).first

    await _vent_paa_synlig(
        dropdown,
        navn="dropdown til konfliktsøgning",
        timeout_ms=timeout_ms,
    )

    await dropdown.select_option(
        value=valideret_tema
    )

    await _vent_mellem_selector_actions(
        page
    )

    valgt_tema = await dropdown.input_value()

    if valgt_tema != valideret_tema:
        raise RuntimeError(
            "WebGIS valgte ikke den forventede "
            f"konfliktsøgning. Forventede {valideret_tema!r}, "
            f"men fik {valgt_tema!r}."
        )

    udfoer_knap = page.locator(
        KONFLIKTSOEGNING_UDFOER_KNAP
    ).first

    await _vent_paa_aktiv(
        udfoer_knap,
        navn="Udfør-knappen",
        timeout_ms=timeout_ms,
    )

    logger.info(
        "Starter konfliktsøgning=%s.",
        valideret_tema,
    )

    await udfoer_knap.click()

    await _vent_mellem_selector_actions(
        page
    )

    await _vent_paa_konfliktsoegning_faerdig(
        page=page,
        timeout_ms=timeout_ms,
    )

    logger.info(
        "Konfliktsøgningen er færdig."
    )


async def _vent_paa_konfliktsoegning_faerdig(
    page: Page,
    *,
    timeout_ms: int,
) -> None:
    """
    Venter på status "Færdig" og kontrollerer, at loading-logoet er væk.
    """

    status = page.locator(
        KONFLIKTSOEGNING_STATUS
    ).first

    try:
        await status.wait_for(
            state="visible",
            timeout=timeout_ms,
        )

        await status.filter(
            has_text=re.compile(
                r"^\s*Færdig\s*$",
                re.IGNORECASE,
            )
        ).wait_for(
            state="visible",
            timeout=timeout_ms,
        )
    except PlaywrightTimeoutError as exc:
        status_tekst = ""

        if await status.count() > 0:
            status_tekst = (
                await status.text_content()
                or ""
            ).strip()

        raise RuntimeError(
            "WebGIS-konfliktsøgningen blev ikke færdig. "
            f"Seneste synlige status: {status_tekst!r}."
        ) from exc

    loading = page.locator(
        KONFLIKTSOEGNING_LOADING
    ).first

    if await loading.count() > 0:
        try:
            await loading.wait_for(
                state="hidden",
                timeout=timeout_ms,
            )
        except PlaywrightTimeoutError as exc:
            raise RuntimeError(
                "WebGIS viste status 'Færdig', men "
                "loading-logoet forsvandt ikke."
            ) from exc


# ------------------------------------------------------------
# Rapport
# ------------------------------------------------------------

async def aabn_rapport(
    page: Page,
    *,
    timeout_ms: int = WEBGIS_RAPPORT_TIMEOUT_MS,
) -> Page:
    """
    Klikker Rapport og Vis rapport og venter på PDF-downloadet.

    WebGIS åbner en midlertidig popupfane og starter derefter en
    browser-download. I headless Chromium bliver popupfanen stående
    på about:blank. Derfor bruges Playwrights download-event i stedet
    for at vente på en PDF-URL i fanen.

    Output:
        Returnerer rapportfanen. Det tilhørende Download-objekt
        gemmes midlertidigt og anvendes af gem_rapport_pdf().
    """

    rapport_knap = page.locator(
        RAPPORT_KNAP
    ).filter(
        has_text=re.compile(
            r"^\s*Rapport\s*$",
            re.IGNORECASE,
        )
    ).first

    await _vent_paa_synlig(
        rapport_knap,
        navn="Rapport-knappen",
        timeout_ms=timeout_ms,
    )

    logger.info(
        "Åbner WebGIS-rapportdialogen."
    )

    await rapport_knap.click()

    await _vent_mellem_selector_actions(
        page
    )

    vis_rapport_knap = page.locator(
        VIS_RAPPORT_KNAP
    ).filter(
        has_text=re.compile(
            r"^\s*Vis rapport\s*$",
            re.IGNORECASE,
        )
    ).first

    await _vent_paa_aktiv(
        vis_rapport_knap,
        navn="Vis rapport-knappen",
        timeout_ms=timeout_ms,
    )

    loading = page.locator(
        RAPPORT_LOADING
    ).first

    event_loop = asyncio.get_running_loop()

    download_future: asyncio.Future[Download] = (
        event_loop.create_future()
    )

    rapport_side: Page | None = None

    def ved_download(
        download: Download,
    ) -> None:
        if not download_future.done():
            download_future.set_result(
                download
            )

    def ved_ny_side(
        ny_side: Page,
    ) -> None:
        ny_side.on(
            "download",
            ved_download,
        )

    page.on(
        "download",
        ved_download,
    )

    page.context.on(
        "page",
        ved_ny_side,
    )

    logger.info(
        "Bestiller rapporten og venter på download-event."
    )

    try:
        async with page.context.expect_page(
            timeout=timeout_ms,
        ) as ny_side_info:
            await vis_rapport_knap.click()

        rapport_side = await ny_side_info.value

        rapport_side.on(
            "download",
            ved_download,
        )

        download = await asyncio.wait_for(
            asyncio.shield(
                download_future
            ),
            timeout=timeout_ms / 1_000,
        )

        download_fejl = await download.failure()

        if download_fejl:
            raise RuntimeError(
                "WebGIS-downloadet fejlede: "
                f"{download_fejl}"
            )

        _RAPPORT_DOWNLOADS[
            id(rapport_side)
        ] = download

        logger.info(
            "Download-event modtaget. "
            "Foreslået filnavn: %s",
            download.suggested_filename,
        )

        if await loading.count() > 0:
            try:
                await loading.wait_for(
                    state="hidden",
                    timeout=timeout_ms,
                )
            except PlaywrightTimeoutError:
                logger.debug(
                    "Rapport-loading kunne ikke længere findes "
                    "på den oprindelige side."
                )

        return rapport_side

    except TimeoutError as exc:
        raise RuntimeError(
            "WebGIS åbnede rapportfanen, men startede ikke "
            "downloadet inden for timeouten."
        ) from exc

    finally:
        page.remove_listener(
            "download",
            ved_download,
        )

        page.context.remove_listener(
            "page",
            ved_ny_side,
        )

        if rapport_side is not None:
            rapport_side.remove_listener(
                "download",
                ved_download,
            )

# ------------------------------------------------------------
# START: gem_rapport_pdf
# ------------------------------------------------------------

async def gem_rapport_pdf(
    webgis_side: Page,
    rapport_side: Page,
    destination: str | Path,
    *,
    timeout_ms: int = WEBGIS_RAPPORT_TIMEOUT_MS,
) -> Path:
    """
    Gemmer PDF-rapporten direkte fra Playwrights download-event.

    Der foretages ikke et nyt HTTP-kald til downloadadressen.
    Det er nødvendigt, fordi WebGIS-downloadet bruger den browser-
    autorisation, som udløste downloadet. Et separat GET-kald kan
    derfor blive afvist af IIS med HTTP 401.5.

    Parametre:
        webgis_side:
            Den oprindelige WebGIS-side. Parameteren bevares for
            kompatibilitet med det eksisterende offentlige API.

        rapport_side:
            Popupfanen, som blev oprettet ved rapportbestillingen.

        destination:
            Stien, hvor PDF-filen skal gemmes.

        timeout_ms:
            Bevares for kompatibilitet med det eksisterende API.

    Output:
        Path til den gemte og validerede PDF-fil.
    """

    _valider_page(
        webgis_side
    )

    _valider_page(
        rapport_side
    )

    if isinstance(
        timeout_ms,
        bool,
    ) or not isinstance(
        timeout_ms,
        int,
    ):
        raise TypeError(
            "timeout_ms skal være et heltal."
        )

    if timeout_ms <= 0:
        raise ValueError(
            "timeout_ms skal være større end 0."
        )

    download = _RAPPORT_DOWNLOADS.pop(
        id(rapport_side),
        None,
    )

    if download is None:
        raise RuntimeError(
            "Der blev ikke registreret et download til "
            "den aktuelle WebGIS-rapportfane."
        )

    destination_path = Path(
        destination
    )

    destination_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination_path.unlink(
        missing_ok=True
    )

    logger.info(
        "Gemmer PDF direkte fra browserens download-event."
    )

    await download.save_as(
        str(destination_path)
    )

    if not destination_path.is_file():
        raise RuntimeError(
            "Den downloadede PDF-rapport blev ikke gemt."
        )

    gemt_filstoerrelse = (
        destination_path.stat().st_size
    )

    if gemt_filstoerrelse == 0:
        raise RuntimeError(
            "Den downloadede PDF-rapport er tom."
        )

    with destination_path.open(
        "rb"
    ) as pdf_fil:
        pdf_signatur = pdf_fil.read(
            5
        )

    if pdf_signatur != b"%PDF-":
        destination_path.unlink(
            missing_ok=True
        )

        raise RuntimeError(
            "Den downloadede fil mangler en gyldig "
            "PDF-signatur."
        )

    logger.info(
        "PDF gemt direkte fra download-event: %s bytes.",
        gemt_filstoerrelse,
    )

    return destination_path

# ------------------------------------------------------------
# SLUT: gem_rapport_pdf
# ------------------------------------------------------------

async def _vent_paa_pdf_url(
    rapport_side: Page,
    *,
    timeout_ms: int,
) -> None:
    """
    Venter på en URL, som ender på .pdf.
    """

    try:
        await rapport_side.wait_for_url(
            re.compile(
                r"\.pdf(?:$|[?#])",
                re.IGNORECASE,
            ),
            timeout=timeout_ms,
        )
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            "Rapportfanen blev åbnet, men navigerede ikke "
            "til en PDF-adresse. "
            f"Aktuel URL: {_sikker_url(rapport_side.url)}"
        ) from exc


# ------------------------------------------------------------
# Playwright-hjælpere
# ------------------------------------------------------------

# ------------------------------------------------------------
# START: _tag_screenshot
# ------------------------------------------------------------

async def _tag_screenshot(
    session: BrowserSession,
    page: Page,
    navn: str,
    *,
    always: bool = True,
) -> None:
    """
    Gemmer et screenshot gennem den fælles BrowserSession.

    Screenshotfejl logges, men skjuler ikke en oprindelig fejl
    fra WebGIS-flowet.

    Output:
        Funktionen returnerer ikke data.
    """

    if session is None:
        raise ValueError(
            "session skal angives."
        )

    if page is None or page.is_closed():
        logger.warning(
            "Screenshot %r blev sprunget over, "
            "fordi siden er lukket.",
            navn,
        )
        return

    try:
        await session.screenshot(
            page,
            navn,
            always=always,
        )
    except Exception:
        logger.exception(
            "Screenshot %r kunne ikke gemmes.",
            navn,
        )

# ------------------------------------------------------------
# SLUT: _tag_screenshot
# ------------------------------------------------------------

# ------------------------------------------------------------
# START: _vent_mellem_selector_actions
# ------------------------------------------------------------

async def _vent_mellem_selector_actions(
    page: Page,
    *,
    ventetid_ms: int = WEBGIS_SELECTOR_ACTION_WAIT_MS,
) -> None:
    """
    Indsætter en fast pause mellem Playwright-selectorhandlinger.

    Funktionen bruges efter click(), fill(), press() og
    select_option(), så WebGIS får tid til at opdatere
    brugerfladen.

    Output:
        Funktionen returnerer ikke data.
    """

    _valider_page(
        page
    )

    if isinstance(
        ventetid_ms,
        bool,
    ) or not isinstance(
        ventetid_ms,
        int,
    ):
        raise TypeError(
            "ventetid_ms skal være et heltal."
        )

    if ventetid_ms < 0:
        raise ValueError(
            "ventetid_ms må ikke være negativ."
        )

    if ventetid_ms == 0:
        return

    await page.wait_for_timeout(
        ventetid_ms
    )

# ------------------------------------------------------------
# SLUT: _vent_mellem_selector_actions
# ------------------------------------------------------------

async def _vent_paa_synlig(
    locator: Locator,
    *,
    navn: str,
    timeout_ms: int,
) -> None:
    """
    Venter på, at et element bliver synligt.
    """

    try:
        await locator.wait_for(
            state="visible",
            timeout=timeout_ms,
        )
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            f"WebGIS-elementet {navn!r} blev ikke synligt."
        ) from exc


async def _vent_paa_aktiv(
    locator: Locator,
    *,
    navn: str,
    timeout_ms: int,
) -> None:
    """
    Venter på, at et element er synligt og aktiveret.
    """

    await _vent_paa_synlig(
        locator,
        navn=navn,
        timeout_ms=timeout_ms,
    )

    try:
        await locator.wait_for(
            state="attached",
            timeout=timeout_ms,
        )

        await locator.evaluate(
            """
            (element, timeoutMs) => new Promise(
                (resolve, reject) => {
                    const startedAt = Date.now();

                    const check = () => {
                        const disabled = (
                            element.disabled === true
                            || element.getAttribute(
                                "aria-disabled"
                            ) === "true"
                        );

                        if (!disabled) {
                            resolve(true);
                            return;
                        }

                        if (
                            Date.now() - startedAt
                            >= timeoutMs
                        ) {
                            reject(
                                new Error(
                                    "Elementet forblev disabled."
                                )
                            );
                            return;
                        }

                        setTimeout(check, 100);
                    };

                    check();
                }
            )
            """,
            timeout_ms,
        )
    except Exception as exc:
        raise RuntimeError(
            f"WebGIS-elementet {navn!r} blev ikke aktivt."
        ) from exc


# ------------------------------------------------------------
# Validering
# ------------------------------------------------------------

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
            "WebGIS-siden er lukket."
        )


def _valider_wkt(
    wkt: str,
) -> str:
    """
    Kontrollerer en grundlæggende WKT-værdi.

    Output:
        Trimmet WKT.
    """

    if not isinstance(wkt, str):
        raise TypeError(
            "wkt skal være tekst."
        )

    valideret_wkt = wkt.strip()

    if not valideret_wkt:
        raise ValueError(
            "wkt må ikke være tom."
        )

    tilladte_geometrityper = (
        "POINT",
        "LINESTRING",
        "POLYGON",
        "MULTIPOINT",
        "MULTILINESTRING",
        "MULTIPOLYGON",
        "GEOMETRYCOLLECTION",
    )

    wkt_upper = valideret_wkt.upper()

    if not wkt_upper.startswith(
        tilladte_geometrityper
    ):
        raise ValueError(
            "wkt starter ikke med en understøttet "
            "WKT-geometritype."
        )

    if (
        valideret_wkt.count("(")
        != valideret_wkt.count(")")
    ):
        raise ValueError(
            "wkt har ikke samme antal åbne og lukkede parenteser."
        )

    return valideret_wkt


def _valider_tema(
    tema: str,
) -> str:
    """
    Kontrollerer dropdown-værdien.

    Output:
        Trimmet temaværdi.
    """

    if not isinstance(tema, str):
        raise TypeError(
            "tema skal være tekst."
        )

    valideret_tema = tema.strip()

    if valideret_tema not in WEBGIS_TILLADTE_TEMAER:
        raise ValueError(
            f"Ukendt WebGIS-tema: {tema!r}. "
            f"Tilladte værdier: {WEBGIS_TILLADTE_TEMAER}."
        )

    return valideret_tema


def _valider_pdf_filnavn(
    filnavn: str,
) -> str:
    """
    Kontrollerer rapportens filnavn.

    Output:
        Et sikkert filnavn, som ender på .pdf.
    """

    if not isinstance(filnavn, str):
        raise TypeError(
            "filnavn skal være tekst."
        )

    valideret_filnavn = filnavn.strip()

    if not valideret_filnavn:
        raise ValueError(
            "filnavn må ikke være tomt."
        )

    if Path(valideret_filnavn).name != valideret_filnavn:
        raise ValueError(
            "filnavn må ikke indeholde en mappesti."
        )

    if not valideret_filnavn.casefold().endswith(
        ".pdf"
    ):
        valideret_filnavn += ".pdf"

    return valideret_filnavn


def _opret_rapportsti(
    *,
    rapportmappe: str | Path,
    filnavn: str,
) -> Path:
    """
    Opretter rapportmappen.

    Output:
        Den komplette sti til PDF-filen.
    """

    rapportmappe_path = Path(
        rapportmappe
    )

    rapportmappe_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    return (
        rapportmappe_path
        / filnavn
    )


def _sikker_url(
    url: str,
) -> str:
    """
    Returnerer URL uden query-parametre eller credentials.
    """

    parsed_url = urlparse(
        str(url or "")
    )

    return parsed_url._replace(
        query="",
        fragment="",
        params="",
    ).geturl()


__all__ = [
    "aabn_rapport",
    "gem_rapport_pdf",
    "indsaet_wkt_i_webgis",
    "opret_webgis_rapport",
    "udfoer_konfliktsoegning",
    "vaelg_jordstykker_byggesag_i_webgis",
]
