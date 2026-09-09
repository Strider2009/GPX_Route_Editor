FROM node:24-alpine AS build
WORKDIR /app
# Install from the lockfile so the image contains exactly the dependency versions
# that CI audited. `npm install` would re-resolve the caret ranges at build time,
# which can ship a version no scanner has ever seen.
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
