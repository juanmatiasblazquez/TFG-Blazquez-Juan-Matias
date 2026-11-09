import { useEffect, useState } from "react";

import { consultarSalud, type Salud } from "../api/salud";

export type EstadoApi =
  | { tipo: "verificando" }
  | { tipo: "operativa"; salud: Salud }
  | { tipo: "degradada"; salud: Salud }
  | { tipo: "sin-conexion" };

// Cada cuánto se vuelve a consultar /api/health: el indicador refleja una caída sin recargar.
const INTERVALO_MS = 10_000;

export function useEstadoApi(): EstadoApi {
  const [estado, setEstado] = useState<EstadoApi>({ tipo: "verificando" });

  useEffect(() => {
    let vigente = true;
    let controlador: AbortController | null = null;

    async function consultar() {
      controlador?.abort();
      controlador = new AbortController();
      try {
        const { cuerpo } = await consultarSalud(controlador.signal);
        if (!vigente) return;
        if (cuerpo === null) {
          // Respondió Nginx pero no la API (502/504 en HTML).
          setEstado({ tipo: "sin-conexion" });
        } else {
          setEstado({ tipo: cuerpo.estado === "ok" ? "operativa" : "degradada", salud: cuerpo });
        }
      } catch (error) {
        if (vigente && !(error instanceof DOMException && error.name === "AbortError")) {
          setEstado({ tipo: "sin-conexion" });
        }
      }
    }

    void consultar();
    const intervalo = window.setInterval(() => void consultar(), INTERVALO_MS);
    return () => {
      vigente = false;
      window.clearInterval(intervalo);
      controlador?.abort();
    };
  }, []);

  return estado;
}
