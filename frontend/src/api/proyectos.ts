import type { Feature, FeatureCollection, Point, Polygon } from "geojson";

import type { EstrategiaOut, VersionResumen } from "./alternativas";
import type { ClienteOut } from "./clientes";
import { consultar, enviar } from "./client";
import type { ParametrosIn, ParametrosOut } from "./parametros";

// Espejo de backend/app/schemas/proyecto.py y de UsuarioResumen (schemas/comunes.py): si cambia
// uno, cambia el otro. Las geometrías son GeoJSON en EPSG:4326 (longitud, latitud).
export type UsuarioResumen = { id_usuario: number; nombre: string; apellido: string };

export type AccesoIn = {
  ubicacion: Point;
  // Lo que no es un número va como texto: la API dice qué está mal (D37).
  ancho_m: number | string | null;
  via_vinculacion: string | null;
};

// Un área reservada del terreno (CU04, paso 5; D59). `clase` es texto libre: el documento no
// enumera ClaseArea. Que esté dentro del terreno y no se superponga lo valida la API.
export type AreaReservadaIn = {
  geometria: Polygon;
  denominacion: string;
  clase: string | null;
  destino: string | null;
};

// Lo que falta (el cliente, el terreno) no se manda: la API responde «Falta este dato» en ese
// campo. El frontend no valida reglas del dominio (D37).
export type ProyectoIn = {
  id_cliente?: number;
  codigo: string;
  nombre: string;
  tipo: string;
  ubicacion: string | null;
  jurisdiccion: string | null;
  // Lo que no es un número va como texto, y la API lo rechaza con su mensaje.
  srid_calculo: number | string | null;
  terreno?: Polygon;
  origen: "dibujado" | "importado";
  accesos: AccesoIn[];
  areas_reservadas: AreaReservadaIn[];
  parametros: ParametrosIn | null;
};

export type AlternativaResumen = {
  id_alternativa: number;
  codigo: string;
  // generada, observada o seleccionada (D69).
  estado: string;
  fecha_creacion: string;
  // Las abiertas de todas sus versiones, y cuántas son bloqueantes: con alguna, no se comparte (CU14, 2.a).
  observaciones_abiertas: number;
  bloqueantes_abiertas: number;
  // De la versión vigente, para la página del proyecto (D73), y la descripción para el cliente (D76).
  cumple_restricciones: boolean;
  cantidad_celdas: number;
  descripcion: string | null;
  // De la primera a la vigente (CU09, D57).
  versiones: VersionResumen[];
};

export type ProyectoResumen = {
  id_proyecto: number;
  codigo: string;
  nombre: string;
  tipo: string;
  cliente: ClienteOut;
  estado: string;
  superficie_m2: number;
  cantidad_alternativas: number;
  fecha_creacion: string;
};

export type TerrenoProps = { superficie_m2: number; perimetro_m: number; origen: string };
export type AccesoProps = {
  id_punto_acceso: number;
  designacion: string;
  ancho_m: number | null;
  via_vinculacion: string | null;
};
export type AreaReservadaProyectoProps = {
  id_area_reservada: number;
  designacion: string;
  clase: string | null;
  denominacion: string;
  destino: string | null;
  superficie_m2: number;
};

export type ProyectoOut = {
  id_proyecto: number;
  codigo: string;
  nombre: string;
  tipo: string;
  ubicacion: string | null;
  jurisdiccion: string | null;
  srid_calculo: number;
  estado: string;
  fecha_creacion: string;
  cliente: ClienteOut;
  responsable: UsuarioResumen;
  terreno: Feature<Polygon, TerrenoProps>;
  accesos: FeatureCollection<Point, AccesoProps>;
  // R1, R2… (D59).
  areas_reservadas: FeatureCollection<Polygon, AreaReservadaProyectoProps>;
  parametros: ParametrosOut | null;
  // La estrategia que la pantalla propone antes de generar (p. 43, paso 1; D36).
  estrategia_sugerida: EstrategiaOut;
  alternativas: AlternativaResumen[];
};

export function listarProyectos(cancelacion?: AbortSignal) {
  return consultar<ProyectoResumen[]>("/proyectos", { signal: cancelacion });
}

export function consultarProyecto(idProyecto: number, cancelacion?: AbortSignal) {
  return consultar<ProyectoOut>(`/proyectos/${idProyecto}`, { signal: cancelacion });
}

export function crearProyecto(datos: ProyectoIn) {
  return enviar<ProyectoOut>("/proyectos", datos);
}

// Reemplaza las áreas reservadas del proyecto, enteras (CU04, paso 5; D59): 200 con el proyecto, o 422
// con el campo si un área sale del terreno, se superpone o deja una parte sin acceso. Las versiones ya
// generadas no cambian. Solo el director técnico (p. 54).
export function reemplazarAreas(idProyecto: number, areas: AreaReservadaIn[]) {
  return enviar<ProyectoOut>(`/proyectos/${idProyecto}/areas-reservadas`, { areas_reservadas: areas }, "PUT");
}
