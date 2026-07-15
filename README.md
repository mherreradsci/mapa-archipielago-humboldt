# Mapa satelital del Archipiélago de Humboldt

Genera cartografía satelital de alta resolución del Archipiélago de Humboldt
(islas Chañaral, Damas, Choros, Gaviota, Tilgo y Pájaros — regiones de Atacama
y Coquimbo, Chile) lista para imprimir en plotter, usando exclusivamente
fuentes de datos de acceso público.

## Productos

Todos se generan en `salida/`:

| Archivo | Descripción |
|---|---|
| `mapa_humboldt_esri.pdf` / `.png` | Lámina A0 (84.1 × 118.9 cm) a 300 DPI con Esri World Imagery (detalle sub-métrico, aspecto "Google Earth") |
| `mapa_humboldt_sentinel.pdf` / `.png` | Misma lámina con Sentinel-2 cloudless de EOX (datos Copernicus 100 % abiertos, 10 m) |
| `mapa_humboldt_interactivo.html` | Mapa web interactivo (folium/Leaflet) con ambas capas conmutables, minimapa, pantalla completa y coordenadas del cursor |

Cada lámina incluye grilla de coordenadas (cada 0.1°), barra de escala corregida
por latitud, flecha de norte, título y la atribución obligatoria de la fuente.

## Uso

```bash
# 1. Crear el entorno (Python 3.12, definido en .python-version)
python -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Generar todo (ambas fuentes + HTML)
.venv/bin/python generar_mapa.py

# Variantes
.venv/bin/python generar_mapa.py --fuente esri        # solo raster Esri
.venv/bin/python generar_mapa.py --producto html      # solo el mapa web
.venv/bin/python generar_mapa.py --dpi 75             # prueba rápida (zoom reducido)
.venv/bin/python generar_mapa.py --zoom 16            # forzar zoom de teselas
```

## Notas técnicas

- **Área**: bbox WGS84 −71.78 a −71.22 lon, −29.68 a −28.92 lat, ajustado
  automáticamente a la proporción exacta de un A0 retrato en Web Mercator
  (EPSG:3857) para que la imagen llene la página sin deformación.
- **Resolución**: el PNG A0 mide ~9933 × 14043 px (~150–350 MB). El PDF incrusta
  el raster a resolución completa; es el formato recomendado para el plotter.
- **Teselas**: se descargan con `contextily` y quedan en caché en
  `salida/.cache_teselas/`, así las corridas siguientes no vuelven a descargar.
  La corrida completa baja ~4 000 teselas Esri (zoom 15) y ~1 000 de EOX
  (zoom 14); requiere red estable y ~4 GB de RAM libres.
- **Requisitos**: solo `contextily`, `matplotlib`, `pyproj`, `folium`, `pillow`,
  `numpy`, `requests` — sin GDAL ni cartopy.

## Fuentes de datos y licencias

- **Esri World Imagery** — teselas de acceso público gratuito; requiere mantener
  la atribución *"Source: Esri, Maxar, Earthstar Geographics, and the GIS User
  Community"* (impresa al pie de la lámina). Para usos comerciales masivos,
  revisar los términos de Esri.
- **Sentinel-2 cloudless** — mosaico anual sin nubes elaborado por
  [EOX IT Services](https://s2maps.eu) a partir de datos del programa
  **Copernicus** (ESA/UE), datos abiertos incluso para uso comercial
  (licencia CC-BY 4.0 del mosaico; datos Sentinel modificados).
- El mapa interactivo además ofrece la capa de referencia de nombres y límites
  de Esri como superposición opcional.
