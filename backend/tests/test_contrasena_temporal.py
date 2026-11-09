"""La contraseña temporal (CU02, paso 6; Seguridad, p. 53; D66): vale 24 h, se muestra una sola vez y,
hasta reemplazarla, la sesión solo permite cambiarla."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from tests.identidades import CONTRASENA, iniciar_sesion


def test_el_alta_da_una_temporal_de_24_horas_que_se_muestra_una_sola_vez(cliente, crear_usuario):
    creado = crear_usuario("consultor_interno")
    temporal = creado["contrasena_temporal"]
    assert len(temporal) == 12
    vence = datetime.fromisoformat(creado["vence"])
    restante = vence - datetime.now(vence.tzinfo)
    assert timedelta(hours=23, minutes=59) < restante <= timedelta(hours=24)
    usuario = creado["usuario"]
    assert (usuario["debe_cambiar_contrasena"], usuario["activo"]) == (True, True)
    # No se vuelve a mostrar: ni en el usuario, ni en la lista.
    leido = cliente.get(f"/api/usuarios/{usuario['id_usuario']}")
    assert temporal not in leido.text and "contrasena_temporal" not in leido.json()
    assert temporal not in cliente.get("/api/usuarios").text


def test_hasta_cambiarla_la_sesion_solo_permite_el_cambio(crear_usuario, anonimo):
    creado = crear_usuario("proyectista")
    entrada = iniciar_sesion(anonimo, creado["usuario"]["email"], creado["contrasena_temporal"])
    assert entrada.status_code == 200
    assert entrada.json()["debe_cambiar_contrasena"] is True
    for metodo, ruta in (("GET", "/api/proyectos"), ("GET", "/api/parametros/referencia"), ("GET", "/api/clientes")):
        respuesta = anonimo.request(metodo, ruta)
        assert respuesta.status_code == 403, ruta
        assert respuesta.json()["causa"] == "Antes de seguir tenés que cambiar la contraseña temporal."
    # Lo que sí permite: ver su sesión y cambiarla.
    assert anonimo.get("/api/sesion").status_code == 200
    cambio = anonimo.put(
        "/api/sesion/contrasena",
        json={"contrasena_actual": creado["contrasena_temporal"], "contrasena_nueva": CONTRASENA},
    )
    assert cambio.status_code == 200, cambio.text
    assert cambio.json()["debe_cambiar_contrasena"] is False
    assert anonimo.get("/api/proyectos").status_code == 200
    # La temporal ya no sirve.
    otro = TestClient(anonimo.app)
    assert iniciar_sesion(otro, creado["usuario"]["email"], creado["contrasena_temporal"]).status_code == 401


def test_la_temporal_vence_a_las_24_horas(crear_usuario, anonimo, reloj):
    creado = crear_usuario()
    email, temporal = creado["usuario"]["email"], creado["contrasena_temporal"]
    reloj.adelantar(hours=23, minutes=59, seconds=59)
    assert iniciar_sesion(anonimo, email, temporal).status_code == 200
    assert anonimo.get("/api/sesion").status_code == 200
    reloj.adelantar(seconds=1)
    # Vencida, ni la sesión que se abrió con ella sigue valiendo, ni se puede volver a entrar.
    assert anonimo.get("/api/sesion").status_code == 401
    respuesta = iniciar_sesion(TestClient(anonimo.app), email, temporal)
    assert respuesta.status_code == 401
    assert respuesta.json()["causa"] == "La contraseña temporal venció."


def test_la_temporal_vencida_con_una_contrasena_incorrecta_da_el_mensaje_generico(crear_usuario, anonimo, reloj):
    """El mensaje propio de la temporal vencida es solo para quien da la contraseña correcta: a quien
    no la conoce no se le revela nada (p. 53)."""
    creado = crear_usuario()
    reloj.adelantar(hours=25)
    respuesta = iniciar_sesion(anonimo, creado["usuario"]["email"], "Otra#Clave1")
    assert respuesta.json()["causa"] == "El correo o la contraseña no son correctos."


def test_el_reemplazo_por_olvido_sigue_las_mismas_reglas_y_cierra_las_sesiones(cliente, con_contrasena, anonimo, reloj):
    email, sesion, id_usuario = con_contrasena()
    respuesta = cliente.post(f"/api/usuarios/{id_usuario}/contrasena-temporal")
    assert respuesta.status_code == 200, respuesta.text
    temporal = respuesta.json()["contrasena_temporal"]
    # La sesión que tenía abierta se cierra, y la contraseña anterior ya no sirve.
    assert sesion.get("/api/proyectos").status_code == 401
    assert iniciar_sesion(anonimo, email, CONTRASENA).status_code == 401
    entrada = iniciar_sesion(anonimo, email, temporal)
    assert entrada.status_code == 200
    assert entrada.json()["debe_cambiar_contrasena"] is True
    assert anonimo.get("/api/proyectos").status_code == 403
    reloj.adelantar(hours=24)
    assert iniciar_sesion(TestClient(anonimo.app), email, temporal).json()["causa"] == "La contraseña temporal venció."
