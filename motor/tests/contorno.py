"""La calle de borde en todo el contorno (D50).

Hasta el motor 0.10.x era la única; desde el 0.11.0 el valor de referencia es «por lado» y el contorno
es la casilla del portal (D86). Las pruebas de lo que es propio de ella (las calles de borde como
avenidas, las transversales de más del triángulo, los números del rectangular de la D50) la piden con
`con_contorno`, y así siguen probando lo mismo que antes.
"""

from dataclasses import replace

from motor_trazados import CalleBorde, SolicitudGeneracion


def con_contorno(solicitud: SolicitudGeneracion) -> SolicitudGeneracion:
    return replace(solicitud, parametros=replace(solicitud.parametros, calle_borde=CalleBorde.CONTORNO))
