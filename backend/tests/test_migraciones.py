import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.db import Base, engine, incluir_objeto
from app.main import app
from tests.datos_referencia import cuerpo_generacion, cuerpo_recalculo

# Sin sesión: alcanza para el health, que es público. Lo demás va con el cliente del director técnico,
# que se vuelve a loguear después de cada migración (`restaurar_identidades`): bajar la base se lleva
# las sesiones, y bajar a `base`, también los usuarios.
anonimo = TestClient(app)


def _version_postgis() -> str | None:
    with engine.connect() as conexion:
        return conexion.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'postgis'")
        ).scalar_one_or_none()


def test_la_migracion_0001_es_la_que_habilita_postgis(alembic_cfg, restaurar_identidades):
    """Sin la migración no hay PostGIS (la imagen ya no lo crea) y el health lo dice.

    Bajar a `base` también prueba que el downgrade de 0002 deshace todas sus tablas: si dejara
    una con columnas geometry, el DROP EXTENSION de 0001 fallaría.
    """
    command.downgrade(alembic_cfg, "base")
    try:
        assert _version_postgis() is None
        respuesta = anonimo.get("/api/health")
        assert respuesta.status_code == 503
        cuerpo = respuesta.json()
        assert (cuerpo["estado"], cuerpo["base"], cuerpo["postgis"]) == ("degradado", "ok", None)

        command.upgrade(alembic_cfg, "head")
        assert _version_postgis() is not None
        assert anonimo.get("/api/health").status_code == 200
    finally:
        # Las demás pruebas asumen la base en head y los usuarios de prueba con su sesión.
        command.upgrade(alembic_cfg, "head")
        restaurar_identidades()


def test_la_0003_les_asigna_un_cliente_a_los_proyectos_que_ya_existian(alembic_cfg, restaurar_identidades):
    """Antes de la 0003 un proyecto no tenía cliente: la migración le asigna uno que lo dice,
    y recién después exige la columna (D35)."""
    command.downgrade(alembic_cfg, "0002")
    try:
        with engine.begin() as conexion:
            conexion.execute(
                text(
                    "INSERT INTO proyecto (id_usuario_responsable, codigo, nombre, tipo, srid_calculo, estado) "
                    "SELECT id_usuario, 'PREVIO-0003', 'Anterior al cliente', 'loteo', 5346, 'listo_para_generar' "
                    "FROM usuario LIMIT 1"
                )
            )
        command.upgrade(alembic_cfg, "0003")
        with engine.connect() as conexion:
            razon_social = conexion.scalar(
                text(
                    "SELECT c.razon_social FROM proyecto p JOIN cliente c USING (id_cliente) "
                    "WHERE p.codigo = 'PREVIO-0003'"
                )
            )
            nulos = conexion.scalar(text("SELECT count(*) FROM proyecto WHERE id_cliente IS NULL"))
        assert razon_social == "Sin cliente (proyectos anteriores a la migración 0003)"
        assert nulos == 0
    finally:
        command.upgrade(alembic_cfg, "head")
        restaurar_identidades()
        # Es un proyecto a medias (sin terreno): las demás pruebas no tienen que verlo.
        with engine.begin() as conexion:
            conexion.execute(text("DELETE FROM proyecto WHERE codigo = 'PREVIO-0003'"))


def test_la_0005_deja_en_null_lo_que_no_aplica(alembic_cfg, restaurar_identidades, cliente, crear_proyecto, generar):
    """La 0004 había completado los umbrales del verde con 1.000 y 20 en todos los conjuntos. La
    0005 los pasa a NULL («no aplica») en los conjuntos que ningún motor 0.4.0 o posterior usó, y
    deja NULL los parámetros nuevos del criterio de forma (D45). No toca ninguna fila de una tabla
    con trigger: los indicadores de una versión anterior ya eran NULL."""
    id_proyecto = crear_proyecto()["id_proyecto"]
    generar(id_proyecto)
    command.downgrade(alembic_cfg, "0004")
    try:
        with engine.begin() as conexion:
            # Dos conjuntos más del mismo proyecto, copias del v1: uno usado por una versión del
            # motor 0.3.1 y otro por una del 0.4.0, cada una en su alternativa.
            ids = {}
            for version, motor, codigo in ((2, "0.3.1", "Y"), (3, "0.4.0", "Z")):
                id_conjunto = conexion.scalar(
                    text(
                        "INSERT INTO conjunto_parametros (id_proyecto, version, vigente, criterio_prioritario, "
                        "porcentaje_espacio_verde, tolerancia_pct) SELECT id_proyecto, :version, false, "
                        "criterio_prioritario, porcentaje_espacio_verde, tolerancia_pct FROM conjunto_parametros "
                        "WHERE id_proyecto = :p AND version = 1 RETURNING id_conjunto"
                    ),
                    {"p": id_proyecto, "version": version},
                )
                conexion.execute(
                    text(
                        "INSERT INTO parametros_loteo SELECT :nuevo, frente_minimo_m, frente_objetivo_m, "
                        "fondo_minimo_m, superficie_minima_m2, superficie_maxima_m2, relacion_fondo_frente_max, "
                        "longitud_maxima_manzana_m, porcentaje_equipamiento, superficie_minima_verde_m2, "
                        "ancho_minimo_verde_m FROM parametros_loteo JOIN conjunto_parametros USING (id_conjunto) "
                        "WHERE id_proyecto = :p AND version = 1"
                    ),
                    {"p": id_proyecto, "nuevo": id_conjunto},
                )
                id_alternativa = conexion.scalar(
                    text(
                        "INSERT INTO alternativa (id_proyecto, codigo, estado) VALUES (:p, :codigo, 'generada') "
                        "RETURNING id_alternativa"
                    ),
                    {"p": id_proyecto, "codigo": codigo},
                )
                verde = "NULL" if motor == "0.3.1" else "1000"
                conexion.execute(
                    text(
                        "INSERT INTO version_alternativa (id_alternativa, id_conjunto, id_usuario, numero, patron_red, "
                        "orientacion_grados, semilla, cumple_restricciones, cantidad_celdas, "
                        "superficie_aprovechable_m2, porcentaje_circulacion, porcentaje_espacio_verde, longitud_red_m, "
                        "duracion_ms, version_motor, superficie_espacio_verde_m2, superficie_espacio_libre_m2, "
                        f"porcentaje_cesion) SELECT :a, :c, id_usuario, 1, 'grilla', 20, 1042, false, 286, 92234.92, "
                        f"28.83, 0, 2763.75, 150, :motor, {verde}, {verde}, {verde} FROM usuario LIMIT 1"
                    ),
                    {"a": id_alternativa, "c": id_conjunto, "motor": motor},
                )
                ids[motor] = (id_conjunto, id_alternativa)
        command.upgrade(alembic_cfg, "head")
        restaurar_identidades()

        with engine.connect() as conexion:
            def parametros(id_conjunto):
                return tuple(
                    conexion.execute(
                        text(
                            "SELECT superficie_minima_verde_m2, ancho_minimo_verde_m, ancho_minimo_lote_m, "
                            "factor_union_maximo FROM parametros_loteo WHERE id_conjunto = :c"
                        ),
                        {"c": id_conjunto},
                    ).one()
                )

            assert parametros(ids["0.3.1"][0]) == (None, None, None, None)
            assert parametros(ids["0.4.0"][0]) == (1000, 20, None, None)
        # Por la API, la versión anterior muestra NULL: el portal dice «no aplica».
        anterior = cliente.get(f"/api/alternativas/{ids['0.3.1'][1]}").json()["version"]
        assert anterior["version_motor"] == "0.3.1"
        indicadores = anterior["indicadores"]
        assert indicadores["superficie_espacio_verde_m2"] is None
        assert indicadores["superficie_espacio_libre_m2"] is None
        assert indicadores["porcentaje_cesion"] is None
    finally:
        command.upgrade(alembic_cfg, "head")
        restaurar_identidades()


def test_la_0006_deja_el_criterio_que_de_hecho_se_uso(alembic_cfg, restaurar_identidades, cliente, crear_proyecto, generar):
    """El criterio del asignador (D46) es «cercania» en los conjuntos que usó el motor 0.5.x (el
    de la sesión 6, que elegía por cercanía) y NULL en los anteriores al asignador y en los que
    nunca se usaron, como en la 0005. Los parámetros del art. 12 y del art. 54 quedan en NULL en
    todos, y los indicadores nuevos, en NULL en las versiones anteriores."""
    id_proyecto = crear_proyecto()["id_proyecto"]
    generar(id_proyecto)
    command.downgrade(alembic_cfg, "0005")
    try:
        with engine.begin() as conexion:
            ids = {}
            for version, motor, codigo in ((2, "0.4.0", "X"), (3, "0.5.0", "Y"), (4, None, None)):
                id_conjunto = conexion.scalar(
                    text(
                        "INSERT INTO conjunto_parametros (id_proyecto, version, vigente, criterio_prioritario, "
                        "porcentaje_espacio_verde, tolerancia_pct) SELECT id_proyecto, :version, false, "
                        "criterio_prioritario, porcentaje_espacio_verde, tolerancia_pct FROM conjunto_parametros "
                        "WHERE id_proyecto = :p AND version = 1 RETURNING id_conjunto"
                    ),
                    {"p": id_proyecto, "version": version},
                )
                columnas = (
                    "frente_minimo_m, frente_objetivo_m, fondo_minimo_m, superficie_minima_m2, superficie_maxima_m2, "
                    "relacion_fondo_frente_max, longitud_maxima_manzana_m, porcentaje_equipamiento, "
                    "superficie_minima_verde_m2, ancho_minimo_verde_m, ancho_minimo_lote_m, factor_union_maximo"
                )
                conexion.execute(
                    text(
                        f"INSERT INTO parametros_loteo (id_conjunto, {columnas}) SELECT :nuevo, {columnas} "
                        "FROM parametros_loteo JOIN conjunto_parametros USING (id_conjunto) "
                        "WHERE id_proyecto = :p AND version = 1"
                    ),
                    {"p": id_proyecto, "nuevo": id_conjunto},
                )
                id_alternativa = None
                if motor is not None:
                    id_alternativa = conexion.scalar(
                        text(
                            "INSERT INTO alternativa (id_proyecto, codigo, estado) VALUES (:p, :codigo, 'generada') "
                            "RETURNING id_alternativa"
                        ),
                        {"p": id_proyecto, "codigo": codigo},
                    )
                    conexion.execute(
                        text(
                            "INSERT INTO version_alternativa (id_alternativa, id_conjunto, id_usuario, numero, "
                            "patron_red, orientacion_grados, semilla, cumple_restricciones, cantidad_celdas, "
                            "superficie_aprovechable_m2, porcentaje_circulacion, porcentaje_espacio_verde, "
                            "longitud_red_m, duracion_ms, version_motor, superficie_espacio_verde_m2, "
                            "superficie_espacio_libre_m2, porcentaje_cesion) SELECT :a, :c, id_usuario, 1, 'grilla', "
                            "20, 1042, true, 259, 83000, 28.83, 7.4, 2763.75, 440, :motor, 9600, 0, 10.4 "
                            "FROM usuario LIMIT 1"
                        ),
                        {"a": id_alternativa, "c": id_conjunto, "motor": motor},
                    )
                ids[motor] = (id_conjunto, id_alternativa)
        command.upgrade(alembic_cfg, "head")
        restaurar_identidades()

        with engine.connect() as conexion:
            def parametros(id_conjunto):
                return tuple(
                    conexion.execute(
                        text(
                            "SELECT criterio_espacio_verde, porcentaje_minimo_avenidas, ancho_minimo_avenida_m, "
                            "ancho_minimo_calle_m, ancho_minimo_calzada_m, porcentaje_incremento_esquina "
                            "FROM parametros_loteo WHERE id_conjunto = :c"
                        ),
                        {"c": id_conjunto},
                    ).one()
                )

            assert parametros(ids["0.5.0"][0]) == ("cercania", None, None, None, None, None)
            assert parametros(ids["0.4.0"][0]) == (None,) * 6
            assert parametros(ids[None][0]) == (None,) * 6
        # Por la API, la versión de la sesión 6 muestra los indicadores nuevos en NULL («no aplica»).
        anterior = cliente.get(f"/api/alternativas/{ids['0.5.0'][1]}").json()["version"]
        assert anterior["indicadores"]["cantidad_lotes_grandes"] is None
        assert anterior["indicadores"]["porcentaje_avenidas"] is None
    finally:
        command.upgrade(alembic_cfg, "head")
        restaurar_identidades()


def test_la_0007_conserva_el_criterio_y_deja_en_null_lo_nuevo(alembic_cfg, restaurar_identidades, cliente, crear_proyecto, generar):
    """Cada conjunto conserva el criterio del asignador que de hecho usó (D51): «menos_lotes» el del
    motor 0.6.0, «cercania» el del 0.5.x y NULL el que nunca se usó. Los lados del art. 48 (D50)
    quedan en NULL en todos, y las distancias al verde, en NULL en las versiones anteriores. El
    valor por defecto nuevo, «cercania», es el de referencia del motor: lo recibe un conjunto nuevo,
    no los que ya existen."""
    id_proyecto = crear_proyecto()["id_proyecto"]
    generar(id_proyecto)
    command.downgrade(alembic_cfg, "0006")
    try:
        with engine.begin() as conexion:
            ids = {}
            columnas = (
                "frente_minimo_m, frente_objetivo_m, fondo_minimo_m, superficie_minima_m2, superficie_maxima_m2, "
                "relacion_fondo_frente_max, longitud_maxima_manzana_m, porcentaje_equipamiento, "
                "superficie_minima_verde_m2, ancho_minimo_verde_m, ancho_minimo_lote_m, factor_union_maximo, "
                "porcentaje_minimo_avenidas, ancho_minimo_avenida_m, ancho_minimo_calle_m, ancho_minimo_calzada_m, "
                "porcentaje_incremento_esquina"
            )
            for version, motor, codigo, criterio in (
                (2, "0.6.0", "X", "menos_lotes"),
                (3, "0.5.0", "Y", "cercania"),
                (4, None, None, None),
            ):
                id_conjunto = conexion.scalar(
                    text(
                        "INSERT INTO conjunto_parametros (id_proyecto, version, vigente, criterio_prioritario, "
                        "porcentaje_espacio_verde, tolerancia_pct) SELECT id_proyecto, :version, false, "
                        "criterio_prioritario, porcentaje_espacio_verde, tolerancia_pct FROM conjunto_parametros "
                        "WHERE id_proyecto = :p AND version = 1 RETURNING id_conjunto"
                    ),
                    {"p": id_proyecto, "version": version},
                )
                conexion.execute(
                    text(
                        f"INSERT INTO parametros_loteo (id_conjunto, {columnas}, criterio_espacio_verde) "
                        f"SELECT :nuevo, {columnas}, :criterio "
                        "FROM parametros_loteo JOIN conjunto_parametros USING (id_conjunto) "
                        "WHERE id_proyecto = :p AND version = 1"
                    ),
                    {"p": id_proyecto, "nuevo": id_conjunto, "criterio": criterio},
                )
                id_alternativa = None
                if motor is not None:
                    id_alternativa = conexion.scalar(
                        text(
                            "INSERT INTO alternativa (id_proyecto, codigo, estado) VALUES (:p, :codigo, 'generada') "
                            "RETURNING id_alternativa"
                        ),
                        {"p": id_proyecto, "codigo": codigo},
                    )
                    conexion.execute(
                        text(
                            "INSERT INTO version_alternativa (id_alternativa, id_conjunto, id_usuario, numero, "
                            "patron_red, orientacion_grados, semilla, cumple_restricciones, cantidad_celdas, "
                            "superficie_aprovechable_m2, porcentaje_circulacion, porcentaje_espacio_verde, "
                            "longitud_red_m, duracion_ms, version_motor, superficie_espacio_verde_m2, "
                            "superficie_espacio_libre_m2, porcentaje_cesion) SELECT :a, :c, id_usuario, 1, 'grilla', "
                            "20, 1042, true, 260, 85500, 27.4, 6.6, 2763.75, 600, :motor, 8553.75, 0, 10 "
                            "FROM usuario LIMIT 1"
                        ),
                        {"a": id_alternativa, "c": id_conjunto, "motor": motor},
                    )
                ids[motor] = (id_conjunto, id_alternativa)
        command.upgrade(alembic_cfg, "head")
        restaurar_identidades()

        with engine.connect() as conexion:
            def parametros(id_conjunto):
                return tuple(
                    conexion.execute(
                        text(
                            "SELECT criterio_espacio_verde, lado_minimo_manzana_m, lado_maximo_manzana_m, "
                            "lado_maximo_sin_pasaje_m FROM parametros_loteo WHERE id_conjunto = :c"
                        ),
                        {"c": id_conjunto},
                    ).one()
                )

            assert parametros(ids["0.6.0"][0]) == ("menos_lotes", None, None, None)
            assert parametros(ids["0.5.0"][0]) == ("cercania", None, None, None)
            assert parametros(ids[None][0]) == (None, None, None, None)
        # Por la API, las versiones anteriores muestran las distancias al verde en NULL («no aplica»).
        for motor in ("0.6.0", "0.5.0"):
            anterior = cliente.get(f"/api/alternativas/{ids[motor][1]}").json()["version"]
            assert anterior["indicadores"]["distancia_media_verde_m"] is None
            assert anterior["indicadores"]["distancia_maxima_verde_m"] is None
        # Un conjunto nuevo recibe el valor de referencia nuevo.
        referencia = cliente.get("/api/parametros/referencia").json()["valores"]["loteo"]
        assert referencia["criterio_espacio_verde"] == "cercania"
        assert (referencia["lado_minimo_manzana_m"], referencia["lado_maximo_manzana_m"]) == (42, 250)
    finally:
        command.upgrade(alembic_cfg, "head")
        restaurar_identidades()


def test_la_0014_deja_la_calle_de_borde_que_de_hecho_se_uso(alembic_cfg, restaurar_identidades, cliente, crear_proyecto, generar):
    """Cada conjunto toma la calle de borde que de hecho usó (D45, D86): «contorno» el que usó un motor de
    la 0.7.0 a la 0.10.x, y NULL el anterior a la calle de borde, el que nunca se usó y el que usó el
    0.11.0 (el rango se cierra ahí: al bajar la base se perdió el valor que ese motor usó). Generar con un
    conjunto en NULL da 422, y uno nuevo recibe el valor de referencia, «por_lado»."""
    id_proyecto = crear_proyecto()["id_proyecto"]
    generar(id_proyecto)
    command.downgrade(alembic_cfg, "0013")
    try:
        with engine.begin() as conexion:
            ids = {}
            columnas = (
                "frente_minimo_m, frente_objetivo_m, fondo_minimo_m, superficie_minima_m2, superficie_maxima_m2, "
                "relacion_fondo_frente_max, longitud_maxima_manzana_m, porcentaje_equipamiento, "
                "superficie_minima_verde_m2, ancho_minimo_verde_m, ancho_minimo_lote_m, factor_union_maximo, "
                "porcentaje_minimo_avenidas, ancho_minimo_avenida_m, ancho_minimo_calle_m, ancho_minimo_calzada_m, "
                "porcentaje_incremento_esquina, criterio_espacio_verde, lado_minimo_manzana_m, "
                "lado_maximo_manzana_m, lado_maximo_sin_pasaje_m"
            )
            for version, motor, codigo in ((2, "0.10.2", "X"), (3, "0.7.0", "Y"), (4, "0.6.0", "Z"), (5, None, None)):
                id_conjunto = conexion.scalar(
                    text(
                        "INSERT INTO conjunto_parametros (id_proyecto, version, vigente, criterio_prioritario, "
                        "porcentaje_espacio_verde, tolerancia_pct) SELECT id_proyecto, :version, false, "
                        "criterio_prioritario, porcentaje_espacio_verde, tolerancia_pct FROM conjunto_parametros "
                        "WHERE id_proyecto = :p AND version = 1 RETURNING id_conjunto"
                    ),
                    {"p": id_proyecto, "version": version},
                )
                conexion.execute(
                    text(
                        f"INSERT INTO parametros_loteo (id_conjunto, {columnas}) SELECT :nuevo, {columnas} "
                        "FROM parametros_loteo JOIN conjunto_parametros USING (id_conjunto) "
                        "WHERE id_proyecto = :p AND version = 1"
                    ),
                    {"p": id_proyecto, "nuevo": id_conjunto},
                )
                if motor is not None:
                    id_alternativa = conexion.scalar(
                        text(
                            "INSERT INTO alternativa (id_proyecto, codigo, estado) VALUES (:p, :codigo, 'generada') "
                            "RETURNING id_alternativa"
                        ),
                        {"p": id_proyecto, "codigo": codigo},
                    )
                    conexion.execute(
                        text(
                            "INSERT INTO version_alternativa (id_alternativa, id_conjunto, id_usuario, numero, tipo, "
                            "patron_red, orientacion_grados, semilla, cumple_restricciones, cantidad_celdas, "
                            "superficie_aprovechable_m2, porcentaje_circulacion, porcentaje_espacio_verde, "
                            "longitud_red_m, duracion_ms, version_motor) SELECT :a, :c, id_usuario, 1, 'generada', "
                            "'grilla', 20, 1042, true, 261, 85500, 36, 6.6, 3590, 600, :motor FROM usuario LIMIT 1"
                        ),
                        {"a": id_alternativa, "c": id_conjunto, "motor": motor},
                    )
                ids[version] = id_conjunto
            ids[1] = conexion.scalar(
                text("SELECT id_conjunto FROM conjunto_parametros WHERE id_proyecto = :p AND version = 1"),
                {"p": id_proyecto},
            )
        command.upgrade(alembic_cfg, "head")
        restaurar_identidades()

        with engine.connect() as conexion:
            def calle_borde(version):
                return conexion.scalar(
                    text("SELECT calle_borde FROM parametros_loteo WHERE id_conjunto = :c"), {"c": ids[version]}
                )

            assert [calle_borde(v) for v in (1, 2, 3, 4, 5)] == [None, "contorno", "contorno", None, None]
        # La v1, vigente, la usó el motor 0.11.0: quedó en NULL y generar con ella da 422 (D45).
        respuesta = cliente.post(f"/api/proyectos/{id_proyecto}/alternativas", json=cuerpo_generacion())
        assert respuesta.status_code == 422
        assert "loteo.calle_borde" in {p["campo"] for p in respuesta.json()["problemas"]}
        referencia = cliente.get("/api/parametros/referencia").json()["valores"]["loteo"]
        assert referencia["calle_borde"] == "por_lado"
    finally:
        command.upgrade(alembic_cfg, "head")
        restaurar_identidades()


def test_la_0010_completa_el_tipo_y_deja_el_trigger_habilitado(alembic_cfg, restaurar_identidades, cliente, crear_proyecto, generar):
    """El tipo de cada versión que ya existía se deduce exacto de lo guardado: sin origen es
    «generada», con sector fijado «recalculada», y con origen y sin sector «copia» (D62). Para
    completarlo, la 0010 deshabilita el trigger de inmutabilidad y lo vuelve a habilitar: después
    sigue rechazando cualquier modificación (D28)."""
    v1 = generar(crear_proyecto()["id_proyecto"])["version"]["id_version"]
    v2 = cliente.post(f"/api/versiones/{v1}/recalculos", json=cuerpo_recalculo(["M2"]))
    assert v2.status_code == 201, v2.text
    v3 = cliente.post(f"/api/versiones/{v1}/copias")
    assert v3.status_code == 201, v3.text
    ids = (v1, v2.json()["version"]["id_version"], v3.json()["version"]["id_version"])
    command.downgrade(alembic_cfg, "0009")
    try:
        command.upgrade(alembic_cfg, "0010")
        with engine.connect() as conexion:
            tipos = [
                conexion.scalar(text("SELECT tipo FROM version_alternativa WHERE id_version = :v"), {"v": v})
                for v in ids
            ]
            habilitado = conexion.scalar(
                text("SELECT tgenabled FROM pg_trigger WHERE tgname = 'version_alternativa_inmutable'")
            )
        assert tipos == ["generada", "recalculada", "copia"]
        # «O»: habilitado (origin). «D» sería deshabilitado.
        assert habilitado == "O"
        with engine.connect() as conexion, pytest.raises(DBAPIError, match="inmutable"):
            conexion.execute(text("UPDATE version_alternativa SET tipo = 'copia' WHERE id_version = :v"), {"v": ids[0]})
    finally:
        command.upgrade(alembic_cfg, "head")
        restaurar_identidades()


def test_si_la_0010_falla_a_mitad_el_trigger_queda_habilitado(alembic_cfg, restaurar_identidades, monkeypatch):
    """Lo validado de la sesión 12 (D72): el trigger se deshabilita y se vuelve a habilitar dentro de la
    transacción de la migración. Si algo falla entre el DISABLE y el ENABLE, el rollback lo deja
    habilitado, y la columna sin crear: no hay un estado intermedio con el trigger apagado."""
    from alembic import op

    original = op.execute

    def falla_en_el_update(sql, *args, **kwargs):
        if str(sql).startswith("UPDATE version_alternativa"):
            raise RuntimeError("falla simulada entre el DISABLE y el ENABLE")
        return original(sql, *args, **kwargs)

    command.downgrade(alembic_cfg, "0009")
    try:
        monkeypatch.setattr(op, "execute", falla_en_el_update)
        with pytest.raises(RuntimeError, match="falla simulada"):
            command.upgrade(alembic_cfg, "0010")
        monkeypatch.undo()
        with engine.connect() as conexion:
            assert conexion.scalar(text("SELECT version_num FROM alembic_version")) == "0009"
            assert conexion.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_name = 'version_alternativa' AND column_name = 'tipo'"
                )
            ) == 0
            assert conexion.scalar(
                text("SELECT tgenabled FROM pg_trigger WHERE tgname = 'version_alternativa_inmutable'")
            ) == "O"
    finally:
        monkeypatch.undo()
        command.upgrade(alembic_cfg, "head")
        restaurar_identidades()


# Las tablas con un trigger de inmutabilidad (RNF04, D28): lo que forma una versión, la copia de sus áreas
# y, desde la 0012, las observaciones (solo cambian de estado), sus respuestas y los enlaces a versiones.
INMUTABLES = {
    "version_alternativa",
    "nodo_red",
    "tramo_circulacion",
    "manzana",
    "celda",
    "incumplimiento",
    "area_reservada_version",
    "observacion",
    "respuesta_observacion",
    "enlace_version",
}


def test_despues_de_migrar_todos_los_triggers_de_inmutabilidad_estan_habilitados():
    """Después de `head`, cada tabla de `INMUTABLES` tiene sus dos triggers (fila y TRUNCATE), y todos
    habilitados: ninguna migración dejó uno apagado (D28, D72)."""
    with engine.connect() as conexion:
        filas = conexion.execute(
            text(
                "SELECT c.relname, t.tgname, t.tgenabled FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                "WHERE NOT t.tgisinternal AND t.tgname LIKE '%\\_inmutable%'"
            )
        ).all()
    assert {tabla for tabla, _, _ in filas} == INMUTABLES
    assert sorted(nombre for _, nombre, _ in filas) == sorted(
        nombre for tabla in INMUTABLES for nombre in (f"{tabla}_inmutable", f"{tabla}_inmutable_truncate")
    )
    assert {nombre: habilitado for _, nombre, habilitado in filas if habilitado != "O"} == {}


def test_los_modelos_coinciden_con_las_migraciones():
    """El esquema sale de las migraciones (escritas a mano); los modelos tienen que decir lo
    mismo, o el ORM leería columnas que no existen (D07, D28)."""
    with engine.connect() as conexion:
        contexto = MigrationContext.configure(
            conexion, opts={"compare_type": True, "include_object": incluir_objeto}
        )
        diferencias = compare_metadata(contexto, Base.metadata)
    assert diferencias == []
