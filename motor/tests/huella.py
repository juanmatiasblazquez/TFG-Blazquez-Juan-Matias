"""Huella de un resultado: un hash de todas sus geometrías (WKB) y sus valores.

Dos resultados con la misma huella son idénticos bit a bit (RNF05). La usa la prueba de
reproducibilidad, también desde un subproceso.
"""

import hashlib
from dataclasses import asdict


def huella(resultado) -> str:
    h = hashlib.sha256()

    def agregar(*valores):
        for valor in valores:
            h.update(valor.wkb if hasattr(valor, "wkb") else repr(valor).encode())

    for tramo in resultado.red.tramos():
        agregar(tramo.origen, tramo.destino, tramo.eje, tramo.jerarquia)
    for corredor in resultado.corredores:
        agregar(corredor)
    for manzana in resultado.manzanas:
        agregar(manzana)
    for celda in resultado.celdas:
        agregar(celda.designacion, celda.geometria, celda.frente, celda.fondo, celda.tipo)
    for incumplimiento in resultado.incumplimientos:
        agregar(incumplimiento.tipo, incumplimiento.elemento, incumplimiento.detalle, incumplimiento.geometria)
    for area in resultado.reservadas:
        agregar(area)
    agregar(asdict(resultado.indicadores))
    return h.hexdigest()


def huella_del_recalculo() -> str:
    """El recálculo de test_recalculo (el rectangular, M8 y M9 fijadas, a 45°), para repetirlo en un
    subproceso con otro PYTHONHASHSEED."""
    from dataclasses import replace

    from motor_trazados import MotorGeneracion
    from motor_trazados.referencia import solicitud_caso

    s = solicitud_caso("referencia")
    motor = MotorGeneracion()
    fijados = motor.fijar(motor.generar(s), ["M8", "M9"], s.estrategia.orientacion)
    nueva = replace(s, estrategia=replace(s.estrategia, orientacion=(s.estrategia.orientacion + 45) % 180))
    return huella(motor.recalcular(nueva, fijados))


if __name__ == "__main__":
    # Usado por test_reproducibilidad y test_recalculo en un subproceso con otro PYTHONHASHSEED:
    #     python huella.py [CASO | recalculo]
    import sys

    from motor_trazados import MotorGeneracion
    from motor_trazados.referencia import solicitud_caso

    argumento = sys.argv[1] if len(sys.argv) > 1 else "referencia"
    if argumento == "recalculo":
        print(huella_del_recalculo())
    else:
        print(huella(MotorGeneracion().generar(solicitud_caso(argumento))))
