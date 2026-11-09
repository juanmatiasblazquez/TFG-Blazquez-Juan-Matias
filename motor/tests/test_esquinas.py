"""Ord. 8060, art. 54 (D49): «Las parcelas esquinas deberán incrementar la medida de su frente
mínimo en un 20% (veinte por ciento)».

- El subdivisor les da el frente de esquina a los lotes de las puntas de cada franja que dan a
  otra calle, y los del medio se reparten el resto (`anchos_de_lotes`).
- En el rectangular, todo lote en esquina tiene al menos 12 m de frente.
- El trazado a mano que incumple está en test_verificador.py.
"""

from dataclasses import replace

import pytest

from motor_trazados.geometria import IndiceEjes, medir, union_cobertura
from motor_trazados.subdivisores import anchos_de_lotes
from motor_trazados.valores_referencia import PARAMETROS_LOTEO_REFERENCIA as P
from motor_trazados.verificador import frente_minimo_en_esquina


def test_el_frente_de_esquina_es_un_20_por_ciento_mas():
    assert frente_minimo_en_esquina(P) == pytest.approx(12)
    assert frente_minimo_en_esquina(replace(P, porcentaje_incremento_esquina=0)) == pytest.approx(10)


@pytest.mark.parametrize(
    ("largo", "esquinas", "esperado"),
    [
        # Una franja de 105 m entre dos transversales (la del rectangular hasta la sesión 6): 9
        # lotes de 11,67 m. Las dos puntas pasan a 12 y los 7 del medio se reparten 81 m (11,57 m,
        # más que el mínimo).
        (105.0, (True, True), [12.0] + [81 / 7] * 7 + [12.0]),
        # Sin esquinas (una franja que llega al borde por los dos lados), iguales.
        (105.0, (False, False), [105 / 9] * 9),
        # Con lotes iguales de 12,5 m las esquinas ya tienen su frente.
        (25.0, (True, True), [12.5, 12.5]),
        # 22 m con una esquina: 12 en la esquina y 10 en el otro.
        (22.0, (True, False), [12.0, 10.0]),
        (22.0, (False, True), [10.0, 12.0]),
        # 22 m con dos esquinas: dos lotes de 11 no llegan, va uno solo.
        (22.0, (True, True), [22.0]),
    ],
)
def test_las_puntas_en_esquina_toman_el_frente_de_esquina(largo, esquinas, esperado):
    anchos = anchos_de_lotes(largo, esquinas, P)
    assert anchos == pytest.approx(esperado)
    assert sum(anchos) == pytest.approx(largo)


def test_sin_incremento_los_lotes_son_iguales():
    assert anchos_de_lotes(105.0, (True, True), replace(P, porcentaje_incremento_esquina=0)) == pytest.approx([105 / 9] * 9)


def test_en_el_rectangular_toda_esquina_tiene_12_m(resultado_referencia_sin_asignador):
    """56 lotes en esquina, todos con 12 m de frente o más (D49). Con la calle de borde por lado (D86),
    las dos puntas de cada franja dan a otra calle salvo contra el lado oeste, que cruza la grilla de
    punta y no la lleva: 16 manzanas × 2 franjas × 2 puntas, menos las 8 de las 4 manzanas de ese
    lado. Con la calle de borde en todo el contorno (D50) eran 64, y hasta el motor 0.6.0, 50 de 286."""
    r = resultado_referencia_sin_asignador
    circulacion = union_cobertura(r.corredores)
    ejes = IndiceEjes([t.eje for t in r.red.tramos()])
    medidas = [medir(c.geometria, circulacion, ejes) for c in r.lotes]
    esquinas = [m for m in medidas if m.esquina]
    assert len(r.lotes) == 288 and len(esquinas) == 64 - 8
    assert all(m.frente >= 12 - 0.01 for m in esquinas)
    assert min(m.frente for m in medidas if not m.esquina) >= P.frente_minimo - 0.01
