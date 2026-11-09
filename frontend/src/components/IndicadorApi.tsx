import { useEstadoApi, type EstadoApi } from "../hooks/useEstadoApi";

type Presentacion = { clase: string; texto: string; detalle: string };

function presentar(estado: EstadoApi): Presentacion {
  switch (estado.tipo) {
    case "verificando":
      return { clase: "verificando", texto: "Verificando la API…", detalle: "Consultando /api/health" };
    case "operativa":
      return {
        clase: "ok",
        texto: `API operativa · PostGIS ${estado.salud.postgis}`,
        detalle: `Base de datos accesible · motor ${estado.salud.motor}`,
      };
    case "degradada":
      return estado.salud.base === "caida"
        ? {
            clase: "degradada",
            texto: "La API no accede a la base de datos",
            detalle: "La API responde, pero PostgreSQL no",
          }
        : {
            clase: "degradada",
            texto: "PostGIS no está habilitado",
            detalle: "La base responde, pero falta la migración 0001",
          };
    case "sin-conexion":
      return {
        clase: "error",
        texto: "Sin conexión con la API",
        detalle: "No hubo respuesta de /api/health",
      };
  }
}

// Compacto, en la barra: solo el punto, con el texto en el `title` y para los lectores de pantalla. El
// texto entero va en el menú del usuario (D73).
export function IndicadorApi({ compacto = false }: { compacto?: boolean }) {
  const { clase, texto, detalle } = presentar(useEstadoApi());
  return (
    <div
      className={`indicador indicador--${clase} ${compacto ? "indicador--compacto" : ""}`}
      role="status"
      aria-live="polite"
      title={compacto ? `${texto} · ${detalle}` : detalle}
    >
      <span className="indicador__punto" aria-hidden="true" />
      {compacto ? <span className="solo-lectores">{texto}</span> : <span>{texto}</span>}
    </div>
  );
}
