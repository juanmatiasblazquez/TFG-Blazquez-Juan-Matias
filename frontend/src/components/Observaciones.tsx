// Leaflet-Geoman se engancha al `L` global que deja Leaflet: se importa después (D37).
import L from "leaflet";
import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";
import type { Geometry, Polygon } from "geojson";
import { useEffect, useRef, useState } from "react";
import { GeoJSON, useMap } from "react-leaflet";

import type { ErrorOut } from "../api/errores";
import {
  cambiarEstadoObservacion,
  listarObservaciones,
  medirSector,
  registrarObservacion,
  responderObservacion,
  type ObservacionOut,
  type SectorMedidoOut,
} from "../api/observaciones";
import {
  ACCIONES_RESPUESTA,
  accionRespuesta,
  CRITICIDADES,
  criticidad,
  estadoObservacion,
  fechaHoraLarga,
  TIPOS_OBSERVACION,
  tipoObservacion,
  type NumeroEscrito,
} from "../formato";
import { useConsulta, type Consulta } from "../hooks/useConsulta";
import { rutas } from "../hooks/useRuta";
import { AvisoError } from "./AvisoError";
import { COLORES } from "./CapasAlternativa";
import { poligonoGeoJSON } from "./EditorTerreno";
import type { Fijar } from "./FijarSectores";
import { nombreCorto } from "./Marco";

// Observaciones (CU11, CU12; pantalla de la p. 50; D69).
//
// - Registrar (el director técnico): tipo, criticidad, detalle y, si se quiere, el sector afectado
//   dibujado sobre el mapa. Si el sector sale del terreno, la API responde 422 con la parte de afuera,
//   que se marca en el mapa para dibujarlo de nuevo (3.a).
// - Responder (el director técnico o el proyectista): al elegir una observación se resalta su sector. Con
//   un comentario (3.b) o con un recálculo (3.a): abre el modo «Fijar sectores» y la versión que resulta
//   queda vinculada a la respuesta.
// - Cerrar (conforme) o reabrir una respondida (el director técnico).
// Qué valores sirven y qué estados cambian lo decide la API (D37).

type FormObservacion = { tipo: string; criticidad: string; descripcion: string };
const FORM_VACIO: FormObservacion = { tipo: "", criticidad: "", descripcion: "" };

export type Observaciones = {
  lista: Consulta<ObservacionOut[]>;
  elegida: number | null;
  elegir: (id: number | null) => void;
  // El formulario de una observación nueva, abierto o no, y su sector dibujado.
  formulario: FormObservacion | null;
  setFormulario: (f: FormObservacion | null) => void;
  sector: Polygon | null;
  setSector: (s: Polygon | null) => void;
  error: ErrorOut | null;
  setError: (e: ErrorOut | null) => void;
  // Cada intento redibuja la geometría del error: react-leaflet no redibuja si cambian los datos.
  intento: number;
  sumarIntento: () => void;
};

export function useObservaciones(idAlternativa: number | null): Observaciones {
  const lista = useConsulta(idAlternativa === null ? null : `observaciones:${idAlternativa}`, (c) =>
    listarObservaciones(idAlternativa!, c),
  );
  const [elegida, elegir] = useState<number | null>(null);
  const [formulario, setFormulario] = useState<FormObservacion | null>(null);
  const [sector, setSector] = useState<Polygon | null>(null);
  const [error, setError] = useState<ErrorOut | null>(null);
  const [intento, setIntento] = useState(0);
  return {
    lista,
    elegida,
    elegir,
    formulario,
    setFormulario,
    sector,
    setSector,
    error,
    setError,
    intento,
    sumarIntento: () => setIntento((n) => n + 1),
  };
}

// B13 (figura 19; D79): el sector que se está dibujando, medido por la API como al registrarlo: su superficie
// y, si sale del terreno, cuánto y dónde (CU11, 3.a), antes de registrar.
export function useMedicionSector(idVersion: number | null, sector: Polygon | null): SectorMedidoOut | null {
  const clave = idVersion !== null && sector ? `sector:${idVersion}:${JSON.stringify(sector.coordinates)}` : null;
  return useConsulta(clave, (c) => medirSector(idVersion!, sector!, c)).datos;
}

// --- El panel -----------------------------------------------------------------------------------

type PropsPanel = {
  obs: Observaciones;
  idProyecto: number;
  codigo: string;
  // La versión vigente: las observaciones se registran sobre ella.
  idVersionVigente: number;
  numeroVigente: number;
  puedeRegistrar: boolean;
  puedeResponder: boolean;
  // Responder con un recálculo: abre el modo «Fijar sectores» con esta observación (CU12, 3.a).
  onResponderConRecalculo: (observacion: ObservacionOut, descripcion: string) => void;
  // Algo cambió: el estado de la alternativa, sus contadores.
  onCambio: () => void;
};

export function PanelObservaciones(props: PropsPanel) {
  const { obs, codigo, numeroVigente, puedeRegistrar } = props;
  const [guardando, setGuardando] = useState(false);
  const lista = obs.lista.datos ?? [];
  const abiertas = lista.filter((o) => o.estado === "abierta").length;
  const problemas = Object.fromEntries((obs.error?.problemas ?? []).map((x) => [x.campo, x.mensaje]));

  async function registrar() {
    if (!obs.formulario) return;
    setGuardando(true);
    obs.setError(null);
    obs.sumarIntento();
    const { tipo, criticidad: crit, descripcion } = obs.formulario;
    // Lo que falta no se manda: la API responde «Falta este dato» en ese campo (D37).
    const cuerpo = {
      ...(tipo ? { tipo } : {}),
      ...(crit ? { criticidad: crit } : {}),
      ...(descripcion ? { descripcion } : {}),
      sector: obs.sector,
    };
    const resultado = await registrarObservacion(props.idVersionVigente, cuerpo);
    setGuardando(false);
    if (resultado.ok) {
      obs.setFormulario(null);
      obs.setSector(null);
      obs.elegir(resultado.datos.id_observacion);
      obs.lista.recargar();
      props.onCambio();
    } else {
      obs.setError(resultado.error);
    }
  }

  const formulario = obs.formulario && (
    <form
      className="tarjeta-seccion tarjeta-seccion--aviso observacion-nueva"
      aria-label="Nueva observación"
      onSubmit={(e) => {
        e.preventDefault();
        void registrar();
      }}
    >
      <h3 className="titulo-seccion">Nueva observación sobre la versión {numeroVigente}</h3>
      <div className="fila-campos fila-campos--dos">
        <div className={`campo ${problemas.tipo ? "campo--error" : ""}`}>
          <label htmlFor="observacion-tipo">Tipo</label>
          <select
            id="observacion-tipo"
            value={obs.formulario.tipo}
            onChange={(e) => obs.setFormulario({ ...obs.formulario!, tipo: e.target.value })}
          >
            <option value="">Elegí un tipo…</option>
            {TIPOS_OBSERVACION.map(([valor, nombre]) => (
              <option key={valor} value={valor}>
                {nombre}
              </option>
            ))}
          </select>
          {problemas.tipo && <p className="campo__problema">{problemas.tipo}</p>}
        </div>
        <fieldset className={`campo ${problemas.criticidad ? "campo--error" : ""}`}>
          <legend>Criticidad</legend>
          <div className="opciones">
            {CRITICIDADES.map(([valor, nombre]) => (
              <label key={valor}>
                <input
                  type="radio"
                  name="observacion-criticidad"
                  value={valor}
                  checked={obs.formulario!.criticidad === valor}
                  onChange={() => obs.setFormulario({ ...obs.formulario!, criticidad: valor })}
                />
                {nombre}
              </label>
            ))}
          </div>
          {problemas.criticidad && <p className="campo__problema">{problemas.criticidad}</p>}
        </fieldset>
      </div>
      <div className={`campo ${problemas.descripcion ? "campo--error" : ""}`}>
        <label htmlFor="observacion-descripcion">Descripción</label>
        <textarea
          id="observacion-descripcion"
          rows={3}
          value={obs.formulario.descripcion}
          onChange={(e) => obs.setFormulario({ ...obs.formulario!, descripcion: e.target.value })}
        />
        {problemas.descripcion && <p className="campo__problema">{problemas.descripcion}</p>}
      </div>
      <div className={`campo ${problemas.sector ? "campo--error" : ""}`}>
        <p className="observacion-nueva__sector">
          <span className="texto-tenue">Sector afectado (opcional)</span>
          {obs.sector ? (
            <span>
              <span className="texto-naranja">Dibujado sobre el mapa</span>{" "}
              <button type="button" className="boton boton--chico" onClick={() => obs.setSector(null)}>
                Borrar el sector
              </button>
            </span>
          ) : (
            <span className="texto-tenue">Dibujalo con la barra del mapa, dentro del terreno</span>
          )}
        </p>
        {problemas.sector && <p className="campo__problema">{problemas.sector}</p>}
      </div>
      {obs.error && <AvisoError error={obs.error} titulo="No se registró la observación" />}
      <div className="acciones acciones--derecha">
        <button
          type="button"
          className="boton"
          onClick={() => {
            obs.setFormulario(null);
            obs.setSector(null);
            obs.setError(null);
          }}
        >
          Cancelar
        </button>
        <button type="submit" className="boton boton--primario" disabled={guardando}>
          {guardando ? "Registrando…" : "Registrar observación"}
        </button>
      </div>
    </form>
  );

  return (
    <section className="panel__seccion observaciones" aria-label="Observaciones">
      <div className="panel__encabezado">
        <span className="texto-tenue">
          {lista.length === 0 ? "" : `${abiertas === 1 ? "1 abierta" : `${abiertas} abiertas`} de ${lista.length}`}
        </span>
        {puedeRegistrar && !obs.formulario && (
          <button
            type="button"
            className="boton"
            onClick={() => {
              obs.setError(null);
              obs.setSector(null);
              obs.setFormulario(FORM_VACIO);
            }}
          >
            Agregar observación
          </button>
        )}
      </div>

      {obs.lista.error && <AvisoError error={obs.lista.error} titulo="No se pudieron leer las observaciones" />}
      {obs.lista.datos && lista.length === 0 && (
        <p className="texto-tenue">La alternativa {codigo} no tiene observaciones.</p>
      )}
      <ul className="lista-observaciones">
        {lista.map((o) => (
          <TarjetaObservacion
            key={o.id_observacion}
            observacion={o}
            elegida={obs.elegida === o.id_observacion}
            {...props}
          />
        ))}
      </ul>
      {formulario}
    </section>
  );
}

function TarjetaObservacion({
  observacion: o,
  elegida,
  obs,
  idProyecto,
  codigo,
  puedeRegistrar,
  puedeResponder,
  onResponderConRecalculo,
  onCambio,
}: PropsPanel & { observacion: ObservacionOut; elegida: boolean }) {
  const [respuesta, setRespuesta] = useState<{ accion: string; descripcion: string } | null>(null);
  const [error, setError] = useState<ErrorOut | null>(null);
  const [ocupado, setOcupado] = useState(false);

  async function hacer(accion: () => ReturnType<typeof responderObservacion>) {
    setOcupado(true);
    setError(null);
    const resultado = await accion();
    setOcupado(false);
    if (resultado.ok) {
      setRespuesta(null);
      obs.lista.recargar();
      onCambio();
    } else {
      setError(resultado.error);
    }
  }

  function responder() {
    if (!respuesta) return;
    if (respuesta.accion === "recalculo_parcial") {
      onResponderConRecalculo(o, respuesta.descripcion);
      return;
    }
    void hacer(() =>
      responderObservacion(o.id_observacion, {
        ...(respuesta.accion ? { accion: respuesta.accion } : {}),
        descripcion: respuesta.descripcion,
        recalculo: null,
      }),
    );
  }

  return (
    <li
      className={`observacion ${elegida ? "observacion--elegida" : ""}`}
      data-designacion={o.designacion}
      onClick={() => obs.elegir(elegida ? null : o.id_observacion)}
    >
      <div className="observacion__insignias">
        <span
          className={`insignia ${o.criticidad === "bloqueante" ? "insignia--codigo" : "insignia--codigo-sugerida"}`}
        >
          {o.designacion}
        </span>
        <span className="insignia">{tipoObservacion(o.tipo)}</span>
        <span className={`insignia ${o.criticidad === "bloqueante" ? "insignia--error" : "insignia--info"}`}>
          {criticidad(o.criticidad)}
        </span>
        <span className={`insignia observacion__estado ${o.estado === "abierta" ? "insignia--aviso" : "insignia--ok"}`}>
          {estadoObservacion(o.estado)}
        </span>
      </div>
      <p className="observacion__descripcion">{o.descripcion}</p>
      <p className="texto-tenue">
        {nombreCorto(o.emisor.nombre, o.emisor.apellido)} · {fechaHoraLarga(o.fecha_emision)} · sobre la versión{" "}
        {o.numero_version}
        {o.sector ? " · sector marcado en el mapa" : ""}
        {o.fecha_cierre ? ` · cerrada el ${fechaHoraLarga(o.fecha_cierre)}` : ""}
      </p>
      {o.respuestas.map((r) => (
        <div className="observacion__respuesta" key={r.id_respuesta}>
          <strong>{accionRespuesta(r.accion)}</strong> · {nombreCorto(r.usuario.nombre, r.usuario.apellido)} ·{" "}
          {fechaHoraLarga(r.fecha)}
          {r.numero_version_resultante !== null && (
            <>
              {" · "}
              <a
                href={rutas.version(idProyecto, codigo, r.numero_version_resultante)}
                onClick={(e) => e.stopPropagation()}
              >
                versión {r.numero_version_resultante}
              </a>
            </>
          )}
          <p>{r.descripcion}</p>
        </div>
      ))}

      {/* Las acciones no eligen ni sueltan la observación. */}
      <div onClick={(e) => e.stopPropagation()}>
        {o.estado === "abierta" && puedeResponder && !respuesta && (
          <button
            type="button"
            className="boton boton--chico"
            onClick={() => setRespuesta({ accion: "", descripcion: "" })}
          >
            Responder
          </button>
        )}
        {respuesta && (
          <div className="subformulario observacion__responder" aria-label={`Responder ${o.designacion}`}>
            <div className="campo">
              <label htmlFor={`accion-${o.id_observacion}`}>Acción</label>
              <select
                id={`accion-${o.id_observacion}`}
                value={respuesta.accion}
                onChange={(e) => setRespuesta({ ...respuesta, accion: e.target.value })}
              >
                <option value="">Elegí una acción…</option>
                {ACCIONES_RESPUESTA.map(([valor, nombre]) => (
                  <option key={valor} value={valor}>
                    {nombre}
                  </option>
                ))}
              </select>
            </div>
            <div className="campo">
              <label htmlFor={`respuesta-${o.id_observacion}`}>Respuesta</label>
              <textarea
                id={`respuesta-${o.id_observacion}`}
                rows={3}
                value={respuesta.descripcion}
                onChange={(e) => setRespuesta({ ...respuesta, descripcion: e.target.value })}
              />
            </div>
            {respuesta.accion === "recalculo_parcial" && (
              <p className="texto-tenue">
                Se abre «Fijar sectores» sobre la versión vigente: conservá las manzanas que están bien y se recalcula
                el resto. La versión nueva queda vinculada a esta respuesta.
              </p>
            )}
            <div className="acciones">
              <button type="button" className="boton boton--primario" disabled={ocupado} onClick={responder}>
                {respuesta.accion === "recalculo_parcial"
                  ? "Elegir lo que se conserva"
                  : ocupado
                    ? "Respondiendo…"
                    : "Responder"}
              </button>
              <button type="button" className="boton" onClick={() => setRespuesta(null)}>
                Cancelar
              </button>
            </div>
          </div>
        )}
        {o.estado === "respondida" && puedeRegistrar && (
          <div className="acciones">
            <button
              type="button"
              className="boton boton--chico"
              disabled={ocupado}
              title="Conforme con la respuesta (Anexo 1.5): la observación queda cerrada"
              onClick={() => void hacer(() => cambiarEstadoObservacion(o.id_observacion, "cerrada"))}
            >
              Cerrar
            </button>
            <button
              type="button"
              className="boton boton--chico"
              disabled={ocupado}
              title="La respuesta no alcanza: vuelve a abierta y, si es bloqueante, a impedir compartir"
              onClick={() => void hacer(() => cambiarEstadoObservacion(o.id_observacion, "abierta"))}
            >
              Reabrir
            </button>
          </div>
        )}
        {error && <AvisoError error={error} titulo="No se pudo" />}
      </div>
    </li>
  );
}

// Lo que manda «Recalcular y responder» (CU12, 3.a): lo elegido en «Fijar sectores», sobre la versión
// vigente, y la estrategia confirmada.
export function pedirRespuestaConRecalculo(
  fijar: Fijar,
  idObservacion: number,
  descripcion: string,
  patronRed: string,
  orientacion: NumeroEscrito,
  semilla: NumeroEscrito,
) {
  return responderObservacion(idObservacion, {
    accion: "recalculo_parcial",
    descripcion,
    recalculo: {
      id_version: fijar.idVersion,
      manzanas: fijar.manzanas,
      estrategia: { patron_red: patronRed, orientacion_grados: orientacion, semilla },
    },
  });
}

// --- El mapa ------------------------------------------------------------------------------------

const ESTILO_SECTOR: L.PathOptions = {
  color: COLORES.incumplimiento,
  weight: 2,
  dashArray: "8 5",
  fillColor: COLORES.incumplimiento,
  fillOpacity: 0.06,
};
const ESTILO_SECTOR_RESPONDIDO: L.PathOptions = { ...ESTILO_SECTOR, color: "#7b8794", fillColor: "#7b8794" };
const ESTILO_SECTOR_ELEGIDO: L.PathOptions = { ...ESTILO_SECTOR, weight: 3.5, fillOpacity: 0.18 };
const ESTILO_NUEVO: L.PathOptions = {
  color: "#d9822b",
  weight: 2.5,
  dashArray: "4 4",
  fillColor: "#f2b56b",
  fillOpacity: 0.22,
};
const ESTILO_ERROR: L.PathOptions = {
  color: COLORES.incumplimiento,
  weight: 3,
  fillColor: COLORES.incumplimiento,
  fillOpacity: 0.45,
};

type PropsCapa = {
  // La parte del sector dibujado que sale del terreno, según la vista previa (B13).
  afuera?: Geometry | null;
  obs: Observaciones;
  // Mientras se responde con un recálculo, solo se resalta esa observación y no se dibuja nada.
  soloLaElegida?: boolean;
};

// Los sectores afectados (el elegido, resaltado y encuadrado), el sector que se está dibujando y, si la API
// lo rechazó, la parte que sale del terreno.
export function CapaObservaciones({ obs, soloLaElegida = false, afuera = null }: PropsCapa) {
  const lista = (obs.lista.datos ?? []).filter((o) => o.sector && (!soloLaElegida || o.id_observacion === obs.elegida));
  const errorGeometria = obs.error?.geometria as Geometry | null | undefined;
  return (
    <>
      {lista.map((o) => (
        <GeoJSON
          key={`sector-${o.id_observacion}-${obs.elegida === o.id_observacion}-${o.estado}`}
          data={o.sector!}
          style={
            obs.elegida === o.id_observacion
              ? ESTILO_SECTOR_ELEGIDO
              : o.estado === "abierta"
                ? ESTILO_SECTOR
                : ESTILO_SECTOR_RESPONDIDO
          }
          onEachFeature={(_, capa) =>
            capa.bindTooltip(o.designacion, { permanent: true, direction: "center", className: "etiqueta-observacion" })
          }
          eventHandlers={{ click: () => obs.elegir(o.id_observacion) }}
        />
      ))}
      <Encuadrar sector={(obs.lista.datos ?? []).find((o) => o.id_observacion === obs.elegida)?.sector ?? null} />
      {obs.sector && (
        <GeoJSON key={`nuevo-${JSON.stringify(obs.sector.coordinates[0][0])}`} data={obs.sector} style={ESTILO_NUEVO} />
      )}
      {errorGeometria && <GeoJSON key={`error-${obs.intento}`} data={errorGeometria} style={ESTILO_ERROR} />}
      {afuera && !errorGeometria && (
        <GeoJSON key={`afuera-${JSON.stringify(afuera).slice(0, 80)}`} data={afuera} style={ESTILO_ERROR} />
      )}
      {obs.formulario && !soloLaElegida && <DibujarSector onSector={obs.setSector} />}
    </>
  );
}

function Encuadrar({ sector }: { sector: Polygon | null }) {
  const mapa = useMap();
  const clave = sector ? JSON.stringify(sector.coordinates[0][0]) : null;
  useEffect(() => {
    // Sin animación, como el encuadre de `MapaBase`.
    if (sector) mapa.fitBounds(L.geoJSON(sector).getBounds(), { padding: [80, 80], maxZoom: 18, animate: false });
    // Solo cuando cambia la elegida (la clave), no en cada render.
  }, [mapa, clave]);
  return null;
}

// Textos de la barra (RNF01): dicen qué se dibuja acá.
const TEXTOS: L.PM.Translations = {
  buttonTitles: {
    drawPolyButton: "Dibujar el sector afectado",
    drawRectButton: "Dibujar el sector afectado como un rectángulo",
  },
};

function DibujarSector({ onSector }: { onSector: (sector: Polygon) => void }) {
  const mapa = useMap();
  const avisar = useRef(onSector);
  useEffect(() => {
    avisar.current = onSector;
  });

  useEffect(() => {
    mapa.pm.setLang("es", TEXTOS, "es");
    mapa.pm.setGlobalOptions({ snappable: true, allowSelfIntersection: false, pathOptions: ESTILO_NUEVO });
    mapa.pm.addControls({
      position: "topleft",
      drawPolygon: true,
      drawRectangle: true,
      drawMarker: false,
      drawPolyline: false,
      drawCircle: false,
      drawCircleMarker: false,
      drawText: false,
      editMode: false,
      dragMode: false,
      cutPolygon: false,
      rotateMode: false,
      removalMode: false,
    });
    // El sector queda en el estado, con la precisión completa (D37), y el mapa lo dibuja desde ahí.
    const alCrear = ({ layer }: { layer: L.Layer }) => {
      if (layer instanceof L.Polygon) {
        const sector = poligonoGeoJSON(layer);
        mapa.removeLayer(layer);
        avisar.current(sector);
      }
    };
    mapa.on("pm:create", alCrear);
    return () => {
      mapa.off("pm:create", alCrear);
      mapa.pm.disableDraw();
      mapa.pm.removeControls();
    };
  }, [mapa]);

  return null;
}
