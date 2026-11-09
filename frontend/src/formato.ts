// Cómo se muestran los números, las fechas y los códigos de la API (RNF01): coma decimal, punto
// de miles y textos en español. Es presentación, no reglas: los valores los calcula la API.
const LOCALE = "es-AR";

export function numero(valor: number, decimales = 2): string {
  return valor.toLocaleString(LOCALE, { minimumFractionDigits: decimales, maximumFractionDigits: decimales });
}

export const metros = (valor: number) => `${numero(valor)} m`;
export const metrosCuadrados = (valor: number) => `${numero(valor)} m²`;
export const hectareas = (metrosCuadrados: number) => `${numero(metrosCuadrados / 10_000)} ha`;
export const kilometros = (metros: number) => `${numero(metros / 1_000)} km`;
export const porcentaje = (valor: number) => `${numero(valor)} %`;
export const grados = (valor: number) => `${numero(valor)}°`;

// «A», «A y B», «A, B y C».
export function enumerar(partes: string[]): string {
  return partes.length <= 1 ? (partes[0] ?? "") : `${partes.slice(0, -1).join(", ")} y ${partes.at(-1)}`;
}

export function fechaHora(iso: string): string {
  return new Date(iso).toLocaleString(LOCALE, { dateStyle: "short", timeStyle: "short" });
}

// «22/09/2026 10:41», como en las tarjetas de las figuras 17 a 19.
export function fechaHoraLarga(iso: string): string {
  const d = new Date(iso);
  const dia = d.toLocaleDateString(LOCALE, { day: "2-digit", month: "2-digit", year: "numeric" });
  const hora = d.toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit", hour12: false });
  return `${dia} ${hora}`;
}

// Una fecha sola, en la hora de Córdoba: la del estudio (el vencimiento de un enlace es el final de un
// día en Córdoba, D70).
export function fecha(iso: string): string {
  return new Date(iso).toLocaleDateString(LOCALE, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "America/Argentina/Cordoba",
  });
}

// Lo que falta para algo, en minutos: «12 minutos», «1 minuto».
export function minutos(segundos: number): string {
  const n = Math.max(1, Math.ceil(segundos / 60));
  return n === 1 ? "1 minuto" : `${n} minutos`;
}

// Nombres para los códigos que guarda la API (CU03, D26). Un código nuevo se muestra tal cual.
const ESTADOS: Record<string, string> = {
  en_preparacion: "En preparación",
  listo_para_generar: "Listo para generar",
  // El estado de una alternativa (D69).
  generada: "Generada",
  observada: "Observada",
  seleccionada: "Seleccionada",
};

const TIPOS_PROYECTO: Record<string, string> = {
  loteo: "Loteo",
  estacionamiento: "Playa de estacionamiento",
};

const TIPOS_INCUMPLIMIENTO: Record<string, string> = {
  conectividad: "Conectividad",
  sin_frente: "Sin frente a una calle",
  frente_minimo: "Frente mínimo",
  fondo_minimo: "Fondo mínimo",
  superficie_minima: "Superficie mínima",
  // Desde el motor 0.6.0 no se marca (D47); queda para nombrarlo en las versiones anteriores.
  superficie_maxima: "Superficie máxima",
  relacion_fondo_frente: "Relación fondo/frente",
  ancho_util: "Ancho útil",
  cesion_espacio_verde: "Cesión de espacio verde",
  // Ley 4146, art. 12 (D48).
  ancho_calle: "Ancho de calle",
  proporcion_avenidas: "Proporción de avenidas",
  // Ord. 8060, art. 48 (D50).
  lado_menor_manzana: "Lado menor de manzana",
  lado_mayor_manzana: "Lado mayor de manzana",
};

// Qué prioriza el asignador de espacios verdes (D46, D51): un criterio de diseño, no una norma.
const CRITERIOS_ESPACIO_VERDE: Record<string, string> = {
  cercania: "Más cercanía",
  menos_lotes: "Menos lotes perdidos",
};

// Por dónde va la calle de borde (D50, D86): un criterio de diseño, no una norma.
const CALLES_BORDE: Record<string, string> = {
  por_lado: "Por lado",
  contorno: "En todo el contorno",
};

const TIPOS_CELDA: Record<string, string> = {
  lote: "Lote",
  espacio_verde: "Espacio verde",
  espacio_libre: "Espacio libre",
};

const PATRONES: Record<string, string> = { grilla: "Grilla" };

// Los roles con cuenta (`schemas/usuario.RolIn`, p. 54). El Cliente no tiene cuenta (CU15). En el
// orden de la tabla: es el del selector del alta.
export const ROLES: [string, string][] = [
  ["director_tecnico", "Director técnico"],
  ["proyectista", "Proyectista"],
  ["consultor_interno", "Consultor interno"],
];
const NOMBRES_ROL: Record<string, string> = Object.fromEntries(ROLES);

// Las observaciones, con los valores del acta (Anexo 1.5) y de los casos de uso (CU11, CU12; D69), en el
// orden del documento: son los de los selectores. Qué valor sirve lo dice la API.
export const TIPOS_OBSERVACION: [string, string][] = [
  ["normativa", "Normativa"],
  ["dimensional", "Dimensional"],
  ["conectividad", "Conectividad"],
  ["comercial", "Comercial"],
  ["grafica", "Gráfica"],
];
export const CRITICIDADES: [string, string][] = [
  ["bloqueante", "Bloqueante"],
  ["sugerida", "Sugerida"],
];
export const ACCIONES_RESPUESTA: [string, string][] = [
  ["recalculo_parcial", "Recálculo parcial de un sector"],
  ["justificacion", "Justificación"],
  ["aclaracion", "Aclaración"],
];
const ESTADOS_OBSERVACION: Record<string, string> = {
  abierta: "Abierta",
  respondida: "Respondida",
  cerrada: "Cerrada",
};
const ESTADOS_ENLACE: Record<string, string> = { vigente: "Vigente", vencido: "Vencido", revocado: "Revocado" };
const de = (lista: [string, string][]) => Object.fromEntries(lista) as Record<string, string>;
export const tipoObservacion = (codigo: string) => de(TIPOS_OBSERVACION)[codigo] ?? codigo;
export const criticidad = (codigo: string) => de(CRITICIDADES)[codigo] ?? codigo;
export const accionRespuesta = (codigo: string) => de(ACCIONES_RESPUESTA)[codigo] ?? codigo;
export const estadoObservacion = (codigo: string) => ESTADOS_OBSERVACION[codigo] ?? codigo;
export const estadoEnlace = (codigo: string) => ESTADOS_ENLACE[codigo] ?? codigo;

export const estado = (codigo: string) => ESTADOS[codigo] ?? codigo;
export const nombreRol = (codigo: string) => NOMBRES_ROL[codigo] ?? codigo;
export const tipoProyecto = (codigo: string) => TIPOS_PROYECTO[codigo] ?? codigo;
export const tipoIncumplimiento = (codigo: string) => TIPOS_INCUMPLIMIENTO[codigo] ?? codigo;
export const tipoCelda = (codigo: string) => TIPOS_CELDA[codigo] ?? codigo;
export const criterioEspacioVerde = (codigo: string) => CRITERIOS_ESPACIO_VERDE[codigo] ?? codigo;
export const calleBorde = (codigo: string) => CALLES_BORDE[codigo] ?? codigo;

export const patron = (codigo: string) => PATRONES[codigo] ?? codigo;

// Lo que se escribe en un campo numérico, para mandarlo a la API. Admite coma decimal. Vacío es
// null («Falta este dato») y lo que no es un número va como texto («Tiene que ser un número»):
// lo que está mal lo dice la API, no el frontend (D37).
export type NumeroEscrito = number | string | null;

export function leerNumero(texto: string): NumeroEscrito {
  const limpio = texto.trim().replace(",", ".");
  if (limpio === "") return null;
  const valor = Number(limpio);
  return Number.isFinite(valor) ? valor : texto.trim();
}

// Al revés: un número de la API en un campo editable, con coma decimal y, si se piden, con esos
// decimales («10,00», como en la figura 16), sin punto de miles: `leerNumero` lo vuelve a leer. null
// («no aplica», D45) es un campo vacío.
export function escribirNumero(valor: number | null, decimales?: number): string {
  if (valor === null) return "";
  return (decimales === undefined ? String(valor) : valor.toFixed(decimales)).replace(".", ",");
}

// Un valor que en una versión anterior del motor no existía (D45).
export const NO_APLICA = "no aplica";

// Los indicadores de la comparación (CU13, D54): el nombre de cada uno y cómo se escribe su valor
// y su diferencia. Cuál tiene una dirección clara y cuál es el mejor lo decide la API (`sentido`,
// `mejores`): acá no hay una copia.
type Unidad = "cantidad" | "m2" | "porcentaje" | "metros";
const INDICADORES: Record<string, [string, Unidad]> = {
  // Los nombres de las figuras 17, 18 y 20: «Celdas útiles», «Superficie aprovechable»… (D73).
  cantidad_celdas: ["Celdas útiles", "cantidad"],
  superficie_aprovechable_m2: ["Superficie aprovechable", "m2"],
  porcentaje_aprovechamiento: ["Aprovechamiento", "porcentaje"],
  superficie_media_celda_m2: ["Superficie media de celda", "m2"],
  porcentaje_circulacion: ["Circulación", "porcentaje"],
  longitud_red_m: ["Longitud de red", "metros"],
  porcentaje_avenidas: ["Avenidas, de la longitud de la red", "porcentaje"],
  // El verde total, puntas incluidas, y el que computa para la cesión (D55).
  porcentaje_espacio_verde: ["Espacio verde total, del terreno", "porcentaje"],
  superficie_verde_computable_m2: ["Verde computable para la cesión", "m2"],
  porcentaje_cesion: ["Cesión, verde computable sobre los lotes", "porcentaje"],
  distancia_media_verde_m: ["Distancia media al verde", "metros"],
  distancia_maxima_verde_m: ["Distancia máxima al verde", "metros"],
  distancia_media_acceso_m: ["Distancia media al acceso", "metros"],
  cantidad_incumplimientos: ["Incumplimientos", "cantidad"],
  // La última fila de la figura 20: del estado de la alternativa, solo entre alternativas (D84).
  observaciones_bloqueantes_abiertas: ["Observaciones bloqueantes abiertas", "cantidad"],
};

export const nombreIndicador = (codigo: string) => INDICADORES[codigo]?.[0] ?? codigo;

function conUnidad(unidad: Unidad, valor: number): string {
  switch (unidad) {
    case "cantidad":
      return numero(valor, 0);
    case "m2":
      return metrosCuadrados(valor);
    case "porcentaje":
      return porcentaje(valor);
    case "metros":
      return metros(valor);
  }
}

// Un valor nulo es «no aplica» o «sin verde»: se muestra una raya.
export function valorIndicador(codigo: string, valor: number | null): string {
  if (valor === null) return "—";
  return conUnidad(INDICADORES[codigo]?.[1] ?? "metros", valor);
}

// La diferencia con su signo; la de un porcentaje, en puntos porcentuales.
export function diferenciaIndicador(codigo: string, diferencia: number | null): string {
  if (diferencia === null) return "—";
  const unidad = INDICADORES[codigo]?.[1] ?? "metros";
  const signo = diferencia > 0 ? "+" : diferencia < 0 ? "−" : "";
  const absoluta = Math.abs(diferencia);
  const texto = unidad === "porcentaje" ? `${numero(absoluta)} p. p.` : conUnidad(unidad, absoluta);
  return `${signo}${texto}`;
}

// Lo que separa a las alternativas además de los parámetros (D54): la estrategia, el motor y las
// áreas reservadas con las que se generó cada una (D59), que la API resume como texto.
const CAMPOS_ESTRATEGIA: Record<string, [string, (valor: number | string) => string]> = {
  "estrategia.patron_red": ["Estrategia · Patrón de la red", (v) => patron(String(v))],
  "estrategia.orientacion_grados": ["Estrategia · Orientación de la grilla", (v) => grados(Number(v))],
  "estrategia.semilla": ["Estrategia · Semilla", (v) => String(v)],
  version_motor: ["Versión del motor", (v) => String(v)],
  areas_reservadas: ["Áreas reservadas", (v) => String(v)],
};

export const esCampoDeEstrategia = (campo: string) => campo in CAMPOS_ESTRATEGIA;
export const etiquetaEstrategia = (campo: string) => CAMPOS_ESTRATEGIA[campo]?.[0] ?? campo;
export function valorEstrategia(campo: string, valor: number | string | null): string {
  if (valor === null) return campo === "areas_reservadas" ? "ninguna" : NO_APLICA;
  return CAMPOS_ESTRATEGIA[campo]?.[1](valor) ?? String(valor);
}
