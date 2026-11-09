import type { Feature, FeatureCollection, Geometry } from "geojson";
import L from "leaflet";
import { useEffect, useRef } from "react";
import { useMap } from "react-leaflet";

type Props<P> = {
  datos: FeatureCollection<Geometry, P>;
  // El texto de cada pieza, o null para no etiquetarla.
  texto: (feature: Feature<Geometry, P>) => string | null;
  clase: string;
  // Lo que tiene que medir la pieza en la pantalla, en píxeles, para que entre su etiqueta.
  ancho: number;
  alto: number;
  // Cambia cuando cambian los datos (la versión): react-leaflet no redibuja solo.
  clave: string;
};

// Etiquetas permanentes en el centro de cada pieza: los nombres de las manzanas (M1…) y «Espacio verde»
// (figuras 17 a 21; D73). Es presentación: una etiqueta se muestra solo si la pieza mide en la pantalla lo
// que la etiqueta, y se vuelve a ver al acercar.
export function EtiquetasMapa<P>({ datos, texto, clase, ancho, alto, clave }: Props<P>) {
  const mapa = useMap();
  const actual = useRef({ datos, texto, ancho, alto });
  actual.current = { datos, texto, ancho, alto };

  useEffect(() => {
    const { datos, texto, ancho, alto } = actual.current;
    const etiquetadas: L.Polygon[] = [];
    // Invisible, sin clics y fuera de Geoman: solo lleva las etiquetas.
    const grupo = L.geoJSON(datos, {
      style: { stroke: false, fill: false },
      interactive: false,
      pmIgnore: true,
    } as L.GeoJSONOptions);
    grupo.eachLayer((capa) => {
      const feature = (capa as L.Polygon & { feature: Feature<Geometry, P> }).feature;
      const etiqueta = texto(feature);
      if (!etiqueta) return;
      capa.bindTooltip(etiqueta, { permanent: true, direction: "center", className: clase, interactive: false });
      etiquetadas.push(capa as L.Polygon);
    });
    grupo.addTo(mapa);
    const actualizar = () => {
      for (const capa of etiquetadas) {
        const limites = capa.getBounds();
        const a = mapa.latLngToContainerPoint(limites.getNorthWest());
        const b = mapa.latLngToContainerPoint(limites.getSouthEast());
        if (Math.abs(b.x - a.x) >= ancho && Math.abs(b.y - a.y) >= alto) capa.openTooltip();
        else capa.closeTooltip();
      }
    };
    actualizar();
    mapa.on("zoomend", actualizar);
    return () => {
      mapa.off("zoomend", actualizar);
      grupo.remove();
    };
  }, [mapa, clave, clase]);

  return null;
}
