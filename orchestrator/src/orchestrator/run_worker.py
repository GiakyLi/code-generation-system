# /orchestrator/src/orchestrator/run_worker.py
# 技术审计与重构报告
#
# ### 1. 核心变更: 集成配置和日志系统
#
# 这是Orchestrator服务的入口点。我们对其进行了重构, 以集成新的、
# 生产级的配置和日志系统, 取代了原始的硬编码值和`print()`语句。
#
# ### 2. 实现细节
#
# - **启动时配置加载**: 程序开始时, 首先调用`get_settings()`来加载和验证所有
#   必要的环境变量。如果任何配置缺失或无效, 服务将无法启动并立即报错,
#   这遵循了“快速失败”原则。
#
# - **结构化日志初始化**: 紧接着, `configure_logging()`被调用, 并传入从配置中
#   获取的`LOG_LEVEL`。这确保了整个Worker的所有日志(包括Temporal客户端的日志)
#   都将遵循我们在`common`库中定义的结构化JSON格式。
#
# - **优雅关闭(Graceful Shutdown)**: 原始代码中已经包含了`try...except KeyboardInterrupt`
#   逻辑, 这是一个很好的实践。我们保留了它, 以确保在手动停止Worker时
#   (例如通过Ctrl+C), 它能够优雅地关闭, 完成正在处理的任务。
#
# ### 3. 优势
#
# 这个重构后的入口点更加健壮和可维护。
# - **可配置性**: 现在可以通过环境变量轻松地更改Temporal服务器地址、任务队列名称
#   和日志级别, 而无需修改任何代码。
# - **可观测性**: 所有输出都是结构化的JSON日志, 为后续的日志聚合、监控和告警
#   打下了坚实的基础。
# - **可靠性**: 启动时验证配置, 防止服务在配置错误的情况下运行。

import asyncio

from common.logging import configure_logging, get_logger
from temporalio.client import Client
from temporalio.worker import Worker

from.activities import (
    cleanup_successful_agent_artifacts,
    generate_code,
    parse_test_results,
    refine_prompt,
    run_tests_in_sandbox,
)
from.config import get_settings
from.workflows.agent_workflow import AgentFSMWorkflow
from.workflows.main_workflow import MainSagaWorkflow

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
            workflows=,
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