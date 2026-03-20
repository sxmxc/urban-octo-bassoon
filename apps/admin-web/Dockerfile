FROM node:24-alpine AS base

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

FROM base AS build

ARG APP_VERSION=2.0.0-alpha.1
ENV VITE_APP_VERSION=${APP_VERSION}

COPY . .

RUN npm run build

FROM base AS dev

COPY . .

EXPOSE 3000

CMD ["sh", "./start.sh"]

FROM nginx:1.29 AS runtime

ARG APP_VERSION=2.0.0-alpha.1
ENV APP_VERSION=${APP_VERSION} \
    API_UPSTREAM=http://api:8000

COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
