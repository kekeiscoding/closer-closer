FROM node:24-alpine AS assets
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ frontend/
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ISATU_DATA_DIR=/data
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 isatu \
    && useradd --uid 10001 --gid isatu --no-create-home isatu \
    && install -d -m 0700 -o isatu -g isatu /data
COPY sss/ sss/
COPY --from=assets /build/sss/static/scanner.js sss/static/scanner.js
USER isatu
EXPOSE 1133
CMD ["gunicorn", "--bind", "0.0.0.0:1133", "--workers", "2", "--threads", "16", "--preload", "--timeout", "90", "--access-logfile", "-", "--access-logformat", "%(m)s %(s)s %(L)ss", "sss:create_app()"]
