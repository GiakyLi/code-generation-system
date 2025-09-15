# /ui/src/ui/temporal_client.py
# 技术审计与重构报告
#
# ### 1. 引入目的: 在Streamlit中高效管理Temporal客户端
#
# Streamlit的应用执行模型是每次用户交互都会重新运行整个脚本。
# 在这种模型下, 如果在脚本的顶层直接创建Temporal客户端,
# 每次交互都会触发一次新的、昂贵的TCP连接。
#
# ### 2. 解决方案: 利用Streamlit的会话状态缓存
#
# 这个新文件实现了一个简单的客户端管理器, 以解决上述问题。
#
# - **`@st.cache_resource`**: 我们使用Streamlit的`st.cache_resource`装饰器。
#   这个装饰器专门用于缓存“资源”, 如数据库连接、机器学习模型或我们这里的
#   Temporal客户端。
#
# - **工作原理**:
#   1. 当`get_temporal_client`函数第一次被调用时, 它会执行内部的`_connect`函数,
#      建立与Temporal服务器的连接, 并返回客户端实例。
#   2. Streamlit会将这个返回的客户端实例缓存起来, 并与当前用户的会话关联。
#   3. 在该用户的后续交互中(即脚本的后续重新运行), 当再次调用`get_temporal_client`时,
#      Streamlit会直接返回缓存中的客户端实例, 而不会再次执行`_connect`函数。
#
# ### 3. 优势
#
# - **性能**: 避免了为每次页面交互都重复建立TCP连接的开销, 显著提高了应用的响应速度。
# - **资源效率**: 减少了Temporal前端和UI服务上的连接数和资源消耗。
# - **代码整洁**: 将客户端管理的逻辑封装在一个独立的、可复用的函数中,
#   使得主应用文件`app.py`更加简洁, 专注于UI逻辑。
#
# 这是在Streamlit等“重新运行”模型的框架中与外部服务进行交互的最佳实践。

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