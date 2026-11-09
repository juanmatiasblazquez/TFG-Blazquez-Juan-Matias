"""Mensaje y tiempo genéricos (CU01, 4.a; Seguridad, p. 53; D66): un correo inexistente, una contraseña
incorrecta y un usuario desactivado responden lo mismo, y el tiempo de respuesta no revela si el correo
está registrado."""

import statistics
import time

from tests.identidades import CONTRASENA, desde, iniciar_sesion

MALA = "Mala#Clave1"


def test_inexistente_incorrecta_y_desactivado_responden_lo_mismo(anonimo, cliente, con_contrasena):
    email, _, _ = con_contrasena()
    desactivado, _, id_desactivado = con_contrasena()
    assert cliente.patch(f"/api/usuarios/{id_desactivado}", json={"activo": False}).status_code == 200
    respuestas = [
        iniciar_sesion(anonimo, "nadie@pruebas.local", MALA, **desde("198.51.100.1")),
        iniciar_sesion(anonimo, email, MALA, **desde("198.51.100.2")),
        # El desactivado, con SU contraseña correcta.
        iniciar_sesion(anonimo, desactivado, CONTRASENA, **desde("198.51.100.3")),
    ]
    assert [r.status_code for r in respuestas] == [401, 401, 401]
    cuerpos = [r.json() for r in respuestas]
    assert cuerpos[0] == cuerpos[1] == cuerpos[2]
    assert cuerpos[0]["causa"] == "El correo o la contraseña no son correctos."
    assert "trazados_sesion" not in anonimo.cookies


def test_un_correo_inexistente_tarda_lo_mismo_que_una_contrasena_incorrecta(anonimo, con_contrasena):
    """Sin `contrasenas.HASH_SIMULADO`, el correo inexistente respondería sin calcular Argon2: en un par
    de milisegundos contra unos 70. Las medianas tienen que diferir en menos de la mitad."""
    email, _, _ = con_contrasena()
    tiempos: dict[str, list[float]] = {"inexistente": [], "incorrecta": []}
    for k in range(9):
        for caso, correo in (("inexistente", f"nadie{k}@pruebas.local"), ("incorrecta", email)):
            # Cada vuelta desde otra dirección: el bloqueo y el límite no entran en la medición.
            inicio = time.perf_counter()
            respuesta = iniciar_sesion(anonimo, correo, MALA, **desde(f"198.51.100.{10 + k}"))
            tiempos[caso].append(time.perf_counter() - inicio)
            assert respuesta.status_code == 401
    inexistente, incorrecta = (statistics.median(tiempos[c]) for c in ("inexistente", "incorrecta"))
    print(f"\nMedianas: correo inexistente {inexistente * 1000:.1f} ms, contraseña incorrecta {incorrecta * 1000:.1f} ms")
    # Los dos calcularon Argon2.
    assert min(inexistente, incorrecta) > 0.02
    assert abs(inexistente - incorrecta) / max(inexistente, incorrecta) < 0.5
