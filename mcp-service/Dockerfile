# Initial tested target: Linux amd64. Runtime has no package-install/build dependency.
FROM python:3.12.11-alpine3.22@sha256:5e511b0e940def74dd23389510300c76017ca9bbc92484c40cff0951adf32245
RUN apk add --no-cache openssh-client \
 && addgroup -g 10001 minicore \
 && adduser -D -H -u 10001 -G minicore minicore
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/vendor/umcp:/app/mcp-service/src
COPY vendor/umcp /app/vendor/umcp
COPY mcp-service/src /app/mcp-service/src
COPY inventory /app/inventory
COPY configs /app/configs
COPY web-ui/dist /app/web-ui/dist
USER 10001:10001
EXPOSE 9000
CMD ["python", "-m", "minicore_mcp"]
