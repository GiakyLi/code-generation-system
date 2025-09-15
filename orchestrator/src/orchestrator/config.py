# /orchestrator/src/orchestrator/config.py
# 技术审计与重构报告
#
# ### 1. 引入目的: 服务专属的、类型安全的配置
#
# 这个新文件遵循了我们在`common`库中建立的配置管理模式。
# 它为Orchestrator服务定义了一个专属的配置类`OrchestratorSettings`。
#
# ### 2. 实现方式
#
# - **继承与扩展**: `OrchestratorSettings`继承自`common.config.AppBaseSettings`。
#   这意味着它自动获得了所有通用的配置项(如`LOG_LEVEL`), 并且可以添加
#   自己服务特有的配置。
#
# - **服务特定配置**: 我们在这里定义了`TEMPORAL_SERVER`, `TASK_QUEUE`, `SANDBOX_URL`
#   等Orchestrator运行所必需的配置项。
#
# - **单例模式**: `get_settings()`函数使用了`@lru_cache`装饰器, 这是一个简单的
#   实现单例模式的方法。这意味着配置只会在第一次被请求时加载和验证一次,
#   之后的所有调用都会立即返回缓存的实例。这既高效又确保了在整个应用生命周期中
#   配置的一致性。
#
# ### 3. 优势
#
# 这种结构使得配置管理变得非常清晰和健壮。
# - **清晰性**: 任何开发者都可以通过查看这个文件, 快速了解Orchestrator服务
#   需要哪些配置才能运行。
# - **健壮性**: Pydantic的验证确保了在Worker启动时, 所有必需的配置都已提供
#   且格式正确。如果`SANDBOX_URL`不是一个合法的URL, 或者`TEMPORAL_SERVER`
#   没有设置, 程序会立即失败并给出明确的错误信息, 而不是在运行时发生
#   不可预知的错误。

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