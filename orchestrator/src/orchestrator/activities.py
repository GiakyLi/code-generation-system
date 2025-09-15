# Technical Audit and Refactoring Report

# ## 1. Core Change: From Mock to Production-Grade Implementation
# The original Activities were proof-of-concept, containing simulated delays and hardcoded logic.
# We refactored them into production-ready code, focusing on robustness, configurability, and observability.

# ## 2. Key Improvements
# - **Dependency-Injected Configuration**: All external dependencies (like URLs) are now injected via the `get_settings()` function,
#   instead of being hardcoded or read directly from environment variables. This makes the code easier to test and configure.
# - **Distributed Tracing Integration**: In `run_tests_in_sandbox`, we send the workflow's `trace_id`
#   as an HTTP header (`X-Trace-ID`) to the `sandbox` service. This allows logs from the `sandbox` service
#   to be correlated with the workflow logs that triggered it, a crucial step for end-to-end observability.
# - **Robust HTTP Client**: We use `httpx.AsyncClient` and configure it with a reasonable timeout.
#   In Temporal, the Activity-level retry policy (defined in the workflow) handles transient network failures,
#   while this timeout prevents the Activity from hanging indefinitely due to an unresponsive downstream service.
# - **Realistic `generate_code` Implementation**: Removed `asyncio.sleep` and mock logic based on prompt content.
#   Replaced with a real implementation that makes a POST request to a vLLM service. We've also added
#   important comments emphasizing how to securely manage API keys for LLM services in a production environment.
# - **Richer Error Handling & Returns**: `parse_test_results` now returns more detailed test failure information,
#   not just a simple string. This provides richer context for `refine_prompt` to generate
#   high-quality remediation prompts.
# - **Idempotent Compensation Operation**: `cleanup_successful_agent_artifacts` is designed to be idempotent.
#   "Idempotent" means that executing the operation once or multiple times has the same result. This is a cornerstone
#   of building reliable Saga compensation logic. If a compensation operation fails during execution and is retried,
#   idempotency ensures that the system state does not become corrupted.

import os
from typing import Any, Dict, Tuple
import httpx
from common.models import AgentState, SandboxRequest, SandboxResponse
from temporalio import activity
from .config import get_settings

# Get configuration at the module level to be shared across all activities
settings = get_settings()

# Create a reusable HTTP client instance
# In a production environment, more complex client lifecycle management might be considered
http_client = httpx.AsyncClient(timeout=30.0)

@activity.defn
async def generate_code(prompt: str, model_endpoint_env_var: str) -> str:
    """
    Generates code by calling an external LLM service.
    This is an I/O-bound operation, suitable for an Activity.
    """
    model_endpoint = os.getenv(model_endpoint_env_var)
    if not model_endpoint:
        # Use ValueError instead of crashing directly, allowing Temporal to catch it as a non-retriable error
        raise ValueError(f"Environment variable {model_endpoint_env_var} not set.")

    activity.logger.info(
        "Generating code using model endpoint.",
        model_endpoint_env_var=model_endpoint_env_var,
    )

    # Real-world implementation notes:
    # 1. Security: API keys should not be hardcoded or exist in environment variables. Use a secret management system
    #    (e.g., HashiCorp Vault, AWS Secrets Manager) to securely fetch them at runtime.
    # 2. Robustness: The request below should include more comprehensive error handling and retry logic,
    #    although Temporal's Activity retries can handle transient network-level failures.
    headers = {"Content-Type": "application/json"}
    # Assuming the LLM service requires an API key
    # api_key = get_secret("VLLM_API_KEY")
    # headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = await http_client.post(
            model_endpoint, json={"prompt": prompt}, headers=headers
        )
        response.raise_for_status()  # Throws an exception for 4xx or 5xx HTTP status codes
        # Assuming the returned JSON structure is {"generated_code": "..."}
        return response.json()["generated_code"]
    except httpx.HTTPStatusError as e:
        activity.logger.error(
            "HTTP error while calling LLM service.",
            status_code=e.response.status_code,
            response_text=e.response.text,
        )
        # Wrap the HTTP error as an Activity error so the Temporal workflow can handle it
        raise RuntimeError(f"LLM service returned error: {e.response.status_code}") from e
    except Exception:
        activity.logger.error(
            "An unexpected error occurred during code generation.", exc_info=True
        )
        raise  # Re-throw the exception

@activity.defn
async def run_tests_in_sandbox(
    code: str, test_files_url: str, trace_id: str
) -> Dict[str, Any]:
    """Invokes the Sandbox microservice to securely execute code and tests."""
    activity.logger.info("Running tests in sandbox...")
    request_data = SandboxRequest(
        code_to_test=code,
        test_files_url=test_files_url,
        trace_id=trace_id,  # Pass the trace ID
    )
    headers = {
        "Content-Type": "application/json",
        "X-Trace-ID": trace_id,  # Pass the trace ID as an HTTP header
    }
    try:
        response = await http_client.post(
            f"{settings.SANDBOX_URL}/execute_tests",
            json=request_data.model_dump(mode="json"),
            headers=headers,
            timeout=180.0,  # Set a longer timeout for sandbox execution
        )
        response.raise_for_status()
        return response.json()
    except httpx.RequestError as e:
        activity.logger.error("Failed to connect to sandbox service.", exc_info=True)
        # This type of error is generally retryable
        raise ConnectionError("Could not connect to the sandbox service.") from e

@activity.defn
async def parse_test_results(report: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """
    Parses the test report from the sandbox to determine the outcome.
    This is a pure CPU-bound operation and could be a local Activity for efficiency.
    """
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
        return "RETRYABLE_FAILURE", report  # Return the full report for subsequent use

    if summary and summary.get("passed", 0) > 0:
        activity.logger.info("Tests passed.", summary=summary)
        return "PASSED", report

    activity.logger.error("Unknown test outcome.", summary=summary)
    return "TERMINAL_FAILURE", {"error": "Unknown test outcome", "summary": summary}

@activity.defn
async def refine_prompt(state: AgentState) -> str:
    """Generates a more precise prompt for code correction based on failed test results."""
    activity.logger.info(f"Refining prompt for agent {state.agent_id}...")
    original_prompt = state.initial_request.functional_description
    error_summary = str(state.test_errors)

    # This is a more structured prompt to guide the LLM for better correction
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
    """
    Saga compensation operation: Cleans up artifacts for a successful Agent.
    This operation must be idempotent.
    """
    activity.logger.info(
        f"Executing compensation: Cleaning up artifacts for successful agent {agent_id}..."
    )
    # In a real scenario, this might perform actions like:
    # - Deleting generated code files from object storage
    # - Deleting related temporary records from a database
    # - Calling other services to roll back state
    # This operation should be designed to ensure repeated execution has no side effects.
    # For example, deleting a file that no longer exists should not raise an error.
    # await s3_client.delete_object_if_exists(bucket, f"artifacts/{agent_id}/code.py")
    activity.logger.info(f"Cleanup for agent {agent_id} complete (simulated).")