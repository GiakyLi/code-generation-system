# /sandbox/src/sandbox/main.py

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
            tests=[],
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