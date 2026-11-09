import { useEffect, useState } from "react";

import { generarAlternativa } from "../api/alternativas";
import type { ErrorOut } from "../api/errores";
import type { ProyectoOut } from "../api/proyectos";
import { escribirNumero, leerNumero, patron } from "../formato";
import { navegar, rutas } from "../hooks/useRuta";
import { AvisoError } from "./AvisoError";

type Props = {
  proyecto: ProyectoOut;
  // Después de generar: recargar el proyecto (la alternativa nueva).
  onGenerada: () => void;
  // Si el motor no puede, la API manda la geometría del problema: la dibuja el mapa de la página.
  onGeometriaError?: (geometria: ErrorOut["geometria"]) => void;
};

// «+ Generar alternativa» (CU06; barra de la figura 17): abre un diálogo con la estrategia que sugiere
// la API (p. 43, paso 1), para confirmarla o cambiarla. El portal no decide valores por defecto (D37).
export function BotonGenerar(props: Props) {
  const [abierto, setAbierto] = useState(false);
  return (
    <>
      <button type="button" className="boton boton--primario" onClick={() => setAbierto(true)}>
        + Generar alternativa
      </button>
      {abierto && <DialogoGenerar {...props} onCerrar={() => setAbierto(false)} />}
    </>
  );
}

function DialogoGenerar({ proyecto: p, onGenerada, onGeometriaError, onCerrar }: Props & { onCerrar: () => void }) {
  const sugerida = p.estrategia_sugerida;
  const [valores, setValores] = useState({
    orientacion: escribirNumero(sugerida.orientacion_grados),
    semilla: String(sugerida.semilla),
  });
  const [generando, setGenerando] = useState(false);
  const [error, setError] = useState<ErrorOut | null>(null);

  useEffect(() => {
    const alTeclear = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !generando) onCerrar();
    };
    document.addEventListener("keydown", alTeclear);
    return () => document.removeEventListener("keydown", alTeclear);
  }, [generando, onCerrar]);

  async function generar() {
    setGenerando(true);
    setError(null);
    onGeometriaError?.(null);
    const resultado = await generarAlternativa(p.id_proyecto, {
      patron_red: sugerida.patron_red,
      orientacion_grados: leerNumero(valores.orientacion),
      semilla: leerNumero(valores.semilla),
    });
    setGenerando(false);
    if (resultado.ok) {
      onGenerada();
      onCerrar();
      navegar(rutas.alternativa(p.id_proyecto, resultado.datos.codigo));
    } else {
      setError(resultado.error);
      onGeometriaError?.(resultado.error.geometria ?? null);
    }
  }

  return (
    <div
      className="dialogo-fondo"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !generando) onCerrar();
      }}
    >
      <div className="dialogo" role="dialog" aria-modal="true" aria-labelledby="titulo-generar">
        <h2 id="titulo-generar">Generar una alternativa</h2>
        <p className="texto-tenue">
          Sugerida: la grilla paralela al lado mayor del terreno. Se genera con los parámetros
          {p.parametros ? ` v${p.parametros.version}` : ""} vigentes.
        </p>
        <div className="generar__campos">
          <div className="campo">
            <label htmlFor="patron">Patrón</label>
            <input id="patron" value={patron(sugerida.patron_red)} readOnly />
          </div>
          <div className="campo">
            <label htmlFor="orientacion">Orientación (°)</label>
            <input
              id="orientacion"
              inputMode="decimal"
              value={valores.orientacion}
              onChange={(e) => setValores({ ...valores, orientacion: e.target.value })}
            />
          </div>
          <div className="campo">
            <label htmlFor="semilla">Semilla</label>
            <input
              id="semilla"
              inputMode="numeric"
              value={valores.semilla}
              onChange={(e) => setValores({ ...valores, semilla: e.target.value })}
            />
          </div>
        </div>
        {error && <AvisoError error={error} titulo="No se pudo generar la alternativa" />}
        {generando && (
          <p className="dialogo__generando" role="status">
            <span className="velo__giro" aria-hidden="true" />
            Generando alternativa…
          </p>
        )}
        <div className="acciones acciones--derecha acciones--pie">
          <button type="button" className="boton" disabled={generando} onClick={onCerrar}>
            Cancelar
          </button>
          <button type="button" className="boton boton--primario" disabled={generando} onClick={generar}>
            {generando ? "Generando…" : "Generar alternativa"}
          </button>
        </div>
      </div>
    </div>
  );
}
