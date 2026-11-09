import { useEffect, useRef, useState, type ReactNode } from "react";

import { nombreRol } from "../formato";
import { rutas, useRuta } from "../hooks/useRuta";
import { useSesion } from "../hooks/useSesion";
import { IndicadorApi } from "./IndicadorApi";

// El marco del portal, como en los prototipos de las p. 48 a 51 (D73): la barra superior azul noche
// (el ícono, «Sistema de trazados», el estudio, las secciones y el usuario) y la barra de cada página
// (las migas, el título, las insignias y las acciones).

// El ícono del sistema: una manzana partida en lotes, sobre una grilla en perspectiva.
export function Logo({ tamano = 30, color = "#5aa2e6" }: { tamano?: number; color?: string }) {
  return (
    <svg className="logo" width={tamano} height={tamano} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <path d="M5 8 L25 5 L28 25 L8 28 Z" fill="none" stroke={color} strokeWidth="2.2" strokeLinejoin="round" />
      <path
        d="M11.7 7 L14.8 26.9 M18.4 6 L21.4 25.9 M6.5 15 L26.4 12.2 M7.5 21.4 L27.3 18.5"
        stroke={color}
        strokeWidth="1.6"
      />
    </svg>
  );
}

type PropsDesplegable = {
  // Lo que muestra el botón.
  etiqueta: ReactNode;
  claseBoton?: string;
  titulo?: string;
  alineacion?: "izquierda" | "derecha";
  // El contenido del menú; `cerrar` lo cierra (al elegir algo).
  children: (cerrar: () => void) => ReactNode;
};

// Un menú que se abre con un botón y se cierra al elegir, al hacer clic afuera o con Escape.
export function Desplegable({
  etiqueta,
  claseBoton = "boton",
  titulo,
  alineacion = "izquierda",
  children,
}: PropsDesplegable) {
  const [abierto, setAbierto] = useState(false);
  const raiz = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!abierto) return;
    const alHacerClic = (e: MouseEvent) => {
      if (raiz.current && !raiz.current.contains(e.target as Node)) setAbierto(false);
    };
    const alTeclear = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAbierto(false);
    };
    document.addEventListener("mousedown", alHacerClic);
    document.addEventListener("keydown", alTeclear);
    return () => {
      document.removeEventListener("mousedown", alHacerClic);
      document.removeEventListener("keydown", alTeclear);
    };
  }, [abierto]);
  return (
    <div className="desplegable" ref={raiz}>
      <button
        type="button"
        className={claseBoton}
        aria-haspopup="menu"
        aria-expanded={abierto}
        title={titulo}
        onClick={() => setAbierto((a) => !a)}
      >
        {etiqueta}
      </button>
      {abierto && (
        <div className={`desplegable__menu desplegable__menu--${alineacion}`} role="menu">
          {children(() => setAbierto(false))}
        </div>
      )}
    </div>
  );
}

// «J. Blazquez»: la inicial del nombre y el apellido, como en la barra de los prototipos.
export function nombreCorto(nombre: string, apellido: string): string {
  const inicial = nombre.trim().charAt(0);
  return inicial ? `${inicial}. ${apellido}` : apellido;
}

export function BarraSuperior() {
  const { sesion, puede } = useSesion();
  const ruta = useRuta();
  const conMenu = sesion !== null && !sesion.debe_cambiar_contrasena;
  const enUsuarios = ruta.pagina === "usuarios";
  return (
    <header className="barra">
      <a className="barra__marca" href={rutas.proyectos}>
        <Logo />
        Sistema de trazados
      </a>
      {sesion?.estudio && <span className="barra__estudio">{sesion.estudio}</span>}
      {conMenu && (
        <nav className="barra__nav" aria-label="Secciones del portal">
          <a
            href={rutas.proyectos}
            className={`barra__enlace ${!enUsuarios && ruta.pagina !== "contrasena" ? "barra__enlace--actual" : ""}`}
          >
            Proyectos
          </a>
          {puede("gestionar_usuarios") && (
            <a href={rutas.usuarios} className={`barra__enlace ${enUsuarios ? "barra__enlace--actual" : ""}`}>
              Usuarios
            </a>
          )}
        </nav>
      )}
      <div className="barra__derecha">
        {/* Sin sesión, el estado de la API se ve entero; con sesión, un punto y el detalle en el menú. */}
        <IndicadorApi compacto={sesion !== null} />
        {sesion && <MenuUsuario />}
      </div>
    </header>
  );
}

function MenuUsuario() {
  const { sesion, salir } = useSesion();
  if (!sesion) return null;
  const { nombre, apellido, rol, email } = sesion.usuario;
  const iniciales = `${nombre.trim().charAt(0)}${apellido.trim().charAt(0)}`.toUpperCase();
  return (
    <Desplegable
      claseBoton="usuario"
      alineacion="derecha"
      titulo={email}
      etiqueta={
        <>
          <span className="avatar" aria-hidden="true">
            {iniciales}
          </span>
          <span className="usuario__nombre">
            <strong>{nombreCorto(nombre, apellido)}</strong>
            <small>{nombreRol(rol)}</small>
          </span>
        </>
      }
    >
      {(cerrar) => (
        <>
          <div className="desplegable__nota">
            <strong>
              {nombre} {apellido}
            </strong>
            <div className="texto-tenue">{email}</div>
          </div>
          <div className="desplegable__nota">
            <IndicadorApi />
          </div>
          <hr className="desplegable__separador" />
          {!sesion.debe_cambiar_contrasena && (
            <a className="desplegable__item" href={rutas.contrasena} onClick={cerrar}>
              Cambiar la contraseña
            </a>
          )}
          <button
            type="button"
            className="desplegable__item"
            onClick={() => {
              cerrar();
              void salir();
            }}
          >
            Cerrar sesión
          </button>
        </>
      )}
    </Desplegable>
  );
}

export type Miga = { texto: string; href?: string };

type PropsBarraPagina = {
  migas?: Miga[];
  titulo: ReactNode;
  // Lo que va al lado del título: el selector de versión, las insignias.
  centro?: ReactNode;
  acciones?: ReactNode;
};

// La barra de cada página: «Proyectos / Loteo … /» sobre el título, y las acciones a la derecha.
export function BarraPagina({ migas = [], titulo, centro, acciones }: PropsBarraPagina) {
  return (
    <div className="barra-pagina">
      <div className="barra-pagina__titulos">
        {migas.length > 0 && (
          <nav className="migas" aria-label="Ubicación">
            {migas.map((m, k) => (
              <span key={k}>{m.href ? <a href={m.href}>{m.texto}</a> : m.texto} / </span>
            ))}
          </nav>
        )}
        <h1 className="barra-pagina__titulo">{titulo}</h1>
      </div>
      {centro && <div className="barra-pagina__centro">{centro}</div>}
      {acciones && <div className="barra-pagina__acciones">{acciones}</div>}
    </div>
  );
}

// Una tarjeta con su título de sección en mayúsculas («ESTRATEGIA DE GENERACIÓN»).
export function TarjetaSeccion({
  titulo,
  extra,
  clase = "",
  children,
  etiqueta,
}: {
  titulo?: ReactNode;
  extra?: ReactNode;
  clase?: string;
  children: ReactNode;
  etiqueta?: string;
}) {
  return (
    <section
      className={`tarjeta-seccion ${clase}`}
      aria-label={etiqueta ?? (typeof titulo === "string" ? titulo : undefined)}
    >
      {titulo && (
        <h3 className="titulo-seccion">
          <span>{titulo}</span>
          {extra}
        </h3>
      )}
      {children}
    </section>
  );
}

// Un ✓ o una ✗ en un círculo, como en «Verificaciones» (p. 49).
export function Marca({ tipo }: { tipo: "ok" | "error" | "aviso" | "info" }) {
  const texto = { ok: "✓", error: "✕", aviso: "!", info: "i" }[tipo];
  return (
    <span className={`marca marca--${tipo}`} aria-hidden="true">
      {texto}
    </span>
  );
}
