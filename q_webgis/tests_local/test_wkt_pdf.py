from __future__ import annotations

from io import BytesIO
import logging
import os
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
import requests
from PIL import Image
from PIL import ImageDraw


logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# Testdata
# ------------------------------------------------------------

WKT = """
POLYGON ((524591.45 6113854.699,
524588.22 6113838.982,
524558.971 6113844.437,
524558.544 6113836.443,
524557.653 6113819.77,
524556.57 6113816.689,
524560.29 6113815.464,
524575.06 6113810.597,
524585.919 6113804.171,
524659.366 6113785.442,
524664.069 6113783.751,
524647.589 6113869.29,
524643.366 6113868.592,
524629.546 6113865.559,
524619.458 6113863.345,
524615.062 6113862.379,
524612.841 6113862.269,
524608.514 6113861.773,
524592.124 6113857.977,
524591.45 6113854.699))
"""


# ------------------------------------------------------------
# Konfiguration
# ------------------------------------------------------------

DATAFORSYNING_TOKEN_ENV_NAME = (
    "DATAFORSYNING_TOKEN"
)

DATAFORSYNING_WMS_URL = (
    "https://api.dataforsyningen.dk/"
    "wms/forvaltning2"
)

OUTPUT_MAPPE = Path(
    "tests_local_output"
)

WIDTH = 1099
HEIGHT = 897
REQUEST_TIMEOUT_SECONDS = 60
BBOX_BUFFER_METER = 25.0
POLYGON_LINE_WIDTH = 5
PDF_RESOLUTION = 300


# ------------------------------------------------------------
# Konfiguration og validering
# ------------------------------------------------------------

def hent_dataforsyning_token() -> str:
    """
    Henter Dataforsyning-tokenet fra miljøvariablerne.

    Output:
        Et ikke-tomt token.
    """

    token = os.getenv(
        DATAFORSYNING_TOKEN_ENV_NAME,
        "",
    ).strip()

    if not token:
        raise RuntimeError(
            f"{DATAFORSYNING_TOKEN_ENV_NAME} mangler i .env."
        )

    return token


def valider_billedstoerrelse(
    width: int,
    height: int,
) -> None:
    """Kontrollerer, at billedets bredde og højde er positive heltal."""

    for navn, vaerdi in (
        ("width", width),
        ("height", height),
    ):
        if isinstance(vaerdi, bool) or not isinstance(
            vaerdi,
            int,
        ):
            raise TypeError(
                f"{navn} skal være et heltal."
            )

        if vaerdi <= 0:
            raise ValueError(
                f"{navn} skal være større end 0."
            )


# ------------------------------------------------------------
# WKT
# ------------------------------------------------------------

def parse_wkt_polygon(
    wkt: str,
) -> list[tuple[float, float]]:
    """
    Parser en enkel WKT POLYGON-værdi.

    Output:
        Liste med polygonpunkter som (x, y).
    """

    if not isinstance(wkt, str):
        raise TypeError(
            "wkt skal være tekst."
        )

    text = wkt.strip()

    if not text:
        raise ValueError(
            "wkt må ikke være tom."
        )

    start = "POLYGON (("
    slut = "))"

    if not text.upper().startswith(start):
        raise ValueError(
            "Kun en enkel WKT POLYGON understøttes."
        )

    if not text.endswith(slut):
        raise ValueError(
            "WKT-polygonen mangler afsluttende parenteser."
        )

    koordinattekst = text[
        len(start):-len(slut)
    ]

    points: list[tuple[float, float]] = []

    for indeks, pair in enumerate(
        koordinattekst.split(","),
        start=1,
    ):
        dele = pair.strip().split()

        if len(dele) != 2:
            raise ValueError(
                "WKT-koordinatparret på position "
                f"{indeks} indeholder ikke præcis x og y."
            )

        try:
            x = float(dele[0])
            y = float(dele[1])
        except ValueError as exc:
            raise ValueError(
                "WKT-koordinatparret på position "
                f"{indeks} indeholder ugyldige tal."
            ) from exc

        points.append(
            (
                x,
                y,
            )
        )

    if len(points) < 4:
        raise ValueError(
            "En polygon skal indeholde mindst fire punkter."
        )

    if points[0] != points[-1]:
        raise ValueError(
            "WKT-polygonens første og sidste punkt skal være ens."
        )

    return points


def calculate_bbox(
    points: list[tuple[float, float]],
    buffer_meter: float = 50.0,
) -> tuple[float, float, float, float]:
    """
    Beregner polygonens bounding box med buffer.

    Output:
        xmin, ymin, xmax, ymax.
    """

    if not points:
        raise ValueError(
            "points må ikke være tom."
        )

    if isinstance(buffer_meter, bool):
        raise TypeError(
            "buffer_meter skal være et tal."
        )

    try:
        buffer_vaerdi = float(
            buffer_meter
        )
    except (TypeError, ValueError) as exc:
        raise TypeError(
            "buffer_meter skal være et tal."
        ) from exc

    if buffer_vaerdi < 0:
        raise ValueError(
            "buffer_meter må ikke være negativ."
        )

    xs = [x for x, _ in points]
    ys = [y for _, y in points]

    xmin = min(xs) - buffer_vaerdi
    ymin = min(ys) - buffer_vaerdi
    xmax = max(xs) + buffer_vaerdi
    ymax = max(ys) + buffer_vaerdi

    if xmin >= xmax or ymin >= ymax:
        raise ValueError(
            "Den beregnede bounding box er ugyldig."
        )

    return (
        xmin,
        ymin,
        xmax,
        ymax,
    )


def world_to_pixel(
    x: float,
    y: float,
    bbox: tuple[float, float, float, float],
    width: int,
    height: int,
) -> tuple[int, int]:
    """
    Konverterer en koordinat til en pixelposition.

    Output:
        Pixelpositionen som (x, y).
    """

    valider_billedstoerrelse(
        width,
        height,
    )

    xmin, ymin, xmax, ymax = bbox

    if xmin >= xmax or ymin >= ymax:
        raise ValueError(
            "bbox er ugyldig."
        )

    px = (
        (x - xmin)
        / (xmax - xmin)
        * width
    )

    py = height - (
        (y - ymin)
        / (ymax - ymin)
        * height
    )

    return (
        round(px),
        round(py),
    )


# ------------------------------------------------------------
# Dataforsyningen
# ------------------------------------------------------------

def hent_kort(
    bbox: tuple[float, float, float, float],
    *,
    token: str,
    width: int = WIDTH,
    height: int = HEIGHT,
    timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
) -> Image.Image:
    """
    Henter et baggrundskort fra Dataforsyningens WMS.

    Output:
        Et færdigindlæst Pillow-billede i RGBA-format.
    """

    if not isinstance(token, str) or not token.strip():
        raise ValueError(
            "token skal være en ikke-tom tekst."
        )

    valider_billedstoerrelse(
        width,
        height,
    )

    if isinstance(timeout_seconds, bool) or not isinstance(
        timeout_seconds,
        int,
    ):
        raise TypeError(
            "timeout_seconds skal være et heltal."
        )

    if timeout_seconds <= 0:
        raise ValueError(
            "timeout_seconds skal være større end 0."
        )

    xmin, ymin, xmax, ymax = bbox

    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "FORMAT": "image/png",
        "TRANSPARENT": "TRUE",
        "LAYERS": "Basis_kort",
        "token": token.strip(),
        "servicename": "forvaltning2",
        "SRS": "EPSG:25832",
        "STYLES": "",
        "WIDTH": width,
        "HEIGHT": height,
        "BBOX": f"{xmin},{ymin},{xmax},{ymax}",
    }

    response = requests.get(
        DATAFORSYNING_WMS_URL,
        params=params,
        timeout=timeout_seconds,
    )

    response.raise_for_status()

    content_type = str(
        response.headers.get(
            "content-type",
            "",
        )
    ).casefold()

    if "image/" not in content_type:
        raise RuntimeError(
            "Dataforsyningen returnerede ikke et billede. "
            f"Content-Type var {content_type!r}."
        )

    try:
        with Image.open(
            BytesIO(response.content)
        ) as source_image:
            source_image.load()

            return source_image.convert(
                "RGBA"
            ).copy()

    except Exception as exc:
        raise RuntimeError(
            "Kortsvaret kunne ikke åbnes som et billede."
        ) from exc


# ------------------------------------------------------------
# Output
# ------------------------------------------------------------

def opret_unikke_outputstier(
    output_mappe: str | Path,
) -> tuple[Path, Path]:
    """
    Opretter unikke filstier til PNG og PDF.

    Output:
        Tuple med PNG-sti og PDF-sti.
    """

    mappe = Path(
        output_mappe
    )

    mappe.mkdir(
        parents=True,
        exist_ok=True,
    )

    unik_reference = uuid4().hex
    grundnavn = f"kort_med_polygon_{unik_reference}"

    return (
        mappe / f"{grundnavn}.png",
        mappe / f"{grundnavn}.pdf",
    )


def gem_kortfiler(
    image: Image.Image,
    points: list[tuple[float, float]],
    bbox: tuple[float, float, float, float],
    *,
    output_mappe: str | Path = OUTPUT_MAPPE,
) -> tuple[Path, Path]:
    """
    Tegner polygonen og gemmer unikke PNG- og PDF-filer.

    Output:
        Tuple med den gemte PNG-sti og PDF-sti.
    """

    if image is None:
        raise ValueError(
            "image skal angives."
        )

    pixel_points = [
        world_to_pixel(
            x=x,
            y=y,
            bbox=bbox,
            width=image.width,
            height=image.height,
        )
        for x, y in points
    ]

    output_image = image.copy()

    draw = ImageDraw.Draw(
        output_image
    )

    draw.line(
        pixel_points,
        fill="red",
        width=POLYGON_LINE_WIDTH,
        joint="curve",
    )

    png_sti, pdf_sti = opret_unikke_outputstier(
        output_mappe
    )

    output_image.save(
        png_sti,
        format="PNG",
    )

    output_image.convert(
        "RGB"
    ).save(
        pdf_sti,
        format="PDF",
        resolution=PDF_RESOLUTION,
    )

    if not png_sti.exists() or png_sti.stat().st_size == 0:
        raise RuntimeError(
            "PNG-filen blev ikke gemt korrekt."
        )

    if not pdf_sti.exists() or pdf_sti.stat().st_size == 0:
        raise RuntimeError(
            "PDF-filen blev ikke gemt korrekt."
        )

    if not pdf_sti.read_bytes().startswith(
        b"%PDF-"
    ):
        raise RuntimeError(
            "Den gemte PDF mangler en gyldig PDF-signatur."
        )

    return (
        png_sti,
        pdf_sti,
    )


# ------------------------------------------------------------
# Lokal test
# ------------------------------------------------------------

def main() -> None:
    """
    Henter et kort, tegner WKT-polygonen og gemmer unikke filer.

    Output:
        Gemmer én PNG og én PDF og udskriver deres absolutte stier.
    """

    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s [%(levelname)s] "
            "%(name)s: %(message)s"
        ),
        force=True,
    )

    token = hent_dataforsyning_token()

    points = parse_wkt_polygon(
        WKT
    )

    bbox = calculate_bbox(
        points,
        buffer_meter=BBOX_BUFFER_METER,
    )

    logger.info(
        "BBOX: %s",
        bbox,
    )

    image = hent_kort(
        bbox,
        token=token,
    )

    png_sti, pdf_sti = gem_kortfiler(
        image=image,
        points=points,
        bbox=bbox,
    )

    logger.info(
        "PNG gemt: %s",
        png_sti.resolve(),
    )

    logger.info(
        "PDF gemt: %s",
        pdf_sti.resolve(),
    )


if __name__ == "__main__":
    main()