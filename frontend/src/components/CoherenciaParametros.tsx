import { useEffect, useState } from "react";

import type { ErrorOut } from "../api/errores";
import { validarParametros, type CoherenciaOut } from "../api/parametros";
import { parametrosDesde, problemasPorCampo, type FormParametros } from "./FormularioParametros";
import { Marca, TarjetaSeccion } from "./Marco";

// Cuánto se espera después de la última tecla antes de validar.
const ESPERA_MS = 400;

export type Coherencia = {
  datos: CoherenciaOut | null;
  // Un valor con otro tipo (un número mal escrito) da 422, como al guardar: va con sus problemas.
  error: ErrorOut | null;
  validando: boolean;
  // Los problemas de lo que se está editando, por campo de ParametrosIn: los mismos que daría guardarlo.
  problemas: Record<string, string>;
};

// La validación en vivo de lo que se está editando (figura 16; D78): la hace la API con el motor, un rato
// después de la última tecla. El pedido anterior se cancela.
export function useCoherencia(form: FormParametros | null): Coherencia {
  const [estado, setEstado] = useState<{ datos: CoherenciaOut | null; error: ErrorOut | null }>({
    datos: null,
    error: null,
  });
  const [validando, setValidando] = useState(false);
  const cuerpo = form ? JSON.stringify(parametrosDesde(form)) : null;

  useEffect(() => {
    if (cuerpo === null) return;
    const controlador = new AbortController();
    setValidando(true);
    const temporizador = window.setTimeout(() => {
      validarParametros(JSON.parse(cuerpo), controlador.signal).then(
        (resultado) => {
          setValidando(false);
          setEstado(resultado.ok ? { datos: resultado.datos, error: null } : { datos: null, error: resultado.error });
        },
        (error: unknown) => {
          if (!(error instanceof DOMException && error.name === "AbortError")) throw error;
        },
      );
    }, ESPERA_MS);
    return () => {
      window.clearTimeout(temporizador);
      controlador.abort();
    };
  }, [cuerpo]);

  return {
    ...estado,
    validando,
    problemas: problemasPorCampo(estado.datos?.problemas ?? estado.error?.problemas ?? []),
  };
}

// «Validación de coherencia» (figura 16): las reglas de la p. 49 y las del motor, cumplidas o no, con sus
// valores. Las decide la API (D78).
export function TarjetaCoherencia({ coherencia }: { coherencia: Coherencia }) {
  const { datos, error, validando } = coherencia;
  return (
    <TarjetaSeccion
      titulo="Validación de coherencia"
      extra={validando ? <span className="texto-tenue tarjeta__estado">Validando…</span> : null}
      clase="tarjeta-coherencia"
    >
      {error && (
        <ul className="verificaciones">
          {error.problemas.map((p) => (
            <li key={p.campo}>
              <Marca tipo="error" />
              <strong>Un valor no se puede leer</strong>
              <p>{p.mensaje}</p>
            </li>
          ))}
        </ul>
      )}
      {datos && datos.reglas.length === 0 && (
        <p className="texto-tenue">
          Hay valores que no sirven: se marcan en su campo. Las reglas se revisan cuando los corrijas.
        </p>
      )}
      {datos && datos.reglas.length > 0 && (
        <ul className="verificaciones">
          {datos.reglas.map((r) => (
            <li key={r.clave} data-clave={r.clave}>
              <Marca tipo={r.cumple ? "ok" : "error"} />
              <strong>{r.descripcion}</strong>
              <p>{r.detalle}</p>
            </li>
          ))}
        </ul>
      )}
      {!datos && !error && <p className="texto-tenue">Validando los valores…</p>}
    </TarjetaSeccion>
  );
}

// «Referencia normativa» (figura 16): de dónde salen los valores de referencia (D23).
export function ReferenciaNormativa() {
  return (
    <div className="aviso-info" role="note">
      <Marca tipo="info" />
      <div>
        <strong>Referencia normativa</strong>
        <p>
          Valores de referencia tomados de la Ley Provincial N.º 4146 y de la Ordenanza N.º 8060 de la ciudad de
          Córdoba: el artículo de cada uno está en el ícono § de su campo. Los marcados «A validar» todavía no se
          verificaron contra la norma, y los «Criterio de diseño» no salen de una. Deben verificarse contra la norma de
          la jurisdicción del proyecto.
        </p>
      </div>
    </div>
  );
}
