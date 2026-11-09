"""RNF05 a través de la API: la misma solicitud (terreno, parámetros y estrategia) guarda las
mismas geometrías, bit a bit, aunque llegue en otro proyecto (D30)."""

from sqlalchemy import text

# (tabla, columnas geométricas, orden). Las filas de una versión se insertan en el orden en
# que las devuelve el motor, que es estable (D25): el id sirve de orden.
CAPAS = (
    ("nodo_red", ("geom",), "id_nodo"),
    ("tramo_circulacion", ("eje", "geom"), "id_tramo"),
    ("manzana", ("geom",), "id_manzana"),
    ("celda", ("geom",), "id_celda"),
    ("incumplimiento", ("geom",), "id_incumplimiento"),
)


def geometrias(db, id_version: int) -> dict[str, list]:
    guardadas = {}
    for tabla, columnas, orden in CAPAS:
        seleccion = ", ".join(f"ST_AsBinary({c})" for c in columnas)
        filas = db.execute(
            text(f"SELECT {seleccion} FROM {tabla} WHERE id_version = :v ORDER BY {orden}"), {"v": id_version}
        ).all()
        guardadas[tabla] = [tuple(bytes(g) if g is not None else None for g in fila) for fila in filas]
    return guardadas


def valores(db, id_version: int) -> list:
    return db.execute(
        text(
            "SELECT designacion, superficie_m2, frente_m, fondo_m, cumple, motivo_incumplimiento "
            "FROM celda WHERE id_version = :v ORDER BY id_celda"
        ),
        {"v": id_version},
    ).all()


def test_la_misma_solicitud_guarda_las_mismas_geometrias(crear_proyecto, generar, db):
    uno = generar(crear_proyecto()["id_proyecto"])["version"]
    otro = generar(crear_proyecto()["id_proyecto"])["version"]  # otro proyecto, mismo terreno

    assert geometrias(db, uno["id_version"]) == geometrias(db, otro["id_version"])
    assert valores(db, uno["id_version"]) == valores(db, otro["id_version"])
    assert uno["indicadores"] == otro["indicadores"]
    assert uno["capas"]["celdas"]["features"][0]["geometry"] == otro["capas"]["celdas"]["features"][0]["geometry"]
