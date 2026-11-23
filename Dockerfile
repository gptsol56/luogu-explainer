FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 服务端监听 0.0.0.0 才让容器外能访问; 密钥只从环境变量注入, 不进镜像
ENV LUOGUBOT_HOST=0.0.0.0
ENV LUOGUBOT_PORT=8848

EXPOSE 8848

CMD ["python", "server/app.py", "--host", "0.0.0.0", "--port", "8848"]