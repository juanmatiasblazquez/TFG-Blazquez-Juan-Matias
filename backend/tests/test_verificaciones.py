"""Las verificaciones de una versión, restricción por restricción (pantalla de la p. 49; D74).

- Con el caso de referencia, las doce restricciones del motor 0.10.0, en el orden del prototipo, todas
  cumplidas y con su detalle.
- El texto de las que fallan y las que no aplican, con versiones armadas a mano: no hace falta que el motor
  produzca un incumplimiento para probar cómo se dice.
"""

from decimal import Decimal
from types import SimpleNamespace

from app.services.verificaciones import RESTRICCIONES, texto, verificaciones_de

ORDEN = [
    "conectividad",
    "sin_frente",
    "frente_minimo",
    "fondo_minimo",
    "superficie_minima",
    "relacion_fondo_frente",
    "ancho_util",
    "cesion_espacio_verde",
    "ancho_calle",
    "proporcion_avenidas",
    "lado_menor_manzana",
    "lado_mayor_manzana",
]


def test_el_caso_de_referencia_cumple_las_doce(cliente, crear_proyecto, generar):
    proyecto = crear_proyecto()
    version = generar(proyecto["id_proyecto"])["version"]
    verificaciones = version["verificaciones"]
    assert [v["tipo"] for v in verificaciones] == ORDEN
    assert all(v["cumple"] and v["cantidad"] == 0 for v in verificaciones)
    detalle = {v["tipo"]: v["detalle"] for v in verificaciones}
    assert detalle["conectividad"] == "Red conexa que incluye los accesos A1 y A2"
    assert detalle["frente_minimo"] == "Todos los lotes tienen al menos 10,00 m de frente (12,00 m en esquina)"
    assert detalle["superficie_minima"] == "Todos los lotes tienen al menos 250,00 m²"
    # Con los indicadores de la versión: la cesión alcanzada contra la exigida.
    cesion = texto(version["indicadores"]["porcentaje_cesion"])
    assert detalle["cesion_espacio_verde"] == f"{cesion} % ≥ 10,00 % requerido"
    # Lo mismo en el GET de la versión.
    leida = cliente.get(f"/api/versiones/{version['id_version']}").json()["version"]
    assert leida["verificaciones"] == verificaciones


def test_el_texto_de_un_numero():
    assert texto(Decimal("1234.5")) == "1.234,50"
    assert texto(10) == "10,00"


# --- Versiones armadas a mano -----------------------------------------------------------------------


def loteo(**cambios) -> SimpleNamespace:
    valores = {
        "frente_minimo_m": Decimal("10"),
        "fondo_minimo_m": Decimal("25"),
        "superficie_minima_m2": Decimal("250"),
        "relacion_fondo_frente_max": Decimal("3"),
        "porcentaje_incremento_esquina": Decimal("20"),
        "ancho_minimo_lote_m": Decimal("10"),
        "porcentaje_minimo_avenidas": Decimal("20"),
        "ancho_minimo_calle_m": Decimal("12"),
        "ancho_minimo_calzada_m": Decimal("6"),
        "lado_minimo_manzana_m": Decimal("42"),
        "lado_maximo_manzana_m": Decimal("250"),
        "lado_maximo_sin_pasaje_m": Decimal("200"),
    }
    return SimpleNamespace(**(valores | cambios))


def version(incumplimientos=(), **cambios) -> SimpleNamespace:
    proyecto = SimpleNamespace(terreno=SimpleNamespace(accesos=[object(), object()]))
    return SimpleNamespace(
        conjunto=SimpleNamespace(loteo=loteo(**cambios), porcentaje_espacio_verde=Decimal("10")),
        incumplimientos=[SimpleNamespace(tipo=t, elemento=e, detalle=d) for t, e, d in incumplimientos],
        alternativa=SimpleNamespace(proyecto=proyecto),
    )


INDICADORES = SimpleNamespace(porcentaje_cesion=10.36, porcentaje_avenidas=20.0)


def por_tipo(v) -> dict:
    return {x.tipo: x for x in verificaciones_de(v, INDICADORES)}


def test_los_lotes_que_fallan_se_cuentan_por_manzana():
    v = version(
        [
            ("superficie_minima", "M3-L07", "superficie 210 m² < 250 m²"),
            ("superficie_minima", "M1-L02", "superficie 230 m² < 250 m²"),
            ("superficie_minima", "M3-L08", "superficie 240 m² < 250 m²"),
        ]
    )
    falla = por_tipo(v)["superficie_minima"]
    assert (falla.cumple, falla.cantidad) == (False, 3)
    assert falla.detalle == "3 lotes con menos de 250,00 m², en las manzanas M1 y M3"
    uno = por_tipo(version([("frente_minimo", "M2-L01", "frente 9 m")]))["frente_minimo"]
    assert uno.detalle == "1 lote con menos de 10,00 m de frente, en la manzana M2"


def test_las_manzanas_que_fallan_se_nombran():
    v = version([("lado_menor_manzana", "M4", "ancho 30 m"), ("lado_menor_manzana", "M10", "ancho 35 m")])
    assert por_tipo(v)["lado_menor_manzana"].detalle == "2 manzanas con menos de 42,00 m de ancho: M4 y M10"


def test_sin_un_detalle_propio_se_usa_el_del_motor():
    v = version([("conectividad", "red", "El acceso A2 no llega a la red.")])
    assert por_tipo(v)["conectividad"].detalle == "El acceso A2 no llega a la red."


def test_sin_avenidas_se_dice_que_el_conjunto_se_aparta_del_art_12():
    """La casilla «Exigir avenidas» desmarcada (D85): no «0,00 % ≥ 0,00 %», sino que no se exigen."""
    sin = por_tipo(version(porcentaje_minimo_avenidas=Decimal("0")))["proporcion_avenidas"]
    assert sin.cumple
    assert sin.detalle == (
        "No se exigen avenidas: todas las calles son locales. El conjunto se aparta de la Ley 4146, art. 12"
    )
    con = por_tipo(version())["proporcion_avenidas"]
    assert con.detalle == "20,00 % de la red ≥ 20,00 % requerido"


def test_lo_que_el_motor_de_la_version_no_verificaba_no_aplica():
    """Un parámetro en NULL: el motor de esa versión no lo usaba (D45), así que no se lista."""
    v = version(ancho_minimo_lote_m=None, porcentaje_minimo_avenidas=None, ancho_minimo_calle_m=None, lado_minimo_manzana_m=None, lado_maximo_manzana_m=None)
    tipos = [x.tipo for x in verificaciones_de(v, INDICADORES)]
    assert tipos == ["conectividad", "sin_frente", "frente_minimo", "fondo_minimo", "superficie_minima", "relacion_fondo_frente", "cesion_espacio_verde"]


def test_un_tipo_que_ya_no_existe_se_lista_con_su_nombre():
    """`superficie_maxima` era un incumplimiento antes del motor 0.6.0 (D47)."""
    v = version([("superficie_maxima", "M1-L01", "superficie 700 m² > 600 m²")])
    ultima = verificaciones_de(v, INDICADORES)[-1]
    assert (ultima.tipo, ultima.nombre, ultima.cumple) == ("superficie_maxima", "Superficie máxima", False)


def test_cada_tipo_del_motor_tiene_su_restriccion():
    from motor_trazados.contrato import TipoIncumplimiento

    assert [r.tipo for r in RESTRICCIONES] == [str(t) for t in TipoIncumplimiento] == ORDEN
