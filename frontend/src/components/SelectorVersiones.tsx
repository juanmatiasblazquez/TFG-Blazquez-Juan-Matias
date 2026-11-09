import type { VersionResumen } from "../api/alternativas";
import { rutas, type PestanaAlternativa } from "../hooks/useRuta";
import { Desplegable } from "./Marco";

type Props = {
  idProyecto: number;
  codigo: string;
  versiones: VersionResumen[];
  actual: number;
  // La pestaña en la que se está: al cambiar de versión se sigue en ella (las observaciones son de la
  // alternativa, así que desde ahí se va al resumen).
  pestana?: PestanaAlternativa;
};

// «Versión 2 · desde v1» (figura 18; CU10): un recálculo dice de qué versión sale, y una copia (volver a
// una versión anterior, D60) de cuál es copia. Cada versión tiene su dirección; la vigente es la de mayor
// número.
export function SelectorVersiones({ idProyecto, codigo, versiones, actual, pestana = "resumen" }: Props) {
  const numeroDe = new Map(versiones.map((v) => [v.id_version, v.numero]));
  const nombre = (v: VersionResumen) => {
    const origen = v.id_version_origen === null ? null : numeroDe.get(v.id_version_origen);
    return `Versión ${v.numero}${v.tipo === "copia" ? ` · copia de v${origen}` : v.tipo === "recalculada" ? ` · desde v${origen}` : ""}`;
  };
  const elegida = versiones.find((v) => v.numero === actual);
  const vigente = Math.max(...versiones.map((v) => v.numero));
  return (
    <Desplegable
      claseBoton="selector"
      titulo={`Versiones de la alternativa ${codigo}`}
      etiqueta={elegida ? nombre(elegida) : `Versión ${actual}`}
    >
      {(cerrar) =>
        versiones.map((v) => (
          <a
            key={v.id_version}
            href={
              pestana === "versiones"
                ? rutas.versiones(idProyecto, codigo, v.numero)
                : rutas.version(idProyecto, codigo, v.numero)
            }
            className={`desplegable__item ${v.numero === actual ? "desplegable__item--actual" : ""}`}
            aria-current={v.numero === actual ? "page" : undefined}
            onClick={cerrar}
          >
            {nombre(v)}
            {v.numero === vigente && <span className="insignia insignia--ok">Vigente</span>}
          </a>
        ))
      }
    </Desplegable>
  );
}
