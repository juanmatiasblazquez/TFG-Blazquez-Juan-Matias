import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { SESION_NO_VALIDA } from "../api/client";
import { cerrarSesion, consultarSesion, type Funcion, type SesionOut } from "../api/sesion";
import { descartarBorrador } from "../borrador";

// La sesión del portal (D63). El token vive en una cookie HttpOnly que el navegador manda solo: acá
// no se guarda nada, ni en localStorage ni en memoria (el borrador del alta no es de la sesión, D81). Lo que se sabe de la sesión es lo que responde
// `GET /api/sesion`: quién es, qué funciones de la p. 54 tiene y cuánto le queda.
//
// - Al abrir el portal se pregunta por la sesión; sin sesión, se muestra el inicio de sesión.
// - Un 401 de cualquier pedido del dominio (`SESION_NO_VALIDA`) vuelve al inicio de sesión con el
//   aviso de que venció: puede haber vencido, haberse cerrado en otra pestaña o haber sido dada de baja.
// - A los 10 minutos del vencimiento aparece un aviso, y al vencer se vuelve al inicio de sesión.
//   Se cuenta desde `segundos_restantes`, el reloj de la API, no la hora de la máquina.
// - La dirección (el hash) no cambia: al volver a entrar se sigue donde se estaba.

export type EstadoSesion =
  | { tipo: "cargando" }
  | { tipo: "sin-sesion"; aviso: string | null }
  | { tipo: "activa"; sesion: SesionOut; venceEn: number };

const AVISO_ANTES_MS = 10 * 60 * 1000;
const VENCIDA = "Tu sesión venció o ya no es válida. Iniciá sesión de nuevo para seguir donde estabas.";
const CERRADA = "Cerraste la sesión.";

type ValorSesion = {
  estado: EstadoSesion;
  sesion: SesionOut | null;
  // Si el rol tiene esta función de la p. 54. Solo oculta: quien decide es la API (D37).
  puede: (funcion: Funcion) => boolean;
  // Minutos que le quedan a la sesión, solo cuando faltan 10 o menos (para el aviso).
  minutosRestantes: number | null;
  entrar: (sesion: SesionOut) => void;
  salir: () => Promise<void>;
};

const Contexto = createContext<ValorSesion | null>(null);

function activa(sesion: SesionOut): EstadoSesion {
  return { tipo: "activa", sesion, venceEn: Date.now() + sesion.segundos_restantes * 1000 };
}

export function ProveedorSesion({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<EstadoSesion>({ tipo: "cargando" });
  const [ahora, setAhora] = useState(() => Date.now());

  useEffect(() => {
    const controlador = new AbortController();
    consultarSesion(controlador.signal).then(
      (resultado) => setEstado(resultado.ok ? activa(resultado.datos) : { tipo: "sin-sesion", aviso: null }),
      (error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) throw error;
      },
    );
    return () => controlador.abort();
  }, []);

  useEffect(() => {
    const alPerderla = () => setEstado((e) => (e.tipo === "activa" ? { tipo: "sin-sesion", aviso: VENCIDA } : e));
    window.addEventListener(SESION_NO_VALIDA, alPerderla);
    return () => window.removeEventListener(SESION_NO_VALIDA, alPerderla);
  }, []);

  useEffect(() => {
    if (estado.tipo !== "activa") return;
    const intervalo = window.setInterval(() => setAhora(Date.now()), 15_000);
    return () => window.clearInterval(intervalo);
  }, [estado.tipo]);

  useEffect(() => {
    if (estado.tipo === "activa" && ahora >= estado.venceEn) setEstado({ tipo: "sin-sesion", aviso: VENCIDA });
  }, [ahora, estado]);

  const entrar = useCallback((sesion: SesionOut) => {
    setAhora(Date.now());
    setEstado(activa(sesion));
  }, []);

  const salir = useCallback(async () => {
    // El borrador del alta es de quien lo escribió: no queda para el que use el navegador después (D81).
    if (estado.tipo === "activa") descartarBorrador(estado.sesion.usuario.id_usuario);
    await cerrarSesion();
    setEstado({ tipo: "sin-sesion", aviso: CERRADA });
  }, [estado]);

  const valor = useMemo<ValorSesion>(() => {
    const sesion = estado.tipo === "activa" ? estado.sesion : null;
    const restante = estado.tipo === "activa" ? estado.venceEn - ahora : null;
    return {
      estado,
      sesion,
      puede: (funcion) => sesion?.permisos.includes(funcion) ?? false,
      minutosRestantes:
        restante !== null && restante <= AVISO_ANTES_MS ? Math.max(1, Math.ceil(restante / 60_000)) : null,
      entrar,
      salir,
    };
  }, [estado, ahora, entrar, salir]);

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useSesion(): ValorSesion {
  const valor = useContext(Contexto);
  if (valor === null) throw new Error("useSesion va dentro de ProveedorSesion");
  return valor;
}
