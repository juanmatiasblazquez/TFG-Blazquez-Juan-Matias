"""La política de contraseñas de la p. 53, el hash y la contraseña temporal (RNF02; D66)."""

import pytest

from app.core import contrasenas
from app.core.contrasenas import FALTA_LARGO, FALTA_MAYUSCULA, FALTA_SIMBOLO, NO_ADMITIDO, SOBRA_LARGO
from tests.identidades import CONTRASENA, iniciar_sesion

# Al menos 8 caracteres, una mayúscula y un carácter especial; letras (con la ñ y las tildes), números
# y símbolos básicos.
PASAN = [
    "Abcdefg!",
    "Pruebas#2026",
    "Contraseña1#",
    "ÑANDÚ.corre",
    "Árbol-del-patio",
    "SoloLetras?",
    "A" + "b" * 126 + "!",
    "Z~`^[]{}|\\:;\"'<>,./_",
]
NO_PASAN = [
    ("Abc!", [FALTA_LARGO]),
    ("abcdefgh!", [FALTA_MAYUSCULA]),
    ("Abcdefgh1", [FALTA_SIMBOLO]),
    ("Abcd efg!", [NO_ADMITIDO]),
    ("Abcdefg!€", [NO_ADMITIDO]),
    ("Abcdefg!😀", [NO_ADMITIDO]),
    ("Abcdefg!\t", [NO_ADMITIDO]),
    ("A!" + "b" * 127, [SOBRA_LARGO]),
    ("", [FALTA_LARGO, FALTA_MAYUSCULA, FALTA_SIMBOLO]),
    ("abc", [FALTA_LARGO, FALTA_MAYUSCULA, FALTA_SIMBOLO]),
]


@pytest.mark.parametrize("contrasena", PASAN)
def test_las_que_cumplen_la_politica_pasan(contrasena):
    assert contrasenas.problemas_de(contrasena) == []


@pytest.mark.parametrize(("contrasena", "problemas"), NO_PASAN)
def test_las_que_no_cumplen_dicen_que_les_falta(contrasena, problemas):
    assert contrasenas.problemas_de(contrasena) == problemas


def test_ningun_mensaje_repite_la_contrasena():
    for contrasena, _ in NO_PASAN:
        if contrasena:
            assert all(contrasena not in mensaje for mensaje in contrasenas.problemas_de(contrasena))


def test_las_temporales_cumplen_la_politica_y_no_se_repiten():
    temporales = [contrasenas.generar_temporal() for _ in range(1000)]
    assert all(contrasenas.problemas_de(t) == [] for t in temporales)
    assert all(len(t) == contrasenas.LONGITUD_TEMPORAL for t in temporales)
    # Sin los caracteres que se confunden al dictarla.
    assert not any(c in t for t in temporales for c in "IlO01")
    assert len(set(temporales)) == 1000


def test_el_hash_es_argon2id_y_verifica():
    guardado = contrasenas.hashear("Pruebas#2026")
    assert guardado.startswith("$argon2id$")
    assert "Pruebas#2026" not in guardado
    assert contrasenas.verificar(guardado, "Pruebas#2026")
    assert not contrasenas.verificar(guardado, "pruebas#2026")
    # Dos hashes de la misma contraseña son distintos: cada uno tiene su sal.
    assert contrasenas.hashear("Pruebas#2026") != guardado


def test_sin_hash_o_con_uno_que_no_es_de_argon2_no_verifica():
    """El usuario de desarrollo tenía «!» (D31): no corresponde a ninguna contraseña."""
    assert not contrasenas.verificar(None, "Pruebas#2026")
    assert not contrasenas.verificar("!", "!")
    assert not contrasenas.necesita_rehash("!")


def test_la_api_rechaza_una_nueva_que_no_cumple_y_no_cambia_nada(con_contrasena, anonimo):
    email, cliente, _ = con_contrasena()
    respuesta = cliente.put(
        "/api/sesion/contrasena", json={"contrasena_actual": CONTRASENA, "contrasena_nueva": "sinmayuscula1"}
    )
    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert cuerpo["causa"] == "La contraseña nueva no cumple la política."
    assert cuerpo["problemas"] == [{"campo": "contrasena_nueva", "mensaje": f"{FALTA_MAYUSCULA} {FALTA_SIMBOLO}"}]
    assert iniciar_sesion(anonimo, email).status_code == 200


def test_la_nueva_tiene_que_ser_distinta_y_hay_que_dar_la_actual(con_contrasena):
    _, cliente, _ = con_contrasena()
    igual = cliente.put("/api/sesion/contrasena", json={"contrasena_actual": CONTRASENA, "contrasena_nueva": CONTRASENA})
    assert igual.status_code == 422
    assert igual.json()["problemas"] == [{"campo": "contrasena_nueva", "mensaje": "Tiene que ser distinta de la actual."}]
    mal = cliente.put("/api/sesion/contrasena", json={"contrasena_actual": "Otra#Clave1", "contrasena_nueva": "Nueva#Clave1"})
    assert mal.status_code == 422
    assert mal.json()["problemas"] == [{"campo": "contrasena_actual", "mensaje": "No es la contraseña actual."}]
