import type { Geometry, Polygon } from "geojson";

import type { EstrategiaIn } from "./alternativas";
import { consultar, enviar } from "./client";
import type { UsuarioResumen } from "./proyectos";

// Espejo de backend/app/schemas/observacion.py: si cambia uno, cambia el otro (CU11, CU12; D69).
// Qué es un sector válido, qué acción lleva un recálculo y qué estados cambian lo decide la API.

// Lo que falta no se manda: la API responde «Falta este dato» en ese campo (D37).
export type ObservacionIn = {
  tipo?: string;
  criticidad?: string;
  descripcion?: string;
  // Dibujado sobre el mapa, con la precisión completa (D37); opcional (RF17).
  sector: Polygon | null;
};

export type RespuestaIn = {
  accion?: string;
  descripcion?: string;
  // Solo con «recalculo_parcial» (CU12, 3.a): sobre la versión vigente, que se nombra.
  recalculo: { id_version: number; estrategia: EstrategiaIn; manzanas: string[] } | null;
};

export type RespuestaOut = {
  id_respuesta: number;
  accion: string;
  descripcion: string;
  usuario: UsuarioResumen;
  fecha: string;
  // La versión que resultó del recálculo (CU12, paso 5); nulas sin recálculo.
  id_version_resultante: number | null;
  numero_version_resultante: number | null;
};

export type ObservacionOut = {
  id_observacion: number;
  // O-1, O-2… por alternativa (p. 50).
  designacion: string;
  id_version: number;
  numero_version: number;
  tipo: string;
  criticidad: string;
  descripcion: string;
  sector: Polygon | null;
  estado: string;
  emisor: UsuarioResumen;
  fecha_emision: string;
  fecha_cierre: string | null;
  respuestas: RespuestaOut[];
};

// La vista previa del sector que se está dibujando (figura 19; D79): su superficie y, si sale del terreno,
// cuánto y dónde (CU11, 3.a). `problema` es el mismo mensaje que daría registrarla.
export type SectorMedidoOut = {
  superficie_m2: number | null;
  afuera_m2: number;
  afuera: Geometry | null;
  problema: string | null;
};

export function medirSector(idVersion: number, sector: Polygon, cancelacion?: AbortSignal) {
  return enviar<SectorMedidoOut>(`/versiones/${idVersion}/observaciones/sector`, { sector }, "POST", cancelacion);
}

export function listarObservaciones(idAlternativa: number, cancelacion?: AbortSignal) {
  return consultar<ObservacionOut[]>(`/alternativas/${idAlternativa}/observaciones`, { signal: cancelacion });
}

// CU11: 201, o 422 con la parte del sector que sale del terreno en `geometria` (3.a).
export function registrarObservacion(idVersion: number, datos: ObservacionIn) {
  return enviar<ObservacionOut>(`/versiones/${idVersion}/observaciones`, datos);
}

// CU12: por comentario (3.b) o por recálculo (3.a), que crea la versión n + 1.
export function responderObservacion(idObservacion: number, datos: RespuestaIn) {
  return enviar<ObservacionOut>(`/observaciones/${idObservacion}/respuestas`, datos);
}

// `cerrar()` («cerrada») o `reabrir()` («abierta»), sobre una respondida (p. 46).
export function cambiarEstadoObservacion(idObservacion: number, estado: "cerrada" | "abierta") {
  return enviar<ObservacionOut>(`/observaciones/${idObservacion}`, { estado }, "PATCH");
}
