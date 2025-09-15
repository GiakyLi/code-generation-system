# /common/src/common/models.py

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl


class TraceableRequest(BaseModel):
    """一个混入类(Mixin), 为服务间请求添加分布式追踪ID。"""

    # trace_id用于关联一次完整请求在所有微服务间的日志。
    trace_id: Optional[str] = None


class InitialRequest(BaseModel):
    """从Streamlit UI发送到编排器的初始请求。"""

    functional_description: str = Field(
       ..., min_length=10, description="功能的详细文字描述"
    )
    # HttpUrl类型会自动验证URL格式
    test_files_url: HttpUrl = Field(
       ..., description="包含测试用例的.tar.gz文件的URL"
    )
    # 使用Field进行数值范围验证, 防止无效输入
    max_iterations: int = Field(
        default=5, gt=0, le=20, description="代码生成的最大迭代次数"
    )


class SandboxRequest(TraceableRequest):
    """从编排器发送到沙箱服务的请求。"""

    code_to_test: str
    test_files_url: HttpUrl


class SandboxResponse(BaseModel):
    """沙箱服务返回的结构化测试报告。"""

    summary: Dict[str, Any]
    tests: List[Any]
    # 增加了stdout和stderr字段, 用于捕获和返回更详细的执行输出, 便于调试。
    stdout: str
    stderr: str
    error: Optional[str] = None


class AgentState(BaseModel):
    """代表单个智能体工作流的完整状态, 用于在Temporal工作流中传递。"""

    agent_id: str
    # 从具体URL改为环境变量名, 增强灵活性和安全性
    model_endpoint_env_var: str
    trace_id: str
    current_iteration: int = 0
    max_iterations: int
    initial_request: InitialRequest
    faulty_code: Optional[str] = None
    # 类型从Any改为更具体的Dict, 增强类型安全性
    test_errors: Optional[Dict[str, Any]] = None


class FinalOutput(BaseModel):
    """向UI呈现的最终成功或失败报告。"""

    status: str
    message: str
    workflow_id: str
    trace_id: str
    code_a: Optional[str] = None
    code_b: Optional[str] = None
    # 错误信息现在是结构化的, 而不仅仅是字符串
    errors_a: Optional[Dict[str, Any]] = None
    errors_b: Optional[Dict[str, Any]] = None
    diff: Optional[str] = None


# 新增: 用于Temporal Workflow查询的模型
class AgentStatus(BaseModel):
    """用于查询Agent工作流当前状态的数据模型。"""

    agent_id: str
    current_iteration: int
    max_iterations: int
    status: str  # e.g., "GENERATING_CODE", "TESTING", "REFINING_PROMPT"
    last_test_summary: Optional[Dict[str, Any]] = None


class MainWorkflowStatus(BaseModel):
    """用于查询主Saga工作流当前状态的数据模型。"""

    status: str  # e.g., "RUNNING", "SUCCESS", "FAILED"
    agent_a_status: Optional[AgentStatus] = None
    agent_b_status: Optional[AgentStatus] = None