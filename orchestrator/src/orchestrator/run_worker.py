# /orchestrator/src/orchestrator/run_worker.py

import asyncio

from common.logging import configure_logging, get_logger
from temporalio.client import Client
from temporalio.worker import Worker

from .activities import (
    cleanup_successful_agent_artifacts,
    generate_code,
    parse_test_results,
    refine_prompt,
    run_tests_in_sandbox,
)
from .config import get_settings
from .workflows.agent_workflow import AgentFSMWorkflow
from .workflows.main_workflow import MainSagaWorkflow

# 在模块级别获取配置和日志记录器
settings = get_settings()
# 初始化日志系统
configure_logging(settings.LOG_LEVEL)
log = get_logger(__name__)


async def main() -> None:
    """主函数, 用于连接Temporal, 并启动Worker。"""
    try:
        # 使用从配置中获取的地址连接到Temporal服务器
        client = await Client.connect(settings.TEMPORAL_SERVER)
        log.info(
            "Successfully connected to Temporal server.",
            server_address=settings.TEMPORAL_SERVER,
        )

        # 创建一个Worker来监听指定的任务队列
        worker = Worker(
            client,
            task_queue=settings.TASK_QUEUE,
            # 修复: 注册需要执行的 Workflow
            workflows=[MainSagaWorkflow, AgentFSMWorkflow],
            activities=[
                generate_code,
                run_tests_in_sandbox,
                parse_test_results,
                refine_prompt,
                cleanup_successful_agent_artifacts,
            ],
        )
        log.info("Worker started.", task_queue=settings.TASK_QUEUE)
        await worker.run()
    except Exception:
        log.error("Worker failed to start or run.", exc_info=True)
        # 在生产环境中, 这里可能需要一个重启策略或告警机制
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Worker shutting down gracefully.")