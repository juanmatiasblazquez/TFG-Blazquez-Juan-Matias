"""Contraseñas: la política de la p. 53, el hash y la contraseña temporal (RNF02; D66). Copia única.

- **Política (p. 53):** al menos 8 caracteres, con una mayúscula y un carácter especial obligatorios.
  Se admiten «todas las letras del abecedario, números y símbolos especiales básicos»:
  - letras: de la A a la Z y la ñ, en mayúscula y minúscula, más las vocales con tilde y la ü;
  - números: del 0 al 9;
  - símbolos básicos: la puntuación ASCII (``!"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~``), sin espacios;
  - a lo sumo 128 caracteres (criterio de diseño: Argon2 acepta cualquier largo, pero una
    contraseña de un megabyte es un ataque, no una contraseña).
- **Hash:** Argon2id (`argon2-cffi`) con los parámetros por defecto, los del RFC 9106 de bajo uso de
  memoria: 3 pasadas, 64 MiB y 4 hilos, unos 70 ms por hash. El documento no nombra un algoritmo.
- **Tiempo constante ante un correo inexistente:** se verifica contra `HASH_SIMULADO`, así tarda lo
  mismo que una contraseña incorrecta y el tiempo no revela si el correo está registrado (p. 53).
- **Temporal:** 12 caracteres de `secrets`, sin los que se confunden al dictarlos (I, l, O, 0, 1), y
  siempre cumple la política.

Ninguna función de este módulo registra ni devuelve una contraseña en un mensaje.
"""

import secrets
import string

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

LONGITUD_MINIMA = 8
LONGITUD_MAXIMA = 128

MAYUSCULAS = string.ascii_uppercase + "ÑÁÉÍÓÚÜ"
LETRAS = string.ascii_lowercase + "ñáéíóúü" + MAYUSCULAS
SIMBOLOS = string.punctuation
ADMITIDOS = frozenset(LETRAS + string.digits + SIMBOLOS)

# Los mensajes de la política. No repiten ningún carácter de la contraseña.
FALTA_LARGO = f"Tiene que tener al menos {LONGITUD_MINIMA} caracteres."
SOBRA_LARGO = f"Admite hasta {LONGITUD_MAXIMA} caracteres."
FALTA_MAYUSCULA = "Tiene que tener al menos una mayúscula."
FALTA_SIMBOLO = "Tiene que tener al menos un carácter especial, por ejemplo # $ % & * + - = ? @ o !."
NO_ADMITIDO = "Solo admite letras, números y símbolos especiales básicos, sin espacios."
# La política en una frase, para el portal (que no la copia, D37) y para la sugerencia de un 422.
DESCRIPCION_POLITICA = (
    f"Al menos {LONGITUD_MINIMA} caracteres, con una mayúscula y un carácter especial. Se admiten letras "
    "(también la ñ y las vocales con tilde), números y los símbolos básicos, sin espacios."
)

_hasher = PasswordHasher()


def problemas_de(contrasena: str) -> list[str]:
    """Lo que le falta a una contraseña para cumplir la política de la p. 53; vacío si la cumple."""
    problemas = []
    if len(contrasena) < LONGITUD_MINIMA:
        problemas.append(FALTA_LARGO)
    if len(contrasena) > LONGITUD_MAXIMA:
        problemas.append(SOBRA_LARGO)
    if not any(c in MAYUSCULAS for c in contrasena):
        problemas.append(FALTA_MAYUSCULA)
    if not any(c in SIMBOLOS for c in contrasena):
        problemas.append(FALTA_SIMBOLO)
    if any(c not in ADMITIDOS for c in contrasena):
        problemas.append(NO_ADMITIDO)
    return problemas


def hashear(contrasena: str) -> str:
    return _hasher.hash(contrasena)


# Un hash de una contraseña que nadie conoce, con los mismos parámetros: contra él se verifica cuando
# el correo no existe o el hash guardado no es de Argon2 (el usuario de desarrollo tenía «!», D31).
HASH_SIMULADO = hashear(secrets.token_urlsafe(32))


def verificar(hash_guardado: str | None, contrasena: str) -> bool:
    """Si la contraseña corresponde al hash. Sin hash o con uno que no es de Argon2, igual hace el
    trabajo completo contra `HASH_SIMULADO` y responde que no: el tiempo es el mismo."""
    try:
        return _hasher.verify(hash_guardado or HASH_SIMULADO, contrasena)
    except InvalidHashError:
        try:
            _hasher.verify(HASH_SIMULADO, contrasena)
        except VerificationError:
            pass
        return False
    except VerificationError:
        return False


def necesita_rehash(hash_guardado: str) -> bool:
    """Si el hash se hizo con otros parámetros: se rehace al iniciar sesión, con la contraseña a mano."""
    try:
        return _hasher.check_needs_rehash(hash_guardado)
    except InvalidHashError:
        return False


# La temporal: sin I, l, O, 0 ni 1, que se confunden al dictarla, y con símbolos fáciles de escribir.
_TEMPORAL_MAYUSCULAS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_TEMPORAL_MINUSCULAS = "abcdefghijkmnpqrstuvwxyz"
_TEMPORAL_DIGITOS = "23456789"
_TEMPORAL_SIMBOLOS = "#$%&*+-=?@"
LONGITUD_TEMPORAL = 12


def generar_temporal() -> str:
    """Una contraseña temporal aleatoria que cumple la política (CU02, paso 6; p. 53)."""
    azar = secrets.SystemRandom()
    obligatorios = [secrets.choice(grupo) for grupo in (_TEMPORAL_MAYUSCULAS, _TEMPORAL_MINUSCULAS, _TEMPORAL_DIGITOS, _TEMPORAL_SIMBOLOS)]
    todos = _TEMPORAL_MAYUSCULAS + _TEMPORAL_MINUSCULAS + _TEMPORAL_DIGITOS + _TEMPORAL_SIMBOLOS
    caracteres = obligatorios + [secrets.choice(todos) for _ in range(LONGITUD_TEMPORAL - len(obligatorios))]
    azar.shuffle(caracteres)
    return "".join(caracteres)
