import type { EstrategiaOut } from "./alternativas";
import { consultar } from "./client";

// Espejo de backend/app/schemas/comparacion.py: si cambia uno, cambia el otro (CU13, D54).
// Qué indicador tiene una dirección clara y cuál es el mejor lo decide la API: el frontend solo
// lo muestra.
export type Sentido = "mayor" | "menor";

// Una alternativa con su versión vigente, o la versión pedida cuando se comparan versiones (D57).
export type AlternativaComparadaOut = {
  id_alternativa: number;
  codigo: string;
  id_version: number;
  numero: number;
  cumple_restricciones: boolean;
  version_parametros: number;
  version_motor: string;
  estrategia: EstrategiaOut;
  // La casilla «Seleccionada» o «Obs. bloqueante» de cada mapa (figura 20; D84).
  estado: string;
  bloqueantes_abiertas: number;
  // La insignia «Criterio del verde» (D83); null si no aplica (D45).
  criterio_espacio_verde: string | null;
};

export type IndicadorComparadoOut = {
  // El campo de IndicadoresOut, u «observaciones_bloqueantes_abiertas» (solo entre alternativas, D84).
  indicador: string;
  // null es una disyuntiva: la diferencia, sin resaltar un mejor.
  sentido: Sentido | null;
  valores: (number | null)[];
  // diferencias[k] = valores[k] − valores[0]; null para la primera o si falta un valor.
  diferencias: (number | null)[];
  // Los índices de las alternativas con el mejor valor; vacía si todas empatan.
  mejores: number[];
};

export type DiferenciaOut = {
  // Un campo de ParametrosIn («loteo.criterio_espacio_verde»), «estrategia.*» o «version_motor».
  campo: string;
  valores: (number | string | null)[];
};

export type ComparacionOut = {
  id_proyecto: number;
  alternativas: AlternativaComparadaOut[];
  indicadores: IndicadorComparadoOut[];
  // Solo lo que difiere.
  diferencias: DiferenciaOut[];
};

// CU13: dos o tres alternativas del proyecto, en el orden de la tabla. Si no son dos o tres, o una
// es de otro proyecto, la API responde 422 en el campo «alternativas».
export function compararAlternativas(idProyecto: number, ids: number[], cancelacion?: AbortSignal) {
  const consulta = ids.map((id) => `alternativas=${id}`).join("&");
  return consultar<ComparacionOut>(`/proyectos/${idProyecto}/comparacion?${consulta}`, { signal: cancelacion });
}

// Dos o tres versiones del proyecto, por ejemplo la v1 y la v2 de una alternativa (D57). La API
// responde 422 en el campo «versiones».
export function compararVersiones(idProyecto: number, ids: number[], cancelacion?: AbortSignal) {
  const consulta = ids.map((id) => `versiones=${id}`).join("&");
  return consultar<ComparacionOut>(`/proyectos/${idProyecto}/comparacion?${consulta}`, { signal: cancelacion });
}
