"""Alta y lista de proyectos: el cliente obligatorio (CU03), los parámetros iniciales (CU05) y la
estrategia que la pantalla sugiere (p. 43, paso 1)."""

from shapely import LineString, box
from shapely.affinity import rotate

from tests.datos_referencia import CLIENTE, cuerpo_proyecto, en_4326_junto_al_de_referencia


def problemas(respuesta) -> dict[str, str]:
    return {p["campo"]: p["mensaje"] for p in respuesta.json()["problemas"]}


def test_el_proyecto_lleva_su_cliente(crear_proyecto, id_cliente):
    proyecto = crear_proyecto()
    assert proyecto["cliente"]["id_cliente"] == id_cliente
    assert proyecto["cliente"]["razon_social"] == CLIENTE


def test_sin_cliente_o_con_uno_que_no_existe_da_422(cliente, nuevo_codigo, id_cliente):
    cuerpo = cuerpo_proyecto(nuevo_codigo(), id_cliente)
    del cuerpo["id_cliente"]
    respuesta = cliente.post("/api/proyectos", json=cuerpo)
    assert respuesta.status_code == 422
    assert problemas(respuesta) == {"id_cliente": "Falta este dato."}

    respuesta = cliente.post("/api/proyectos", json=cuerpo_proyecto(nuevo_codigo(), 999999))
    assert respuesta.status_code == 422
    assert respuesta.json()["causa"] == "El cliente no existe."
    assert problemas(respuesta) == {"id_cliente": "No existe el cliente 999999."}


def test_la_lista_va_del_mas_nuevo_al_mas_viejo_y_cuenta_las_alternativas(cliente, crear_proyecto, generar):
    viejo, nuevo = crear_proyecto(), crear_proyecto()
    generar(viejo["id_proyecto"])
    lista = cliente.get("/api/proyectos").json()
    ids = [p["id_proyecto"] for p in lista]
    assert ids.index(nuevo["id_proyecto"]) < ids.index(viejo["id_proyecto"])
    fila = lista[ids.index(viejo["id_proyecto"])]
    assert fila["codigo"] == viejo["codigo"]
    assert fila["cliente"]["razon_social"] == CLIENTE
    assert fila["estado"] == "listo_para_generar"
    assert fila["superficie_m2"] == viejo["terreno"]["properties"]["superficie_m2"]
    assert fila["cantidad_alternativas"] == 1
    assert lista[ids.index(nuevo["id_proyecto"])]["cantidad_alternativas"] == 0


def test_la_estrategia_sugerida_sigue_el_lado_mayor_del_terreno(crear_proyecto):
    # El de referencia está rotado 20°: la grilla sugerida es la de su caso (D27).
    assert crear_proyecto()["estrategia_sugerida"] == {"patron_red": "grilla", "orientacion_grados": 20.0, "semilla": 1042}

    girado = rotate(box(-200, -100, 200, 100), 110, origin=(0, 0))
    acceso = LineString(girado.exterior.coords[:2]).interpolate(0.5, normalized=True)
    proyecto = crear_proyecto(
        terreno=en_4326_junto_al_de_referencia(girado), accesos=[en_4326_junto_al_de_referencia(acceso)]
    )
    assert proyecto["estrategia_sugerida"]["orientacion_grados"] == 110.0


def test_el_alta_puede_traer_sus_propios_parametros(cliente, crear_proyecto):
    valores = cliente.get("/api/parametros/referencia").json()["valores"]
    valores["loteo"] |= {"frente_minimo_m": 12, "frente_objetivo_m": 15}
    proyecto = crear_proyecto(parametros=valores)
    parametros = proyecto["parametros"]
    assert (parametros["version"], parametros["vigente"]) == (1, True)
    assert (parametros["loteo"]["frente_minimo_m"], parametros["loteo"]["frente_objetivo_m"]) == (12, 15)


def test_un_alta_con_parametros_incoherentes_da_422_y_no_registra_nada(cliente, nuevo_codigo, id_cliente):
    valores = cliente.get("/api/parametros/referencia").json()["valores"]
    valores["loteo"]["superficie_minima_m2"] = 700  # más que la máxima, 600 (CU05, 3.a)
    codigo = nuevo_codigo()
    respuesta = cliente.post("/api/proyectos", json=cuerpo_proyecto(codigo, id_cliente, parametros=valores))
    assert respuesta.status_code == 422
    assert respuesta.json()["causa"] == "Los parámetros no son coherentes."
    assert problemas(respuesta) == {
        "parametros.loteo.superficie_minima_m2": "No puede ser mayor que la superficie máxima."
    }
    assert codigo not in [p["codigo"] for p in cliente.get("/api/proyectos").json()]
