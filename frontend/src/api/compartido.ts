import type { Feature, FeatureCollection, MultiPolygon, Point, Polygon } from "geojson";

import { consultar } from "./client";

// Espejo de backend/app/schemas/compartido.py (CU15; D70, D71). Es lo único que ve el cliente.
//
// El token viaja en el encabezado `Authorization`, nunca en la dirección: la página lo lee del fragmento
// (#/compartido/<token>), que el navegador no manda al servidor ni pone en un Referer. Sin cookies
// (`credentials: "omit"`): el cliente no tiene sesión, y si el navegador tuviera una del estudio, no viaja.

export type CompartidoOut = {
  // El nombre del estudio, o null (D74).
  estudio: string | null;
  proyecto: { nombre: string; ubicacion: string | null; cliente: string; superficie_terreno_m2: number };
  alternativas: string[];
  // «Compartido por L. Ferreyra, director técnico.» (p. 51; D75): la inicial, el apellido y el rol.
  compartido_por: { nombre: string; rol: string };
  vence: string;
};

export type IndicadoresCompartidosOut = {
  cantidad_lotes: number;
  superficie_media_lote_m2: number | null;
  superficie_aprovechable_m2: number;
  porcentaje_aprovechamiento: number;
  superficie_espacio_verde_m2: number | null;
  porcentaje_espacio_verde: number;
  longitud_red_m: number;
  superficie_terreno_m2: number;
};

export type CapasCompartidasOut = {
  terreno: Feature<Polygon>;
  accesos: FeatureCollection<Point, { designacion: string }>;
  calles: FeatureCollection<MultiPolygon, { jerarquia: string }>;
  manzanas: FeatureCollection<Polygon, { designacion: string }>;
  celdas: FeatureCollection<Polygon, { designacion: string; tipo: string }>;
  areas_reservadas: FeatureCollection<Polygon, { designacion: string; denominacion: string }>;
};

export type AlternativaCompartidaOut = {
  codigo: string;
  // La descripción que tenía la alternativa al compartir (D76), o null.
  descripcion: string | null;
  indicadores: IndicadoresCompartidosOut;
  capas: CapasCompartidasOut;
};

function conToken(token: string, cancelacion?: AbortSignal): RequestInit {
  return { signal: cancelacion, credentials: "omit", headers: { Authorization: `Bearer ${token}` } };
}

export function consultarCompartido(token: string, cancelacion?: AbortSignal) {
  return consultar<CompartidoOut>("/compartido", conToken(token, cancelacion));
}

export function consultarAlternativaCompartida(token: string, codigo: string, cancelacion?: AbortSignal) {
  return consultar<AlternativaCompartidaOut>(
    `/compartido/alternativas/${encodeURIComponent(codigo)}`,
    conToken(token, cancelacion),
  );
}
