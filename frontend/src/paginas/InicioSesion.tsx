import { useState, type FormEvent } from "react";

import type { ErrorOut } from "../api/errores";
import { iniciarSesion } from "../api/sesion";
import { AvisoError } from "../components/AvisoError";
import { useSesion } from "../hooks/useSesion";

// CU01: correo y contraseña. Lo que responde la API se muestra tal cual (D32): el mensaje genérico
// si no coinciden (4.a), y el bloqueo o el límite por minuto con la hora en que se puede volver a
// probar (4.b). La dirección no cambia: después de entrar se sigue donde se estaba.
export function InicioSesion({ aviso }: { aviso: string | null }) {
  const { entrar } = useSesion();
  const [email, setEmail] = useState("");
  const [contrasena, setContrasena] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<ErrorOut | null>(null);

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setEnviando(true);
    setError(null);
    const resultado = await iniciarSesion(email, contrasena);
    setEnviando(false);
    if (resultado.ok) {
      entrar(resultado.datos);
    } else {
      setContrasena("");
      setError(resultado.error);
    }
  }

  return (
    <div className="pagina pagina--centrada">
      <form className="tarjeta" onSubmit={enviar} aria-label="Iniciar sesión">
        <h2>Iniciar sesión</h2>
        {aviso && !error && <p className="aviso aviso--info">{aviso}</p>}
        {error && (
          <AvisoError
            error={error}
            titulo={error.causa.startsWith("Se bloqueó") || error.causa.startsWith("Demasiadas") ? "Acceso bloqueado" : undefined}
          />
        )}
        <div className="campo">
          <label htmlFor="email">Correo</label>
          <input
            id="email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div className="campo">
          <label htmlFor="contrasena">Contraseña</label>
          <input
            id="contrasena"
            type="password"
            autoComplete="current-password"
            value={contrasena}
            onChange={(e) => setContrasena(e.target.value)}
            required
          />
        </div>
        <div className="acciones acciones--pie">
          <button type="submit" className="boton boton--primario" disabled={enviando}>
            {enviando ? "Entrando…" : "Entrar"}
          </button>
        </div>
        <p className="texto-tenue">
          ¿Olvidaste la contraseña? Pedile al director técnico del estudio una contraseña temporal.
        </p>
      </form>
    </div>
  );
}
