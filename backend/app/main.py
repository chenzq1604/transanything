"""
FastAPI应用入口
配置CORS、挂载路由、启动应用
后端固定端口18030
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
import socket

# 禁用oneDNN以解决PaddlePaddle 3.3+ PIR RT-DETR模型兼容性问题
os.environ.setdefault("FLAGS_use_mkldnn", "0")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import convert, files, upload, llm_config, engine_check
from app.config import settings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 设置TESSDATA_PREFIX环境变量（Kreuzberg/Tesseract OCR需要）
if not os.environ.get("TESSDATA_PREFIX"):
    tessdata_dir = os.path.join(os.path.expanduser("~"), ".kreuzberg", "tessdata")
    if os.path.isdir(tessdata_dir):
        os.environ["TESSDATA_PREFIX"] = tessdata_dir
        logger.info(f"TESSDATA_PREFIX设置为: {tessdata_dir}")

@asynccontextmanager
async def lifespan(app_instance):
    """应用生命周期管理：启动时写入端口文件，关闭时清理"""
    logger.info("TransAnything API 启动中...")
    logger.info(f"上传目录: {settings.UPLOAD_DIR}")
    logger.info(f"输出目录: {settings.OUTPUT_DIR}")
    logger.info(f"LLM模型: {settings.LLM_MODEL}")

    # 后台预加载 PaddleOCR 模型
    prewarm_task = asyncio.create_task(_prewarm_paddle_pipelines())

    yield  # 服务器运行中

    # 关闭时取消预加载任务
    prewarm_task.cancel()


# 创建FastAPI应用实例
app = FastAPI(
    title="TransAnything API",
    description="文件转Markdown的Web平台后端API",
    version="0.1.0",
    lifespan=lifespan,
)

# 配置CORS（开发阶段允许所有来源）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(upload.router)
app.include_router(convert.router)
app.include_router(files.router)
app.include_router(llm_config.router)
app.include_router(engine_check.router)


@app.on_event("startup")
async def startup_event() -> None:
    """应用启动后写入端口文件"""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    port_file = os.path.join(project_root, ".backend_port")
    port = 18030
    with open(port_file, "w") as f:
        f.write(str(port))
    logger.info(f"端口文件已写入: {port_file} -> {port}")


async def _prewarm_paddle_pipelines() -> None:
    """后台预加载 PaddleOCR 高级管线模型（不阻塞启动）"""
    await asyncio.sleep(2)  # 等服务器完全启动后再加载

    # PP-StructureV3
    try:
        from app.engines.factory import _get_ppstructure_engine
        pe = _get_ppstructure_engine()
        logger.info("后台开始预加载 PP-StructureV3 模型（可能需要 1-2 分钟）...")
        await asyncio.to_thread(pe._get_pipeline)
        logger.info("PP-StructureV3 模型预加载完成")
    except Exception as e:
        logger.warning("PP-StructureV3 预加载跳过: %s", e)

    # PP-ChatOCRv4
    try:
        from app.engines.factory import _get_ppchatocr_engine
        ce = _get_ppchatocr_engine()
        logger.info("后台开始预加载 PP-ChatOCRv4 模型（可能需要 1-2 分钟）...")
        await asyncio.to_thread(ce._get_pipeline)
        logger.info("PP-ChatOCRv4 模型预加载完成")
    except Exception as e:
        logger.warning("PP-ChatOCRv4 预加载跳过: %s", e)


@app.get("/", tags=["健康检查"])
async def root() -> dict:
    """
    健康检查接口

    Returns:
        服务状态信息
    """
    return {
        "service": "TransAnything API",
        "status": "running",
        "version": "0.1.0",
    }


@app.get("/api/health", tags=["健康检查"])
async def health_check() -> dict:
    """
    API健康检查接口

    Returns:
        API状态信息
    """
    # 返回代码版本标识，便于确认Electron是否使用了最新代码
    return {"status": "ok", "code_version": "20260614-v3"}
