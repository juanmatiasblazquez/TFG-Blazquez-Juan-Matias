import type { Feature, Geometry } from "geojson";
import L from "leaflet";
import { GeoJSON } from "react-leaflet";

import type { CapasCompartidasOut } from "../api/compartido";
import { COLORES, ESTILO_RESERVADA } from "./CapasAlternativa";
import { EtiquetasMapa } from "./EtiquetasMapa";
import { iconoAcceso } from "./iconos";
import { ESTILO_TERRENO } from "./TerrenoYAccesos";

// El trazado que ve el cliente (CU15, paso 5; figura 21): calles, lotes, espacios verdes y libres, las
// manzanas con su nombre y las áreas reservadas (RF14), con los colores del estudio (D73). Sin control de
// capas, como en la figura; sin incumplimientos, sin ejes ni nodos y sin popups de medidas: solo lo que el
// CU15 menciona (D70).

const ESTILO_CALLE: L.PathOptions = {
  color: COLORES.bordeCalle,
  weight: 0.5,
  fillColor: COLORES.calle,
  fillOpacity: 1,
  interactive: false,
};
const ESTILO_LOTE: L.PathOptions = {
  color: COLORES.bordeLote,
  weight: 0.7,
  fillColor: COLORES.loteCumple,
  fillOpacity: 1,
};
const ESTILO_VERDE: L.PathOptions = {
  color: COLORES.bordeVerde,
  weight: 1,
  fillColor: COLORES.espacioVerde,
  fillOpacity: 1,
};
const ESTILO_LIBRE: L.PathOptions = {
  color: COLORES.bordeLibre,
  weight: 0.8,
  fillColor: COLORES.espacioLibre,
  fillOpacity: 1,
};

type CeldaCompartida = Feature<Geometry, { designacion: string; tipo: string }>;
const deTipo = (tipo: string) => (f: CeldaCompartida) => f.properties.tipo === tipo;
// Solo las manzanas con lotes llevan su nombre («M3-L07» es de la M3): una manzana entera de verde lleva
// «Espacio verde», como en la figura 21.
function nombresDeManzanas(capas: CapasCompartidasOut) {
  const conLotes = new Set(
    capas.celdas.features.filter((f) => f.properties.tipo === "lote").map((f) => f.properties.designacion.split("-")[0]),
  );
  return (f: Feature<Geometry, { designacion: string }>) => (conLotes.has(f.properties.designacion) ? f.properties.designacion : null);
}
const textoVerde = (f: CeldaCompartida) => (f.properties.tipo === "espacio_verde" ? "Espacio verde" : null);

export function CapasCompartidas({ codigo, capas }: { codigo: string; capas: CapasCompartidasOut }) {
  return (
    <>
      <GeoJSON key={`calles-${codigo}`} data={capas.calles} style={ESTILO_CALLE} />
      <GeoJSON
        key={`lotes-${codigo}`}
        data={capas.celdas}
        filter={deTipo("lote")}
        style={ESTILO_LOTE}
        onEachFeature={(f: CeldaCompartida, capa) =>
          capa.bindTooltip(`Lote ${f.properties.designacion}`, { sticky: true })
        }
      />
      <GeoJSON
        key={`verde-${codigo}`}
        data={capas.celdas}
        filter={deTipo("espacio_verde")}
        style={ESTILO_VERDE}
        interactive={false}
      />
      <GeoJSON
        key={`libre-${codigo}`}
        data={capas.celdas}
        filter={deTipo("espacio_libre")}
        style={ESTILO_LIBRE}
        interactive={false}
      />
      {capas.areas_reservadas.features.length > 0 && (
        <GeoJSON
          key={`reservadas-${codigo}`}
          data={capas.areas_reservadas}
          style={ESTILO_RESERVADA}
          onEachFeature={(f: Feature<Geometry, { designacion: string; denominacion: string }>, capa) =>
            capa.bindTooltip(`${f.properties.designacion}: ${f.properties.denominacion}`, { sticky: true })
          }
        />
      )}
      <EtiquetasMapa
        clave={`manzanas-${codigo}`}
        datos={capas.manzanas}
        texto={nombresDeManzanas(capas)}
        clase="etiqueta-manzana"
        ancho={28}
        alto={16}
      />
      <EtiquetasMapa
        clave={`verde-${codigo}`}
        datos={capas.celdas}
        texto={textoVerde}
        clase="etiqueta-verde"
        ancho={90}
        alto={22}
      />
      <GeoJSON key={`terreno-${codigo}`} data={capas.terreno} style={{ ...ESTILO_TERRENO, interactive: false }} />
      <GeoJSON
        key={`accesos-${codigo}`}
        data={capas.accesos}
        pointToLayer={(f: Feature<Geometry, { designacion: string }>, latlng) =>
          L.marker(latlng, { icon: iconoAcceso(f.properties.designacion), interactive: false })
        }
      />
    </>
  );
}
