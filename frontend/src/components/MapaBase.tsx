import type { LatLngBoundsExpression } from "leaflet";
import { useEffect, type ReactNode } from "react";
import { MapContainer, ScaleControl, TileLayer, ZoomControl, useMap } from "react-leaflet";

// Centro de la ciudad de Córdoba: el ámbito de la organización modelada (p. 15 del documento).
const CENTRO_CORDOBA: [number, number] = [-31.4167, -64.1833];
const ZOOM_INICIAL = 13;

// Cartografía base de OpenStreetMap (diagrama de despliegue, p. 52). La atribución es
// obligatoria por la licencia ODbL de los datos. La base se atenúa con CSS (`.mapa`), como en las
// figuras 15 a 21: lo que importa es el trazado (D73).
const URL_TESELAS = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATRIBUCION = '&copy; <a href="https://www.openstreetmap.org/copyright">colaboradores de OpenStreetMap</a>';

type Props = {
  children?: ReactNode;
  // Lo que el mapa encuadra al abrirse, por ejemplo el terreno del proyecto.
  encuadre?: LatLngBoundsExpression | null;
  // Si cambia, vuelve a encuadrar aunque el encuadre sea el mismo (otra pestaña del proyecto).
  claveEncuadre?: string;
  // El norte arriba a la derecha y los botones de zoom: no van en los mapas chicos de la comparación.
  norte?: boolean;
  zoom?: boolean;
  // La escala abajo a la izquierda: tampoco va en los mapas chicos.
  escala?: boolean;
  // El margen del encuadre, en píxeles (el panel de capas tapa la esquina de arriba a la izquierda).
  margen?: number;
};

export function MapaBase({
  children,
  encuadre,
  claveEncuadre = "",
  norte = true,
  zoom = true,
  escala = true,
  margen = 28,
}: Props) {
  return (
    <>
      {/* Zoom fraccionario al encuadrar: el terreno llena el mapa, como en las figuras. Los botones siguen
          de a un nivel. */}
      <MapContainer center={CENTRO_CORDOBA} zoom={ZOOM_INICIAL} zoomControl={false} zoomSnap={0.25} className="mapa">
        <TileLayer url={URL_TESELAS} attribution={ATRIBUCION} maxZoom={19} />
        {/* Controles con textos en español (RNF01): el de Leaflet por defecto dice "Zoom in". */}
        {zoom && <ZoomControl position="topleft" zoomInTitle="Acercar" zoomOutTitle="Alejar" />}
        {escala && <ScaleControl position="bottomleft" imperial={false} />}
        {encuadre && <Encuadrar limites={encuadre} clave={claveEncuadre} margen={margen} />}
        {children}
      </MapContainer>
      {norte && <Norte />}
    </>
  );
}

function Encuadrar({
  limites,
  clave: otra,
  margen,
}: {
  limites: LatLngBoundsExpression;
  clave: string;
  margen: number;
}) {
  const mapa = useMap();
  // Se encuadra cuando cambian los límites (por eso la clave), no en cada render.
  const clave = JSON.stringify(limites) + otra;
  // Sin animación: si la pantalla cambia durante una, el temporizador de Leaflet corre sobre un mapa ya
  // desmontado («_leaflet_pos»).
  useEffect(() => {
    mapa.fitBounds(limites, { padding: [margen, margen], animate: false });
  }, [mapa, clave]);
  return null;
}

// El norte, arriba a la derecha. El mapa nunca rota: es solo una referencia, como en las figuras.
function Norte() {
  return (
    <div className="sobre-mapa norte" aria-label="Norte arriba">
      <span>N</span>
      <span className="norte__circulo">
        <svg width="16" height="22" viewBox="0 0 16 22" aria-hidden="true" focusable="false">
          <path d="M8 1 L15 21 L8 16 L1 21 Z" fill="#13293d" />
        </svg>
      </span>
    </div>
  );
}
