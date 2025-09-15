# /orchestrator/src/orchestrator/activities.py

import os
from typing import Any, Dict, Tuple
import httpx
from common.models import AgentState, SandboxRequest, SandboxResponse
from temporalio import activity
from .config import get_settings

settings = get_settings()

http_client = httpx.AsyncClient(timeout=30.0)

@activity.defn
async def generate_code(prompt: str, model_endpoint_env_var: str) -> str:
    """Activity: 调用外部大语言模型服务生成代码。"""
    model_endpoint = os.getenv(model_endpoint_env_var)
    if not model_endpoint:
        # 如果环境变量未设置，则抛出不可重试的错误。
        raise ValueError(f"Environment variable {model_endpoint_env_var} not set.")

    activity.logger.info(
        "Generating code using model endpoint.",
        model_endpoint_env_var=model_endpoint_env_var,
    )

    headers = {"Content-Type": "application/json"}

    try:
        response = await http_client.post(
            model_endpoint, json={"prompt": prompt}, headers=headers
        )
        response.raise_for_status()
        return response.json()["generated_code"]
    except httpx.HTTPStatusError as e:
        activity.logger.error(
            "HTTP error while calling LLM service.",
            status_code=e.response.status_code,
            response_text=e.response.text,
        )
        raise RuntimeError(f"LLM service returned error: {e.response.status_code}") from e
    except Exception:
        activity.logger.error(
            "An unexpected error occurred during code generation.", exc_info=True
        )
        raise

@activity.defn
async def run_tests_in_sandbox(
    code: str, test_files_url: str, trace_id: str
) -> Dict[str, Any]:
    """Activity: 调用沙箱微服务以安全地执行代码和测试。"""
    activity.logger.info("Running tests in sandbox...")
    request_data = SandboxRequest(
        code_to_test=code,
        test_files_url=test_files_url,
        trace_id=trace_id,
    )
    # 将 trace_id 作为 HTTP 头部传递，用于分布式追踪。
    headers = {
        "Content-Type": "application/json",
        "X-Trace-ID": trace_id,
    }
    try:
        response = await http_client.post(
            f"{settings.SANDBOX_URL}/execute_tests",
            json=request_data.model_dump(mode="json"),
            headers=headers,
            timeout=180.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.RequestError as e:
        activity.logger.error("Failed to connect to sandbox service.", exc_info=True)
        raise ConnectionError("Could not connect to the sandbox service.") from e

@activity.defn
async def parse_test_results(report: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Activity: 解析沙箱返回的测试报告，判断最终结果。"""
    activity.logger.info("Parsing test results...")
    sandbox_response = SandboxResponse(**report)

    if sandbox_response.error:
        activity.logger.error(
            "Sandbox reported a terminal execution error.",
            error=sandbox_response.error,
        )
        return "TERMINAL_FAILURE", {"error": sandbox_response.error}

    summary = sandbox_response.summary
    if summary and summary.get("failed", 0) > 0:
        activity.logger.warning("Tests failed.", summary=summary)
        # 测试失败，但可以重试。返回完整报告供后续步骤使用。
        return "RETRYABLE_FAILURE", report

    if summary and summary.get("passed", 0) > 0:
        activity.logger.info("Tests passed.", summary=summary)
        return "PASSED", report

    activity.logger.error("Unknown test outcome.", summary=summary)
    return "TERMINAL_FAILURE", {"error": "Unknown test outcome", "summary": summary}

@activity.defn
async def refine_prompt(state: AgentState) -> str:
    """Activity: 根据失败的测试结果，生成一个用于代码修正的、更精确的提示。"""
    activity.logger.info(f"Refining prompt for agent {state.agent_id}...")
    original_prompt = state.initial_request.functional_description
    error_summary = str(state.test_errors)

    return f"""
The original task was: {original_prompt}

The following code was generated but failed the tests:
```python
{state.faulty_code}
```

The test execution failed with the following results:
{error_summary}

Based on the test errors, please provide a corrected version of the Python code.
Only output the raw Python code, without any explanations or markdown formatting.
"""

@activity.defn
async def cleanup_successful_agent_artifacts(agent_id: str) -> None:
    """Saga 补偿操作: 清理成功 Agent 留下的产物。此操作必须是幂等的。"""
    activity.logger.info(
        f"Executing compensation: Cleaning up artifacts for successful agent {agent_id}..."
    )
    # 此处应包含实际的清理逻辑，例如从对象存储中删除文件。
    activity.logger.info(f"Cleanup for agent {agent_id} complete (simulated).")