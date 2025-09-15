# /orchestrator/Dockerfile

FROM python:3.11-slim

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=false \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONUNBUFFERED=1

ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

RUN pip install poetry

# 优先复制并安装依赖, 以利用Docker的层缓存机制
# CORRECTED: 路径相对于项目根目录上下文
COPY orchestrator/pyproject.toml orchestrator/poetry.lock ./
COPY common/pyproject.toml common/poetry.lock ./common/
RUN poetry install --no-root --no-dev

# 复制应用程序源代码
# CORRECTED: 路径相对于项目根目录上下文
COPY orchestrator/src ./src
COPY common/src ./common/src

# 默认启动命令
CMD ["python", "-m", "orchestrator.run_worker"]