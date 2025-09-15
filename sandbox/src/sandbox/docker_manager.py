# /sandbox/src/sandbox/docker_manager.py

import asyncio
import os
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
                # 优化: 逐个安全地解压成员
                for member in tar.getmembers():
                    member_path = os.path.join(path, member.name)
                    # 安全检查：确保解压路径在目标目录内
                    if not os.path.abspath(member_path).startswith(os.path.abspath(path)):
                        raise SandboxExecutionError(f"Malicious tar file detected: {member.name}")
                    tar.extract(member, path=path)
        except httpx.RequestError as e:
            raise SandboxExecutionError(
                f"Failed to download test files from {url}"
            ) from e
        except tarfile.TarError as e:
            raise SandboxExecutionError(
                "Failed to extract test files. Ensure it's a valid tar archive."
            ) from e