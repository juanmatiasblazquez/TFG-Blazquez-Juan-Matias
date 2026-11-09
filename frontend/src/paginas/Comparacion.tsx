import L from "leaflet";
import { useMemo, useState, type ReactNode } from "react";

import {
  compararAlternativas,
  compararVersiones,
  type AlternativaComparadaOut,
  type ComparacionOut,
  type IndicadorComparadoOut,
} from "../api/comparacion";
import { seleccionar } from "../api/enlaces";
import type { ErrorOut } from "../api/errores";
import { consultarProyecto, type ProyectoOut } from "../api/proyectos";
import { consultarVersion } from "../api/versiones";
import { AvisoError } from "../components/AvisoError";
import { CapasAlternativa, RayadoFijado } from "../components/CapasAlternativa";
import { TarjetaCompartir } from "../components/CompartirAlternativas";
import { etiquetaParametro, valorParametro } from "../components/FormularioParametros";
import { BarraPagina, Desplegable, TarjetaSeccion } from "../components/Marco";
import { MapaBase } from "../components/MapaBase";
import { TerrenoYAccesos } from "../components/TerrenoYAccesos";
import {
  criterioEspacioVerde,
  diferenciaIndicador,
  esCampoDeEstrategia,
  etiquetaEstrategia,
  grados,
  nombreIndicador,
  valorEstrategia,
  valorIndicador,
} from "../formato";
import { useConsulta } from "../hooks/useConsulta";
import { codigoVersion, leerCodigo, rutas } from "../hooks/useRuta";
import { useSesion } from "../hooks/useSesion";
import { useGrupoMapas, useSincronizarMapa, type GrupoMapas } from "../hooks/useSincronizarMapas";

type Props = {
  id: number;
  // Los códigos de la dirección, en el orden de la tabla: la primera es la base de la diferencia.
  // «A» es la versión vigente de A, y «A.2», su versión 2 (D57).
  codigos: string[];
};

// Las filas de la figura 20, en su orden; las demás van en «Más indicadores». Es solo el orden de la
// pantalla: qué fila tiene un mejor lo dice la API (`sentido`, `mejores`; D54).
const PRINCIPALES = [
  "cantidad_celdas",
  "porcentaje_aprovechamiento",
  "porcentaje_circulacion",
  "porcentaje_espacio_verde",
  "longitud_red_m",
  "distancia_media_acceso_m",
  "superficie_media_celda_m2",
  "cantidad_incumplimientos",
  "observaciones_bloqueantes_abiertas",
];

// CU13 (figura 20): dos o tres alternativas del proyecto lado a lado, con los mapas sincronizados, la
// tabla de indicadores, compartir con el cliente y lo que las diferencia. Todo lo calcula la API (D54): cuál
// es el mejor valor y qué parámetros difieren. Con una versión en la dirección, se comparan versiones: por
// ejemplo, la v1 y la v2 de un recálculo (D57).
export function Comparacion({ id, codigos }: Props) {
  const puedeCompartir = useSesion().puede("compartir_alternativas");
  const proyecto = useConsulta(`proyecto:${id}`, (c) => consultarProyecto(id, c));
  const p = proyecto.datos;
  const grupo = useGrupoMapas();
  const encuadre = useMemo(() => (p ? L.geoJSON(p.terreno).getBounds() : null), [p]);
  const [errorSeleccion, setErrorSeleccion] = useState<ErrorOut | null>(null);
  const [seleccionando, setSeleccionando] = useState(false);

  const pedidos = codigos.map(leerCodigo);
  const porVersion = pedidos.some((x) => x.numero !== null);
  // Cada código, con su alternativa y la versión pedida (la vigente si no dice cuál).
  const elegidas = p
    ? pedidos.map(({ codigo, numero }) => {
        const a = p.alternativas.find((x) => x.codigo === codigo);
        const v = a && (numero === null ? a.versiones.at(-1) : a.versiones.find((x) => x.numero === numero));
        return a && v ? { alternativa: a, version: v } : null;
      })
    : [];
  const faltantes = p ? codigos.filter((_, k) => !elegidas[k]) : [];
  const ids = elegidas.flatMap((e) => (e ? [porVersion ? e.version.id_version : e.alternativa.id_alternativa] : []));
  // Con una sola elegida todavía no hay nada que comparar: se espera la segunda. Si son
  // demasiadas, lo dice la API (D37).
  const clave =
    p && faltantes.length === 0 && ids.length >= 2
      ? `comparacion:${id}:${porVersion ? "versiones" : "alternativas"}:${ids.join(",")}`
      : null;
  const comparacion = useConsulta(clave, (c) =>
    porVersion ? compararVersiones(id, ids, c) : compararAlternativas(id, ids, c),
  );
  const c = comparacion.datos;

  if (proyecto.error) {
    return (
      <div className="pagina">
        <AvisoError error={proyecto.error} titulo="No se pudo abrir el proyecto" />
        <a href={rutas.proyectos}>Volver a la lista</a>
      </div>
    );
  }
  if (!p) return <p className="pagina texto-tenue">Cargando el proyecto…</p>;

  // CU14, paso 1, desde la comparación: la selección pasa a ser la de ahora con esta alternativa sumada o
  // sacada. Si tiene una observación bloqueante sin responder, la API responde 409 (D37).
  async function alternarSeleccion(codigo: string, marcada: boolean) {
    if (!p) return;
    const actuales = p.alternativas.filter((a) => a.estado === "seleccionada").map((a) => a.codigo);
    const codigosNuevos = marcada ? [...actuales, codigo] : actuales.filter((x) => x !== codigo);
    setSeleccionando(true);
    setErrorSeleccion(null);
    const resultado = await seleccionar(id, codigosNuevos);
    setSeleccionando(false);
    if (resultado.ok) {
      proyecto.recargar();
      comparacion.recargar();
    } else {
      setErrorSeleccion(resultado.error);
    }
  }

  const eleccion = <Eleccion proyecto={p} codigos={codigos} />;
  return (
    <div className="vista">
      <BarraPagina
        migas={[
          { texto: "Proyectos", href: rutas.proyectos },
          { texto: p.nombre, href: rutas.proyecto(id) },
        ]}
        titulo={porVersion ? "Comparación de versiones" : "Comparación de alternativas"}
        acciones={
          <>
            {c && <InsigniaCriterio alternativas={c.alternativas} />}
            {c && (
              <Desplegable etiqueta={porVersion ? "Cambiar versiones" : "Cambiar alternativas"} alineacion="derecha">
                {() => <div className="comparacion__menu">{eleccion}</div>}
              </Desplegable>
            )}
          </>
        }
      />
      <div className="vista__cuerpo vista__cuerpo--hoja comparacion">
        {/* Sin dos elegidas todavía, la elección va a la vista; después, en «Cambiar alternativas». */}
        {!c && eleccion}
        {faltantes.length > 0 && <p className="texto-tenue">El proyecto no tiene «{faltantes.join("», «")}».</p>}
        {comparacion.cargando && <p className="texto-tenue">Comparando…</p>}
        {comparacion.error && <AvisoError error={comparacion.error} titulo="No se pudo comparar" />}
        {errorSeleccion && <AvisoError error={errorSeleccion} titulo="No se puede seleccionar esa alternativa" />}

        {c && (
          <>
            <RayadoFijado />
            <div
              className="comparacion__mapas"
              style={{ gridTemplateColumns: `repeat(${c.alternativas.length}, minmax(0, 1fr))` }}
            >
              {c.alternativas.map((a) => (
                <MapaComparado
                  key={a.id_version}
                  proyecto={p}
                  alternativa={a}
                  porVersion={porVersion}
                  grupo={grupo}
                  encuadre={encuadre}
                  casilla={
                    porVersion ? null : (
                      <CasillaSeleccion
                        alternativa={a}
                        puede={puedeCompartir}
                        ocupado={seleccionando}
                        onCambiar={(codigo, marcada) => void alternarSeleccion(codigo, marcada)}
                      />
                    )
                  }
                />
              ))}
            </div>
            <div className={`comparacion__tablas ${!porVersion && puedeCompartir ? "" : "comparacion__tablas--una"}`}>
              <TarjetaSeccion
                titulo="Indicadores comparados · el valor más favorable se resalta"
                etiqueta="Indicadores comparados"
              >
                <TablaIndicadores comparacion={c} porVersion={porVersion} />
              </TarjetaSeccion>
              {/* CU13, 5.a: de la comparación a compartir con el cliente (CU14). */}
              {!porVersion && puedeCompartir && <TarjetaCompartir proyecto={p} onCambio={() => proyecto.recargar()} />}
            </div>
            <TarjetaSeccion titulo="Qué las diferencia">
              <p className="texto-tenue">La estrategia y los parámetros que no son iguales en todas.</p>
              <TablaDiferencias comparacion={c} porVersion={porVersion} />
            </TarjetaSeccion>
          </>
        )}
      </div>
    </div>
  );
}

// «A», o «A · v2» cuando se comparan versiones.
const etiqueta = (a: AlternativaComparadaOut, porVersion: boolean) =>
  porVersion ? `${a.codigo} · v${a.numero}` : a.codigo;

// La elección de las alternativas (y de las versiones de las recalculadas): agrega al final o saca. El
// orden de la elección es el de la tabla.
function Eleccion({ proyecto: p, codigos }: { proyecto: ProyectoOut; codigos: string[] }) {
  const alternar = (codigo: string) =>
    rutas.comparacion(
      p.id_proyecto,
      codigos.includes(codigo) ? codigos.filter((x) => x !== codigo) : [...codigos, codigo],
    );
  const chip = (codigo: string, texto: string, clave: number) => {
    const elegida = codigos.includes(codigo);
    return (
      <a
        key={clave}
        href={alternar(codigo)}
        className={`chip ${elegida ? "chip--activo" : ""}`}
        aria-pressed={elegida}
        title={elegida ? "Sacar de la comparación" : "Sumar a la comparación"}
      >
        {texto}
      </a>
    );
  };
  return (
    <>
      <div className="comparacion__eleccion">
        <span className="texto-tenue">Alternativas:</span>
        <nav className="chips" aria-label="Alternativas para comparar">
          {p.alternativas.map((a) => chip(a.codigo, a.codigo, a.id_alternativa))}
        </nav>
        <span className="texto-tenue">Elegí dos o tres. La primera es la base de las diferencias.</span>
      </div>
      {/* Las versiones de las alternativas recalculadas (CU09): «A.1» contra «A.2» (D57). */}
      {p.alternativas.some((a) => a.versiones.length > 1) && (
        <div className="comparacion__eleccion">
          <span className="texto-tenue">Versiones:</span>
          <nav className="chips" aria-label="Versiones para comparar">
            {p.alternativas
              .filter((a) => a.versiones.length > 1)
              .flatMap((a) =>
                a.versiones.map((v) =>
                  chip(codigoVersion(a.codigo, v.numero), `${a.codigo} · v${v.numero}`, v.id_version),
                ),
              )}
          </nav>
        </div>
      )}
    </>
  );
}

// «Criterio del verde: Más cercanía» (D83): en el lugar del criterio prioritario de la figura 20, que el
// motor no usa. Si difiere, lo dice: la tabla «Qué las diferencia» muestra cuál tiene cada una.
function InsigniaCriterio({ alternativas }: { alternativas: AlternativaComparadaOut[] }) {
  const criterios = [...new Set(alternativas.map((a) => a.criterio_espacio_verde))];
  if (criterios.length === 1 && criterios[0] === null) return null;
  const texto =
    criterios.length === 1 && criterios[0] !== null ? criterioEspacioVerde(criterios[0]) : "distinto en cada una";
  return <span className="insignia insignia--grande">Criterio del verde: {texto}</span>;
}

type PropsCasilla = {
  alternativa: AlternativaComparadaOut;
  puede: boolean;
  ocupado: boolean;
  onCambiar: (codigo: string, marcada: boolean) => void;
};

// «Seleccionada» o, si tiene una observación bloqueante sin responder, «Obs. bloqueante» deshabilitada: la
// cantidad la da la API (`bloqueantes_abiertas`, las que impiden compartir; D69, D84).
function CasillaSeleccion({ alternativa: a, puede, ocupado, onCambiar }: PropsCasilla) {
  const seleccionada = a.estado === "seleccionada";
  if (a.bloqueantes_abiertas > 0) {
    return (
      <label
        className="casilla casilla--deshabilitada"
        title="Tiene observaciones bloqueantes sin responder: no se puede compartir (CU14, 2.a)."
      >
        <input type="checkbox" checked={false} disabled /> Obs. bloqueante
      </label>
    );
  }
  if (!puede) return seleccionada ? <span className="insignia insignia--info">Seleccionada</span> : null;
  return (
    <label className="casilla" title="Seleccionarla para compartirla con el cliente (CU14)">
      <input
        type="checkbox"
        checked={seleccionada}
        disabled={ocupado}
        onChange={(e) => onCambiar(a.codigo, e.target.checked)}
      />{" "}
      Seleccionada
    </label>
  );
}

type PropsMapa = {
  proyecto: ProyectoOut;
  alternativa: AlternativaComparadaOut;
  porVersion: boolean;
  grupo: GrupoMapas;
  encuadre: L.LatLngBounds | null;
  casilla: ReactNode;
};

// Una alternativa (la versión comparada) con sus capas, en un mapa chico del grupo sincronizado.
function MapaComparado({ proyecto, alternativa: a, porVersion, grupo, encuadre, casilla }: PropsMapa) {
  const leida = useConsulta(`version:${a.id_version}`, (c) => consultarVersion(a.id_version, c));
  return (
    <article className="comparacion__tarjeta" aria-label={`Alternativa ${a.codigo} · v${a.numero}`}>
      <header className="comparacion__titulo">
        <h3>
          <a href={rutas.version(proyecto.id_proyecto, a.codigo, a.numero)}>Alternativa {a.codigo}</a> · v{a.numero}
        </h3>
        <span
          className={`insignia ${a.cumple_restricciones ? "insignia--ok" : "insignia--error"}`}
          title={`Orientación ${grados(a.estrategia.orientacion_grados)} · semilla ${a.estrategia.semilla} · parámetros v${a.version_parametros} · motor ${a.version_motor}`}
        >
          {a.cumple_restricciones ? "Conforme" : "No conforme"}
        </span>
        <span className="comparacion__casilla">{porVersion ? null : casilla}</span>
      </header>
      <div className="comparacion__mapa">
        <MapaBase encuadre={encuadre} norte={false} zoom={false} escala={false} margen={12}>
          <Sincronizar grupo={grupo} />
          {leida.datos && <CapasAlternativa version={leida.datos.version} etiquetas={false} />}
          <TerrenoYAccesos proyecto={proyecto} />
        </MapaBase>
      </div>
      {leida.error && <AvisoError error={leida.error} titulo="No se pudo leer la alternativa" />}
    </article>
  );
}

function Sincronizar({ grupo }: { grupo: GrupoMapas }) {
  useSincronizarMapa(grupo);
  return null;
}

type PropsTabla = { comparacion: ComparacionOut; porVersion: boolean };

// Los indicadores, con la diferencia contra la primera en texto chico. Se resalta el mejor solo donde la
// API da un sentido: en las disyuntivas (la circulación, el verde, la red) no hay un mejor (D54, C1).
function TablaIndicadores({ comparacion: c, porVersion }: PropsTabla) {
  const [todos, setTodos] = useState(false);
  const principales = PRINCIPALES.flatMap((k) => c.indicadores.filter((f) => f.indicador === k));
  const resto = c.indicadores.filter((f) => !PRINCIPALES.includes(f.indicador));
  const base = etiqueta(c.alternativas[0], porVersion);
  const fila = (f: IndicadorComparadoOut) => (
    <tr key={f.indicador}>
      <td
        title={f.sentido ? (f.sentido === "mayor" ? "Más es mejor" : "Menos es mejor") : "Una disyuntiva: sin un mejor"}
      >
        {nombreIndicador(f.indicador)}
      </td>
      {f.valores.map((valor, k) => (
        <td
          key={k}
          className={`numero ${f.mejores.includes(k) ? "comparacion__mejor" : ""}`}
          title={f.mejores.includes(k) ? "El valor más favorable" : undefined}
        >
          {valorIndicador(f.indicador, valor)}
          {k > 0 && f.diferencias[k] !== null && f.diferencias[k] !== 0 && (
            <small className="comparacion__delta" title={`Contra ${base}`}>
              {diferenciaIndicador(f.indicador, f.diferencias[k])}
            </small>
          )}
        </td>
      ))}
    </tr>
  );
  return (
    <>
      <table className="tabla comparacion__tabla">
        <thead>
          <tr>
            <th>Indicador</th>
            {c.alternativas.map((a) => (
              <th key={a.id_version} className="numero">
                Alternativa {a.codigo} · v{a.numero}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {principales.map(fila)}
          {todos && resto.map(fila)}
        </tbody>
      </table>
      <p className="comparacion__nota texto-tenue">
        Se resalta solo donde la dirección es clara; en la circulación, el verde y la red, la diferencia, sin juzgar. La
        diferencia chica es contra {porVersion ? base : `la alternativa ${base}`}.{" "}
        {resto.length > 0 && (
          <button type="button" className="boton boton--enlace" onClick={() => setTodos((x) => !x)}>
            {todos ? "Menos indicadores" : `Más indicadores (${resto.length})`}
          </button>
        )}
      </p>
    </>
  );
}

// Lo que difiere: la estrategia, la versión del motor y los parámetros, por valor (D54).
function TablaDiferencias({ comparacion: c, porVersion }: PropsTabla) {
  if (c.diferencias.length === 0) {
    return <p>No difieren en la estrategia ni en los parámetros.</p>;
  }
  return (
    <table className="tabla comparacion__tabla comparacion__tabla--diferencias">
      <thead>
        <tr>
          <th>Qué cambia</th>
          {c.alternativas.map((a) => (
            <th key={a.id_version}>{etiqueta(a, porVersion)}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {c.diferencias.map((d) => {
          const deEstrategia = esCampoDeEstrategia(d.campo);
          return (
            <tr key={d.campo}>
              <td>{deEstrategia ? etiquetaEstrategia(d.campo) : etiquetaParametro(d.campo)}</td>
              {d.valores.map((valor, k) => (
                <td key={k}>{deEstrategia ? valorEstrategia(d.campo, valor) : valorParametro(d.campo, valor)}</td>
              ))}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
