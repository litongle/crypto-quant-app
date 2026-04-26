# 前端Docker配置修复

## 问题
在执行 \docker compose up -d\ 时出现错误:
\\\
resolve : lstat /root/projects/gc/frontend/docker: no such file or directory
\\\

## 修复方案
1. 添加了 \docker/frontend/Dockerfile\ 配置文件
2. 使用多阶段构建:
   - 第一阶段使用 node:20-alpine 构建 Vue.js 应用
   - 第二阶段使用 nginx:1.25-alpine 部署静态文件

## 测试方法
执行 \docker compose up -d\ 命令，确认所有服务能够正常启动。

## 注意事项
这是由 Droid AI 辅助创建的 PR。
