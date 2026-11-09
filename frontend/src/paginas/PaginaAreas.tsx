import L from "leaflet";
import { useMemo, useState } from "react";

import type { ErrorOut } from "../api/errores";
import { reemplazarAreas, type ProyectoOut } from "../api/proyectos";
import { AvisoError } from "../components/AvisoError";
import { RayadoFijado } from "../components/CapasAlternativa";
import { EditorAreas } from "../components/EditorAreas";
import type { AreaDibujada } from "../components/EditorTerreno";
import { AREA_VACIA, areasParaEnviar, FormularioAreas, type DatosArea } from "../components/FormularioAreas";
import { BarraPagina, TarjetaSeccion } from "../components/Marco";
import { MapaBase } from "../components/MapaBase";
import { TerrenoYAccesos } from "../components/TerrenoYAccesos";
import { hectareas } from "../formato";
import { rutas } from "../hooks/useRuta";
import { useSesion } from "../hooks/useSesion";

// Las áreas reservadas del proyecto (CU04, paso 5; D59): verlas y, el director técnico, editarlas. Las
// alternativas ya generadas no cambian: cada versión guarda las áreas con las que se generó.
export function PaginaAreas({ proyecto: p, recargar }: { proyecto: ProyectoOut; recargar: () => void }) {
  const { puede } = useSesion();
  const puedeRegistrar = puede("registrar_proyectos");
  const [editando, setEditando] = useState(false);
  // Las dibujadas y lo escrito de cada una, por el id de su capa.
  const [dibujadas, setDibujadas] = useState<(AreaDibujada & { inicial: number | null })[]>([]);
  const [datos, setDatos] = useState<Record<number, DatosArea>>({});
  const [error, setError] = useState<ErrorOut | null>(null);
  const [guardando, setGuardando] = useState(false);
  const encuadre = useMemo(() => L.geoJSON(p.terreno).getBounds(), [p]);
  const problemas = Object.fromEntries((error?.problemas ?? []).map((x) => [x.campo, x.mensaje]));

  // Las áreas que el editor trae del proyecto llegan con su id: sus datos salen de ahí hasta que se
  // escriba otra cosa.
  function cambiar(areas: (AreaDibujada & { inicial: number | null })[]) {
    setDibujadas(areas);
    setDatos((anteriores) => {
      const nuevos = { ...anteriores };
      for (const area of areas) {
        if (nuevos[area.id] || area.inicial === null) continue;
        const propiedades = p.areas_reservadas.features.find(
          (f) => f.properties.id_area_reservada === area.inicial,
        )?.properties;
        nuevos[area.id] = propiedades
          ? {
              denominacion: propiedades.denominacion,
              clase: propiedades.clase ?? "",
              destino: propiedades.destino ?? "",
            }
          : AREA_VACIA;
      }
      return nuevos;
    });
  }

  function dejarDeEditar() {
    setEditando(false);
    setError(null);
    setDibujadas([]);
    setDatos({});
  }

  async function guardar() {
    setGuardando(true);
    setError(null);
    const resultado = await reemplazarAreas(p.id_proyecto, areasParaEnviar(dibujadas, datos));
    setGuardando(false);
    if (resultado.ok) {
      dejarDeEditar();
      recargar();
    } else {
      setError(resultado.error);
    }
  }

  return (
    <div className="vista">
      <BarraPagina
        migas={[
          { texto: "Proyectos", href: rutas.proyectos },
          { texto: p.nombre, href: rutas.proyecto(p.id_proyecto) },
        ]}
        titulo={editando ? "Editar las áreas reservadas" : "Áreas reservadas"}
        acciones={
          puedeRegistrar &&
          (editando ? (
            <>
              <button type="button" className="boton" onClick={dejarDeEditar}>
                Cancelar
              </button>
              <button type="button" className="boton boton--primario" disabled={guardando} onClick={guardar}>
                {guardando ? "Guardando…" : "Guardar las áreas"}
              </button>
            </>
          ) : (
            <button type="button" className="boton" onClick={() => setEditando(true)}>
              Editar las áreas
            </button>
          ))
        }
      />
      <div className="vista__cuerpo">
        <div className="espacio">
          <aside className="panel">
            <TarjetaSeccion titulo="Qué son">
              <p style={{ margin: 0 }}>
                Lo que no se lotea: una servidumbre, una reserva. El motor las descuenta del terreno y les pone una
                calle alrededor. Cambiarlas no toca las alternativas ya generadas: cada versión guarda las áreas con las
                que se generó, y las nuevas se generan con estas.
              </p>
            </TarjetaSeccion>
            {!editando && (
              <TarjetaSeccion titulo={`Áreas del proyecto (${p.areas_reservadas.features.length})`}>
                {p.areas_reservadas.features.length === 0 && (
                  <p className="texto-tenue">El proyecto no tiene áreas reservadas.</p>
                )}
                <ul className="lista-versiones">
                  {p.areas_reservadas.features.map((f) => (
                    <li key={f.properties.id_area_reservada}>
                      <span>
                        <strong>{f.properties.designacion}</strong> {f.properties.denominacion}
                        {f.properties.clase && <span className="texto-tenue"> · {f.properties.clase}</span>}
                        {f.properties.destino && <span className="texto-tenue"> · {f.properties.destino}</span>}
                      </span>
                      <span className="texto-tenue">{hectareas(f.properties.superficie_m2)}</span>
                    </li>
                  ))}
                </ul>
                {!puedeRegistrar && <p className="texto-tenue">Editar las áreas es del director técnico (CU04).</p>}
              </TarjetaSeccion>
            )}
            {editando && (
              <>
                <p className="texto-tenue">
                  Con la barra del mapa: dibujá un área nueva, mové sus vértices, rotala o borrala. Al guardar, estas
                  áreas reemplazan a las que tenía el proyecto.
                </p>
                {error && <AvisoError error={error} titulo="No se guardaron las áreas" />}
                <FormularioAreas areas={dibujadas} datos={datos} onCambio={setDatos} problemas={problemas} />
              </>
            )}
          </aside>
          <div className="espacio__mapa">
            <RayadoFijado />
            <MapaBase encuadre={encuadre}>
              {/* Al editarlas, las áreas las dibuja el editor. */}
              <TerrenoYAccesos proyecto={p} conAreas={!editando} />
              {editando && (
                <EditorAreas
                  key={p.areas_reservadas.features.map((f) => f.properties.id_area_reservada).join("-")}
                  iniciales={p.areas_reservadas.features.map((f) => ({
                    idAreaReservada: f.properties.id_area_reservada,
                    poligono: f.geometry,
                  }))}
                  onCambio={cambiar}
                />
              )}
            </MapaBase>
          </div>
        </div>
      </div>
    </div>
  );
}
