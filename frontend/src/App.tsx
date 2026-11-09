import { BarraSuperior } from "./components/Marco";
import { useRuta, rutas } from "./hooks/useRuta";
import { ProveedorSesion, useSesion } from "./hooks/useSesion";
import { CambioContrasena } from "./paginas/CambioContrasena";
import { Comparacion } from "./paginas/Comparacion";
import { InicioSesion } from "./paginas/InicioSesion";
import { ListaProyectos } from "./paginas/ListaProyectos";
import { NuevoProyecto } from "./paginas/NuevoProyecto";
import { Usuarios } from "./paginas/Usuarios";
import { VistaCompartida } from "./paginas/VistaCompartida";
import { VistaProyecto } from "./paginas/VistaProyecto";

export function App() {
  const ruta = useRuta();
  // Lo que ve el cliente por un enlace (CU15): sin sesión, sin inicio de sesión y sin el menú del
  // estudio. No pasa por `ProveedorSesion`, que pediría la sesión al abrir (D70, D71).
  if (ruta.pagina === "compartido") return <VistaCompartida key={ruta.token} token={ruta.token} />;
  return (
    <ProveedorSesion>
      <Portal />
    </ProveedorSesion>
  );
}

// Antes de cualquier pantalla, la sesión (D63): sin sesión, el inicio de sesión (CU01); con una
// contraseña temporal, el cambio obligatorio (p. 53). Lo que el rol no puede hacer se oculta en cada
// pantalla con `puede`, pero quien decide es la API (D37).
function Portal() {
  const { estado, sesion, minutosRestantes } = useSesion();
  const ruta = useRuta();

  let contenido;
  if (estado.tipo === "cargando") {
    contenido = <p className="pagina texto-tenue">Cargando…</p>;
  } else if (estado.tipo === "sin-sesion") {
    contenido = <InicioSesion aviso={estado.aviso} />;
  } else if (sesion?.debe_cambiar_contrasena) {
    contenido = <CambioContrasena obligatorio />;
  } else {
    contenido = (
      <>
        {ruta.pagina === "proyectos" && <ListaProyectos />}
        {ruta.pagina === "nuevo" && <NuevoProyecto />}
        {ruta.pagina === "usuarios" && <Usuarios />}
        {ruta.pagina === "contrasena" && <CambioContrasena obligatorio={false} />}
        {ruta.pagina === "proyecto" && (
          // La `key` descarta el estado de un proyecto al abrir otro.
          <VistaProyecto key={ruta.id} ruta={ruta} />
        )}
        {ruta.pagina === "comparacion" && (
          // CU13. La `key` descarta los mapas de otro proyecto.
          <Comparacion key={ruta.id} id={ruta.id} codigos={ruta.codigos} />
        )}
        {ruta.pagina === "no-encontrada" && (
          <div className="pagina">
            <p>No existe esta pantalla.</p>
            <a href={rutas.proyectos}>Ir a la lista de proyectos</a>
          </div>
        )}
      </>
    );
  }

  return (
    <div className="app">
      <BarraSuperior />
      {minutosRestantes !== null && !sesion?.debe_cambiar_contrasena && (
        <div className="aviso-vencimiento" role="status">
          Tu sesión vence en {minutosRestantes === 1 ? "1 minuto" : `${minutosRestantes} minutos`}: guardá lo que estés
          haciendo. Después vas a tener que volver a iniciar sesión.
        </div>
      )}
      <main className="contenido">{contenido}</main>
    </div>
  );
}
