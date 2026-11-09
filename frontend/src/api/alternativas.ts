import type { FeatureCollection, Geometry, LineString, MultiPolygon, Point, Polygon } from "geojson";

import { consultar, enviar } from "./client";
import type { UsuarioResumen } from "./proyectos";

// Espejo de backend/app/schemas/alternativa.py: si cambia uno, cambia el otro. Las propiedades
// de cada capa son las que arma services/generacion.presentar_alternativa.
// Lo que falta va como null, y lo que no es un número, como texto: la API dice qué está mal.
export type EstrategiaIn = {
  patron_red: string;
  orientacion_grados: number | string | null;
  semilla: number | string | null;
};

export type EstrategiaOut = {
  patron_red: string;
  orientacion_grados: number;
  semilla: number;
};

export type IndicadoresOut = {
  // Celdas útiles: lotes sin incumplimientos (RF11, D26).
  cantidad_celdas: number;
  superficie_aprovechable_m2: number;
  porcentaje_aprovechamiento: number;
  cantidad_fracciones_no_conformes: number;
  // Todos los incumplimientos de la versión (lotes, cesión, art. 12…): la comparación (CU13, D54).
  cantidad_incumplimientos: number;
  porcentaje_circulacion: number;
  porcentaje_espacio_verde: number;
  longitud_red_m: number;
  distancia_media_acceso_m: number | null;
  // Remanentes (D41): nulos en las versiones anteriores al motor 0.4.0. El verde total y el que
  // computa para la cesión, sin las puntas del art. 48 (D55; nulo antes del motor 0.8.0). La cesión
  // alcanzada es el verde computable sobre la superficie de todos los lotes.
  superficie_espacio_verde_m2: number | null;
  superficie_verde_computable_m2: number | null;
  superficie_espacio_libre_m2: number | null;
  porcentaje_cesion: number | null;
  // Los lotes que pasan la superficie máxima (D47) y el % de la red que es avenida (Ley 4146,
  // art. 12; D48): nulos en las versiones anteriores al motor 0.6.0.
  cantidad_lotes_grandes: number | null;
  porcentaje_avenidas: number | null;
  // La distancia media y la máxima de los lotes al espacio verde más cercano, por la red (D51):
  // nulas en las versiones anteriores al motor 0.7.0, o sin lotes o sin verde.
  distancia_media_verde_m: number | null;
  distancia_maxima_verde_m: number | null;
  // La superficie aprovechable sobre las celdas útiles (p. 51); null sin celdas útiles.
  superficie_media_celda_m2: number | null;
  // La de las áreas reservadas con las que se generó (D59): 0 sin áreas. La disponible es el terreno
  // menos las áreas: lo que se lotea.
  superficie_reservada_m2: number;
  superficie_disponible_m2: number;
  // Sobre qué superficie son el aprovechamiento, la circulación y el verde (D61): «disponible» desde
  // el motor 0.10.0, «terreno» en las versiones anteriores, que se guardaron así.
  base_porcentajes: "disponible" | "terreno";
};

// `fijado` / `fijada`: conservado de la versión de origen en un recálculo (CU09, D56).
export type TramoProps = { id_tramo: number; jerarquia: string; orden: number; fijado: boolean; longitud_m?: number };
export type NodoProps = { id_nodo: number; acceso: string | null };
export type ManzanaProps = { id_manzana: number; designacion: string; superficie_m2: number; fijada: boolean };
export type CeldaProps = {
  id_celda: number;
  designacion: string;
  manzana: string | null;
  // «lote», «espacio_verde» o «espacio_libre» (D41).
  tipo: string;
  superficie_m2: number;
  frente_m: number;
  fondo_m: number;
  cumple: boolean;
  motivo_incumplimiento: string | null;
  fijada: boolean;
};
export type IncumplimientoProps = { tipo: string; elemento: string; detalle: string };
// Un área reservada con la que se generó la versión (su copia, D59): R1, R2…
export type AreaReservadaProps = {
  designacion: string;
  clase: string | null;
  denominacion: string;
  destino: string | null;
  superficie_m2: number;
};

export type CapasOut = {
  ejes: FeatureCollection<LineString, TramoProps>;
  calles: FeatureCollection<MultiPolygon, TramoProps>;
  nodos: FeatureCollection<Point, NodoProps>;
  manzanas: FeatureCollection<Polygon, ManzanaProps>;
  celdas: FeatureCollection<Polygon, CeldaProps>;
  incumplimientos: FeatureCollection<Geometry | null, IncumplimientoProps>;
  areas_reservadas: FeatureCollection<Polygon, AreaReservadaProps>;
};

// Una fila de «Diferencias entre versiones» (p. 50; CU09, D56): esta menos la de origen.
export type DiferenciaIndicadorOut = {
  indicador: string;
  sentido: "mayor" | "menor" | null;
  origen: number | null;
  nueva: number | null;
  diferencia: number | null;
};

// Qué se conservó de la versión de origen en un recálculo (CU09, p. 50; D56).
export type FijacionOut = {
  id_version_origen: number;
  numero_origen: number;
  manzanas: string[];
  cantidad_celdas: number;
  cantidad_lotes: number;
  superficie_m2: number;
  // Donde la red fijada se une a la nueva (D60): los anclajes de la vista previa, cuántos de ellos
  // se unieron a una calle nueva, y los empalmes (nodos nuevos sobre el costado de una calle fijada).
  cantidad_anclajes: number;
  cantidad_anclajes_unidos: number;
  cantidad_empalmes: number;
  sector: MultiPolygon;
};

export type VersionOut = {
  id_version: number;
  numero: number;
  id_version_origen: number | null;
  id_conjunto: number;
  version_parametros: number;
  estrategia: EstrategiaOut;
  generada_por: UsuarioResumen;
  fecha_generacion: string;
  duracion_ms: number;
  version_motor: string;
  cumple_restricciones: boolean;
  indicadores: IndicadoresOut;
  capas: CapasOut;
  // Solo en una versión que sale de un recálculo (CU09).
  fijacion: FijacionOut | null;
  diferencias_con_origen: DiferenciaIndicadorOut[] | null;
  // Cómo nació (D62): la v1, un recálculo (con fijación y diferencias) o una copia (volver a una
  // versión anterior, D60).
  tipo: TipoVersion;
  // Las restricciones que verificó el motor, con ✓ o ✗ y su detalle, escrito por la API (p. 49; D74).
  verificaciones: VerificacionOut[];
  // Las observaciones cuya respuesta con un recálculo creó esta versión: «Responde a O-1» (p. 50; D74).
  responde_a: string[];
};

// Una restricción verificada (`services.verificaciones`, D74). El portal la muestra tal cual (D37).
export type VerificacionOut = {
  tipo: string;
  nombre: string;
  cumple: boolean;
  cantidad: number;
  detalle: string;
};

// Generada, recalculada o copia (`schemas/alternativa.TipoVersionOut`, D62).
export type TipoVersion = "generada" | "recalculada" | "copia";

export type VersionResumen = {
  id_version: number;
  numero: number;
  // La versión de la que sale un recálculo o una copia; null en la que se generó.
  id_version_origen: number | null;
  fecha_generacion: string;
  tipo: TipoVersion;
};

export type AlternativaOut = {
  id_alternativa: number;
  id_proyecto: number;
  codigo: string;
  estado: string;
  fecha_creacion: string;
  // Lo que el estudio le cuenta al cliente de este trazado (p. 51; D76), o null.
  descripcion: string | null;
  versiones: VersionResumen[];
  // La versión vigente (la de mayor número), o la pedida en `GET /versiones/{id}`.
  version: VersionOut;
};

// CU06: 201 con la alternativa nueva, o 422 con causa y sugerencia si el motor no puede.
export function generarAlternativa(idProyecto: number, estrategia: EstrategiaIn) {
  return enviar<AlternativaOut>(`/proyectos/${idProyecto}/alternativas`, { estrategia });
}

export function consultarAlternativa(idAlternativa: number, cancelacion?: AbortSignal) {
  return consultar<AlternativaOut>(`/alternativas/${idAlternativa}`, { signal: cancelacion });
}

// La descripción para el cliente (D76): se copia en el enlace al compartir.
export function describirAlternativa(idAlternativa: number, descripcion: string | null) {
  return enviar<AlternativaOut>(`/alternativas/${idAlternativa}`, { descripcion }, "PATCH");
}
