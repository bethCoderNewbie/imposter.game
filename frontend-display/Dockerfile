FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# HOST_IP: LAN address of the Docker host (e.g. http://192.168.1.100).
# Pass at build time: docker compose build --build-arg HOST_IP=http://192.168.1.100
# Or set HOST_IP in your shell before running docker compose up --build.
ARG HOST_IP
ARG QR_BACKEND_URL
ARG MOBILE_URL
ENV VITE_HOST_IP=$HOST_IP
ENV VITE_QR_BACKEND_URL=$QR_BACKEND_URL
ENV VITE_MOBILE_URL=$MOBILE_URL
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
