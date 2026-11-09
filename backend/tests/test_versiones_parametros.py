"""Las versiones del conjunto de parámetros de un proyecto (figura 16, «Versiones del conjunto»; D82).

De la última a la primera, cada una con las alternativas cuya versión vigente se generó con ella.
"""


def configurar(cliente, id_proyecto: int, **loteo) -> int:
    valores = cliente.get("/api/parametros/referencia").json()["valores"]
    valores["loteo"] |= loteo
    respuesta = cliente.post(f"/api/proyectos/{id_proyecto}/parametros", json=valores)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["version"]


def test_cada_version_con_las_alternativas_que_la_usan(cliente, crear_proyecto, generar):
    id_proyecto = crear_proyecto(caso="irregular")["id_proyecto"]
    generar(id_proyecto)
    assert configurar(cliente, id_proyecto, criterio_espacio_verde="menos_lotes") == 2
    generar(id_proyecto)
    generar(id_proyecto, orientacion_grados=110.0)
    assert configurar(cliente, id_proyecto, frente_minimo_m=12) == 3

    respuesta = cliente.get(f"/api/proyectos/{id_proyecto}/parametros")
    assert respuesta.status_code == 200, respuesta.text
    versiones = respuesta.json()
    assert [(v["version"], v["vigente"], v["usada_por"]) for v in versiones] == [
        (3, True, []),
        (2, False, ["B", "C"]),
        (1, False, ["A"]),
    ]
    # Cada una con sus valores, como el GET del proyecto.
    assert versiones[0]["loteo"]["frente_minimo_m"] == 12
    assert versiones[1]["loteo"]["criterio_espacio_verde"] == "menos_lotes"
    proyecto = cliente.get(f"/api/proyectos/{id_proyecto}").json()
    assert {k: v for k, v in versiones[0].items() if k != "usada_por"} == proyecto["parametros"]


def test_un_proyecto_que_no_existe_da_404(cliente):
    respuesta = cliente.get("/api/proyectos/999999/parametros")
    assert respuesta.status_code == 404
