# /orchestrator/src/orchestrator/workflows/main_workflow.py

import asyncio
import uuid
from datetime import timedelta
from typing import List

from common.models import (
    AgentState,
    FinalOutput,
    InitialRequest,
    MainWorkflowStatus,
)
from temporalio import workflow
from temporalio.common import ParentClosePolicy
from temporalio.exceptions import ChildWorkflowFailure

from.agent_workflow import AgentFSMWorkflow


@workflow.defn
class MainSagaWorkflow:
    def __init__(self) -> None:
        self._status = "PENDING"
        self._agent_a_handle: workflow.ChildWorkflowHandle | None = None
        self._agent_b_handle: workflow.ChildWorkflowHandle | None = None
        self._trace_id: str = ""

    @workflow.run
    async def execute(self, request: InitialRequest) -> FinalOutput:
        """执行主Saga工作流, 并行启动和管理两个Agent子工作流。"""
        self._trace_id = str(uuid.uuid4())
        self._status = "RUNNING"
        workflow.logger.info(
            "Main Saga workflow started.",
            trace_id=self._trace_id,
            request=request.model_dump(),
        )

        # 从配置中获取模型端点的环境变量名
        # 注意: 工作流不能直接访问os.getenv, 因此这些信息需要从外部传入
        # 这里我们假设这些信息可以从Worker的上下文中获取, 或者通过请求传递
        # 为了简化, 我们暂时硬编码, 但在生产中应通过配置注入
        settings = workflow.info().search_attributes.get("settings", {})
        model_a_env_var = settings.get("VLLM_MODEL_A_ENV_VAR", "VLLM_MODEL_A_URL")
        model_b_env_var = settings.get("VLLM_MODEL_B_ENV_VAR", "VLLM_MODEL_B_URL")

        agent_a_state = AgentState(
            agent_id="agent_a",
            model_endpoint_env_var=model_a_env_var,
            trace_id=self._trace_id,
            max_iterations=request.max_iterations,
            initial_request=request,
        )
        agent_b_state = AgentState(
            agent_id="agent_b",
            model_endpoint_env_var=model_b_env_var,
            trace_id=self._trace_id,
            max_iterations=request.max_iterations,
            initial_request=request,
        )

        try:
            # 并行启动两个子工作流
            self._agent_a_handle = workflow.start_child_workflow(
                AgentFSMWorkflow.execute,
                agent_a_state,
                id=f"agent-a-{self._trace_id}",
                parent_close_policy=ParentClosePolicy.TERMINATE,
            )
            self._agent_b_handle = workflow.start_child_workflow(
                AgentFSMWorkflow.execute,
                agent_b_state,
                id=f"agent-b-{self._trace_id}",
                parent_close_policy=ParentClosePolicy.TERMINATE,
            )

            # 等待两个子工作流的结果
            result_a, result_b = await asyncio.gather(
                self._agent_a_handle, self._agent_b_handle
            )

            self._status = "SUCCESS"
            workflow.logger.info("Both agents succeeded.", trace_id=self._trace_id)
            return FinalOutput(
                status="SUCCESS",
                message="Both agents succeeded.",
                workflow_id=workflow.info().workflow_id,
                trace_id=self._trace_id,
                code_a=result_a,
                code_b=result_b,
            )
        except ChildWorkflowFailure as e:
            # 当任何一个子工作流失败时, 进入Saga补偿逻辑
            self._status = "FAILED_AND_ROLLING_BACK"
            workflow.logger.error(
                f"A child workflow failed: {e.cause}", trace_id=self._trace_id
            )

            # 检查哪个Agent成功了, 并为其执行补偿操作
            compensations: List[workflow.ActivityHandle] = []
            if self._agent_a_handle:
                try:
                    # 检查Agent A是否成功
                    await self._agent_a_handle.result()
                    workflow.logger.info(
                        "Agent A succeeded, scheduling compensation.",
                        trace_id=self._trace_id,
                    )
                    compensations.append(
                        workflow.execute_activity(
                            "cleanup_successful_agent_artifacts",
                            "agent_a",
                            start_to_close_timeout=timedelta(minutes=1),
                        )
                    )
                except ChildWorkflowFailure:
                    # Agent A失败了, 不需要补偿
                    pass
            if self._agent_b_handle:
                try:
                    # 检查Agent B是否成功
                    await self._agent_b_handle.result()
                    workflow.logger.info(
                        "Agent B succeeded, scheduling compensation.",
                        trace_id=self._trace_id,
                    )
                    compensations.append(
                        workflow.execute_activity(
                            "cleanup_successful_agent_artifacts",
                            "agent_b",
                            start_to_close_timeout=timedelta(minutes=1),
                        )
                    )
                except ChildWorkflowFailure:
                    # Agent B失败了, 不需要补偿
                    pass

            if compensations:
                # 使用gather确保所有补偿操作都会被尝试, 即使其中一个失败
                await asyncio.gather(*compensations, return_exceptions=True)
                workflow.logger.info(
                    "All compensations executed.", trace_id=self._trace_id
                )

            self._status = "ROLLED_BACK"
            return FinalOutput(
                status="ROLLED_BACK",
                message=f"Workflow failed and was rolled back. Reason: {e.cause}",
                workflow_id=workflow.info().workflow_id,
                trace_id=self._trace_id,
            )

    @workflow.query
    async def get_status(self) -> MainWorkflowStatus:
        """提供主工作流及其所有子工作流的层级状态。"""
        agent_a_status = None
        if self._agent_a_handle:
            try:
                agent_a_status = await self._agent_a_handle.query(
                    AgentFSMWorkflow.get_status
                )
            except Exception:
                # 如果查询失败(例如, 子工作流已完成), 则忽略
                pass

        agent_b_status = None
        if self._agent_b_handle:
            try:
                agent_b_status = await self._agent_b_handle.query(
                    AgentFSMWorkflow.get_status
                )
            except Exception:
                pass

        return MainWorkflowStatus(
            status=self._status,
            agent_a_status=agent_a_status,
            agent_b_status=agent_b_status,
        )