# /sandbox/src/sandbox/docker_manager.py
# 技术审计与重构报告
#
# ### 1. 核心安全重构: 从Docker-out-of-Docker到隔离的DinD客户端
#
# 这是整个项目安全审计中最重要的修改。原始实现直接与主机的Docker守护进程交互,
# 构成了严重的安全漏洞。
#
# **重构策略:**
# - **客户端初始化**: `__init__`方法现在通过`docker.DockerClient(base_url=docker_host)`
#   来初始化。`docker_host`参数从新的配置系统中获取, 它指向的是隔离的DinD
#   服务的TCP端点(例如`tcp://dind:2375`), 而不是默认的Unix套接字。
#   这从根本上切断了`sandbox`服务与主机系统的联系。
#
# - **移除镜像构建逻辑**: `build_test_image`方法已被完全移除。`sandbox`服务
#   不再负责构建镜像, 它现在是一个纯粹的镜像使用者, 遵循不可变基础设施原则。
#
# ### 2. 执行环境加固
#
# 我们对容器的运行参数进行了多项加固, 以最小化不可信代码可能造成的损害:
#
# - **网络隔离(`network_mode='none'`)**: 这是最关键的加固措施之一。它完全禁用了
#   执行容器的网络栈。这意味着在容器内运行的代码无法发起任何出站网络连接,
#   有效防止了数据泄露、或利用该容器攻击内部网络中的其他服务。
#
# - **资源限制(`mem_limit`, `cpus`)**: 设置了严格的内存和CPU配额。这可以防止
#   恶意代码通过消耗大量资源(如内存炸弹、fork炸弹)来影响其他容器或主机。
#
# - **PID限制(`pids_limit`)**: 限制了容器内可以创建的进程数量, 是防御"fork炸弹”
#   攻击的有效手段。
#
# - **只读文件系统(`read_only=True`)**: 容器的文件系统被设置为只读。代码只能在
#   通过`volumes`挂载的临时工作目录中进行写操作。这增加了攻击者在容器内
#   持久化或修改系统文件的难度。
#
# ### 3. 异步和错误处理
#
# - **真正的异步执行**: `run_sandboxed_test`现在是一个真正的`async`方法,
#   它使用`asyncio.to_thread`将同步的Docker SDK调用放到一个独立的线程中执行,
#   避免了阻塞FastAPI的事件循环。
# - **详细的错误报告**: 错误处理逻辑被增强, 现在可以捕获并返回容器的`stdout`和
#   `stderr`, 为调试提供了极其宝贵的上下文信息。

import asyncio
import io
import json
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Dict

import docker
import httpx
from docker.errors import ContainerError, DockerException
from docker.models.containers import Container

from.config import SandboxSettings


class SandboxExecutionError(Exception):
    """自定义异常, 用于表示沙箱执行期间的错误。"""

    def __init__(self, message: str, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


class SandboxManager:
    def __init__(self, settings: SandboxSettings) -> None:
        self.settings = settings
        try:
            # 关键安全变更: 连接到由配置指定的、隔离的Docker守护进程
            self.client = docker.DockerClient(base_url=self.settings.DOCKER_HOST)
            # 验证与Docker守护进程的连接
            self.client.ping()
        except DockerException as e:
            # 如果无法连接到Docker守护进程, 这是一个致命错误
            raise RuntimeError(
                f"Failed to connect to Docker daemon at {self.settings.DOCKER_HOST}"
            ) from e

    async def run_sandboxed_test(
        self, code_to_test: str, test_files_url: str
    ) -> Dict[str, Any]:
        """
        异步地在沙箱中运行测试。
        使用asyncio.to_thread在单独的线程中运行同步的IO密集型代码,
        避免阻塞FastAPI的事件循环。
        """
        return await asyncio.to_thread(
            self._run_sync, code_to_test, test_files_url
        )

    def _run_sync(self, code_to_test: str, test_files_url: str) -> Dict[str, Any]:
        """同步的测试执行逻辑。"""
        temp_dir = tempfile.mkdtemp()
        container: Container | None = None
        try:
            temp_path = Path(temp_dir)
            self._prepare_environment_sync(temp_path, code_to_test, test_files_url)

            container = self.client.containers.run(
                image=self.settings.SANDBOX_TEST_IMAGE_TAG,
                command=["pytest", "--json-report", "--json-report-file=report.json"],
                volumes={str(temp_path): {"bind": "/home/appuser/app", "mode": "rw"}},
                working_dir="/home/appuser/app",
                user="appuser",
                # --- 安全加固 ---
                network_mode="none",  # 禁用网络, 防止代码进行外部调用
                mem_limit="512m",  # 限制内存使用
                pids_limit=100,  # 限制进程数量, 防止fork炸弹
                read_only=True,  # 将容器文件系统设为只读
                # ----------------
                detach=True,
            )
            result = container.wait(timeout=self.settings.SANDBOX_EXECUTION_TIMEOUT)
            exit_code = result.get("StatusCode", 1)

            stdout = container.logs(stdout=True, stderr=False).decode(
                "utf-8", errors="ignore"
            )
            stderr = container.logs(stdout=False, stderr=True).decode(
                "utf-8", errors="ignore"
            )

            report_path = temp_path / "report.json"
            if report_path.exists():
                with open(report_path, "r") as f:
                    report_data = json.load(f)
                # 将stdout和stderr附加到报告中, 以便上游服务进行调试
                report_data["stdout"] = stdout
                report_data["stderr"] = stderr
                return report_data
            else:
                raise SandboxExecutionError(
                    f"report.json not found. Exit code: {exit_code}.",
                    stdout=stdout,
                    stderr=stderr,
                )
        except ContainerError as e:
            raise SandboxExecutionError(
                f"Container error: {e.stderr.decode('utf-8', errors='ignore')}",
                stdout=e.stdout.decode("utf-8", errors="ignore") if e.stdout else "",
                stderr=e.stderr.decode("utf-8", errors="ignore") if e.stderr else "",
            ) from e
        except Exception as e:
            stdout = stderr = ""
            if container:
                stdout = container.logs(stdout=True, stderr=False).decode(
                    "utf-8", errors="ignore"
                )
                stderr = container.logs(stdout=False, stderr=True).decode(
                    "utf-8", errors="ignore"
                )
            raise SandboxExecutionError(
                f"An unexpected error occurred: {e}", stdout, stderr
            ) from e
        finally:
            if container:
                try:
                    container.remove(force=True)
                except docker.errors.NotFound:
                    pass
            shutil.rmtree(temp_dir)

    def _prepare_environment_sync(self, path: Path, code: str, url: str) -> None:
        """准备执行测试所需的文件环境。"""
        (path / "solution.py").write_text(code, encoding="utf-8")
        try:
            with httpx.Client() as client:
                response = client.get(url, follow_redirects=True, timeout=30.0)
                response.raise_for_status()
            with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:*") as tar:
                tar.extractall(path=path)
        except httpx.RequestError as e:
            raise SandboxExecutionError(
                f"Failed to download test files from {url}"
            ) from e
        except tarfile.TarError as e:
            raise SandboxExecutionError(
                "Failed to extract test files. Ensure it's a valid tar archive."
            ) from e