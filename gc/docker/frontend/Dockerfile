# 阶段1: 构建前端应用
FROM node:20-alpine as build-stage
WORKDIR /app

# 复制package.json和package-lock.json
COPY package*.json ./

# 安装项目依赖
RUN npm ci

# 复制项目文件并构建
COPY . .
RUN npm run build

# 阶段2: 使用nginx提供静态文件
FROM nginx:1.25-alpine as production-stage
COPY --from=build-stage /app/dist /usr/share/nginx/html
EXPOSE 80

# 默认nginx配置
CMD ["nginx", "-g", "daemon off;"]
