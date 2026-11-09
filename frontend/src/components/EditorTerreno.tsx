// Leaflet-Geoman se engancha al `L` global que deja Leaflet: se importa después (D37).
import L from "leaflet";
import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";
import type { Point, Polygon } from "geojson";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import { useMap } from "react-leaflet";

import { ESTILO_RESERVADA } from "./CapasAlternativa";
import { iconoAcceso } from "./iconos";

// Un área reservada dibujada (CU04, paso 5; D59). `id` es estable mientras el área está en el mapa:
// con él la pantalla guarda su denominación, su clase y su destino aunque se borre otra.
export type AreaDibujada = { id: number; poligono: Polygon };
export type Dibujo = { terreno: Polygon | null; accesos: Point[]; areas: AreaDibujada[] };

// Las herramientas de «Herramientas de delimitación» (figura 15). Activar la que ya está activa la termina.
export type Herramienta = "terreno" | "rectangulo" | "acceso" | "area" | "editar" | "rotar" | "borrar";

export type ControlesEditor = {
  activar: (herramienta: Herramienta) => void;
  terminar: () => void;
  // El terreno importado de una planilla (D80): reemplaza al dibujado.
  cargarTerreno: (poligono: Polygon) => void;
};

type Props = {
  // Con las herramientas o sin ellas: lo dibujado se sigue viendo.
  habilitado: boolean;
  onCambio: (dibujo: Dibujo) => void;
  // Lo que había en el borrador (D81): se carga una vez, al montar.
  inicial?: Dibujo | null;
  // La denominación de cada área, en orden: «R1 · Servidumbre de electroducto».
  nombresAreas?: string[];
  onHerramienta?: (herramienta: Herramienta | null) => void;
};

// La herramienta de las áreas reservadas: una copia del polígono de Geoman con su nombre, así el
// `pm:create` dice si lo que se dibujó es el terreno o un área.
const HERRAMIENTA_AREA = "AreaReservada";
// Qué forma de Geoman dibuja cada herramienta.
const FORMAS: Partial<Record<Herramienta, string>> = {
  terreno: "Polygon",
  rectangulo: "Rectangle",
  acceso: "Marker",
  area: HERRAMIENTA_AREA,
};

// Textos de Geoman (RNF01): los de las ayudas mientras se dibuja.
const TEXTOS: L.PM.Translations = {
  tooltips: {
    placeMarker: "Hacé clic sobre el borde del terreno",
    firstVertex: "Hacé clic para poner el primer vértice",
    continueLine: "Hacé clic para seguir",
    finishPoly: "Hacé clic en el primer vértice para cerrar",
    finishRect: "Hacé clic para terminar",
  },
};

const ESTILO_TERRENO: L.PathOptions = { color: "#13293d", weight: 2.5, fillColor: "#ffffff", fillOpacity: 0.35 };

const aLatLngs = (poligono: Polygon) => poligono.coordinates[0].slice(0, -1).map(([x, y]) => L.latLng(y, x));

// El terreno como polígono libre, rectángulo o planilla importada, los accesos sobre su borde y las áreas
// reservadas de su interior (CU04, pasos 2 a 5). Las herramientas son los botones del panel (figura 15): la
// barra de Geoman no se muestra.
//
// - Un solo terreno: dibujar o importar otro reemplaza al anterior.
// - Los accesos se pegan al borde (snapping): el motor los quiere a menos de 1 cm del perímetro. Las
//   áreas también se pegan, así una contra el borde lo toca de verdad.
// - Nada se valida acá: lo mide y lo valida la API con las reglas del motor mientras se dibuja (D79), y de
//   nuevo al registrar (D37, D59).
export const EditorTerreno = forwardRef<ControlesEditor, Props>(function EditorTerreno(
  { habilitado, onCambio, inicial = null, nombresAreas = [], onHerramienta },
  ref,
) {
  const mapa = useMap();
  const avisar = useRef(onCambio);
  const avisarHerramienta = useRef(onHerramienta);
  const nombres = useRef(nombresAreas);
  const primero = useRef(inicial);
  const capas = useRef<{
    terreno: L.Polygon | null;
    accesos: L.Marker[];
    areas: L.Polygon[];
    agregar: (capa: L.Layer, forma: string) => void;
  } | null>(null);

  useEffect(() => {
    avisar.current = onCambio;
    avisarHerramienta.current = onHerramienta;
    nombres.current = nombresAreas;
  });

  useEffect(() => {
    mapa.pm.setLang("es", TEXTOS, "es");
    mapa.pm.setGlobalOptions({
      snappable: true,
      snapDistance: 25,
      allowSelfIntersection: true,
      pathOptions: ESTILO_TERRENO,
      markerStyle: { icon: iconoAcceso() },
    });
    // La herramienta de las áreas se crea una sola vez por mapa.
    const dibujos = mapa.pm.Draw as unknown as Record<string, L.PM.DrawShape | undefined>;
    if (!dibujos[HERRAMIENTA_AREA]) {
      const { drawInstance } = mapa.pm.Toolbar.copyDrawControl("Polygon", {
        name: HERRAMIENTA_AREA,
        block: "draw",
        title: "Área reservada",
        className: "control-icon leaflet-pm-icon-polygon icono-area-reservada",
      });
      drawInstance.setPathOptions(ESTILO_RESERVADA);
    }

    const estado = {
      terreno: null as L.Polygon | null,
      accesos: [] as L.Marker[],
      areas: [] as L.Polygon[],
      agregar: (capa: L.Layer, forma: string) => agregar(capa, forma),
    };
    capas.current = estado;

    const informar = () => {
      estado.areas.forEach((area, i) => area.setTooltipContent(rotuloArea(i, nombres.current[i])));
      avisar.current({
        terreno: estado.terreno && poligonoGeoJSON(estado.terreno),
        accesos: estado.accesos.map(puntoGeoJSON),
        areas: estado.areas.map((area) => ({ id: L.stamp(area), poligono: poligonoGeoJSON(area) })),
      });
    };

    function agregar(capa: L.Layer, forma: string) {
      if (capa instanceof L.Marker) {
        // El código va dentro del círculo azul, como en la figura 15.
        capa.setIcon(iconoAcceso(`A${estado.accesos.length + 1}`));
        capa.on("pm:edit", informar);
        estado.accesos.push(capa);
      } else if (capa instanceof L.Polygon && forma === HERRAMIENTA_AREA) {
        capa.setStyle(ESTILO_RESERVADA);
        // `setStyle` no aplica `className` a una capa que ya existe: el rayado va a mano (index.css).
        capa.getElement()?.classList.add("rayado-reservada");
        capa.bindTooltip(rotuloArea(estado.areas.length, nombres.current[estado.areas.length]), {
          permanent: true,
          direction: "center",
          className: "etiqueta-area",
        });
        capa.on("pm:edit", informar);
        capa.on("pm:rotateend", informar);
        estado.areas.push(capa);
      } else if (capa instanceof L.Polygon) {
        if (estado.terreno) mapa.removeLayer(estado.terreno);
        capa.setStyle(ESTILO_TERRENO);
        estado.terreno = capa;
        capa.on("pm:edit", informar);
        capa.on("pm:rotateend", informar);
      }
      informar();
    }

    const alCrear = ({ layer, shape }: { layer: L.Layer; shape: string }) => agregar(layer, shape);

    const alBorrar = ({ layer }: { layer: L.Layer }) => {
      if (layer === estado.terreno) estado.terreno = null;
      const indice = estado.accesos.indexOf(layer as L.Marker);
      if (indice >= 0) estado.accesos.splice(indice, 1);
      const area = estado.areas.indexOf(layer as L.Polygon);
      if (area >= 0) estado.areas.splice(area, 1);
      // Los accesos se renumeran: el ícono lleva el código.
      estado.accesos.forEach((acceso, i) => acceso.setIcon(iconoAcceso(`A${i + 1}`)));
      informar();
    };

    // Qué herramienta quedó activa, para resaltar su botón.
    const herramientaDe = (forma: string): Herramienta | null =>
      (Object.entries(FORMAS).find(([, f]) => f === forma)?.[0] as Herramienta | undefined) ?? null;
    const alEmpezar = ({ shape }: { shape: string }) => avisarHerramienta.current?.(herramientaDe(shape));
    const alTerminar = () => avisarHerramienta.current?.(null);
    const modo =
      (herramienta: Herramienta) =>
      ({ enabled }: { enabled: boolean }) =>
        avisarHerramienta.current?.(enabled ? herramienta : null);
    const alEditar = modo("editar");
    const alRotar = modo("rotar");
    const alQuitar = modo("borrar");

    mapa.on("pm:create", alCrear);
    mapa.on("pm:remove", alBorrar);
    mapa.on("pm:drawstart", alEmpezar);
    mapa.on("pm:drawend", alTerminar);
    mapa.on("pm:globaleditmodetoggled", alEditar);
    mapa.on("pm:globalrotatemodetoggled", alRotar);
    mapa.on("pm:globalremovalmodetoggled", alQuitar);

    // El borrador (D81): el terreno, los accesos y las áreas, como si se hubieran dibujado.
    const borrador = primero.current;
    if (borrador?.terreno) {
      agregar(L.polygon(aLatLngs(borrador.terreno)).addTo(mapa), "Polygon");
      borrador.accesos.forEach((p) =>
        agregar(L.marker([p.coordinates[1], p.coordinates[0]], { icon: iconoAcceso() }).addTo(mapa), "Marker"),
      );
      borrador.areas.forEach((a) => agregar(L.polygon(aLatLngs(a.poligono)).addTo(mapa), HERRAMIENTA_AREA));
      mapa.fitBounds(estado.terreno!.getBounds(), { padding: [40, 40], animate: false });
    }

    return () => {
      mapa.off("pm:create", alCrear);
      mapa.off("pm:remove", alBorrar);
      mapa.off("pm:drawstart", alEmpezar);
      mapa.off("pm:drawend", alTerminar);
      mapa.off("pm:globaleditmodetoggled", alEditar);
      mapa.off("pm:globalrotatemodetoggled", alRotar);
      mapa.off("pm:globalremovalmodetoggled", alQuitar);
      if (estado.terreno) mapa.removeLayer(estado.terreno);
      estado.accesos.forEach((acceso) => mapa.removeLayer(acceso));
      estado.areas.forEach((area) => mapa.removeLayer(area));
      capas.current = null;
    };
  }, [mapa]);

  // El nombre de cada área en su rótulo, a medida que se escribe.
  const claveNombres = nombresAreas.join("\u0000");
  useEffect(() => {
    capas.current?.areas.forEach((area, i) => area.setTooltipContent(rotuloArea(i, nombres.current[i])));
  }, [claveNombres]);

  const terminar = () => {
    mapa.pm.disableDraw();
    mapa.pm.disableGlobalEditMode();
    mapa.pm.disableGlobalRotateMode();
    mapa.pm.disableGlobalRemovalMode();
    avisarHerramienta.current?.(null);
  };

  useImperativeHandle(ref, () => ({
    activar: (herramienta) => {
      const activa =
        (FORMAS[herramienta] !== undefined && mapa.pm.Draw.getActiveShape() === FORMAS[herramienta]) ||
        (herramienta === "editar" && mapa.pm.globalEditModeEnabled()) ||
        (herramienta === "rotar" && mapa.pm.globalRotateModeEnabled()) ||
        (herramienta === "borrar" && mapa.pm.globalRemovalModeEnabled());
      terminar();
      if (activa) return;
      const forma = FORMAS[herramienta];
      if (forma) {
        mapa.pm.enableDraw(forma, forma === "Marker" ? { continueDrawing: true } : {});
      } else if (herramienta === "editar") {
        mapa.pm.enableGlobalEditMode();
      } else if (herramienta === "rotar") {
        mapa.pm.enableGlobalRotateMode();
      } else if (herramienta === "borrar") {
        mapa.pm.enableGlobalRemovalMode();
      }
    },
    terminar,
    cargarTerreno: (poligono) => {
      terminar();
      const capa = L.polygon(aLatLngs(poligono)).addTo(mapa);
      capas.current?.agregar(capa, "Polygon");
      mapa.fitBounds(capa.getBounds(), { padding: [40, 40], animate: false });
    },
  }));

  // Escape termina la herramienta activa.
  useEffect(() => {
    if (!habilitado) return;
    const alTeclear = (e: KeyboardEvent) => {
      if (e.key === "Escape") terminar();
    };
    document.addEventListener("keydown", alTeclear);
    return () => document.removeEventListener("keydown", alTeclear);
    // `terminar` solo usa el mapa.
  }, [habilitado]);

  // Al volver al paso del terreno, el mapa estuvo oculto: recalcula su tamaño. Al dejarlo, termina la
  // herramienta.
  useEffect(() => {
    if (habilitado) mapa.invalidateSize();
    else terminar();
  }, [mapa, habilitado]);

  return null;
});

function rotuloArea(indice: number, nombre?: string): string {
  return nombre?.trim() ? `R${indice + 1} · ${nombre.trim()}` : `R${indice + 1}`;
}

// GeoJSON a mano, con la precisión completa: `toGeoJSON()` redondea a 6 decimales (unos 10 cm)
// y un acceso pegado al borde dejaría de estar a menos de 1 cm del perímetro (D37). También lo usa
// el contorno del sector que se fija (CU09).
export function poligonoGeoJSON(capa: L.Polygon): Polygon {
  const anillo = (capa.getLatLngs()[0] as L.LatLng[]).map((p) => [p.lng, p.lat]);
  return { type: "Polygon", coordinates: [[...anillo, anillo[0]]] };
}

function puntoGeoJSON(marcador: L.Marker): Point {
  const { lng, lat } = marcador.getLatLng();
  return { type: "Point", coordinates: [lng, lat] };
}
