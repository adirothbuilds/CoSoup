FROM node:24-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json tsconfig.base.json ./
COPY apps/web/package.json apps/web/package.json
COPY apps/mobile/package.json apps/mobile/package.json
COPY packages/client/package.json packages/client/package.json
COPY packages/design/package.json packages/design/package.json
RUN --mount=type=secret,id=build_ca,required=false,mode=0444 \
    if [ -f /run/secrets/build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; fi; \
    npm ci --workspace @stock-scanner/web --workspace @stock-scanner/client --workspace @stock-scanner/design \
      --include-workspace-root --ignore-scripts --no-audit --no-fund --strict-ssl=true --fetch-retries=0 --fetch-timeout=30000
COPY packages packages
COPY apps/web apps/web
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.28-alpine AS runtime
COPY --from=build --chmod=755 /app/apps/web/dist /usr/share/nginx/html
COPY --chmod=644 apps/web/deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --chmod=644 apps/web/deploy/headers.conf /etc/nginx/scanner-headers.conf
USER 101:101
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s CMD wget -Y off -q -O /dev/null http://127.0.0.1:8080/health || exit 1
CMD ["nginx", "-g", "daemon off;"]
