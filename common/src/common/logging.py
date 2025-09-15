# /common/src/common/logging.py
# 技术审计与重构报告
#
# ### 1. 引入目的: 实现生产级的结构化日志
#
# 原始代码中的日志记录方式是`print()`或Python标准`logging`模块的简单使用。
# 在一个由多个微服务组成的分布式系统中, 这种非结构化的日志是调试和监控的噩梦。
# 当问题发生时, 工程师需要在多个服务的、格式各异的文本日志中手动搜索,
# 难以关联一次请求在不同服务间的完整调用链。
#
# ### 2. 解决方案: Structlog
#
# 我们引入`structlog`库来建立一个统一的、结构化的日志系统。
#
# - **JSON格式输出**: `configure_logging`函数将日志配置为输出JSON格式。
#   JSON日志可以被现代日志聚合工具(如Elasticsearch, Loki, Datadog, Splunk)
#   轻松地解析、索引和查询。
#
# - **上下文关联(Contextual Logging)**: `structlog`的核心优势是能够将上下文信息
#   (如`trace_id`, `workflow_id`, `user_id`)绑定到日志记录器。
#   这意味着一旦在请求开始时注入了`trace_id`, 后续在该请求处理过程中的所有日志
#   都会自动带上这个ID。
#
# ### 3. 对可观测性的巨大提升
#
# 这种改变将调试过程从“大海捞针”转变为“精确制导”。当用户报告一个问题时,
# 我们可以根据UI提供的`workflow_id`(其中包含了`trace_id`), 在日志系统中
# 过滤出`trace_id=<some-id>`, 立即就能看到这次请求从UI发起, 到Orchestrator
# 工作流的每一步, 再到Sandbox执行测试的完整、按时间排序的日志流。
#
# 这是从简单的“日志记录”到真正的“系统可观测性”的飞跃, 是任何生产级分布式系统
# 不可或缺的能力。

import logging
import sys
from typing import Any

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """
    配置全局的结构化日志系统(structlog)。

    Args:
        log_level: 日志级别(e.g., "INFO", "DEBUG").
    """
    # 共享的处理器链, 用于所有日志记录器
    shared_processors: list[structlog.types.Processor] =

    structlog.configure(
        processors=shared_processors
        + [
            # 将日志记录最终交给标准的logging模块处理
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        # 使用缓存的记录器工厂以提高性能
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 配置标准的logging模块, 使其与structlog协同工作
    formatter = structlog.stdlib.ProcessorFormatter(
        # 定义最终输出的处理器, 这里我们使用JSON格式
        processor=structlog.processors.JSONRenderer(),
        # 如果需要, 可以保留原始的`logging.LogRecord`字段
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())

    # 将关键库的日志级别调高, 以减少噪音
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("temporalio").setLevel(logging.WARNING)


def get_logger(name: str) -> Any:
    """
    获取一个配置好的structlog日志记录器。

    Args:
        name: 日志记录器的名称, 通常是模块名`__name__`

    Returns:
        一个structlog日志记录器实例。
    """
    return structlog.get_logger(name)