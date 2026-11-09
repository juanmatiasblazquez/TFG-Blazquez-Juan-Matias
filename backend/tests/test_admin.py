"""Los comandos de administración (D68): el primer director técnico, la contraseña temporal por comando
y el desbloqueo de emergencia. No hay credenciales por defecto: todo usuario nace con una temporal."""

import re

import pytest

from app.admin import main
from tests.identidades import desde, iniciar_sesion


def temporal_de(salida: str) -> str:
    return re.search(r"Contraseña temporal: (\S+)", salida).group(1)


def test_crear_director_imprime_la_temporal_una_vez_y_con_ella_se_entra(capsys, anonimo, nuevo_correo):
    email = nuevo_correo("director")
    assert main(["crear-director", "--nombre", "Ana", "--apellido", "Pérez", "--email", email.upper()]) == 0
    salida = capsys.readouterr().out
    assert salida.count("Contraseña temporal:") == 1
    entrada = iniciar_sesion(anonimo, email, temporal_de(salida))
    assert entrada.status_code == 200, entrada.text
    cuerpo = entrada.json()
    assert (cuerpo["usuario"]["rol"], cuerpo["debe_cambiar_contrasena"]) == ("director_tecnico", True)
    # El mismo correo, otra vez: no se pisa a nadie.
    assert main(["crear-director", "--nombre", "Ana", "--apellido", "Pérez", "--email", email]) == 1
    assert "El correo ya está registrado." in capsys.readouterr().out


def test_ningun_comando_acepta_una_contrasena_elegida(capsys):
    with pytest.raises(SystemExit):
        main(["crear-director", "--nombre", "A", "--apellido", "B", "--email", "c@d.ar", "--contrasena", "Elegida#1"])
    capsys.readouterr()


def test_contrasena_temporal_por_comando(capsys, anonimo, crear_usuario):
    email = crear_usuario()["usuario"]["email"]
    assert main(["contrasena-temporal", "--email", email]) == 0
    assert iniciar_sesion(anonimo, email, temporal_de(capsys.readouterr().out)).status_code == 200
    assert main(["contrasena-temporal", "--email", "nadie@pruebas.local"]) == 1
    capsys.readouterr()


def test_desbloquear_levanta_el_bloqueo_de_una_direccion(capsys, anonimo, reloj, con_contrasena):
    email, _, _ = con_contrasena()
    bloqueada = desde("203.0.113.30")
    for _ in range(10):
        iniciar_sesion(anonimo, email, "Mala#Clave1", **bloqueada)
        reloj.adelantar(seconds=7)
    assert iniciar_sesion(anonimo, email, "Pruebas#2026", **bloqueada).status_code == 429
    assert main(["desbloquear", "--direccion", "203.0.113.30"]) == 0
    assert "1 fila(s)" in capsys.readouterr().out
    assert iniciar_sesion(anonimo, email, "Pruebas#2026", **bloqueada).status_code == 200
