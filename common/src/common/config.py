# /common/src/common/config.py

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppBaseSettings(BaseSettings):
    """
    所有服务共享的基础配置。
    它会自动从环境变量或.env文件中加载配置。
    """

    # model_config用于配置Pydantic的行为。
    # case_sensitive=False 表示环境变量名不区分大小写。
    # env_file=".env"指定了要加载的.env文件。
    model_config = SettingsConfigDict(case_sensitive=False, env_file=".env")

    # 定义了日志级别, 并限制其取值范围, 提供了默认值。
    # Literal类型确保了LOG_LEVEL只能是指定的几个值之一, 否则启动时会报错。
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"