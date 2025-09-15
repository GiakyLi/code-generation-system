# /common/src/common/models.py
# 技术审计与重构报告
#
# ### 1. 核心变更: 增强数据模型的验证与健壮性
#
# 原始的数据模型(Pydantic BaseModel)只定义了数据的形状, 但缺乏严格的验证。
# 这意味着无效的数据(如负的迭代次数、格式错误的URL)可能会进入系统核心逻辑,
# 导致不可预测的运行时错误。
#
# ### 2. 实施策略: 利用Pydantic的验证能力
#
# 我们对模型进行了如下增强, 以在系统边界(API入口)就拒绝无效数据, 实现“防卫式编程”。
#
# - **使用`Field`进行范围验证**:
#   在`InitialRequest`中, `max_iterations`现在使用`Field(gt=0, le=20)`进行约束。
#   `gt=0`确保了迭代次数必须是正数, `le=20`则作为一个简单的安全限制, 防止滥用导致
#   过长的循环和资源消耗。任何超出此范围的请求都会在被接受时立即失败。
#
# - **使用专用类型进行格式验证**:
#   `test_files_url`的类型从普通的`str`改为了Pydantic的`HttpUrl`。
#   这个类型会自动验证传入的字符串是否是一个合法的HTTP或HTTPS URL。
#   这可以防止因URL格式错误导致后续的HTTP请求失败。
#
# - **引入`TraceableRequest`混入类**:
#   为了支持跨服务的分布式追踪, 我们创建了一个`TraceableRequest`混入类,
#   它包含一个可选的`trace_id`字段。所有服务间的请求模型都应继承它,
#   以便在整个调用链中传递和记录同一个追踪ID, 这是实现系统可观测性的关键一环。
#
# ### 3. 带来的好处
#
# 这些看似微小的改动, 极大地提升了系统的整体健壮性。它们将数据验证的责任
# 从业务逻辑中分离出来, 集中在数据模型定义中, 使得代码更清晰、更安全。
# 通过在数据进入系统的第一时间进行严格校验, 我们遵循了“快速失败”原则,
# 从而避免了无效数据污染系统状态, 减少了后期调试的难度。

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
    test_errors: Optional] = None


class FinalOutput(BaseModel):
    """向UI呈现的最终成功或失败报告。"""

    status: str
    message: str
    workflow_id: str
    trace_id: str
    code_a: Optional[str] = None
    code_b: Optional[str] = None
    # 错误信息现在是结构化的, 而不仅仅是字符串
    errors_a: Optional]] = None
    errors_b: Optional]] = None
    diff: Optional[str] = None


# 新增: 用于Temporal Workflow查询的模型
class AgentStatus(BaseModel):
    """用于查询Agent工作流当前状态的数据模型。"""

    agent_id: str
    current_iteration: int
    max_iterations: int
    status: str  # e.g., "GENERATING_CODE", "TESTING", "REFINING_PROMPT"
    last_test_summary: Optional] = None


class MainWorkflowStatus(BaseModel):
    """用于查询主Saga工作流当前状态的数据模型。"""

    status: str  # e.g., "RUNNING", "SUCCESS", "FAILED"
    agent_a_status: Optional = None
    agent_b_status: Optional = None