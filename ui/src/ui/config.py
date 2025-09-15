# /ui/src/ui/config.py
# 技术审计与重构报告
#
# ### 1. 引入目的: 为UI服务提供类型安全的配置
#
# 与其他服务一样, 这个新文件为UI服务提供了专属的、经过验证的配置管理。
#
# ### 2. 实现方式
#
# - **继承与扩展**: `UISettings`继承自`common.config.AppBaseSettings`。
#
# - **服务特定配置**:
#   - `UI_TEMPORAL_SERVER`: UI服务连接Temporal前端所需的地址。
#     注意, 这个值可能与Orchestrator worker使用的地址不同。
#     例如, 在Kubernetes中, Worker可能通过内部服务名连接, 而UI
#     可能需要通过一个外部可访问的地址(如Ingress)连接。
#     将它们区分为两个不同的配置变量提供了这种灵活性。
#
#   - `TASK_QUEUE`: 指定启动工作流时要发送到的任务队列名称。
#
# - **单例模式**: 同样使用`@lru_cache`的`get_settings()`函数。
#
# ### 3. 优势
#
# 这种模式确保了UI服务的配置是集中、明确且经过验证的,
# 避免了在应用代码中硬编码配置值。

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