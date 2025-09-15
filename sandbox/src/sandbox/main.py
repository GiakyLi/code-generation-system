# /sandbox/src/sandbox/main.py
# 技术审计与重构报告
#
# ### 1. 核心变更: 集成配置、日志和分布式追踪
#
# 这是Sandbox微服务的API入口。我们对其进行了全面的现代化改造, 使其成为一个健壮、
# 可观测的生产级服务。
#
# ### 2. 关键改进
#
# - **移除启动时镜像构建**: 最重要的变更是移除了`@app.on_event("startup")`中
#   构建Docker镜像的逻辑。如前所述, 这遵循了不可变基础设施原则, 极大地提高了
#   服务的启动速度和可靠性。现在, `startup`事件只用于打印一条日志, 确认服务
#   已成功启动。
#
# - **依赖注入**: `SandboxManager`和配置实例现在通过依赖注入的方式进行管理。
#   `get_settings`和`get_sandbox_manager`函数利用`lru_cache`来确保这些
#   昂贵的对象(如Docker客户端连接)在应用的生命周期内只被创建一次。
#   FastAPI的依赖注入系统会自动处理这些, 使得端点函数`execute_tests_endpoint`
#   的逻辑非常干净。
#
# - **分布式追踪中间件**: 我们添加了一个新的FastAPI中间件`LoggingMiddleware`。
#   它的作用是:
#   1. 检查传入请求的`X-Trace-ID`头。
#   2. 如果存在, 就将这个ID绑定到`structlog`的上下文中。
#   这意味着从这个请求处理开始, 直到它完成, 所有由该服务产生的日志都会自动
#   包含这个`trace_id`。这使得我们将Sandbox的日志与Orchestrator的日志关联
#   起来成为可能, 实现了端到端的追踪。
#
# - **健康检查端点**: 新增了`/health`端点。这个简单的端点返回`{"status": "ok"}`,
#   用于`docker-compose.yml`中的`healthcheck`。这比检查进程是否存在要可靠得多,
#   因为它能确认Web服务本身是否仍在正常响应请求。
#
# - **更完善的错误处理**: 端点中的`try...except`块现在能捕获我们自定义的
#   `SandboxExecutionError`, 并将其详细信息(包括stdout和stderr)格式化
#   到一个结构化的`SandboxResponse`中返回给调用者(Orchestrator)。
#   这为工作流提供了更丰富的失败上下文。

from functools import lru_cache
from typing import Any, Callable, Dict

import structlog
from common.logging import configure_logging, get_logger
from common.models import SandboxRequest, SandboxResponse
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware

from.config import get_settings
from.docker_manager import SandboxExecutionError, SandboxManager

# 在应用启动时配置日志
configure_logging(get_settings().LOG_LEVEL)
log = get_logger(__name__)

app = FastAPI(title="Secure Code Execution Sandbox")


# 使用lru_cache实现单例模式, 确保SandboxManager只被实例化一次
@lru_cache
def get_sandbox_manager() -> SandboxManager:
    return SandboxManager(settings=get_settings())


# 新增: 用于分布式追踪的中间件
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 清除上一个请求可能留下的上下文
        structlog.contextvars.clear_contextvars()
        # 从请求头中获取trace_id
        trace_id = request.headers.get("X-Trace-ID")
        if trace_id:
            # 将trace_id绑定到日志上下文中
            structlog.contextvars.bind_contextvars(trace_id=trace_id)
        response = await call_next(request)
        return response


app.add_middleware(LoggingMiddleware)


@app.on_event("startup")
async def startup_event() -> None:
    """
    应用启动事件。
    移除了动态构建镜像的逻辑, 现在只记录一条启动信息。
    """
    log.info(
        "Sandbox service starting up.",
        settings=get_settings().model_dump(),
    )
    # 预热Docker客户端连接
    try:
        get_sandbox_manager().client.ping()
        log.info("Successfully connected to Docker daemon.")
    except Exception:
        log.error("Failed to connect to Docker daemon on startup.", exc_info=True)
        # 在生产环境中, 这应该导致服务启动失败
        raise


@app.post(
    "/execute_tests", response_model=SandboxResponse, status_code=status.HTTP_200_OK
)
async def execute_tests_endpoint(
    request: SandboxRequest,
    sandbox_manager: SandboxManager = Depends(get_sandbox_manager),
) -> SandboxResponse:
    """接收代码和测试, 在安全的沙箱环境中执行它们, 并返回结果。"""
    log.info("Received request to execute tests.")
    try:
        result_json = await sandbox_manager.run_sandboxed_test(
            code_to_test=request.code_to_test,
            test_files_url=str(request.test_files_url),
        )
        return SandboxResponse(**result_json)
    except SandboxExecutionError as e:
        log.error(
            "Sandbox execution error occurred.",
            error=str(e),
            stdout=e.stdout,
            stderr=e.stderr,
        )
        return SandboxResponse(
            summary={"error": "Sandbox execution failed"},
            tests=,
            stdout=e.stdout,
            stderr=e.stderr,
            error=str(e),
        )
    except Exception:
        log.error("An unexpected internal error occurred.", exc_info=True)
        # 对于未知的服务器内部错误, 抛出HTTP500异常
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred in the sandbox.",
        )


# 新增: 健康检查端点
@app.get("/health", status_code=status.HTTP_200_OK)
def health_check() -> Dict[str, str]:
    """提供给容器编排系统(如Docker Compose, Kubernetes)的健康检查端点。"""
    return {"status": "ok"}