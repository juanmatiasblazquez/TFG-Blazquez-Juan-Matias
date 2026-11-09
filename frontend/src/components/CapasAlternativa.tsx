import type { Feature, Geometry } from "geojson";
import L from "leaflet";
import { useState, type CSSProperties } from "react";
import { GeoJSON } from "react-leaflet";

import type { AreaReservadaProps, CeldaProps, ManzanaProps, VersionOut } from "../api/alternativas";
import { metros, metrosCuadrados, tipoCelda, tipoIncumplimiento } from "../formato";
import { EtiquetasMapa } from "./EtiquetasMapa";

// Colores de las capas (RF14), los de las figuras 15 a 21 (D73): los lotes en blanco con una línea fina,
// las calles gris azulado, el verde claro, las áreas reservadas rayadas en naranja y lo que no cumple en
// rojo. Los lotes que no cumplen se marcan, no se ocultan (CU06, 6.a). El espacio libre (D41), que las
// figuras no tienen, va en un tono neutro.
export const COLORES = {
  calle: "#d3d9e0",
  bordeCalle: "#c0c9d3",
  manzana: "#4d6680",
  loteCumple: "#ffffff",
  bordeLote: "#8a9bb0",
  loteNoCumple: "#f6caca",
  espacioVerde: "#cfe8c8",
  bordeVerde: "#6fa86f",
  espacioLibre: "#ece7df",
  bordeLibre: "#b3a793",
  incumplimiento: "#c62828",
  eje: "#52606d",
  // Lo fijado en un recálculo y lo que se elige para fijar (CU09, D56).
  fijado: "#2b6cb0",
  // Las áreas reservadas, rayadas en naranja como en la p. 48 (D59).
  reservada: "#d08a35",
  fondoReservada: "#f7e3c4",
};

const ESTILO_CALLE: L.PathOptions = {
  color: COLORES.bordeCalle,
  weight: 0.5,
  fillColor: COLORES.calle,
  fillOpacity: 1,
};
const ESTILO_MANZANA: L.PathOptions = { color: COLORES.manzana, weight: 0.8, opacity: 0.6, fill: false };
const ESTILO_INCUMPLIMIENTO: L.PathOptions = {
  color: COLORES.incumplimiento,
  weight: 1.8,
  fillColor: "#e57373",
  fillOpacity: 0.3,
};
const ESTILO_EJE: L.PathOptions = { color: COLORES.eje, weight: 1, dashArray: "4 4" };

// El sector fijado, rayado en azul. El rayado es un <pattern> SVG (`RayadoFijado`) que la clase
// `rayado-fijado` pone como relleno (index.css): Leaflet no rellena con patrones.
export const ESTILO_FIJADO: L.PathOptions = {
  color: COLORES.fijado,
  weight: 2.5,
  // Otro trazo que el borde del terreno, que es continuo.
  dashArray: "10 5",
  className: "rayado-fijado",
  interactive: false,
};

// Un área reservada (D59): rayada en naranja, con el mismo mecanismo (`rayado-reservada`).
export const ESTILO_RESERVADA: L.PathOptions = {
  color: COLORES.reservada,
  weight: 1.5,
  className: "rayado-reservada",
};

// La definición de los rayados (el sector fijado y las áreas reservadas), una vez por pantalla con
// mapas.
export function RayadoFijado() {
  return (
    <svg className="definiciones-svg" aria-hidden="true" focusable="false">
      <defs>
        <pattern id="rayado-fijado" patternUnits="userSpaceOnUse" width="9" height="9" patternTransform="rotate(45)">
          <rect width="9" height="9" fill="#ffffff" fillOpacity="0.7" />
          <line x1="0" y1="0" x2="0" y2="9" stroke={COLORES.fijado} strokeWidth="1.6" strokeOpacity="0.7" />
        </pattern>
        <pattern
          id="rayado-reservada"
          patternUnits="userSpaceOnUse"
          width="8"
          height="8"
          patternTransform="rotate(-45)"
        >
          <rect width="8" height="8" fill={COLORES.fondoReservada} />
          <line x1="0" y1="0" x2="0" y2="8" stroke={COLORES.reservada} strokeWidth="1.4" />
        </pattern>
      </defs>
    </svg>
  );
}

// El popup de un área reservada: su designación, a qué corresponde y su superficie.
export function popupArea(feature: Feature<Geometry, AreaReservadaProps>, capa: L.Layer) {
  const p = feature.properties;
  const filas: [string, string][] = [["Superficie", metrosCuadrados(p.superficie_m2)]];
  if (p.clase) filas.push(["Clase", p.clase]);
  if (p.destino) filas.push(["Destino", p.destino]);
  capa.bindPopup(contenido(`Área reservada ${p.designacion}: ${p.denominacion}`, filas));
}

function estiloLote(feature?: Feature<Geometry, CeldaProps>): L.PathOptions {
  return feature?.properties.cumple
    ? { color: COLORES.bordeLote, weight: 0.7, fillColor: COLORES.loteCumple, fillOpacity: 1 }
    : { color: COLORES.incumplimiento, weight: 1.2, fillColor: COLORES.loteNoCumple, fillOpacity: 1 };
}

const ESTILO_VERDE: L.PathOptions = {
  color: COLORES.bordeVerde,
  weight: 1,
  fillColor: COLORES.espacioVerde,
  fillOpacity: 1,
};
const ESTILO_LIBRE: L.PathOptions = {
  color: COLORES.bordeLibre,
  weight: 0.8,
  fillColor: COLORES.espacioLibre,
  fillOpacity: 1,
};

// La capa de cada tipo de celda («lote», «espacio_verde», «espacio_libre»).
const deTipo = (tipo: string) => (feature: Feature<Geometry, CeldaProps>) => feature.properties.tipo === tipo;

function popupCelda(feature: Feature<Geometry, CeldaProps>, capa: L.Layer) {
  const p = feature.properties;
  if (p.tipo !== "lote") {
    // Un remanente: la zona donde no entra un lote válido (D41).
    capa.bindPopup(
      contenido(`${tipoCelda(p.tipo)} ${p.designacion}`, [["Superficie", metrosCuadrados(p.superficie_m2)]]),
    );
    return;
  }
  const filas: [string, string][] = [
    ["Superficie", metrosCuadrados(p.superficie_m2)],
    ["Frente", metros(p.frente_m)],
    ["Fondo", metros(p.fondo_m)],
    ["Cumple", p.cumple ? "Sí" : "No"],
  ];
  if (p.motivo_incumplimiento) filas.push(["Motivo", p.motivo_incumplimiento]);
  capa.bindPopup(contenido(`Lote ${p.designacion}`, filas));
}

function popupIncumplimiento(
  feature: Feature<Geometry | null, { tipo: string; elemento: string; detalle: string }>,
  capa: L.Layer,
) {
  const p = feature.properties;
  capa.bindPopup(
    contenido(tipoIncumplimiento(p.tipo), [
      ["Elemento", p.elemento],
      ["Detalle", p.detalle],
    ]),
  );
}

// El popup se arma con nodos de texto, no con HTML concatenado.
function contenido(titulo: string, filas: [string, string][]): HTMLElement {
  const raiz = document.createElement("div");
  const encabezado = document.createElement("strong");
  encabezado.textContent = titulo;
  raiz.append(encabezado);
  for (const [nombre, valor] of filas) {
    const linea = document.createElement("div");
    linea.textContent = `${nombre}: ${valor}`;
    raiz.append(linea);
  }
  return raiz;
}

const comoCirculo = (radio: number, color: string) => (_: unknown, latlng: L.LatLng) =>
  L.circleMarker(latlng, { radius: radio, color, weight: 1, fillColor: color, fillOpacity: 0.9 });

// --- Las capas y el panel «Capas» ---------------------------------------------------------------------

export type ClaveCapa =
  | "celdas"
  | "calles"
  | "verde"
  | "libre"
  | "manzanas"
  | "reservadas"
  | "fijado"
  | "incumplimientos"
  | "red";

export type CapasVisibles = Record<ClaveCapa, boolean>;

// Lo que se ve al abrir: todo menos los ejes y los nodos de la red.
export const CAPAS_INICIALES: CapasVisibles = {
  celdas: true,
  calles: true,
  verde: true,
  libre: true,
  manzanas: true,
  reservadas: true,
  fijado: true,
  incumplimientos: true,
  red: false,
};

// Cómo se ve la muestra de una capa en el panel y en las leyendas.
export type Muestra = {
  color: string;
  borde?: string;
  fondo?: string;
  tipo?: "relleno" | "borde" | "punteada" | "rayada";
};

export type EntradaCapa = { clave: ClaveCapa; nombre: string; muestra: Muestra };

// Las capas de una versión, en el orden del panel de la figura 17. Las que la versión no tiene no van.
export function capasDe(version: VersionOut): EntradaCapa[] {
  const { capas } = version;
  const hay = (tipo: string) => capas.celdas.features.some((f) => f.properties.tipo === tipo);
  const entradas: (EntradaCapa | false)[] = [
    { clave: "celdas", nombre: "Celdas", muestra: { color: COLORES.loteCumple, borde: COLORES.bordeLote } },
    { clave: "calles", nombre: "Red de circulación", muestra: { color: COLORES.calle, borde: COLORES.bordeCalle } },
    hay("espacio_verde") && {
      clave: "verde",
      nombre: "Espacios verdes",
      muestra: { color: COLORES.espacioVerde, borde: COLORES.bordeVerde },
    },
    hay("espacio_libre") && {
      clave: "libre",
      nombre: "Espacio libre",
      muestra: { color: COLORES.espacioLibre, borde: COLORES.bordeLibre },
    },
    capas.areas_reservadas.features.length > 0 && {
      clave: "reservadas",
      nombre: "Áreas reservadas",
      muestra: { color: COLORES.reservada, fondo: COLORES.fondoReservada, tipo: "rayada" },
    },
    version.fijacion !== null && {
      clave: "fijado",
      nombre: `Sector fijado (conservado de v${version.fijacion.numero_origen})`,
      muestra: { color: COLORES.fijado, fondo: "#ffffff", tipo: "rayada" },
    },
    {
      clave: "incumplimientos",
      nombre: "Incumplimientos",
      muestra: { color: COLORES.loteNoCumple, borde: COLORES.incumplimiento },
    },
    { clave: "manzanas", nombre: "Manzanas", muestra: { color: COLORES.manzana, tipo: "borde" } },
    { clave: "red", nombre: "Ejes y nodos de la red", muestra: { color: COLORES.eje, tipo: "punteada" } },
  ];
  return entradas.filter((e): e is EntradaCapa => e !== false);
}

// La muestra de una capa: un rectangulito con su relleno, su borde o su rayado.
export function MuestraCapa({ muestra }: { muestra: Muestra }) {
  const tipo = muestra.tipo ?? "relleno";
  const clase = tipo === "relleno" ? "muestra" : `muestra muestra--${tipo}`;
  const estilo = {
    "--color": muestra.color,
    "--borde-muestra": muestra.borde ?? muestra.color,
    "--fondo-muestra": muestra.fondo ?? "transparent",
  } as CSSProperties;
  return <span className={clase} style={estilo} aria-hidden="true" />;
}

type PropsPanelCapas = {
  entradas: EntradaCapa[];
  visibles: CapasVisibles;
  onCambio: (visibles: CapasVisibles) => void;
  titulo?: string;
};

// El panel «Capas» arriba a la izquierda, con una casilla y una muestra por capa (figura 17). Es también
// la leyenda. Se pliega para ver el mapa entero.
export function PanelCapas({ entradas, visibles, onCambio, titulo = "Capas" }: PropsPanelCapas) {
  const [plegado, setPlegado] = useState(false);
  return (
    <div className={`sobre-mapa capas ${plegado ? "capas--plegado" : ""}`} aria-label="Capas del mapa">
      <p className="capas__titulo">
        {titulo}
        <button
          type="button"
          className="capas__plegar"
          title={plegado ? "Mostrar las capas" : "Ocultar las capas"}
          aria-expanded={!plegado}
          onClick={() => setPlegado(!plegado)}
        >
          {plegado ? "▸" : "▾"}
        </button>
      </p>
      {entradas.map((e) => (
        <label key={e.clave} className="capas__item">
          <input
            type="checkbox"
            checked={visibles[e.clave]}
            onChange={(evento) => onCambio({ ...visibles, [e.clave]: evento.target.checked })}
          />
          <MuestraCapa muestra={e.muestra} />
          {e.nombre}
        </label>
      ))}
    </div>
  );
}

// Solo las manzanas con lotes llevan su nombre: en las figuras, una manzana entera de verde no lo lleva.
function nombresDeManzanas(version: VersionOut) {
  const conLotes = new Set(
    version.capas.celdas.features.filter((f) => f.properties.tipo === "lote").map((f) => f.properties.manzana),
  );
  return (f: Feature<Geometry, ManzanaProps>) =>
    conLotes.has(f.properties.designacion) ? f.properties.designacion : null;
}

// Las capas de una versión, según lo que esté prendido en el panel. La `key` de cada GeoJSON es la
// versión: react-leaflet no redibuja si cambian los datos.
export function CapasAlternativa({
  version,
  visibles = CAPAS_INICIALES,
  etiquetas = true,
}: {
  version: VersionOut;
  visibles?: CapasVisibles;
  // Los nombres de las manzanas: no van en los mapas chicos de la comparación (figura 20).
  etiquetas?: boolean;
}) {
  const { capas, id_version } = version;
  return (
    <>
      {visibles.calles && <GeoJSON key={`calles-${id_version}`} data={capas.calles} style={ESTILO_CALLE} />}
      {visibles.celdas && (
        <GeoJSON
          key={`lotes-${id_version}`}
          data={capas.celdas}
          filter={deTipo("lote")}
          style={estiloLote}
          onEachFeature={popupCelda}
        />
      )}
      {visibles.verde && (
        <GeoJSON
          key={`verde-${id_version}`}
          data={capas.celdas}
          filter={deTipo("espacio_verde")}
          style={ESTILO_VERDE}
          onEachFeature={popupCelda}
        />
      )}
      {visibles.libre && (
        <GeoJSON
          key={`libre-${id_version}`}
          data={capas.celdas}
          filter={deTipo("espacio_libre")}
          style={ESTILO_LIBRE}
          onEachFeature={popupCelda}
        />
      )}
      {visibles.reservadas && capas.areas_reservadas.features.length > 0 && (
        // RF14: las áreas reservadas con las que se generó la versión (D59).
        <GeoJSON
          key={`reservadas-${id_version}`}
          data={capas.areas_reservadas}
          style={ESTILO_RESERVADA}
          onEachFeature={popupArea}
        />
      )}
      {visibles.fijado && version.fijacion && (
        // CU09: lo que se conservó de la versión de origen, con sus calles (D56).
        <GeoJSON key={`fijado-${id_version}`} data={version.fijacion.sector} style={ESTILO_FIJADO} />
      )}
      {visibles.incumplimientos && (
        <GeoJSON
          key={`incumplimientos-${id_version}`}
          data={capas.incumplimientos}
          style={ESTILO_INCUMPLIMIENTO}
          pointToLayer={comoCirculo(6, COLORES.incumplimiento)}
          onEachFeature={popupIncumplimiento}
        />
      )}
      {visibles.manzanas && (
        <>
          <GeoJSON key={`manzanas-${id_version}`} data={capas.manzanas} style={ESTILO_MANZANA} interactive={false} />
          {etiquetas && (
            <EtiquetasMapa
              clave={`etiquetas-${id_version}`}
              datos={capas.manzanas}
              texto={nombresDeManzanas(version)}
              clase="etiqueta-manzana"
              ancho={28}
              alto={16}
            />
          )}
        </>
      )}
      {visibles.red && (
        <>
          <GeoJSON key={`ejes-${id_version}`} data={capas.ejes} style={ESTILO_EJE} interactive={false} />
          <GeoJSON key={`nodos-${id_version}`} data={capas.nodos} pointToLayer={comoCirculo(3, COLORES.eje)} />
        </>
      )}
    </>
  );
}
