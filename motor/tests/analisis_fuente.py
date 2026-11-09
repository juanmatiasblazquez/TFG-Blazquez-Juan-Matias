"""Lectura estática del código del motor, para las pruebas de arquitectura (RNF07, RNF05).

Se analiza el AST sin ejecutar nada: así también se ven los imports y las llamadas que
están dentro de funciones que ninguna prueba recorre.
"""

import ast
from dataclasses import dataclass
from pathlib import Path

import motor_trazados

RAIZ_PAQUETE = Path(motor_trazados.__file__).resolve().parent


@dataclass(frozen=True)
class Hallazgo:
    archivo: str
    linea: int
    detalle: str

    def __str__(self) -> str:
        return f"  {self.archivo}:{self.linea}: {self.detalle}"


def modulos_del_paquete() -> list[tuple[str, ast.Module]]:
    """(ruta relativa, AST) de cada .py del paquete, en orden estable."""
    modulos = []
    for ruta in sorted(RAIZ_PAQUETE.rglob("*.py")):
        relativa = ruta.relative_to(RAIZ_PAQUETE.parent).as_posix()
        # utf-8-sig, igual que el intérprete: en Windows algunos editores (y Set-Content de
        # PowerShell 5.1) guardan con BOM, y con "utf-8" el BOM rompe ast.parse.
        arbol = ast.parse(ruta.read_text(encoding="utf-8-sig"), filename=relativa)
        modulos.append((relativa, arbol))
    return modulos


def imports_absolutos(arbol: ast.Module) -> list[tuple[int, str]]:
    """(línea, módulo) de cada import absoluto, ordenados por línea.

    `from x import y` se informa como `x.y` para que `from numpy import random` se vea
    como `numpy.random`. Los imports relativos (`from . import semillas`) no se informan:
    no salen del paquete.
    """
    encontrados = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            encontrados.extend((nodo.lineno, alias.name) for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
            encontrados.extend(
                (nodo.lineno, f"{nodo.module}.{alias.name}") for alias in nodo.names
            )
    return sorted(encontrados)


def imports_internos(arbol: ast.Module, paquete: str) -> list[tuple[int, str]]:
    """(línea, submódulo) de cada import de un módulo del propio paquete.

    `from .coordenadas import a_metros`, `from . import coordenadas` e
    `import motor_trazados.coordenadas` se informan los tres como «coordenadas».
    """
    encontrados = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and nodo.level > 0:
            if nodo.module:
                encontrados.append((nodo.lineno, nodo.module.split(".")[0]))
            else:
                encontrados.extend((nodo.lineno, alias.name) for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.module.split(".")[0] == paquete:
            partes = nodo.module.split(".")
            if len(partes) > 1:
                encontrados.append((nodo.lineno, partes[1]))
            else:
                encontrados.extend((nodo.lineno, alias.name) for alias in nodo.names)
        elif isinstance(nodo, ast.Import):
            for alias in nodo.names:
                partes = alias.name.split(".")
                if partes[0] == paquete and len(partes) > 1:
                    encontrados.append((nodo.lineno, partes[1]))
    return sorted(encontrados)


def nombre_punteado(nodo: ast.expr) -> str | None:
    """`np.random.seed` → "np.random.seed"; None si la expresión no es una cadena de nombres."""
    partes = []
    while isinstance(nodo, ast.Attribute):
        partes.append(nodo.attr)
        nodo = nodo.value
    if not isinstance(nodo, ast.Name):
        return None
    partes.append(nodo.id)
    return ".".join(reversed(partes))
