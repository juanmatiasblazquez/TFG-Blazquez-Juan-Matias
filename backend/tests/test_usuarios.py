"""Gestión de usuarios (CU02, RF02; D66, D68): alta con contraseña temporal, correo ya registrado
(6.a), modificación de datos y rol (3.a), baja que no borra (3.b) y reactivación."""

import pytest
from sqlalchemy import text

from tests.identidades import CONTRASENA, USUARIOS, iniciar_sesion


def test_alta_y_lista_con_rol_y_estado(cliente, nuevo_correo):
    email = nuevo_correo("alta")
    respuesta = cliente.post("/api/usuarios", json={"nombre": "Lía", "apellido": "Núñez", "email": email, "rol": "proyectista"})
    assert respuesta.status_code == 201, respuesta.text
    usuario = respuesta.json()["usuario"]
    assert respuesta.headers["Location"] == f"/api/usuarios/{usuario['id_usuario']}"
    assert (usuario["rol"], usuario["activo"], usuario["debe_cambiar_contrasena"]) == ("proyectista", True, True)
    lista = cliente.get("/api/usuarios").json()
    fila = next(u for u in lista if u["email"] == email)
    assert (fila["nombre"], fila["rol"], fila["activo"]) == ("Lía", "proyectista", True)
    assert all("hash_contrasena" not in u for u in lista)


def test_6a_el_correo_ya_registrado_se_informa_sin_importar_como_se_escriba(cliente, crear_usuario):
    email = crear_usuario()["usuario"]["email"]
    respuesta = cliente.post(
        "/api/usuarios", json={"nombre": "Otra", "apellido": "Persona", "email": f" {email.upper()} ", "rol": "consultor_interno"}
    )
    assert respuesta.status_code == 409
    cuerpo = respuesta.json()
    assert cuerpo["causa"] == "El correo ya está registrado."
    assert cuerpo["problemas"] == [{"campo": "email", "mensaje": "Ya hay un usuario con este correo."}]


@pytest.mark.parametrize(
    ("cambios", "campo"),
    [
        ({"email": "sin-arroba"}, "email"),
        ({"rol": "cliente"}, "rol"),
        ({"rol": "administrador"}, "rol"),
        ({"nombre": ""}, "nombre"),
    ],
)
def test_datos_invalidos_dan_422_en_el_campo(cliente, cambios, campo):
    cuerpo = {"nombre": "Nombre", "apellido": "Apellido", "email": "valido@pruebas.local", "rol": "proyectista"} | cambios
    respuesta = cliente.post("/api/usuarios", json=cuerpo)
    assert respuesta.status_code == 422
    assert [p["campo"] for p in respuesta.json()["problemas"]] == [campo]


def test_3a_modificar_datos_y_rol(cliente, crear_usuario, nuevo_correo):
    id_usuario = crear_usuario("consultor_interno")["usuario"]["id_usuario"]
    nuevo = nuevo_correo("cambiado")
    respuesta = cliente.patch(f"/api/usuarios/{id_usuario}", json={"apellido": "Cambiado", "email": nuevo.upper(), "rol": "proyectista"})
    assert respuesta.status_code == 200, respuesta.text
    assert (respuesta.json()["apellido"], respuesta.json()["email"], respuesta.json()["rol"]) == ("Cambiado", nuevo, "proyectista")
    # El correo de otro usuario, no.
    otro = USUARIOS["proyectista"][0]
    assert cliente.patch(f"/api/usuarios/{id_usuario}", json={"email": otro}).status_code == 409
    assert cliente.patch("/api/usuarios/999999", json={"apellido": "X"}).status_code == 404


def test_3b_la_baja_desactiva_y_no_borra_ni_rompe_la_autoria(cliente, con_contrasena, nuevo_codigo, id_cliente, db):
    """Un usuario nunca se borra (CU02): sus proyectos siguen diciendo quién los registró."""
    from tests.datos_referencia import cuerpo_proyecto

    _, sesion, id_usuario = con_contrasena("director_tecnico")
    proyecto = sesion.post("/api/proyectos", json=cuerpo_proyecto(nuevo_codigo(), id_cliente))
    assert proyecto.status_code == 201, proyecto.text
    respuesta = cliente.patch(f"/api/usuarios/{id_usuario}", json={"activo": False})
    assert respuesta.status_code == 200
    assert respuesta.json()["activo"] is False
    assert db.scalar(text("SELECT count(*) FROM usuario WHERE id_usuario = :u"), {"u": id_usuario}) == 1
    leido = cliente.get(f"/api/proyectos/{proyecto.json()['id_proyecto']}").json()
    assert leido["responsable"]["id_usuario"] == id_usuario
    # Sigue en la lista, desactivado, después de los activos.
    lista = cliente.get("/api/usuarios").json()
    fila = next(u for u in lista if u["id_usuario"] == id_usuario)
    assert fila["activo"] is False
    assert lista.index(fila) > max(i for i, u in enumerate(lista) if u["activo"])
    # Reactivado, vuelve con una temporal nueva (D72).
    assert cliente.post(f"/api/usuarios/{id_usuario}/reactivacion").status_code == 200


def test_siempre_queda_un_director_tecnico_activo(cliente, db):
    """Dar de baja o cambiarle el rol al último director técnico activo da 409: si no, nadie podría
    volver a gestionar usuarios desde el portal."""
    yo = cliente.get("/api/sesion").json()["usuario"]["id_usuario"]
    otros = db.scalars(
        text(
            "UPDATE usuario SET activo = false WHERE rol = 'director_tecnico' AND activo AND id_usuario <> :yo "
            "RETURNING id_usuario"
        ),
        {"yo": yo},
    ).all()
    db.commit()
    try:
        for cambios in ({"activo": False}, {"rol": "proyectista"}):
            respuesta = cliente.patch(f"/api/usuarios/{yo}", json=cambios)
            assert respuesta.status_code == 409, cambios
            assert respuesta.json()["causa"] == "Tiene que quedar al menos un director técnico activo."
        # Un null explícito no cambia nada.
        assert cliente.patch(f"/api/usuarios/{yo}", json={"rol": None, "activo": None}).status_code == 200
    finally:
        if otros:
            db.execute(text("UPDATE usuario SET activo = true WHERE id_usuario = ANY(:ids)"), {"ids": list(otros)})
            db.commit()
    assert cliente.get("/api/usuarios").status_code == 200


def test_reactivar_da_una_temporal_nueva_y_la_contrasena_anterior_ya_no_vale(cliente, con_contrasena, anonimo):
    """Lo validado de la sesión 12 (D72): reactivar es del director técnico y genera una temporal nueva,
    que vale 24 h, se muestra una vez y obliga a cambiarla. Quien vuelve no entra con la de antes."""
    email, _, id_usuario = con_contrasena("proyectista")
    assert cliente.patch(f"/api/usuarios/{id_usuario}", json={"activo": False}).status_code == 200
    respuesta = cliente.post(f"/api/usuarios/{id_usuario}/reactivacion")
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["usuario"]["activo"] is True
    assert cuerpo["usuario"]["debe_cambiar_contrasena"] is True
    temporal = cuerpo["contrasena_temporal"]
    assert iniciar_sesion(anonimo, email, CONTRASENA).status_code == 401
    assert iniciar_sesion(anonimo, email, temporal).status_code == 200
    # Con la temporal, la sesión solo permite cambiarla (p. 53).
    assert anonimo.get("/api/proyectos").status_code == 403
    # La lista no la vuelve a mostrar.
    assert temporal not in cliente.get("/api/usuarios").text


def test_reactivar_a_un_activo_da_409_y_el_patch_ya_no_reactiva(cliente, con_contrasena):
    _, _, id_usuario = con_contrasena("proyectista")
    respuesta = cliente.post(f"/api/usuarios/{id_usuario}/reactivacion")
    assert respuesta.status_code == 409
    assert "ya está activo" in respuesta.json()["causa"]
    # El PATCH solo da de baja: reactivar sin temporal no es posible.
    respuesta = cliente.patch(f"/api/usuarios/{id_usuario}", json={"activo": True})
    assert respuesta.status_code == 422
    assert respuesta.json()["problemas"][0]["campo"] == "activo"
