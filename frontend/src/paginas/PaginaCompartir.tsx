import type { ProyectoOut } from "../api/proyectos";
import { CompartirAlternativas } from "../components/CompartirAlternativas";
import { BarraPagina } from "../components/Marco";
import { rutas } from "../hooks/useRuta";

// Compartir con el cliente (CU14; D70): la selección, el enlace y la lista de enlaces del proyecto.
export function PaginaCompartir({ proyecto: p, recargar }: { proyecto: ProyectoOut; recargar: () => void }) {
  return (
    <div className="vista">
      <BarraPagina
        migas={[
          { texto: "Proyectos", href: rutas.proyectos },
          { texto: p.nombre, href: rutas.proyecto(p.id_proyecto) },
        ]}
        titulo="Compartir con el cliente"
        acciones={
          p.alternativas.length >= 2 && (
            <a className="boton" href={rutas.comparacion(p.id_proyecto, [])}>
              Comparar
            </a>
          )
        }
      />
      <div className="vista__cuerpo vista__cuerpo--hoja">
        <div className="tarjeta-seccion" style={{ maxWidth: "62rem" }}>
          <CompartirAlternativas proyecto={p} onCambio={recargar} />
        </div>
      </div>
    </div>
  );
}
