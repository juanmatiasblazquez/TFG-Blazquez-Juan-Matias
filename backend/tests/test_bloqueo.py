"""El bloqueo por intentos fallidos (CU01, 4.b; Seguridad, p. 53; D64, D65), con el reloj simulado:
tras 10 intentos fallidos consecutivos desde una dirección, 30 minutos sin poder iniciar sesión desde
ella. La dirección es la que informa Nginx, y no se esquiva falsificando el encabezado."""

from app.services.acceso import DURACION_BLOQUEO
from tests.identidades import CONTRASENA, desde, iniciar_sesion

MALA = "Mala#Clave1"
# Entre intento e intento: así el límite por minuto (10) no se mezcla con el bloqueo.
PAUSA = 7


def fallar(anonimo, reloj, email, veces, **encabezados):
    for _ in range(veces):
        respuesta = iniciar_sesion(anonimo, email, MALA, **encabezados)
        assert respuesta.status_code == 401, respuesta.text
        reloj.adelantar(seconds=PAUSA)


def test_diez_fallos_consecutivos_bloquean_la_direccion_30_minutos(anonimo, reloj, con_contrasena):
    email, _, _ = con_contrasena()
    direccion = desde("203.0.113.10")
    fallar(anonimo, reloj, email, 9, **direccion)
    # El décimo todavía responde que no coinciden, y deja la dirección bloqueada.
    assert iniciar_sesion(anonimo, email, MALA, **direccion).status_code == 401
    bloqueado = iniciar_sesion(anonimo, email, CONTRASENA, **direccion)
    assert bloqueado.status_code == 429
    assert bloqueado.json()["causa"] == "Se bloqueó el inicio de sesión desde esta dirección por demasiados intentos fallidos."
    # 30 minutos, menos lo que tardó de verdad el pedido.
    assert DURACION_BLOQUEO.total_seconds() - 5 <= int(bloqueado.headers["Retry-After"]) <= DURACION_BLOQUEO.total_seconds()
    # A los 29:59 sigue bloqueada, también con la contraseña correcta.
    reloj.adelantar(minutes=29, seconds=59)
    assert iniciar_sesion(anonimo, email, CONTRASENA, **direccion).status_code == 429
    # A los 30:00 se levanta.
    reloj.adelantar(seconds=1)
    assert iniciar_sesion(anonimo, email, CONTRASENA, **direccion).status_code == 200


def test_cuenta_los_fallos_de_cualquier_cuenta_desde_esa_direccion(anonimo, reloj, con_contrasena):
    """Es por dirección, no por cuenta: probar contraseñas contra varios correos (existan o no) también
    bloquea."""
    email, _, _ = con_contrasena()
    direccion = desde("203.0.113.11")
    for k in range(10):
        correo = email if k % 2 else f"nadie{k}@pruebas.local"
        assert iniciar_sesion(anonimo, correo, MALA, **direccion).status_code == 401
        reloj.adelantar(seconds=PAUSA)
    assert iniciar_sesion(anonimo, email, CONTRASENA, **direccion).status_code == 429


def test_un_ingreso_correcto_vuelve_el_contador_a_cero(anonimo, reloj, con_contrasena):
    email, _, _ = con_contrasena()
    direccion = desde("203.0.113.12")
    fallar(anonimo, reloj, email, 9, **direccion)
    assert iniciar_sesion(anonimo, email, CONTRASENA, **direccion).status_code == 200
    reloj.adelantar(seconds=PAUSA)
    fallar(anonimo, reloj, email, 9, **direccion)
    # 18 fallos, pero nunca 10 seguidos: no está bloqueada.
    assert iniciar_sesion(anonimo, email, CONTRASENA, **direccion).status_code == 200


def test_no_se_esquiva_falsificando_el_encabezado_de_la_direccion(anonimo, reloj, con_contrasena):
    """Lo que el cliente escriba en X-Forwarded-For queda ANTES del valor que agrega Nginx: la API usa
    el último (D64). En el despliegue, además, Nginx pisa el encabezado entero (`api.inc`)."""
    email, _, _ = con_contrasena()
    real = "203.0.113.13"
    for k in range(10):
        falsificado = {"X-Forwarded-For": f"10.0.{k}.1, {real}", "X-Real-IP": f"10.0.{k}.1"}
        assert iniciar_sesion(anonimo, email, MALA, **falsificado).status_code == 401
        reloj.adelantar(seconds=PAUSA)
    otro_disfraz = {"X-Forwarded-For": f"192.0.2.99, {real}", "X-Real-IP": "192.0.2.99"}
    assert iniciar_sesion(anonimo, email, CONTRASENA, **otro_disfraz).status_code == 429
    assert iniciar_sesion(anonimo, email, CONTRASENA, **desde(real)).status_code == 429
    # Otra dirección real no está bloqueada: un atacante no deja afuera a los demás.
    assert iniciar_sesion(anonimo, email, CONTRASENA, **desde("203.0.113.14")).status_code == 200


def test_el_bloqueo_no_corta_las_sesiones_abiertas(anonimo, reloj, con_contrasena):
    """Bloquea el inicio de sesión, no lo que ya está adentro (D65)."""
    email, sesion, _ = con_contrasena()
    direccion = desde("203.0.113.15")
    fallar(anonimo, reloj, email, 10, **direccion)
    assert iniciar_sesion(anonimo, email, CONTRASENA, **direccion).status_code == 429
    assert sesion.get("/api/proyectos", headers=direccion).status_code == 200


def test_el_cambio_de_contrasena_tambien_cuenta(anonimo, reloj, con_contrasena):
    """Verifica una contraseña, así que no sirve para probar contraseñas sin límite."""
    email, sesion, _ = con_contrasena()
    direccion = desde("203.0.113.16")
    for _ in range(10):
        respuesta = sesion.put(
            "/api/sesion/contrasena",
            json={"contrasena_actual": MALA, "contrasena_nueva": "Nueva#Clave1"},
            headers=direccion,
        )
        assert respuesta.status_code == 422
        reloj.adelantar(seconds=PAUSA)
    assert iniciar_sesion(anonimo, email, CONTRASENA, **direccion).status_code == 429


def test_el_director_ve_las_direcciones_bloqueadas_y_las_destraba(cliente, anonimo, reloj, con_contrasena):
    """Lo validado de la sesión 12 (D72): con todo el estudio detrás de la misma dirección pública, diez
    errores de una persona dejan afuera a todos. El director técnico, con su sesión abierta (el bloqueo no
    corta las sesiones), ve las direcciones bloqueadas con el tiempo que les queda y las destraba."""
    email, _, _ = con_contrasena()
    bloqueada, otra = "203.0.113.40", "203.0.113.41"
    fallar(anonimo, reloj, email, 10, **desde(bloqueada))
    fallar(anonimo, reloj, email, 3, **desde(otra))
    reloj.adelantar(minutes=10)
    lista = cliente.get("/api/direcciones-bloqueadas")
    assert lista.status_code == 200, lista.text
    # Solo la bloqueada: la otra tiene fallos, pero no llegó al décimo.
    assert [fila["direccion"] for fila in lista.json()] == [bloqueada]
    fila = lista.json()[0]
    assert fila["intentos_fallidos"] == 10
    # 30 minutos desde el décimo fallo, menos la pausa que le siguió, los tres de la otra y los 10 minutos.
    esperado = DURACION_BLOQUEO.total_seconds() - 4 * PAUSA - 10 * 60
    assert esperado - 5 <= fila["segundos_restantes"] <= esperado
    assert iniciar_sesion(anonimo, email, CONTRASENA, **desde(bloqueada)).status_code == 429
    assert cliente.delete(f"/api/direcciones-bloqueadas/{bloqueada}").status_code == 204
    assert cliente.get("/api/direcciones-bloqueadas").json() == []
    assert iniciar_sesion(anonimo, email, CONTRASENA, **desde(bloqueada)).status_code == 200
    # Destrabar una que no está bloqueada da 404.
    respuesta = cliente.delete(f"/api/direcciones-bloqueadas/{otra}")
    assert respuesta.status_code == 404
    assert "no está bloqueada" in respuesta.json()["causa"]


def test_una_direccion_ipv6_tambien_se_destraba(cliente, anonimo, reloj, con_contrasena):
    email, _, _ = con_contrasena()
    direccion = "2001:db8::7"
    fallar(anonimo, reloj, email, 10, **desde(direccion))
    assert [f["direccion"] for f in cliente.get("/api/direcciones-bloqueadas").json()] == [direccion]
    assert cliente.delete("/api/direcciones-bloqueadas/2001%3Adb8%3A%3A7").status_code == 204
    assert iniciar_sesion(anonimo, email, CONTRASENA, **desde(direccion)).status_code == 200
