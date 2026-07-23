"""Tests for generar_mapa.py core utilities."""

import math
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

# Import functions from parent directory
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from generar_mapa import (
    a_mercator,
    a_wgs84,
    bbox_mercator_ajustado,
    distancia_terreno_m,
    formatear_grado,
    recortar_y_remuestrear,
)


class TestCoordinateTransformations:
    """Test WGS84 ↔ Web Mercator conversions."""

    def test_a_mercator_at_equator(self):
        """Mercator at equator should preserve longitude, y=0."""
        x, y = a_mercator(0, 0)
        assert x == pytest.approx(0, abs=1)
        assert y == pytest.approx(0, abs=1)

    def test_a_mercator_chilean_coordinates(self):
        """Test with actual project coordinates (Humboldt Archipelago)."""
        lon, lat = -71.5, -29.3
        x, y = a_mercator(lon, lat)
        # Mercator should give negative x for western hemisphere, negative y for south
        assert x < 0
        assert y < 0

    def test_roundtrip_mercator_wgs84(self):
        """Conversion should be reversible."""
        lon_orig, lat_orig = -71.5, -29.3
        x, y = a_mercator(lon_orig, lat_orig)
        lon_back, lat_back = a_wgs84(x, y)
        assert lon_back == pytest.approx(lon_orig, rel=1e-6)
        assert lat_back == pytest.approx(lat_orig, rel=1e-6)


class TestCoordinateFormatting:
    """Test coordinate display formatting."""

    def test_formatear_grado_negative_longitude(self):
        """−71.5° should format as 71°30′O (west)."""
        result = formatear_grado(-71.5, "lon")
        assert result == "71°30′O"

    def test_formatear_grado_negative_latitude(self):
        """−29.25° should format as 29°15′S (south)."""
        result = formatear_grado(-29.25, "lat")
        assert result == "29°15′S"

    def test_formatear_grado_positive_longitude(self):
        """71.5° should format as 71°30′E (east)."""
        result = formatear_grado(71.5, "lon")
        assert result == "71°30′E"

    def test_formatear_grado_positive_latitude(self):
        """29.25° should format as 29°15′N (north)."""
        result = formatear_grado(29.25, "lat")
        assert result == "29°15′N"

    def test_formatear_grado_minute_rounding(self):
        """59.99 minutes should round to next degree."""
        result = formatear_grado(-29.99983, "lat")
        assert result == "30°00′S"


class TestDistanceCorrection:
    """Test latitude-corrected ground distance."""

    def test_distancia_terreno_equator(self):
        """At equator (lat=0), cos(0)=1, so distance equals input."""
        dx_mercator = 1000
        dist = distancia_terreno_m(dx_mercator, lat=0)
        assert dist == pytest.approx(1000)

    def test_distancia_terreno_chile(self):
        """At 29°S, cos(29°) ≈ 0.875, so distance < mercator."""
        dx_mercator = 1000
        dist = distancia_terreno_m(dx_mercator, lat=-29.3)
        expected = 1000 * math.cos(math.radians(29.3))
        assert dist == pytest.approx(expected)

    def test_distancia_terreno_symmetry(self):
        """cos(−lat) = cos(lat), so north/south should match."""
        dx = 1000
        dist_south = distancia_terreno_m(dx, lat=-45)
        dist_north = distancia_terreno_m(dx, lat=45)
        assert dist_south == pytest.approx(dist_north)


class TestBoundingBoxAdjustment:
    """Test aspect ratio matching for A0 page."""

    def test_bbox_mercator_ajustado_returns_tuple(self):
        """Should return (w, s, e, n) mercator bbox."""
        bbox = bbox_mercator_ajustado(1.4)
        assert isinstance(bbox, tuple)
        assert len(bbox) == 4
        w, s, e, n = bbox
        assert w < e  # west < east
        assert s < n  # south < north

    def test_bbox_mercator_ajustado_aspect_ratio(self):
        """Output bbox should have target aspect ratio (height/width)."""
        aspecto = 1.4
        w, s, e, n = bbox_mercator_ajustado(aspecto)
        height = n - s
        width = e - w
        actual_aspect = height / width
        assert actual_aspect == pytest.approx(aspecto, rel=1e-3)

    def test_bbox_mercator_ajustado_square(self):
        """Square aspect ratio (1.0) should produce equal width/height."""
        w, s, e, n = bbox_mercator_ajustado(1.0)
        height = n - s
        width = e - w
        assert height == pytest.approx(width)


class TestImageResampling:
    """Test image cropping and resampling."""

    def test_recortar_y_remuestrear_output_size(self):
        """Output should match requested pixel dimensions."""
        # Create synthetic test image (100×100 RGB)
        img = np.random.randint(0, 256, (100, 100, 3), dtype=np.uint8)
        # Extent covers full image
        extent = (0, 100, 0, 100)
        # Bbox is center half
        bbox = (25, 25, 75, 75)
        # Request 50×50 output
        px_destino = (50, 50)

        result = recortar_y_remuestrear(img, extent, bbox, px_destino)

        assert result.shape == (50, 50, 3)
        assert result.dtype == np.uint8

    def test_recortar_y_remuestrear_rgb_conversion(self):
        """RGBA input should be converted to RGB."""
        # Create RGBA test image
        img_rgba = np.random.randint(0, 256, (100, 100, 4), dtype=np.uint8)
        extent = (0, 100, 0, 100)
        bbox = (0, 0, 100, 100)
        px_destino = (50, 50)

        result = recortar_y_remuestrear(img_rgba, extent, bbox, px_destino)

        # Should be RGB (3 channels)
        assert result.shape == (50, 50, 3)

    def test_recortar_y_remuestrear_scaling(self):
        """Small bbox cropped from large image should scale up correctly."""
        # 100×100 image, crop small center region, scale to larger output
        img = np.ones((100, 100, 3), dtype=np.uint8) * 128
        extent = (0, 100, 0, 100)
        bbox = (40, 40, 60, 60)  # 20×20 center region
        px_destino = (100, 100)  # Scale up to 100×100

        result = recortar_y_remuestrear(img, extent, bbox, px_destino)

        assert result.shape == (100, 100, 3)
        # Scaled uniform image should remain uniform
        assert np.std(result) < 5  # Very low variance


class TestTileSources:
    """Test tile source configuration."""

    def test_fuentes_structure(self):
        """FUENTES dict should have required keys for each source."""
        from generar_mapa import FUENTES

        required_keys = {"nombre", "zoom", "atribucion"}

        for fuente_name, fuente_config in FUENTES.items():
            assert isinstance(fuente_name, str), f"Source name should be string: {fuente_name}"
            assert isinstance(fuente_config, dict), f"Source config should be dict: {fuente_name}"
            assert required_keys.issubset(fuente_config.keys()), \
                f"Source '{fuente_name}' missing keys: {required_keys - set(fuente_config.keys())}"

    def test_fuentes_zoom_levels(self):
        """Zoom levels should be integers in reasonable range."""
        from generar_mapa import FUENTES

        for fuente_name, fuente_config in FUENTES.items():
            zoom = fuente_config["zoom"]
            assert isinstance(zoom, int), f"Zoom should be int for '{fuente_name}', got {type(zoom)}"
            assert 0 <= zoom <= 20, f"Zoom out of range for '{fuente_name}': {zoom}"

    def test_fuentes_attribution_strings(self):
        """Attribution strings should not be empty."""
        from generar_mapa import FUENTES

        for fuente_name, fuente_config in FUENTES.items():
            atribucion = fuente_config["atribucion"]
            assert isinstance(atribucion, str), f"Attribution should be string for '{fuente_name}'"
            assert len(atribucion) > 0, f"Attribution should not be empty for '{fuente_name}'"
            assert "©" in atribucion or "Copernicus" in atribucion or "Esri" in atribucion or "Sentinel" in atribucion, \
                f"Attribution missing expected credit marker for '{fuente_name}'"
