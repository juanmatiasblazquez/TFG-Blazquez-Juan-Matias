import { useEffect, useRef, useState } from "react";

import { crearCliente, listarClientes, type ClienteIn } from "../api/clientes";
import type { ErrorOut } from "../api/errores";
import { consultarReferencia } from "../api/parametros";
import { crearProyecto, type ProyectoIn } from "../api/proyectos";
import { importarVertices, medirTerreno, type MedicionOut } from "../api/terrenos";
import { descartarBorrador, guardarBorrador, leerBorrador } from "../borrador";
import { AvisoError } from "../components/AvisoError";
import { RayadoFijado } from "../components/CapasAlternativa";
import { ReferenciaNormativa, TarjetaCoherencia, useCoherencia } from "../components/CoherenciaParametros";
import { EditorTerreno, type ControlesEditor, type Dibujo, type Herramienta } from "../components/EditorTerreno";
import { areasParaEnviar, FormularioAreas, type DatosArea } from "../components/FormularioAreas";
import {
  FormularioParametros,
  formularioDesde,
  parametrosDesde,
  problemasPorCampo,
  type FormParametros,
} from "../components/FormularioParametros";
import { MapaBase } from "../components/MapaBase";
import { BarraPagina, Marca, TarjetaSeccion } from "../components/Marco";
import { Pasos } from "../components/Pasos";
import { RotulosTerreno } from "../components/RotulosTerreno";
import { fechaHora, leerNumero, numero } from "../formato";
import { useConsulta } from "../hooks/useConsulta";
import { navegar, rutas } from "../hooks/useRuta";
import { useSesion } from "../hooks/useSesion";

type Paso = 1 | 2 | 3;

const PASOS: [Paso, string][] = [
  [1, "Datos del proyecto"],
  [2, "Terreno"],
  [3, "Parámetros"],
];

// En qué paso se corrige un campo que la API señaló.
function pasoDe(campo: string): Paso {
  if (campo.startsWith("terreno") || campo.startsWith("accesos") || campo.startsWith("areas_reservadas")) return 2;
  if (campo.startsWith("parametros")) return 3;
  return 1;
}

const DATOS_VACIOS = { codigo: "", nombre: "", tipo: "loteo", ubicacion: "", jurisdiccion: "", srid_calculo: "" };
const CLIENTE_VACIO = { razon_social: "", cuit: "", email: "", telefono: "" };
const DIBUJO_VACIO: Dibujo = { terreno: null, accesos: [], areas: [] };

// Lo que se guarda en el navegador (D81). Las áreas van en el orden del dibujo: sus `id` cambian al
// volver a dibujarlas.
type Borrador = {
  guardado: string;
  paso: Paso;
  datos: typeof DATOS_VACIOS;
  idCliente: number | null;
  dibujo: Dibujo;
  origen: "dibujado" | "importado";
  vias: string[];
  anchos: string[];
  areas: DatosArea[];
  parametros: FormParametros | null;
};

// El valor `indice` de una lista; los que todavía no se escribieron quedan vacíos.
function conValor(lista: string[], indice: number, texto: string): string[] {
  const nueva = [...lista];
  nueva[indice] = texto;
  return Array.from(nueva, (valor) => valor ?? "");
}

// Qué dice el aviso del mapa con cada herramienta (figura 15).
const AYUDAS: Record<Herramienta, [string, string]> = {
  terreno: ["Dibujo del polígono", "Clic para agregar vértices · clic en el primero para cerrar · Esc para cancelar"],
  rectangulo: ["Dibujo del rectángulo", "Clic en una esquina y clic en la opuesta"],
  acceso: ["Punto de acceso", "Clic sobre el borde del terreno · Esc o el botón para terminar"],
  area: ["Área reservada", "Clic para agregar vértices · clic en el primero para cerrar"],
  editar: ["Mover vértices", "Arrastrá un vértice del terreno o de un área, o un acceso · Esc para terminar"],
  rotar: ["Rotar", "Arrastrá una esquina del terreno o de un área · Esc para terminar"],
  borrar: ["Borrar", "Clic en el terreno, en un área o en un acceso · Esc para terminar"],
};

// Las herramientas de la figura 15, con el `title` que dice qué hacen.
const HERRAMIENTAS: [Herramienta, string, string, string][] = [
  ["terreno", "Dibujar polígono", "Dibujar el terreno (polígono libre)", "⬠"],
  ["acceso", "Punto de acceso", "Agregar un acceso sobre el borde del terreno", "●"],
  ["area", "Área reservada", "Dibujar un área reservada dentro del terreno", "▨"],
];
const SECUNDARIAS: [Herramienta, string, string][] = [
  ["rectangulo", "Rectángulo", "Dibujar el terreno (rectángulo)"],
  ["editar", "Mover vértices", "Mover vértices del terreno, de un área o de un acceso"],
  ["rotar", "Rotar", "Rotar el terreno o un área"],
  ["borrar", "Borrar", "Borrar el terreno, un área o un acceso"],
];

// El alta del proyecto (CU03, que ejecuta CU04 y CU05; figuras 15 y 16). Todo va en un solo POST al final;
// lo que falte o esté mal lo señala la API, campo por campo (D37). Mientras tanto, la API mide el terreno y
// valida la geometría (D79) y la coherencia de los parámetros (D78), y el navegador guarda un borrador (D81).
export function NuevoProyecto() {
  const { puede, sesion } = useSesion();
  const idUsuario = sesion?.usuario.id_usuario ?? 0;
  const [recuperado] = useState(() => leerBorrador<Borrador>(idUsuario));
  const [paso, setPaso] = useState<Paso>(recuperado?.paso ?? 1);
  const [datos, setDatos] = useState(recuperado?.datos ?? DATOS_VACIOS);
  const [idCliente, setIdCliente] = useState<number | null>(recuperado?.idCliente ?? null);
  const clientes = useConsulta("clientes", listarClientes);
  const [altaCliente, setAltaCliente] = useState<typeof CLIENTE_VACIO | null>(null);
  const [errorCliente, setErrorCliente] = useState<ErrorOut | null>(null);
  const [dibujo, setDibujo] = useState<Dibujo>(recuperado?.dibujo ?? DIBUJO_VACIO);
  const [origen, setOrigen] = useState<"dibujado" | "importado">(recuperado?.origen ?? "dibujado");
  const [vias, setVias] = useState<string[]>(recuperado?.vias ?? []);
  const [anchos, setAnchos] = useState<string[]>(recuperado?.anchos ?? []);
  // Por el `id` de cada área dibujada: no se pierde lo escrito si se borra otra.
  const [datosAreas, setDatosAreas] = useState<Record<number, DatosArea>>({});
  const areasPendientes = useRef<DatosArea[] | null>(recuperado?.areas ?? null);
  const referencia = useConsulta("referencia", consultarReferencia);
  const [parametros, setParametros] = useState<FormParametros | null>(recuperado?.parametros ?? null);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<ErrorOut | null>(null);
  const [aviso, setAviso] = useState<string | null>(recuperado ? recuperado.guardado : null);
  const [guardadoEn, setGuardadoEn] = useState<string | null>(null);
  const [claveEditor, setClaveEditor] = useState(0);
  const [inicial, setInicial] = useState<Dibujo | null>(recuperado?.dibujo ?? null);
  const editor = useRef<ControlesEditor>(null);
  const [herramienta, setHerramienta] = useState<Herramienta | null>(null);
  const [medicion, setMedicion] = useState<MedicionOut | null>(null);
  const [errorMedicion, setErrorMedicion] = useState<ErrorOut | null>(null);
  const [importacion, setImportacion] = useState<{ texto: string; error: ErrorOut | null } | null>(null);
  const [importado, setImportado] = useState<string | null>(null);

  // Hasta que se toque, el formulario muestra los valores por defecto que sirve la API.
  const formParametros = parametros ?? (referencia.datos && formularioDesde(referencia.datos.valores));
  const coherencia = useCoherencia(paso === 3 ? formParametros : null);
  const problemas = Object.fromEntries((error?.problemas ?? []).map((p) => [p.campo, p.mensaje]));
  const pasosConProblemas = new Set((error?.problemas ?? []).map((p) => pasoDe(p.campo)));
  const problemasParametros = { ...coherencia.problemas, ...problemasPorCampo(error?.problemas ?? [], "parametros.") };
  const nombresAreas = dibujo.areas.map(({ id }) => datosAreas[id]?.denominacion ?? "");

  // Lo que dibuja el editor; al recuperar un borrador, los datos de cada área vuelven a su `id` nuevo.
  function alDibujar(nuevo: Dibujo) {
    setDibujo(nuevo);
    const pendientes = areasPendientes.current;
    if (pendientes && nuevo.areas.length === pendientes.length) {
      setDatosAreas(Object.fromEntries(nuevo.areas.map((a, i) => [a.id, pendientes[i]])));
      areasPendientes.current = null;
    }
  }

  // El borrador (D81): un segundo después del último cambio, si hay algo escrito o dibujado.
  const algoEscrito =
    idCliente !== null ||
    dibujo.terreno !== null ||
    parametros !== null ||
    Object.entries(datos).some(([campo, valor]) => campo !== "tipo" && valor.trim() !== "");
  useEffect(() => {
    if (!algoEscrito || !idUsuario) return;
    const temporizador = window.setTimeout(() => {
      const ahora = new Date();
      const borrador: Borrador = {
        guardado: ahora.toISOString(),
        paso,
        datos,
        idCliente,
        dibujo,
        origen,
        vias,
        anchos,
        areas: dibujo.areas.map(({ id }) => datosAreas[id] ?? { denominacion: "", clase: "", destino: "" }),
        parametros,
      };
      if (guardarBorrador(idUsuario, borrador)) {
        setGuardadoEn(ahora.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }));
      }
    }, 1000);
    return () => window.clearTimeout(temporizador);
  }, [algoEscrito, idUsuario, paso, datos, idCliente, dibujo, origen, vias, anchos, datosAreas, parametros]);

  function descartar() {
    descartarBorrador(idUsuario);
    setPaso(1);
    setDatos(DATOS_VACIOS);
    setIdCliente(null);
    setDibujo(DIBUJO_VACIO);
    setOrigen("dibujado");
    setVias([]);
    setAnchos([]);
    setDatosAreas({});
    areasPendientes.current = null;
    setParametros(null);
    setError(null);
    setAviso(null);
    setGuardadoEn(null);
    setInicial(null);
    setClaveEditor((k) => k + 1);
  }

  // La medición y la validación de la geometría, mientras se dibuja (D79).
  const sridEscrito = datos.srid_calculo;
  useEffect(() => {
    if (!dibujo.terreno) {
      setMedicion(null);
      setErrorMedicion(null);
      return;
    }
    const controlador = new AbortController();
    const temporizador = window.setTimeout(() => {
      medirTerreno(
        {
          terreno: dibujo.terreno!,
          accesos: dibujo.accesos,
          areas_reservadas: dibujo.areas.map((a) => a.poligono),
          srid_calculo: leerNumero(sridEscrito),
        },
        controlador.signal,
      ).then(
        (resultado) => {
          setMedicion(resultado.ok ? resultado.datos : null);
          setErrorMedicion(resultado.ok ? null : resultado.error);
        },
        (e: unknown) => {
          if (!(e instanceof DOMException && e.name === "AbortError")) throw e;
        },
      );
    }, 300);
    return () => {
      window.clearTimeout(temporizador);
      controlador.abort();
    };
  }, [dibujo, sridEscrito]);

  async function darDeAltaCliente() {
    if (!altaCliente) return;
    const cuerpo: ClienteIn = {
      razon_social: altaCliente.razon_social,
      cuit: altaCliente.cuit || null,
      email: altaCliente.email || null,
      telefono: altaCliente.telefono || null,
    };
    const resultado = await crearCliente(cuerpo);
    if (resultado.ok) {
      setIdCliente(resultado.datos.id_cliente);
      setAltaCliente(null);
      setErrorCliente(null);
      clientes.recargar();
    } else {
      setErrorCliente(resultado.error);
    }
  }

  // B4 (D80): la planilla la lee la API; el polígono vuelve con la precisión completa.
  async function importar() {
    if (!importacion) return;
    const resultado = await importarVertices(importacion.texto, leerNumero(datos.srid_calculo));
    if (!resultado.ok) {
      setImportacion({ ...importacion, error: resultado.error });
      return;
    }
    const { terreno, formato, srid_calculo, sistema, cantidad_vertices } = resultado.datos;
    editor.current?.cargarTerreno(terreno);
    setOrigen("importado");
    // En POSGAR, la faja de la planilla es el sistema de cálculo, si no se eligió otro.
    if (formato === "posgar" && datos.srid_calculo.trim() === "") {
      setDatos({ ...datos, srid_calculo: String(srid_calculo) });
    }
    setImportacion(null);
    setAviso(null);
    setGuardadoEn(null);
    setErrorMedicion(null);
    setImportado(`Se importaron ${cantidad_vertices} vértices en ${sistema}.`);
  }

  async function registrar() {
    setEnviando(true);
    setError(null);
    const cuerpo: ProyectoIn = {
      ...(idCliente !== null && { id_cliente: idCliente }),
      codigo: datos.codigo,
      nombre: datos.nombre,
      tipo: datos.tipo,
      ubicacion: datos.ubicacion || null,
      jurisdiccion: datos.jurisdiccion || null,
      srid_calculo: leerNumero(datos.srid_calculo),
      ...(dibujo.terreno && { terreno: dibujo.terreno }),
      origen,
      accesos: dibujo.accesos.map((ubicacion, i) => ({
        ubicacion,
        ancho_m: leerNumero(anchos[i] ?? ""),
        via_vinculacion: vias[i]?.trim() || null,
      })),
      areas_reservadas: areasParaEnviar(dibujo.areas, datosAreas),
      parametros: formParametros && parametrosDesde(formParametros),
    };
    const resultado = await crearProyecto(cuerpo);
    setEnviando(false);
    if (resultado.ok) {
      descartarBorrador(idUsuario);
      navegar(rutas.proyecto(resultado.datos.id_proyecto));
    } else {
      setError(resultado.error);
    }
  }

  // Sin el permiso, la pantalla no ofrece el alta: la API respondería 403 igual (D37).
  if (!puede("registrar_proyectos")) {
    return (
      <div className="pagina">
        <h2>Nuevo proyecto</h2>
        <p className="texto-tenue">
          Tu rol no permite registrar proyectos: es del director técnico.{" "}
          <a href={rutas.proyectos}>Volver a la lista</a>
        </p>
      </div>
    );
  }

  const campoTexto = (campo: keyof typeof datos, etiqueta: string, placeholder?: string) => (
    <div className={`campo ${problemas[campo] ? "campo--error" : ""}`}>
      <label htmlFor={campo}>{etiqueta}</label>
      <input
        id={campo}
        name={campo}
        value={datos[campo]}
        placeholder={placeholder}
        onChange={(e) => setDatos({ ...datos, [campo]: e.target.value })}
      />
      {problemas[campo] && <p className="campo__problema">{problemas[campo]}</p>}
    </div>
  );
  const cliente = clientes.datos?.find((c) => c.id_cliente === idCliente);
  const ayuda = herramienta
    ? AYUDAS[herramienta]
    : dibujo.terreno
      ? null
      : (["Delimitación del terreno", "Elegí «Dibujar polígono» o «Importar vértices CSV»"] as [string, string]);
  const activar = (h: Herramienta) => {
    if (h === "terreno" || h === "rectangulo") setOrigen("dibujado");
    editor.current?.activar(h);
  };

  return (
    <div className="vista">
      <BarraPagina
        migas={[{ texto: "Proyectos", href: rutas.proyectos }]}
        titulo="Nuevo proyecto"
        centro={
          <Pasos
            pasos={PASOS.map(([numero, texto]) => ({
              texto,
              estado: numero < paso ? "hecho" : numero === paso ? "actual" : "pendiente",
              onElegir: () => setPaso(numero),
              conProblemas: pasosConProblemas.has(numero),
            }))}
          />
        }
        acciones={
          <>
            {guardadoEn && (
              <span className="insignia insignia--grande insignia--info" title="En este navegador (D81)">
                Borrador guardado {guardadoEn}
              </span>
            )}
            {paso > 1 ? (
              <button type="button" className="boton" onClick={() => setPaso((paso - 1) as Paso)}>
                Volver
              </button>
            ) : (
              <a className="boton" href={rutas.proyectos}>
                Cancelar
              </a>
            )}
            {paso < 3 ? (
              <button type="button" className="boton boton--primario" onClick={() => setPaso((paso + 1) as Paso)}>
                Guardar y continuar
              </button>
            ) : (
              <button type="button" className="boton boton--primario" disabled={enviando} onClick={registrar}>
                {enviando ? "Registrando…" : "Registrar proyecto"}
              </button>
            )}
          </>
        }
      />
      <div className="vista__cuerpo">
        {/* El mapa queda montado en el paso 3, oculto: lo dibujado no se pierde. */}
        <div className="espacio espacio--panel-izquierda" style={paso === 3 ? { display: "none" } : undefined}>
          <aside className="panel panel--alta">
            {aviso && (
              <p className="aviso aviso--info">
                Se recuperó el borrador del {fechaHora(aviso)}, guardado en este navegador.{" "}
                <button type="button" className="boton boton--enlace" onClick={descartar}>
                  Descartar borrador
                </button>
              </p>
            )}
            {error && <AvisoError error={error} titulo="No se pudo registrar el proyecto" />}

            {paso === 1 && (
              <TarjetaSeccion titulo="Datos del proyecto">
                <div className={`campo ${problemas.id_cliente ? "campo--error" : ""}`}>
                  <label htmlFor="id_cliente">Cliente</label>
                  <select
                    id="id_cliente"
                    value={idCliente ?? ""}
                    onChange={(e) => setIdCliente(e.target.value ? Number(e.target.value) : null)}
                  >
                    <option value="">Elegí un cliente…</option>
                    {clientes.datos?.map((c) => (
                      <option key={c.id_cliente} value={c.id_cliente}>
                        {c.razon_social}
                        {c.cuit ? ` (CUIT ${c.cuit})` : ""}
                      </option>
                    ))}
                  </select>
                  {problemas.id_cliente && <p className="campo__problema">{problemas.id_cliente}</p>}
                  {clientes.error && (
                    <AvisoError error={clientes.error} titulo="No se pudo leer la lista de clientes" />
                  )}
                  {!altaCliente && (
                    <button type="button" className="boton boton--enlace" onClick={() => setAltaCliente(CLIENTE_VACIO)}>
                      ¿No está? Dar de alta un cliente
                    </button>
                  )}
                </div>

                {altaCliente && (
                  <fieldset className="subformulario">
                    <legend>Nuevo cliente</legend>
                    {errorCliente && <AvisoError error={errorCliente} titulo="No se pudo dar de alta el cliente" />}
                    {(
                      [
                        ["razon_social", "Razón social"],
                        ["cuit", "CUIT (opcional)"],
                        ["email", "Correo (opcional)"],
                        ["telefono", "Teléfono (opcional)"],
                      ] as const
                    ).map(([campo, etiqueta]) => (
                      <div className="campo" key={campo}>
                        <label htmlFor={`cliente.${campo}`}>{etiqueta}</label>
                        <input
                          id={`cliente.${campo}`}
                          value={altaCliente[campo]}
                          onChange={(e) => setAltaCliente({ ...altaCliente, [campo]: e.target.value })}
                        />
                      </div>
                    ))}
                    <div className="acciones">
                      <button type="button" className="boton boton--primario" onClick={darDeAltaCliente}>
                        Dar de alta
                      </button>
                      <button type="button" className="boton" onClick={() => setAltaCliente(null)}>
                        Cancelar
                      </button>
                    </div>
                  </fieldset>
                )}

                {campoTexto("codigo", "Código", "Por ejemplo, LT-2026-014")}
                {campoTexto("nombre", "Nombre")}
                <div className={`campo ${problemas.tipo ? "campo--error" : ""}`}>
                  <span className="campo__etiqueta">Tipo de proyecto</span>
                  <TipoProyecto />
                  {problemas.tipo && <p className="campo__problema">{problemas.tipo}</p>}
                </div>
                {campoTexto("ubicacion", "Ubicación (opcional)")}
                {campoTexto("jurisdiccion", "Jurisdicción (opcional)", "Por ejemplo, Municipalidad de Córdoba")}
                {campoTexto(
                  "srid_calculo",
                  "Sistema de cálculo, EPSG (opcional)",
                  "Vacío: la faja POSGAR 2007 del terreno",
                )}
              </TarjetaSeccion>
            )}

            {paso === 2 && (
              <>
                <TarjetaSeccion titulo="Proyecto">
                  <dl className="filas">
                    <dt>Nombre</dt>
                    <dd>{datos.nombre || "—"}</dd>
                    <dt>Código</dt>
                    <dd>{datos.codigo || "—"}</dd>
                    <dt>Cliente</dt>
                    <dd>{cliente?.razon_social ?? "—"}</dd>
                  </dl>
                  <span className="campo__etiqueta">Tipo de proyecto</span>
                  <TipoProyecto />
                  <dl className="filas">
                    <dt>Sistema de cálculo</dt>
                    <dd>
                      {medicion?.sistema ??
                        (datos.srid_calculo.trim()
                          ? `EPSG:${datos.srid_calculo.trim()}`
                          : "La faja POSGAR 2007 del terreno")}
                    </dd>
                  </dl>
                </TarjetaSeccion>

                <TarjetaSeccion titulo="Herramientas de delimitación">
                  <div className="herramientas">
                    {HERRAMIENTAS.slice(0, 1).map(([clave, texto, titulo, icono]) => (
                      <BotonHerramienta
                        key={clave}
                        activa={herramienta === clave}
                        titulo={titulo}
                        icono={icono}
                        onClick={() => activar(clave)}
                      >
                        {texto}
                      </BotonHerramienta>
                    ))}
                    <BotonHerramienta
                      activa={importacion !== null}
                      titulo="Importar los vértices del terreno desde una planilla (CSV)"
                      icono="⇪"
                      onClick={() => {
                        editor.current?.terminar();
                        setImportado(null);
                        setImportacion(importacion ? null : { texto: "", error: null });
                      }}
                    >
                      Importar vértices CSV
                    </BotonHerramienta>
                    {HERRAMIENTAS.slice(1).map(([clave, texto, titulo, icono]) => (
                      <BotonHerramienta
                        key={clave}
                        activa={herramienta === clave}
                        titulo={titulo}
                        icono={icono}
                        onClick={() => activar(clave)}
                      >
                        {texto}
                      </BotonHerramienta>
                    ))}
                  </div>
                  <div className="herramientas herramientas--chicas">
                    {SECUNDARIAS.map(([clave, texto, titulo]) => (
                      <button
                        key={clave}
                        type="button"
                        className={`boton boton--chico ${herramienta === clave ? "boton--activo" : ""}`}
                        title={titulo}
                        aria-pressed={herramienta === clave}
                        onClick={() => activar(clave)}
                      >
                        {texto}
                      </button>
                    ))}
                  </div>
                  {importacion && (
                    <ImportarPlanilla
                      texto={importacion.texto}
                      error={importacion.error}
                      onTexto={(texto) => setImportacion({ ...importacion, texto, error: null })}
                      onImportar={() => void importar()}
                      onCancelar={() => setImportacion(null)}
                    />
                  )}
                  {importado && <p className="texto-ok">{importado}</p>}
                </TarjetaSeccion>

                <TarjetaSeccion titulo="Terreno">
                  {problemas.terreno && <p className="campo__problema">{problemas.terreno}</p>}
                  <div className="datos-terreno">
                    <Dato
                      titulo="Superficie"
                      valor={medicion?.superficie_m2 != null ? numero(medicion.superficie_m2 / 10_000) : "—"}
                      unidad="ha"
                    />
                    <Dato
                      titulo="Perímetro"
                      valor={medicion?.perimetro_m != null ? numero(medicion.perimetro_m, 1) : "—"}
                      unidad="m"
                    />
                    <Dato titulo="Vértices" valor={medicion ? String(medicion.vertices.length) : "—"} />
                  </div>
                </TarjetaSeccion>

                <TarjetaSeccion titulo="Accesos y áreas reservadas">
                  {dibujo.accesos.length === 0 && <p className="texto-tenue">Todavía no hay accesos.</p>}
                  {dibujo.accesos.map((_, i) => (
                    <div key={i}>
                      <div className="fila-acceso">
                        <span className="codigo-redondo">A{i + 1}</span>
                        <label htmlFor={`via-${i}`} className="oculto">
                          A{i + 1}: vía de vinculación
                        </label>
                        <input
                          id={`via-${i}`}
                          value={vias[i] ?? ""}
                          placeholder="Vía de vinculación (opcional)"
                          onChange={(e) => setVias(conValor(vias, i, e.target.value))}
                        />
                        <label htmlFor={`ancho-${i}`} className="fila-acceso__rotulo">
                          ancho
                        </label>
                        <span className="campo__entrada fila-acceso__ancho">
                          <input
                            id={`ancho-${i}`}
                            inputMode="decimal"
                            value={anchos[i] ?? ""}
                            onChange={(e) => setAnchos(conValor(anchos, i, e.target.value))}
                          />
                          <span className="campo__unidad">m</span>
                        </span>
                      </div>
                      {problemas[`accesos[${i}]`] && <p className="campo__problema">{problemas[`accesos[${i}]`]}</p>}
                      {problemas[`accesos.${i}.ancho_m`] && (
                        <p className="campo__problema">{problemas[`accesos.${i}.ancho_m`]}</p>
                      )}
                    </div>
                  ))}
                  {problemas.accesos && <p className="campo__problema">{problemas.accesos}</p>}
                  <FormularioAreas
                    areas={dibujo.areas}
                    datos={datosAreas}
                    onCambio={setDatosAreas}
                    problemas={problemas}
                    superficies={medicion?.areas.map((a) => a.superficie_m2)}
                  />
                </TarjetaSeccion>

                <TarjetaSeccion titulo="Validación de la geometría">
                  {errorMedicion && <AvisoError error={errorMedicion} titulo="No se pudo medir el terreno" />}
                  {!medicion && !errorMedicion && (
                    <p className="texto-tenue">Se valida con las reglas del motor a medida que se dibuja.</p>
                  )}
                  {medicion && (
                    <ul className="verificaciones">
                      {medicion.reglas.map((r) => (
                        <li key={r.clave} data-clave={r.clave}>
                          <Marca tipo={r.cumple ? "ok" : "error"} />
                          <strong>{r.descripcion}</strong>
                          {!r.cumple && <p>{r.detalle}</p>}
                        </li>
                      ))}
                    </ul>
                  )}
                </TarjetaSeccion>
              </>
            )}
          </aside>

          <div className="espacio__mapa">
            <RayadoFijado />
            <MapaBase>
              <EditorTerreno
                key={claveEditor}
                ref={editor}
                habilitado={paso === 2}
                onCambio={alDibujar}
                inicial={inicial}
                nombresAreas={nombresAreas}
                onHerramienta={setHerramienta}
              />
              {paso === 2 && <RotulosTerreno medicion={medicion} />}
            </MapaBase>
            {paso === 2 && ayuda && (
              <div className="sobre-mapa aviso-mapa" role="status">
                <strong>{ayuda[0]}</strong>
                <span>{ayuda[1]}</span>
              </div>
            )}
          </div>
        </div>

        {paso === 3 && (
          <div className="vista__cuerpo--hoja alta-parametros">
            {aviso && (
              <p className="aviso aviso--info">
                Se recuperó el borrador del {fechaHora(aviso)}, guardado en este navegador.{" "}
                <button type="button" className="boton boton--enlace" onClick={descartar}>
                  Descartar borrador
                </button>
              </p>
            )}
            {error && <AvisoError error={error} titulo="No se pudo registrar el proyecto" />}
            <div className="parametros-pagina">
              <div className="parametros-pagina__principal">
                {referencia.error && (
                  <AvisoError error={referencia.error} titulo="No se pudieron leer los valores por defecto" />
                )}
                {formParametros && referencia.datos && (
                  <FormularioParametros
                    form={formParametros}
                    onCambio={setParametros}
                    fuentes={referencia.datos.fuentes}
                    referencia={referencia.datos.valores}
                    problemas={problemasParametros}
                    anchosTotales={coherencia.datos?.anchos_totales}
                    enUso={coherencia.datos?.jerarquias_en_uso}
                  />
                )}
                <ReferenciaNormativa />
              </div>
              <aside className="parametros-pagina__lateral" aria-label="Validación">
                {formParametros && <TarjetaCoherencia coherencia={coherencia} />}
              </aside>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// El tipo de proyecto (figura 15): la playa de estacionamiento se ve, pero todavía no se puede elegir
// (decisión del autor, sesión 14): el motor no la genera.
function TipoProyecto() {
  return (
    <div className="segmentado" role="radiogroup" aria-label="Tipo de proyecto">
      <button type="button" role="radio" aria-checked="true" className="segmentado__opcion segmentado__opcion--activa">
        Loteo
      </button>
      <span title="Todavía no implementada">
        <button type="button" role="radio" aria-checked="false" className="segmentado__opcion" disabled>
          Playa de estacionamiento
        </button>
      </span>
      <span className="segmentado__nota">Playa de estacionamiento: todavía no implementada.</span>
    </div>
  );
}

type PropsBoton = { activa: boolean; titulo: string; icono: string; onClick: () => void; children: string };

function BotonHerramienta({ activa, titulo, icono, onClick, children }: PropsBoton) {
  return (
    <button
      type="button"
      className={`herramienta ${activa ? "herramienta--activa" : ""}`}
      title={titulo}
      aria-pressed={activa}
      onClick={onClick}
    >
      <span className="herramienta__icono" aria-hidden="true">
        {icono}
      </span>
      {children}
    </button>
  );
}

function Dato({ titulo, valor, unidad }: { titulo: string; valor: string; unidad?: string }) {
  return (
    <div className="dato-terreno">
      <span>{titulo}</span>
      <strong>
        {valor}
        {unidad && valor !== "—" && <small> {unidad}</small>}
      </strong>
    </div>
  );
}

type PropsImportar = {
  texto: string;
  error: ErrorOut | null;
  onTexto: (texto: string) => void;
  onImportar: () => void;
  onCancelar: () => void;
};

// La planilla de vértices (D80): un archivo o el texto pegado. La lee la API.
function ImportarPlanilla({ texto, error, onTexto, onImportar, onCancelar }: PropsImportar) {
  return (
    <div className="importar">
      <div className="campo">
        <label htmlFor="planilla-archivo">Archivo CSV</label>
        <input
          id="planilla-archivo"
          type="file"
          accept=".csv,.txt,text/csv,text/plain"
          onChange={(e) => {
            const archivo = e.target.files?.[0];
            if (archivo) void archivo.text().then(onTexto);
          }}
        />
      </div>
      <div className={`campo ${error ? "campo--error" : ""}`}>
        <label htmlFor="planilla-texto">O pegá los vértices</label>
        <textarea
          id="planilla-texto"
          rows={5}
          value={texto}
          placeholder={"vertice;este;norte\nV1;4436512,30;6522140,15\n…"}
          onChange={(e) => onTexto(e.target.value)}
        />
      </div>
      <p className="campo__fuente">
        Una cabecera <code>este;norte</code> (POSGAR 2007, en metros, como las planillas de mensura) o{" "}
        <code>latitud;longitud</code> (en grados), con <code>vertice</code> opcional, y un vértice por línea. Con «;»,
        la coma decimal.
      </p>
      {error && <AvisoError error={error} titulo="No se pudo importar la planilla" />}
      <div className="acciones">
        <button type="button" className="boton boton--primario" disabled={!texto.trim()} onClick={onImportar}>
          Importar
        </button>
        <button type="button" className="boton" onClick={onCancelar}>
          Cancelar
        </button>
      </div>
    </div>
  );
}
