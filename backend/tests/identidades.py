"""Los usuarios de prueba y el inicio de sesión, sin estado: los importan el conftest y las pruebas.

(El conftest no se importa desde las pruebas: pytest lo carga como `conftest`, y un
`from tests.conftest import …` cargaría otra copia, con otros clientes HTTP.)
"""

from fastapi.testclient import TestClient

from app.core.permisos import Rol

# La contraseña de los usuarios de prueba: cumple la política de la p. 53.
CONTRASENA = "Pruebas#2026"
USUARIOS = {
    Rol.DIRECTOR_TECNICO: ("director@pruebas.local", "Dora", "Directora"),
    Rol.PROYECTISTA: ("proyectista@pruebas.local", "Pedro", "Proyectista"),
    Rol.CONSULTOR_INTERNO: ("consultor@pruebas.local", "Carla", "Consultora"),
}


def iniciar_sesion(cliente: TestClient, email: str, contrasena: str = CONTRASENA, **encabezados):
    return cliente.post("/api/sesion", json={"email": email, "contrasena": contrasena}, headers=encabezados)


def desde(direccion: str) -> dict[str, str]:
    """El encabezado con el que Nginx informa la dirección del navegador (D64)."""
    return {"X-Forwarded-For": direccion}
