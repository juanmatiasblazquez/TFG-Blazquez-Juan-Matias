import type { AreaReservadaIn } from "../api/proyectos";
import { metrosCuadrados } from "../formato";
import type { AreaDibujada } from "./EditorTerreno";

// Lo que el director técnico indica de cada área (CU04, paso 5): a qué corresponde, y la clase y el
// destino, opcionales. La clase es texto libre: el documento no enumera ClaseArea (D29, D59).
export type DatosArea = { denominacion: string; clase: string; destino: string };
export const AREA_VACIA: DatosArea = { denominacion: "", clase: "", destino: "" };

// El cuerpo de las áreas para la API. Una denominación vacía va igual: la API responde qué falta (D37).
export function areasParaEnviar(areas: AreaDibujada[], datos: Record<number, DatosArea>): AreaReservadaIn[] {
  return areas.map(({ id, poligono }) => {
    const area = datos[id] ?? AREA_VACIA;
    return {
      geometria: poligono,
      denominacion: area.denominacion.trim(),
      clase: area.clase.trim() || null,
      destino: area.destino.trim() || null,
    };
  });
}

type Props = {
  areas: AreaDibujada[];
  // Por el `id` de cada área dibujada: no se pierde lo escrito si se borra otra.
  datos: Record<number, DatosArea>;
  onCambio: (datos: Record<number, DatosArea>) => void;
  // Los problemas de la API por campo, con el nombre que da la API («areas_reservadas[0].denominacion»).
  problemas: Record<string, string>;
  // La superficie de cada área, medida por la API (D79); null mientras no se midió.
  superficies?: (number | null)[];
};

// Los datos de las áreas reservadas, R1, R2…: en el alta (CU03, figura 15) y en la vista del proyecto
// (D59). Cada una en una fila, con su código, a qué corresponde y su superficie; abajo, la clase y el destino.
export function FormularioAreas({ areas, datos, onCambio, problemas, superficies = [] }: Props) {
  return (
    <>
      {areas.length === 0 && <p className="texto-tenue">No hay áreas reservadas (son opcionales).</p>}
      {areas.map(({ id }, i) => {
        const area = datos[id] ?? AREA_VACIA;
        const cambiar = (campo: keyof DatosArea, valor: string) =>
          onCambio({ ...datos, [id]: { ...area, [campo]: valor } });
        const problema = (campo: string) => problemas[`areas_reservadas[${i}]${campo}`];
        const superficie = superficies[i];
        return (
          <div className={`fila-area ${problema("") ? "campo--error" : ""}`} key={id}>
            <div className="fila-area__principal">
              <span className="codigo-redondo codigo-redondo--area">R{i + 1}</span>
              <div className={`campo ${problema(".denominacion") ? "campo--error" : ""}`}>
                <label htmlFor={`area-${id}-denominacion`} className="oculto">
                  R{i + 1}: a qué corresponde
                </label>
                <input
                  id={`area-${id}-denominacion`}
                  value={area.denominacion}
                  placeholder="A qué corresponde: servidumbre, reserva…"
                  onChange={(e) => cambiar("denominacion", e.target.value)}
                />
              </div>
              {superficie != null && <span className="fila-area__dato">{metrosCuadrados(superficie)}</span>}
            </div>
            {problema("") && <p className="campo__problema">{problema("")}</p>}
            {problema(".denominacion") && <p className="campo__problema">{problema(".denominacion")}</p>}
            <div className="campos-dos fila-area__mas">
              <div className={`campo ${problema(".clase") ? "campo--error" : ""}`}>
                <label htmlFor={`area-${id}-clase`}>Clase (opcional)</label>
                <input id={`area-${id}-clase`} value={area.clase} onChange={(e) => cambiar("clase", e.target.value)} />
                {problema(".clase") && <p className="campo__problema">{problema(".clase")}</p>}
              </div>
              <div className={`campo ${problema(".destino") ? "campo--error" : ""}`}>
                <label htmlFor={`area-${id}-destino`}>Destino (opcional)</label>
                <input
                  id={`area-${id}-destino`}
                  value={area.destino}
                  onChange={(e) => cambiar("destino", e.target.value)}
                />
                {problema(".destino") && <p className="campo__problema">{problema(".destino")}</p>}
              </div>
            </div>
          </div>
        );
      })}
      {problemas.areas_reservadas && <p className="campo__problema">{problemas.areas_reservadas}</p>}
    </>
  );
}
