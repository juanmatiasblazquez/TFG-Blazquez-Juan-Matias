"""La conversión de coordenadas funciona de punta a punta (D21, D30): PostGIS, que tiene su
propio PROJ, mide sobre las geometrías guardadas en 4326 las mismas superficies que el motor
informó en metros."""

import pytest
from sqlalchemy import text

# Por celda (lotes y espacios verdes): superficie del motor (redondeada al centímetro cuadrado en numeric(10,2)),
# superficie plana en el sistema de cálculo según PostGIS y superficie elipsoidal (GRS80).
CONSULTA_LOTES = text(
    """
    SELECT c.designacion,
           c.superficie_m2::float8 AS motor,
           ST_Area(ST_Transform(c.geom, p.srid_calculo)) AS plana,
           ST_Area(c.geom::geography) AS elipsoidal
      FROM celda c
      JOIN version_alternativa v ON v.id_version = c.id_version
      JOIN alternativa a ON a.id_alternativa = v.id_alternativa
      JOIN proyecto p ON p.id_proyecto = a.id_proyecto
     WHERE c.id_version = :id_version
     ORDER BY c.designacion
    """
)


def test_postgis_mide_en_cada_lote_la_superficie_que_informo_el_motor(crear_proyecto, generar, db):
    alternativa = generar(crear_proyecto()["id_proyecto"])
    lotes = db.execute(CONSULTA_LOTES, {"id_version": alternativa["version"]["id_version"]}).all()
    assert len(lotes) == len(alternativa["version"]["capas"]["celdas"]["features"]) > 250
    for lote in lotes:
        # Mismo sistema de cálculo: la diferencia es el redondeo de la columna (≤ 0,005 m²) y
        # la de dos implementaciones de PROJ, muy por debajo del centímetro cuadrado.
        assert lote.plana == pytest.approx(lote.motor, abs=0.01), lote.designacion
        # Contra la superficie sobre el elipsoide, independiente de la proyección: en la ciudad
        # de Córdoba la plana en la faja 4 es un 0,03 % mayor (D21). Un SRID equivocado o los
        # ejes invertidos darían diferencias de órdenes de magnitud.
        assert lote.elipsoidal == pytest.approx(lote.motor, rel=1e-3), lote.designacion
        assert lote.elipsoidal < lote.motor


def test_postgis_mide_el_terreno_como_el_motor(crear_proyecto, db):
    proyecto = crear_proyecto()
    plana, guardada = db.execute(
        text(
            """
            SELECT ST_Area(ST_Transform(t.geom, p.srid_calculo)), t.superficie_m2::float8
              FROM terreno t JOIN proyecto p ON p.id_proyecto = t.id_proyecto
             WHERE p.id_proyecto = :id
            """
        ),
        {"id": proyecto["id_proyecto"]},
    ).one()
    assert guardada == pytest.approx(480 * 270, abs=0.01)
    assert plana == pytest.approx(guardada, abs=0.01)
