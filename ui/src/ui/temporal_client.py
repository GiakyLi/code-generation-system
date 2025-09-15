# /ui/src/ui/temporal_client.py

import asyncio
from typing import Any

import streamlit as st
from temporalio.client import Client, WorkflowHandle

from.config import get_settings

# 获取UI配置
settings = get_settings()


@st.cache_resource
def get_temporal_client() -> Client:
    """
    获取一个缓存的Temporal客户端实例。
    使用`st.cache_resource`确保在整个用户会话中只创建一个客户端。
    """

    async def _connect() -> Client:
        try:
            client = await Client.connect(settings.UI_TEMPORAL_SERVER)
            print("Successfully connected to Temporal server.")
            return client
        except Exception as e:
            print(f"Failed to connect to Temporal server: {e}")
            # 在Streamlit中, 抛出异常会显示一个错误消息
            raise

    # Streamlit在顶层不支持await, 所以我们用asyncio.run来执行异步连接
    return asyncio.run(_connect())


async def start_workflow(client: Client, request_data: dict[str, Any]) -> WorkflowHandle:
    """异步启动一个新的工作流。"""
    # 使用`start_workflow`并立即返回handle, 不等待其完成
    handle = await client.start_workflow(
        "MainSagaWorkflow",
        request_data,
        id=f"code-gen-ui-{st.session_state.session_id}",
        task_queue=settings.TASK_QUEUE,
    )
    return handle