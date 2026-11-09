import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En desarrollo el navegador no habla con Vite directo: entra por Nginx
// (http://localhost:8080), que deriva /api a la API y el resto a este servidor
// (frontend/nginx/dev.conf). Por eso:
// - hmr.clientPort: el websocket del hot reload se abre contra el puerto de Nginx.
// - watch.usePolling: en Docker Desktop sobre Windows los cambios del bind mount no generan
//   eventos de archivo dentro del contenedor; sin polling no hay hot reload.
const puertoNginx = Number(process.env.HTTP_PORT ?? 8080);

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    hmr: { clientPort: puertoNginx },
    watch: { usePolling: process.env.DEV_POLLING === "1", interval: 300 },
  },
});
