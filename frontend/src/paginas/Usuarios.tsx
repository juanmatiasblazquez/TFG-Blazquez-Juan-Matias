import { useState, type FormEvent } from "react";

import type { ErrorOut } from "../api/errores";
import {
  crearUsuario,
  desbloquear,
  listarBloqueadas,
  listarUsuarios,
  modificarUsuario,
  reactivarUsuario,
  reemplazarContrasena,
  type UsuarioIn,
  type UsuarioOut,
} from "../api/usuarios";
import { AvisoError } from "../components/AvisoError";
import { BarraPagina } from "../components/Marco";
import { fechaHora, minutos, nombreRol, ROLES } from "../formato";
import { useConsulta } from "../hooks/useConsulta";
import { useSesion } from "../hooks/useSesion";

const VACIO: UsuarioIn = { nombre: "", apellido: "", email: "", rol: "proyectista" };

// La contraseña temporal recién generada: se muestra una sola vez (CU02, paso 6; p. 53).
type Temporal = { usuario: string; contrasena: string; vence: string };

// CU02: la lista con el rol y el estado, el alta, la modificación de datos y rol, la baja (que nunca
// borra), la reactivación con una temporal nueva (D72) y la contraseña temporal para quien la olvidó. Y
// las direcciones bloqueadas por intentos fallidos, para destrabarlas (D72). Solo el director técnico
// (p. 54); las reglas (correo repetido, el último director técnico) las dice la API.
export function Usuarios() {
  const { puede, sesion } = useSesion();
  const usuarios = useConsulta(puede("gestionar_usuarios") ? "usuarios" : null, listarUsuarios);
  const bloqueadas = useConsulta(puede("gestionar_usuarios") ? "bloqueadas" : null, listarBloqueadas);
  const [alta, setAlta] = useState<UsuarioIn | null>(null);
  const [edicion, setEdicion] = useState<UsuarioOut | null>(null);
  const [temporal, setTemporal] = useState<Temporal | null>(null);
  const [error, setError] = useState<ErrorOut | null>(null);
  const [ocupado, setOcupado] = useState(false);

  if (!puede("gestionar_usuarios")) {
    return (
      <div className="pagina">
        <h2>Usuarios</h2>
        <p className="texto-tenue">Tu rol no permite gestionar usuarios: es del director técnico.</p>
      </div>
    );
  }

  const problemas = Object.fromEntries((error?.problemas ?? []).map((p) => [p.campo, p.mensaje]));

  async function hacer<T>(
    accion: () => Promise<{ ok: true; datos: T } | { ok: false; error: ErrorOut }>,
    alTerminar: (datos: T) => void,
  ) {
    setOcupado(true);
    setError(null);
    const resultado = await accion();
    setOcupado(false);
    if (resultado.ok) {
      alTerminar(resultado.datos);
      usuarios.recargar();
    } else {
      setError(resultado.error);
    }
  }

  function darDeAlta(evento: FormEvent) {
    evento.preventDefault();
    if (!alta) return;
    hacer(
      () => crearUsuario(alta),
      (creado) => {
        setAlta(null);
        setTemporal({
          usuario: `${creado.usuario.nombre} ${creado.usuario.apellido}`,
          contrasena: creado.contrasena_temporal,
          vence: creado.vence,
        });
      },
    );
  }

  function guardarEdicion(evento: FormEvent) {
    evento.preventDefault();
    if (!edicion) return;
    const { nombre, apellido, email, rol } = edicion;
    hacer(
      () => modificarUsuario(edicion.id_usuario, { nombre, apellido, email, rol }),
      () => setEdicion(null),
    );
  }

  // La baja es una modificación; la reactivación genera una temporal nueva, que se muestra una vez (D72).
  const cambiarEstado = (u: UsuarioOut) =>
    u.activo
      ? hacer(
          () => modificarUsuario(u.id_usuario, { activo: false }),
          () => {},
        )
      : hacer(
          () => reactivarUsuario(u.id_usuario),
          (r) =>
            setTemporal({ usuario: `${u.nombre} ${u.apellido}`, contrasena: r.contrasena_temporal, vence: r.vence }),
        );

  const destrabar = (direccion: string) =>
    hacer(
      () => desbloquear(direccion),
      () => bloqueadas.recargar(),
    );

  const nuevaTemporal = (u: UsuarioOut) =>
    hacer(
      () => reemplazarContrasena(u.id_usuario),
      (t) => setTemporal({ usuario: `${u.nombre} ${u.apellido}`, contrasena: t.contrasena_temporal, vence: t.vence }),
    );

  const formulario = (
    datos: UsuarioIn,
    cambiar: (d: UsuarioIn) => void,
    alEnviar: (e: FormEvent) => void,
    titulo: string,
    boton: string,
    cancelar: () => void,
  ) => (
    <form className="subformulario subformulario--usuario" onSubmit={alEnviar} aria-label={titulo}>
      <h3>{titulo}</h3>
      <div className="fila-campos">
        {(
          [
            ["nombre", "Nombre"],
            ["apellido", "Apellido"],
            ["email", "Correo"],
          ] as const
        ).map(([campo, etiqueta]) => (
          <div className={`campo ${problemas[campo] ? "campo--error" : ""}`} key={campo}>
            <label htmlFor={`usuario-${campo}`}>{etiqueta}</label>
            <input
              id={`usuario-${campo}`}
              value={datos[campo]}
              onChange={(e) => cambiar({ ...datos, [campo]: e.target.value })}
            />
            {problemas[campo] && <p className="campo__problema">{problemas[campo]}</p>}
          </div>
        ))}
        <div className={`campo ${problemas.rol ? "campo--error" : ""}`}>
          <label htmlFor="usuario-rol">Rol</label>
          <select id="usuario-rol" value={datos.rol} onChange={(e) => cambiar({ ...datos, rol: e.target.value })}>
            {ROLES.map(([codigo, nombre]) => (
              <option key={codigo} value={codigo}>
                {nombre}
              </option>
            ))}
          </select>
          {problemas.rol && <p className="campo__problema">{problemas.rol}</p>}
        </div>
      </div>
      <div className="acciones">
        <button type="submit" className="boton boton--primario" disabled={ocupado}>
          {boton}
        </button>
        <button type="button" className="boton" onClick={cancelar}>
          Cancelar
        </button>
      </div>
    </form>
  );

  return (
    <div className="vista">
      <BarraPagina
        titulo="Usuarios"
        acciones={
          !alta && (
            <button
              type="button"
              className="boton boton--primario"
              onClick={() => {
                setError(null);
                setEdicion(null);
                setAlta(VACIO);
              }}
            >
              Nuevo usuario
            </button>
          )
        }
      />
      <div className="vista__cuerpo vista__cuerpo--hoja">
        <p className="texto-tenue">
          Un usuario nunca se borra: al darlo de baja queda desactivado, y sus proyectos y versiones siguen diciendo
          quién los hizo. Al crearlo, o si olvidó su contraseña, el sistema genera una contraseña temporal que vale 24
          horas y se muestra una sola vez: entregásela y pedile que la cambie al entrar. Reactivar a alguien también le
          genera una temporal nueva.
        </p>

        {temporal && (
          <div className="aviso aviso--temporal" role="status">
            <p className="aviso__titulo">Contraseña temporal de {temporal.usuario}</p>
            <p className="temporal">
              <code>{temporal.contrasena}</code>
              <button
                type="button"
                className="boton"
                onClick={() => navigator.clipboard?.writeText(temporal.contrasena)}
              >
                Copiar
              </button>
            </p>
            <p>Vale hasta el {fechaHora(temporal.vence)}.</p>
            <p>
              Se muestra esta única vez: en la base queda solo su hash. Al entrar, el usuario la tiene que reemplazar
              por una propia.
            </p>
            <button type="button" className="boton" onClick={() => setTemporal(null)}>
              Listo, ya la entregué
            </button>
          </div>
        )}

        {error && <AvisoError error={error} titulo="No se pudo guardar" />}
        {alta && formulario(alta, setAlta, darDeAlta, "Nuevo usuario", "Dar de alta", () => setAlta(null))}
        {edicion &&
          formulario(
            edicion,
            (d) => setEdicion({ ...edicion, ...d }),
            guardarEdicion,
            `Modificar a ${edicion.nombre} ${edicion.apellido}`,
            "Guardar",
            () => setEdicion(null),
          )}

        {usuarios.error && <AvisoError error={usuarios.error} titulo="No se pudo leer la lista de usuarios" />}
        {usuarios.datos && (
          <table className="tabla">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Correo</th>
                <th>Rol</th>
                <th>Estado</th>
                <th>Alta</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {usuarios.datos.map((u) => {
                const yo = u.id_usuario === sesion?.usuario.id_usuario;
                return (
                  <tr key={u.id_usuario} className={u.activo ? "" : "fila--inactiva"}>
                    <td>
                      {u.apellido}, {u.nombre}
                      {yo && <span className="texto-tenue"> (vos)</span>}
                    </td>
                    <td>{u.email}</td>
                    <td>{nombreRol(u.rol)}</td>
                    <td>
                      <span className={`insignia ${u.activo ? "insignia--ok" : "insignia--error"}`}>
                        {u.activo ? "Activo" : "Desactivado"}
                      </span>
                      {u.activo && u.debe_cambiar_contrasena && u.vence_contrasena_temporal && (
                        <div className="texto-tenue">temporal hasta el {fechaHora(u.vence_contrasena_temporal)}</div>
                      )}
                    </td>
                    <td>{fechaHora(u.fecha_alta)}</td>
                    <td className="acciones-fila">
                      <button
                        type="button"
                        className="boton boton--chico"
                        onClick={() => {
                          setError(null);
                          setAlta(null);
                          setEdicion(u);
                        }}
                      >
                        Modificar
                      </button>
                      <button
                        type="button"
                        className="boton boton--chico"
                        disabled={ocupado}
                        onClick={() => cambiarEstado(u)}
                      >
                        {u.activo ? "Dar de baja" : "Reactivar"}
                      </button>
                      <button
                        type="button"
                        className="boton boton--chico"
                        disabled={ocupado}
                        onClick={() => nuevaTemporal(u)}
                      >
                        Contraseña temporal
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        <section className="bloqueadas" aria-label="Direcciones bloqueadas">
          <h3>Direcciones bloqueadas</h3>
          <p className="texto-tenue">
            Tras 10 intentos fallidos seguidos, el inicio de sesión desde esa dirección queda bloqueado 30 minutos. Si
            todo el estudio sale a internet por la misma dirección, el error de una persona deja afuera a todos: desde
            acá se destraba. Las sesiones abiertas no se cortan.
          </p>
          {bloqueadas.error && (
            <AvisoError error={bloqueadas.error} titulo="No se pudieron leer las direcciones bloqueadas" />
          )}
          {bloqueadas.datos && bloqueadas.datos.length === 0 && (
            <p className="texto-tenue">No hay direcciones bloqueadas.</p>
          )}
          {bloqueadas.datos && bloqueadas.datos.length > 0 && (
            <table className="tabla tabla--compacta">
              <thead>
                <tr>
                  <th>Dirección</th>
                  <th>Intentos fallidos</th>
                  <th>Bloqueada hasta</th>
                  <th>Le queda</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {bloqueadas.datos.map((b) => (
                  <tr key={b.direccion}>
                    <td>
                      <code>{b.direccion}</code>
                    </td>
                    <td>{b.intentos_fallidos}</td>
                    <td>{fechaHora(b.bloqueada_hasta)}</td>
                    <td>{minutos(b.segundos_restantes)}</td>
                    <td>
                      <button
                        type="button"
                        className="boton boton--chico"
                        disabled={ocupado}
                        onClick={() => destrabar(b.direccion)}
                      >
                        Desbloquear
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <button type="button" className="boton boton--chico" onClick={bloqueadas.recargar}>
            Actualizar
          </button>
        </section>
      </div>
    </div>
  );
}
