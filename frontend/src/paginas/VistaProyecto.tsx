import { consultarProyecto } from "../api/proyectos";
import { AvisoError } from "../components/AvisoError";
import { BarraPagina } from "../components/Marco";
import { useConsulta } from "../hooks/useConsulta";
import { rutas, type RutaProyecto } from "../hooks/useRuta";
import { PaginaAreas } from "./PaginaAreas";
import { PaginaCompartir } from "./PaginaCompartir";
import { PaginaParametros } from "./PaginaParametros";
import { PaginaProyecto } from "./PaginaProyecto";
import { VistaAlternativa } from "./VistaAlternativa";

// Un proyecto y sus secciones (D73): la página del proyecto (`#/proyectos/7`), cada alternativa con sus
// versiones y sus observaciones (figuras 17 a 19), los parámetros (figura 16), las áreas reservadas
// (D59) y lo compartido con el cliente (CU14). El proyecto se lee una vez acá y cada página lo recibe.
export function VistaProyecto({ ruta }: { ruta: RutaProyecto }) {
  const proyecto = useConsulta(`proyecto:${ruta.id}`, (c) => consultarProyecto(ruta.id, c));
  const p = proyecto.datos;

  if (proyecto.error) {
    return (
      <div className="vista">
        <BarraPagina migas={[{ texto: "Proyectos", href: rutas.proyectos }]} titulo="Proyecto" />
        <div className="vista__cuerpo vista__cuerpo--hoja">
          <AvisoError error={proyecto.error} titulo="No se pudo abrir el proyecto" />
          <a href={rutas.proyectos}>Volver a la lista</a>
        </div>
      </div>
    );
  }
  if (!p) return <p className="pagina texto-tenue">Cargando el proyecto…</p>;

  switch (ruta.seccion) {
    case "resumen":
      return <PaginaProyecto proyecto={p} recargar={proyecto.recargar} />;
    case "alternativas":
      return (
        <VistaAlternativa
          // Otra alternativa, otro estado (la versión pedida, el modo «Fijar sectores»).
          key={ruta.alternativa}
          proyecto={p}
          recargarProyecto={proyecto.recargar}
          codigo={ruta.alternativa}
          numeroVersion={ruta.version}
          pestana={ruta.pestana}
        />
      );
    case "parametros":
      return <PaginaParametros proyecto={p} recargar={proyecto.recargar} />;
    case "areas":
      return <PaginaAreas proyecto={p} recargar={proyecto.recargar} />;
    case "compartir":
      return <PaginaCompartir proyecto={p} recargar={proyecto.recargar} />;
  }
}
