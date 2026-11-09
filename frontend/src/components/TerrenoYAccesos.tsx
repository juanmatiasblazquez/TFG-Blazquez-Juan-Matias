import L from "leaflet";
import { GeoJSON, Marker } from "react-leaflet";

import type { ProyectoOut } from "../api/proyectos";
import { ESTILO_RESERVADA, popupArea } from "./CapasAlternativa";
import { iconoAcceso } from "./iconos";

// El borde del terreno, continuo y en azul noche como en las figuras 15 a 21 (D73). La clase lo identifica
// para la skill verify (la sincronía de los mapas de la comparación).
export const ESTILO_TERRENO: L.PathOptions = { color: "#13293d", weight: 2.5, fill: false, className: "borde-terreno" };

type Props = {
  proyecto: ProyectoOut;
  // Las áreas reservadas del proyecto (D59). Con una versión en el mapa no van: la versión muestra las
  // suyas, las de su copia, que pueden ser otras si el proyecto las cambió.
  conAreas?: boolean;
};

// El borde del terreno y los accesos con su designación (A1, A2…), sobre el mapa del proyecto y
// sobre cada mapa de la comparación, y, si se pide, las áreas reservadas del proyecto (R1, R2…).
// Geoman los ignora (`pmIgnore`): al editar las áreas del proyecto, el terreno y los accesos no se mueven.
export function TerrenoYAccesos({ proyecto, conAreas = false }: Props) {
  return (
    <>
      <GeoJSON
        key={`terreno-${proyecto.id_proyecto}`}
        data={proyecto.terreno}
        style={ESTILO_TERRENO}
        interactive={false}
        pmIgnore
      />
      {conAreas && proyecto.areas_reservadas.features.length > 0 && (
        <GeoJSON
          key={`areas-${proyecto.id_proyecto}-${proyecto.areas_reservadas.features.map((f) => f.properties.id_area_reservada).join("-")}`}
          data={proyecto.areas_reservadas}
          style={ESTILO_RESERVADA}
          onEachFeature={popupArea}
          pmIgnore
        />
      )}
      {proyecto.accesos.features.map((acceso) => {
        const [lng, lat] = acceso.geometry.coordinates;
        return (
          <Marker
            key={acceso.properties.id_punto_acceso}
            position={[lat, lng]}
            icon={iconoAcceso(acceso.properties.designacion)}
            title={acceso.properties.via_vinculacion ?? undefined}
            pmIgnore
          />
        );
      })}
    </>
  );
}
