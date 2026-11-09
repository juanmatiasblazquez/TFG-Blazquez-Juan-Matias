import type { Geometry } from "geojson";

// Espejo de backend/app/schemas/errores.py (ErrorOut, ProblemaOut): si cambia uno, cambia el
// otro. Es el cuerpo de TODA respuesta de error de la API (D32).
export type ProblemaOut = {
  campo: string;
  mensaje: string;
};

export type ErrorOut = {
  causa: string;
  sugerencia: string | null;
  problemas: ProblemaOut[];
  // GeoJSON (EPSG:4326) de lo que falló, por ejemplo la parte de la red que no se conecta.
  geometria: Geometry | null;
};
