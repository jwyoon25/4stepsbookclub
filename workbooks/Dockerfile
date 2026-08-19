FROM ghcr.io/typst/typst:0.15.1 AS typst

FROM node:24-alpine

ENV NODE_ENV=production
WORKDIR /app

COPY --from=typst /bin/typst /usr/local/bin/typst
COPY service/package.json service/package-lock.json ./
RUN npm ci --omit=dev --omit=optional

COPY . ./workbooks
RUN mkdir -p /app/workbooks/output && chown -R node:node /app

USER node
EXPOSE 8080

CMD ["node", "workbooks/service/server.mjs"]
