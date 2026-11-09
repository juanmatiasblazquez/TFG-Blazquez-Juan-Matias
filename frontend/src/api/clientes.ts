import { consultar, enviar } from "./client";

// Espejo de backend/app/schemas/cliente.py (ClienteIn, ClienteOut): si cambia uno, cambia el otro.
export type ClienteIn = {
  razon_social: string;
  cuit: string | null;
  email: string | null;
  telefono: string | null;
};

export type ClienteOut = {
  id_cliente: number;
  razon_social: string;
  // NN-NNNNNNNN-N: la API lo normaliza y verifica (D35).
  cuit: string | null;
  email: string | null;
  telefono: string | null;
};

export function listarClientes(cancelacion?: AbortSignal) {
  return consultar<ClienteOut[]>("/clientes", { signal: cancelacion });
}

export function crearCliente(datos: ClienteIn) {
  return enviar<ClienteOut>("/clientes", datos);
}
