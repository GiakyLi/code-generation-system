# /orchestrator/src/orchestrator/config.py

from functools import lru_cache

from common.config import AppBaseSettings
from pydantic import HttpUrl


class OrchestratorSettings(AppBaseSettings):
    """Orchestrator服务的特定配置。"""

    TEMPORAL_SERVER: str = "localhost:7233"
    TASK_QUEUE: str = "code-generation-task-queue"
    SANDBOX_URL: HttpUrl = "http://localhost:8000"
    # 定义模型端点的环境变量名, 而不是硬编码URL, 增强灵活性和安全性
    VLLM_MODEL_A_ENV_VAR: str = "VLLM_MODEL_A_URL"
    VLLM_MODEL_B_ENV_VAR: str = "VLLM_MODEL_B_URL"


@lru_cache
def get_settings() -> OrchestratorSettings:
    """
    获取并缓存Orchestrator的配置实例。
    使用lru_cache确保配置只被加载一次(单例模式)。
    """
    return OrchestratorSettings()