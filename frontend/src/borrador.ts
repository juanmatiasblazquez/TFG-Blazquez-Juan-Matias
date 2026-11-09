// El borrador del alta (B5; D81): lo escrito y lo dibujado, en el navegador, para no perderlo si se cierra
// la pestaña. Es por usuario (`trazados:borrador:<id>`), no tiene nada de la sesión (D63) y se borra al
// registrar el proyecto y al cerrar la sesión. El almacenamiento puede no estar (una ventana privada, un
// navegador que lo bloquea): entonces no hay borrador, y el alta sigue igual.

const PREFIJO = "trazados:borrador:";

const clave = (idUsuario: number) => `${PREFIJO}${idUsuario}`;

export function leerBorrador<T>(idUsuario: number): T | null {
  try {
    const texto = window.localStorage.getItem(clave(idUsuario));
    return texto ? (JSON.parse(texto) as T) : null;
  } catch {
    return null;
  }
}

export function guardarBorrador<T>(idUsuario: number, borrador: T): boolean {
  try {
    window.localStorage.setItem(clave(idUsuario), JSON.stringify(borrador));
    return true;
  } catch {
    return false;
  }
}

export function descartarBorrador(idUsuario: number): void {
  try {
    window.localStorage.removeItem(clave(idUsuario));
  } catch {
    // Sin almacenamiento no hay nada que borrar.
  }
}
