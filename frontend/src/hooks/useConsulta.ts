import { useCallback, useEffect, useRef, useState } from "react";

import type { Resultado } from "../api/client";
import type { ErrorOut } from "../api/errores";

export type Consulta<T> = {
  datos: T | null;
  error: ErrorOut | null;
  cargando: boolean;
  recargar: () => void;
};

type Estado<T> = { clave: string | null; datos: T | null; error: ErrorOut | null };

// Un GET de la API con su estado. `clave` identifica lo que se pide (por ejemplo «proyecto:7»):
// si cambia, se descarta lo anterior y se vuelve a pedir; `recargar` pide de nuevo sin borrar lo
// que se está mostrando. Con `clave` null no se pide nada.
export function useConsulta<T>(
  clave: string | null,
  cargar: (cancelacion: AbortSignal) => Promise<Resultado<T>>,
): Consulta<T> {
  const [estado, setEstado] = useState<Estado<T>>({ clave: null, datos: null, error: null });
  const [vuelta, setVuelta] = useState(0);
  const cargarActual = useRef(cargar);

  useEffect(() => {
    cargarActual.current = cargar;
  });

  useEffect(() => {
    if (clave === null) return;
    const controlador = new AbortController();
    cargarActual.current(controlador.signal).then(
      (resultado) =>
        setEstado(
          resultado.ok
            ? { clave, datos: resultado.datos, error: null }
            : { clave, datos: null, error: resultado.error },
        ),
      (error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) throw error;
      },
    );
    return () => controlador.abort();
  }, [clave, vuelta]);

  const recargar = useCallback(() => setVuelta((v) => v + 1), []);
  const vigente = estado.clave === clave;
  return {
    datos: vigente ? estado.datos : null,
    error: vigente ? estado.error : null,
    cargando: clave !== null && !vigente,
    recargar,
  };
}
