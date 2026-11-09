import { useState } from "react";

import type { ErrorOut } from "../api/errores";
import {
  configurarParametros,
  consultarReferencia,
  consultarVersionesParametros,
  type ConjuntoParametrosOut,
} from "../api/parametros";
import type { ProyectoOut } from "../api/proyectos";
import { AvisoError } from "../components/AvisoError";
import { ReferenciaNormativa, TarjetaCoherencia, useCoherencia } from "../components/CoherenciaParametros";
import {
  FormularioParametros,
  formularioDesde,
  parametrosDesde,
  problemasPorCampo,
  type FormParametros,
} from "../components/FormularioParametros";
import { BarraPagina, Marca, TarjetaSeccion } from "../components/Marco";
import { Pasos } from "../components/Pasos";
import { enumerar, fecha, tipoProyecto } from "../formato";
import { useConsulta } from "../hooks/useConsulta";
import { rutas } from "../hooks/useRuta";
import { useSesion } from "../hooks/useSesion";

// Los parámetros del proyecto (CU05; figura 16). Cada cambio crea una versión nueva del conjunto, que pasa
// a ser la vigente; las alternativas ya generadas conservan la suya (D36). A la derecha, las versiones del
// conjunto (D82), la coherencia en vivo (D78) y el efecto del cambio. Todo lo decide la API (D37).
export function PaginaParametros({ proyecto: p, recargar }: { proyecto: ProyectoOut; recargar: () => void }) {
  const { puede } = useSesion();
  const puedeEditar = puede("registrar_proyectos");
  const referencia = useConsulta("referencia", consultarReferencia);
  const vigente = p.parametros;
  const versiones = useConsulta(`parametros:${p.id_proyecto}:${vigente?.version ?? 0}`, (c) =>
    consultarVersionesParametros(p.id_proyecto, c),
  );
  const [edicion, setEdicion] = useState<FormParametros | null>(null);
  // La versión anterior que se está mirando, de solo lectura («Ver»).
  const [vista, setVista] = useState<number | null>(null);
  const [error, setError] = useState<ErrorOut | null>(null);
  const [guardando, setGuardando] = useState(false);

  const mirada = vista === null ? null : (versiones.datos?.find((v) => v.version === vista) ?? null);
  const mostrado = edicion ?? (mirada ? formularioDesde(mirada) : vigente ? formularioDesde(vigente) : null);
  // La coherencia la valida quien puede configurar los parámetros (p. 54).
  const coherencia = useCoherencia(puedeEditar ? mostrado : null);
  const problemas = edicion ? { ...coherencia.problemas, ...problemasPorCampo(error?.problemas ?? []) } : {};
  const version = vigente?.version ?? 0;

  async function guardar() {
    if (!edicion) return;
    setGuardando(true);
    setError(null);
    const resultado = await configurarParametros(p.id_proyecto, parametrosDesde(edicion));
    setGuardando(false);
    if (resultado.ok) {
      setEdicion(null);
      recargar();
    } else {
      setError(resultado.error);
    }
  }

  const insignia = edicion
    ? { clase: "insignia--aviso", texto: `Editando versión ${version + 1}` }
    : mirada && !mirada.vigente
      ? { clase: "", texto: `Viendo la versión ${mirada.version}` }
      : { clase: "insignia--ok", texto: `Versión ${version} vigente` };
  return (
    <div className="vista">
      <BarraPagina
        migas={[
          { texto: "Proyectos", href: rutas.proyectos },
          { texto: p.nombre, href: rutas.proyecto(p.id_proyecto) },
        ]}
        titulo="Parámetros del proyecto"
        centro={
          <Pasos
            pasos={[
              { texto: "Datos del proyecto", estado: "hecho" },
              { texto: "Terreno", estado: "hecho" },
              { texto: "Parámetros", estado: "actual" },
            ]}
          />
        }
        acciones={
          <>
            <span className="insignia insignia--grande">Tipo: {tipoProyecto(p.tipo).toLowerCase()}</span>
            {vigente && <span className={`insignia insignia--grande ${insignia.clase}`}>{insignia.texto}</span>}
            {vigente && puedeEditar && !edicion && (
              <button
                type="button"
                className="boton"
                onClick={() => {
                  setVista(null);
                  setEdicion(formularioDesde(vigente));
                }}
              >
                Editar parámetros
              </button>
            )}
          </>
        }
      />
      <div className="vista__cuerpo vista__cuerpo--hoja">
        <div className="parametros-pagina">
          <div className="parametros-pagina__principal">
            {!vigente && <p className="texto-tenue">El proyecto no tiene parámetros vigentes.</p>}
            {referencia.error && <AvisoError error={referencia.error} titulo="No se pudieron leer las fuentes" />}
            {mirada && !mirada.vigente && !edicion && (
              <p className="aviso aviso--info">
                La versión {mirada.version}, de solo lectura.{" "}
                <button type="button" className="boton boton--enlace" onClick={() => setVista(null)}>
                  Volver a la vigente
                </button>
              </p>
            )}
            {error && <AvisoError error={error} titulo="No se guardaron los parámetros" />}
            {mostrado && referencia.datos && (
              <FormularioParametros
                form={mostrado}
                onCambio={edicion ? setEdicion : undefined}
                fuentes={referencia.datos.fuentes}
                referencia={referencia.datos.valores}
                problemas={problemas}
                anchosTotales={edicion ? coherencia.datos?.anchos_totales : null}
                enUso={edicion ? coherencia.datos?.jerarquias_en_uso : null}
              />
            )}
            <ReferenciaNormativa />
            {edicion && (
              <div className="acciones acciones--derecha">
                <button
                  type="button"
                  className="boton"
                  onClick={() => {
                    setEdicion(null);
                    setError(null);
                  }}
                >
                  Cancelar
                </button>
                <button type="button" className="boton boton--primario" disabled={guardando} onClick={guardar}>
                  {guardando ? "Guardando…" : `Guardar como versión ${version + 1}`}
                </button>
              </div>
            )}
          </div>
          <aside className="parametros-pagina__lateral" aria-label="Versiones y validación">
            {versiones.error && <AvisoError error={versiones.error} titulo="No se pudieron leer las versiones" />}
            {versiones.datos && (
              <TarjetaVersiones
                versiones={versiones.datos}
                nueva={edicion ? version + 1 : null}
                vista={mirada?.version ?? version}
                onVer={edicion ? undefined : (v) => setVista(v.vigente ? null : v.version)}
              />
            )}
            {puedeEditar && mostrado && <TarjetaCoherencia coherencia={coherencia} />}
            {versiones.datos && <TarjetaEfecto versiones={versiones.datos} nueva={edicion ? version + 1 : null} />}
          </aside>
        </div>
      </div>
    </div>
  );
}

type PropsVersiones = {
  versiones: ConjuntoParametrosOut[];
  // La que se está editando, sin guardar.
  nueva: number | null;
  // La que se muestra en el formulario.
  vista: number;
  onVer?: (version: ConjuntoParametrosOut) => void;
};

// «Versiones del conjunto» (figura 16; D82): de la última a la primera, con las alternativas que conservan
// cada una. El ER no guarda quién creó cada versión (D29).
function TarjetaVersiones({ versiones, nueva, vista, onVer }: PropsVersiones) {
  return (
    <TarjetaSeccion titulo="Versiones del conjunto">
      <ul className="versiones-conjunto">
        {nueva !== null && (
          <li>
            <span className="versiones-conjunto__numero versiones-conjunto__numero--edicion">v{nueva}</span>
            <div>
              <strong>En edición</strong>
              <span>Sin guardar</span>
            </div>
          </li>
        )}
        {versiones.map((v) => (
          <li key={v.id_conjunto} className={nueva === null && v.version === vista ? "versiones-conjunto__actual" : ""}>
            <span className={`versiones-conjunto__numero ${v.vigente ? "versiones-conjunto__numero--vigente" : ""}`}>
              v{v.version}
            </span>
            <div>
              <strong>{v.vigente ? "Vigente" : "Anterior"}</strong>
              <span>
                {fecha(v.fecha_creacion)} ·{" "}
                {v.usada_por.length === 0 ? "sin alternativas" : `usada por ${enumerar(v.usada_por)}`}
              </span>
            </div>
            {onVer && v.version !== vista && (
              <button type="button" className="boton boton--enlace" onClick={() => onVer(v)}>
                Ver
              </button>
            )}
          </li>
        ))}
      </ul>
    </TarjetaSeccion>
  );
}

// «Efecto del cambio» (figura 16): las alternativas conservan su versión; lo nuevo usa la vigente (D36).
function TarjetaEfecto({ versiones, nueva }: { versiones: ConjuntoParametrosOut[]; nueva: number | null }) {
  const conservan = versiones.filter((v) => v.usada_por.length > 0);
  const vigente = versiones.find((v) => v.vigente)?.version;
  return (
    <TarjetaSeccion titulo="Efecto del cambio">
      <div className="efecto">
        <Marca tipo={nueva === null ? "info" : "aviso"} />
        <div>
          <strong>
            {conservan.length === 0
              ? "Todavía no hay alternativas generadas"
              : conservan
                  .map(
                    (v) =>
                      `${v.usada_por.length === 1 ? `La alternativa ${v.usada_por[0]} conserva` : `Las alternativas ${enumerar(v.usada_por)} conservan`} la versión ${v.version}`,
                  )
                  .join("; ")}
          </strong>
          <p>
            {nueva === null
              ? `Las nuevas generaciones y recálculos usan la versión ${vigente}.`
              : `Las nuevas generaciones y recálculos usarán la versión ${nueva} una vez guardada.`}
          </p>
        </div>
      </div>
    </TarjetaSeccion>
  );
}
