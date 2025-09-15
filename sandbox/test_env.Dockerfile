# /sandbox/test_env.Dockerfile

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