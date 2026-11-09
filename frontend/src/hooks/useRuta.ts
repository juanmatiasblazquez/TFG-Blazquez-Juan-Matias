import { useEffect, useState } from "react";

// Rutas por hash (D37): cada pantalla tiene su dirección, sin sumar un enrutador ni tocar la
// configuración de Nginx (el servidor siempre entrega index.html).
//   #/                          lista de proyectos
//   #/proyectos/nuevo           alta en tres pasos
//   #/proyectos/7               página del proyecto: sus datos, sus alternativas y lo demás (D73)
//   #/proyectos/7/B             la alternativa B, en su versión vigente (prototipo de la p. 49)
//   #/proyectos/7/B/2           la versión 2 de la alternativa B (CU10, D57)
//   #/proyectos/7/B/versiones   la alternativa B, con la pestaña «Versiones» (p. 50; D73)
//   #/proyectos/7/B/2/versiones la versión 2 de B, con la pestaña «Versiones»
//   #/proyectos/7/B/observaciones   la alternativa B, con sus observaciones (CU11, CU12; p. 50; D69)
//   #/proyectos/7/parametros    los parámetros del proyecto
//   #/proyectos/7/areas         las áreas reservadas (y su edición, D59)
//   #/proyectos/7/compartir     la selección y los enlaces compartidos (CU14; D70)
//   #/usuarios                  gestión de usuarios (CU02)
//   #/contrasena                cambiar la contraseña propia
//   #/proyectos/7/comparar/A/B  comparación de las alternativas A y B (o A/B/C; CU13, D54)
//   #/proyectos/7/comparar/A.1/A.2  comparación de las versiones 1 y 2 de A (D57)
//   #/compartido/<token>        lo que ve el cliente, sin sesión (CU15). El token va en el fragmento,
//                               que el navegador no manda al servidor ni pone en un Referer (D71)
export type PestanaAlternativa = "resumen" | "versiones" | "observaciones";

export type RutaProyecto =
  | { pagina: "proyecto"; id: number; seccion: "resumen" }
  | {
      pagina: "proyecto";
      id: number;
      seccion: "alternativas";
      alternativa: string;
      version: number | null;
      pestana: PestanaAlternativa;
    }
  | { pagina: "proyecto"; id: number; seccion: "parametros" }
  | { pagina: "proyecto"; id: number; seccion: "areas" }
  | { pagina: "proyecto"; id: number; seccion: "compartir" };

export type Ruta =
  | { pagina: "proyectos" }
  | { pagina: "nuevo" }
  | RutaProyecto
  | { pagina: "compartido"; token: string }
  | { pagina: "usuarios" }
  | { pagina: "contrasena" }
  | { pagina: "comparacion"; id: number; codigos: string[] }
  | { pagina: "no-encontrada" };

export const rutas = {
  proyectos: "#/",
  nuevo: "#/proyectos/nuevo",
  proyecto: (id: number) => `#/proyectos/${id}`,
  alternativa: (id: number, codigo: string) => `#/proyectos/${id}/${codigo}`,
  version: (id: number, codigo: string, numero: number) => `#/proyectos/${id}/${codigo}/${numero}`,
  // La pestaña «Versiones» de la vigente o de una versión (p. 50).
  versiones: (id: number, codigo: string, numero: number | null = null) =>
    `#/proyectos/${id}/${codigo}${numero === null ? "" : `/${numero}`}/versiones`,
  parametros: (id: number) => `#/proyectos/${id}/parametros`,
  areas: (id: number) => `#/proyectos/${id}/areas`,
  observaciones: (id: number, codigo: string) => `#/proyectos/${id}/${codigo}/observaciones`,
  compartir: (id: number) => `#/proyectos/${id}/compartir`,
  usuarios: "#/usuarios",
  contrasena: "#/contrasena",
  // Las alternativas en el orden de la tabla: la primera es contra la que se calculan las
  // diferencias. Una versión se escribe «A.2» (`codigoVersion`).
  comparacion: (id: number, codigos: string[]) => `#/proyectos/${id}/comparar${codigos.map((c) => `/${c}`).join("")}`,
};

export function leerRuta(hash: string): Ruta {
  const partes = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (partes.length === 0 || (partes.length === 1 && partes[0] === "proyectos")) return { pagina: "proyectos" };
  if (partes.length === 1 && partes[0] === "usuarios") return { pagina: "usuarios" };
  if (partes.length === 1 && partes[0] === "contrasena") return { pagina: "contrasena" };
  if (partes[0] === "compartido") {
    return partes.length === 2 ? { pagina: "compartido", token: partes[1] } : { pagina: "no-encontrada" };
  }
  if (partes[0] !== "proyectos") return { pagina: "no-encontrada" };
  if (partes[1] === "nuevo") return partes.length === 2 ? { pagina: "nuevo" } : { pagina: "no-encontrada" };
  const id = Number(partes[1]);
  if (!Number.isInteger(id) || id <= 0) return { pagina: "no-encontrada" };
  // Cuántas se pueden comparar lo dice la API (D37): acá solo se leen los códigos.
  if (partes[2] === "comparar") return { pagina: "comparacion", id, codigos: partes.slice(3) };
  if (partes[2] === "parametros") {
    return partes.length === 3 ? { pagina: "proyecto", id, seccion: "parametros" } : { pagina: "no-encontrada" };
  }
  if (partes[2] === "areas") {
    return partes.length === 3 ? { pagina: "proyecto", id, seccion: "areas" } : { pagina: "no-encontrada" };
  }
  if (partes[2] === "compartir") {
    return partes.length === 3 ? { pagina: "proyecto", id, seccion: "compartir" } : { pagina: "no-encontrada" };
  }
  if (partes.length === 2) return { pagina: "proyecto", id, seccion: "resumen" };
  if (partes.length > 5) return { pagina: "no-encontrada" };
  const alternativa = partes[2];
  let resto = partes.slice(3);
  let version: number | null = null;
  if (resto.length > 0 && /^\d+$/.test(resto[0])) {
    version = Number(resto[0]);
    if (version <= 0) return { pagina: "no-encontrada" };
    resto = resto.slice(1);
  }
  if (resto.length === 0)
    return { pagina: "proyecto", id, seccion: "alternativas", alternativa, version, pestana: "resumen" };
  if (resto.length === 1 && resto[0] === "versiones") {
    return { pagina: "proyecto", id, seccion: "alternativas", alternativa, version, pestana: "versiones" };
  }
  // Las observaciones son de la alternativa, no de una versión: se registran sobre la vigente (D69).
  if (resto.length === 1 && resto[0] === "observaciones" && version === null) {
    return { pagina: "proyecto", id, seccion: "alternativas", alternativa, version: null, pestana: "observaciones" };
  }
  return { pagina: "no-encontrada" };
}

// Una versión en la dirección de la comparación: «A.2» es la versión 2 de A; «A», la vigente.
export const codigoVersion = (codigo: string, numero: number) => `${codigo}.${numero}`;

// Lo que no se entiende queda como código entero, y la pantalla dice que no existe.
export function leerCodigo(texto: string): { codigo: string; numero: number | null } {
  const [codigo, numero, ...resto] = texto.split(".");
  if (numero === undefined) return { codigo, numero: null };
  const n = Number(numero);
  return resto.length === 0 && Number.isInteger(n) && n > 0 ? { codigo, numero: n } : { codigo: texto, numero: null };
}

export function navegar(hash: string) {
  window.location.hash = hash;
}

export function useRuta(): Ruta {
  const [ruta, setRuta] = useState(() => leerRuta(window.location.hash));
  useEffect(() => {
    const alCambiar = () => setRuta(leerRuta(window.location.hash));
    window.addEventListener("hashchange", alCambiar);
    return () => window.removeEventListener("hashchange", alCambiar);
  }, []);
  return ruta;
}
