import type { MultiPoint, MultiPolygon, Polygon } from "geojson";

import type { AlternativaOut, EstrategiaIn, EstrategiaOut } from "./alternativas";
import { consultar, enviar } from "./client";

// Espejo de backend/app/schemas/recalculo.py: si cambia uno, cambia el otro (CU09, D56).
// Qué se fija, los anclajes y si el sector abarca todo el terreno lo decide la API con el motor: el
// frontend solo manda lo que se eligió en el mapa (D37).
export type SectorIn = {
  // Designaciones de manzana: un clic en una celda elige su manzana.
  manzanas: string[];
  // Un contorno dibujado: suma las manzanas que quedan enteras adentro.
  contorno: Polygon | null;
};

export type SectorOut = {
  id_version: number;
  manzanas: string[];
  sector: MultiPolygon;
  anclajes: MultiPoint;
  cantidad_anclajes: number;
  superficie_m2: number;
  // El sector sobre la superficie disponible: el terreno menos las áreas reservadas (D61).
  porcentaje_disponible: number;
  cantidad_celdas: number;
  cantidad_lotes: number;
  cantidad_celdas_utiles: number;
  superficie_espacio_verde_m2: number;
  // La que se propone para recalcular: la de la versión de origen (D60).
  estrategia_sugerida: EstrategiaOut;
};

export type RecalculoIn = { estrategia: EstrategiaIn; manzanas: string[] };

// Una versión cualquiera, con la forma de la alternativa (el selector de versiones, D57).
export function consultarVersion(idVersion: number, cancelacion?: AbortSignal) {
  return consultar<AlternativaOut>(`/versiones/${idVersion}`, { signal: cancelacion });
}

// CU09, paso 3: lo que se conservaría, sin guardar nada. 422 si no se eligió nada, si una manzana
// no existe o si lo fijado abarca todo el terreno (3.a).
export function verSector(idVersion: number, sector: SectorIn) {
  return enviar<SectorOut>(`/versiones/${idVersion}/sector`, sector);
}

// CU09: 201 con la versión n + 1 de la misma alternativa, o 422 con causa y sugerencia (3.a, 5.a).
export function recalcular(idVersion: number, recalculo: RecalculoIn) {
  return enviar<AlternativaOut>(`/versiones/${idVersion}/recalculos`, recalculo);
}

// Volver a una versión anterior (p. 50; D60): 201 con la versión n + 1, copia de la elegida, o 422
// si la elegida ya es la vigente. Nunca modifica una versión.
export function volverAVersion(idVersion: number) {
  return enviar<AlternativaOut>(`/versiones/${idVersion}/copias`, {});
}
