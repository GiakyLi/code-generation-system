# /orchestrator/Dockerfile
# 技术审计与重构报告
#
# ### 1. 核心变更: 优化构建流程和安全性
#
# 我们对Dockerfile进行了标准化和优化, 以提高构建效率、减小镜像大小并增强安全性。
#
# - **多阶段构建(虽然此处未显式使用, 但为最佳实践)**: 对于更复杂的应用,
#   应使用多阶段构建。一个阶段用于安装依赖和编译, 另一个阶段仅复制必要的
#   运行时文件到一个干净的基础镜像中。这可以显著减小最终镜像的体积。
#
# - **依赖缓存**: `COPY pyproject.toml poetry.lock./`和`RUN poetry install`
#   被放在`COPY./src./src`之前。这是Docker镜像构建的最佳实践。
#   只要`pyproject.toml`和`poetry.lock`文件没有变化, Docker就会使用
#   这一层的缓存, 从而避免了在每次代码变更时都重新下载和安装所有依赖,
#   大大加快了构建速度。
#
# - **移除不必要的开发依赖**: `poetry install`命令使用了`--no-dev`和`--no-root`
#   标志。这确保了最终的生产镜像中不包含任何仅用于开发的包(如`ruff`, `mypy`)
#   或项目本身的可编辑安装。这减小了镜像体积, 也减少了潜在的攻击面。
#
# - **标准化环境变量**: `POETRY_*`环境变量确保了Poetry在非交互式的CI/CD环境中
#   能够以可预测的方式运行。`PYTHONUNBUFFERED=1`确保Python的输出(如日志)
#   能直接发送到stdout/stderr, 而不会被缓冲, 这对于实时日志收集至关重要。

# 使用官方的slim镜像作为基础, 以减小镜像体积
FROM python:3.11-slim

# 设置环境变量, 优化Poetry在容器中的行为并确保日志实时输出
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=false \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONUNBUFFERED=1

# 将Python包的安装路径添加到PATH中, 以便可以直接运行通过poetry安装的脚本
ENV PATH="/root/.local/bin:$PATH"

# 设置工作目录
WORKDIR /app

# 安装Poetry
RUN pip install poetry

# 优先复制并安装依赖, 以利用Docker的层缓存机制
# 只要依赖文件没有变化, 就不需要重新执行poetry install
COPY pyproject.toml poetry.lock./
# 同样处理共享的common库的依赖
COPY../common/pyproject.toml../common/poetry.lock./common/
RUN poetry install --no-root --no-dev

# 复制应用程序源代码
COPY./src./src
COPY../common/src./common/src

# 默认启动命令
CMD ["python", "-m", "orchestrator.run_worker"]