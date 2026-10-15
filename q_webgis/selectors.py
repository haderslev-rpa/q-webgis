"""
Stabile Playwright-selectors til WebGIS.

Selectors med entydige id'er prioriteres over CSS-klasser,
attributter og tekst.
"""


# ------------------------------------------------------------
# Global temasøgning
# ------------------------------------------------------------

GLOBALT_SOEGEFELT = (
    'input.ssInput[placeholder="Søg"]'
)

# Bevares af hensyn til eksisterende kode, som eventuelt stadig
# finder selve søgeresultatet "Jordstykker - Byggesag".
JORDSTYKKER_BYGGESAG_RESULTAT = (
    'div.ssResultTitle[title="Jordstykker - Byggesag"]'
)

# Resultatgruppen, der vises under den globale søgning.
# Antallet i aria-label kan ændre sig, derfor bruges ^= i stedet
# for at være bundet til eksempelvis "Temaer (*)".
TEMAER_RESULTAT = (
    'li.result.highlight '
    'div.ssResult[role="button"]'
    '[aria-label^="Temaer ("]'
)


# ------------------------------------------------------------
# Arbejdsgeometri
# ------------------------------------------------------------

HVAD_GAELDER_FOR_MENU = (
    "#workinglayer"
)

INDSAET_WKT_KNAP = (
    "#userdatasourceDrawToolBox_drawFeatureWKT"
)

WKT_TEKSTFELT = (
    "#userdatasourceDrawToolBox_textarea"
)

WKT_OK_KNAP = (
    "#userdatasourceDrawToolBox_ok"
)

HVAD_GAELDER_FOR_KNAP = (
    "#dynamiclayer_userdatasource_handlers_1"
)


# ------------------------------------------------------------
# Konfliktsøgning
# ------------------------------------------------------------

KONFLIKTSOEGNING_DROPDOWN = (
    "select.spatialqueryoption_target"
)

KONFLIKTSOEGNING_UDFOER_KNAP = (
    "#searchlast_search"
)

KONFLIKTSOEGNING_LOADING = (
    "#infobox_progressbar"
)

KONFLIKTSOEGNING_STATUS = (
    "#infobox_statusbar_text"
)


# ------------------------------------------------------------
# Rapport
# ------------------------------------------------------------

RAPPORT_KNAP = (
    "div.infoboxcontent_reportfunction"
)

VIS_RAPPORT_KNAP = (
    'button[onclick="infobox.reportOK();"]'
)

RAPPORT_LOADING = (
    ".sps-loading-container"
)

RAPPORT_LOADING_TEKST = (
    ".sps-loading-container >> text=Arbejder"
)