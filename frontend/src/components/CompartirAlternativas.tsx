import { useState } from "react";

import {
  compartir,
  direccionDelEnlace,
  listarEnlaces,
  revocarEnlace,
  seleccionar,
  type EnlaceOut,
} from "../api/enlaces";
import type { ErrorOut } from "../api/errores";
import type { ProyectoOut } from "../api/proyectos";
import { enumerar, estado, estadoEnlace, fecha, fechaHora } from "../formato";
import { useConsulta } from "../hooks/useConsulta";
import { rutas } from "../hooks/useRuta";
import { AvisoError } from "./AvisoError";
import { TarjetaSeccion } from "./Marco";

// Seleccionar alternativas, compartirlas con el cliente y revocar el enlace (CU14; p. 45; D70, D71).
//
// - Marcar una alternativa la selecciona en la API (p. 45, paso 2). Si tiene una observación bloqueante
//   sin responder, la API responde 409 y el aviso dice cuál (CU14, 2.a): el portal no lo decide (D37).
// - El enlace se genera con la fecha de vencimiento (obligatoria, 30 días como máximo, lo dice la API) y
//   con las versiones vigentes de las seleccionadas. El token se muestra esta única vez.
// - La lista de enlaces dice su estado (vigente, vencido o revocado) y permite revocarlos.

type Props = { proyecto: ProyectoOut; onCambio: () => void };

export function CompartirAlternativas({ proyecto, onCambio }: Props) {
  const id = proyecto.id_proyecto;
  const enlaces = useConsulta(`enlaces:${id}`, (c) => listarEnlaces(id, c));
  const [vencimiento, setVencimiento] = useState("");
  const [error, setError] = useState<ErrorOut | null>(null);
  const [errorEnlace, setErrorEnlace] = useState<ErrorOut | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [nuevo, setNuevo] = useState<{ direccion: string; enlace: EnlaceOut } | null>(null);
  const [copiado, setCopiado] = useState(false);
  const [revocando, setRevocando] = useState<number | null>(null);

  const seleccionadas = proyecto.alternativas.filter((a) => a.estado === "seleccionada").map((a) => a.codigo);

  async function alternar(codigo: string, marcada: boolean) {
    const codigos = marcada ? [...seleccionadas, codigo] : seleccionadas.filter((c) => c !== codigo);
    setOcupado(true);
    setError(null);
    const resultado = await seleccionar(id, codigos);
    setOcupado(false);
    if (resultado.ok) onCambio();
    else setError(resultado.error);
  }

  async function generar() {
    setOcupado(true);
    setErrorEnlace(null);
    setNuevo(null);
    setCopiado(false);
    const resultado = await compartir(id, vencimiento || null);
    setOcupado(false);
    if (resultado.ok) {
      setNuevo({ direccion: direccionDelEnlace(resultado.datos.token), enlace: resultado.datos.enlace });
      enlaces.recargar();
    } else {
      setErrorEnlace(resultado.error);
    }
  }

  async function revocar(idEnlace: number) {
    setOcupado(true);
    setErrorEnlace(null);
    const resultado = await revocarEnlace(idEnlace);
    setOcupado(false);
    setRevocando(null);
    if (resultado.ok) enlaces.recargar();
    else setErrorEnlace(resultado.error);
  }

  return (
    <>
      <section className="panel__seccion compartir" aria-label="Alternativas seleccionadas">
        <h3>Alternativas para el cliente</h3>
        <p className="texto-tenue">
          Marcá las que se van a presentar a {proyecto.cliente.razon_social}. Una alternativa con observaciones
          bloqueantes sin responder no se puede compartir.
        </p>
        {proyecto.alternativas.length === 0 && <p className="texto-tenue">Todavía no hay alternativas.</p>}
        <ul className="lista-seleccion">
          {proyecto.alternativas.map((a) => (
            <li key={a.id_alternativa}>
              <label>
                <input
                  type="checkbox"
                  checked={a.estado === "seleccionada"}
                  disabled={ocupado}
                  onChange={(e) => void alternar(a.codigo, e.target.checked)}
                />{" "}
                <strong>Alternativa {a.codigo}</strong> · v{a.versiones.at(-1)?.numero} vigente
              </label>{" "}
              <span
                className={`insignia ${a.estado === "observada" ? "insignia--aviso" : a.estado === "seleccionada" ? "insignia--ok" : ""}`}
              >
                {estado(a.estado)}
              </span>
              {a.bloqueantes_abiertas > 0 && (
                <a className="insignia insignia--error" href={rutas.observaciones(id, a.codigo)}>
                  {a.bloqueantes_abiertas === 1
                    ? "1 bloqueante sin responder"
                    : `${a.bloqueantes_abiertas} bloqueantes sin responder`}
                </a>
              )}
            </li>
          ))}
        </ul>
        {error && <AvisoError error={error} titulo="No se puede seleccionar esa alternativa" />}

        <h4>Compartir</h4>
        <div className="fila-campos fila-campos--dos">
          <div
            className={`campo ${errorEnlace?.problemas.some((p) => p.campo === "fecha_vencimiento") ? "campo--error" : ""}`}
          >
            <label htmlFor="vencimiento">Vencimiento del enlace</label>
            <input id="vencimiento" type="date" value={vencimiento} onChange={(e) => setVencimiento(e.target.value)} />
          </div>
        </div>
        <p className="texto-tenue">
          Obligatorio, de 30 días como máximo: el enlace vale hasta el final de ese día. Comparte las versiones vigentes
          de las seleccionadas ({seleccionadas.length > 0 ? seleccionadas.join(", ") : "ninguna"}); lo que se genere
          después no cambia lo que ve el cliente.
        </p>
        <button type="button" className="boton boton--primario" disabled={ocupado} onClick={() => void generar()}>
          Generar enlace
        </button>
        {nuevo && (
          <div className="aviso aviso--temporal enlace-nuevo" role="status">
            <p className="aviso__titulo">Enlace para el cliente</p>
            <p className="temporal">
              <code className="enlace-nuevo__direccion">{nuevo.direccion}</code>
              <button
                type="button"
                className="boton"
                onClick={() => {
                  void navigator.clipboard?.writeText(nuevo.direccion);
                  setCopiado(true);
                }}
              >
                {copiado ? "Copiado" : "Copiar"}
              </button>
            </p>
            <p>
              Vale hasta el {fecha(nuevo.enlace.fecha_vencimiento)} y comparte{" "}
              {nuevo.enlace.versiones.map((v) => `${v.codigo_alternativa} · v${v.numero_version}`).join(", ")}.
            </p>
            <p>Se muestra esta única vez: en la base queda solo su hash. Si se pierde, revocalo y generá otro.</p>
            <button type="button" className="boton" onClick={() => setNuevo(null)}>
              Listo, ya lo copié
            </button>
          </div>
        )}
        {errorEnlace && <AvisoError error={errorEnlace} titulo="No se pudo generar el enlace" />}
      </section>

      <section className="panel__seccion" aria-label="Enlaces del proyecto">
        <h3>Enlaces del proyecto</h3>
        {enlaces.error && <AvisoError error={enlaces.error} titulo="No se pudieron leer los enlaces" />}
        {enlaces.datos && enlaces.datos.length === 0 && <p className="texto-tenue">Todavía no se compartió nada.</p>}
        {enlaces.datos && enlaces.datos.length > 0 && (
          <table className="tabla tabla--compacta tabla-enlaces">
            <thead>
              <tr>
                <th>Estado</th>
                <th>Comparte</th>
                <th>Vence</th>
                <th>Accesos</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {enlaces.datos.map((e) => (
                <tr key={e.id_enlace} data-estado={e.estado}>
                  <td>
                    <span className={`insignia ${e.estado === "vigente" ? "insignia--ok" : "insignia--error"}`}>
                      {estadoEnlace(e.estado)}
                    </span>
                  </td>
                  <td>
                    {e.versiones.map((v) => `${v.codigo_alternativa} · v${v.numero_version}`).join(", ")}
                    <div className="texto-tenue">
                      {e.creado_por.nombre} {e.creado_por.apellido} · {fechaHora(e.fecha_creacion)}
                    </div>
                  </td>
                  <td>{fecha(e.fecha_vencimiento)}</td>
                  <td>
                    {e.cantidad_accesos}
                    {e.ultimo_acceso && <div className="texto-tenue">último: {fechaHora(e.ultimo_acceso)}</div>}
                  </td>
                  <td>
                    {e.estado === "vigente" && revocando !== e.id_enlace && (
                      <button
                        type="button"
                        className="boton boton--chico"
                        disabled={ocupado}
                        onClick={() => setRevocando(e.id_enlace)}
                      >
                        Revocar
                      </button>
                    )}
                    {revocando === e.id_enlace && (
                      <span className="confirmar">
                        ¿Revocar? El cliente deja de verlo.{" "}
                        <button
                          type="button"
                          className="boton boton--chico boton--peligro"
                          disabled={ocupado}
                          onClick={() => void revocar(e.id_enlace)}
                        >
                          Sí, revocar
                        </button>{" "}
                        <button type="button" className="boton boton--chico" onClick={() => setRevocando(null)}>
                          No
                        </button>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}

// «Compartir con el cliente» de la comparación (figura 20; CU13, 5.a; D84): las seleccionadas, el
// destinatario, el vencimiento, el enlace recién generado (una sola vez, C3), el estado del último vigente y
// revocarlo. La lista completa queda en la pestaña «Compartir».
export function TarjetaCompartir({ proyecto, onCambio }: Props) {
  const id = proyecto.id_proyecto;
  const enlaces = useConsulta(`enlaces:${id}`, (c) => listarEnlaces(id, c));
  const [vencimiento, setVencimiento] = useState("");
  const [error, setError] = useState<{ error: ErrorOut; titulo: string } | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [nuevo, setNuevo] = useState<string | null>(null);
  const [copiado, setCopiado] = useState(false);
  const [revocando, setRevocando] = useState(false);

  const seleccionadas = proyecto.alternativas
    .filter((a) => a.estado === "seleccionada")
    .map((a) => `${a.codigo} · v${a.versiones.at(-1)?.numero}`);
  // La lista viene de la más nueva a la más vieja.
  const vigente = enlaces.datos?.find((e) => e.estado === "vigente") ?? null;
  const conError = (campo: string) => error?.error.problemas.some((p) => p.campo === campo);

  async function generar() {
    setOcupado(true);
    setError(null);
    setNuevo(null);
    setCopiado(false);
    const resultado = await compartir(id, vencimiento || null);
    setOcupado(false);
    if (resultado.ok) {
      setNuevo(direccionDelEnlace(resultado.datos.token));
      enlaces.recargar();
      onCambio();
    } else {
      setError({ error: resultado.error, titulo: "No se pudo generar el enlace" });
    }
  }

  async function revocar(idEnlace: number) {
    setOcupado(true);
    setError(null);
    const resultado = await revocarEnlace(idEnlace);
    setOcupado(false);
    setRevocando(false);
    if (resultado.ok) {
      setNuevo(null);
      enlaces.recargar();
    } else {
      setError({ error: resultado.error, titulo: "No se pudo revocar el enlace" });
    }
  }

  return (
    <TarjetaSeccion titulo="Compartir con el cliente" clase="tarjeta-compartir">
      <dl className="filas">
        <dt>Alternativas seleccionadas</dt>
        <dd>{seleccionadas.length > 0 ? enumerar(seleccionadas) : "ninguna"}</dd>
        <dt>Destinatario</dt>
        <dd>{proyecto.cliente.razon_social}</dd>
      </dl>
      <div className={`campo ${conError("fecha_vencimiento") ? "campo--error" : ""}`}>
        <label htmlFor="vencimiento-comparacion">Vencimiento del enlace</label>
        <input
          id="vencimiento-comparacion"
          type="date"
          value={vencimiento}
          onChange={(e) => setVencimiento(e.target.value)}
        />
      </div>
      {nuevo && (
        <div className="enlace-generado" role="status">
          <code className="enlace-nuevo__direccion">{nuevo}</code>
          <button
            type="button"
            className="boton boton--chico"
            onClick={() => {
              void navigator.clipboard?.writeText(nuevo);
              setCopiado(true);
            }}
          >
            {copiado ? "Copiado" : "Copiar"}
          </button>
        </div>
      )}
      {nuevo && <p className="texto-tenue">Se muestra esta única vez: en la base queda solo su hash.</p>}
      {vigente && (
        <dl className="filas">
          <dt>Estado</dt>
          <dd className="texto-ok">
            Vigente · {vigente.cantidad_accesos === 1 ? "1 acceso" : `${vigente.cantidad_accesos} accesos`}
          </dd>
          <dt>Comparte</dt>
          <dd>
            {enumerar(vigente.versiones.map((v) => `${v.codigo_alternativa} · v${v.numero_version}`))}, hasta el{" "}
            {fecha(vigente.fecha_vencimiento)}
          </dd>
        </dl>
      )}
      {error && <AvisoError error={error.error} titulo={error.titulo} />}
      {revocando && vigente ? (
        <p className="confirmar">
          ¿Revocar el enlace vigente? El cliente deja de verlo.{" "}
          <button
            type="button"
            className="boton boton--chico boton--peligro"
            disabled={ocupado}
            onClick={() => void revocar(vigente.id_enlace)}
          >
            Sí, revocar
          </button>{" "}
          <button type="button" className="boton boton--chico" onClick={() => setRevocando(false)}>
            No
          </button>
        </p>
      ) : (
        <div className="acciones acciones--derecha">
          {vigente && (
            <button type="button" className="boton" disabled={ocupado} onClick={() => setRevocando(true)}>
              Revocar enlace
            </button>
          )}
          <button type="button" className="boton boton--primario" disabled={ocupado} onClick={() => void generar()}>
            Generar enlace
          </button>
        </div>
      )}
      <a className="tarjeta-compartir__todos" href={rutas.compartir(id)}>
        Ver todos los enlaces
      </a>
    </TarjetaSeccion>
  );
}
