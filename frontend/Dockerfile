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
# Use in CI: docker build --target build -o dist .
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build
