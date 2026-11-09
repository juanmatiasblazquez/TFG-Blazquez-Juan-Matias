"""El límite de solicitudes por minuto al inicio de sesión (Seguridad, p. 53; D65)."""

from app.core import contrasenas
from app.services.acceso import SOLICITUDES_POR_MINUTO
from tests.identidades import CONTRASENA, desde, iniciar_sesion


def test_pasado_el_limite_del_minuto_da_429_hasta_el_minuto_siguiente(anonimo, reloj, con_contrasena):
    email, _, _ = con_contrasena()
    direccion = desde("198.51.100.40")
    # Aun con la contraseña correcta: el límite cuenta solicitudes, no fallos.
    for _ in range(SOLICITUDES_POR_MINUTO):
        assert iniciar_sesion(anonimo, email, CONTRASENA, **direccion).status_code == 200
        reloj.adelantar(seconds=5)
    respuesta = iniciar_sesion(anonimo, email, CONTRASENA, **direccion)
    assert respuesta.status_code == 429
    assert respuesta.json()["causa"] == "Demasiadas solicitudes de inicio de sesión en un minuto."
    # La ventana empezó con la primera: quedan 10 s, menos lo que tardaron de verdad los pedidos (el reloj
    # simulado suma su desfase a la hora real).
    assert 7 <= int(respuesta.headers["Retry-After"]) <= 10
    reloj.adelantar(seconds=10)
    assert iniciar_sesion(anonimo, email, CONTRASENA, **direccion).status_code == 200
    # Otra dirección tiene su propio límite.
    assert iniciar_sesion(anonimo, email, CONTRASENA, **desde("198.51.100.41")).status_code == 200


def test_lo_limitado_no_llega_a_verificar_la_contrasena(anonimo, monkeypatch, con_contrasena):
    """El orden de cada pedido es bloqueo, límite y recién después Argon2: lo rechazado no gasta CPU."""
    email, _, _ = con_contrasena()
    direccion = desde("198.51.100.42")
    for _ in range(SOLICITUDES_POR_MINUTO):
        iniciar_sesion(anonimo, email, CONTRASENA, **direccion)
    verificaciones = []
    original = contrasenas.verificar
    monkeypatch.setattr(contrasenas, "verificar", lambda *a: verificaciones.append(1) or original(*a))
    assert iniciar_sesion(anonimo, email, CONTRASENA, **direccion).status_code == 429
    assert verificaciones == []
