"""Clientes: CU03 exige uno por proyecto, y si no está cargado se da de alta primero (D35)."""

import pytest

from app.schemas.cliente import normalizar_cuit

# CUIT con el dígito verificador correcto. Son datos de prueba, en una base que se recrea.
CUIT_A = "20-12345678-6"
CUIT_B = "30-71234567-1"


def problemas(respuesta) -> dict[str, str]:
    return {p["campo"]: p["mensaje"] for p in respuesta.json()["problemas"]}


def test_alta_y_lectura_de_un_cliente(cliente):
    datos = {"razon_social": "Desarrollos del Sur S.A.", "cuit": "20123456786", "email": "obras@sur.com.ar"}
    respuesta = cliente.post("/api/clientes", json=datos)
    assert respuesta.status_code == 201
    creado = respuesta.json()
    # El CUIT se guarda con guiones, como el varchar(13) del ER.
    assert creado | {"id_cliente": 0} == {
        "id_cliente": 0,
        "razon_social": "Desarrollos del Sur S.A.",
        "cuit": CUIT_A,
        "email": "obras@sur.com.ar",
        "telefono": None,
    }
    assert respuesta.headers["location"] == f"/api/clientes/{creado['id_cliente']}"
    assert cliente.get(respuesta.headers["location"]).json() == creado


@pytest.mark.parametrize(
    ("cuit", "mensaje"),
    [
        ("20-12345678-5", "No es un CUIT válido: el dígito verificador no coincide."),
        ("20-1234567-6", "Tiene que tener 11 dígitos, con o sin guiones (NN-NNNNNNNN-N)."),
        ("CUIT", "Tiene que tener 11 dígitos, con o sin guiones (NN-NNNNNNNN-N)."),
    ],
)
def test_un_cuit_invalido_da_422_en_el_campo(cliente, cuit, mensaje):
    respuesta = cliente.post("/api/clientes", json={"razon_social": "Mal cargado", "cuit": cuit})
    assert respuesta.status_code == 422
    assert problemas(respuesta) == {"cuit": mensaje}


def test_el_verificador_10_no_es_valido():
    # 20-00000001-? da 10: a ese DNI se le asigna el prefijo 23, que da otro verificador.
    with pytest.raises(ValueError, match="dígito verificador"):
        normalizar_cuit("20000000010")
    assert normalizar_cuit("20 12.345.678 6") == CUIT_A


def test_un_cuit_repetido_da_409_aunque_se_escriba_distinto(cliente, crear_cliente):
    crear_cliente(razon_social="Primera", cuit=CUIT_B)
    respuesta = cliente.post("/api/clientes", json={"razon_social": "Segunda", "cuit": CUIT_B.replace("-", "")})
    assert respuesta.status_code == 409
    assert respuesta.json()["causa"] == f"Ya existe un cliente con el CUIT {CUIT_B}."
    assert problemas(respuesta) == {"cuit": "Ya está en uso."}


def test_sin_cuit_se_pueden_cargar_varios(crear_cliente):
    uno, otro = crear_cliente(), crear_cliente()
    assert uno["id_cliente"] != otro["id_cliente"]
    assert uno["cuit"] is None and otro["cuit"] is None


def test_los_opcionales_vacios_quedan_nulos_y_el_correo_se_valida(cliente, crear_cliente):
    vacio = crear_cliente(cuit="", email="", telefono=" ")
    assert (vacio["cuit"], vacio["email"], vacio["telefono"]) == (None, None, None)
    respuesta = cliente.post("/api/clientes", json={"razon_social": "Sin correo", "email": "no-es-un-correo"})
    assert respuesta.status_code == 422
    assert problemas(respuesta) == {"email": "No es una dirección de correo válida."}


def test_la_lista_va_por_razon_social(cliente, crear_cliente):
    zeta, alfa = crear_cliente(razon_social="Zeta Loteos"), crear_cliente(razon_social="Alfa Urbanizaciones")
    ids = [c["id_cliente"] for c in cliente.get("/api/clientes").json()]
    assert ids.index(alfa["id_cliente"]) < ids.index(zeta["id_cliente"])


def test_un_cliente_que_no_existe_da_404(cliente):
    respuesta = cliente.get("/api/clientes/999999")
    assert respuesta.status_code == 404
    assert respuesta.json()["causa"] == "No existe el cliente 999999."
