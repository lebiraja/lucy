FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies based on package.json and optionally package-lock.json
COPY package*.json ./
RUN npm ci

# Copy the rest of the code and build
COPY . .
RUN npm run build

# Production server
FROM nginx:alpine

# Copy built assets to Nginx html folder
COPY --from=builder /app/dist /usr/share/nginx/html

# Replace default Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
