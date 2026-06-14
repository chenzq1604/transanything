"""
转换API
处理文件转换请求，包括触发转换、批量转换、进度查询和保存用户编辑后的Markdown
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query

from app.engines.factory import ENGINE_AUTO, ENGINE_LLM, ENGINE_MARKITDOWN, ENGINE_MINERU, ENGINE_PADDLEOCR, ENGINE_PPCHATOCR, ENGINE_PPSTRUCTURE, ENGINE_PYMUPDF
from app.models.schemas import BatchConvertRequest, ConvertResponse, EngineResult, SaveMarkdownRequest
from app.services.convert_service import get_convert_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["转换"])

# 有效的引擎类型集合
VALID_ENGINES = {ENGINE_MARKITDOWN, ENGINE_PADDLEOCR, ENGINE_PPSTRUCTURE, ENGINE_PPCHATOCR, ENGINE_MINERU, ENGINE_LLM}


@router.post("/convert/{file_id}", response_model=ConvertResponse, summary="触发文件转换")
async def convert_file(
    file_id: str,
    use_llm_optimize: bool = Query(default=True, description="是否使用LLM优化转换结果"),
    engine_type: str = Query(
        default=ENGINE_MARKITDOWN,
        description="转换引擎类型：markitdown/paddleocr/ppstructure/ppchatocr/mineru/llm",
    ),
) -> ConvertResponse:
    """
    触发指定文件的转换操作（单引擎）

    PDF文件支持四级策略（auto模式自动降级）：
    1. PyMuPDF文本提取（快速）
    2. MarkItDown转换（中等）
    3. PaddleOCR本地识别（适合扫描件）
    4. LLM图片识别（慢但最准确）

    也可手动指定引擎类型

    Args:
        file_id: 要转换的文件ID
        use_llm_optimize: 是否使用LLM优化（query参数，默认True）
        engine_type: 引擎类型（query参数，默认markitdown）

    Returns:
        转换响应，包含Markdown内容和状态

    Raises:
        HTTPException: 文件不存在或转换失败
    """
    # 校验engine_type
    if engine_type not in VALID_ENGINES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的引擎类型: {engine_type}，可选值: {', '.join(VALID_ENGINES)}",
        )

    service = get_convert_service()

    # 检查文件是否存在
    file_info = await service.get_file(file_id)
    if file_info is None:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")

    # 检查是否已在转换中
    from app.services.progress import get_progress_tracker
    tracker = get_progress_tracker()
    current_progress = tracker.get_progress(file_id)
    if current_progress and current_progress.status == "converting":
        raise HTTPException(status_code=409, detail="该文件正在转换中，请稍候")

    # 启动后台转换任务
    asyncio.create_task(
        service.convert(file_id, use_llm_optimize=use_llm_optimize, engine_type=engine_type)
    )

    return ConvertResponse(
        file_id=file_id,
        markdown_content="",
        status="converting",
    )


@router.post("/convert/{file_id}/batch", summary="批量多引擎转换")
async def convert_batch(file_id: str, request: BatchConvertRequest) -> dict:
    """
    批量触发多个引擎的转换操作

    各引擎并行执行，互不影响，一个引擎失败不影响其他引擎。
    异步执行，立即返回，前端通过轮询进度API获取各引擎状态。

    Args:
        file_id: 要转换的文件ID
        request: 批量转换请求体，包含engine_types和use_llm_optimize

    Returns:
        包含file_id、初始engine_results和status的响应

    Raises:
        HTTPException: 文件不存在、引擎类型无效或已在转换中
    """
    # 校验engine_types
    invalid_engines = [et for et in request.engine_types if et not in VALID_ENGINES]
    if invalid_engines:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的引擎类型: {', '.join(invalid_engines)}，可选值: {', '.join(VALID_ENGINES)}",
        )

    if not request.engine_types:
        raise HTTPException(status_code=400, detail="至少需要指定一个引擎类型")

    service = get_convert_service()

    # 检查文件是否存在
    file_info = await service.get_file(file_id)
    if file_info is None:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")

    # 检查是否已在转换中
    from app.services.progress import get_progress_tracker
    tracker = get_progress_tracker()
    current_progress = tracker.get_progress(file_id)
    if current_progress and current_progress.status == "converting":
        raise HTTPException(status_code=409, detail="该文件正在转换中，请稍候")

    # 启动后台批量转换任务
    async def _batch_task():
        """后台批量转换任务"""
        try:
            await service.convert_batch(
                file_id,
                engine_types=request.engine_types,
                use_llm_optimize=request.use_llm_optimize,
            )
        except Exception as e:
            logger.error(f"批量转换任务异常: {file_id}, 错误: {str(e)}")

    asyncio.create_task(_batch_task())

    # 构建初始引擎结果列表
    from app.models.schemas import ENGINE_NAMES
    initial_results = []
    for et in request.engine_types:
        engine_name = ENGINE_NAMES.get(et, et)
        initial_results.append(EngineResult(
            engine_type=et,
            engine_name=engine_name,
            status="pending",
        ).model_dump())

    return {
        "file_id": file_id,
        "engine_results": initial_results,
        "status": "converting",
    }


@router.put("/convert/{file_id}/save", summary="保存用户编辑后的Markdown")
async def save_markdown(file_id: str, request: SaveMarkdownRequest) -> dict:
    """
    保存用户编辑后的Markdown内容

    Args:
        file_id: 文件ID
        request: 包含编辑后Markdown内容的请求体

    Returns:
        保存结果信息

    Raises:
        HTTPException: 文件不存在或保存失败
    """
    service = get_convert_service()

    # 检查文件是否存在
    file_info = await service.get_file(file_id)
    if file_info is None:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")

    try:
        output_path = await service.save_markdown(file_id, request.content)
        return {"message": "保存成功", "file_id": file_id, "output_path": output_path}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"保存Markdown失败: {file_id}, 错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


@router.get("/engines", summary="获取可用引擎列表")
async def get_engines(file_type: str = Query(default=".pdf", description="文件类型")) -> dict:
    """
    获取指定文件类型可用的引擎列表

    Args:
        file_type: 文件类型（如.pdf, .docx）

    Returns:
        可用引擎列表
    """
    from app.engines.factory import get_available_engines

    engines = get_available_engines(file_type)
    engine_info = {
        ENGINE_MARKITDOWN: {"name": "MarkItDown", "description": "微软开源库，支持广泛格式"},
        ENGINE_PADDLEOCR: {"name": "PaddleOCR v6", "description": "本地GPU OCR，适合扫描件和图片型PDF"},
        ENGINE_PPSTRUCTURE: {"name": "PP-StructureV3", "description": "版面分析+表格识别+公式识别+印章识别"},
        ENGINE_PPCHATOCR: {"name": "PP-ChatOCRv4", "description": "OCR+版面分析+可选LLM关键信息提取"},
        ENGINE_MINERU: {"name": "MinerU", "description": "端到端文档理解：版面分析+OCR+公式+表格+图片"},
        ENGINE_LLM: {"name": "LLM图片识别", "description": "渲染图片后用多模态LLM识别，最准确但最慢"},
    }

    result = []
    for eng in engines:
        if eng in engine_info:
            result.append({"type": eng, **engine_info[eng]})

    return {"file_type": file_type, "engines": result}


@router.get("/convert/{file_id}/progress", summary="获取转换进度")
async def convert_progress(file_id: str) -> dict:
    """
    获取转换进度（轮询方式），支持多引擎独立进度

    前端通过定时轮询此端点获取转换进度。
    当存在多引擎进度时，返回各引擎独立进度和整体汇总进度。

    Args:
        file_id: 文件ID

    Returns:
        进度信息JSON，包含整体进度和各引擎独立进度
    """
    from app.services.progress import get_progress_tracker

    tracker = get_progress_tracker()
    progress = tracker.get_progress(file_id)

    if progress is None:
        return {
            "file_id": file_id,
            "status": "idle",
            "current_engine": "",
            "current_step": "",
            "message": "",
            "engines_tried": [],
            "current_step_num": 0,
            "total_steps": 0,
            "percentage": 0,
            "engines": {},
        }

    # 构建各引擎独立进度
    engines_progress = {}
    if progress.engine_progresses:
        for engine_type, engine_prog in progress.engine_progresses.items():
            engines_progress[engine_type] = {
                "status": engine_prog.status,
                "percentage": engine_prog.percentage,
                "step": engine_prog.current_step,
                "message": engine_prog.message,
            }

    return {
        "file_id": progress.file_id,
        "status": progress.status,
        "current_engine": progress.current_engine,
        "current_step": progress.current_step,
        "message": progress.message,
        "engines_tried": progress.engines_tried,
        "current_step_num": progress.current_step_num,
        "total_steps": progress.total_steps,
        "percentage": progress.percentage,
        "engines": engines_progress,
    }
