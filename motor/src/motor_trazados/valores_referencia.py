"""Valores de referencia de los parámetros de loteo, con su fuente (D23).

Son valores **configurables**, no reglas rígidas (p. 10): otra jurisdicción usa la misma
estructura con otros valores. Cada uno lleva en FUENTES el artículo que lo respalda o la
marca «a validar» si no se pudo verificar en la norma; una prueba exige que ninguno quede
sin fuente.

Normas consultadas el 27/10/2026:
- Ley Provincial 4146 (Córdoba, 1949), texto publicado por la Dirección de Catastro:
  https://www.catastrocordoba.gob.ar/ley4146
- Ordenanza 8060/85 de la ciudad de Córdoba (fraccionamiento de tierras), texto del Digesto
  municipal con modificatorias hasta la Ord. 10996:
  https://static.cordoba.gov.ar/DigestoWeb/pdf/20386653-d9ad-4cc1-a995-e9e627c82bed/TEX_8060.pdf
  Puede haber modificatorias posteriores a ese texto. Los arts. 48 y 54 se volvieron a leer en ese
  texto el 04/11/2026 (D49), junto con el Dec. Reglamentario 737-D-86, art. 17.
- Ley 4146, art. 12: verificado por el autor en el texto de Catastro Córdoba (D48).

Qué norma rige en cada caso lo define la jurisdicción del proyecto (RF04). Los valores de
abajo corresponden a la zona 2 de la Ord. 8060 (ciudad de Córdoba).
"""

from .contrato import CalleBorde, CriterioEspacioVerde, JerarquiaCorredor, ParametrosLoteo

A_VALIDAR = "A VALIDAR"
# Prefijo de la fuente de un valor que es un criterio de diseño y no sale de una norma: el
# portal lo marca así, para no presentarlo como una exigencia legal (D46).
CRITERIO_DISENO = "Criterio de diseño"

PARAMETROS_LOTEO_REFERENCIA = ParametrosLoteo(
    frente_minimo=10.0,
    frente_objetivo=12.0,
    fondo_minimo=25.0,
    superficie_minima=250.0,
    superficie_maxima=600.0,
    relacion_fondo_frente_max=3.0,
    longitud_maxima_manzana=140.0,
    porcentaje_espacio_verde=10.0,
    porcentaje_equipamiento=5.0,
    superficie_minima_verde=1000.0,
    ancho_minimo_verde=20.0,
    ancho_minimo_lote=10.0,
    factor_union_maximo=1.5,
    porcentaje_minimo_avenidas=20.0,
    ancho_minimo_avenida=20.0,
    ancho_minimo_calle=12.0,
    ancho_minimo_calzada=6.0,
    porcentaje_incremento_esquina=20.0,
    criterio_espacio_verde=CriterioEspacioVerde.CERCANIA,
    lado_minimo_manzana=42.0,
    lado_maximo_manzana=250.0,
    lado_maximo_sin_pasaje=200.0,
    calle_borde=CalleBorde.POR_LADO,
)

JERARQUIAS_REFERENCIA = (
    # Ord. 8060, art. 14 d, perfil 6 (colectoras): calzada 12 m y veredas de 3 a 4 m, 18 a 20 m
    # entre líneas municipales. Se toma la vereda de 4 m: 20 m en total.
    JerarquiaCorredor("Colectora (perfil 6)", 1, ancho_calzada=12.0, ancho_vereda=4.0, radio_ochava=6.0),
    # Ord. 8060, art. 14 e, perfil 9 (locales): 12 m entre líneas municipales, calzada 7 m y
    # veredas de 2,5 m.
    JerarquiaCorredor("Local (perfil 9)", 2, ancho_calzada=7.0, ancho_vereda=2.5, radio_ochava=4.0),
)

FUENTES: dict[str, str] = {
    "frente_minimo": (
        "Ley 4146, art. 9 (lugares simplemente habitables); Ord. 8060, art. 6, Cuadro I, zona 2 "
        "(texto según Ord. 9089, art. 3)."
    ),
    "frente_objetivo": "Criterio de diseño (pantalla de parámetros, p. 49 del documento).",
    "fondo_minimo": (
        f"{A_VALIDAR}: p. 49 del documento. No figura en la Ley 4146 ni en la Ord. 8060 "
        "(250 m² / 10 m = 25 m)."
    ),
    "superficie_minima": (
        "Ord. 8060, art. 6, Cuadro I, zona 2. La Ley 4146 no fija superficie mínima fuera de "
        "las zonas de turismo (art. 9: 700 m²)."
    ),
    "superficie_maxima": (
        f"{CRITERIO_DISENO} (p. 49 del documento). No es una restricción: decide cuándo una fracción "
        "se une a su vecino y cuándo se subdivide un lote; el que la pasa es un lote grande (D47)."
    ),
    "relacion_fondo_frente_max": (
        f"{A_VALIDAR}: p. 49 del documento. Desde el motor 0.5.0 decide si una pieza es un lote: "
        "la que la pasa es un remanente (D43)."
    ),
    "longitud_maxima_manzana": (
        f"{CRITERIO_DISENO} (p. 49 del documento): la grilla corta las manzanas en este largo. No puede "
        "pasar el lado mayor sin pasaje peatonal de la Ord. 8060, art. 48 (200 m), porque el motor no "
        "traza pasajes (D50)."
    ),
    "lado_minimo_manzana": (
        "Ord. 8060, art. 48: «La dimensión del lado menor de cada manzana deberá ser de 42,00 m. como "
        "mínimo» (texto leído en el Digesto, D49). En una manzana irregular, su ancho: el diámetro del "
        "mayor círculo que entra en ella (D50)."
    ),
    "lado_maximo_manzana": (
        "Ord. 8060, art. 48: «La dimensión del lado mayor no podrá exceder de 250,00 m.», salvo razones "
        "debidamente fundadas. Se mide como el lado largo del rectángulo mínimo de la manzana (D50)."
    ),
    "lado_maximo_sin_pasaje": (
        "Ord. 8060, art. 48: si el lado mayor excede los 200,00 m, debe proyectarse un pasaje peatonal "
        "en la parte central de la manzana. El motor no traza pasajes: pasarlo es un incumplimiento "
        "(D50)."
    ),
    "porcentaje_espacio_verde": (
        "Ley 4146, art. 7, y Ord. 8060, art. 67: el 10 % de la superficie total de los lotes "
        "(no del terreno)."
    ),
    "porcentaje_equipamiento": "Ord. 8060, art. 67 (equipamiento comunitario, además del verde).",
    "superficie_minima_verde": (
        f"{A_VALIDAR}: criterio de diseño (D41), una plazoleta de unos tres lotes. La Ley 4146, "
        "art. 7, pide espacios verdes de ubicación y dimensiones adecuadas sin fijar medidas."
    ),
    "ancho_minimo_verde": (
        f"{A_VALIDAR}: criterio de diseño (D41). Se mide como el diámetro del mayor círculo que "
        "entra en el remanente; con menos de 20 m es un cantero, no una plaza (Ley 4146, art. 7, "
        "sin medidas)."
    ),
    "ancho_minimo_lote": (
        f"{A_VALIDAR}: criterio de diseño (D43). Es el diámetro del mayor círculo que entra en el "
        "lote, medido como el ancho del verde. Igual al frente mínimo: un lote rectangular que "
        "alcanza el frente mínimo lo cumple siempre, y el criterio solo actúa sobre las formas "
        "irregulares (una L, un lote bandera, una punta triangular)."
    ),
    "factor_union_maximo": (
        f"{A_VALIDAR}: criterio de diseño (D43, propuesta del autor). Una fracción se une a su lote "
        "vecino si el lote que resulta no pasa este factor por la mediana de los lotes de su "
        "manzana."
    ),
    "porcentaje_minimo_avenidas": (
        "Ley 4146, art. 12 (verificado por el autor en el texto de Catastro Córdoba): no menos del "
        "20 % de la longitud total de calles son avenidas. El motor elige las avenidas mínimas para "
        "llegar (D48)."
    ),
    "ancho_minimo_avenida": "Ley 4146, art. 12: las avenidas miden al menos 20 m de ancho (D48).",
    "ancho_minimo_calle": (
        "Ley 4146, art. 12: las calles miden al menos 12 m de ancho; también la Ord. 8060, art. 25."
    ),
    "ancho_minimo_calzada": (
        "Ley 4146, art. 12: al menos 6 m de calzada. Se verifica sobre la calzada de la jerarquía: "
        "el corredor no dibuja la calzada aparte de las veredas (D48)."
    ),
    "porcentaje_incremento_esquina": (
        "Ord. 8060, art. 54: «Las parcelas esquinas deberán incrementar la medida de su frente mínimo "
        "en un 20% (veinte por ciento)». En los loteos rurales de las zonas 9, 10 y 11 va 0 (Dec. "
        "Reglamentario 737-D-86, art. 17 b; D49)."
    ),
    "criterio_espacio_verde": (
        f"{CRITERIO_DISENO}, no una norma (D46, D51): la Ley 4146, art. 7, pide espacios verdes de "
        "ubicación adecuada, no central. «Más cercanía» (el de referencia) elige la pieza que deja "
        "los lotes más cerca del verde, sin otra prioridad; «menos lotes perdidos», la que cuesta "
        "menos lotes, con los lotes grandes primero."
    ),
    "calle_borde": (
        f"{CRITERIO_DISENO}, no una norma (D50, D86): la Ord. 8060, art. 48, pide que el lado menor de "
        "cada manzana mida al menos 42 m, no una calle perimetral. «Por lado» (el de referencia) la lleva "
        "en los lados casi paralelos a las filas, que sin ella quedarían con frente de un solo lado, en los "
        "de una entrante y en los de un acceso; en los demás, las filas terminan contra el límite. «En "
        "todo el contorno» la lleva por todo el límite."
    ),
    "jerarquias.anchos": (
        "Ord. 8060, art. 14 (perfiles 6 y 9). Ambos cumplen el mínimo de 12 m de la Ord. 8060, "
        "art. 25, y de la Ley 4146, art. 12 (calzada de 6 m como mínimo); la colectora de 20 m "
        "alcanza el ancho de avenida de la Ley 4146, art. 12, y es la jerarquía de las avenidas "
        "que elige el motor (D48)."
    ),
    "jerarquias.radio_ochava": (
        f"{A_VALIDAR}: 6 m y 4 m de la p. 49 del documento. La Ord. 8060, art. 55, dice que la "
        "ochava es vía pública y remite su medida al Reglamento de Edificación, que no se verificó."
    ),
}
