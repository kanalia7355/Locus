import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    {
      name: "local-development-boundary",
      configureServer(server) {
        server.middlewares.use((request, response, next) => {
          const hosts = ["127.0.0.1:5174", "localhost:5174"];
          const origins = ["http://127.0.0.1:5174", "http://localhost:5174"];
          if (
            !["127.0.0.1", "::1", "::ffff:127.0.0.1"].includes(
              request.socket.remoteAddress ?? "",
            ) ||
            !hosts.includes(request.headers.host ?? "") ||
            (!["GET", "HEAD", "OPTIONS"].includes(request.method ?? "") &&
              !origins.includes(request.headers.origin ?? ""))
          ) {
            response.statusCode = 403;
            response.end("Local development access only");
            return;
          }
          response.setHeader("Referrer-Policy", "no-referrer");
          response.setHeader("X-Content-Type-Options", "nosniff");
          next();
        });
      },
    },
  ],
  server: {
    host: "127.0.0.1",
    port: 5174,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  preview: { host: "127.0.0.1", port: 4173 },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
