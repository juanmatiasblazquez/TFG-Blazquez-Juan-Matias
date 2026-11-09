import { consultar, enviar } from "./client";

// Espejo de backend/app/schemas/parametros.py: si cambia uno, cambia el otro. Los nombres son
// los del ER (D29). Los valores por defecto y su fuente los sirve la API desde el motor (D36):
// acá no hay una copia.
export type LoteoOut = {
  frente_minimo_m: number;
  frente_objetivo_m: number;
  fondo_minimo_m: number;
  superficie_minima_m2: number;
  superficie_maxima_m2: number;
  relacion_fondo_frente_max: number;
  longitud_maxima_manzana_m: number;
  porcentaje_equipamiento: number;
  // Cuándo un remanente es espacio verde (D41) y el criterio de forma del lote (D43). null es
  // «no aplica»: el conjunto es anterior al motor que usa el parámetro (D45).
  superficie_minima_verde_m2: number | null;
  ancho_minimo_verde_m: number | null;
  ancho_minimo_lote_m: number | null;
  factor_union_maximo: number | null;
  // Ley 4146, art. 12 (D48), Ord. 8060, art. 54 (D49) y el criterio del asignador (D46), de la
  // migración 0006; null en un conjunto anterior al motor 0.6.0.
  porcentaje_minimo_avenidas: number | null;
  ancho_minimo_avenida_m: number | null;
  ancho_minimo_calle_m: number | null;
  ancho_minimo_calzada_m: number | null;
  porcentaje_incremento_esquina: number | null;
  // «cercania» (el de referencia desde el motor 0.7.0, D51) o «menos_lotes»: un criterio de
  // diseño, no una norma.
  criterio_espacio_verde: string | null;
  // Ord. 8060, art. 48 (D50), de la migración 0007; null en un conjunto anterior al motor 0.7.0.
  lado_minimo_manzana_m: number | null;
  lado_maximo_manzana_m: number | null;
  lado_maximo_sin_pasaje_m: number | null;
  // Por dónde va la calle de borde (D86): «por_lado» (el de referencia) o «contorno» (D50), de la
  // migración 0014; null en un conjunto anterior al motor 0.11.0 que ningún motor con calle de borde usó.
  calle_borde: string | null;
};

// Los campos numéricos del loteo: todos menos el criterio del asignador y la calle de borde.
export type CampoLoteo = Exclude<keyof LoteoOut, "criterio_espacio_verde" | "calle_borde">;

export type JerarquiaValoresOut = {
  nombre: string;
  orden: number;
  ancho_calzada_m: number;
  ancho_vereda_m: number;
  // Largo de la línea de ochava (D24); el nombre es el del ER.
  radio_ochava_m: number;
  // Calzada + 2 × vereda: lo calcula el motor (D78). No se manda.
  ancho_total_m: number;
  // Si el motor la usa (D85): sin avenidas, la mayor no. No se manda.
  en_uso: boolean;
};

export type JerarquiaOut = JerarquiaValoresOut & { id_jerarquia: number };

export type ValoresParametrosOut = {
  criterio_prioritario: string;
  porcentaje_espacio_verde: number;
  tolerancia_pct: number;
  loteo: LoteoOut | null;
  jerarquias: JerarquiaValoresOut[];
};

export type ParametrosOut = Omit<ValoresParametrosOut, "jerarquias"> & {
  id_conjunto: number;
  version: number;
  vigente: boolean;
  fecha_creacion: string;
  jerarquias: JerarquiaOut[];
};

// Una versión del conjunto, con las alternativas cuya versión vigente se generó con ella (D82).
export type ConjuntoParametrosOut = ParametrosOut & { usada_por: string[] };

// Una regla de coherencia de la p. 49 o del motor, cumplida o no (D78).
export type ReglaCoherenciaOut = {
  clave: string;
  descripcion: string;
  cumple: boolean;
  detalle: string;
};

export type CoherenciaOut = {
  // Vacía mientras algún valor no sea un número válido.
  reglas: ReglaCoherenciaOut[];
  problemas: { campo: string; mensaje: string }[];
  // Calzada + 2 × vereda de cada jerarquía, con lo que se está editando (la cuenta es del motor).
  anchos_totales: number[];
  // Si el motor usaría cada jerarquía con lo que se está editando (D85).
  jerarquias_en_uso: boolean[];
};

export type FuenteOut = {
  texto: string;
  a_validar: boolean;
  // No sale de una norma (D46): se marca como criterio de diseño.
  criterio_diseno: boolean;
};

export type ReferenciaParametrosOut = {
  tipo: string;
  valores: ValoresParametrosOut;
  // Por campo de ParametrosIn: «loteo.frente_minimo_m», «jerarquias.radio_ochava_m»…
  fuentes: Record<string, FuenteOut>;
};

// ParametrosIn: la misma forma que los valores. Lo que falta va como null, y lo que no es un
// número, como texto: la API dice qué está mal (formato.leerNumero).
type Numero = number | string | null;

export type ParametrosIn = {
  criterio_prioritario: string;
  porcentaje_espacio_verde: Numero;
  tolerancia_pct: Numero;
  loteo: Record<CampoLoteo, Numero> & { criterio_espacio_verde: string | null; calle_borde: string | null };
  jerarquias: {
    nombre: string;
    orden: number;
    ancho_calzada_m: Numero;
    ancho_vereda_m: Numero;
    radio_ochava_m: Numero;
  }[];
};

export function consultarReferencia(cancelacion?: AbortSignal) {
  return consultar<ReferenciaParametrosOut>("/parametros/referencia", { signal: cancelacion });
}

// Las versiones del conjunto, de la última a la primera (D82).
export function consultarVersionesParametros(idProyecto: number, cancelacion?: AbortSignal) {
  return consultar<ConjuntoParametrosOut[]>(`/proyectos/${idProyecto}/parametros`, { signal: cancelacion });
}

// La coherencia de lo que se está editando, sin guardarlo (D78). Un valor con otro tipo da 422, como al
// guardar.
export function validarParametros(datos: ParametrosIn, cancelacion?: AbortSignal) {
  return enviar<CoherenciaOut>("/parametros/validacion", datos, "POST", cancelacion);
}

// CU05: una versión nueva del conjunto, que pasa a ser la vigente.
export function configurarParametros(idProyecto: number, datos: ParametrosIn) {
  return enviar<ParametrosOut>(`/proyectos/${idProyecto}/parametros`, datos);
}
