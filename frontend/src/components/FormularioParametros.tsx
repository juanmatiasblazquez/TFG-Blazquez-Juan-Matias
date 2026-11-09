import type { CampoLoteo, FuenteOut, ParametrosIn, ValoresParametrosOut } from "../api/parametros";
import {
  NO_APLICA,
  calleBorde,
  criterioEspacioVerde,
  escribirNumero,
  leerNumero,
  metros,
  numero,
  porcentaje,
  type NumeroEscrito,
} from "../formato";
import { TarjetaSeccion } from "./Marco";

// El formulario guarda lo que se escribe, como texto; al enviarlo se pasa a números
// (formato.leerNumero). Si un valor no es coherente lo dice la API, que valida con el motor
// (CU05, 3.a; D36, D78): acá no hay reglas.
export type FormParametros = {
  criterio_prioritario: string;
  porcentaje_espacio_verde: string;
  tolerancia_pct: string;
  loteo: Record<CampoLoteo, string>;
  // En la API van dentro de `loteo` (D46, D86); vacío es «no aplica» en un conjunto anterior.
  criterio_espacio_verde: string;
  calle_borde: string;
  jerarquias: {
    nombre: string;
    orden: number;
    ancho_calzada_m: string;
    ancho_vereda_m: string;
    radio_ochava_m: string;
    // El de la API, guardado (D78): no se manda.
    ancho_total_m: number | null;
    // Si el motor la usa, de la API (D85): no se manda.
    en_uso: boolean;
  }[];
};

// Un campo del loteo: su nombre en la pantalla y su unidad, que va dentro del campo (figura 16).
type Definicion = [CampoLoteo, string, string];

// Las tarjetas de la figura 16, con los parámetros que el motor usa. El criterio prioritario, la tolerancia
// y el equipamiento no se muestran: el motor no los usa todavía (decisión del autor, D83). Se mandan con el
// valor que trajo la API.
const PARCELA: Definicion[] = [
  ["frente_minimo_m", "Frente mínimo", "m"],
  ["fondo_minimo_m", "Fondo mínimo", "m"],
  ["superficie_minima_m2", "Superficie mínima", "m²"],
  ["superficie_maxima_m2", "Superficie máxima", "m²"],
  ["relacion_fondo_frente_max", "Relación fondo/frente máx.", ""],
  ["frente_objetivo_m", "Frente objetivo", "m"],
  // Criterio de forma (D43): con la relación, decide si una pieza es un lote.
  ["ancho_minimo_lote_m", "Ancho útil mínimo", "m"],
  ["factor_union_maximo", "Tope de unión", "× típico"],
  // Ord. 8060, art. 54 (D49).
  ["porcentaje_incremento_esquina", "Frente en esquina", "% más"],
];
const MANZANAS: Definicion[] = [
  ["longitud_maxima_manzana_m", "Longitud máxima de manzana", "m"],
  // Ord. 8060, art. 48 (D50).
  ["lado_minimo_manzana_m", "Lado menor mínimo", "m"],
  ["lado_maximo_manzana_m", "Lado mayor máximo", "m"],
  ["lado_maximo_sin_pasaje_m", "Lado mayor sin pasaje", "m"],
  // Cuándo un remanente es espacio verde y no espacio libre (D41).
  ["superficie_minima_verde_m2", "Superficie mínima del verde", "m²"],
  ["ancho_minimo_verde_m", "Ancho mínimo del verde", "m"],
];
// Ley 4146, art. 12 (D48).
const CALLES: Definicion[] = [
  ["ancho_minimo_calle_m", "Ancho mínimo de calle", "m"],
  ["ancho_minimo_avenida_m", "Ancho mínimo de avenida", "m"],
  ["ancho_minimo_calzada_m", "Calzada mínima", "m"],
  ["porcentaje_minimo_avenidas", "Mínimo de avenidas", "% calles"],
];
// Los de las avenidas: sin avenidas (la casilla desmarcada, porcentaje 0) el motor no los usa y no se
// muestran (D85). Se mandan con su valor.
const DE_AVENIDAS: CampoLoteo[] = ["ancho_minimo_avenida_m", "porcentaje_minimo_avenidas"];
const ETIQUETA_AVENIDAS = "Exigir avenidas (Ley 4146, art. 12)";
// La calle de borde (D86): la casilla marcada es «contorno» (D50) y desmarcada, «por_lado». Los nombres de
// los dos valores viven en formato.ts.
const ETIQUETA_CALLE_BORDE = "Calle de borde en todo el contorno";
const CALLE_BORDE_MARCADA = "contorno";
const CALLE_BORDE_DESMARCADA = "por_lado";
// Lo que se guarda pero no se muestra (D83).
const OCULTOS: Definicion[] = [["porcentaje_equipamiento", "Equipamiento comunitario", "%"]];
// Qué prioriza el asignador de espacios verdes (D46, D51). Los nombres viven en formato.ts.
const CRITERIOS_VERDE = ["cercania", "menos_lotes"];
const CRITERIOS: [string, string][] = [
  ["superficie_aprovechable", "Superficie aprovechable"],
  ["cantidad_celdas", "Cantidad de celdas"],
  ["longitud_red", "Longitud de red"],
];
const CAMPOS_LOTEO = [...PARCELA, ...MANZANAS, ...CALLES, ...OCULTOS].map(([campo]) => campo);
const ETIQUETA_CRITERIO_VERDE = "Criterio del verde";
const CONJUNTO: Record<string, [string, string]> = {
  porcentaje_espacio_verde: ["Espacio verde", "%"],
  tolerancia_pct: ["Tolerancia", "%"],
  criterio_prioritario: ["Criterio prioritario", ""],
};
const COLUMNAS_JERARQUIA = {
  nombre: "Jerarquía",
  ancho_calzada_m: "Ancho de calzada (m)",
  ancho_vereda_m: "Ancho de vereda (m)",
  // El nombre del ER es «radio» (D24, D29): es el largo de la línea de ochava.
  radio_ochava_m: "Largo de ochava (m)",
};
const SECCIONES: [string, Definicion[]][] = [
  ["Parcela", PARCELA],
  ["Manzanas y cesiones", MANZANAS],
  ["Red de circulación", CALLES],
  ["Manzanas y cesiones", OCULTOS],
];

const conUnidad = (etiqueta: string, unidad: string) => (unidad ? `${etiqueta} (${unidad})` : etiqueta);

// Para la comparación (CU13, D54): el nombre de un campo de ParametrosIn con su sección
// («Parcela · Frente mínimo (m)»), con las mismas etiquetas del formulario.
export function etiquetaParametro(campo: string): string {
  if (campo === "loteo.criterio_espacio_verde") return `Manzanas y cesiones · ${ETIQUETA_CRITERIO_VERDE}`;
  if (campo === "loteo.calle_borde") return "Red de circulación · Calle de borde";
  for (const [seccion, campos] of SECCIONES) {
    const encontrado = campos.find(([c]) => `loteo.${c}` === campo);
    if (encontrado) return `${seccion} · ${conUnidad(encontrado[1], encontrado[2])}`;
  }
  if (campo in CONJUNTO) return `Manzanas y cesiones · ${conUnidad(...CONJUNTO[campo])}`;
  const jerarquia = /^jerarquias\[(\d+)\]\.(\w+)$/.exec(campo);
  if (jerarquia) {
    const columna = COLUMNAS_JERARQUIA[jerarquia[2] as keyof typeof COLUMNAS_JERARQUIA] ?? jerarquia[2];
    return `Jerarquía ${Number(jerarquia[1]) + 1} · ${columna}`;
  }
  return campo;
}

// El valor de un parámetro, escrito como en el formulario. null es «no aplica» (D45).
export function valorParametro(campo: string, valor: number | string | null): string {
  if (valor === null) return NO_APLICA;
  if (campo === "loteo.criterio_espacio_verde") return criterioEspacioVerde(String(valor));
  if (campo === "loteo.calle_borde") return calleBorde(String(valor));
  if (campo === "criterio_prioritario") return CRITERIOS.find(([v]) => v === valor)?.[1] ?? String(valor);
  return typeof valor === "number" ? numero(valor) : valor;
}

export function formularioDesde(valores: ValoresParametrosOut): FormParametros {
  const loteo = Object.fromEntries(
    CAMPOS_LOTEO.map((campo) => [campo, valores.loteo ? escribirNumero(valores.loteo[campo], 2) : ""]),
  ) as Record<CampoLoteo, string>;
  return {
    criterio_prioritario: valores.criterio_prioritario,
    porcentaje_espacio_verde: escribirNumero(valores.porcentaje_espacio_verde, 2),
    tolerancia_pct: escribirNumero(valores.tolerancia_pct, 2),
    loteo,
    criterio_espacio_verde: valores.loteo?.criterio_espacio_verde ?? "",
    calle_borde: valores.loteo?.calle_borde ?? "",
    jerarquias: valores.jerarquias.map((j) => ({
      nombre: j.nombre,
      orden: j.orden,
      ancho_calzada_m: escribirNumero(j.ancho_calzada_m, 2),
      ancho_vereda_m: escribirNumero(j.ancho_vereda_m, 2),
      radio_ochava_m: escribirNumero(j.radio_ochava_m, 2),
      ancho_total_m: j.ancho_total_m,
      en_uso: j.en_uso,
    })),
  };
}

export function parametrosDesde(form: FormParametros): ParametrosIn {
  return {
    criterio_prioritario: form.criterio_prioritario,
    porcentaje_espacio_verde: leerNumero(form.porcentaje_espacio_verde),
    tolerancia_pct: leerNumero(form.tolerancia_pct),
    loteo: {
      ...(Object.fromEntries(CAMPOS_LOTEO.map((campo) => [campo, leerNumero(form.loteo[campo])])) as Record<
        CampoLoteo,
        NumeroEscrito
      >),
      // Vacío va como null: la API dice que falta (D37).
      criterio_espacio_verde: form.criterio_espacio_verde || null,
      calle_borde: form.calle_borde || null,
    },
    jerarquias: form.jerarquias.map((j) => ({
      nombre: j.nombre,
      orden: j.orden,
      ancho_calzada_m: leerNumero(j.ancho_calzada_m),
      ancho_vereda_m: leerNumero(j.ancho_vereda_m),
      radio_ochava_m: leerNumero(j.radio_ochava_m),
    })),
  };
}

// Los problemas de la API por campo de ParametrosIn: los de la validación de Pydantic vienen como
// «jerarquias.0.ancho_calzada_m» y los del motor como «jerarquias[0].ancho_calzada_m».
export function problemasPorCampo(
  problemas: { campo: string; mensaje: string }[],
  prefijo = "",
): Record<string, string> {
  const resultado: Record<string, string> = {};
  for (const { campo, mensaje } of problemas) {
    if (!campo.startsWith(prefijo)) continue;
    const clave = campo.slice(prefijo.length).replace(/^jerarquias\.(\d+)\./, "jerarquias[$1].");
    resultado[clave] ??= mensaje;
  }
  return resultado;
}

type Props = {
  form: FormParametros;
  // Sin `onCambio`, el formulario es de solo lectura.
  onCambio?: (form: FormParametros) => void;
  // Por campo de ParametrosIn: de dónde sale cada valor de referencia (D23).
  fuentes: Record<string, FuenteOut>;
  referencia: ValoresParametrosOut | null;
  // Los problemas que devolvió la API, por campo de ParametrosIn (sin prefijo).
  problemas?: Record<string, string>;
  // El ancho total de cada jerarquía con lo que se está editando, de la validación en vivo (D78).
  anchosTotales?: number[] | null;
  // Si el motor usaría cada jerarquía con lo que se está editando, de la validación en vivo (D85).
  enUso?: boolean[] | null;
};

// Las tarjetas «Parcela», «Manzanas y cesiones» y «Red de circulación» de la figura 16.
export function FormularioParametros({
  form,
  onCambio,
  fuentes,
  referencia,
  problemas = {},
  anchosTotales,
  enUso,
}: Props) {
  const cambiar = (cambio: Partial<FormParametros>) => onCambio?.({ ...form, ...cambio });
  // La casilla «Exigir avenidas» es el porcentaje del art. 12 distinto de 0 (D85). Vacío o mal escrito
  // cuenta como marcada, para que se vea el campo con su problema.
  const porcentajeAvenidas = form.loteo.porcentaje_minimo_avenidas;
  const exigeAvenidas = leerNumero(porcentajeAvenidas) !== 0;
  const conAvenidas = (exige: boolean) =>
    cambiar({
      loteo: {
        ...form.loteo,
        // Al volver a marcarla, el valor de referencia que sirve la API: acá no hay números de la norma.
        porcentaje_minimo_avenidas: exige ? escribirNumero(referencia?.loteo?.porcentaje_minimo_avenidas ?? null, 2) : "0",
      },
    });
  const referenciaAvenidas = referencia?.loteo;
  const normaAvenidas =
    referenciaAvenidas?.porcentaje_minimo_avenidas != null && referenciaAvenidas.ancho_minimo_avenida_m != null
      ? `, que pide el ${porcentaje(referenciaAvenidas.porcentaje_minimo_avenidas)} de la red en avenidas de al ` +
        `menos ${metros(referenciaAvenidas.ancho_minimo_avenida_m)}`
      : "";
  const cambiarJerarquia = (k: number, campo: string, texto: string) =>
    cambiar({ jerarquias: form.jerarquias.map((j, i) => (i === k ? { ...j, [campo]: texto } : j)) });
  const campoLoteo = ([campo, etiqueta, unidad]: Definicion) => (
    <Campo
      key={campo}
      id={`loteo.${campo}`}
      etiqueta={etiqueta}
      unidad={unidad}
      valor={form.loteo[campo]}
      onCambio={onCambio && ((texto) => cambiar({ loteo: { ...form.loteo, [campo]: texto } }))}
      fuente={fuentes[`loteo.${campo}`]}
      referencia={referencia?.loteo?.[campo]}
      problema={problemas[`loteo.${campo}`]}
    />
  );
  const problemasJerarquias = Object.entries(problemas).filter(([campo]) => campo.startsWith("jerarquias"));
  const columnas = ["ancho_calzada_m", "ancho_vereda_m", "radio_ochava_m"] as const;

  return (
    <div className="parametros">
      <div className="parametros__fila">
        <TarjetaSeccion titulo="Parcela">
          <div className="campos-dos">{PARCELA.map(campoLoteo)}</div>
        </TarjetaSeccion>

        <TarjetaSeccion titulo="Manzanas y cesiones">
          <div className="campos-dos">
            {campoLoteo(MANZANAS[0])}
            <Campo
              id="porcentaje_espacio_verde"
              etiqueta={CONJUNTO.porcentaje_espacio_verde[0]}
              unidad="%"
              valor={form.porcentaje_espacio_verde}
              onCambio={onCambio && ((texto) => cambiar({ porcentaje_espacio_verde: texto }))}
              fuente={fuentes.porcentaje_espacio_verde}
              referencia={referencia?.porcentaje_espacio_verde}
              problema={problemas.porcentaje_espacio_verde}
            />
            {MANZANAS.slice(1).map(campoLoteo)}
          </div>
          {/* En el lugar del criterio prioritario de la figura 16, que el motor no usa (D83). */}
          <fieldset className={`campo ${problemas["loteo.criterio_espacio_verde"] ? "campo--error" : ""}`}>
            <legend className="campo__rotulo">
              {ETIQUETA_CRITERIO_VERDE}
              <Fuente fuente={fuentes["loteo.criterio_espacio_verde"]} />
            </legend>
            {!onCambio && form.criterio_espacio_verde === "" ? (
              <p className="campo__referencia" title="El conjunto es anterior al motor que usa este parámetro (D45)">
                {NO_APLICA}
              </p>
            ) : (
              <div className="opciones" role="radiogroup" aria-label={ETIQUETA_CRITERIO_VERDE}>
                {CRITERIOS_VERDE.map((valor) => (
                  <label key={valor}>
                    <input
                      type="radio"
                      name="loteo.criterio_espacio_verde"
                      value={valor}
                      checked={form.criterio_espacio_verde === valor}
                      disabled={!onCambio}
                      onChange={() => cambiar({ criterio_espacio_verde: valor })}
                    />
                    {criterioEspacioVerde(valor)}
                  </label>
                ))}
              </div>
            )}
            <Marcas fuente={fuentes["loteo.criterio_espacio_verde"]} />
            {problemas["loteo.criterio_espacio_verde"] && (
              <p className="campo__problema">{problemas["loteo.criterio_espacio_verde"]}</p>
            )}
          </fieldset>
        </TarjetaSeccion>
      </div>

      <TarjetaSeccion titulo="Red de circulación: jerarquías de corredores">
        {/* Un conjunto anterior al art. 12 (D45) no tiene el porcentaje: la casilla no aplica. */}
        {(onCambio || porcentajeAvenidas !== "") && (
          <div className="parametros__avenidas">
            <span className="campo__rotulo">
              <label className={`casilla ${onCambio ? "" : "casilla--deshabilitada"}`}>
                <input
                  type="checkbox"
                  name="exigir_avenidas"
                  checked={exigeAvenidas}
                  disabled={!onCambio}
                  onChange={(e) => conAvenidas(e.target.checked)}
                />
                {ETIQUETA_AVENIDAS}
              </label>
              <Fuente fuente={fuentes["loteo.porcentaje_minimo_avenidas"]} />
            </span>
            {!exigeAvenidas && (
              <p className="campo__referencia">
                Todas las calles son de la jerarquía local. El conjunto se aparta del art. 12 de la Ley 4146
                {normaAvenidas}.
              </p>
            )}
          </div>
        )}
        <div className="campos-cuatro">
          {CALLES.filter(([campo]) => exigeAvenidas || !DE_AVENIDAS.includes(campo)).map(campoLoteo)}
        </div>
        {/* Un conjunto anterior al motor 0.11.0 que ningún motor con calle de borde usó no la tiene (D45). */}
        {(onCambio || form.calle_borde !== "") && (
          <div className={`parametros__calle-borde ${problemas["loteo.calle_borde"] ? "campo--error" : ""}`}>
            <span className="campo__rotulo">
              <label className={`casilla ${onCambio ? "" : "casilla--deshabilitada"}`}>
                <input
                  type="checkbox"
                  name="loteo.calle_borde"
                  checked={form.calle_borde === CALLE_BORDE_MARCADA}
                  disabled={!onCambio}
                  onChange={(e) =>
                    cambiar({ calle_borde: e.target.checked ? CALLE_BORDE_MARCADA : CALLE_BORDE_DESMARCADA })
                  }
                />
                {ETIQUETA_CALLE_BORDE}
              </label>
              <Fuente fuente={fuentes["loteo.calle_borde"]} />
            </span>
            <p className="campo__referencia">
              {form.calle_borde === CALLE_BORDE_MARCADA
                ? "Una calle recorre todo el límite del terreno."
                : form.calle_borde === CALLE_BORDE_DESMARCADA
                  ? "Solo en los lados paralelos a las filas, en los de una entrante y en los de un acceso; en los " +
                    "demás, las manzanas llegan hasta el límite."
                  : `Sin valor en este conjunto. Referencia: ${calleBorde(referencia?.loteo?.calle_borde ?? "")}.`}
            </p>
            <Marcas fuente={fuentes["loteo.calle_borde"]} />
            {problemas["loteo.calle_borde"] && <p className="campo__problema">{problemas["loteo.calle_borde"]}</p>}
          </div>
        )}
        <table className="tabla tabla-jerarquias">
          <thead>
            <tr>
              <th>Orden</th>
              <th>Jerarquía</th>
              <th className="numero">
                Ancho de calzada <Fuente fuente={fuentes["jerarquias.ancho_calzada_m"]} />
              </th>
              <th className="numero">Ancho de vereda</th>
              <th className="numero">
                Largo de ochava <Fuente fuente={fuentes["jerarquias.radio_ochava_m"]} />
              </th>
              <th className="numero" title="Calzada + 2 × vereda: lo calcula el motor">
                Ancho total
              </th>
            </tr>
          </thead>
          <tbody>
            {form.jerarquias.map((j, k) => {
              const total = anchosTotales?.[k] ?? j.ancho_total_m;
              // La que el motor no usa (la mayor, sin avenidas; D85) no se muestra: lo decide la API. Solo con
              // un `false` explícito: un borrador del alta anterior a D85 no lo trae (D81).
              if ((enUso?.[k] ?? j.en_uso) === false) return null;
              return (
                <tr key={j.orden}>
                  <td>{j.orden}</td>
                  <td>
                    <input
                      aria-label={`Nombre de la jerarquía ${k + 1}`}
                      name={`jerarquias[${k}].nombre`}
                      className={`tabla-jerarquias__nombre ${problemas[`jerarquias[${k}].nombre`] ? "input--error" : ""}`}
                      value={j.nombre}
                      readOnly={!onCambio}
                      onChange={(e) => cambiarJerarquia(k, "nombre", e.target.value)}
                    />
                  </td>
                  {columnas.map((campo) => (
                    <td key={campo} className="numero">
                      <span className="campo__entrada campo__entrada--tabla">
                        <input
                          aria-label={`${COLUMNAS_JERARQUIA[campo]} de la jerarquía ${k + 1}`}
                          name={`jerarquias[${k}].${campo}`}
                          className={problemas[`jerarquias[${k}].${campo}`] ? "input--error" : ""}
                          inputMode="decimal"
                          value={j[campo]}
                          readOnly={!onCambio}
                          onChange={(e) => cambiarJerarquia(k, campo, e.target.value)}
                        />
                        <span className="campo__unidad">m</span>
                      </span>
                    </td>
                  ))}
                  <td className="numero tabla-jerarquias__total">{total === null ? "—" : `${numero(total)} m`}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="campo__marcas tabla-jerarquias__marcas">
          <Marcas fuente={fuentes["jerarquias.ancho_calzada_m"]} prefijo="Anchos: " />
          <Marcas fuente={fuentes["jerarquias.radio_ochava_m"]} prefijo="Ochava: " />
        </p>
        {problemasJerarquias.map(([campo, mensaje]) => (
          <p key={campo} className="campo__problema">
            {etiquetaParametro(campo)}: {mensaje}
          </p>
        ))}
      </TarjetaSeccion>
    </div>
  );
}

type PropsCampo = {
  id: string;
  etiqueta: string;
  unidad: string;
  valor: string;
  onCambio?: (texto: string) => void;
  fuente?: FuenteOut;
  referencia?: number | null;
  problema?: string;
};

function Campo({ id, etiqueta, unidad, valor, onCambio, fuente, referencia, problema }: PropsCampo) {
  // Solo lectura y sin valor: el conjunto es anterior al motor que usa el parámetro (D45).
  const noAplica = !onCambio && valor === "";
  return (
    <div className={`campo ${problema ? "campo--error" : ""}`}>
      <label htmlFor={id} className="campo__rotulo">
        {etiqueta}
        <Fuente fuente={fuente} />
      </label>
      <span className="campo__entrada">
        <input
          id={id}
          name={id}
          inputMode="decimal"
          value={noAplica ? NO_APLICA : valor}
          readOnly={!onCambio}
          onChange={(e) => onCambio?.(e.target.value)}
          title={noAplica ? "El conjunto es anterior al motor que usa este parámetro (D45)" : undefined}
        />
        {unidad && !noAplica && <span className="campo__unidad">{unidad}</span>}
      </span>
      <Marcas fuente={fuente} />
      {problema && <p className="campo__problema">{problema}</p>}
      {!noAplica && referencia != null && leerNumero(valor) !== referencia && (
        <p className="campo__referencia">Referencia: {numero(referencia)}</p>
      )}
    </div>
  );
}

// De dónde sale el valor (D23): un ícono con el artículo de la norma al pasar el mouse, y las marcas que
// tienen que verse: «A validar» y «Criterio de diseño», que no sale de una norma (D46).
// El ícono va junto al nombre; las marcas, debajo del campo, para que los campos de una fila queden
// alineados.
function Fuente({ fuente }: { fuente?: FuenteOut }) {
  if (!fuente) return null;
  return (
    <span className="fuente" title={fuente.texto} aria-label={`Fuente: ${fuente.texto}`} role="img" tabIndex={0}>
      §
    </span>
  );
}

function Marcas({ fuente, prefijo }: { fuente?: FuenteOut; prefijo?: string }) {
  if (!fuente || (!fuente.a_validar && !fuente.criterio_diseno)) return null;
  return (
    <span className="campo__marcas">
      {prefijo}
      {fuente.a_validar && <span className="insignia insignia--aviso insignia--mini">A validar</span>}
      {fuente.criterio_diseno && <span className="insignia insignia--diseno insignia--mini">Criterio de diseño</span>}
    </span>
  );
}
