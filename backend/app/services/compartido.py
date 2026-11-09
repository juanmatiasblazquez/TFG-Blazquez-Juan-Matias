"""Lo que ve el cliente por un enlace (CU15, RF16; prototipo de la p. 51; D70).

Arma los schemas propios de `app.schemas.compartido` campo por campo, sin pasar por los del estudio: lo que
no está acá no sale, aunque el modelo lo tenga. Las versiones son las del enlace (`enlace_version`), no las
vigentes: lo que se generó después de compartir no se ve.
"""

from app.core.config import settings
from app.core.errores import ErrorApi
from app.models import EnlaceCompartido, EnlaceVersion, Usuario
from app.schemas.compartido import (
    AlternativaCompartidaOut,
    CapasCompartidasOut,
    CompartidoOut,
    CompartidoPorOut,
    IndicadoresCompartidosOut,
    ProyectoCompartidoOut,
)
from app.services import proyectos
from app.services.conversiones import coleccion, feature
from app.services.generacion import indicadores_de


def _orden(codigo: str) -> tuple[int, str]:
    # A, B… Z, AA (`generacion.codigo_alternativa`).
    return len(codigo), codigo


def compartido_por(usuario: Usuario) -> CompartidoPorOut:
    """«L. Ferreyra»: la inicial del nombre y el apellido, y el rol (p. 51; D75). Ni el correo ni el id."""
    inicial = usuario.nombre.strip()[:1]
    nombre = f"{inicial}. {usuario.apellido.strip()}" if inicial else usuario.apellido.strip()
    return CompartidoPorOut(nombre=nombre, rol=usuario.rol)


def presentar(enlace: EnlaceCompartido) -> CompartidoOut:
    """CU15, paso 3: los datos del proyecto, las alternativas compartidas y quién compartió."""
    proyecto = enlace.proyecto
    return CompartidoOut(
        estudio=settings.nombre_estudio.strip() or None,
        proyecto=ProyectoCompartidoOut(
            nombre=proyecto.nombre,
            ubicacion=proyecto.ubicacion,
            cliente=proyecto.cliente.razon_social,
            superficie_terreno_m2=float(proyecto.terreno.superficie_m2),
        ),
        alternativas=sorted((ev.version.alternativa.codigo for ev in enlace.versiones), key=_orden),
        compartido_por=compartido_por(enlace.usuario),
        vence=enlace.fecha_vencimiento,
    )


def version_compartida(enlace: EnlaceCompartido, codigo: str) -> EnlaceVersion:
    """La versión que el enlace comparte de esa alternativa, con la descripción que tenía al compartir. 404
    si el enlace no la comparte: para el cliente, las demás alternativas no existen."""
    for enlace_version in enlace.versiones:
        if enlace_version.version.alternativa.codigo == codigo:
            return enlace_version
    raise ErrorApi(404, f"Este enlace no comparte la alternativa {codigo}.", "Elegí una de las alternativas del enlace.")


def presentar_alternativa(enlace_version: EnlaceVersion) -> AlternativaCompartidaOut:
    """CU15, paso 5: el trazado sobre cartografía, los indicadores principales de la p. 51 y la descripción
    del trazado que tenía la alternativa al compartir (D76)."""
    version = enlace_version.version
    alternativa = version.alternativa
    proyecto = alternativa.proyecto
    terreno = proyecto.terreno
    indicadores = indicadores_de(version, terreno)
    jerarquia_de = {j.id_jerarquia: j.nombre for j in version.conjunto.jerarquias}
    return AlternativaCompartidaOut(
        codigo=alternativa.codigo,
        descripcion=enlace_version.descripcion,
        indicadores=IndicadoresCompartidosOut(
            cantidad_lotes=indicadores.cantidad_celdas,
            superficie_media_lote_m2=indicadores.superficie_media_celda_m2,
            superficie_aprovechable_m2=indicadores.superficie_aprovechable_m2,
            porcentaje_aprovechamiento=indicadores.porcentaje_aprovechamiento,
            superficie_espacio_verde_m2=indicadores.superficie_espacio_verde_m2,
            porcentaje_espacio_verde=indicadores.porcentaje_espacio_verde,
            longitud_red_m=indicadores.longitud_red_m,
            superficie_terreno_m2=float(terreno.superficie_m2),
        ),
        capas=CapasCompartidasOut(
            terreno=feature(terreno.geom, {}),
            accesos=coleccion(
                [
                    feature(acceso.geom, {"designacion": designacion})
                    for designacion, acceso in proyectos.designaciones_de_accesos(proyecto)
                ]
            ),
            calles=coleccion(
                [
                    feature(t.geom, {"jerarquia": jerarquia_de[t.id_jerarquia]})
                    for t in version.tramos
                    if t.geom is not None
                ]
            ),
            manzanas=coleccion([feature(m.geom, {"designacion": m.designacion}) for m in version.manzanas]),
            celdas=coleccion([feature(c.geom, {"designacion": c.designacion, "tipo": c.tipo}) for c in version.celdas]),
            areas_reservadas=coleccion(
                [
                    feature(a.geom, {"designacion": a.designacion, "denominacion": a.denominacion})
                    for a in version.areas_reservadas
                ]
            ),
        ),
    )
