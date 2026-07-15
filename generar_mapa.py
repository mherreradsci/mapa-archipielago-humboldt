#!/usr/bin/env python3
"""
Mapa satelital del Archipiélago de Humboldt (Chile) para impresión en plotter.

Genera, a partir de datos de acceso público:
  - PDF y PNG en formato A0 (841 x 1189 mm) a 300 DPI, con imagen Esri World
    Imagery (sub-métrica) y con Sentinel-2 cloudless de EOX (datos Copernicus).
  - Un mapa interactivo HTML (folium) con ambas capas conmutables.

Uso:
    python generar_mapa.py                        # todo (ambas fuentes + HTML)
    python generar_mapa.py --fuente esri          # solo raster Esri
    python generar_mapa.py --producto html        # solo el HTML
    python generar_mapa.py --dpi 75               # corrida rápida de prueba

Atribución obligatoria de las fuentes (se imprime al pie del mapa):
  Esri:  "Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community"
  EOX:   "Sentinel-2 cloudless by EOX IT Services GmbH
          (Contains modified Copernicus Sentinel data)"
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

# Los mosaicos superan el límite anti "decompression bomb" de Pillow (178 Mpx).
Image.MAX_IMAGE_PIXELS = None

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

DIR_SALIDA = Path(__file__).resolve().parent / "salida"
DIR_CACHE = DIR_SALIDA / ".cache_teselas"

# Área de interés (WGS84): desde Isla Chañaral hasta Punta de Choros / I. Pájaros.
BBOX_WGS84 = {"oeste": -71.78, "este": -71.22, "sur": -29.68, "norte": -28.92}

# A0 retrato: 841 x 1189 mm.
A0_PULGADAS = (841 / 25.4, 1189 / 25.4)  # (33.11, 46.81) in

# Márgenes del lienzo (fracción de la figura): [izq, abajo, ancho, alto].
RECT_EJES = [0.015, 0.030, 0.970, 0.912]

URL_ESRI = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
URL_EOX = "https://tiles.maps.eox.at/wmts/1.0.0/{capa}/default/g/{z}/{y}/{x}.jpg"
CAPAS_EOX = ["s2cloudless-2024_3857", "s2cloudless-2023_3857", "s2cloudless_3857"]

FUENTES = {
    "esri": {
        "nombre": "Esri World Imagery",
        "zoom": 15,  # ~4.2 m/px a 29°S: nitidez plena para A0 a 300 DPI
        "atribucion": (
            "Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community"
        ),
    },
    "sentinel": {
        "nombre": "Sentinel-2 cloudless (EOX / Copernicus)",
        "zoom": 14,  # resolución nativa 10 m: más zoom no aporta detalle
        "atribucion": (
            "Sentinel-2 cloudless by EOX IT Services GmbH — "
            "https://s2maps.eu (Contains modified Copernicus Sentinel data)"
        ),
    },
}


# ---------------------------------------------------------------------------
# Utilidades geográficas
# ---------------------------------------------------------------------------

def a_mercator(lon: float, lat: float) -> tuple[float, float]:
    """WGS84 -> Web Mercator (EPSG:3857)."""
    from pyproj import Transformer

    tr = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    return tr.transform(lon, lat)


def a_wgs84(x: float, y: float) -> tuple[float, float]:
    """Web Mercator (EPSG:3857) -> WGS84."""
    from pyproj import Transformer

    tr = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    return tr.transform(x, y)


def bbox_mercator_ajustado(aspecto_objetivo: float) -> tuple[float, float, float, float]:
    """Bbox (w, s, e, n) en EPSG:3857 con relación alto/ancho exacta.

    Se expande el lado corto alrededor del centro para calzar con la caja de
    ejes del lienzo A0, de modo que el mapa llene la página sin deformarse.
    """
    w, s = a_mercator(BBOX_WGS84["oeste"], BBOX_WGS84["sur"])
    e, n = a_mercator(BBOX_WGS84["este"], BBOX_WGS84["norte"])
    ancho, alto = e - w, n - s
    cx, cy = (w + e) / 2, (s + n) / 2
    if alto / ancho < aspecto_objetivo:
        alto = ancho * aspecto_objetivo
    else:
        ancho = alto / aspecto_objetivo
    return (cx - ancho / 2, cy - alto / 2, cx + ancho / 2, cy + alto / 2)


def formatear_grado(valor: float, eje: str) -> str:
    """-71.5 -> \"71°30′O\"  |  -29.25 -> \"29°15′S\" (estilo cartográfico chileno)."""
    hemisferio = ("O" if valor < 0 else "E") if eje == "lon" else ("S" if valor < 0 else "N")
    grados_abs = abs(valor)
    g = int(grados_abs)
    m = round((grados_abs - g) * 60)
    if m == 60:
        g, m = g + 1, 0
    return f"{g}°{m:02d}′{hemisferio}"


def distancia_terreno_m(dx_mercator: float, lat: float) -> float:
    """Distancia real en el terreno para una distancia en metros Mercator."""
    return dx_mercator * math.cos(math.radians(lat))


# ---------------------------------------------------------------------------
# Descarga del mosaico de teselas
# ---------------------------------------------------------------------------

_CAPA_EOX: str | None = None


def capa_eox_disponible() -> str:
    """Devuelve la capa Sentinel-2 más reciente disponible en EOX (con memoización)."""
    import requests

    global _CAPA_EOX
    if _CAPA_EOX is not None:
        return _CAPA_EOX
    for capa in CAPAS_EOX:
        url = URL_EOX.format(capa=capa, z=8, y=147, x=77)  # tesela sobre Chile
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                _CAPA_EOX = capa
                return capa
        except requests.RequestException:
            continue
    raise RuntimeError("Ningún mosaico Sentinel-2 de EOX respondió; revisa la red.")


def descargar_mosaico(
    bbox: tuple[float, float, float, float], fuente: str, zoom: int
) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Descarga y ensambla las teselas del bbox. Devuelve (imagen, extent w,e,s,n)."""
    import contextily as ctx

    DIR_CACHE.mkdir(parents=True, exist_ok=True)
    ctx.set_cache_dir(str(DIR_CACHE))

    if fuente == "esri":
        url = URL_ESRI
    else:
        capa = capa_eox_disponible()
        print(f"  Capa EOX seleccionada: {capa}")
        url = URL_EOX.format(capa=capa, z="{z}", y="{y}", x="{x}")

    w, s, e, n = bbox
    ultimo_error: Exception | None = None
    for intento in range(1, 4):
        try:
            img, extent = ctx.bounds2img(w, s, e, n, zoom=zoom, source=url, ll=False)
            return img, extent
        except Exception as exc:  # red o servidor: reintento con espera
            ultimo_error = exc
            espera = 15 * intento
            print(f"  Intento {intento} falló ({exc}); reintento en {espera}s…")
            time.sleep(espera)
    raise RuntimeError(f"No se pudo descargar el mosaico de {fuente}: {ultimo_error}")


def recortar_y_remuestrear(
    img: np.ndarray,
    extent: tuple[float, float, float, float],
    bbox: tuple[float, float, float, float],
    px_destino: tuple[int, int],
) -> np.ndarray:
    """Recorta el mosaico al bbox exacto y lo remuestrea al tamaño de impresión."""
    ex_w, ex_e, ex_s, ex_n = extent
    w, s, e, n = bbox
    alto_px, ancho_px = img.shape[:2]
    sx = ancho_px / (ex_e - ex_w)
    sy = alto_px / (ex_n - ex_s)
    col0 = max(0, int((w - ex_w) * sx))
    col1 = min(ancho_px, int(math.ceil((e - ex_w) * sx)))
    fila0 = max(0, int((ex_n - n) * sy))
    fila1 = min(alto_px, int(math.ceil((ex_n - s) * sy)))
    recorte = img[fila0:fila1, col0:col1]

    pil = Image.fromarray(recorte)
    if pil.mode == "RGBA":
        pil = pil.convert("RGB")
    pil = pil.resize(px_destino, Image.LANCZOS)
    return np.asarray(pil)


def construir_imagen(
    bbox: tuple[float, float, float, float],
    fuente: str,
    zoom: int,
    px_destino: tuple[int, int],
    n_bandas: int = 8,
) -> np.ndarray:
    """Ensambla la imagen final por bandas horizontales para acotar la RAM.

    En lugar de materializar el mosaico completo (>1 GB a zoom 15), descarga y
    remuestrea franja por franja y las apila; el pico de memoria queda en la
    imagen final más una sola franja.
    """
    w, s, e, n = bbox
    px_w, px_h = px_destino
    bordes = np.linspace(0, px_h, n_bandas + 1).round().astype(int)
    filas: list[np.ndarray] = []
    for i in range(n_bandas):
        y0, y1 = int(bordes[i]), int(bordes[i + 1])
        n_i = n - (n - s) * (y0 / px_h)
        s_i = n - (n - s) * (y1 / px_h)
        print(f"  Banda {i + 1}/{n_bandas}…", flush=True)
        img, extent = descargar_mosaico((w, s_i, e, n_i), fuente, zoom)
        filas.append(
            recortar_y_remuestrear(img, extent, (w, s_i, e, n_i), (px_w, y1 - y0))
        )
        del img
    return np.vstack(filas)


# ---------------------------------------------------------------------------
# Composición cartográfica (matplotlib)
# ---------------------------------------------------------------------------

def dibujar_graticula(ax, bbox, tamano_fuente: float) -> None:
    """Grilla de coordenadas cada 0.1° con etiquetas dentro del marco."""
    import matplotlib.patheffects as pe

    w, s, e, n = bbox
    lon_o, lat_s = a_wgs84(w, s)
    lon_e, lat_n = a_wgs84(e, n)
    halo = [pe.withStroke(linewidth=tamano_fuente * 0.18, foreground="white")]
    paso = 0.1

    lon = math.ceil(lon_o / paso) * paso
    while lon < lon_e:
        x, _ = a_mercator(lon, lat_s)
        ax.plot([x, x], [s, n], color="white", alpha=0.35, lw=1.2, zorder=3)
        for y_frac, va in ((0.006, "bottom"), (0.994, "top")):
            ax.text(
                x, s + (n - s) * y_frac, formatear_grado(lon, "lon"),
                ha="center", va=va, fontsize=tamano_fuente, color="black",
                path_effects=halo, zorder=4,
            )
        lon += paso

    lat = math.ceil(lat_s / paso) * paso
    while lat < lat_n:
        _, y = a_mercator(lon_o, lat)
        ax.plot([w, e], [y, y], color="white", alpha=0.35, lw=1.2, zorder=3)
        for x_frac, ha in ((0.004, "left"), (0.996, "right")):
            ax.text(
                w + (e - w) * x_frac, y, formatear_grado(lat, "lat"),
                ha=ha, va="center", fontsize=tamano_fuente, color="black",
                path_effects=halo, zorder=4, rotation=90,
            )
        lat += paso


def dibujar_barra_escala(ax, bbox, tamano_fuente: float) -> None:
    """Barra de escala de 4 segmentos de 5 km, corregida por latitud."""
    from matplotlib.patches import Rectangle

    w, s, e, n = bbox
    _, lat_centro = a_wgs84((w + e) / 2, (s + n) / 2)
    segmento_terreno = 5_000  # m reales por segmento
    segmento_merc = segmento_terreno / math.cos(math.radians(lat_centro))
    n_seg = 4

    x0 = w + (e - w) * 0.035
    y0 = s + (n - s) * 0.030
    alto = (n - s) * 0.004

    fondo = Rectangle(
        (x0 - segmento_merc * 0.25, y0 - alto * 2.2),
        segmento_merc * (n_seg + 0.5), alto * 7.5,
        facecolor="white", alpha=0.75, edgecolor="none", zorder=5,
    )
    ax.add_patch(fondo)
    for i in range(n_seg):
        ax.add_patch(Rectangle(
            (x0 + i * segmento_merc, y0), segmento_merc, alto,
            facecolor="black" if i % 2 == 0 else "white",
            edgecolor="black", lw=1.0, zorder=6,
        ))
    for i in range(n_seg + 1):
        ax.text(
            x0 + i * segmento_merc, y0 + alto * 1.5, f"{i * 5}",
            ha="center", va="bottom", fontsize=tamano_fuente, zorder=6,
        )
    ax.text(
        x0 + n_seg * segmento_merc / 2, y0 - alto * 1.0, "kilómetros",
        ha="center", va="top", fontsize=tamano_fuente * 0.85, zorder=6,
    )


def dibujar_flecha_norte(ax, bbox, tamano_fuente: float) -> None:
    """Flecha de norte en la esquina superior derecha."""
    from matplotlib.patches import Polygon

    w, s, e, n = bbox
    cx = w + (e - w) * 0.955
    cy = s + (n - s) * 0.945
    alto = (n - s) * 0.028
    ancho = (e - w) * 0.010

    ax.add_patch(Polygon(
        [(cx, cy + alto / 2), (cx - ancho, cy - alto / 2), (cx, cy - alto / 5)],
        facecolor="black", edgecolor="black", zorder=6,
    ))
    ax.add_patch(Polygon(
        [(cx, cy + alto / 2), (cx + ancho, cy - alto / 2), (cx, cy - alto / 5)],
        facecolor="white", edgecolor="black", zorder=6,
    ))
    import matplotlib.patheffects as pe

    ax.text(
        cx, cy + alto * 0.62, "N", ha="center", va="bottom",
        fontsize=tamano_fuente * 1.6, fontweight="bold", zorder=6,
        path_effects=[pe.withStroke(linewidth=tamano_fuente * 0.2, foreground="white")],
    )


def componer_lamina(
    imagen: np.ndarray,
    bbox: tuple[float, float, float, float],
    fuente: str,
    dpi: int,
) -> None:
    """Compone la lámina A0 y la guarda como PNG y PDF."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # El tamaño en puntos es independiente del DPI: 26 pt es legible en un A0.
    fs_base = 26

    fig = plt.figure(figsize=A0_PULGADAS, dpi=dpi)
    ax = fig.add_axes(RECT_EJES)
    w, s, e, n = bbox
    ax.imshow(imagen, extent=(w, e, s, n), interpolation="none", zorder=1)
    ax.set_xlim(w, e)
    ax.set_ylim(s, n)
    ax.set_xticks([])
    ax.set_yticks([])
    for lado in ax.spines.values():
        lado.set_linewidth(2.5)

    dibujar_graticula(ax, bbox, fs_base * 0.75)
    dibujar_barra_escala(ax, bbox, fs_base * 0.8)
    dibujar_flecha_norte(ax, bbox, fs_base)

    info = FUENTES[fuente]
    fig.text(
        0.5, 0.985, "ARCHIPIÉLAGO DE HUMBOLDT",
        ha="center", va="top", fontsize=fs_base * 2.6, fontweight="bold",
    )
    fig.text(
        0.5, 0.958,
        f"Regiones de Atacama y Coquimbo, Chile — Imagen satelital: {info['nombre']}",
        ha="center", va="top", fontsize=fs_base * 1.1,
    )
    fig.text(
        0.5, 0.0165,
        f"{info['atribucion']}  |  Sistema de referencia: WGS84 / Web Mercator "
        f"(EPSG:3857)  |  Elaborado: {dt.date.today():%d-%m-%Y}",
        ha="center", va="center", fontsize=fs_base * 0.65, color="0.25",
    )

    DIR_SALIDA.mkdir(parents=True, exist_ok=True)
    for extension in ("png", "pdf"):
        destino = DIR_SALIDA / f"mapa_humboldt_{fuente}.{extension}"
        print(f"  Guardando {destino.name}…")
        fig.savefig(destino, dpi=dpi, facecolor="white")
    plt.close(fig)


def generar_raster(fuente: str, dpi: int, zoom_override: int | None) -> None:
    """Flujo completo: descarga, remuestreo y composición para una fuente."""
    info = FUENTES[fuente]
    zoom = zoom_override if zoom_override is not None else info["zoom"]
    if dpi < 150 and zoom_override is None:
        zoom = max(zoom - 3, 9)  # corrida de prueba: menos teselas

    ancho_fig_px = int(round(A0_PULGADAS[0] * dpi))
    alto_fig_px = int(round(A0_PULGADAS[1] * dpi))
    px_mapa = (int(ancho_fig_px * RECT_EJES[2]), int(alto_fig_px * RECT_EJES[3]))
    aspecto = px_mapa[1] / px_mapa[0]
    bbox = bbox_mercator_ajustado(aspecto)

    print(f"[{info['nombre']}] zoom {zoom}, lienzo {ancho_fig_px}x{alto_fig_px} px", flush=True)
    n_bandas = 8 if zoom >= 14 else 1
    imagen = construir_imagen(bbox, fuente, zoom, px_mapa, n_bandas)
    print(f"  Imagen ensamblada: {imagen.shape[1]}x{imagen.shape[0]} px", flush=True)
    componer_lamina(imagen, bbox, fuente, dpi)


# ---------------------------------------------------------------------------
# Mapa interactivo (folium)
# ---------------------------------------------------------------------------

def generar_html() -> None:
    import folium
    from folium.plugins import Fullscreen, MiniMap, MousePosition

    print("[HTML interactivo]")
    try:
        capa_eox = capa_eox_disponible()
    except RuntimeError:
        capa_eox = CAPAS_EOX[0]

    m = folium.Map(
        location=[-29.30, -71.50], zoom_start=11, tiles=None, control_scale=True,
    )
    folium.TileLayer(
        tiles=URL_ESRI,
        attr=FUENTES["esri"]["atribucion"],
        name="Esri World Imagery (alta resolución)",
        max_zoom=19,
    ).add_to(m)
    folium.TileLayer(
        tiles=URL_EOX.format(capa=capa_eox, z="{z}", y="{y}", x="{x}"),
        attr=FUENTES["sentinel"]["atribucion"],
        name="Sentinel-2 cloudless (Copernicus/EOX)",
        max_zoom=15,
        show=False,
    ).add_to(m)
    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Esri",
        name="Nombres y límites (referencia)",
        overlay=True,
        show=True,
        max_zoom=19,
    ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    Fullscreen(title="Pantalla completa", title_cancel="Salir").add_to(m)
    MiniMap(toggle_display=True).add_to(m)
    MousePosition(
        position="bottomright", separator=" , ", prefix="Lat/Lon:",
        lat_formatter="function(n){return n.toFixed(5)}",
        lng_formatter="function(n){return n.toFixed(5)}",
    ).add_to(m)
    m.fit_bounds([
        [BBOX_WGS84["sur"], BBOX_WGS84["oeste"]],
        [BBOX_WGS84["norte"], BBOX_WGS84["este"]],
    ])

    titulo = (
        '<div style="position:fixed;top:12px;left:50%;transform:translateX(-50%);'
        'z-index:9999;background:rgba(255,255,255,.9);padding:6px 18px;'
        'border-radius:6px;font:600 16px/1.4 sans-serif;box-shadow:0 1px 4px rgba(0,0,0,.3);">'
        "Archipiélago de Humboldt — Chile</div>"
    )
    m.get_root().html.add_child(folium.Element(titulo))

    DIR_SALIDA.mkdir(parents=True, exist_ok=True)
    destino = DIR_SALIDA / "mapa_humboldt_interactivo.html"
    m.save(str(destino))
    print(f"  Guardado {destino.name}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument(
        "--fuente", choices=["esri", "sentinel", "ambas"], default="ambas",
        help="imagen satelital a usar para los raster (defecto: ambas)",
    )
    parser.add_argument(
        "--producto", choices=["raster", "html", "todos"], default="todos",
        help="qué generar (defecto: todos)",
    )
    parser.add_argument(
        "--dpi", type=int, default=300,
        help="resolución de impresión; use 72-96 para pruebas rápidas (defecto: 300)",
    )
    parser.add_argument(
        "--zoom", type=int, default=None,
        help="forzar nivel de zoom de teselas (defecto: 15 Esri / 14 Sentinel-2)",
    )
    args = parser.parse_args()

    inicio = time.time()
    if args.producto in ("raster", "todos"):
        fuentes = ["esri", "sentinel"] if args.fuente == "ambas" else [args.fuente]
        for fuente in fuentes:
            generar_raster(fuente, args.dpi, args.zoom)
    if args.producto in ("html", "todos"):
        generar_html()
    print(f"Listo en {time.time() - inicio:.0f} s. Archivos en: {DIR_SALIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
