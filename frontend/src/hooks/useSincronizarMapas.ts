import type L from "leaflet";
import { useEffect, useState } from "react";
import { useMap } from "react-leaflet";

// Mapas que se mueven juntos (CU13, D54): mover o hacer zoom en uno lleva a los demás al mismo
// centro y zoom. Los mapas de la comparación tienen el mismo tamaño, así que muestran lo mismo.
// Sin Leaflet.Sync: son unas líneas, y no suma una dependencia.
export type GrupoMapas = { mapas: Set<L.Map>; copiando: boolean };

export function useGrupoMapas(): GrupoMapas {
  // Un objeto estable para toda la vida de la pantalla.
  const [grupo] = useState<GrupoMapas>(() => ({ mapas: new Set(), copiando: false }));
  return grupo;
}

// Se usa dentro de cada MapContainer del grupo.
export function useSincronizarMapa(grupo: GrupoMapas) {
  const mapa = useMap();
  useEffect(() => {
    grupo.mapas.add(mapa);
    const copiar = () => {
      // Mover los demás dispara su propio «move»: `copiando` corta el eco.
      if (grupo.copiando) return;
      grupo.copiando = true;
      try {
        for (const otro of grupo.mapas) {
          if (otro !== mapa) otro.setView(mapa.getCenter(), mapa.getZoom(), { animate: false });
        }
      } finally {
        grupo.copiando = false;
      }
    };
    mapa.on("move zoomend", copiar);
    return () => {
      mapa.off("move zoomend", copiar);
      grupo.mapas.delete(mapa);
    };
  }, [mapa, grupo]);
}
