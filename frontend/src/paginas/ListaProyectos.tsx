import { listarProyectos } from "../api/proyectos";
import { AvisoError } from "../components/AvisoError";
import { BarraPagina } from "../components/Marco";
import { estado, fechaHora, hectareas, tipoProyecto } from "../formato";
import { useConsulta } from "../hooks/useConsulta";
import { rutas } from "../hooks/useRuta";
import { useSesion } from "../hooks/useSesion";

// Pantalla 1: los proyectos del estudio, del más nuevo al más viejo.
export function ListaProyectos() {
  const { datos: proyectos, error, cargando } = useConsulta("proyectos", listarProyectos);
  const { puede } = useSesion();

  return (
    <div className="vista">
      <BarraPagina
        titulo="Proyectos"
        acciones={
          // Registrar proyectos es del director técnico (p. 54).
          puede("registrar_proyectos") && (
            <a className="boton boton--primario" href={rutas.nuevo}>
              + Nuevo proyecto
            </a>
          )
        }
      />
      <div className="vista__cuerpo vista__cuerpo--hoja">
        {cargando && <p className="texto-tenue">Cargando proyectos…</p>}
        {error && <AvisoError error={error} titulo="No se pudo leer la lista de proyectos" />}
        {proyectos && proyectos.length === 0 && (
          <p className="texto-tenue">
            Todavía no hay proyectos.{puede("registrar_proyectos") && " Creá el primero con «+ Nuevo proyecto»."}
          </p>
        )}
        {proyectos && proyectos.length > 0 && (
          <div className="tarjeta-seccion tarjeta-tabla">
            <table className="tabla">
              <thead>
                <tr>
                  <th>Código</th>
                  <th>Nombre</th>
                  <th>Cliente</th>
                  <th>Tipo</th>
                  <th>Estado</th>
                  <th className="numero">Superficie</th>
                  <th className="numero">Alternativas</th>
                  <th>Creado</th>
                </tr>
              </thead>
              <tbody>
                {proyectos.map((p) => (
                  <tr key={p.id_proyecto}>
                    <td>
                      <a href={rutas.proyecto(p.id_proyecto)}>{p.codigo}</a>
                    </td>
                    <td>{p.nombre}</td>
                    <td>{p.cliente.razon_social}</td>
                    <td>{tipoProyecto(p.tipo)}</td>
                    <td>{estado(p.estado)}</td>
                    <td className="numero">{hectareas(p.superficie_m2)}</td>
                    <td className="numero">{p.cantidad_alternativas}</td>
                    <td>{fechaHora(p.fecha_creacion)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
