# Proxy a la API. ÚNICA copia: lo incluyen dev.conf y prod.conf dentro de `location /api/`.
#
# Resolver de Docker + proxy_pass con variable: Nginx resuelve «api» en cada request (con
# caché de 10 s) en lugar de una sola vez al arrancar. Sin esto, cuando el contenedor api se
# recrea (docker compose up --build) y cambia de IP, Nginx sigue apuntando a la vieja y
# responde 502 hasta que se lo reinicia. Sin URI en el proxy_pass, el path llega intacto
# (/api/health → /api/health).
resolver 127.0.0.11 valid=10s ipv6=off;
set $api_upstream http://api:8000;
proxy_pass $api_upstream;

proxy_http_version 1.1;
# Con el puerto ($http_host y no $host): la API compara el Origin de un pedido con el Host cuando el
# navegador no manda Sec-Fetch-Site (D63).
proxy_set_header Host $http_host;
proxy_set_header X-Real-IP $remote_addr;
# La dirección del navegador (D64). Nginx es el único salto: PISA lo que haya mandado el cliente, en
# lugar de agregarle la suya ($proxy_add_x_forwarded_for). Si no, un cliente que manda su propio
# X-Forwarded-For elige con qué dirección lo ve la API: esquiva el bloqueo por intentos fallidos o
# bloquea a otro (Seguridad, p. 53).
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;

# Una generación de trazado puede tardar (RNF03: tiempo acorde al tamaño del terreno).
proxy_read_timeout 120s;
