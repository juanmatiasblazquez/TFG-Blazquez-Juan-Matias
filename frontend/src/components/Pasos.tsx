// Los pasos del alta en la barra de la página (figuras 15 y 16): «✓ Datos del proyecto —— ✓ Terreno ——
// 3 Parámetros». Un paso con `onElegir` se puede abrir; uno con problemas lleva un punto rojo.
export type PasoBarra = {
  texto: string;
  estado: "hecho" | "actual" | "pendiente";
  onElegir?: () => void;
  conProblemas?: boolean;
};

export function Pasos({ pasos }: { pasos: PasoBarra[] }) {
  return (
    <ol className="pasos" aria-label="Pasos">
      {pasos.map((paso, k) => (
        <li key={paso.texto} className={`pasos__paso pasos__paso--${paso.estado}`}>
          {k > 0 && <span className="pasos__linea" aria-hidden="true" />}
          <button
            type="button"
            className="pasos__boton"
            disabled={!paso.onElegir}
            onClick={paso.onElegir}
            aria-current={paso.estado === "actual" ? "step" : undefined}
          >
            <span className="pasos__numero" aria-hidden="true">
              {paso.estado === "hecho" ? "✓" : k + 1}
            </span>
            {paso.texto}
            {paso.conProblemas && <span className="pasos__marca" title="Hay datos para corregir" />}
          </button>
        </li>
      ))}
    </ol>
  );
}
