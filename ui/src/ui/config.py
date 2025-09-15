# /ui/src/ui/config.py

from functools import lru_cache

from common.config import AppBaseSettings


class UISettings(AppBaseSettings):
    """UI服务的特定配置。"""

    # 从UI容器连接到Temporal服务器的地址
    UI_TEMPORAL_SERVER: str = "temporal:7233"
    TASK_QUEUE: str = "code-generation-task-queue"


@lru_cache
def get_settings() -> UISettings:
    """获取并缓存UI的配置实例。"""
    return UISettings()