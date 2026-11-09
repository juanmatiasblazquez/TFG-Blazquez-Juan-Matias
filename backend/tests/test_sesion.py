"""La sesión (CU01, RF01, RNF02; D63): la cookie, el vencimiento a las 12 h, el cierre, y que
desactivar o cambiar el rol corten enseguida porque se leen de la base en cada operación."""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.permisos import Funcion
from app.main import crear_app
from tests.identidades import CONTRASENA, USUARIOS, iniciar_sesion

DIRECTOR = USUARIOS["director_tecnico"][0]


def test_iniciar_sesion_da_una_cookie_httponly_y_la_sesion(anonimo):
    respuesta = iniciar_sesion(anonimo, DIRECTOR)
    assert respuesta.status_code == 200, respuesta.text
    cookie = respuesta.headers["set-cookie"]
    assert cookie.startswith("trazados_sesion=")
    for atributo in ("HttpOnly", "SameSite=strict", "Path=/api", "Max-Age=43200"):
        assert atributo in cookie, atributo
    # En desarrollo, sin Secure: el portal de desarrollo es HTTP.
    assert "Secure" not in cookie
    cuerpo = respuesta.json()
    assert cuerpo["usuario"]["email"] == DIRECTOR
    assert cuerpo["usuario"]["rol"] == "director_tecnico"
    assert cuerpo["permisos"] == [str(f) for f in Funcion]
    assert cuerpo["debe_cambiar_contrasena"] is False
    assert 43190 < cuerpo["segundos_restantes"] <= 43200
    # El token no viaja en el cuerpo: solo en la cookie.
    token = anonimo.cookies["trazados_sesion"]
    assert token not in respuesta.text
    assert anonimo.get("/api/sesion").json()["usuario"]["email"] == DIRECTOR


def test_el_correo_se_escribe_como_sea(anonimo):
    assert iniciar_sesion(anonimo, f"  {DIRECTOR.upper()} ").status_code == 200


def test_en_produccion_la_cookie_es_secure():
    produccion = TestClient(
        crear_app(Settings(app_env="prod", db_password="una-clave-propia-y-larga")), base_url="https://testserver"
    )
    respuesta = iniciar_sesion(produccion, DIRECTOR)
    assert respuesta.status_code == 200, respuesta.text
    assert "Secure" in respuesta.headers["set-cookie"]
    assert produccion.get("/api/proyectos").status_code == 200


def test_sin_sesion_o_con_un_token_inventado_da_401(anonimo):
    respuesta = anonimo.get("/api/proyectos")
    assert respuesta.status_code == 401
    assert respuesta.json()["causa"] == "Iniciá sesión para continuar."
    anonimo.cookies.set("trazados_sesion", "inventado", domain="testserver.local", path="/api")
    respuesta = anonimo.get("/api/proyectos")
    assert respuesta.status_code == 401
    assert respuesta.json()["causa"] == "Tu sesión venció o ya no es válida."


def test_cerrar_sesion_invalida_el_token_aunque_se_lo_vuelva_a_mandar(anonimo):
    assert iniciar_sesion(anonimo, DIRECTOR).status_code == 200
    token = anonimo.cookies["trazados_sesion"]
    respuesta = anonimo.delete("/api/sesion")
    assert respuesta.status_code == 204
    assert 'trazados_sesion=""' in respuesta.headers["set-cookie"]
    assert anonimo.get("/api/sesion").status_code == 401
    otro = TestClient(anonimo.app)
    otro.cookies.set("trazados_sesion", token, domain="testserver.local", path="/api")
    assert otro.get("/api/sesion").status_code == 401
    # Cerrar sesión sin sesión también se puede.
    assert otro.delete("/api/sesion").status_code == 204


def test_la_sesion_vence_a_las_12_horas(anonimo, reloj):
    assert iniciar_sesion(anonimo, DIRECTOR).status_code == 200
    reloj.adelantar(hours=11, minutes=59, seconds=59)
    assert anonimo.get("/api/proyectos").status_code == 200
    assert anonimo.get("/api/sesion").json()["segundos_restantes"] <= 1
    reloj.adelantar(seconds=1)
    respuesta = anonimo.get("/api/proyectos")
    assert respuesta.status_code == 401
    assert respuesta.json()["causa"] == "Tu sesión venció o ya no es válida."


def test_desactivar_corta_la_sesion_abierta_en_el_pedido_siguiente(cliente, con_contrasena):
    email, sesion, id_usuario = con_contrasena("proyectista")
    assert sesion.get("/api/proyectos").status_code == 200
    assert cliente.patch(f"/api/usuarios/{id_usuario}", json={"activo": False}).status_code == 200
    assert sesion.get("/api/proyectos").status_code == 401
    # Desactivado, no entra, y con el mensaje genérico (CU01, 4.a).
    otra = TestClient(sesion.app)
    respuesta = iniciar_sesion(otra, email)
    assert respuesta.status_code == 401
    assert respuesta.json()["causa"] == "El correo o la contraseña no son correctos."
    # Reactivado, entra con la temporal nueva (D72); la sesión cerrada sigue cerrada.
    reactivado = cliente.post(f"/api/usuarios/{id_usuario}/reactivacion")
    assert reactivado.status_code == 200, reactivado.text
    assert sesion.get("/api/proyectos").status_code == 401
    assert iniciar_sesion(otra, email, reactivado.json()["contrasena_temporal"]).status_code == 200


def test_cambiar_el_rol_vale_en_el_pedido_siguiente_de_la_misma_sesion(cliente, con_contrasena):
    _, sesion, id_usuario = con_contrasena("director_tecnico")
    assert sesion.get("/api/usuarios").status_code == 200
    assert cliente.patch(f"/api/usuarios/{id_usuario}", json={"rol": "consultor_interno"}).status_code == 200
    respuesta = sesion.get("/api/usuarios")
    assert respuesta.status_code == 403
    assert respuesta.json()["causa"] == "El rol consultor interno no permite gestionar usuarios y roles."
    assert sesion.get("/api/sesion").json()["permisos"] == ["consultar_alternativas"]
    assert sesion.get("/api/proyectos").status_code == 200
    assert cliente.patch(f"/api/usuarios/{id_usuario}", json={"rol": "proyectista"}).status_code == 200
    assert sesion.get("/api/sesion").json()["permisos"] == [
        "generar_alternativas",
        "consultar_alternativas",
        "responder_observaciones",
        "compartir_alternativas",
    ]


def test_cambiar_la_contrasena_cierra_las_otras_sesiones_y_conserva_la_propia(con_contrasena):
    email, primera, _ = con_contrasena()
    segunda = TestClient(primera.app)
    assert iniciar_sesion(segunda, email).status_code == 200
    cambio = primera.put("/api/sesion/contrasena", json={"contrasena_actual": CONTRASENA, "contrasena_nueva": "Otra#Clave26"})
    assert cambio.status_code == 200, cambio.text
    assert primera.get("/api/proyectos").status_code == 200
    assert segunda.get("/api/proyectos").status_code == 401


def test_un_pedido_que_modifica_desde_otro_sitio_da_403(anonimo):
    """CSRF (D63): `SameSite=Strict` y, además, el aviso del navegador de que el pedido viene de otro
    origen. Otro puerto de localhost es «el mismo sitio» para `SameSite`, pero no el mismo origen."""
    for encabezados in ({"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"}, {"Origin": "http://localhost:8000"}):
        respuesta = iniciar_sesion(anonimo, DIRECTOR, **encabezados)
        assert respuesta.status_code == 403, encabezados
        assert respuesta.json()["causa"] == "El pedido viene de otro sitio."
    # Del mismo origen, o sin aviso (no es un navegador), pasa.
    assert iniciar_sesion(anonimo, DIRECTOR, **{"Sec-Fetch-Site": "same-origin"}).status_code == 200
    assert iniciar_sesion(anonimo, DIRECTOR, **{"Origin": "http://testserver"}).status_code == 200
    # Una consulta no modifica nada: pasa aunque venga de otro sitio (y la cookie Strict no viaja).
    assert anonimo.get("/api/health", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200
