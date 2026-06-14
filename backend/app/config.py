"""
配置管理模块
使用pydantic-settings管理应用配置，支持环境变量覆盖
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置类，所有配置项均可通过环境变量覆盖"""

    # LLM相关配置（用户通过前端界面配置，不硬编码默认值）
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    LLM_MODEL: str = ""

    # 文件存储路径
    UPLOAD_DIR: str = "./uploads"
    OUTPUT_DIR: str = "./outputs"

    # PaddleOCR相关配置
    PADDLEOCR_DEVICE: str = "gpu"
    PADDLEOCR_MODEL_CACHE_DIR: str = "./models/paddleocr"
    PADDLEOCR_REC_MODEL_ID: str = "PaddlePaddle/PP-OCRv6_medium_rec"
    PADDLEOCR_DET_MODEL_DIR: str = ""
    PADDLEOCR_REC_MODEL_DIR: str = "./models/paddleocr/PP-OCRv6_medium_rec"
    PADDLEOCR_CLS_MODEL_DIR: str = ""

    # 数据库配置
    SQLITE_URL: str = "sqlite:///./transanything.db"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


def ensure_directories(settings: Settings) -> None:
    """确保上传和输出目录存在"""
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)


# 全局配置实例
settings = Settings()
ensure_directories(settings)
