import type { Geometry } from "geojson";
import L from "leaflet";
import { GeoJSON } from "react-leaflet";

import { COLORES } from "./CapasAlternativa";

const ESTILO_ERROR: L.PathOptions = { color: COLORES.incumplimiento, weight: 4, fillOpacity: 0.25 };

// Lo que la API marcó en un error (D32): la parte de la red que no se conecta, lo que sale del terreno.
// `clave` cambia en cada intento: react-leaflet no redibuja si cambian los datos.
export function GeometriaError({
  geometria,
  clave,
}: {
  geometria: Geometry | null | undefined;
  clave: string | number;
}) {
  if (!geometria) return null;
  return (
    <GeoJSON
      key={`error-${clave}`}
      data={geometria}
      style={ESTILO_ERROR}
      pointToLayer={(_, latlng) => L.circleMarker(latlng, { ...ESTILO_ERROR, radius: 8 })}
    />
  );
}
