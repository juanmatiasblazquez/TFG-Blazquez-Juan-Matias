"""RNF04: las versiones son inmutables. Generar de nuevo crea otra alternativa, nunca pisa la
anterior, y la base rechaza cualquier modificación de una versión guardada (D28)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

# Todo lo que forma una versión. La huella incluye cada columna de cada fila, geometrías en
# EWKB incluidas (el ::text de una fila).
PARTES = ("nodo_red", "tramo_circulacion", "manzana", "celda", "incumplimiento", "area_reservada_version")


def huella(db, id_version: int) -> list[str]:
    filas = [db.scalar(text("SELECT v::text FROM version_alternativa v WHERE id_version = :v"), {"v": id_version})]
    for tabla in PARTES:
        filas.append(
            db.scalar(
                text(f"SELECT md5(string_agg(t::text, '|' ORDER BY t::text)) FROM {tabla} t WHERE id_version = :v"),
                {"v": id_version},
            )
        )
    return filas


def test_generar_dos_veces_crea_otra_alternativa_y_la_primera_queda_intacta(cliente, crear_proyecto, generar, db):
    proyecto = crear_proyecto()
    primera = generar(proyecto["id_proyecto"])
    antes = huella(db, primera["version"]["id_version"])
    db.rollback()

    segunda = generar(proyecto["id_proyecto"], semilla=7)

    assert (primera["codigo"], segunda["codigo"]) == ("A", "B")
    assert primera["version"]["numero"] == segunda["version"]["numero"] == 1
    versiones = db.scalar(
        text(
            "SELECT count(*) FROM version_alternativa v JOIN alternativa a USING (id_alternativa) "
            "WHERE a.id_proyecto = :p"
        ),
        {"p": proyecto["id_proyecto"]},
    )
    assert versiones == 2
    assert huella(db, primera["version"]["id_version"]) == antes
    assert cliente.get(f"/api/alternativas/{primera['id_alternativa']}").json() == primera
    leido = cliente.get(f"/api/proyectos/{proyecto['id_proyecto']}").json()
    assert [a["codigo"] for a in leido["alternativas"]] == ["A", "B"]


@pytest.fixture
def version_guardada(cliente, crear_proyecto, generar) -> int:
    """Una versión con filas en todas sus tablas, también en `incumplimiento`: un DELETE sin filas
    no dispara el trigger de fila. Los cinco casos de referencia ya cumplen todo (D44, D47), así que
    el rectangular se genera con la colectora de 18 m: sin una jerarquía de avenida, la proporción
    del art. 12 de la Ley 4146 queda marcada (D48)."""
    id_proyecto = crear_proyecto()["id_proyecto"]
    valores = cliente.get("/api/parametros/referencia").json()["valores"]
    valores["jerarquias"][0]["ancho_vereda_m"] = 3
    assert cliente.post(f"/api/proyectos/{id_proyecto}/parametros", json=valores).status_code == 201
    version = generar(id_proyecto)["version"]
    assert version["capas"]["incumplimientos"]["features"]
    return version["id_version"]


@pytest.mark.parametrize(
    "sentencia",
    [
        "UPDATE version_alternativa SET semilla = semilla + 1 WHERE id_version = :v",
        "DELETE FROM version_alternativa WHERE id_version = :v",
        "UPDATE celda SET cumple = NOT cumple WHERE id_version = :v",
        "DELETE FROM celda WHERE id_version = :v",
        "UPDATE manzana SET fijada = true WHERE id_version = :v",
        "UPDATE tramo_circulacion SET fijado = true WHERE id_version = :v",
        "UPDATE nodo_red SET id_punto_acceso = NULL WHERE id_version = :v",
        "DELETE FROM incumplimiento WHERE id_version = :v",
        "TRUNCATE incumplimiento",
        "TRUNCATE area_reservada_version",
    ],
)
def test_la_base_rechaza_modificar_una_version_guardada(db, version_guardada, sentencia):
    with pytest.raises(DBAPIError, match="inmutables"):
        db.execute(text(sentencia), {"v": version_guardada})
    db.rollback()


# --- Observaciones, respuestas y enlaces (migración 0012, D69, D70) -----------------------------------


@pytest.fixture
def observada(cliente, crear_proyecto, generar) -> dict:
    """Una observación respondida y un enlace que comparte la versión."""
    proyecto = crear_proyecto()
    alternativa = generar(proyecto["id_proyecto"])
    observacion = cliente.post(
        f"/api/versiones/{alternativa['version']['id_version']}/observaciones",
        json={"tipo": "grafica", "criticidad": "sugerida", "descripcion": "Revisar las cotas."},
    ).json()
    respondida = cliente.post(
        f"/api/observaciones/{observacion['id_observacion']}/respuestas",
        json={"accion": "aclaracion", "descripcion": "Las cotas son las del motor."},
    )
    assert respondida.status_code == 201, respondida.text
    assert cliente.patch(f"/api/proyectos/{proyecto['id_proyecto']}/seleccion", json={"alternativas": ["A"]}).status_code == 200
    from datetime import timedelta

    from app.core import reloj

    fecha = (reloj.hoy() + timedelta(days=3)).isoformat()
    enlace = cliente.post(f"/api/proyectos/{proyecto['id_proyecto']}/enlaces", json={"fecha_vencimiento": fecha})
    assert enlace.status_code == 201, enlace.text
    return {"o": observacion["id_observacion"], "e": enlace.json()["enlace"]["id_enlace"]}


@pytest.mark.parametrize(
    ("sentencia", "mensaje"),
    [
        # Lo observado no cambia: ni el detalle, ni la criticidad, ni la versión, ni el sector.
        ("UPDATE observacion SET descripcion = 'otra' WHERE id_observacion = :o", "no se modifica"),
        ("UPDATE observacion SET criticidad = 'bloqueante' WHERE id_observacion = :o", "no se modifica"),
        ("UPDATE observacion SET sector = ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 0))', 4326) "
         "WHERE id_observacion = :o", "no se modifica"),
        ("DELETE FROM observacion WHERE id_observacion = :o", "no se modifica"),
        ("TRUNCATE observacion CASCADE", "no se modifica|inmutables"),
        # Una respuesta y el enlace a sus versiones no cambian nunca.
        ("UPDATE respuesta_observacion SET descripcion = 'otra' WHERE id_observacion = :o", "inmutables"),
        ("DELETE FROM respuesta_observacion WHERE id_observacion = :o", "inmutables"),
        ("UPDATE enlace_version SET id_version = id_version WHERE id_enlace = :e", "inmutables"),
        ("DELETE FROM enlace_version WHERE id_enlace = :e", "inmutables"),
    ],
)
def test_la_base_protege_lo_observado_las_respuestas_y_lo_compartido(db, observada, sentencia, mensaje):
    with pytest.raises(DBAPIError, match=mensaje):
        db.execute(text(sentencia), observada)
    db.rollback()


def test_una_observacion_solo_cambia_de_estado(db, observada):
    """El ciclo de revisión cambia el estado y la fecha de cierre, y nada más."""
    db.execute(
        text("UPDATE observacion SET estado = 'cerrada', fecha_cierre = now() WHERE id_observacion = :o"), observada
    )
    assert db.scalar(text("SELECT estado FROM observacion WHERE id_observacion = :o"), observada) == "cerrada"
    db.rollback()
