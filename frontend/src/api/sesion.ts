// Espejo de backend/app/schemas/sesion.py (D63).
import { consultar, enviar } from "./client";

export type UsuarioSesionOut = {
  id_usuario: number;
  nombre: string;
  apellido: string;
  email: string;
  rol: string;
};

// La sesión actual. `permisos` son las funciones de la tabla de la p. 54 que tiene el rol: con ellas
// el portal oculta lo que no puede hacer, sin copiar la tabla (D37). Quien decide es la API.
export type SesionOut = {
  usuario: UsuarioSesionOut;
  permisos: Funcion[];
  // Con una contraseña temporal, la sesión solo permite cambiarla (p. 53).
  debe_cambiar_contrasena: boolean;
  vence: string;
  // Según el reloj de la API: el aviso de vencimiento no depende de la hora de la máquina.
  segundos_restantes: number;
  politica_contrasena: string;
  // El nombre del estudio (`NOMBRE_ESTUDIO`), para la barra; null si no se configuró (D74).
  estudio: string | null;
};

// Las filas de la tabla de la p. 54 (`app.core.permisos.Funcion`).
export type Funcion =
  | "gestionar_usuarios"
  | "registrar_proyectos"
  | "generar_alternativas"
  | "consultar_alternativas"
  | "registrar_observaciones"
  | "responder_observaciones"
  | "compartir_alternativas";

// CU01: 200 con la sesión (y la cookie, que pone el navegador), 401 con el mensaje genérico o 429 si
// la dirección está bloqueada o pasó el límite por minuto.
export function iniciarSesion(email: string, contrasena: string) {
  return enviar<SesionOut>("/sesion", { email, contrasena });
}

export function consultarSesion(cancelacion?: AbortSignal) {
  return consultar<SesionOut>("/sesion", { signal: cancelacion });
}

export function cerrarSesion() {
  return enviar<null>("/sesion", undefined, "DELETE");
}

export function cambiarContrasena(contrasena_actual: string, contrasena_nueva: string) {
  return enviar<SesionOut>("/sesion/contrasena", { contrasena_actual, contrasena_nueva }, "PUT");
}
