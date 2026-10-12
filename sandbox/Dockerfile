# myopencode-sandbox：容器沙箱后端基础镜像（python3 + node + git + bash）
# 构建：docker build -t myopencode-sandbox:latest ./sandbox
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git bash curl ca-certificates gnupg build-essential \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
