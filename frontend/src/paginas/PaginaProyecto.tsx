import type { Geometry } from "geojson";
import L from "leaflet";
import { useMemo, useState } from "react";

import type { ProyectoOut } from "../api/proyectos";
import { RayadoFijado } from "../components/CapasAlternativa";
import { GeometriaError } from "../components/GeometriaError";
import { BotonGenerar } from "../components/GenerarAlternativa";
import { BarraPagina, TarjetaSeccion } from "../components/Marco";
import { MapaBase } from "../components/MapaBase";
import { TerrenoYAccesos } from "../components/TerrenoYAccesos";
import { criterioEspacioVerde, estado, hectareas, metros, numero, tipoProyecto } from "../formato";
import { rutas } from "../hooks/useRuta";
import { useSesion } from "../hooks/useSesion";

// La página del proyecto (`#/proyectos/7`; D73). Las figuras no la muestran: es donde llevan las migas
// («Proyectos / Loteo … /») y desde donde se llega a cada alternativa (figura 17), a la comparación
// (figura 20), a los parámetros (figura 16), a las áreas reservadas y a lo compartido con el cliente.
export function PaginaProyecto({ proyecto: p, recargar }: { proyecto: ProyectoOut; recargar: () => void }) {
  const { puede } = useSesion();
  const [errorGeometria, setErrorGeometria] = useState<Geometry | null>(null);
  const [intento, setIntento] = useState(0);
  const encuadre = useMemo(() => L.geoJSON(p.terreno).getBounds(), [p]);
  const id = p.id_proyecto;

  return (
    <div className="vista">
      <BarraPagina
        migas={[{ texto: "Proyectos", href: rutas.proyectos }]}
        titulo={p.nombre}
        centro={
          <>
            <span className="insignia">{p.codigo}</span>
            <span className="insignia">Tipo: {tipoProyecto(p.tipo).toLowerCase()}</span>
            <span className="insignia insignia--info">{estado(p.estado)}</span>
          </>
        }
        acciones={
          <>
            {p.alternativas.length >= 2 && (
              <a className="boton" href={rutas.comparacion(id, [])}>
                Comparar
              </a>
            )}
            {puede("generar_alternativas") && (
              <BotonGenerar
                proyecto={p}
                onGenerada={recargar}
                onGeometriaError={(g) => {
                  setErrorGeometria(g);
                  setIntento((n) => n + 1);
                }}
              />
            )}
          </>
        }
      />
      <div className="vista__cuerpo">
        <div className="espacio">
          <aside className="panel">
            <TarjetaSeccion titulo={`Alternativas (${p.alternativas.length})`}>
              {p.alternativas.length === 0 ? (
                <p className="texto-tenue">
                  Todavía no hay alternativas de este proyecto.
                  {puede("generar_alternativas") ? " Generá la primera con «+ Generar alternativa»." : ""}
                </p>
              ) : (
                <ul className="lista-alternativas">
                  {p.alternativas.map((a) => {
                    const vigente = a.versiones.at(-1);
                    return (
                      <li key={a.id_alternativa}>
                        <div className="lista-alternativas__fila">
                          <a className="lista-alternativas__nombre" href={rutas.alternativa(id, a.codigo)}>
                            Alternativa {a.codigo}
                          </a>
                          <span className="texto-tenue">· v{vigente?.numero}</span>
                          <span className={`insignia ${a.cumple_restricciones ? "insignia--ok" : "insignia--error"}`}>
                            {a.cumple_restricciones ? "Conforme" : "No conforme"}
                          </span>
                          {a.estado !== "generada" && (
                            <span
                              className={`insignia ${a.estado === "observada" ? "insignia--aviso" : "insignia--info"}`}
                            >
                              {estado(a.estado)}
                            </span>
                          )}
                        </div>
                        <div className="texto-tenue">
                          {numero(a.cantidad_celdas, 0)} celdas útiles
                          {a.observaciones_abiertas > 0 && (
                            <>
                              {" · "}
                              <a href={rutas.observaciones(id, a.codigo)}>
                                {a.observaciones_abiertas === 1
                                  ? "1 observación abierta"
                                  : `${a.observaciones_abiertas} observaciones abiertas`}
                                {a.bloqueantes_abiertas > 0 &&
                                  ` (${a.bloqueantes_abiertas} bloqueante${a.bloqueantes_abiertas > 1 ? "s" : ""})`}
                              </a>
                            </>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </TarjetaSeccion>

            <TarjetaSeccion titulo="Proyecto">
              <dl className="filas">
                <dt>Código</dt>
                <dd>{p.codigo}</dd>
                <dt>Cliente</dt>
                <dd>{p.cliente.razon_social}</dd>
                {p.ubicacion && (
                  <>
                    <dt>Ubicación</dt>
                    <dd>{p.ubicacion}</dd>
                  </>
                )}
                {p.jurisdiccion && (
                  <>
                    <dt>Jurisdicción</dt>
                    <dd>{p.jurisdiccion}</dd>
                  </>
                )}
                <dt>Sistema de cálculo</dt>
                <dd>EPSG:{p.srid_calculo}</dd>
                <dt>Superficie del terreno</dt>
                <dd>{hectareas(p.terreno.properties.superficie_m2)}</dd>
                <dt>Perímetro</dt>
                <dd>{metros(p.terreno.properties.perimetro_m)}</dd>
              </dl>
            </TarjetaSeccion>

            <TarjetaSeccion titulo="Accesos y áreas reservadas">
              <ul className="lista-versiones">
                {p.accesos.features.map((a) => (
                  <li key={a.properties.id_punto_acceso}>
                    <span>
                      <strong>{a.properties.designacion}</strong> {a.properties.via_vinculacion ?? "Acceso"}
                    </span>
                    <span className="texto-tenue">
                      {a.properties.ancho_m === null ? "" : `ancho ${metros(a.properties.ancho_m)}`}
                    </span>
                  </li>
                ))}
                {p.areas_reservadas.features.map((a) => (
                  <li key={a.properties.id_area_reservada}>
                    <span>
                      <strong>{a.properties.designacion}</strong> {a.properties.denominacion}
                    </span>
                    <span className="texto-tenue">{hectareas(a.properties.superficie_m2)}</span>
                  </li>
                ))}
              </ul>
            </TarjetaSeccion>

            <TarjetaSeccion titulo="Secciones del proyecto">
              <div className="enlaces-proyecto">
                <a href={rutas.parametros(id)}>
                  Parámetros{p.parametros ? ` (versión ${p.parametros.version} vigente)` : ""}
                </a>
                {p.parametros?.loteo?.criterio_espacio_verde && (
                  <span className="texto-tenue">
                    Criterio del verde: {criterioEspacioVerde(p.parametros.loteo.criterio_espacio_verde)}
                  </span>
                )}
                <a href={rutas.areas(id)}>Áreas reservadas ({p.areas_reservadas.features.length})</a>
                {puede("compartir_alternativas") && <a href={rutas.compartir(id)}>Compartir con el cliente</a>}
                {p.alternativas.length >= 2 && <a href={rutas.comparacion(id, [])}>Comparar alternativas</a>}
              </div>
            </TarjetaSeccion>
          </aside>
          <div className="espacio__mapa">
            <RayadoFijado />
            <MapaBase encuadre={encuadre}>
              <TerrenoYAccesos proyecto={p} conAreas />
              <GeometriaError geometria={errorGeometria} clave={intento} />
            </MapaBase>
          </div>
        </div>
      </div>
    </div>
  );
}
