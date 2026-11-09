// Leaflet-Geoman se engancha al `L` global que deja Leaflet: se importa después (D37).
import L from "leaflet";
import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";
import type { Polygon } from "geojson";
import { useEffect, useRef } from "react";
import { useMap } from "react-leaflet";

import { ESTILO_RESERVADA } from "./CapasAlternativa";
import { poligonoGeoJSON, type AreaDibujada } from "./EditorTerreno";

// Un área que ya tenía el proyecto: su polígono y su id (para recuperar su denominación, su clase y su
// destino en el formulario).
export type AreaInicial = { idAreaReservada: number; poligono: Polygon };

type Props = {
  iniciales: AreaInicial[];
  // Las áreas como quedan, en orden (R1, R2…), con el `id` de su capa; `inicial` es el id del área
  // del proyecto de la que sale, si sale de una.
  onCambio: (areas: (AreaDibujada & { inicial: number | null })[]) => void;
};

// Textos de la barra (RNF01): acá solo se dibujan, editan, rotan y borran áreas reservadas.
const TEXTOS: L.PM.Translations = {
  buttonTitles: {
    drawPolyButton: "Dibujar un área reservada dentro del terreno",
    editButton: "Mover vértices de un área",
    rotateButton: "Rotar un área",
    deleteButton: "Borrar un área",
  },
};

// Editar las áreas reservadas de un proyecto que ya existe (CU04, paso 5; D59), sobre el terreno y los
// accesos que dibuja `TerrenoYAccesos` (que Geoman ignora: `pmIgnore`). Nada se valida acá: si un área
// sale del terreno, pisa otra o toma un acceso, lo dice la API al guardar (D37).
export function EditorAreas({ iniciales, onCambio }: Props) {
  const mapa = useMap();
  const avisar = useRef(onCambio);
  const inicialesRef = useRef(iniciales);

  useEffect(() => {
    avisar.current = onCambio;
  });

  useEffect(() => {
    mapa.pm.setLang("es", TEXTOS, "es");
    mapa.pm.setGlobalOptions({ snappable: true, snapDistance: 25, allowSelfIntersection: true, pathOptions: ESTILO_RESERVADA });

    const areas: L.Polygon[] = [];
    const origen = new Map<number, number>();

    const informar = () => {
      areas.forEach((area, i) => area.setTooltipContent(`R${i + 1}`));
      avisar.current(
        areas.map((area) => ({ id: L.stamp(area), poligono: poligonoGeoJSON(area), inicial: origen.get(L.stamp(area)) ?? null })),
      );
    };

    const sumar = (capa: L.Polygon) => {
      capa.setStyle(ESTILO_RESERVADA);
      // `setStyle` no aplica `className` a una capa que ya existe: el rayado va a mano (index.css).
      capa.getElement()?.classList.add("rayado-reservada");
      capa.bindTooltip(`R${areas.length + 1}`, { permanent: true, direction: "center", className: "etiqueta-area" });
      capa.on("pm:edit", informar);
      capa.on("pm:rotateend", informar);
      areas.push(capa);
    };

    for (const { idAreaReservada, poligono } of inicialesRef.current) {
      const capa = L.polygon(
        poligono.coordinates[0].slice(0, -1).map(([lng, lat]) => [lat, lng] as L.LatLngTuple),
        ESTILO_RESERVADA,
      ).addTo(mapa);
      origen.set(L.stamp(capa), idAreaReservada);
      sumar(capa);
    }
    informar();

    const alCrear = ({ layer }: { layer: L.Layer }) => {
      if (layer instanceof L.Polygon) {
        sumar(layer);
        informar();
      }
    };
    const alBorrar = ({ layer }: { layer: L.Layer }) => {
      const indice = areas.indexOf(layer as L.Polygon);
      if (indice >= 0) areas.splice(indice, 1);
      informar();
    };

    mapa.on("pm:create", alCrear);
    mapa.on("pm:remove", alBorrar);
    mapa.pm.addControls({
      position: "topleft",
      drawPolygon: true,
      editMode: true,
      rotateMode: true,
      removalMode: true,
      drawMarker: false,
      drawRectangle: false,
      drawPolyline: false,
      drawCircle: false,
      drawCircleMarker: false,
      drawText: false,
      dragMode: false,
      cutPolygon: false,
    });
    return () => {
      mapa.off("pm:create", alCrear);
      mapa.off("pm:remove", alBorrar);
      mapa.pm.disableDraw();
      mapa.pm.disableGlobalEditMode();
      mapa.pm.disableGlobalRotateMode();
      mapa.pm.disableGlobalRemovalMode();
      mapa.pm.removeControls();
      areas.forEach((area) => mapa.removeLayer(area));
    };
  }, [mapa]);

  return null;
}
