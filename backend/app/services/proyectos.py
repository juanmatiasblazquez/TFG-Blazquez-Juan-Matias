"""Alta, consulta y parámetros de los proyectos (CU03, CU04 y CU05), y sus áreas reservadas
(CU04, paso 5; D59)."""

import psycopg.errors
from motor_trazados import coordenadas
from motor_trazados.contrato import validar_accesos, validar_reservadas, validar_terreno
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.errores import ErrorApi
from app.models import (
    Alternativa,
    AreaReservada,
    Cliente,
    ConjuntoParametros,
    Proyecto,
    PuntoAcceso,
    Terreno,
    Usuario,
)
from app.models.observacion import abiertas, bloqueantes
from app.models.proyecto import LISTO_PARA_GENERAR
from app.schemas.alternativa import EstrategiaOut, VersionResumen
from app.schemas.comunes import UsuarioResumen
from app.schemas.parametros import ParametrosIn
from app.schemas.proyecto import (
    AlternativaResumen,
    AreaReservadaIn,
    AreasReservadasIn,
    ProyectoIn,
    ProyectoOut,
    ProyectoResumen,
)
from app.services import clientes, parametros, terrenos
from app.services.conversiones import centesimos, coleccion, feature, guardable, numero
from app.services.solicitud import areas_reservadas, estrategia_sugerida, terreno_y_accesos


def crear(db: Session, datos: ProyectoIn, usuario: Usuario) -> Proyecto:
    """Registra el proyecto con su cliente, su terreno, sus accesos y el conjunto de parámetros
    v1: el que llegó o, si no llegó ninguno, el de referencia.

    Como llega todo junto (CU03 ejecuta CU04 y CU05), el proyecto queda «listo para generar»
    (CU03, paso 7). Valida con las mismas reglas que el motor, en metros.
    """
    terreno_4326 = datos.terreno.a_shapely()
    accesos_4326 = [acceso.ubicacion.a_shapely() for acceso in datos.accesos]
    srid = terrenos.sistema_de_calculo(datos.srid_calculo, terreno_4326)
    terreno = coordenadas.a_metros(terreno_4326, srid)
    accesos = [coordenadas.a_metros(acceso, srid) for acceso in accesos_4326]
    areas_4326 = [area.geometria.a_shapely() for area in datos.areas_reservadas]
    problemas = validar_terreno(terreno) + validar_accesos(accesos, terreno)
    if not problemas:
        # CU04, paso 6 y curso 6.a: las áreas, con la regla del motor (D59).
        problemas = validar_reservadas([coordenadas.a_metros(area, srid) for area in areas_4326], terreno, accesos)
    if problemas:
        raise ErrorApi(
            422,
            "El terreno no es válido.",
            "Corregí el polígono, los accesos o las áreas reservadas señalados (CU04).",
            [(parametros.campo_er(problema.campo), problema.mensaje) for problema in problemas],
        )
    cliente = db.get(Cliente, datos.id_cliente)
    if cliente is None:
        raise ErrorApi(
            422,
            "El cliente no existe.",
            "Elegí un cliente cargado o dalo de alta primero (CU03).",
            [("id_cliente", f"No existe el cliente {datos.id_cliente}.")],
        )
    if db.scalar(select(Proyecto.id_proyecto).where(Proyecto.codigo == datos.codigo)) is not None:
        raise _codigo_repetido(datos.codigo)

    proyecto = Proyecto(
        cliente=cliente,
        responsable=usuario,
        codigo=datos.codigo,
        nombre=datos.nombre,
        tipo=str(datos.tipo),
        ubicacion=datos.ubicacion,
        jurisdiccion=datos.jurisdiccion,
        srid_calculo=srid,
        estado=LISTO_PARA_GENERAR,
        terreno=Terreno(
            geom=guardable(terreno_4326),
            superficie_m2=centesimos(terreno.area),
            perimetro_m=centesimos(terreno.length),
            origen=datos.origen,
            accesos=[
                PuntoAcceso(geom=guardable(punto), ancho_m=acceso.ancho_m, via_vinculacion=acceso.via_vinculacion)
                for punto, acceso in zip(accesos_4326, datos.accesos, strict=True)
            ],
            areas_reservadas=_areas(datos.areas_reservadas, areas_4326),
        ),
    )
    if datos.parametros is None:
        conjunto = parametros.conjunto_de_referencia()
    else:
        conjunto = parametros.conjunto_desde(datos.parametros, version=1)
        parametros.validar(proyecto, conjunto, prefijo="parametros.")
    proyecto.conjuntos = [conjunto]
    db.add(proyecto)
    try:
        db.commit()
    except IntegrityError as error:
        # Dos altas simultáneas con el mismo código: la restricción única decide.
        db.rollback()
        if isinstance(error.orig, psycopg.errors.UniqueViolation):
            raise _codigo_repetido(datos.codigo) from error
        raise
    return proyecto


def reemplazar_areas(db: Session, id_proyecto: int, datos: AreasReservadasIn) -> Proyecto:
    """Las áreas reservadas del proyecto, enteras (CU04, paso 5; D59): las que llegan reemplazan a las
    que tenía, con la misma validación del alta, que es la del motor (`validar_reservadas`).

    Las versiones ya generadas no cambian: cada una guarda la copia de las áreas con las que se generó
    (`area_reservada_version`), con la que se reproduce y se recalcula (RNF05). Las generaciones
    nuevas usan las áreas nuevas."""
    proyecto = obtener(db, id_proyecto)
    db.execute(select(Proyecto.id_proyecto).where(Proyecto.id_proyecto == id_proyecto).with_for_update())
    terreno, accesos = terreno_y_accesos(proyecto)
    areas_4326 = [area.geometria.a_shapely() for area in datos.areas_reservadas]
    reservadas = [coordenadas.a_metros(area, proyecto.srid_calculo) for area in areas_4326]
    problemas = validar_reservadas(reservadas, terreno, accesos)
    if problemas:
        raise ErrorApi(
            422,
            "Las áreas reservadas no son válidas.",
            "Corregí las áreas o los accesos señalados (CU04, 6.a).",
            [(parametros.campo_er(problema.campo), problema.mensaje) for problema in problemas],
        )
    proyecto.terreno.areas_reservadas = _areas(datos.areas_reservadas, areas_4326)
    db.commit()
    return proyecto


def _areas(datos: list[AreaReservadaIn], areas_4326) -> list[AreaReservada]:
    """Las filas de las áreas, en el orden en que llegaron (R1, R2…), con el polígono tal cual."""
    return [
        AreaReservada(geom=guardable(area), clase=dato.clase, denominacion=dato.denominacion, destino=dato.destino)
        for area, dato in zip(areas_4326, datos, strict=True)
    ]


def configurar_parametros(db: Session, id_proyecto: int, datos: ParametrosIn) -> ConjuntoParametros:
    """CU05: una versión nueva del conjunto de parámetros, que pasa a ser la vigente.

    La anterior queda guardada: cada versión de alternativa conserva el conjunto con el que se
    generó (p. 49). Se valida con el motor antes de guardar (CU05, 3.a).
    """
    proyecto = obtener(db, id_proyecto)
    # Con el proyecto bloqueado, dos configuraciones simultáneas no toman el mismo número.
    db.execute(select(Proyecto.id_proyecto).where(Proyecto.id_proyecto == id_proyecto).with_for_update())
    ultima = db.scalar(select(func.max(ConjuntoParametros.version)).where(ConjuntoParametros.id_proyecto == id_proyecto))
    conjunto = parametros.conjunto_desde(datos, version=(ultima or 0) + 1)
    parametros.validar(proyecto, conjunto)

    # Primero deja de haber un vigente: el índice único parcial admite uno solo por proyecto.
    db.execute(
        update(ConjuntoParametros)
        .where(ConjuntoParametros.id_proyecto == id_proyecto, ConjuntoParametros.vigente)
        .values(vigente=False)
    )
    conjunto.proyecto = proyecto
    db.add(conjunto)
    db.commit()
    return conjunto


def obtener(db: Session, id_proyecto: int) -> Proyecto:
    proyecto = db.get(Proyecto, id_proyecto)
    if proyecto is None:
        raise ErrorApi(404, f"No existe el proyecto {id_proyecto}.")
    return proyecto


def listar(db: Session) -> list[ProyectoResumen]:
    """Todos los proyectos del estudio, del más nuevo al más viejo. Sin roles todavía, no se
    filtra por responsable (D31)."""
    consulta = (
        select(Proyecto)
        .options(selectinload(Proyecto.cliente), selectinload(Proyecto.terreno), selectinload(Proyecto.alternativas))
        .order_by(Proyecto.fecha_creacion.desc(), Proyecto.id_proyecto.desc())
    )
    return [
        ProyectoResumen(
            id_proyecto=p.id_proyecto,
            codigo=p.codigo,
            nombre=p.nombre,
            tipo=p.tipo,
            cliente=clientes.presentar(p.cliente),
            estado=p.estado,
            superficie_m2=float(p.terreno.superficie_m2),
            cantidad_alternativas=len(p.alternativas),
            fecha_creacion=p.fecha_creacion,
        )
        for p in db.scalars(consulta)
    ]


def presentar(proyecto: Proyecto) -> ProyectoOut:
    terreno = proyecto.terreno
    conjunto = proyecto.parametros_vigentes()
    sugerida = estrategia_sugerida(proyecto)
    return ProyectoOut(
        id_proyecto=proyecto.id_proyecto,
        codigo=proyecto.codigo,
        nombre=proyecto.nombre,
        tipo=proyecto.tipo,
        ubicacion=proyecto.ubicacion,
        jurisdiccion=proyecto.jurisdiccion,
        srid_calculo=proyecto.srid_calculo,
        estado=proyecto.estado,
        fecha_creacion=proyecto.fecha_creacion,
        cliente=clientes.presentar(proyecto.cliente),
        responsable=resumen_usuario(proyecto.responsable),
        terreno=feature(
            terreno.geom,
            {
                "superficie_m2": numero(terreno.superficie_m2),
                "perimetro_m": numero(terreno.perimetro_m),
                "origen": terreno.origen,
            },
        ),
        accesos=coleccion(
            [
                feature(
                    acceso.geom,
                    {
                        "id_punto_acceso": acceso.id_punto_acceso,
                        "designacion": designacion,
                        "ancho_m": numero(acceso.ancho_m),
                        "via_vinculacion": acceso.via_vinculacion,
                    },
                )
                for designacion, acceso in designaciones_de_accesos(proyecto)
            ]
        ),
        areas_reservadas=coleccion(
            [
                feature(
                    area.geom,
                    {
                        "id_area_reservada": area.id_area_reservada,
                        "designacion": f"R{k}",
                        "clase": area.clase,
                        "denominacion": area.denominacion,
                        "destino": area.destino,
                        "superficie_m2": float(centesimos(metros.area)),
                    },
                )
                for k, (area, metros) in enumerate(
                    zip(terreno.areas_reservadas, areas_reservadas(proyecto), strict=True), 1
                )
            ]
        ),
        parametros=None if conjunto is None else parametros.presentar_parametros(conjunto),
        estrategia_sugerida=EstrategiaOut(
            patron_red=str(sugerida.patron_red), orientacion_grados=sugerida.orientacion, semilla=sugerida.semilla
        ),
        alternativas=[resumen_alternativa(a) for a in proyecto.alternativas],
    )


def resumen_alternativa(alternativa: Alternativa) -> AlternativaResumen:
    """Una alternativa en el proyecto y en la selección (CU14): su estado, sus observaciones abiertas y
    sus versiones."""
    return AlternativaResumen(
        id_alternativa=alternativa.id_alternativa,
        codigo=alternativa.codigo,
        estado=alternativa.estado,
        fecha_creacion=alternativa.fecha_creacion,
        observaciones_abiertas=len(abiertas(alternativa)),
        bloqueantes_abiertas=len(bloqueantes(alternativa)),
        cumple_restricciones=alternativa.version_vigente().cumple_restricciones,
        cantidad_celdas=alternativa.version_vigente().cantidad_celdas,
        descripcion=alternativa.descripcion,
        versiones=resumen_versiones(alternativa),
    )


def designaciones_de_accesos(proyecto: Proyecto) -> list[tuple[str, PuntoAcceso]]:
    """A1, A2… en el orden de alta, el mismo con el que el motor los nombra (A{k})."""
    return [(f"A{k}", acceso) for k, acceso in enumerate(proyecto.terreno.accesos, 1)]


def resumen_versiones(alternativa: Alternativa) -> list[VersionResumen]:
    """Las versiones de una alternativa, de la primera a la vigente, con la de origen de cada
    recálculo (CU09): el proyecto y la alternativa las sirven igual."""
    return [
        VersionResumen(
            id_version=v.id_version,
            numero=v.numero,
            id_version_origen=v.id_version_origen,
            fecha_generacion=v.fecha_generacion,
            tipo=v.tipo,
        )
        for v in alternativa.versiones
    ]


def resumen_usuario(usuario: Usuario) -> UsuarioResumen:
    return UsuarioResumen(id_usuario=usuario.id_usuario, nombre=usuario.nombre, apellido=usuario.apellido)


def _codigo_repetido(codigo: str) -> ErrorApi:
    return ErrorApi(
        409,
        f"Ya existe un proyecto con el código «{codigo}».",
        "Usá otro código: identifica al proyecto en el estudio.",
        [("codigo", "Ya está en uso.")],
    )
