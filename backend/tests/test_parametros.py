"""Parámetros (CU05; D36): los valores por defecto los sirve la API desde el motor, con su
fuente, y cada configuración es una versión nueva que valida el motor."""

from dataclasses import fields

import pytest
from motor_trazados.valores_referencia import A_VALIDAR, FUENTES, JERARQUIAS_REFERENCIA, PARAMETROS_LOTEO_REFERENCIA
from sqlalchemy import select

from app.models import ConjuntoParametros
from app.services.parametros import CAMPOS_ER


def problemas(respuesta) -> dict[str, str]:
    return {p["campo"]: p["mensaje"] for p in respuesta.json()["problemas"]}


def valor(valores: dict, campo: str):
    """'loteo.frente_minimo_m' → valores['loteo']['frente_minimo_m']."""
    for parte in campo.split("."):
        valores = valores[parte]
    return valores


@pytest.fixture
def referencia(cliente) -> dict:
    respuesta = cliente.get("/api/parametros/referencia")
    assert respuesta.status_code == 200
    return respuesta.json()


def test_los_valores_por_defecto_son_los_del_motor(referencia):
    assert referencia["tipo"] == "loteo"
    valores = referencia["valores"]
    for campo in fields(PARAMETROS_LOTEO_REFERENCIA):
        assert valor(valores, CAMPOS_ER[campo.name]) == getattr(PARAMETROS_LOTEO_REFERENCIA, campo.name), campo.name
    assert [(j["nombre"], j["orden"], j["ancho_calzada_m"], j["ancho_vereda_m"], j["radio_ochava_m"]) for j in valores["jerarquias"]] == [
        (j.nombre, j.orden, j.ancho_calzada, j.ancho_vereda, j.radio_ochava) for j in JERARQUIAS_REFERENCIA
    ]


def test_cada_valor_tiene_su_fuente_o_dice_a_validar(referencia):
    fuentes = referencia["fuentes"]
    esperados = {CAMPOS_ER[c.name] for c in fields(PARAMETROS_LOTEO_REFERENCIA)} | {
        "criterio_prioritario",
        "tolerancia_pct",
        "jerarquias.ancho_calzada_m",
        "jerarquias.ancho_vereda_m",
        "jerarquias.radio_ochava_m",
    }
    assert esperados <= fuentes.keys()
    assert all(f["texto"] and not f["texto"].startswith(A_VALIDAR) for f in fuentes.values())
    # Lo que el motor marca «a validar» (D23), y nada más.
    marcados = {campo for campo, f in fuentes.items() if f["a_validar"]}
    assert marcados == {
        "loteo.fondo_minimo_m",
        "loteo.relacion_fondo_frente_max",
        "jerarquias.radio_ochava_m",
        # Los umbrales del espacio verde (D41) y el criterio de forma del lote (D43).
        "loteo.superficie_minima_verde_m2",
        "loteo.ancho_minimo_verde_m",
        "loteo.ancho_minimo_lote_m",
        "loteo.factor_union_maximo",
    }
    assert sum(texto.startswith(A_VALIDAR) for texto in FUENTES.values()) == len(marcados)
    assert "Ley 4146, art. 9" in fuentes["loteo.frente_minimo_m"]["texto"]


def test_el_criterio_del_asignador_se_marca_como_criterio_de_diseno(referencia):
    """El autor lo pidió así (D46): el criterio del asignador no es una norma. Las normas
    verificadas (el art. 12 de la Ley 4146 y los arts. 48 y 54 de la Ord. 8060) no llevan la marca.
    Desde el motor 0.7.0 el criterio de referencia es «más cercanía» (D51)."""
    fuentes = referencia["fuentes"]
    assert referencia["valores"]["loteo"]["criterio_espacio_verde"] == "cercania"
    criterio = fuentes["loteo.criterio_espacio_verde"]
    assert criterio["criterio_diseno"] and not criterio["a_validar"]
    assert fuentes["loteo.superficie_maxima_m2"]["criterio_diseno"]
    for campo in (
        "loteo.frente_minimo_m",
        "loteo.porcentaje_minimo_avenidas",
        "loteo.ancho_minimo_avenida_m",
        "loteo.ancho_minimo_calle_m",
        "loteo.ancho_minimo_calzada_m",
        "loteo.porcentaje_incremento_esquina",
        "loteo.lado_minimo_manzana_m",
        "loteo.lado_maximo_manzana_m",
        "loteo.lado_maximo_sin_pasaje_m",
    ):
        assert not fuentes[campo]["criterio_diseno"], campo
    assert "Ley 4146, art. 12" in fuentes["loteo.porcentaje_minimo_avenidas"]["texto"]
    assert "Ord. 8060, art. 54" in fuentes["loteo.porcentaje_incremento_esquina"]["texto"]
    for campo in ("loteo.lado_minimo_manzana_m", "loteo.lado_maximo_manzana_m", "loteo.lado_maximo_sin_pasaje_m"):
        assert "Ord. 8060, art. 48" in fuentes[campo]["texto"], campo
    valores = referencia["valores"]["loteo"]
    assert (valores["lado_minimo_manzana_m"], valores["lado_maximo_manzana_m"], valores["lado_maximo_sin_pasaje_m"]) == (
        42,
        250,
        200,
    )


def test_el_criterio_del_asignador_es_uno_de_los_dos(cliente, crear_proyecto, referencia):
    id_proyecto = crear_proyecto()["id_proyecto"]
    valores = referencia["valores"]
    valores["loteo"]["criterio_espacio_verde"] = "belleza"
    respuesta = cliente.post(f"/api/proyectos/{id_proyecto}/parametros", json=valores)
    assert respuesta.status_code == 422
    assert problemas(respuesta) == {
        "loteo.criterio_espacio_verde": "Tiene que ser uno de estos valores: 'menos_lotes' o 'cercania'."
    }


def test_con_menos_lotes_se_genera_con_ese_criterio(cliente, crear_proyecto, generar, referencia):
    """El mismo terreno con los dos criterios (D46, D51): la A con el de referencia, «más cercanía»,
    y la B con «menos lotes perdidos». Lo guardado se compara con el motor corrido aparte: «menos
    lotes» no pierde más lotes, y «cercanía» deja los lotes a la misma distancia del verde o más
    cerca."""
    from dataclasses import replace

    import motor_trazados as mt
    from motor_trazados.referencia import solicitud_referencia

    id_proyecto = crear_proyecto()["id_proyecto"]
    cercania = generar(id_proyecto)
    valores = referencia["valores"]
    valores["loteo"]["criterio_espacio_verde"] = "menos_lotes"
    assert cliente.post(f"/api/proyectos/{id_proyecto}/parametros", json=valores).status_code == 201
    menos = generar(id_proyecto)
    s = solicitud_referencia()
    for alternativa, criterio in ((menos, mt.CriterioEspacioVerde.MENOS_LOTES), (cercania, mt.CriterioEspacioVerde.CERCANIA)):
        motor = mt.MotorGeneracion().generar(replace(s, parametros=replace(s.parametros, criterio_espacio_verde=criterio)))
        indicadores = alternativa["version"]["indicadores"]
        assert indicadores["cantidad_celdas"] == motor.indicadores.cantidad_celdas, criterio
        assert indicadores["distancia_media_verde_m"] == pytest.approx(motor.indicadores.distancia_media_verde, abs=0.005)
    a, b = cercania["version"]["indicadores"], menos["version"]["indicadores"]
    assert b["cantidad_celdas"] >= a["cantidad_celdas"]
    assert a["distancia_media_verde_m"] <= b["distancia_media_verde_m"]


def test_sin_avenidas_todas_las_calles_son_locales(cliente, crear_proyecto, generar, referencia):
    """La casilla «Exigir avenidas» desmarcada (D85) es el porcentaje del art. 12 en 0: se guarda como una
    versión nueva, la colectora queda guardada pero fuera de uso, y la alternativa sale sin avenidas, sin
    incumplimientos de calle y con menos circulación. Lo guardado se compara con el motor corrido aparte."""
    from dataclasses import replace

    import motor_trazados as mt
    from motor_trazados.referencia import solicitud_referencia

    id_proyecto = crear_proyecto()["id_proyecto"]
    con_avenidas = generar(id_proyecto)["version"]
    valores = referencia["valores"]
    valores["loteo"]["porcentaje_minimo_avenidas"] = 0
    # Lo leído (con `en_uso` y el ancho total) se puede volver a mandar tal cual.
    guardado = cliente.post(f"/api/proyectos/{id_proyecto}/parametros", json=valores)
    assert guardado.status_code == 201, guardado.text
    assert [(j["nombre"], j["en_uso"]) for j in guardado.json()["jerarquias"]] == [
        (j.nombre, j is JERARQUIAS_REFERENCIA[-1]) for j in JERARQUIAS_REFERENCIA
    ]
    leidos = cliente.get(f"/api/proyectos/{id_proyecto}/parametros").json()
    assert [[j["en_uso"] for j in v["jerarquias"]] for v in leidos] == [[False, True], [True, True]]

    sin_avenidas = generar(id_proyecto)["version"]
    indicadores = sin_avenidas["indicadores"]
    s = solicitud_referencia()
    motor = mt.MotorGeneracion().generar(replace(s, parametros=replace(s.parametros, porcentaje_minimo_avenidas=0.0)))
    assert indicadores["cantidad_celdas"] == motor.indicadores.cantidad_celdas
    assert indicadores["porcentaje_circulacion"] == pytest.approx(motor.indicadores.porcentaje_circulacion, abs=0.005)
    assert indicadores["porcentaje_avenidas"] == 0
    assert indicadores["porcentaje_circulacion"] < con_avenidas["indicadores"]["porcentaje_circulacion"]
    verificaciones = {v["tipo"]: v for v in sin_avenidas["verificaciones"]}
    assert verificaciones["ancho_calle"]["cumple"] and verificaciones["proporcion_avenidas"]["cumple"]
    assert "se aparta de la Ley 4146, art. 12" in verificaciones["proporcion_avenidas"]["detalle"]


def test_la_calle_de_borde_por_lado_es_el_valor_de_referencia_y_un_criterio_de_diseno(referencia):
    """La norma pide el lado menor de la manzana (Ord. 8060, art. 48), no una calle perimetral (D86)."""
    assert referencia["valores"]["loteo"]["calle_borde"] == "por_lado"
    fuente = referencia["fuentes"]["loteo.calle_borde"]
    assert fuente["criterio_diseno"] and not fuente["a_validar"]
    assert "Ord. 8060, art. 48" in fuente["texto"]


def test_la_calle_de_borde_es_una_de_las_dos(cliente, crear_proyecto, referencia):
    id_proyecto = crear_proyecto()["id_proyecto"]
    valores = referencia["valores"]
    valores["loteo"]["calle_borde"] = "ninguna"
    respuesta = cliente.post(f"/api/proyectos/{id_proyecto}/parametros", json=valores)
    assert respuesta.status_code == 422
    assert problemas(respuesta) == {
        "loteo.calle_borde": "Tiene que ser uno de estos valores: 'contorno' o 'por_lado'."
    }


def test_con_la_calle_de_borde_en_todo_el_contorno_se_genera_como_antes(cliente, crear_proyecto, generar, referencia):
    """La casilla «Calle de borde en todo el contorno» (D86) es una versión nueva del conjunto: en el
    irregular, la A sale por lado (127 lotes) y la B como hasta el motor 0.10.x (116). Lo guardado se
    compara con el motor corrido aparte, y la comparación dice que las separa la calle de borde."""
    from dataclasses import replace

    import motor_trazados as mt
    from motor_trazados.referencia import solicitud_caso

    id_proyecto = crear_proyecto(caso="irregular")["id_proyecto"]
    por_lado = generar(id_proyecto)
    valores = referencia["valores"]
    valores["loteo"]["calle_borde"] = "contorno"
    guardado = cliente.post(f"/api/proyectos/{id_proyecto}/parametros", json=valores)
    assert guardado.status_code == 201, guardado.text
    assert (guardado.json()["version"], guardado.json()["loteo"]["calle_borde"]) == (2, "contorno")
    contorno = generar(id_proyecto)
    s = solicitud_caso("irregular")
    for alternativa, calle_borde in ((por_lado, mt.CalleBorde.POR_LADO), (contorno, mt.CalleBorde.CONTORNO)):
        motor = mt.MotorGeneracion().generar(replace(s, parametros=replace(s.parametros, calle_borde=calle_borde)))
        indicadores = alternativa["version"]["indicadores"]
        assert indicadores["cantidad_celdas"] == motor.indicadores.cantidad_celdas == len(motor.lotes), calle_borde
        assert indicadores["porcentaje_circulacion"] == pytest.approx(motor.indicadores.porcentaje_circulacion, abs=0.005)
    assert (por_lado["version"]["indicadores"]["cantidad_celdas"], contorno["version"]["indicadores"]["cantidad_celdas"]) == (
        127,
        116,
    )
    comparacion = cliente.get(
        f"/api/proyectos/{id_proyecto}/comparacion",
        params=[("alternativas", por_lado["id_alternativa"]), ("alternativas", contorno["id_alternativa"])],
    )
    assert comparacion.status_code == 200, comparacion.text
    diferencias = {d["campo"]: d["valores"] for d in comparacion.json()["diferencias"]}
    assert diferencias["loteo.calle_borde"] == ["por_lado", "contorno"]


def test_configurar_crea_una_version_nueva_y_vigente(cliente, crear_proyecto, generar, referencia, db):
    proyecto = crear_proyecto()
    id_proyecto = proyecto["id_proyecto"]
    primera = generar(id_proyecto)

    valores = referencia["valores"]
    valores["loteo"]["frente_objetivo_m"] = 15
    respuesta = cliente.post(f"/api/proyectos/{id_proyecto}/parametros", json=valores)
    assert respuesta.status_code == 201
    nuevo = respuesta.json()
    assert (nuevo["version"], nuevo["vigente"], nuevo["loteo"]["frente_objetivo_m"]) == (2, True, 15)
    assert cliente.get(f"/api/proyectos/{id_proyecto}").json()["parametros"] == nuevo

    versiones = db.execute(
        select(ConjuntoParametros.version, ConjuntoParametros.vigente)
        .where(ConjuntoParametros.id_proyecto == id_proyecto)
        .order_by(ConjuntoParametros.version)
    ).all()
    assert [tuple(v) for v in versiones] == [(1, False), (2, True)]
    # La alternativa que ya estaba conserva la v1; la siguiente se genera con la v2 (p. 49).
    segunda = generar(id_proyecto)
    assert segunda["version"]["version_parametros"] == 2
    leida = cliente.get(f"/api/alternativas/{primera['id_alternativa']}").json()
    assert leida["version"]["version_parametros"] == 1


@pytest.mark.parametrize(
    ("cambiar", "esperado"),
    [
        (
            lambda v: v["loteo"].update(superficie_minima_m2=700),
            {"loteo.superficie_minima_m2": "No puede ser mayor que la superficie máxima."},
        ),
        (
            lambda v: v["loteo"].update(frente_objetivo_m=8),
            {"loteo.frente_objetivo_m": "No puede ser menor que el frente mínimo."},
        ),
        (
            lambda v: v["jerarquias"][1].update(ancho_calzada_m=0),
            {"jerarquias[1].ancho_calzada_m": "Tiene que ser mayor que 0."},
        ),
        (
            lambda v: (v.update(porcentaje_espacio_verde=60), v["loteo"].update(porcentaje_equipamiento=50)),
            {"porcentaje_espacio_verde": "Las cesiones suman más del 100 %."},
        ),
        (
            lambda v: v["jerarquias"][1].update(orden=1),
            {"jerarquias": "Dos jerarquías no pueden tener el mismo orden."},
        ),
        # El criterio de forma (D43).
        (
            lambda v: v["loteo"].update(ancho_minimo_lote_m=12),
            {"loteo.ancho_minimo_lote_m": "No puede ser mayor que el frente mínimo."},
        ),
        (
            lambda v: v["loteo"].update(factor_union_maximo=0.8),
            {
                "loteo.factor_union_maximo": "Tiene que ser al menos 1: con menos, ninguna fracción se puede "
                "unir a su lote vecino."
            },
        ),
        # Ley 4146, art. 12 (D48).
        (
            lambda v: v["loteo"].update(ancho_minimo_calzada_m=14),
            {
                "loteo.ancho_minimo_calzada_m": "No puede ser mayor que el ancho mínimo de la calle.",
                # Y las calzadas de las dos jerarquías no la alcanzan (D78).
                "jerarquias[0].ancho_calzada_m": "Mide menos que la calzada mínima de 14,00 m (Ley 4146, art. 12).",
                "jerarquias[1].ancho_calzada_m": "Mide menos que la calzada mínima de 14,00 m (Ley 4146, art. 12).",
            },
        ),
        (
            lambda v: v["loteo"].update(porcentaje_minimo_avenidas=120),
            {"loteo.porcentaje_minimo_avenidas": "Tiene que estar entre 0 y 100."},
        ),
    ],
)
def test_valores_incoherentes_dan_422_con_el_campo_del_er(cliente, crear_proyecto, referencia, db, cambiar, esperado):
    """Las reglas son las del motor (SolicitudGeneracion.validar); la API solo traduce el campo."""
    id_proyecto = crear_proyecto()["id_proyecto"]
    valores = referencia["valores"]
    cambiar(valores)
    respuesta = cliente.post(f"/api/proyectos/{id_proyecto}/parametros", json=valores)
    assert respuesta.status_code == 422
    assert respuesta.json()["causa"] == "Los parámetros no son coherentes."
    assert problemas(respuesta) == esperado
    versiones = db.execute(
        select(ConjuntoParametros.version, ConjuntoParametros.vigente).where(ConjuntoParametros.id_proyecto == id_proyecto)
    ).all()
    assert [tuple(v) for v in versiones] == [(1, True)]  # no se guardó nada


def test_los_limites_de_las_columnas_los_pone_la_api(cliente, crear_proyecto, referencia):
    id_proyecto = crear_proyecto()["id_proyecto"]
    valores = referencia["valores"]
    valores["loteo"]["frente_minimo_m"] = 10.125
    valores["criterio_prioritario"] = "belleza"
    respuesta = cliente.post(f"/api/proyectos/{id_proyecto}/parametros", json=valores)
    assert respuesta.status_code == 422
    assert problemas(respuesta) == {
        "loteo.frente_minimo_m": "Admite hasta 2 decimales.",
        "criterio_prioritario": "Tiene que ser uno de estos valores: 'superficie_aprovechable', "
        "'cantidad_celdas' o 'longitud_red'.",
    }


def test_un_conjunto_nuevo_lleva_los_parametros_de_forma(cliente, crear_proyecto, referencia):
    """Un conjunto nuevo los manda siempre: solo los conjuntos anteriores a la 0005 y a la 0006 los
    tienen en NULL (D45)."""
    id_proyecto = crear_proyecto()["id_proyecto"]
    valores = referencia["valores"]
    del valores["loteo"]["ancho_minimo_lote_m"]
    valores["loteo"]["factor_union_maximo"] = None
    del valores["loteo"]["criterio_espacio_verde"]
    valores["loteo"]["porcentaje_minimo_avenidas"] = None
    respuesta = cliente.post(f"/api/proyectos/{id_proyecto}/parametros", json=valores)
    assert respuesta.status_code == 422
    assert set(problemas(respuesta)) == {
        "loteo.ancho_minimo_lote_m",
        "loteo.factor_union_maximo",
        "loteo.criterio_espacio_verde",
        "loteo.porcentaje_minimo_avenidas",
    }


def test_generar_con_un_conjunto_anterior_al_motor_da_422_con_los_campos(cliente, crear_proyecto, db):
    """Un conjunto con un parámetro en NULL («no aplica», D45) no se completa en silencio: generar
    da 422 con los campos que faltan, y configurar los parámetros lo resuelve."""
    from sqlalchemy import text

    id_proyecto = crear_proyecto()["id_proyecto"]
    # Como queda un conjunto anterior a la 0005 (parametros_loteo no tiene trigger).
    db.execute(
        text(
            "UPDATE parametros_loteo SET ancho_minimo_lote_m = NULL, factor_union_maximo = NULL "
            "WHERE id_conjunto = (SELECT id_conjunto FROM conjunto_parametros WHERE id_proyecto = :p)"
        ),
        {"p": id_proyecto},
    )
    db.commit()
    # El proyecto los muestra en NULL: el portal dice «no aplica».
    vigente = cliente.get(f"/api/proyectos/{id_proyecto}").json()["parametros"]
    assert vigente["loteo"]["ancho_minimo_lote_m"] is None
    assert vigente["loteo"]["factor_union_maximo"] is None
    estrategia = {"estrategia": {"patron_red": "grilla", "orientacion_grados": 20, "semilla": 1042}}
    respuesta = cliente.post(f"/api/proyectos/{id_proyecto}/alternativas", json=estrategia)
    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert "anterior al motor" in cuerpo["causa"] and "CU05" in cuerpo["sugerencia"]
    assert set(problemas(respuesta)) == {"loteo.ancho_minimo_lote_m", "loteo.factor_union_maximo"}


def test_configurar_un_proyecto_que_no_existe_da_404(cliente, referencia):
    respuesta = cliente.post("/api/proyectos/999999/parametros", json=referencia["valores"])
    assert respuesta.status_code == 404
