# Trazados de loteo

Prototipo del Trabajo Final de Grado de Ingeniería en Software (Universidad Siglo 21): **sistema web de
generación automática de trazados de loteo mediante partición de polígonos**.

Sobre un terreno dibujado en cartografía real, un motor de partición de polígonos con restricciones genera
alternativas de loteo: una red de circulación conexa con los accesos, y manzanas y lotes con frente sobre
ella, que cumplen los parámetros del proyecto y la normativa de Córdoba que se tomó como referencia (Ley
4146 y Ord. 8060).

- **Motor de generación:** trabaja sobre cualquier polígono válido. Genera la red de calles con sus ochavas
  y las avenidas exigidas, subdivide las manzanas en lotes y asigna los espacios verdes hasta la cesión
  exigida. También verifica las restricciones y calcula los indicadores. Calles, lotes y verdes forman una
  partición exacta del terreno. La misma entrada da siempre el mismo resultado.
- **Recálculo:** se fijan las manzanas que se quieren conservar y el motor genera el resto. Cada cambio
  crea una versión nueva, y ninguna versión se modifica.
- **Portal web:** el alta del proyecto con el dibujo del terreno, los accesos y las áreas reservadas, y los
  parámetros con su fuente normativa. Desde ahí se generan las alternativas y se comparan lado a lado.
- **Usuarios y roles:** director técnico, proyectista y consultor interno, cada uno con sus permisos. La
  sesión va en una cookie, las contraseñas se guardan con Argon2id y una dirección se bloquea tras varios
  intentos fallidos.
- **Observaciones y enlace al cliente:** las alternativas se observan y se responden (con un comentario o
  con un recálculo), y se comparten con el cliente por un enlace de solo lectura, que vence y se puede
  revocar.

## Stack

| Capa | Tecnologías |
|---|---|
| API | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, GeoAlchemy2, Argon2 |
| Base de datos | PostgreSQL 17 + PostGIS 3.5 |
| Motor | Python: Shapely, NetworkX, NumPy y pyproj, en un paquete independiente de la API |
| Frontend | React 18, TypeScript, Vite, Leaflet y Leaflet-Geoman sobre OpenStreetMap |
| Infraestructura | Nginx como única entrada, Docker Compose |

## Arquitectura

```
Navegador ──HTTP──▶ proxy (Nginx) ──/api──▶ api (FastAPI + motor) ──▶ db (PostgreSQL + PostGIS)
     │                   └── resto ──▶ frontend (React + Leaflet)
     └──HTTPS──▶ teselas de OpenStreetMap
```

- El navegador habla solo con Nginx: `/api/*` va a la API y el resto al frontend. Como todo sale del mismo
  origen, no hace falta CORS.
- La API usa al motor, nunca al revés. El motor no conoce la API ni la base: recibe geometrías y parámetros
  en metros y devuelve geometrías y resultados.
- Las geometrías se guardan en EPSG:4326, y el motor calcula en POSGAR 2007 (en la ciudad de Córdoba,
  EPSG:5346).

## Estructura del repositorio

```
.
├── backend/                  API (contenedor «api»)
│   ├── app/
│   │   ├── api/routers/      endpoints HTTP, uno por grupo (proyectos, alternativas, versiones…)
│   │   ├── api/dependencias.py   sesión, permisos por rol y enlace del cliente
│   │   ├── core/             configuración, base de datos, errores, permisos, contraseñas
│   │   ├── models/           modelos SQLAlchemy (tablas)
│   │   ├── schemas/          entrada y salida de cada endpoint (Pydantic)
│   │   ├── services/         casos de uso: generación, recálculo, comparación, observaciones…
│   │   ├── admin.py          comandos de administración (crear el primer director técnico)
│   │   └── main.py           la aplicación FastAPI
│   ├── migrations/           migraciones Alembic (la 0001 habilita PostGIS)
│   ├── tests/                pruebas de la API, contra una base de test propia
│   ├── Dockerfile
│   └── entrypoint.sh         espera la base, migra y arranca Uvicorn
├── motor/                    paquete motor-trazados, independiente de la API y de la base
│   ├── src/motor_trazados/
│   │   ├── contrato.py       tipos de entrada y salida, y sus validaciones
│   │   ├── motor.py          MotorGeneracion: orquesta la generación y el recálculo
│   │   ├── generador_red.py  la grilla de calles, la calle de borde y la elección de avenidas
│   │   ├── red.py            la red de circulación como grafo
│   │   ├── corredores.py     la superficie de calle, con las ochavas
│   │   ├── subdivisores.py   de manzanas a lotes
│   │   ├── remanentes.py     lo que no es lote: espacio verde o libre
│   │   ├── asignador.py      los espacios verdes hasta la cesión exigida
│   │   ├── verificador.py    las restricciones de cada lote, manzana y red
│   │   ├── indicadores.py    superficies, porcentajes y distancias
│   │   ├── geometria.py      tolerancias y cierre de la partición
│   │   ├── valores_referencia.py   valores por defecto con su fuente normativa
│   │   ├── semillas.py       la única fuente de azar (reproducibilidad)
│   │   ├── coordenadas.py    conversión entre coordenadas geográficas y POSGAR 2007
│   │   ├── exportar.py       salida en GeoJSON
│   │   └── referencia.py     casos de referencia con nombre
│   ├── tests/                pruebas del motor, en su propio contenedor
│   └── pyproject.toml        dependencias con versión exacta
├── frontend/                 portal web
│   ├── src/
│   │   ├── api/              un módulo por grupo de endpoints, con sus tipos
│   │   ├── hooks/            rutas, sesión, consultas
│   │   ├── paginas/          una pantalla por archivo
│   │   └── components/       mapa, capas, formularios, paneles
│   ├── nginx/                configuración de Nginx (desarrollo y producción)
│   ├── Dockerfile            servidor de desarrollo de Vite
│   └── Dockerfile.prod       build + Nginx (el proxy de producción)
├── docker/db/                imagen de PostgreSQL + PostGIS
├── scripts/
│   └── generar-referencia.ps1   carga proyectos de demostración por la API
├── docker-compose.yml        desarrollo
├── docker-compose.prod.yml   producción: proxy, api y db
└── .env.example              variables de entorno, para copiar a .env
```

## Requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows, macOS o Linux) con Docker
  Compose v2.17 o superior.
- Git.
- No hace falta tener Python ni Node instalados: todo corre en contenedores.
- El navegador necesita internet para las teselas del mapa (OpenStreetMap).

## Puesta en marcha, paso a paso

Los comandos están en PowerShell. Donde cambian en bash (Linux o macOS), va también la versión de bash.

**1. Clonar el repositorio**

```powershell
git clone <url-del-repositorio> trazados-loteo
cd trazados-loteo
```

**2. Crear el archivo de entorno**

```powershell
Copy-Item .env.example .env      # bash: cp .env.example .env
```

Para desarrollo, los valores de ejemplo sirven tal cual. Los que más se cambian:
- `HTTP_PORT`: el puerto del portal (8080);
- `DB_PORT_HOST`: el puerto de la base en `127.0.0.1` (5432), para conectarse con QGIS, pgAdmin o psql;
- `NOMBRE_ESTUDIO`: el nombre que aparece en la barra del portal (opcional).

**3. Levantar los contenedores**

```powershell
docker compose up --build -d
```

La primera vez tarda unos minutos, porque construye las imágenes. Al arrancar, la API espera a la base,
aplica las migraciones (`alembic upgrade head`) y queda con recarga automática, igual que el frontend.

**4. Comprobar que todo esté sano**

```powershell
docker compose ps                                  # db y api tienen que figurar como (healthy)
curl.exe http://localhost:8080/api/health          # bash: curl http://localhost:8080/api/health
# {"estado":"ok","base":"ok","postgis":"3.5.x","motor":"0.11.0"}
```

Si la base no responde o PostGIS no está habilitado, el chequeo responde 503 con `"estado": "degradado"`.

**5. Crear el primer usuario (director técnico)**

No hay usuarios ni contraseñas por defecto. Este comando crea un director técnico e imprime una
**contraseña temporal**, que se muestra una sola vez y vale 24 horas:

```powershell
docker compose exec api python -m app.admin crear-director --nombre <nombre> --apellido <apellido> --email <correo>
```

**6. Entrar al portal**

Abrí http://localhost:8080 e iniciá sesión con el correo y la contraseña temporal. El portal pide
reemplazarla por una propia. Después, desde «Usuarios», el director técnico da de alta a los demás
(proyectistas y consultores).

**7. (Opcional) Cargar proyectos de demostración**

El script `scripts/generar-referencia.ps1` crea un cliente y un proyecto con un terreno de ejemplo, y genera
una alternativa a través de la API. Para usarlo, el usuario tiene que haber cambiado ya su contraseña
temporal.

```powershell
$env:TRAZADOS_EMAIL = '<correo del director técnico>'
powershell -ExecutionPolicy Bypass -File scripts\generar-referencia.ps1 -Caso prototipo   # pide la contraseña
```

Algunas opciones:
- `-Caso`: elige el terreno (`referencia`, `irregular`, `l`, `u`, `triangulo`, `reservada_centro`,
  `reservada_borde` o `prototipo`);
- `-SoloProyecto`: crea el proyecto sin generar, para generar desde el portal;
- `-Comparacion`: un proyecto con tres alternativas para comparar;
- `-Recalculo`: una alternativa con una versión recalculada;
- `-Compartir`: comparte la alternativa e imprime el enlace del cliente.

Las capas generadas quedan en `salida\api\` como GeoJSON, para abrirlas en QGIS.

**8. Parar**

```powershell
docker compose down        # agregar -v borra también la base
```

### Direcciones útiles

| Qué | Dónde |
|---|---|
| Portal | http://localhost:8080 |
| Chequeo de salud | http://localhost:8080/api/health |
| Documentación de la API (OpenAPI, solo en desarrollo) | http://localhost:8080/api/docs |
| Base de datos | `127.0.0.1:5432`, base y usuario `trazados` (contraseña en `.env`) |

Para probar los endpoints desde `/api/docs`, primero hay que iniciar sesión con `POST /api/sesion`.

## Recorrido rápido del portal

1. **Nuevo proyecto**, en tres pasos:
   - los datos y el cliente;
   - el terreno (dibujado, como rectángulo o importado de una planilla de vértices), los accesos y las
     áreas reservadas;
   - los parámetros del loteo, con su fuente normativa y la validación de coherencia en vivo.
2. **Generar alternativa:** la orientación de la grilla y la semilla vienen sugeridas. Cada alternativa
   muestra calles, manzanas, lotes y espacios verdes, con sus indicadores y las restricciones verificadas.
3. **Comparar** dos o tres alternativas lado a lado, con los mapas sincronizados.
4. **Fijar sectores y recalcular:** se eligen las manzanas que se conservan y se genera el resto como una
   versión nueva.
5. **Observaciones:** se registran sobre un sector dibujado, y se responden con un comentario o con un
   recálculo.
6. **Compartir:** las alternativas elegidas se comparten con el cliente por un enlace con vencimiento. El
   cliente ve el trazado y sus indicadores sin iniciar sesión.

Lo que un rol no puede hacer no aparece en el portal, y si se pide igual, la API responde 403.

## Pruebas

```powershell
# API: corre contra una base de test propia (trazados_test), que se borra y se recrea en cada corrida
docker compose exec -e DB_NAME=trazados_test api pytest

# Motor: en su propio contenedor, sin la API instalada (así se prueba que es independiente)
docker compose run --rm motor

# Motor: barridos largos sobre 96 terrenos (unos 10 minutos)
docker compose run --rm motor pytest -m barrido -s

# Frontend: chequeo de tipos
docker compose exec frontend npm run typecheck
```

Lo que cubren:
- que el motor no dependa de la API y que sea reproducible: la misma solicitud da el mismo resultado, bit a
  bit;
- que la partición cierre sin huecos ni solapes;
- cada restricción, con un trazado armado para incumplirla;
- que la base rechace modificar una versión;
- la tabla de permisos por rol contra lo que responde la API;
- el flujo completo, desde la API hasta el motor.

Para ver el resultado del motor sin la API, `docker compose run --rm motor python -m motor_trazados.referencia
--todos` escribe los casos de referencia en `motor/salida/<caso>/` como GeoJSON (EPSG:4326). Se abren en QGIS
sobre una capa de OpenStreetMap, y para medir en metros conviene poner el SRC del proyecto en EPSG:5346.

## Producción (local)

`docker-compose.prod.yml` levanta exactamente tres contenedores:
- `proxy`: Nginx, que sirve el build del frontend y es el único con puertos publicados;
- `api`;
- `db`.

La API y la base quedan en una red interna, sin salida a internet.

```powershell
# En .env: DB_PASSWORD con una contraseña propia (la de ejemplo se rechaza) y HTTP_PORT a elección
docker compose -f docker-compose.prod.yml up --build -d
docker compose -f docker-compose.prod.yml exec api python -m app.admin crear-director --nombre <nombre> --apellido <apellido> --email <correo>
```

- Sin `DB_PASSWORD`, Compose no arranca, y con la contraseña de ejemplo no arranca la API.
- La cookie de la sesión lleva `Secure`, así que hace falta HTTPS o `localhost`.
- Todavía faltan HTTPS con certificados, los respaldos automáticos de la base y el script de despliegue.

## Problemas comunes

- **`curl` en PowerShell 5.1** es un alias de `Invoke-WebRequest`: usá `curl.exe`.
- **El puerto 8080 o el 5432 están ocupados:** cambiá `HTTP_PORT` o `DB_PORT_HOST` en `.env` y volvé a
  levantar.
- **Cambiaste dependencias** (`backend/requirements.txt`, `motor/pyproject.toml` o
  `frontend/package.json`): `docker compose up --build`.
- **El hot reload no reacciona en Windows:** ya está configurado con polling. Si sigue sin reaccionar,
  `docker compose restart api frontend`.
- **Vite responde 504 «Outdated Optimize Dep»:** `docker compose restart frontend`.
- **«Dirección bloqueada» al iniciar sesión** (tras 10 intentos fallidos; en desarrollo, toda la máquina
  comparte una dirección): `docker compose exec api python -m app.admin desbloquear --todas`.
- **Olvidaste la contraseña del único director técnico:**
  `docker compose exec api python -m app.admin contrasena-temporal --email <correo>`.

## Notas

- El código, los comentarios y la interfaz están en español.
- Los comentarios citan requerimientos (`RF`, `RNF`), casos de uso (`CU`) y decisiones de diseño (`D` y un
  número). Remiten a la especificación y al registro de decisiones del trabajo, que no forman parte de este
  repositorio.

## Autoría

Juan Matías Blazquez, Trabajo Final de Grado de Ingeniería en Software, Universidad Siglo 21.

© 2026 Juan Matías Blazquez. Todos los derechos reservados.
