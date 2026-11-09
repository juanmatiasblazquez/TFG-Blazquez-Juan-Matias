// Cliente HTTP mínimo sobre fetch.
//
// La API vive en el MISMO origen que el frontend: en desarrollo y en producción Nginx deriva
// /api a la API (frontend/nginx/api.inc). Por eso la base es relativa y no hay CORS ni una
// variable de entorno con la URL de la API (a diferencia de GO7, docs/decisiones.md D09).
import type { ErrorOut } from "./errores";

const BASE_URL = "/api";

export type Respuesta<T> = {
  ok: boolean;
  status: number;
  // null cuando la respuesta no es JSON (p. ej. el 502 de Nginx si la API está caída).
  cuerpo: T | null;
};

// El evento con el que el portal se entera de que la sesión dejó de valer (venció, se cerró o al
// usuario lo dieron de baja): la API respondió 401 a un pedido del dominio (D63). Lo escucha
// `hooks/useSesion`. Los pedidos de la propia sesión (`/sesion`) no lo disparan: los maneja ella. Los
// de la página del cliente (`/compartido`) tampoco: el cliente no tiene sesión (CU15, D71).
export const SESION_NO_VALIDA = "sesion-no-valida";

// Lanza solo si no hubo respuesta HTTP (red caída o pedido cancelado). Un 4xx/5xx vuelve
// como Respuesta con ok=false: algunos, como el 503 de /api/health, traen un cuerpo útil.
// La cookie de la sesión la manda el navegador solo: es del mismo origen y `HttpOnly` (D63), así
// que ningún script la lee ni la escribe.
export async function pedir<T>(ruta: string, init?: RequestInit): Promise<Respuesta<T>> {
  const respuesta = await fetch(`${BASE_URL}${ruta}`, {
    ...init,
    credentials: init?.credentials ?? "same-origin",
    headers: { Accept: "application/json", ...init?.headers },
  });
  if (respuesta.status === 401 && !ruta.startsWith("/sesion") && !ruta.startsWith("/compartido")) {
    window.dispatchEvent(new Event(SESION_NO_VALIDA));
  }
  const esJson = respuesta.headers.get("content-type")?.includes("application/json") ?? false;
  const cuerpo = esJson ? ((await respuesta.json()) as T) : null;
  return { ok: respuesta.ok, status: respuesta.status, cuerpo };
}

// Un pedido al dominio: los datos, o el error en el formato único de la API (D32). Las reglas
// las decide la API; el frontend muestra la causa, la sugerencia y los problemas que devuelve.
export type Resultado<T> = { ok: true; datos: T } | { ok: false; status: number; error: ErrorOut };

export async function consultar<T>(ruta: string, init?: RequestInit): Promise<Resultado<T>> {
  let respuesta: Respuesta<unknown>;
  try {
    respuesta = await pedir<unknown>(ruta, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    return {
      ok: false,
      status: 0,
      error: errorSinRespuesta("No hubo respuesta de la API.", "Revisá que los contenedores estén levantados."),
    };
  }
  if (respuesta.ok && respuesta.cuerpo !== null) return { ok: true, datos: respuesta.cuerpo as T };
  // 204: hecho, sin cuerpo (cerrar sesión).
  if (respuesta.status === 204) return { ok: true, datos: null as T };
  if (esErrorOut(respuesta.cuerpo)) return { ok: false, status: respuesta.status, error: respuesta.cuerpo };
  return {
    ok: false,
    status: respuesta.status,
    error: errorSinRespuesta(
      `La API respondió HTTP ${respuesta.status} sin detalle.`,
      "Revisá el registro de la API: docker compose logs api.",
    ),
  };
}

export function enviar<T>(
  ruta: string,
  cuerpo: unknown,
  metodo: "POST" | "PUT" | "PATCH" | "DELETE" = "POST",
  // Para los pedidos que se repiten mientras se edita (la coherencia, la medición): el anterior se cancela.
  cancelacion?: AbortSignal,
): Promise<Resultado<T>> {
  return consultar<T>(ruta, {
    method: metodo,
    headers: { "Content-Type": "application/json" },
    body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
    signal: cancelacion,
  });
}

function esErrorOut(cuerpo: unknown): cuerpo is ErrorOut {
  return typeof cuerpo === "object" && cuerpo !== null && "causa" in cuerpo;
}

function errorSinRespuesta(causa: string, sugerencia: string): ErrorOut {
  return { causa, sugerencia, problemas: [], geometria: null };
}
