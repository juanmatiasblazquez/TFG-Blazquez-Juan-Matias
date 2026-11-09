import L from "leaflet";
import { useMemo, useState } from "react";

import { consultarAlternativaCompartida, consultarCompartido } from "../api/compartido";
import { AvisoError } from "../components/AvisoError";
import { RayadoFijado } from "../components/CapasAlternativa";
import { CapasCompartidas } from "../components/CapasCompartidas";
import { Logo, TarjetaSeccion } from "../components/Marco";
import { MapaBase } from "../components/MapaBase";
import { fecha, nombreRol, numero } from "../formato";
import { useConsulta } from "../hooks/useConsulta";

// Lo que ve el cliente por un enlace, sin cuenta (CU15; figura 21; D70, D71, D73).
//
// - El token sale del fragmento de la dirección (#/compartido/<token>) y viaja solo en el encabezado
//   `Authorization` de los pedidos a /api/compartido: no queda en ningún registro ni en un Referer.
// - Muestra los datos del proyecto y las alternativas compartidas (paso 3); al elegir una, su trazado, su
//   descripción y sus indicadores principales (paso 5). Solo lectura: no hay ningún control que modifique
//   nada.
// - Si el enlace venció o fue revocado, la API responde 410 y la página bloquea el ingreso (2.a).
export function VistaCompartida({ token }: { token: string }) {
  const compartido = useConsulta(`compartido`, (c) => consultarCompartido(token, c));
  const [elegida, setElegida] = useState<string | null>(null);
  const datos = compartido.datos;
  const codigo = elegida ?? datos?.alternativas[0] ?? null;
  const alternativa = useConsulta(codigo && `compartida:${codigo}`, (c) =>
    consultarAlternativaCompartida(token, codigo!, c),
  );
  const a = alternativa.datos;
  const encuadre = useMemo(() => (a ? L.geoJSON(a.capas.terreno).getBounds() : null), [a]);

  return (
    <div className="app">
      <header className="cabecera-cliente">
        <Logo color="#3b86d1" />
        <span className="cabecera-cliente__nombre">{datos?.estudio ?? "Sistema de trazados"}</span>
        <span className="insignia insignia--grande">Vista de solo lectura</span>
      </header>
      {compartido.cargando && <p className="pagina texto-tenue">Abriendo el enlace…</p>}
      {compartido.error && (
        <div className="pagina compartida__bloqueo">
          <AvisoError error={compartido.error} titulo="No se puede abrir este enlace" />
        </div>
      )}
      {datos && (
        <>
          <div className="subcabecera-cliente">
            <div>
              <p className="texto-tenue" style={{ margin: 0 }}>
                Propuesta de trazado para {datos.proyecto.cliente}
              </p>
              <h1>{datos.proyecto.nombre}</h1>
            </div>
            <div className="segmentado" role="group" aria-label="Alternativas compartidas">
              {datos.alternativas.map((c) => (
                <button
                  type="button"
                  key={c}
                  className={`segmentado__opcion ${c === codigo ? "segmentado__opcion--activa" : ""}`}
                  aria-pressed={c === codigo}
                  onClick={() => setElegida(c)}
                >
                  Alternativa {c}
                </button>
              ))}
            </div>
          </div>
          <main className="contenido">
            <div className="cliente">
              <div className="cliente__mapa">
                <RayadoFijado />
                <MapaBase encuadre={encuadre}>{a && <CapasCompartidas codigo={a.codigo} capas={a.capas} />}</MapaBase>
              </div>
              <aside className="cliente__panel">
                {alternativa.error && <AvisoError error={alternativa.error} titulo="No se pudo abrir la alternativa" />}
                {a && (
                  <section aria-label={`Alternativa ${a.codigo}`}>
                    <TarjetaSeccion titulo={`Alternativa ${a.codigo}`}>
                      {a.descripcion ? (
                        <p style={{ margin: 0, fontSize: "1.05rem" }}>{a.descripcion}</p>
                      ) : (
                        <p className="texto-tenue" style={{ margin: 0 }}>
                          {datos.proyecto.ubicacion ?? "Trazado propuesto por el estudio."}
                        </p>
                      )}
                    </TarjetaSeccion>
                    <div className="indicadores-cliente">
                      <Tarjeta titulo="Lotes" valor={numero(a.indicadores.cantidad_lotes, 0)} />
                      <Tarjeta
                        titulo="Superficie media de lote"
                        valor={
                          a.indicadores.superficie_media_lote_m2 === null
                            ? "—"
                            : numero(a.indicadores.superficie_media_lote_m2, 0)
                        }
                        unidad={a.indicadores.superficie_media_lote_m2 === null ? undefined : "m²"}
                      />
                      <Tarjeta
                        titulo="Superficie aprovechable"
                        valor={numero(a.indicadores.superficie_aprovechable_m2 / 10_000)}
                        unidad={`ha · ${numero(a.indicadores.porcentaje_aprovechamiento, 1)} %`}
                      />
                      <Tarjeta
                        titulo="Espacios verdes"
                        valor={
                          a.indicadores.superficie_espacio_verde_m2 === null
                            ? "—"
                            : numero(a.indicadores.superficie_espacio_verde_m2 / 10_000)
                        }
                        unidad={`ha · ${numero(a.indicadores.porcentaje_espacio_verde, 1)} %`}
                      />
                      <Tarjeta
                        titulo="Longitud de calles"
                        valor={numero(a.indicadores.longitud_red_m / 1000)}
                        unidad="km"
                      />
                      <Tarjeta
                        titulo="Superficie del terreno"
                        valor={numero(a.indicadores.superficie_terreno_m2 / 10_000)}
                        unidad="ha"
                      />
                    </div>
                    <p className="aviso aviso--info">
                      <span className="aviso__icono" aria-hidden="true">
                        i
                      </span>
                      <span>
                        Las superficies son aproximadas y quedan sujetas a la mensura y a la aprobación municipal
                        definitivas.
                      </span>
                    </p>
                  </section>
                )}
                <p className="texto-tenue">
                  Compartido por {datos.compartido_por.nombre}, {nombreRol(datos.compartido_por.rol).toLowerCase()}.
                  <br />
                  Enlace vigente hasta el {fecha(datos.vence)}.
                </p>
              </aside>
            </div>
          </main>
        </>
      )}
    </div>
  );
}

function Tarjeta({ titulo, valor, unidad }: { titulo: string; valor: string; unidad?: string }) {
  return (
    <div className="indicador-cliente">
      <span className="indicador-cliente__titulo">{titulo}</span>
      <span className="indicador-cliente__valor">
        {valor}
        {unidad && <span className="indicador-cliente__detalle"> {unidad}</span>}
      </span>
    </div>
  );
}
