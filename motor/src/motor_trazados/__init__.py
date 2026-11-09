"""Motor de generación de trazados (paquete «motor-trazados»).

Particiona el polígono de un terreno en celdas útiles con frente sobre una red de
circulación conexa. El mismo motor, con otros parámetros, resuelve loteos y playas de
estacionamiento.

Contrato (NO romper; ver CLAUDE.md, «Invariantes de arquitectura»):

- RNF07: es INDEPENDIENTE de la API y de la base de datos. Recibe geometrías y
  parámetros y devuelve geometrías y resultados. Solo importa la biblioteca estándar,
  shapely, networkx, numpy y pyproj. Lo ata tests/test_independencia.py.
- RNF05: una misma combinación de polígono, parámetros y estrategia produce siempre la
  misma alternativa. Toda aleatoriedad sale de `semillas.generador(semilla)`. Lo ata
  tests/test_semillas.py.
- Opera en coordenadas proyectadas, en metros (nota del diagrama de clases del motor,
  p. 47 del documento). Las geometrías se guardan en EPSG:4326: la conversión está en
  `coordenadas`, el único módulo que importa pyproj, y la llama la API (D21).

Uso:

    from motor_trazados import MotorGeneracion, SolicitudGeneracion
    resultado = MotorGeneracion().generar(solicitud)
"""

from importlib.metadata import version

# La versión vive en pyproject.toml (copia única); acá solo se lee. La API la expone en
# /api/health como prueba de que el paquete está instalado en su contenedor.
__version__ = version("motor-trazados")

from .contrato import (  # noqa: E402
    CalleBorde,
    CeldaGenerada,
    CriterioEspacioVerde,
    ElementosFijados,
    Estrategia,
    Incumplimiento,
    Indicadores,
    JerarquiaCorredor,
    ManzanaFijada,
    ParametrosEstacionamiento,
    ParametrosLoteo,
    PatronRed,
    ReglaCoherencia,
    ResultadoGeneracion,
    SentidoCirculacion,
    SolicitudGeneracion,
    TipoCelda,
    TipoIncumplimiento,
    TipoProyecto,
    TramoFijado,
    coherencia_de_loteo,
    exige_avenidas,
    jerarquias_en_uso,
    reglas_de_coherencia,
)
from .errores import (  # noqa: E402
    ErrorConectividad,
    ErrorMotor,
    NoImplementado,
    Problema,
    SinDominioRestante,
    SolicitudInvalida,
    TerrenoSinLotes,
)
from .motor import MotorGeneracion  # noqa: E402

__all__ = [
    "CalleBorde",
    "CeldaGenerada",
    "CriterioEspacioVerde",
    "ElementosFijados",
    "ErrorConectividad",
    "ErrorMotor",
    "Estrategia",
    "Incumplimiento",
    "Indicadores",
    "JerarquiaCorredor",
    "ManzanaFijada",
    "MotorGeneracion",
    "NoImplementado",
    "ParametrosEstacionamiento",
    "ParametrosLoteo",
    "PatronRed",
    "Problema",
    "ReglaCoherencia",
    "ResultadoGeneracion",
    "SentidoCirculacion",
    "SinDominioRestante",
    "SolicitudGeneracion",
    "SolicitudInvalida",
    "TerrenoSinLotes",
    "TipoCelda",
    "TipoIncumplimiento",
    "TipoProyecto",
    "TramoFijado",
    "__version__",
    "coherencia_de_loteo",
    "exige_avenidas",
    "jerarquias_en_uso",
    "reglas_de_coherencia",
]
