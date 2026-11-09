import { consultar, enviar } from "./client";
import type { AlternativaResumen, UsuarioResumen } from "./proyectos";

// Espejo de backend/app/schemas/enlace.py: si cambia uno, cambia el otro (CU14; D70).

export type VersionCompartida = { id_version: number; codigo_alternativa: string; numero_version: number };

export type EnlaceOut = {
  id_enlace: number;
  estado: "vigente" | "vencido" | "revocado";
  fecha_creacion: string;
  fecha_vencimiento: string;
  creado_por: UsuarioResumen;
  versiones: VersionCompartida[];
  ultimo_acceso: string | null;
  cantidad_accesos: number;
};

// El token se muestra esta única vez (CU14, paso 5): la base guarda solo su hash.
export type EnlaceCreadoOut = { enlace: EnlaceOut; token: string };

// La dirección que se le manda al cliente. El token va en el fragmento (#), que el navegador nunca manda
// al servidor ni pone en un Referer: así no queda en ningún registro (D71).
export const direccionDelEnlace = (token: string) => `${window.location.origin}/#/compartido/${token}`;

// CU14, paso 1 (p. 45, paso 2): la selección pasa a ser exactamente esta. 409 si alguna tiene una
// observación bloqueante sin responder (2.a).
export function seleccionar(idProyecto: number, codigos: string[]) {
  return enviar<{ alternativas: AlternativaResumen[] }>(`/proyectos/${idProyecto}/seleccion`, { alternativas: codigos }, "PATCH");
}

// CU14, pasos 3 a 5. La fecha va como la escribió el usuario: la API dice si sirve (D37).
export function compartir(idProyecto: number, fechaVencimiento: string | null) {
  return enviar<EnlaceCreadoOut>(`/proyectos/${idProyecto}/enlaces`, fechaVencimiento ? { fecha_vencimiento: fechaVencimiento } : {});
}

export function listarEnlaces(idProyecto: number, cancelacion?: AbortSignal) {
  return consultar<EnlaceOut[]>(`/proyectos/${idProyecto}/enlaces`, { signal: cancelacion });
}

export function revocarEnlace(idEnlace: number) {
  return enviar<EnlaceOut>(`/enlaces/${idEnlace}`, { revocado: true }, "PATCH");
}
