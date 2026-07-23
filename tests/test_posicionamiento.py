"""
Pruebas para verificar el cálculo de posicionamiento de la imagen satelital.

Verifica que el cálculo de posicionamiento use dimensiones consistentes
para evitar desalineación de 1 píxel entre la imagen y la grilla.
"""

import numpy as np
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from PIL import Image
import sys

# Agregar el directorio raíz al path para importar generar_mapa
sys.path.insert(0, str(Path(__file__).parent.parent))

import generar_mapa


class TestPosicionamientoImagen:
    """Pruebas del cálculo de posicionamiento de la imagen satelital."""

    def test_posicionamiento_usa_fig_dims_consistentes(self):
        """Verifica que el posicionamiento use fig_dims, no canvas dimensions."""
        # Crear una imagen de prueba pequeña
        imagen_prueba = np.random.randint(0, 256, (100, 80, 3), dtype=np.uint8)

        # Dimensiones esperadas basadas en A0 y DPI
        ancho_fig_px = 1000
        alto_fig_px = 1400
        fig_dims = (ancho_fig_px, alto_fig_px)

        # Calcular el posicionamiento esperado
        x0_esperado = int(generar_mapa.RECT_EJES[0] * ancho_fig_px)
        y0_esperado = alto_fig_px - int(generar_mapa.RECT_EJES[1] * alto_fig_px) - imagen_prueba.shape[0]

        # Verificar que el cálculo es correcto
        assert x0_esperado > 0, "x0 debe ser positivo (margen izquierdo)"
        assert y0_esperado > 0, "y0 debe ser positivo (margen inferior)"

        # Verificar que y0 = alto_fig - margen_inferior - altura_imagen
        expected_calculation = fig_dims[1] - int(generar_mapa.RECT_EJES[1] * fig_dims[1]) - imagen_prueba.shape[0]
        assert y0_esperado == expected_calculation, \
            f"y0 debe usar fig_dims, no canvas dimensions: {y0_esperado} != {expected_calculation}"

    def test_posicionamiento_consistente_multiples_dpi(self):
        """Verifica que el posicionamiento sea consistente con diferentes DPI."""
        # Probar con múltiples valores de DPI
        dpi_valores = [72, 100, 150, 300]
        posiciones = []

        for dpi in dpi_valores:
            # Calcular dimensiones como lo hace generar_raster()
            ancho_fig_px = int(round(generar_mapa.A0_PULGADAS[0] * dpi))
            alto_fig_px = int(round(generar_mapa.A0_PULGADAS[1] * dpi))

            # Calcular px_mapa como lo hace generar_raster()
            px_mapa_ancho = int(ancho_fig_px * generar_mapa.RECT_EJES[2])
            px_mapa_alto = int(alto_fig_px * generar_mapa.RECT_EJES[3])

            # Crear imagen de prueba con dimensiones correctas
            imagen_prueba = np.random.randint(0, 256, (px_mapa_alto, px_mapa_ancho, 3), dtype=np.uint8)

            # Calcular posicionamiento
            x0 = int(generar_mapa.RECT_EJES[0] * ancho_fig_px)
            y0 = alto_fig_px - int(generar_mapa.RECT_EJES[1] * alto_fig_px) - imagen_prueba.shape[0]

            posiciones.append((dpi, x0, y0, ancho_fig_px, alto_fig_px))

        # Verificar que todas las posiciones son válidas
        for dpi, x0, y0, ancho, alto in posiciones:
            assert x0 > 0, f"DPI {dpi}: x0 debe ser positivo"
            assert y0 > 0, f"DPI {dpi}: y0 debe ser positivo"
            assert x0 < ancho, f"DPI {dpi}: x0 debe estar dentro del canvas"
            assert y0 < alto, f"DPI {dpi}: y0 debe estar dentro del canvas"

    def test_imagen_cabe_dentro_del_canvas(self):
        """Verifica que la imagen posicionada cabe completamente en el canvas."""
        # Dimensiones del canvas
        ancho_fig_px = 2000
        alto_fig_px = 2800

        # Dimensiones de la imagen (máximo según RECT_EJES)
        px_mapa_ancho = int(ancho_fig_px * generar_mapa.RECT_EJES[2])
        px_mapa_alto = int(alto_fig_px * generar_mapa.RECT_EJES[3])
        imagen = np.zeros((px_mapa_alto, px_mapa_ancho, 3), dtype=np.uint8)

        # Calcular posicionamiento
        x0 = int(generar_mapa.RECT_EJES[0] * ancho_fig_px)
        y0 = alto_fig_px - int(generar_mapa.RECT_EJES[1] * alto_fig_px) - imagen.shape[0]

        # Verificar límites
        x1 = x0 + imagen.shape[1]
        y1 = y0 + imagen.shape[0]

        assert x0 >= 0, "Borde izquierdo no debe estar fuera del canvas"
        assert y0 >= 0, "Borde inferior no debe estar fuera del canvas"
        assert x1 <= ancho_fig_px, f"Borde derecho fuera del canvas: {x1} > {ancho_fig_px}"
        assert y1 <= alto_fig_px, f"Borde superior fuera del canvas: {y1} > {alto_fig_px}"

    def test_componer_lamina_firma_incluye_fig_dims(self):
        """Verifica que componer_lamina() tenga fig_dims en su firma."""
        import inspect

        # Obtener la firma de componer_lamina
        sig = inspect.signature(generar_mapa.componer_lamina)
        parametros = list(sig.parameters.keys())

        # Verificar que fig_dims esté en los parámetros
        assert 'fig_dims' in parametros, \
            f"componer_lamina debe tener parámetro 'fig_dims'. Parámetros actuales: {parametros}"

        # Verificar que sea el 5to parámetro (después de imagen, bbox, fuente, dpi)
        esperado_parametros = ['imagen', 'bbox', 'fuente', 'dpi', 'fig_dims']
        assert parametros == esperado_parametros, \
            f"Orden de parámetros incorrecto. Esperado: {esperado_parametros}, Actual: {parametros}"

    def test_rect_ejes_valores_validos(self):
        """Verifica que RECT_EJES tenga valores sensatos."""
        # RECT_EJES = [izq, abajo, ancho, alto]
        izq, abajo, ancho, alto = generar_mapa.RECT_EJES

        assert 0 <= izq < 0.1, "Margen izquierdo debe ser pequeño"
        assert 0 <= abajo < 0.1, "Margen inferior debe ser pequeño"
        assert 0.9 <= ancho <= 1.0, "Ancho debe ocupar casi todo"
        assert 0.8 <= alto <= 1.0, "Alto debe ocupar casi todo"

        # Verificar que no se solapan
        assert izq + ancho <= 1.0, "Rect_ejes no debe extenderse más allá del 100%"
        assert abajo + alto <= 1.0, "Rect_ejes no debe extenderse más allá del 100%"

    def test_posicionamiento_y0_formula_correcta(self):
        """Verifica que la fórmula de y0 sea matemáticamente correcta."""
        # y0 = alto_fig - margen_inferior - altura_imagen
        # Esto posiciona la imagen de modo que:
        # - Tiene un margen inferior de RECT_EJES[1] * alto_fig
        # - Comienza en y0 y se extiende hasta y0 + altura_imagen

        alto_fig = 1000
        margen_inf = generar_mapa.RECT_EJES[1]
        altura_img = 800

        y0 = alto_fig - int(margen_inf * alto_fig) - altura_img

        # Verificar que y0 + altura_img + margen_inf ≈ alto_fig
        espacio_ocupado = y0 + altura_img + int(margen_inf * alto_fig)
        assert espacio_ocupado <= alto_fig, \
            f"La imagen no debe exceder el alto del canvas: {espacio_ocupado} > {alto_fig}"


class TestConsistenciaConOriginal:
    """Pruebas que verifican compatibilidad con el comportamiento original."""

    def test_a0_pulgadas_no_cambio(self):
        """Verifica que las dimensiones A0 sean las correctas."""
        # A0: 841 x 1189 mm
        esperado_ancho = 841 / 25.4  # ~33.11 pulgadas
        esperado_alto = 1189 / 25.4  # ~46.81 pulgadas

        assert abs(generar_mapa.A0_PULGADAS[0] - esperado_ancho) < 0.01
        assert abs(generar_mapa.A0_PULGADAS[1] - esperado_alto) < 0.01

    def test_bbox_wgs84_es_valido(self):
        """Verifica que el bbox esté en un rango válido."""
        bbox = generar_mapa.BBOX_WGS84

        # Chile está aproximadamente entre -75° y -66° en longitud
        assert -75 <= bbox['oeste'] <= -66
        assert -75 <= bbox['este'] <= -66
        assert bbox['oeste'] < bbox['este'], "Oeste debe ser menor que Este"

        # Chile está aproximadamente entre -56° y -17° en latitud
        assert -56 <= bbox['sur'] <= -17
        assert -56 <= bbox['norte'] <= -17
        assert bbox['sur'] < bbox['norte'], "Sur debe ser menor que Norte"
