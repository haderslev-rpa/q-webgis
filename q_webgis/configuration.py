from pathlib import Path


# ------------------------------------------------------------
# WebGIS
# ------------------------------------------------------------

WEBGIS_URL = (
    "https://webgis.intern.udcit.dk/"
    "spatialmap?profile=maxi"
)

WEBGIS_CREDENTIAL_NAME = "DIRXOAS"

WEBGIS_PROFILE = "maxi"


# ------------------------------------------------------------
# Spatialanalyse
# ------------------------------------------------------------

BYGGESAG_DATASOURCE = (
    "ds-byggesag_cases_matrikel"
)

WEBGIS_MAXROWS = 20_000


# ------------------------------------------------------------
# Playwright
# ------------------------------------------------------------

# Standard-timeout for almindelige WebGIS-handlinger.
WEBGIS_TIMEOUT_MS = 60_000

# Udvidet timeout til konfliktsøgning og rapportgenerering.
WEBGIS_RAPPORT_TIMEOUT_MS = 180_000

# Fast pause mellem Playwright-selectorhandlinger.
# 1.000 millisekunder svarer til ét sekund.
WEBGIS_SELECTOR_ACTION_WAIT_MS = 1_000


# ------------------------------------------------------------
# Konfliktsøgning
# ------------------------------------------------------------

WEBGIS_STANDARD_TEMA = "byggesag"

WEBGIS_TILLADTE_TEMAER = (
    "vissible_themes",
    "byggesag",
    "jordvarme",
    "landskab_naturp3",
    "landzonesager",
    "slam",
    "sten_og_jorddiger",
    "vandloeb",
    "vvm",
    "samlet",
    "groen_trepart_ovrig_interesse",
    "groen_trepart_synergi",
)


# ------------------------------------------------------------
# Rapport
# ------------------------------------------------------------

WEBGIS_RAPPORT_MAPPE = Path(
    "runtime_output"
)

WEBGIS_RAPPORT_FILNAVN = (
    "webgis_rapport.pdf"
)