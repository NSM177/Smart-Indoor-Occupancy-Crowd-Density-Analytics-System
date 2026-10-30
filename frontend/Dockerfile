FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

ARG VITE_API_BASE_URL=http://localhost:4000/api/v1
ARG VITE_WS_URL=ws://localhost:4000/ws/realtime
ARG VITE_AI_SERVICE_URL=http://localhost:8000

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_WS_URL=$VITE_WS_URL
ENV VITE_AI_SERVICE_URL=$VITE_AI_SERVICE_URL

RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
COPY --from=builder /app/package.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/vite.config.ts ./

EXPOSE 3000
CMD ["npm", "run", "preview"]
