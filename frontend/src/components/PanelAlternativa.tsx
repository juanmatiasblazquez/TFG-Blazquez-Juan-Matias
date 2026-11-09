import { useState } from "react";

import {
  describirAlternativa,
  type AlternativaOut,
  type DiferenciaIndicadorOut,
  type VersionOut,
} from "../api/alternativas";
import type { ErrorOut } from "../api/errores";
import { consultarVersion } from "../api/versiones";
import {
  diferenciaIndicador,
  fechaHoraLarga,
  grados,
  hectareas,
  metros,
  metrosCuadrados,
  NO_APLICA,
  nombreIndicador,
  numero,
  patron,
  porcentaje,
  valorIndicador,
} from "../formato";
import { useConsulta } from "../hooks/useConsulta";
import { codigoVersion, rutas } from "../hooks/useRuta";
import { AvisoError } from "./AvisoError";
import { Marca, nombreCorto, TarjetaSeccion } from "./Marco";

// Las pestañas «Resumen» y «Versiones» de una alternativa (figuras 17 y 18; CU08, CU09, CU10; D73).
// Todo lo calcula el motor y lo guarda la API, también el texto de las verificaciones (D74): acá solo se
// muestra (D37). Los indicadores que un motor anterior no calculaba son null: «no aplica» (D45).

// --- Resumen (figura 17) ------------------------------------------------------------------------------

type PropsResumen = {
  alternativa: AlternativaOut;
  puedeDescribir: boolean;
  // La descripción cambió: recargar la alternativa y el proyecto.
  onCambio: () => void;
};

export function PanelResumen({ alternativa, puedeDescribir, onCambio }: PropsResumen) {
  const v = alternativa.version;
  return (
    <>
      <Estrategia version={v} />
      <Indicadores version={v} />
      <Verificaciones version={v} />
      <DescripcionCliente alternativa={alternativa} puedeDescribir={puedeDescribir} onCambio={onCambio} />
    </>
  );
}

function Estrategia({ version: v }: { version: VersionOut }) {
  return (
    <TarjetaSeccion titulo="Estrategia de generación">
      <dl className="filas">
        <dt>Patrón de red · orientación</dt>
        <dd>
          {patron(v.estrategia.patron_red)} · {grados(v.estrategia.orientacion_grados)}
        </dd>
        <dt>Semilla · parámetros</dt>
        <dd>
          {v.estrategia.semilla} · versión {v.version_parametros}
        </dd>
        <dt>Generada por</dt>
        <dd title={`Motor ${v.version_motor}`}>
          {nombreCorto(v.generada_por.nombre, v.generada_por.apellido)} · {fechaHoraLarga(v.fecha_generacion)} ·{" "}
          {numero(v.duracion_ms / 1000, 1)} s
        </dd>
      </dl>
    </TarjetaSeccion>
  );
}

function Tarjeta({ titulo, valor, unidad, ayuda }: { titulo: string; valor: string; unidad?: string; ayuda?: string }) {
  return (
    <div className="tarjeta-indicador" title={ayuda}>
      <span className="tarjeta-indicador__titulo">{titulo}</span>
      <span className="tarjeta-indicador__valor">
        {valor}
        {unidad && <span className="tarjeta-indicador__unidad"> {unidad}</span>}
      </span>
    </div>
  );
}

// Los seis indicadores de la figura 17 en tarjetas, y los demás en «Más indicadores».
function Indicadores({ version: v }: { version: VersionOut }) {
  const i = v.indicadores;
  // La base de los porcentajes la dice la API (D61): la disponible, o el terreno en una versión anterior.
  const base = i.base_porcentajes === "disponible" ? "de la superficie disponible" : "del terreno";
  return (
    <TarjetaSeccion titulo="Indicadores">
      <div className="tarjetas indicadores">
        <Tarjeta
          titulo="Celdas útiles"
          valor={numero(i.cantidad_celdas, 0)}
          ayuda="Lotes que cumplen todas las restricciones"
        />
        <Tarjeta
          titulo="Superficie aprovechable"
          valor={numero(i.superficie_aprovechable_m2 / 10_000)}
          unidad={`ha · ${numero(i.porcentaje_aprovechamiento, 1)} %`}
          ayuda={`La de las celdas útiles; el porcentaje, ${base}`}
        />
        <Tarjeta
          titulo="Circulación"
          valor={numero(i.porcentaje_circulacion, 1)}
          unidad="%"
          ayuda={`Las calles, ${base}`}
        />
        <Tarjeta
          titulo="Espacios verdes"
          valor={numero(i.porcentaje_espacio_verde, 1)}
          unidad="%"
          ayuda={`Todo el verde, ${base}. La cesión es sobre los lotes: está en «Verificaciones»`}
        />
        <Tarjeta titulo="Longitud de red" valor={numero(i.longitud_red_m / 1000)} unidad="km" />
        <Tarjeta
          titulo="Distancia media al acceso"
          valor={i.distancia_media_acceso_m === null ? "—" : numero(i.distancia_media_acceso_m, 0)}
          unidad={i.distancia_media_acceso_m === null ? undefined : "m"}
          ayuda="De cada lote al acceso más cercano, por la red"
        />
      </div>
      <details className="mas-indicadores">
        <summary>Más indicadores</summary>
        <dl className="filas">
          <dt>Superficie disponible</dt>
          <dd title="El terreno menos las áreas reservadas: lo que se lotea (D61)">
            {hectareas(i.superficie_disponible_m2)}
          </dd>
          <dt>Superficie media de celda</dt>
          <dd>{i.superficie_media_celda_m2 === null ? "—" : metrosCuadrados(i.superficie_media_celda_m2)}</dd>
          <dt>Espacio verde</dt>
          <dd title="Todo el verde, también las puntas que no alcanzan el lado menor del art. 48 (D55)">
            {i.superficie_espacio_verde_m2 === null ? NO_APLICA : metrosCuadrados(i.superficie_espacio_verde_m2)}
          </dd>
          <dt>Verde computable</dt>
          <dd title="El verde que cuenta para la cesión (D55)">
            {i.superficie_verde_computable_m2 === null ? NO_APLICA : metrosCuadrados(i.superficie_verde_computable_m2)}
          </dd>
          <dt>Cesión alcanzada</dt>
          <dd title="Espacio verde computable sobre la superficie de los lotes (Ley 4146, art. 7; D55)">
            {i.porcentaje_cesion === null ? NO_APLICA : `${porcentaje(i.porcentaje_cesion)} de los lotes`}
          </dd>
          <dt>Espacio libre</dt>
          <dd>{i.superficie_espacio_libre_m2 === null ? NO_APLICA : metrosCuadrados(i.superficie_espacio_libre_m2)}</dd>
          <dt>Áreas reservadas</dt>
          <dd title="No son lotes ni verde, no cuentan para la cesión y se descuentan de la superficie disponible (D59, D61)">
            {i.superficie_reservada_m2 === 0
              ? "ninguna"
              : `${v.capas.areas_reservadas.features.map((f) => f.properties.designacion).join(", ")} · ${metrosCuadrados(
                  i.superficie_reservada_m2,
                )}`}
          </dd>
          <dt>Avenidas</dt>
          <dd title="Longitud de avenidas sobre la de toda la red (Ley 4146, art. 12)">
            {i.porcentaje_avenidas === null ? NO_APLICA : `${porcentaje(i.porcentaje_avenidas)} de la red`}
          </dd>
          <dt>Lotes grandes</dt>
          <dd title="Lotes que pasan la superficie máxima: no son un incumplimiento (D47)">
            {i.cantidad_lotes_grandes === null ? NO_APLICA : numero(i.cantidad_lotes_grandes, 0)}
          </dd>
          <dt>Distancia al verde</dt>
          <dd title="De cada lote al espacio verde más cercano, por la red (D51)">
            {i.distancia_media_verde_m === null || i.distancia_maxima_verde_m === null
              ? NO_APLICA
              : `media ${metros(i.distancia_media_verde_m)} · máx. ${metros(i.distancia_maxima_verde_m)}`}
          </dd>
          <dt>Celdas no conformes</dt>
          <dd>{numero(i.cantidad_fracciones_no_conformes, 0)}</dd>
        </dl>
      </details>
    </TarjetaSeccion>
  );
}

// Las restricciones que verificó el motor, con ✓ o ✗ y su detalle (figura 17; D74).
function Verificaciones({ version: v, titulo = "Verificaciones" }: { version: VersionOut; titulo?: string }) {
  return (
    <TarjetaSeccion titulo={titulo}>
      <ul className="verificaciones">
        {v.verificaciones.map((x) => (
          <li key={x.tipo} data-tipo={x.tipo}>
            <Marca tipo={x.cumple ? "ok" : "error"} />
            <strong>{x.nombre}</strong>
            <p>{x.detalle}</p>
          </li>
        ))}
      </ul>
    </TarjetaSeccion>
  );
}

// La descripción del trazado para el cliente (figura 21; D76). Se copia en el enlace al compartir.
function DescripcionCliente({ alternativa, puedeDescribir, onCambio }: PropsResumen) {
  const [edicion, setEdicion] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<ErrorOut | null>(null);

  async function guardar() {
    if (edicion === null) return;
    setGuardando(true);
    setError(null);
    const resultado = await describirAlternativa(alternativa.id_alternativa, edicion);
    setGuardando(false);
    if (resultado.ok) {
      setEdicion(null);
      onCambio();
    } else {
      setError(resultado.error);
    }
  }

  return (
    <TarjetaSeccion
      titulo="Descripción para el cliente"
      extra={
        puedeDescribir &&
        edicion === null && (
          <button
            type="button"
            className="boton boton--chico"
            onClick={() => setEdicion(alternativa.descripcion ?? "")}
          >
            {alternativa.descripcion ? "Editar" : "Escribir"}
          </button>
        )
      }
    >
      {edicion === null ? (
        <p className={alternativa.descripcion ? "" : "texto-tenue"} style={{ margin: 0 }}>
          {alternativa.descripcion ?? "Sin descripción. El cliente ve los indicadores y el trazado."}
        </p>
      ) : (
        <>
          <div className="campo">
            <label htmlFor="descripcion-cliente">Lo que ve el cliente arriba de los indicadores</label>
            <textarea id="descripcion-cliente" rows={4} value={edicion} onChange={(e) => setEdicion(e.target.value)} />
          </div>
          <p className="texto-tenue">
            Se copia en el enlace al compartir: cambiarla después no cambia lo que ya ve el cliente.
          </p>
          {error && <AvisoError error={error} titulo="No se guardó la descripción" />}
          <div className="acciones">
            <button type="button" className="boton boton--primario" disabled={guardando} onClick={guardar}>
              {guardando ? "Guardando…" : "Guardar"}
            </button>
            <button type="button" className="boton" onClick={() => setEdicion(null)}>
              Cancelar
            </button>
          </div>
        </>
      )}
    </TarjetaSeccion>
  );
}

// --- Versiones (figura 18) -------------------------------------------------------------------------------

type PropsVersiones = {
  alternativa: AlternativaOut;
  puedeGenerar: boolean;
  // Volver a una versión: la API crea la versión n + 1, que la copia (D60).
  onVolver: (idVersion: number) => void;
  volviendo: boolean;
  errorVolver: ErrorOut | null;
};

// Las cinco filas de «Diferencias entre versiones» de la figura 18; las demás, en «Más».
const PRINCIPALES = [
  "cantidad_celdas",
  "cantidad_incumplimientos",
  "porcentaje_aprovechamiento",
  "superficie_media_celda_m2",
  "distancia_media_acceso_m",
];

export function PanelVersiones({ alternativa, puedeGenerar, onVolver, volviendo, errorVolver }: PropsVersiones) {
  const v = alternativa.version;
  const vigente = Math.max(...alternativa.versiones.map((x) => x.numero));
  const numeroDe = new Map(alternativa.versiones.map((x) => [x.id_version, x.numero]));
  const origen = v.id_version_origen === null ? null : (numeroDe.get(v.id_version_origen) ?? null);
  // «Mantener versión N»: la versión ya es la vigente (D56); mantenerla es cerrar esta pregunta (D77).
  const [mantenida, setMantenida] = useState<number | null>(null);

  return (
    <>
      {v.fijacion && <Fijacion alternativa={alternativa} version={v} />}
      {v.tipo === "copia" && origen !== null && (
        <TarjetaSeccion titulo="Copia de una versión anterior">
          <p style={{ margin: 0 }}>
            Copia de la{" "}
            <a href={rutas.versiones(alternativa.id_proyecto, alternativa.codigo, origen)}>versión {origen}</a>, que no
            cambia: las mismas manzanas, lotes, calles, áreas e indicadores (D60).
          </p>
        </TarjetaSeccion>
      )}
      {v.diferencias_con_origen && origen !== null && (
        <Diferencias filas={v.diferencias_con_origen} origen={origen} nueva={v.numero} />
      )}
      <VerificacionesBreves version={v} />

      {puedeGenerar &&
        v.numero === vigente &&
        v.tipo === "recalculada" &&
        origen !== null &&
        mantenida !== v.numero && (
          <div className="acciones acciones--derecha">
            <button type="button" className="boton" disabled={volviendo} onClick={() => onVolver(v.id_version_origen!)}>
              {volviendo ? "Volviendo…" : `Volver a la versión ${origen}`}
            </button>
            <button type="button" className="boton boton--primario" onClick={() => setMantenida(v.numero)}>
              Mantener versión {v.numero}
            </button>
          </div>
        )}
      {puedeGenerar && v.numero === vigente && v.tipo === "recalculada" && origen !== null && (
        <p className="texto-tenue">
          {mantenida === v.numero
            ? `La versión ${v.numero} queda como la vigente.`
            : `La versión ${v.numero} ya es la vigente. Volver crea la versión ${vigente + 1}, copia de la ${origen}, sin borrar la ${v.numero} (D60).`}
        </p>
      )}
      {puedeGenerar && v.numero < vigente && (
        <div className="acciones acciones--derecha">
          <button
            type="button"
            className="boton"
            disabled={volviendo}
            title="Crea una versión nueva que copia esta; ninguna versión cambia (D60)"
            onClick={() => onVolver(v.id_version)}
          >
            {volviendo ? "Volviendo…" : `Volver a la versión ${v.numero}`}
          </button>
        </div>
      )}
      {errorVolver && <AvisoError error={errorVolver} titulo="No se pudo volver a esa versión" />}
      <TarjetaSeccion titulo={`Versiones de la alternativa ${alternativa.codigo}`}>
        <ul className="lista-versiones">
          {alternativa.versiones.map((x) => {
            const desde = x.id_version_origen === null ? null : numeroDe.get(x.id_version_origen);
            return (
              <li key={x.id_version} className={x.numero === v.numero ? "lista-versiones__actual" : ""}>
                <a href={rutas.versiones(alternativa.id_proyecto, alternativa.codigo, x.numero)}>
                  Versión {x.numero}
                  {x.tipo === "recalculada" ? ` · desde v${desde}` : x.tipo === "copia" ? ` · copia de v${desde}` : ""}
                </a>
                <span className="texto-tenue">
                  {fechaHoraLarga(x.fecha_generacion)}
                  {x.numero === vigente && (
                    <>
                      {" "}
                      <span className="insignia insignia--ok">Vigente</span>
                    </>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      </TarjetaSeccion>
    </>
  );
}

// CU09 (figura 18): qué se conservó de la versión de origen y con qué estrategia se recalculó el resto.
function Fijacion({ alternativa, version: v }: { alternativa: AlternativaOut; version: VersionOut }) {
  const f = v.fijacion!;
  // La duración de la generación completa es la de la versión de origen.
  const origen = useConsulta(`version:${f.id_version_origen}`, (c) => consultarVersion(f.id_version_origen, c));
  const duracionOrigen = origen.datos?.version.duracion_ms;
  return (
    <TarjetaSeccion titulo="Fijación de sectores y recálculo" etiqueta="Fijación y recálculo">
      <dl className="filas">
        <dt>Sector fijado</dt>
        <dd>
          {f.manzanas.join(", ")} · {numero(f.cantidad_celdas, 0)} celdas · {hectareas(f.superficie_m2)}
        </dd>
        <dt>Puntos de anclaje en el borde</dt>
        <dd
          title={`Unidos a la red nueva: ${f.cantidad_anclajes_unidos} de ${f.cantidad_anclajes}; empalmes sobre calles fijadas: ${f.cantidad_empalmes}`}
        >
          {numero(f.cantidad_anclajes, 0)} nodos · {numero(f.cantidad_anclajes_unidos, 0)} unidos
        </dd>
        <dt>Empalmes sobre calles fijadas</dt>
        <dd>{numero(f.cantidad_empalmes, 0)}</dd>
        <dt>Estrategia del recálculo</dt>
        <dd>
          {patron(v.estrategia.patron_red)} · {grados(v.estrategia.orientacion_grados)} · semilla {v.estrategia.semilla}
        </dd>
        <dt>Duración</dt>
        <dd>
          {numero(v.duracion_ms / 1000, 1)} s
          {duracionOrigen !== undefined && ` (generación completa: ${numero(duracionOrigen / 1000, 1)} s)`}
        </dd>
      </dl>
      <p className="texto-tenue" style={{ margin: "0.6rem 0 0" }}>
        Desde la{" "}
        <a href={rutas.versiones(alternativa.id_proyecto, alternativa.codigo, f.numero_origen)}>
          versión {f.numero_origen}
        </a>
        , que no cambia ·{" "}
        <a
          href={rutas.comparacion(alternativa.id_proyecto, [
            codigoVersion(alternativa.codigo, f.numero_origen),
            codigoVersion(alternativa.codigo, v.numero),
          ])}
        >
          comparar v{f.numero_origen} con v{v.numero}
        </a>
      </p>
    </TarjetaSeccion>
  );
}

function claseDiferencia(d: DiferenciaIndicadorOut): string {
  if (d.sentido === null || d.diferencia === null || d.diferencia === 0) return "";
  const mejor = (d.sentido === "mayor") === d.diferencia > 0;
  return mejor ? "diferencia--mejor" : "diferencia--peor";
}

function FilaDiferencia({ d }: { d: DiferenciaIndicadorOut }) {
  return (
    <tr>
      <td>{nombreIndicador(d.indicador)}</td>
      <td className="numero">{valorIndicador(d.indicador, d.origen)}</td>
      <td className="numero">{valorIndicador(d.indicador, d.nueva)}</td>
      <td className={`numero ${claseDiferencia(d)}`}>{diferenciaIndicador(d.indicador, d.diferencia)}</td>
    </tr>
  );
}

// La tabla de la figura 18. El color de la diferencia sale del `sentido` que manda la API (D54): solo en
// los indicadores con una dirección clara; las disyuntivas van sin color.
function Diferencias({ filas, origen, nueva }: { filas: DiferenciaIndicadorOut[]; origen: number; nueva: number }) {
  const principales = PRINCIPALES.map((k) => filas.find((d) => d.indicador === k)).filter(
    (d): d is DiferenciaIndicadorOut => !!d,
  );
  const otras = filas.filter((d) => !PRINCIPALES.includes(d.indicador));
  const encabezado = (
    <thead>
      <tr>
        <th>Indicador</th>
        <th className="numero">V{origen}</th>
        <th className="numero">V{nueva}</th>
        <th className="numero">Dif.</th>
      </tr>
    </thead>
  );
  return (
    <TarjetaSeccion titulo="Diferencias entre versiones">
      <table className="tabla tabla--compacta diferencias" aria-label="Diferencias entre versiones">
        {encabezado}
        <tbody>
          {principales.map((d) => (
            <FilaDiferencia key={d.indicador} d={d} />
          ))}
        </tbody>
      </table>
      {otras.length > 0 && (
        <details className="mas-indicadores">
          <summary>Más indicadores</summary>
          <table className="tabla tabla--compacta">
            <tbody>
              {otras.map((d) => (
                <FilaDiferencia key={d.indicador} d={d} />
              ))}
            </tbody>
          </table>
        </details>
      )}
    </TarjetaSeccion>
  );
}

// «Verificaciones de la versión 2» (figura 18): una línea si cumple todo; si no, lo que falla.
function VerificacionesBreves({ version: v }: { version: VersionOut }) {
  const fallan = v.verificaciones.filter((x) => !x.cumple);
  return (
    <TarjetaSeccion titulo={`Verificaciones de la versión ${v.numero}`}>
      {fallan.length === 0 ? (
        <ul className="verificaciones">
          <li>
            <Marca tipo="ok" />
            <strong>Las {v.verificaciones.length} restricciones verificadas</strong>
            <p>Sin incumplimientos</p>
          </li>
        </ul>
      ) : (
        <ul className="verificaciones">
          {fallan.map((x) => (
            <li key={x.tipo}>
              <Marca tipo="error" />
              <strong>{x.nombre}</strong>
              <p>{x.detalle}</p>
            </li>
          ))}
        </ul>
      )}
    </TarjetaSeccion>
  );
}
