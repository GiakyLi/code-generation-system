# /orchestrator/src/orchestrator/workflows/agent_workflow.py

from datetime import timedelta
from typing import Dict, Optional

from common.models import AgentState, AgentStatus
from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

# 将Activity的定义移到工作流外部, 以便更好地组织代码
# 并为每个Activity定义健壮的重试策略
generate_code = activity.create(
    name="generate_code",
    start_to_close_timeout=timedelta(minutes=5),
    retry_policy=RetryPolicy(
        maximum_attempts=3,
        non_retryable_error_types=["ValueError"],  # 配置错误不应重试
    ),
)
run_tests_in_sandbox = activity.create(
    name="run_tests_in_sandbox",
    start_to_close_timeout=timedelta(minutes=3),
    retry_policy=RetryPolicy(
        maximum_attempts=5,
        initial_interval=timedelta(seconds=5),
        backoff_coefficient=2.0,
    ),
)
parse_test_results = activity.create(
    name="parse_test_results",
    start_to_close_timeout=timedelta(seconds=30),
)
refine_prompt = activity.create(
    name="refine_prompt",
    start_to_close_timeout=timedelta(minutes=2),
)


@workflow.defn
class AgentFSMWorkflow:
    def __init__(self) -> None:
        self._state: Optional = None
        self._status: str = "PENDING"
        self._last_test_summary: Dict = {}

    @workflow.run
    async def execute(self, state: AgentState) -> str:
        """执行有限状态机(FSM)工作流, 用于单个Agent的代码生成和测试循环。"""
        self._state = state
        workflow.logger.info(
            f"[{self._state.agent_id}] FSM workflow started.",
            trace_id=self._state.trace_id,
        )

        for i in range(self._state.max_iterations):
            self._state.current_iteration = i + 1
            workflow.logger.info(
                f"[{self._state.agent_id}] Starting iteration "
                f"{self._state.current_iteration}/{self._state.max_iterations}."
            )

            # 1. 状态: 生成或优化提示
            self._status = (
                "REFINING_PROMPT" if self._state.faulty_code else "GENERATING_CODE"
            )
            if self._state.faulty_code:
                prompt = await refine_prompt(self._state)
            else:
                prompt = self._state.initial_request.functional_description

            # 2. 状态: 生成代码
            self._status = "GENERATING_CODE"
            generated_code = await generate_code(
                prompt, self._state.model_endpoint_env_var
            )
            self._state.faulty_code = generated_code

            # 3. 状态: 在沙箱中运行测试
            self._status = "TESTING"
            test_report_dict = await run_tests_in_sandbox(
                generated_code,
                str(self._state.initial_request.test_files_url),
                self._state.trace_id,
            )
            self._last_test_summary = test_report_dict.get("summary", {})

            # 4. 状态: 解析测试结果
            self._status = "PARSING_RESULTS"
            outcome, report_details = await parse_test_results(test_report_dict)

            if outcome == "PASSED":
                self._status = "SUCCESS"
                workflow.logger.info(
                    f"[{self._state.agent_id}] Tests passed on attempt {self._state.current_iteration}."
                )
                return generated_code
            elif outcome == "TERMINAL_FAILURE":
                self._status = "FAILED"
                workflow.logger.error(
                    f"[{self._state.agent_id}] Terminal failure detected.",
                    details=report_details,
                )
                raise ApplicationError(
                    f"[{self._state.agent_id}] Unrecoverable error in code or tests.",
                    non_retryable=True,
                )
            else:  # RETRYABLE_FAILURE
                self._state.test_errors = report_details
                workflow.logger.warning(
                    f"[{self._state.agent_id}] Retriable failure on attempt {self._state.current_iteration}."
                )
                # 使用确定性的指数退避延迟
                delay_seconds = 2**i
                workflow.logger.info(
                    f"[{self._state.agent_id}] Sleeping for {delay_seconds} seconds before next attempt."
                )
                # 必须使用 workflow.sleep 来保证确定性
                await workflow.sleep(delay_seconds)

        self._status = "FAILED"
        raise ApplicationError(
            f"[{self._state.agent_id}] Max iterations ({self._state.max_iterations}) reached.",
            non_retryable=True,
        )

    @workflow.query
    def get_status(self) -> AgentStatus:
        """提供工作流当前状态的只读视图。"""
        if not self._state:
            return AgentStatus(
                agent_id="N/A",
                current_iteration=0,
                max_iterations=0,
                status=self._status,
                last_test_summary={},
            )
        return AgentStatus(
            agent_id=self._state.agent_id,
            current_iteration=self._state.current_iteration,
            max_iterations=self._state.max_iterations,
            status=self._status,
            last_test_summary=self._last_test_summary,
        )