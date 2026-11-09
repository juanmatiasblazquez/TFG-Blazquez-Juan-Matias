import L from "leaflet";

// El punto de acceso (A1, A2…): un círculo azul con su código adentro, como en las figuras 15 a 21 (D73).
// Es un DivIcon: el ícono por defecto de Leaflet busca imágenes por una ruta que el build de Vite no
// conserva. Sin código (al dibujarlo, antes de que tenga uno), un punto chico.
export function iconoAcceso(designacion?: string): L.DivIcon {
  if (!designacion) return L.divIcon({ className: "icono-acceso", iconSize: [14, 14], iconAnchor: [7, 7] });
  // El texto va como nodo, no como HTML.
  const texto = document.createElement("span");
  texto.textContent = designacion;
  return L.divIcon({ className: "icono-acceso", html: texto, iconSize: [26, 26], iconAnchor: [13, 13] });
}
