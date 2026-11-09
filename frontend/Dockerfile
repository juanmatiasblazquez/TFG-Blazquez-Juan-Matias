# Frontend de DESARROLLO: dev-server de Vite con hot reload, detrás del Nginx de dev.
# En producción no corre: el contenedor «proxy» sirve el build estático (Dockerfile.prod).
FROM node:24-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
