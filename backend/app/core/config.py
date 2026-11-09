from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

# Contraseñas de ejemplo (.env.example y los defaults de abajo): solo válidas en dev/test.
# El guard de producción no arranca si alguna sigue en pie.
DB_PASSWORDS_INSEGURAS = {"", "trazados", "trazados-dev"}


class Settings(BaseSettings):
    # La configuración llega por variables de entorno (las pone docker compose desde .env).
    # hide_input_in_errors: sin esto, un error de validación imprime en el log del
    # contenedor todos los valores recibidos, contraseña de la base incluida.
    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    # Entorno de ejecución: "dev" (default, permite valores de ejemplo) o "prod" (activa el
    # guard fail-fast; ver _validar_produccion).
    app_env: str = "dev"

    db_host: str = "db"
    db_port: int = 5432
    db_name: str = "trazados"
    db_user: str = "trazados"
    db_password: str = "trazados-dev"

    # El nombre del estudio (D74): la barra del portal y la cabecera de la vista del cliente, como en
    # los prototipos de las p. 48 a 51. Vacío, el portal dice solo «Sistema de trazados».
    nombre_estudio: str = ""

    @property
    def es_produccion(self) -> bool:
        return self.app_env.strip().lower() == "prod"

    @property
    def cookie_segura(self) -> bool:
        """La cookie de la sesión lleva `Secure` en producción: el navegador solo la manda por HTTPS
        (D63). Se deriva del entorno y no de una variable, así no hay forma de apagarla en producción
        por error. En `localhost` los navegadores la aceptan también por HTTP, que es lo que usa el
        prod local."""
        return self.es_produccion

    @model_validator(mode="after")
    def _validar_produccion(self) -> "Settings":
        """Fail-fast: en producción no se permiten los valores de ejemplo.

        Evita publicar sin querer con la contraseña de la base que figura en el repositorio.
        En dev/test no hace nada.

        La autenticación no suma un secreto (D63): el token de la sesión es aleatorio y se guarda
        hasheado, no se firma. Tampoco hay credenciales por defecto que vigilar: ningún entorno siembra
        usuarios, y el primer director técnico se crea con `python -m app.admin crear-director`, que
        siempre genera una contraseña temporal (D68).
        """
        if not self.es_produccion:
            return self
        errores: list[str] = []
        if self.db_password.strip() in DB_PASSWORDS_INSEGURAS:
            errores.append("DB_PASSWORD está vacía o usa una contraseña de ejemplo.")
        if errores:
            raise ValueError(
                "Configuración insegura para APP_ENV=prod: "
                + " ".join(errores)
                + " Definí valores propios en el entorno (.env)."
            )
        return self

    @property
    def database_url(self) -> URL:
        # URL.create y no una f-string: una contraseña con "@", ":" o "%" rompería la URL.
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


settings = Settings()
