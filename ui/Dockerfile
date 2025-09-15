# /ui/Dockerfile

FROM python:3.11-slim

# 配置Poetry环境变量并禁用Python输出缓冲
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=false \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONUNBUFFERED=1

# 将Poetry的安装路径添加到PATH
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# 安装Poetry
RUN pip install poetry

# 优先复制并安装依赖, 以利用Docker的层缓存机制
# CORRECTED: 明确指定源文件相对于根上下文的路径
COPY ui/pyproject.toml ui/poetry.lock ./
COPY common/pyproject.toml common/poetry.lock ./common/

# 安装项目依赖
RUN poetry install --no-root --no-dev

# 复制应用程序源代码
# CORRECTED: 明确指定源目录相对于根上下文的路径
COPY ui/src ./src
COPY common/src ./common/src

# 声明容器在运行时监听的端口
EXPOSE 8501

# 使用exec形式的CMD, 以便正确处理信号
CMD ["streamlit", "run", "src/ui/app.py"]