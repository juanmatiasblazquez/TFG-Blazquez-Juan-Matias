import L from "leaflet";
import { useEffect } from "react";
import { useMap } from "react-leaflet";

import type { MedicionOut } from "../api/terrenos";
import { numero } from "../formato";

// Cuánto se separan los rótulos del borde, hacia afuera del terreno, en píxeles.
const SEPARACION_VERTICE = 14;
const SEPARACION_LADO = 11;

// V1, V2… en cada vértice y el largo de cada lado, a lo largo del lado y hacia afuera (figura 15). Los
// valores los mide la API en el sistema de cálculo (D79): acá solo se ubican en la pantalla. No son capas
// de Geoman (`pmIgnore`): no se mueven ni se borran con las herramientas.
export function RotulosTerreno({ medicion }: { medicion: MedicionOut | null }) {
  const mapa = useMap();

  useEffect(() => {
    if (!medicion || medicion.vertices.length < 3) return;
    const zoom = mapa.getZoom();
    // En la proyección del mapa los ángulos no cambian con el zoom: se calculan una vez.
    const pantalla = (posicion: [number, number]) => mapa.project(L.latLng(posicion[1], posicion[0]), zoom);
    const vertices = medicion.vertices.map((v) => pantalla(v.posicion));
    const centro = vertices.reduce((a, b) => a.add(b), L.point(0, 0)).divideBy(vertices.length);
    const grupo = L.layerGroup();

    medicion.vertices.forEach((v, k) => {
      const hacia = unitario(vertices[k].subtract(centro));
      grupo.addLayer(rotulo(v.posicion, v.designacion, hacia.multiplyBy(SEPARACION_VERTICE), 0, "rotulo-vertice"));
    });
    medicion.lados.forEach((lado, k) => {
      const a = vertices[k];
      const b = vertices[(k + 1) % vertices.length];
      const direccion = b.subtract(a);
      let angulo = (Math.atan2(direccion.y, direccion.x) * 180) / Math.PI;
      // Que se lea de izquierda a derecha.
      if (angulo > 90) angulo -= 180;
      if (angulo < -90) angulo += 180;
      const normal = unitario(L.point(-direccion.y, direccion.x));
      const medio = a.add(b).divideBy(2);
      const afuera =
        normal.x * (medio.x - centro.x) + normal.y * (medio.y - centro.y) >= 0 ? normal : normal.multiplyBy(-1);
      grupo.addLayer(
        rotulo(
          lado.punto_medio,
          `${numero(lado.largo_m)} m`,
          afuera.multiplyBy(SEPARACION_LADO),
          angulo,
          "rotulo-lado",
        ),
      );
    });
    grupo.addTo(mapa);
    return () => {
      grupo.remove();
    };
  }, [mapa, medicion]);

  return null;
}

function unitario(p: L.Point): L.Point {
  const largo = Math.hypot(p.x, p.y);
  return largo === 0 ? L.point(0, 0) : p.divideBy(largo);
}

function rotulo(
  posicion: [number, number],
  texto: string,
  desplazamiento: L.Point,
  angulo: number,
  clase: string,
): L.Marker {
  // El texto va como nodo, no como HTML.
  const contenido = document.createElement("span");
  contenido.className = clase;
  contenido.textContent = texto;
  contenido.style.transform = `translate(-50%, -50%) translate(${desplazamiento.x}px, ${desplazamiento.y}px) rotate(${angulo}deg)`;
  return L.marker(L.latLng(posicion[1], posicion[0]), {
    icon: L.divIcon({ className: "rotulo", html: contenido, iconSize: [0, 0] }),
    interactive: false,
    keyboard: false,
    pmIgnore: true,
  } as L.MarkerOptions);
}
