# Build stage
FROM node:20-alpine AS builder
WORKDIR /app

# Copy package files (from apps/frontend directory)
COPY apps/frontend/package*.json ./
RUN npm ci --legacy-peer-deps

# Copy source files (from apps/frontend directory)
COPY apps/frontend/ .

# Build the application
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Production stage
FROM nginx:alpine
WORKDIR /usr/share/nginx/html

# Copy built files from builder
COPY --from=builder /app/dist .

# Copy nginx configuration for SPA
RUN echo 'server { \
    listen 80; \
    server_name _; \
    root /usr/share/nginx/html; \
    index index.html; \
    location / { \
        try_files $uri $uri/ /index.html; \
    } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

