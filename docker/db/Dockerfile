# Contenedor «db»: PostgreSQL 17 + PostGIS 3.5 (diagrama de despliegue, p. 52 del documento).
#
# La imagen oficial trae /docker-entrypoint-initdb.d/10_postgis.sh, que al crear el volumen
# habilita postgis, postgis_topology y el geocodificador tiger. Se borra a propósito: la
# extensión la habilita la migración 0001 (control de migraciones, RNF06). Así el esquema
# entero sale de Alembic y el /api/health que dice "PostGIS habilitado" prueba que la
# migración corrió (docs/decisiones.md, D06).
FROM postgis/postgis:17-3.5

RUN rm -f /docker-entrypoint-initdb.d/10_postgis.sh
