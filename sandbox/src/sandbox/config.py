# /sandbox/src/sandbox/config.py
# 技术审计与重构报告
#
# ### 1. 引入目的: 为Sandbox服务提供类型安全的配置
#
# 与Orchestrator类似, 这个新文件为Sandbox服务提供了专属的、经过验证的配置管理。
#
# ### 2. 实现方式
#
# - **继承与扩展**: `SandboxSettings`继承自`common.config.AppBaseSettings`,
#   获得了通用的`LOG_LEVEL`配置。
#
# - **服务特定配置**:
#   - `DOCKER_HOST`: 这是与安全重构最相关的配置。它指定了Docker客户端应该
#     连接的Docker守护进程地址。在我们的新架构中, 它将指向隔离的DinD
#     服务的地址(如`tcp://dind:2375`), 而不是默认的Unix套接字。
#     如果此变量未设置, 代码将无法启动, 从而强制执行安全配置。
#
#   - `SANDBOX_TEST_IMAGE_TAG`: 指定用于执行测试的、预先构建好的Docker镜像。
#     这遵循了不可变基础设施的原则。
#
#   - `SANDBOX_EXECUTION_TIMEOUT`: 为代码执行设置一个全局的超时限制,
#     防止恶意或有缺陷的代码(如无限循环)耗尽系统资源。
#
# - **单例模式**: 同样使用`@lru_cache`的`get_settings()`函数来确保配置在
#   应用生命周期内只被加载和验证一次。
#
# ### 3. 优势
#
# 这种模式将所有可调参数集中管理, 使得Sandbox服务的行为变得可预测和易于配置。
# 通过强制要求`DOCKER_HOST`的设置, 我们在代码层面也加强了安全策略,
# 防止开发者无意中回退到不安全的Docker-out-of-Docker模式。

from functools import lru_cache

from common.config import AppBaseSettings
from pydantic import Field


class SandboxSettings(AppBaseSettings):
    """Sandbox服务的特定配置。"""

    # 关键安全配置: 指定要连接的Docker守护进程地址。
    # 在生产环境中, 这应该指向隔离的DinD服务。
    DOCKER_HOST: str

    # 用于执行测试的Docker镜像标签
    SANDBOX_TEST_IMAGE_TAG: str = "test-execution-env:latest"

    # 在沙箱容器内执行测试的最大超时时间(秒)
    SANDBOX_EXECUTION_TIMEOUT: int = Field(default=60, gt=0, le=300)


@lru_cache
def get_settings() -> SandboxSettings:
    """获取并缓存Sandbox的配置实例。"""
    return SandboxSettings()