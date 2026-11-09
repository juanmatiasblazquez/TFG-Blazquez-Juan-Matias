// Espejo de backend/app/schemas/usuario.py (CU02; D66).
import { consultar, enviar } from "./client";

export type UsuarioOut = {
  id_usuario: number;
  nombre: string;
  apellido: string;
  email: string;
  rol: string;
  activo: boolean;
  fecha_alta: string;
  // Con una contraseña temporal pendiente de cambio, y hasta cuándo vale (p. 53).
  debe_cambiar_contrasena: boolean;
  vence_contrasena_temporal: string | null;
};

export type UsuarioIn = { nombre: string; apellido: string; email: string; rol: string };
// `activo: false` es la baja. Reactivar es otra operación, porque genera una temporal nueva (D72).
export type UsuarioCambiosIn = Partial<UsuarioIn> & { activo?: false };

// La contraseña temporal se muestra una sola vez (CU02, paso 6): en la base queda solo su hash.
export type ContrasenaTemporalOut = { contrasena_temporal: string; vence: string };
export type UsuarioCreadoOut = { usuario: UsuarioOut } & ContrasenaTemporalOut;

export function listarUsuarios(cancelacion?: AbortSignal) {
  return consultar<UsuarioOut[]>("/usuarios", { signal: cancelacion });
}

// 201 con la temporal, o 409 si el correo ya está registrado (6.a).
export function crearUsuario(datos: UsuarioIn) {
  return enviar<UsuarioCreadoOut>("/usuarios", datos);
}

// Datos, rol o baja (`activo: false`; nunca se borra).
export function modificarUsuario(idUsuario: number, cambios: UsuarioCambiosIn) {
  return enviar<UsuarioOut>(`/usuarios/${idUsuario}`, cambios, "PATCH");
}

export function reemplazarContrasena(idUsuario: number) {
  return enviar<ContrasenaTemporalOut>(`/usuarios/${idUsuario}/contrasena-temporal`, {});
}

// Vuelve a dar de alta a un usuario desactivado con una temporal nueva, que se muestra una vez (D72).
export function reactivarUsuario(idUsuario: number) {
  return enviar<UsuarioCreadoOut>(`/usuarios/${idUsuario}/reactivacion`, undefined);
}

// Una dirección con el inicio de sesión bloqueado (CU01, 4.b; D65, D72). Espejo de DireccionBloqueadaOut.
export type DireccionBloqueadaOut = {
  direccion: string;
  intentos_fallidos: number;
  bloqueada_hasta: string;
  // Con el reloj de la API.
  segundos_restantes: number;
};

export function listarBloqueadas(cancelacion?: AbortSignal) {
  return consultar<DireccionBloqueadaOut[]>("/direcciones-bloqueadas", { signal: cancelacion });
}

export function desbloquear(direccion: string) {
  return enviar<null>(`/direcciones-bloqueadas/${encodeURIComponent(direccion)}`, undefined, "DELETE");
}
