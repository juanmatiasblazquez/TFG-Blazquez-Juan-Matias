"""Roles y funciones: la tabla de la p. 54 (Seguridad), copia única (RF03; D67).

Cada endpoint del dominio declara la función que ejerce con `Depends(requiere(Funcion.X))`
(`app/api/dependencias.py`). Una meta-prueba (`tests/test_tabla_roles.py`) exige que toda ruta la
declare, y la prueba de la tabla compara lo que responde la API con la tabla del documento, transcrita
aparte: no con este diccionario.

El portal no copia la tabla: `GET /api/sesion` le da la lista de funciones del usuario (`permisos`),
y con ella oculta lo que el rol no puede hacer (D37). Quien decide es la API.

El Cliente no tiene cuenta (CU15: «sin cuenta de usuario»): ve lo que el estudio comparte con él por
un enlace, que es la sesión siguiente. Por eso no es un `Rol`.
"""

from enum import StrEnum


class Rol(StrEnum):
    """Los roles con cuenta (ER `usuario.rol`, varchar(20)). El documento tipa `rol: Rol` sin enumerar
    sus valores (p. 46): son las columnas de la tabla de la p. 54, salvo el Cliente."""

    DIRECTOR_TECNICO = "director_tecnico"
    PROYECTISTA = "proyectista"
    CONSULTOR_INTERNO = "consultor_interno"


class Funcion(StrEnum):
    """Las filas de la tabla de la p. 54, en su orden."""

    GESTIONAR_USUARIOS = "gestionar_usuarios"
    # «Registrar proyectos, delimitar terrenos y configurar parámetros» (CU03, CU04, CU05).
    REGISTRAR_PROYECTOS = "registrar_proyectos"
    # «Generar alternativas y recalcular sectores» (CU06, CU09).
    GENERAR_ALTERNATIVAS = "generar_alternativas"
    # «Consultar alternativas» (CU10, CU13).
    CONSULTAR_ALTERNATIVAS = "consultar_alternativas"
    REGISTRAR_OBSERVACIONES = "registrar_observaciones"
    RESPONDER_OBSERVACIONES = "responder_observaciones"
    # «Seleccionar alternativas, compartirlas y revocarlas» (CU14).
    COMPARTIR_ALTERNATIVAS = "compartir_alternativas"


PERMISOS: dict[Rol, frozenset[Funcion]] = {
    Rol.DIRECTOR_TECNICO: frozenset(Funcion),
    Rol.PROYECTISTA: frozenset(
        {
            Funcion.GENERAR_ALTERNATIVAS,
            Funcion.CONSULTAR_ALTERNATIVAS,
            Funcion.RESPONDER_OBSERVACIONES,
            Funcion.COMPARTIR_ALTERNATIVAS,
        }
    ),
    Rol.CONSULTOR_INTERNO: frozenset({Funcion.CONSULTAR_ALTERNATIVAS}),
}

# Para los mensajes (RNF01).
NOMBRES_ROL = {
    Rol.DIRECTOR_TECNICO: "director técnico",
    Rol.PROYECTISTA: "proyectista",
    Rol.CONSULTOR_INTERNO: "consultor interno",
}
DESCRIPCIONES = {
    Funcion.GESTIONAR_USUARIOS: "gestionar usuarios y roles",
    Funcion.REGISTRAR_PROYECTOS: "registrar proyectos, delimitar terrenos y configurar parámetros",
    Funcion.GENERAR_ALTERNATIVAS: "generar alternativas y recalcular sectores",
    Funcion.CONSULTAR_ALTERNATIVAS: "consultar alternativas",
    Funcion.REGISTRAR_OBSERVACIONES: "registrar observaciones",
    Funcion.RESPONDER_OBSERVACIONES: "responder observaciones",
    Funcion.COMPARTIR_ALTERNATIVAS: "seleccionar alternativas, compartirlas y revocarlas",
}


def funciones_de(rol: str) -> list[Funcion]:
    """Las funciones de un rol, en el orden de la tabla. Un rol desconocido no tiene ninguna."""
    try:
        permitidas = PERMISOS[Rol(rol)]
    except ValueError:
        return []
    return [funcion for funcion in Funcion if funcion in permitidas]


def permite(rol: str, funcion: Funcion) -> bool:
    return funcion in funciones_de(rol)
