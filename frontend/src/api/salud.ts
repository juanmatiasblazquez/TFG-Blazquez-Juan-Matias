import { pedir } from "./client";

// Espejo de backend/app/schemas/salud.py (SaludOut): si cambia uno, cambia el otro.
export type Salud = {
  estado: "ok" | "degradado";
  base: "ok" | "caida";
  postgis: string | null;
  motor: string;
};

export function consultarSalud(cancelacion?: AbortSignal) {
  return pedir<Salud>("/health", { signal: cancelacion });
}
