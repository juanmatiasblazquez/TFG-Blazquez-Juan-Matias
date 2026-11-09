"""Modelos ORM del flujo de generación (ER, p. 47; D28).

Están las entidades del flujo, desde el registro del proyecto hasta compartirlo con el cliente
(observaciones y enlaces, D69 y D70), y las de la identidad (usuarios, sesiones y el control de acceso,
D63 a D65). Los nombres de tablas y columnas son los del ER; lo que se aparta está anotado en el modelo y
en D28.

migrations/env.py importa este paquete, así cada modelo queda registrado en Base.metadata
(lo usa la prueba de que los modelos coinciden con las migraciones).
"""

from app.models.alternativa import (
    Alternativa,
    AreaReservadaVersion,
    Celda,
    Incumplimiento,
    Manzana,
    NodoRed,
    TramoCirculacion,
    VersionAlternativa,
)
from app.models.cliente import Cliente
from app.models.enlace import EnlaceCompartido, EnlaceVersion
from app.models.observacion import Observacion, RespuestaObservacion
from app.models.parametros import ConjuntoParametros, JerarquiaCorredor, ParametrosLoteo
from app.models.proyecto import AreaReservada, Proyecto, PuntoAcceso, Terreno
from app.models.usuario import AccesoDireccion, Sesion, Usuario

__all__ = [
    "AccesoDireccion",
    "Alternativa",
    "AreaReservada",
    "AreaReservadaVersion",
    "Celda",
    "Cliente",
    "ConjuntoParametros",
    "EnlaceCompartido",
    "EnlaceVersion",
    "Incumplimiento",
    "JerarquiaCorredor",
    "Manzana",
    "NodoRed",
    "Observacion",
    "ParametrosLoteo",
    "Proyecto",
    "PuntoAcceso",
    "RespuestaObservacion",
    "Sesion",
    "Terreno",
    "TramoCirculacion",
    "Usuario",
    "VersionAlternativa",
]
