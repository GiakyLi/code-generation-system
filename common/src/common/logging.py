# /common/src/common/logging.py

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
    shared_processors: list[structlog.types.Processor] = [
        # 将trace_id等上下文变量添加到日志记录中
        structlog.contextvars.merge_contextvars,
        # 添加日志记录器名称
        structlog.stdlib.add_logger_name,
        # 添加日志级别
        structlog.stdlib.add_log_level,
        # 添加ISO格式的时间戳
        structlog.processors.TimeStamper(fmt="iso"),
    ]

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