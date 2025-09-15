# /sandbox/test_env.Dockerfile
# 技术审计与重构报告
#
# ### 1. 审计结论: 基本安全实践到位, 但可进一步加固
#
# 这个Dockerfile用于构建一个隔离的环境, 以执行来自用户的不可信代码。
# 原始文件已经包含了一些重要的安全实践:
#
# - **使用非root用户(`appuser`)**: 这是容器安全的基本要求。它限制了在容器内
#   运行的代码的权限, 即使代码找到了容器逃逸的漏洞, 它在主机上也不会拥有root权限。
#
# - **使用最小化的基础镜像(`python:3.11-slim`)**: 减少了不必要的系统库和工具,
#   从而减小了潜在的攻击面。
#
# ### 2. 增强建议
#
# 虽然当前实现是可接受的, 但在高安全要求的生产环境中, 可以考虑以下进一步的加固措施:
#
# - **使用更小的基础镜像**: 考虑使用`distroless`镜像或从`scratch`开始构建一个
#   静态链接的Python环境。这些镜像不包含shell或包管理器, 极大地增加了攻击者
#   在容器内进行横向移动的难度。
#
# - **移除不必要的工具**: 确保最终镜像中不包含`pip`等工具。依赖应在构建时
#   完全安装好。
#
# - **安全扫描**: 在CI/CD流程中, 应使用工具(如Trivy, Snyk, Clair)对这个镜像
#   进行扫描, 以发现已知的操作系统或库级别的漏洞。
#
# 对于当前项目范围, 我们保留了原始实现, 因为它在安全性和易用性之间取得了
# 合理的平衡, 但上述建议对于未来的安全迭代至关重要。

# 使用一个最小化的Python镜像作为基础
FROM python:3.11-slim

# 创建一个没有特权的专用用户来运行代码, 这是关键的安全措施
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

# 设置工作目录
WORKDIR /home/appuser/app

# 安装测试所需的依赖
# --no-cache-dir 减小镜像体积
# --user 确保包安装在用户目录下, 避免权限问题
RUN pip install --no-cache-dir --user pytest pytest-json-report

# 将用户安装的包路径添加到PATH中
ENV PATH="/home/appuser/.local/bin:${PATH}"

# 默认命令, 在容器启动时提供一个shell
# 实际执行时, 这个命令会被`docker run`的参数覆盖
CMD ["/bin/bash"]