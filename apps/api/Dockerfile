FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS runtime

ARG APP_VERSION=2.0.0-alpha.2
ENV APP_VERSION=${APP_VERSION}
COPY . .

EXPOSE 8000
CMD ["sh", "./start.prod.sh"]

FROM base AS dev

RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .

EXPOSE 8000
CMD ["sh", "./start.sh"]
