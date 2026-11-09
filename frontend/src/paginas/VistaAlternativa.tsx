import type { Geometry } from "geojson";
import L from "leaflet";
import { useMemo, useState } from "react";
import { Pane } from "react-leaflet";

import { consultarAlternativa, type AlternativaOut } from "../api/alternativas";
import type { ErrorOut } from "../api/errores";
import type { ObservacionOut } from "../api/observaciones";
import type { ProyectoOut } from "../api/proyectos";
import { consultarVersion, volverAVersion } from "../api/versiones";
import { AvisoError } from "../components/AvisoError";
import {
  CAPAS_INICIALES,
  CapasAlternativa,
  capasDe,
  PanelCapas,
  RayadoFijado,
  type CapasVisibles,
} from "../components/CapasAlternativa";
import { CapaFijar, PanelFijar, pedirRecalculo, useFijarSectores } from "../components/FijarSectores";
import { BotonGenerar } from "../components/GenerarAlternativa";
import { GeometriaError } from "../components/GeometriaError";
import { BarraPagina, Desplegable } from "../components/Marco";
import { MapaBase } from "../components/MapaBase";
import {
  CapaObservaciones,
  PanelObservaciones,
  pedirRespuestaConRecalculo,
  useMedicionSector,
  useObservaciones,
} from "../components/Observaciones";
import { PanelResumen, PanelVersiones } from "../components/PanelAlternativa";
import { SelectorVersiones } from "../components/SelectorVersiones";
import { TerrenoYAccesos } from "../components/TerrenoYAccesos";
import { estado, metrosCuadrados } from "../formato";
import { useConsulta } from "../hooks/useConsulta";
import { navegar, rutas, type PestanaAlternativa } from "../hooks/useRuta";
import { useSesion } from "../hooks/useSesion";

type Props = {
  proyecto: ProyectoOut;
  recargarProyecto: () => void;
  codigo: string;
  // El número de versión que pide la dirección; sin él, la vigente (D57).
  numeroVersion: number | null;
  pestana: PestanaAlternativa;
};

// Una alternativa (figuras 17, 18 y 19; D73): el mapa a la izquierda y el panel a la derecha, con las
// pestañas «Resumen», «Versiones» y «Observaciones». En la barra, las versiones, si cumple, y las acciones:
// fijar sectores y recalcular (CU09), comparar (CU13) y generar otra (CU06). Las observaciones se registran
// y se responden acá (CU11, CU12; D69).
//
// Lo que el rol no puede hacer no se ofrece (p. 54): generar, fijar, volver a una versión, responder y
// describir para el cliente son del director técnico y del proyectista; registrar observaciones, del
// director técnico. Quien decide es la API, que responde 403 (D37, D67).
export function VistaAlternativa({ proyecto: p, recargarProyecto, codigo, numeroVersion, pestana }: Props) {
  const { puede } = useSesion();
  const puedeGenerar = puede("generar_alternativas");
  const id = p.id_proyecto;
  const resumen = p.alternativas.find((a) => a.codigo === codigo) ?? null;
  const alternativa = useConsulta(resumen && `alternativa:${resumen.id_alternativa}`, (c) =>
    consultarAlternativa(resumen!.id_alternativa, c),
  );
  // La vigente viene con la alternativa; otra versión se pide aparte (D57).
  const pedida = numeroVersion === null ? null : (resumen?.versiones.find((v) => v.numero === numeroVersion) ?? null);
  const otra = pedida && pedida.id_version !== resumen?.versiones.at(-1)?.id_version ? pedida : null;
  const versionLeida = useConsulta(otra && `version:${otra.id_version}`, (c) => consultarVersion(otra!.id_version, c));
  // La que acaba de salir de un recálculo o de una copia se muestra con la respuesta del 201 (la misma
  // del GET) mientras se recarga el proyecto.
  const [reciente, setReciente] = useState<AlternativaOut | null>(null);
  const desdeReciente =
    reciente &&
    resumen &&
    reciente.id_alternativa === resumen.id_alternativa &&
    reciente.version.numero === numeroVersion
      ? reciente
      : null;
  const leida = otra ? versionLeida : alternativa;
  const mostrada = desdeReciente ?? leida.datos;
  // Las observaciones de la alternativa: su número va en la pestaña aunque no esté abierta.
  const obs = useObservaciones(resumen ? resumen.id_alternativa : null);
  const enObservaciones = pestana === "observaciones";
  // B13: el sector que se dibuja, medido por la API sobre la versión que se observa (D79).
  const sectorMedido = useMedicionSector(
    enObservaciones && obs.formulario ? (mostrada?.version.id_version ?? null) : null,
    obs.sector,
  );
  // Responder una observación con un recálculo (CU12, 3.a): el modo «Fijar sectores» con su respuesta.
  const [respondiendo, setRespondiendo] = useState<{ observacion: ObservacionOut; descripcion: string } | null>(null);

  const [capas, setCapas] = useState<CapasVisibles>(CAPAS_INICIALES);
  // CU09: la versión cuyas manzanas se están fijando, si se está en ese modo.
  const [fijando, setFijando] = useState<number | null>(null);
  const fijar = useFijarSectores(mostrada?.version.id_version ?? 0);
  const enModoFijar = mostrada !== null && fijando === mostrada.version.id_version;
  const [recalculando, setRecalculando] = useState(false);
  const [errorRecalculo, setErrorRecalculo] = useState<ErrorOut | null>(null);
  const [volviendo, setVolviendo] = useState(false);
  const [errorVolver, setErrorVolver] = useState<ErrorOut | null>(null);
  // La geometría de un error (de generar o de recalcular), con un intento por pedido para redibujarla.
  const [errorGeometria, setErrorGeometria] = useState<Geometry | null>(null);
  const [intento, setIntento] = useState(0);

  const encuadre = useMemo(() => L.geoJSON(p.terreno).getBounds(), [p]);

  function recargar() {
    recargarProyecto();
    alternativa.recargar();
  }

  async function confirmarRecalculo(orientacion: number | string | null, semilla: number | string | null) {
    if (!mostrada) return;
    setRecalculando(true);
    setErrorRecalculo(null);
    setIntento((n) => n + 1);
    if (respondiendo) {
      // La respuesta y la versión nueva se guardan juntas, vinculadas (D69).
      const respuesta = await pedirRespuestaConRecalculo(
        fijar,
        respondiendo.observacion.id_observacion,
        respondiendo.descripcion,
        mostrada.version.estrategia.patron_red,
        orientacion,
        semilla,
      );
      setRecalculando(false);
      if (respuesta.ok) {
        salirDeFijar();
        recargar();
        obs.lista.recargar();
      } else {
        setErrorRecalculo(respuesta.error);
        setErrorGeometria(respuesta.error.geometria ?? null);
      }
      return;
    }
    const resultado = await pedirRecalculo(fijar, mostrada.version.estrategia.patron_red, orientacion, semilla);
    setRecalculando(false);
    if (resultado.ok) {
      setReciente(resultado.datos);
      setFijando(null);
      fijar.soltarTodo();
      recargar();
      navegar(rutas.versiones(id, resultado.datos.codigo, resultado.datos.version.numero));
    } else {
      setErrorRecalculo(resultado.error);
      setErrorGeometria(resultado.error.geometria ?? null);
    }
  }

  // Volver a una versión: la API crea la versión n + 1, que la copia (D60).
  async function volver(idVersion: number) {
    setVolviendo(true);
    setErrorVolver(null);
    const resultado = await volverAVersion(idVersion);
    setVolviendo(false);
    if (resultado.ok) {
      setReciente(resultado.datos);
      recargar();
      navegar(rutas.versiones(id, resultado.datos.codigo, resultado.datos.version.numero));
    } else {
      setErrorVolver(resultado.error);
    }
  }

  function salirDeFijar() {
    setFijando(null);
    setErrorRecalculo(null);
    setErrorGeometria(null);
    setRespondiendo(null);
    fijar.soltarTodo();
  }

  function responderConRecalculo(observacion: ObservacionOut, descripcion: string) {
    if (!mostrada) return;
    obs.setFormulario(null);
    obs.setSector(null);
    obs.elegir(observacion.id_observacion);
    setRespondiendo({ observacion, descripcion });
    setErrorRecalculo(null);
    setFijando(mostrada.version.id_version);
  }

  const migas = [
    { texto: "Proyectos", href: rutas.proyectos },
    { texto: p.nombre, href: rutas.proyecto(id) },
  ];

  if (!resumen) {
    return (
      <div className="vista">
        <BarraPagina migas={migas} titulo={`Alternativa ${codigo}`} />
        <div className="vista__cuerpo vista__cuerpo--hoja">
          <p className="texto-tenue">El proyecto no tiene la alternativa «{codigo}».</p>
        </div>
      </div>
    );
  }

  const v = mostrada?.version;
  const vigente = resumen.versiones.at(-1)!;
  const observaciones = obs.lista.datos ?? [];
  const bloqueantes = resumen.bloqueantes_abiertas;
  const insigniaBloqueantes =
    bloqueantes > 0 ? (
      <span className="insignia insignia--error insignia--grande">
        {bloqueantes === 1 ? "1 bloqueante abierta" : `${bloqueantes} bloqueantes abiertas`}
      </span>
    ) : null;
  const comparar =
    p.alternativas.length >= 2 ? (
      <a className="boton" href={rutas.comparacion(id, [])}>
        Comparar
      </a>
    ) : (
      <button type="button" className="boton" disabled title="Hacen falta al menos dos alternativas">
        Comparar
      </button>
    );

  const barra = enObservaciones ? (
    <BarraPagina
      migas={[
        ...migas,
        { texto: `Alternativa ${codigo} · versión ${vigente.numero}`, href: rutas.alternativa(id, codigo) },
      ]}
      titulo="Observaciones"
      acciones={
        <>
          {insigniaBloqueantes}
          {comparar}
          <a className="boton" href={rutas.alternativa(id, codigo)}>
            Volver a la alternativa
          </a>
        </>
      }
    />
  ) : (
    <BarraPagina
      migas={migas}
      titulo={
        <Desplegable
          claseBoton="titulo-desplegable"
          titulo="Otra alternativa del proyecto"
          etiqueta={`Alternativa ${codigo}`}
        >
          {(cerrar) =>
            p.alternativas.map((a) => (
              <a
                key={a.id_alternativa}
                className={`desplegable__item ${a.codigo === codigo ? "desplegable__item--actual" : ""}`}
                href={rutas.alternativa(id, a.codigo)}
                onClick={cerrar}
              >
                Alternativa {a.codigo}
                <span className={`insignia ${a.cumple_restricciones ? "insignia--ok" : "insignia--error"}`}>
                  {a.cumple_restricciones ? "Conforme" : "No conforme"}
                </span>
              </a>
            ))
          }
        </Desplegable>
      }
      centro={
        mostrada && v ? (
          <>
            <SelectorVersiones
              idProyecto={id}
              codigo={codigo}
              versiones={mostrada.versiones}
              actual={v.numero}
              pestana={pestana}
            />
            {v.cumple_restricciones ? (
              <span className="insignia insignia--ok insignia--grande">Conforme</span>
            ) : (
              <span className="insignia insignia--error insignia--grande">
                {v.indicadores.cantidad_incumplimientos === 1
                  ? "1 incumplimiento"
                  : `${v.indicadores.cantidad_incumplimientos} incumplimientos`}
              </span>
            )}
            {v.responde_a.length > 0 && (
              <span className="insignia insignia--info insignia--grande">Responde a {v.responde_a.join(", ")}</span>
            )}
            {resumen.estado !== "generada" && (
              <span
                className={`insignia insignia--grande ${resumen.estado === "observada" ? "insignia--aviso" : "insignia--info"}`}
              >
                {estado(resumen.estado)}
              </span>
            )}
          </>
        ) : null
      }
      acciones={
        <>
          {puedeGenerar && mostrada && (
            <button
              type="button"
              className="boton"
              title="Conservar manzanas de esta versión y recalcular el resto (CU09)"
              disabled={enModoFijar}
              onClick={() => {
                setErrorRecalculo(null);
                setFijando(mostrada.version.id_version);
              }}
            >
              Fijar sectores
            </button>
          )}
          {comparar}
          {puedeGenerar && (
            <BotonGenerar
              proyecto={p}
              onGenerada={recargarProyecto}
              onGeometriaError={(g) => {
                setErrorGeometria(g);
                setIntento((n) => n + 1);
              }}
            />
          )}
        </>
      }
    />
  );

  const pestanas = (
    <nav className="pestanas-panel" aria-label="Vista de la alternativa">
      {(
        [
          [
            "resumen",
            "Resumen",
            numeroVersion === null ? rutas.alternativa(id, codigo) : rutas.version(id, codigo, numeroVersion),
          ],
          ["versiones", `Versiones (${resumen.versiones.length})`, rutas.versiones(id, codigo, numeroVersion)],
          ["observaciones", `Observaciones (${observaciones.length})`, rutas.observaciones(id, codigo)],
        ] as const
      ).map(([clave, texto, href]) => (
        <a
          key={clave}
          href={href}
          className={`pestanas-panel__item ${pestana === clave ? "pestanas-panel__item--actual" : ""}`}
          aria-current={pestana === clave ? "page" : undefined}
        >
          {texto}
        </a>
      ))}
    </nav>
  );

  return (
    <div className="vista">
      {barra}
      <div className="vista__cuerpo">
        <div className="espacio">
          <aside className="panel">
            {enModoFijar && mostrada ? (
              <PanelFijar
                key={mostrada.version.id_version}
                fijar={fijar}
                alternativa={mostrada}
                versionParametros={p.parametros?.version ?? null}
                recalculando={recalculando}
                error={errorRecalculo}
                onRecalcular={confirmarRecalculo}
                onCancelar={salirDeFijar}
                respuesta={
                  respondiendo && {
                    designacion: respondiendo.observacion.designacion,
                    descripcion: respondiendo.descripcion,
                    onDescripcion: (texto) => setRespondiendo({ ...respondiendo, descripcion: texto }),
                  }
                }
              />
            ) : (
              <>
                {pestanas}
                {numeroVersion !== null && !pedida && !desdeReciente && (
                  <p className="texto-tenue">
                    La alternativa {codigo} no tiene la versión {numeroVersion}.
                  </p>
                )}
                {leida.cargando && !desdeReciente && <p className="texto-tenue">Cargando la alternativa…</p>}
                {leida.error && <AvisoError error={leida.error} titulo="No se pudo leer la alternativa" />}
                {mostrada && pestana === "resumen" && (
                  <PanelResumen
                    alternativa={mostrada}
                    puedeDescribir={puede("compartir_alternativas")}
                    onCambio={recargar}
                  />
                )}
                {mostrada && pestana === "versiones" && (
                  <PanelVersiones
                    alternativa={mostrada}
                    puedeGenerar={puedeGenerar}
                    onVolver={(idVersion) => void volver(idVersion)}
                    volviendo={volviendo}
                    errorVolver={errorVolver}
                  />
                )}
                {mostrada && enObservaciones && (
                  <PanelObservaciones
                    obs={obs}
                    idProyecto={id}
                    codigo={codigo}
                    idVersionVigente={mostrada.version.id_version}
                    numeroVigente={mostrada.version.numero}
                    puedeRegistrar={puede("registrar_observaciones")}
                    puedeResponder={puede("responder_observaciones")}
                    onResponderConRecalculo={responderConRecalculo}
                    onCambio={recargar}
                  />
                )}
              </>
            )}
          </aside>

          <div className="espacio__mapa">
            <RayadoFijado />
            <MapaBase encuadre={encuadre} claveEncuadre={pestana}>
              {v && <CapasAlternativa version={v} visibles={capas} />}
              {/* Encima de las capas de la versión, que pueden llegar después y tienen los lotes opacos: el
                  borde del terreno, y lo que se elige, se observa o falló. */}
              <Pane name="contorno" style={{ zIndex: 410 }}>
                <TerrenoYAccesos proyecto={p} conAreas={!v} />
              </Pane>
              <Pane name="encima" style={{ zIndex: 420 }}>
                {enModoFijar && v && <CapaFijar version={v} fijar={fijar} />}
                {(enObservaciones || respondiendo) && (
                  <CapaObservaciones obs={obs} soloLaElegida={enModoFijar} afuera={sectorMedido?.afuera ?? null} />
                )}
                <GeometriaError geometria={errorGeometria} clave={intento} />
              </Pane>
            </MapaBase>
            {/* Mientras se dibuja el sector de una observación, el aviso va donde va el panel de capas (figura 19). */}
            {enObservaciones && obs.formulario && !enModoFijar ? (
              <div className="sobre-mapa aviso-mapa aviso-mapa--naranja" role="status">
                <strong>Dibujando el sector de la observación</strong>
                {!obs.sector && <span>Con la barra: clic para agregar vértices, clic en el primero para cerrar.</span>}
                {obs.sector && sectorMedido && (
                  <span className={sectorMedido.problema ? "texto-error" : undefined}>
                    {sectorMedido.superficie_m2 !== null && `Sector de ${metrosCuadrados(sectorMedido.superficie_m2)}`}
                    {sectorMedido.problema
                      ? `${sectorMedido.superficie_m2 !== null ? ". " : ""}${sectorMedido.problema} Dibujalo de nuevo dentro del terreno.`
                      : ", dentro del terreno."}
                  </span>
                )}
                {obs.sector && <span>Para cambiarlo, borralo y dibujalo de nuevo.</span>}
              </div>
            ) : (
              v && <PanelCapas entradas={capasDe(v)} visibles={capas} onCambio={setCapas} />
            )}
            {recalculando && (
              <div className="velo" role="status">
                <span className="velo__giro" aria-hidden="true" />
                Recalculando el resto del terreno…
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
