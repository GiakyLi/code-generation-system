# /ui/src/ui/app.py

import asyncio
import time
import uuid
from typing import Any, Dict, Optional

import streamlit as st
from common.models import InitialRequest, MainWorkflowStatus
from diff_match_patch import diff_match_patch
from temporalio.client import WorkflowHandle
from temporalio.exceptions import WorkflowFailureError

from.temporal_client import get_temporal_client, start_workflow


def render_diff(code_a: str, code_b: str) -> str:
    """生成并渲染两段代码的HTML差异。"""
    dmp = diff_match_patch()
    diffs = dmp.diff_main(code_a, code_b)
    dmp.diff_cleanupSemantic(diffs)
    return dmp.diff_prettyHtml(diffs)


def display_status(
    status_container: Any, status: Optional[MainWorkflowStatus]
) -> None:
    """在Streamlit容器中渲染工作流状态。"""
    if not status:
        status_container.info("正在获取工作流状态...")
        return

    with status_container.container():
        st.subheader(f"主工作流状态: {status.status}")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("##### Agent A")
            if status.agent_a_status:
                st.write(f"**状态:** {status.agent_a_status.status}")
                st.write(
                    f"**迭代:** "
                    f"{status.agent_a_status.current_iteration}/{status.agent_a_status.max_iterations}"
                )
                if status.agent_a_status.last_test_summary:
                    st.write("**上次测试结果:**")
                    st.json(status.agent_a_status.last_test_summary)
            else:
                st.write("等待启动...")
        with col2:
            st.markdown("##### Agent B")
            if status.agent_b_status:
                st.write(f"**状态:** {status.agent_b_status.status}")
                st.write(
                    f"**迭代:** "
                    f"{status.agent_b_status.current_iteration}/{status.agent_b_status.max_iterations}"
                )
                if status.agent_b_status.last_test_summary:
                    st.write("**上次测试结果:**")
                    st.json(status.agent_b_status.last_test_summary)
            else:
                st.write("等待启动...")


async def poll_workflow_status(
    handle: WorkflowHandle, status_container: Any
) -> Dict[str, Any]:
    """轮询工作流状态直到其完成。"""
    while True:
        try:
            # 使用查询来获取实时状态
            status = await handle.query("get_status")
            display_status(status_container, status)
            # 检查工作流是否已完成
            # 这是一个技巧: 尝试用0.1秒超时获取结果
            try:
                return await asyncio.wait_for(handle.result(), timeout=0.1)
            except asyncio.TimeoutError:
                # 工作流仍在运行
                pass
        except Exception as e:
            status_container.error(f"查询工作流状态时出错: {e}")
            # 发生查询错误时, 直接尝试获取最终结果
            break
        time.sleep(2)  # 等待2秒后再次轮询

    # 如果循环中断, 说明工作流可能已完成或出错, 获取最终结果
    try:
        return await handle.result()
    except WorkflowFailureError as e:
        st.error(f"工作流执行失败: {e.cause}")
        return {"status": "FAILED", "message": str(e.cause)}


def main() -> None:
    st.set_page_config(layout="wide", page_title="代码生成系统")
    st.title("弹性、异步代码生成系统 (生产版)")

    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if "workflow_handle" not in st.session_state:
        st.session_state.workflow_handle = None

    # 从缓存中获取Temporal客户端
    try:
        client = get_temporal_client()
    except Exception as e:
        st.error(f"无法连接到Temporal服务: {e}")
        st.stop()

    with st.sidebar:
        st.header("任务提交")
        with st.form("request_form"):
            functional_description = st.text_area(
                "功能描述",
                height=200,
                value="编写一个名为`my_func`的函数, 它不接受任何参数并返回数字42。",
            )
            # 注意: 为了方便本地测试, 我们使用了一个由docker-compose启动的简单文件服务器
            test_files_url = st.text_input(
                "测试文件URL (.tar.gz)",
                value="http://test-file-server:8080/tests.tar.gz",
            )
            max_iterations = st.slider("最大迭代次数", 1, 10, 5)
            submitted = st.form_submit_button("生成代码")

    if submitted:
        if not functional_description or not test_files_url:
            st.error("请填写所有字段。")
        else:
            request = InitialRequest(
                functional_description=functional_description,
                test_files_url=test_files_url,
                max_iterations=max_iterations,
            )
            with st.spinner("正在启动工作流..."):
                try:
                    handle = asyncio.run(start_workflow(client, request.model_dump()))
                    st.session_state.workflow_handle = handle
                    st.success(f"工作流已成功启动! ID: {handle.id}")
                    st.info("您现在可以实时监控其进度。")
                except Exception as e:
                    st.error(f"启动工作流失败: {e}")
                    st.exception(e)

    if st.session_state.workflow_handle:
        st.divider()
        st.header("工作流实时监控")
        st.write(f"当前监控的工作流ID: **{st.session_state.workflow_handle.id}**")
        status_placeholder = st.empty()
        result = asyncio.run(
            poll_workflow_status(st.session_state.workflow_handle, status_placeholder)
        )

        st.header("最终结果")
        if result.get("status") == "SUCCESS":
            st.success(f"工作流成功完成: {result.get('message')}")
            code_a = result.get("code_a", "")
            code_b = result.get("code_b", "")
            tab1, tab2, tab3 = st.tabs(["Agent A Code", "Agent B Code", "Code Diff"])
            with tab1:
                st.code(code_a, language="python")
            with tab2:
                st.code(code_b, language="python")
            with tab3:
                diff_html = render_diff(code_a, code_b)
                st.components.v1.html(diff_html, height=600, scrolling=True)
        else:
            st.error(f"工作流失败或被回滚: {result.get('message')}")
            st.json(result)

        # 清理状态以便下次运行
        st.session_state.workflow_handle = None


if __name__ == "__main__":
    main()