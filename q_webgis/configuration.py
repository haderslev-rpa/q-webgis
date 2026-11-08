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
# WebGIS API
# ------------------------------------------------------------

WEBGIS_STORED_DATA_URL = (
    "https://webgis.intern.udcit.dk/"
    "spatialmap?page=spatialanalyze-get-stored-data"
)

WEBGIS_STORED_DATA_PAGE = (
    "spatialanalyze-get-stored-data"
)


# ------------------------------------------------------------
# Bådpladsredigering
# ------------------------------------------------------------

WEBGIS_BAADPLADS_UPDATE_URL = (
    "https://webgis.intern.udcit.dk/"
    "sfs/rest/features/ds-baadplads/sps"
)


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
#
# 60.000 millisekunder svarer til 60 sekunder.
WEBGIS_TIMEOUT_MS = 60_000


# Samlet timeout for konfliktsøgning og rapportgenerering.
#
# Timeouten omfatter:
# - ventetid på rapportdialogen
# - WebGIS' generering af rapporten
# - registrering af download eller PDF-URL
# - efterfølgende polling af den samme PDF-URL
#
# 30 minutter giver plads til tunge konfliktrapporter uden at
# blokere robotten i flere timer.
WEBGIS_RAPPORT_TIMEOUT_MS = 30 * 60 * 1_000


# Maksimal timeout for ét HTTP-kald mod en kendt PDF-URL.
#
# Denne værdi anvendes, når WebGIS har oprettet en adresse som:
# /tmp/report123456789.pdf
#
# Ét request må højst vente 60 sekunder. Hvis svaret endnu ikke
# er en gyldig PDF, foretages et nyt forsøg efter poll-intervallet.
WEBGIS_PDF_REQUEST_TIMEOUT_MS = 60_000


# Ventetid mellem gentagne hentninger af den samme PDF-URL.
#
# Rapporten genbestilles ikke. Robotten forsøger blot at hente
# den allerede oprettede rapport igen.
#
# 5.000 millisekunder svarer til 5 sekunder.
WEBGIS_PDF_POLL_INTERVAL_MS = 5_000


# Fast pause mellem Playwright-selectorhandlinger.
#
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