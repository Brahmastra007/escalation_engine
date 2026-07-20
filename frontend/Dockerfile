# --- Dev stage ---
# Used by VS Code Dev Container and docker-compose.dev.yml.
# Installs dependencies and keeps the container running for development.
FROM node:20-alpine AS dev
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# --- Build stage ---
# Compiles TypeScript and bundles the app into static files.
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build

# --- Prod stage ---
# Serves the built static files with nginx (tiny, fast, no Node.js runtime needed).
FROM nginx:alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
