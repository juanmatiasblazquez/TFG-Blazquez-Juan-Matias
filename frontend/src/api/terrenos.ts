import type { Point, Polygon } from "geojson";

import { enviar } from "./client";

// Espejo de backend/app/schemas/terrenos.py: si cambia uno, cambia el otro (CU04; figura 15; D79, D80).
// La API mide y valida con las reglas del motor: el portal no calcula nada (D37).

export type MedicionIn = {
  terreno: Polygon;
  accesos: Point[];
  areas_reservadas: Polygon[];
  // Lo que se escribió en el paso 1: la API dice si sirve.
  srid_calculo: number | string | null;
};

export type ReglaGeometriaOut = { clave: string; descripcion: string; cumple: boolean; detalle: string };

export type MedicionOut = {
  srid_calculo: number;
  sistema: string;
  // null si el polígono no es válido.
  superficie_m2: number | null;
  perimetro_m: number | null;
  vertices: { designacion: string; posicion: [number, number] }[];
  lados: { desde: string; hasta: string; largo_m: number; punto_medio: [number, number] }[];
  areas: { designacion: string; superficie_m2: number | null }[];
  reglas: ReglaGeometriaOut[];
  problemas: { campo: string; mensaje: string }[];
};

export type ImportacionOut = {
  // En EPSG:4326, con la precisión completa.
  terreno: Polygon;
  formato: "posgar" | "geograficas";
  sistema: string;
  srid_calculo: number;
  cantidad_vertices: number;
};

// Lo dibujado en el paso 2 del alta, medido y validado (D79). Lo que está mal va en las reglas, con 200.
export function medirTerreno(datos: MedicionIn, cancelacion?: AbortSignal) {
  return enviar<MedicionOut>("/terrenos/medicion", datos, "POST", cancelacion);
}

// Una planilla de vértices, en POSGAR 2007 o en latitud y longitud (D80). 422 con los problemas por línea.
export function importarVertices(contenido: string, sridCalculo: number | string | null) {
  return enviar<ImportacionOut>("/terrenos/importacion", { contenido, srid_calculo: sridCalculo });
}
