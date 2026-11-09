// Leaflet-Geoman se engancha al `L` global que deja Leaflet: se importa después (D37).
import L from "leaflet";
import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";
import type { Feature, Geometry, Polygon } from "geojson";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { GeoJSON, useMap } from "react-leaflet";

import type { AlternativaOut, ManzanaProps, VersionOut } from "../api/alternativas";
import type { ErrorOut } from "../api/errores";
import { recalcular, verSector, type SectorOut } from "../api/versiones";
import { escribirNumero, hectareas, leerNumero, metrosCuadrados, numero, patron, porcentaje } from "../formato";
import { AvisoError } from "./AvisoError";
import { COLORES, ESTILO_FIJADO } from "./CapasAlternativa";
import { TarjetaSeccion } from "./Marco";
import { poligonoGeoJSON } from "./EditorTerreno";

// CU09 (pantalla de la p. 50; D56): fijar manzanas de una versión y recalcular el resto.
//
// - Un clic en una manzana (sobre sus lotes) la elige o la suelta.
// - Un contorno dibujado suma las manzanas que quedan enteras adentro: lo resuelve la API, que
//   devuelve la lista; el contorno se borra y queda la elección por manzanas.
// - Cada cambio pide la vista previa (paso 3): el sector con sus calles, los anclajes y sus
//   indicadores. Qué se fija y si abarca todo el terreno lo decide la API con el motor (D37).

export type Fijar = {
  idVersion: number;
  manzanas: string[];
  vista: SectorOut | null;
  error: ErrorOut | null;
  consultando: boolean;
  alternar: (designacion: string) => void;
  sumarContorno: (contorno: Polygon) => void;
  soltarTodo: () => void;
};

const iguales = (a: string[], b: string[]) => a.length === b.length && a.every((x, k) => x === b[k]);

export function useFijarSectores(idVersion: number): Fijar {
  const [manzanas, setManzanas] = useState<string[]>([]);
  const [vista, setVista] = useState<SectorOut | null>(null);
  const [error, setError] = useState<ErrorOut | null>(null);
  const [consultando, setConsultando] = useState(false);
  // Solo vale la respuesta del último pedido; `elegidas` es la elección sin esperar al render.
  const pedido = useRef(0);
  const elegidas = useRef<string[]>([]);

  const elegir = useCallback((nuevas: string[]) => {
    elegidas.current = nuevas;
    setManzanas(nuevas);
  }, []);

  const soltarTodo = useCallback(() => {
    pedido.current++;
    elegir([]);
    setVista(null);
    setError(null);
    setConsultando(false);
  }, [elegir]);

  // Otra versión, otra elección.
  const [deVersion, setDeVersion] = useState(idVersion);
  if (deVersion !== idVersion) {
    setDeVersion(idVersion);
    soltarTodo();
  }

  const pedir = useCallback(
    async (manzanasPedidas: string[], contorno: Polygon | null) => {
      const n = ++pedido.current;
      setConsultando(true);
      const resultado = await verSector(idVersion, { manzanas: manzanasPedidas, contorno });
      if (n !== pedido.current) return;
      setConsultando(false);
      if (resultado.ok) {
        // La API ordena y suma las del contorno: esa es la elección.
        elegir(resultado.datos.manzanas);
        setVista(resultado.datos);
        setError(null);
      } else {
        // Sin vista previa válida, lo elegido queda marcado sin el sector.
        setVista(null);
        setError(resultado.error);
      }
    },
    [idVersion, elegir],
  );

  const alternar = useCallback(
    (designacion: string) => {
      const actuales = elegidas.current;
      const nuevas = actuales.includes(designacion)
        ? actuales.filter((m) => m !== designacion)
        : [...actuales, designacion];
      if (nuevas.length === 0) {
        soltarTodo();
        return;
      }
      elegir(nuevas);
      void pedir(nuevas, null);
    },
    [elegir, pedir, soltarTodo],
  );

  const sumarContorno = useCallback((contorno: Polygon) => void pedir(elegidas.current, contorno), [pedir]);

  // Mientras la vista previa sea de otra elección, no se muestra: se espera la respuesta.
  const vigente = vista && iguales(vista.manzanas, manzanas) ? vista : null;
  return { idVersion, manzanas, vista: vigente, error, consultando, alternar, sumarContorno, soltarTodo };
}

const ESTILO_ELEGIDA: L.PathOptions = {
  color: COLORES.fijado,
  weight: 2.5,
  fillColor: COLORES.fijado,
  fillOpacity: 0.3,
};
// Con relleno casi transparente: así el clic en cualquier punto de la manzana la elige.
const ESTILO_LIBRE: L.PathOptions = { color: COLORES.manzana, weight: 1, fillColor: "#ffffff", fillOpacity: 0.05 };

// Sobre el mapa: las manzanas para elegir, la barra del contorno, el sector de la vista previa
// (rayado) y sus anclajes.
export function CapaFijar({ version, fijar }: { version: VersionOut; fijar: Fijar }) {
  const mapa = useMap();
  const alternar = useRef(fijar.alternar);
  useEffect(() => {
    alternar.current = fijar.alternar;
  });

  const clave = fijar.manzanas.join(",");
  const estilo = useMemo(() => {
    const elegidas = new Set(clave.split(","));
    // La clase identifica la manzana (la usa el recorrido de la skill verify); Leaflet la pone al
    // crear el trazo y no la cambia después.
    return (feature?: Feature<Geometry, ManzanaProps>) => ({
      ...(feature && elegidas.has(feature.properties.designacion) ? ESTILO_ELEGIDA : ESTILO_LIBRE),
      className: feature ? `fijar__manzana fijar__manzana--${feature.properties.designacion}` : "fijar__manzana",
    });
  }, [clave]);

  return (
    <>
      <GeoJSON
        key={`fijar-${version.id_version}`}
        data={version.capas.manzanas}
        style={estilo}
        onEachFeature={(feature: Feature<Geometry, ManzanaProps>, capa) => {
          capa.bindTooltip(feature.properties.designacion, { sticky: true, direction: "top" });
          capa.on("click", () => {
            // Mientras se dibuja el contorno, el clic es un vértice.
            if (!mapa.pm.globalDrawModeEnabled()) alternar.current(feature.properties.designacion);
          });
        }}
      />
      {fijar.vista && (
        <>
          <GeoJSON key={`sector-${clave}`} data={fijar.vista.sector} style={ESTILO_FIJADO} />
          <GeoJSON
            key={`anclajes-${clave}`}
            data={fijar.vista.anclajes}
            pointToLayer={(_, latlng) =>
              L.circleMarker(latlng, {
                radius: 5,
                color: "#ffffff",
                weight: 2,
                fillColor: COLORES.fijado,
                fillOpacity: 1,
                interactive: false,
              })
            }
          />
        </>
      )}
      <ContornoSector onContorno={fijar.sumarContorno} />
    </>
  );
}

// Textos de la barra (RNF01): dicen qué se dibuja acá, no el terreno del alta.
const TEXTOS: L.PM.Translations = {
  buttonTitles: {
    drawPolyButton: "Dibujar un contorno: suma las manzanas que quedan enteras adentro",
    drawRectButton: "Dibujar un contorno rectangular: suma las manzanas que quedan enteras adentro",
  },
};

const ESTILO_CONTORNO: L.PathOptions = { color: COLORES.fijado, weight: 2, dashArray: "6 4", fillOpacity: 0.08 };

function ContornoSector({ onContorno }: { onContorno: (contorno: Polygon) => void }) {
  const mapa = useMap();
  const avisar = useRef(onContorno);
  useEffect(() => {
    avisar.current = onContorno;
  });

  useEffect(() => {
    mapa.pm.setLang("es", TEXTOS, "es");
    mapa.pm.setGlobalOptions({ snappable: false, allowSelfIntersection: false, pathOptions: ESTILO_CONTORNO });
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
    // El contorno no queda en el mapa: la API lo vuelve manzanas.
    const alCrear = ({ layer }: { layer: L.Layer }) => {
      if (layer instanceof L.Polygon) {
        const contorno = poligonoGeoJSON(layer);
        mapa.removeLayer(layer);
        avisar.current(contorno);
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

type PropsPanel = {
  fijar: Fijar;
  alternativa: AlternativaOut;
  versionParametros: number | null;
  recalculando: boolean;
  error: ErrorOut | null;
  onRecalcular: (orientacion: number | string | null, semilla: number | string | null) => void;
  onCancelar: () => void;
  // Con una observación: el recálculo es su respuesta (CU12, 3.a), y la versión que resulte queda
  // vinculada a ella (D69).
  respuesta?: { designacion: string; descripcion: string; onDescripcion: (texto: string) => void } | null;
};

// En el panel: la vista previa del sector, la estrategia (la que sugiere la API, para cambiarla) y el
// botón de recalcular (CU09, pasos 3 y 4).
export function PanelFijar({
  fijar,
  alternativa,
  versionParametros,
  recalculando,
  error,
  onRecalcular,
  onCancelar,
  respuesta = null,
}: PropsPanel) {
  const version = alternativa.version;
  // Hasta que se toque, la estrategia es la que sugiere la API con la vista previa: la de la versión de
  // origen (D60). El frontend no decide valores por defecto (D37).
  const [editada, setEditada] = useState<{ orientacion: string; semilla: string } | null>(null);
  const v = fijar.vista;
  const sugerida = v?.estrategia_sugerida ?? null;
  const { orientacion, semilla } = editada ?? {
    orientacion: sugerida ? escribirNumero(sugerida.orientacion_grados) : "",
    semilla: sugerida ? String(sugerida.semilla) : "",
  };
  const nueva = Math.max(...alternativa.versiones.map((x) => x.numero)) + 1;

  return (
    <section className="panel__seccion fijar" aria-label="Fijar sectores">
      <h2 className="titulo-panel">
        {respuesta ? `Responder ${respuesta.designacion} con un recálculo · ` : "Fijar sectores de "}
        {alternativa.codigo} · v{version.numero}
      </h2>
      {respuesta && (
        <p className="aviso aviso--info">
          El sector afectado por {respuesta.designacion} está marcado en el mapa: conservá lo que está bien y se
          recalcula el resto. La versión nueva queda vinculada a la respuesta.
        </p>
      )}
      <p className="texto-tenue">
        Hacé clic en una manzana para fijarla o soltarla, o dibujá un contorno con la barra del mapa: suma las manzanas
        que quedan enteras adentro. Lo fijado se conserva con sus lotes y sus calles; el resto se recalcula y queda como
        versión {nueva}. La versión {version.numero} no cambia.
      </p>

      <TarjetaSeccion titulo="Fijación de sectores">
        {fijar.manzanas.length === 0 && <p className="texto-tenue">Todavía no hay ninguna manzana elegida.</p>}
        {fijar.consultando && <p className="texto-tenue">Calculando el sector…</p>}
        {v && (
          <dl className="filas" aria-label="Sector fijado">
            <dt>Sector fijado</dt>
            <dd>{v.manzanas.join(", ")}</dd>
            <dt>Superficie</dt>
            <dd>
              {hectareas(v.superficie_m2)} · {porcentaje(v.porcentaje_disponible)} de la superficie disponible
            </dd>
            <dt>Celdas</dt>
            <dd>
              {numero(v.cantidad_celdas, 0)} ({numero(v.cantidad_lotes, 0)} lotes, {numero(v.cantidad_celdas_utiles, 0)}{" "}
              útiles)
            </dd>
            <dt>Espacio verde</dt>
            <dd>{metrosCuadrados(v.superficie_espacio_verde_m2)}</dd>
            <dt>Anclajes</dt>
            <dd title="Nodos de las calles fijadas que siguen hacia lo que se recalcula: ahí se une la red nueva">
              {numero(v.cantidad_anclajes, 0)} nodos en el borde
            </dd>
          </dl>
        )}
        {fijar.error && <AvisoError error={fijar.error} titulo="No se puede fijar ese sector" />}
      </TarjetaSeccion>

      <TarjetaSeccion titulo="Estrategia del recálculo">
        <div className="generar__campos">
          <div className="campo">
            <label htmlFor="patron-recalculo">Patrón</label>
            <input id="patron-recalculo" value={patron(version.estrategia.patron_red)} readOnly />
          </div>
          <div className="campo">
            <label htmlFor="orientacion-recalculo">Orientación (°)</label>
            <input
              id="orientacion-recalculo"
              inputMode="decimal"
              value={orientacion}
              onChange={(e) => setEditada({ orientacion: e.target.value, semilla })}
            />
          </div>
          <div className="campo">
            <label htmlFor="semilla-recalculo">Semilla</label>
            <input
              id="semilla-recalculo"
              inputMode="numeric"
              value={semilla}
              onChange={(e) => setEditada({ orientacion, semilla: e.target.value })}
            />
          </div>
        </div>
        <p className="texto-tenue">
          {sugerida
            ? `Sugerida: la de la versión ${version.numero}, así la grilla nueva sigue a la fijada.`
            : "La sugiere la API al elegir el sector."}{" "}
          Se recalcula con los parámetros{versionParametros ? ` v${versionParametros}` : ""} vigentes.
        </p>
      </TarjetaSeccion>
      {respuesta && (
        <div className="campo">
          <label htmlFor="respuesta-recalculo">Respuesta a {respuesta.designacion}</label>
          <textarea
            id="respuesta-recalculo"
            rows={3}
            value={respuesta.descripcion}
            onChange={(e) => respuesta.onDescripcion(e.target.value)}
          />
        </div>
      )}
      <div className="acciones">
        <button
          type="button"
          className="boton boton--primario"
          disabled={recalculando || fijar.manzanas.length === 0}
          title={fijar.manzanas.length === 0 ? "Elegí al menos una manzana" : undefined}
          onClick={() => onRecalcular(leerNumero(orientacion), leerNumero(semilla))}
        >
          {recalculando ? "Recalculando…" : respuesta ? "Recalcular y responder" : "Recalcular"}
        </button>
        <button type="button" className="boton" disabled={fijar.manzanas.length === 0} onClick={fijar.soltarTodo}>
          Soltar todo
        </button>
        <button type="button" className="boton" onClick={onCancelar}>
          Cancelar
        </button>
      </div>
      {error && (
        <AvisoError
          error={error}
          titulo={respuesta ? "No se pudo responder con el recálculo" : "No se pudo recalcular"}
        />
      )}
    </section>
  );
}

// Lo que manda el botón «Recalcular»: lo elegido y la estrategia confirmada (CU09, paso 4).
export function pedirRecalculo(
  fijar: Fijar,
  patronRed: string,
  orientacion: number | string | null,
  semilla: number | string | null,
) {
  return recalcular(fijar.idVersion, {
    manzanas: fijar.manzanas,
    estrategia: { patron_red: patronRed, orientacion_grados: orientacion, semilla },
  });
}
