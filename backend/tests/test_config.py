import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_prod_no_arranca_con_la_contrasena_de_ejemplo():
    with pytest.raises(ValidationError, match="DB_PASSWORD") as error:
        Settings(app_env="prod", db_password="trazados-dev")
    # El mensaje termina en el log del contenedor: no tiene que mostrar los valores recibidos.
    assert "trazados-dev" not in str(error.value)


def test_prod_arranca_con_una_contrasena_propia():
    assert Settings(app_env="prod", db_password="una-clave-propia-y-larga").es_produccion


def test_dev_permite_los_valores_de_ejemplo():
    assert not Settings(app_env="dev", db_password="trazados-dev").es_produccion


def test_la_url_soporta_contrasenas_con_caracteres_especiales():
    url = Settings(db_password="p@ss:w%rd/1").database_url
    assert url.password == "p@ss:w%rd/1"
    assert "p%40ss%3Aw%25rd%2F1" in url.render_as_string(hide_password=False)
