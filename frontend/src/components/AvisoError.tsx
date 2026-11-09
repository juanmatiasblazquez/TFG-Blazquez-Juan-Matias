import { useEffect, useRef } from "react";

import type { ErrorOut } from "../api/errores";

type Props = {
  error: ErrorOut;
  // Qué se estaba haciendo, por ejemplo «No se pudo generar la alternativa».
  titulo?: string;
};

// Un error de la API tal como llega (D32): la causa, la sugerencia y los problemas por campo.
// Al aparecer se desplaza hasta quedar a la vista: el botón que lo provocó puede estar lejos.
export function AvisoError({ error, titulo }: Props) {
  const aviso = useRef<HTMLDivElement>(null);
  useEffect(() => {
    aviso.current?.scrollIntoView({ block: "nearest" });
  }, [error]);

  return (
    <div className="aviso aviso--error" role="alert" ref={aviso}>
      {titulo && <p className="aviso__titulo">{titulo}</p>}
      <p>
        <strong>Causa:</strong> {error.causa}
      </p>
      {error.sugerencia && (
        <p>
          <strong>Sugerencia:</strong> {error.sugerencia}
        </p>
      )}
      {error.problemas.length > 0 && (
        <ul className="aviso__problemas">
          {error.problemas.map((problema) => (
            <li key={`${problema.campo}:${problema.mensaje}`}>
              <code>{problema.campo}</code>: {problema.mensaje}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
