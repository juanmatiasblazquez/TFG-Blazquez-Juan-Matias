import { useState, type FormEvent } from "react";

import type { ErrorOut } from "../api/errores";
import { cambiarContrasena } from "../api/sesion";
import { AvisoError } from "../components/AvisoError";
import { rutas } from "../hooks/useRuta";
import { useSesion } from "../hooks/useSesion";

// Cambiar la contraseña (p. 53). Con una contraseña temporal es obligatorio: hasta hacerlo, la sesión
// no permite otra cosa (la API responde 403 a todo lo demás). Después, se puede usar cuando se quiera.
// La política la dice la API (`politica_contrasena`) y la valida ella: acá no hay una copia (D37).
// Que las dos nuevas coincidan sí se mira acá: es un error de tipeo, no una regla.
export function CambioContrasena({ obligatorio }: { obligatorio: boolean }) {
  const { sesion, entrar, salir } = useSesion();
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [repetida, setRepetida] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<ErrorOut | null>(null);
  const [listo, setListo] = useState(false);
  if (!sesion) return null;

  const distintas = repetida !== "" && nueva !== repetida;
  const problemas = Object.fromEntries((error?.problemas ?? []).map((p) => [p.campo, p.mensaje]));

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    if (distintas) return;
    setEnviando(true);
    setError(null);
    const resultado = await cambiarContrasena(actual, nueva);
    setEnviando(false);
    if (resultado.ok) {
      setListo(true);
      setActual("");
      setNueva("");
      setRepetida("");
      entrar(resultado.datos);
    } else {
      setError(resultado.error);
    }
  }

  return (
    <div className="pagina pagina--centrada">
      <form className="tarjeta" onSubmit={enviar} aria-label="Cambiar la contraseña">
        <h2>{obligatorio ? "Elegí tu contraseña" : "Cambiar la contraseña"}</h2>
        {obligatorio && (
          <p className="aviso aviso--info">
            Entraste con una contraseña temporal. Para seguir, reemplazala por una propia: hasta entonces la
            sesión no permite otra cosa.
          </p>
        )}
        {listo && !obligatorio && <p className="aviso aviso--ok">La contraseña se cambió. Las demás sesiones se cerraron.</p>}
        <p className="texto-tenue">{sesion.politica_contrasena}</p>
        {error && <AvisoError error={error} titulo="No se cambió la contraseña" />}
        <div className={`campo ${problemas.contrasena_actual ? "campo--error" : ""}`}>
          <label htmlFor="actual">{obligatorio ? "Contraseña temporal" : "Contraseña actual"}</label>
          <input
            id="actual"
            type="password"
            autoComplete="current-password"
            value={actual}
            onChange={(e) => setActual(e.target.value)}
            required
          />
          {problemas.contrasena_actual && <p className="campo__problema">{problemas.contrasena_actual}</p>}
        </div>
        <div className={`campo ${problemas.contrasena_nueva ? "campo--error" : ""}`}>
          <label htmlFor="nueva">Contraseña nueva</label>
          <input
            id="nueva"
            type="password"
            autoComplete="new-password"
            value={nueva}
            onChange={(e) => setNueva(e.target.value)}
            required
          />
          {problemas.contrasena_nueva && <p className="campo__problema">{problemas.contrasena_nueva}</p>}
        </div>
        <div className={`campo ${distintas ? "campo--error" : ""}`}>
          <label htmlFor="repetida">Repetí la contraseña nueva</label>
          <input
            id="repetida"
            type="password"
            autoComplete="new-password"
            value={repetida}
            onChange={(e) => setRepetida(e.target.value)}
            required
          />
          {distintas && <p className="campo__problema">No coincide con la contraseña nueva.</p>}
        </div>
        <div className="acciones acciones--pie">
          <button type="submit" className="boton boton--primario" disabled={enviando || distintas}>
            {enviando ? "Guardando…" : "Guardar la contraseña"}
          </button>
          {obligatorio ? (
            <button type="button" className="boton" onClick={salir}>
              Cerrar sesión
            </button>
          ) : (
            <a className="boton" href={rutas.proyectos}>
              Volver
            </a>
          )}
        </div>
      </form>
    </div>
  );
}
