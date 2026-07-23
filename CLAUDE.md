# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Single-script Python project (`generar_mapa.py`) that generates print-ready A0 satellite maps of the Humboldt Archipelago (Chile) plus an interactive folium HTML map, using public tile sources (Esri World Imagery and EOX Sentinel-2 cloudless). All code, comments, CLI flags, and output messages are in Spanish — keep new code consistent with that.

## Commands

```bash
# Environment (Python 3.12, see .python-version)
python -m venv .venv
.venv/bin/pip install -r requirements.txt

# Full run: both raster sources + HTML (slow: downloads ~5000 tiles, needs ~2 GB RAM, peaks at ~1.6 GB at 300 DPI)
.venv/bin/python generar_mapa.py

# Fast test run (low DPI automatically reduces tile zoom by 3 levels)
.venv/bin/python generar_mapa.py --dpi 75

# Partial runs
.venv/bin/python generar_mapa.py --fuente esri      # one raster source (esri|sentinel|ambas)
.venv/bin/python generar_mapa.py --producto html    # only the folium map (raster|html|todos)
.venv/bin/python generar_mapa.py --zoom 16          # force tile zoom level
```

Tests and linting are configured. To verify changes before running the full map generator:

```bash
# Run all tests (unit tests for geo utilities, image processing)
make test              # or: .venv/bin/python -m pytest tests/ -v

# Check code style with ruff
make lint              # or: .venv/bin/ruff check generar_mapa.py

# Both at once
make check
```

Also, test with `--dpi 75` (fast, uses tile cache) rather than a full 300 DPI run, which takes a long time and heavy downloads.

Outputs go to `salida/`; downloaded tiles are cached in `salida/.cache_teselas/` (contextily cache), so repeated runs don't re-download.

## Architecture of generar_mapa.py

The script is organized as a pipeline, top to bottom in the file:

1. **Config constants** — `BBOX_WGS84` (area of interest), `FUENTES` (per-source name/zoom/mandatory attribution), tile URL templates, `A0_PULGADAS`, `RECT_EJES` (axes rectangle as figure fractions).
2. **Geo utilities** — WGS84↔Web Mercator conversion via pyproj; `bbox_mercator_ajustado()` expands the bbox's short side so its aspect ratio exactly matches the A0 axes box (the map fills the page without distortion). Ground distances must be corrected by `cos(lat)` because Web Mercator inflates lengths (~14% at 29°S) — see `distancia_terreno_m()` and the scale bar.
3. **Tile download** — `construir_imagen()` downloads and resamples the mosaic in 8 horizontal bands (`n_bandas`) to cap RAM: the full mosaic at zoom 15 exceeds 1 GB, so only one band plus the final image is ever in memory. `descargar_mosaico()` retries 3× with backoff. `capa_eox_disponible()` probes EOX layers newest-first (`CAPAS_EOX`) and memoizes the first that responds.
4. **Map composition (matplotlib + Pillow)** — `componer_lamina()` assembles the A0 sheet: image + graticule (every 0.1°), latitude-corrected scale bar, north arrow, title, and the source attribution footer. Font sizes are in points (independent of DPI), derived from `fs_base = 26`. **Since v0.2:** PNG and PDF are both rendered via Pillow (not matplotlib's PDF backend) to reduce peak RAM from ~6–8 GB to ~1.6 GB at 300 DPI.
5. **Interactive map** — `generar_html()` builds the folium map with both switchable base layers plus an Esri reference overlay.
6. **CLI** — `main()` wires `--fuente/--producto/--dpi/--zoom` to the two generators.

Heavy imports (contextily, matplotlib, pyproj, folium) are deferred inside functions so partial runs stay fast.

## Constraints

- **Attribution is mandatory**: the Esri and EOX/Copernicus attribution strings in `FUENTES` must remain printed on the sheets and in the HTML layer attributions (license requirement).
- `Image.MAX_IMAGE_PIXELS = None` is intentional: the A0 raster (~9933×14043 px) exceeds Pillow's decompression-bomb limit.
- Dependencies are deliberately minimal (no GDAL, no cartopy) — keep it that way unless there's a strong reason.
