# /sandbox/src/sandbox/config.py

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