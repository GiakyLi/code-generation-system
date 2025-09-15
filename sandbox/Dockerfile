# /sandbox/Dockerfile
# 技术审计与重构报告
#
# ### 1. 核心变更: 遵循不可变基础设施原则
#
# 原始的`sandbox`服务在启动时会动态构建其用于执行测试的Docker镜像。
# 这是一个严重的反模式, 它导致:
# - **启动缓慢**: 每次服务启动都需要等待镜像构建完成。
# - **不可靠**: 构建过程可能因网络问题或基础镜像变更而失败, 导致服务无法启动。
# - **状态不一致**: 不同实例的`sandbox`服务可能因为构建时间不同而拥有不一样的
#   测试环境镜像, 破坏了环境的一致性。
#
# ### 2. 重构策略
#
# 我们彻底移除了在容器内构建镜像的逻辑。
#
# - **预构建镜像**: 测试环境镜像(`test-execution-env`)现在通过`docker-compose.yml`
#   中的一个独立服务块进行构建。在生产CI/CD流程中, 这个镜像应该被构建、标记版本、
#   进行安全扫描, 然后推送到一个集中的容器镜像仓库(如ECR, GCR, Docker Hub)。
#
# - **运行时拉取**: `sandbox`服务现在只负责在运行时从镜像仓库(或本地缓存)
#   拉取并使用这个预先构建好的、不可变的镜像。
#
# - **移除构建工具**: 这个`sandbox`服务的Dockerfile不再需要复制`test_env.Dockerfile`,
#   因为它不再负责构建任务。
#
# 这种转变遵循了“不可变基础设施”的核心原则: 一旦部署, 基础设施(在这里是Docker镜像)
# 就不应再被更改。任何变更都应该通过构建一个新的镜像并重新部署来实现。
# 这极大地提高了系统的可预测性、可靠性和安全性。

FROM python:3.11-slim

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=false \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONUNBUFFERED=1

ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

RUN pip install poetry

# 优先复制并安装依赖, 以利用Docker的层缓存机制
COPY pyproject.toml poetry.lock./
COPY../common/pyproject.toml../common/poetry.lock./common/
RUN poetry install --no-root --no-dev

# 复制应用程序源代码
COPY./src./src
COPY../common/src./common/src

# 默认启动命令
CMD ["uvicorn", "sandbox.main:app", "--host", "0.0.0.0", "--port", "8000"]