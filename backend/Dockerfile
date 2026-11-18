FROM node:22-alpine

WORKDIR /app

RUN apk add --no-cache openssl

COPY package.json package-lock.json ./
COPY prisma ./prisma
RUN npm ci

COPY tsconfig.json ./
COPY src ./src
RUN npx prisma generate && npm run build && npm prune --omit=dev

ENV NODE_ENV=production
ENV PORT=5000

USER node
EXPOSE 5000

CMD ["node", "dist/index.js"]
