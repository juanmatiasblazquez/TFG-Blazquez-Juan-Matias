"""RNF07: el motor es un paquete independiente de la API y de la base de datos.

Estas pruebas fallan si el motor pasa a depender de algo que no sea la biblioteca estándar
o sus cuatro dependencias de cálculo. Si una dependencia nueva es legítima (por ejemplo,
otra biblioteca de geometría), se agrega a PERMITIDOS *y* se registra la decisión en
docs/decisiones.md: la prueba no se "arregla" sin dejar escrito por qué.
"""

import ast
import importlib.util
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from analisis_fuente import (
    Hallazgo,
    imports_absolutos,
    imports_internos,
    modulos_del_paquete,
    nombre_punteado,
)

PAQUETE = "motor_trazados"

# Lo único que el motor puede importar, además de la biblioteca estándar y de sí mismo:
# las dependencias del artefacto motor-trazados en el diagrama de despliegue (p. 52).
PERMITIDOS = {"shapely", "networkx", "numpy", "pyproj"}

# Lo que delataría un acople con la API o con la base. La allowlist ya los deja afuera;
# esta lista sirve para las pruebas dinámicas y para que el mensaje sea explícito.
DELATORES = {
    "app",
    "fastapi",
    "starlette",
    "uvicorn",
    "pydantic",
    "pydantic_settings",
    "sqlalchemy",
    "alembic",
    "psycopg",
    "psycopg2",
    "geoalchemy2",
}

MENSAJE = (
    "El motor rompe su independencia (RNF07). Recibe geometrías y parámetros y devuelve "
    "geometrías y resultados: la API y la base lo usan a él, nunca al revés.\n"
)

# D21: el núcleo trabaja solo en metros y no sabe nada de coordenadas geográficas. pyproj se
# usa en un único módulo de borde, y el núcleo no importa ningún módulo de borde (la
# conversión y la exportación las llama la API, o el caso de referencia).
UNICO_CON_PYPROJ = f"{PAQUETE}/coordenadas.py"
MODULOS_DE_BORDE = {"coordenadas", "exportar", "referencia"}


def violaciones_de_dependencia(modulos: list[tuple[str, ast.Module]]) -> list[Hallazgo]:
    hallazgos = []
    for archivo, arbol in modulos:
        for linea, modulo in imports_absolutos(arbol):
            raiz = modulo.split(".")[0]
            if raiz == PAQUETE or raiz in PERMITIDOS or raiz in sys.stdlib_module_names:
                continue
            hallazgos.append(
                Hallazgo(archivo, linea, f"importa «{modulo}», fuera de la allowlist del motor")
            )
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Call) and _es_import_dinamico(nodo.func):
                hallazgos.append(
                    Hallazgo(
                        archivo,
                        nodo.lineno,
                        "import dinámico: el análisis estático no puede ver qué carga",
                    )
                )
    return sorted(hallazgos, key=lambda h: (h.archivo, h.linea))


def _es_import_dinamico(funcion: ast.expr) -> bool:
    nombre = nombre_punteado(funcion) or ""
    return nombre.split(".")[-1] in {"__import__", "import_module"}


def test_el_motor_solo_importa_lo_permitido():
    hallazgos = violaciones_de_dependencia(modulos_del_paquete())
    assert not hallazgos, MENSAJE + "\n".join(map(str, hallazgos))


def test_el_detector_encuentra_un_acople():
    """Sin esta prueba, un detector roto (que no encuentra nada) pasaría en verde."""
    codigo = ast.parse(
        "import os\n"
        "from app.core.db import SessionLocal\n"
        "import fastapi\n"
        "from . import semillas\n"
        "import importlib\n"
        "importlib.import_module('sqlalchemy')\n"
        "import shapely.geometry\n"
    )
    hallazgos = violaciones_de_dependencia([("motor_trazados/sintetico.py", codigo)])
    assert [h.linea for h in hallazgos] == [2, 3, 6]


def violaciones_del_borde(modulos: list[tuple[str, ast.Module]]) -> list[Hallazgo]:
    hallazgos = []
    for archivo, arbol in modulos:
        for linea, modulo in imports_absolutos(arbol):
            if modulo.split(".")[0] == "pyproj" and archivo != UNICO_CON_PYPROJ:
                hallazgos.append(
                    Hallazgo(archivo, linea, f"importa «{modulo}»: solo coordenadas.py usa pyproj")
                )
        if Path(archivo).stem in MODULOS_DE_BORDE:
            continue
        for linea, interno in imports_internos(arbol, PAQUETE):
            if interno in MODULOS_DE_BORDE:
                hallazgos.append(
                    Hallazgo(archivo, linea, f"el núcleo importa «{interno}», que es un módulo de borde")
                )
    return sorted(hallazgos, key=lambda h: (h.archivo, h.linea))


def test_el_nucleo_no_sabe_de_coordenadas_geograficas():
    hallazgos = violaciones_del_borde(modulos_del_paquete())
    assert not hallazgos, (
        "El núcleo del motor trabaja solo en metros (D21): pyproj vive en coordenadas.py y el "
        "núcleo no importa los módulos de borde.\n" + "\n".join(map(str, hallazgos))
    )


def test_el_detector_encuentra_coordenadas_en_el_nucleo():
    """Sin esta prueba, un detector roto pasaría en verde."""
    nucleo = ast.parse(
        "import pyproj\n"
        "from .coordenadas import a_metros\n"
        "from . import exportar\n"
        "from .geometria import TOLERANCIA\n"
        "import motor_trazados.referencia\n"
    )
    borde = ast.parse("from pyproj import Transformer\nfrom .contrato import SolicitudGeneracion\n")
    hallazgos = violaciones_del_borde(
        [(f"{PAQUETE}/motor.py", nucleo), (UNICO_CON_PYPROJ, borde)]
    )
    assert [(h.archivo, h.linea) for h in hallazgos] == [(f"{PAQUETE}/motor.py", n) for n in (1, 2, 3, 5)]


def test_importar_el_motor_no_carga_la_api_ni_la_base():
    """Cubre lo que el AST no ve: lo que se carga de forma transitiva al importar."""
    programa = (
        "import importlib, pkgutil, sys, motor_trazados\n"
        "for m in pkgutil.walk_packages(motor_trazados.__path__, 'motor_trazados.'):\n"
        "    importlib.import_module(m.name)\n"
        "print('\\n'.join(sys.modules))\n"
    )
    salida = subprocess.run(
        [sys.executable, "-c", programa], capture_output=True, text=True, check=True
    ).stdout.split()
    cargados = sorted({modulo.split(".")[0] for modulo in salida} & DELATORES)
    assert not cargados, MENSAJE + f"Importar el motor carga: {cargados}"


def test_las_dependencias_declaradas_estan_en_la_allowlist():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    declaradas = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["dependencies"]
    nombres = {re.split(r"[\s<>=!~\[;]", requisito)[0].lower().replace("-", "_") for requisito in declaradas}
    fuera = sorted(nombres - PERMITIDOS)
    assert not fuera, MENSAJE + f"pyproject.toml declara dependencias fuera de la allowlist: {fuera}"


def test_corre_aislado_de_la_api():
    """Las pruebas del motor corren en su propio contenedor, sin la API instalada.

    Si esto falla, se están corriendo en el contenedor api (o en un entorno con la API
    instalada) y un import prohibido podría pasar desapercibido. Correrlas con:
    docker compose run --rm motor
    """
    instalados = sorted(m for m in DELATORES if importlib.util.find_spec(m) is not None)
    assert not instalados, (
        f"El entorno de pruebas del motor tiene instalado {instalados}. "
        "Correlas aisladas: docker compose run --rm motor"
    )
