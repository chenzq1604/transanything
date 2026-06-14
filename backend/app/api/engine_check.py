"""
引擎环境检测API
检测各引擎所需的Python包、GPU、外部工具等依赖是否满足
返回每个引擎的可用状态及不可用原因
"""

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/engines", tags=["引擎检测"])


def _check_package(package_name: str) -> bool:
    """检测Python包是否可导入"""
    try:
        __import__(package_name)
        return True
    except ImportError:
        return False


def _check_nvidia_gpu() -> tuple[bool, str]:
    """
    检测NVIDIA GPU是否可用
    优先用PaddlePaddle检测，其次用PyTorch检测
    Returns:
        (可用, 原因说明)
    """
    # 尝试PaddlePaddle
    if _check_package("paddle"):
        try:
            import paddle
            if paddle.device.is_compiled_with_cuda():
                try:
                    paddle.device.set_device("gpu:0")
                    return True, "NVIDIA GPU可用（PaddlePaddle CUDA）"
                except Exception:
                    return False, "未检测到NVIDIA GPU（PaddlePaddle已编译CUDA但无可用设备）"
            else:
                return False, "PaddlePaddle为CPU版本，未编译CUDA支持"
        except Exception as e:
            return False, f"PaddlePaddle检测异常: {str(e)[:100]}"

    # 尝试PyTorch
    if _check_package("torch"):
        try:
            import torch
            if torch.cuda.is_available():
                return True, "NVIDIA GPU可用（PyTorch CUDA）"
            else:
                return False, "未检测到NVIDIA GPU（PyTorch）"
        except Exception as e:
            return False, f"PyTorch检测异常: {str(e)[:100]}"

    return False, "未安装PaddlePaddle或PyTorch，无法检测GPU"


def _check_paddleocr_deps() -> tuple[bool, str]:
    """
    检测PaddleOCR系列引擎依赖
    需要: paddleocr + paddle + NVIDIA GPU
    Returns:
        (可用, 原因说明)
    """
    if not _check_package("paddleocr"):
        return False, "未安装 paddleocr 包"
    if not _check_package("paddle"):
        return False, "未安装 paddlepaddle 包"
    gpu_ok, gpu_reason = _check_nvidia_gpu()
    if not gpu_ok:
        return False, f"GPU不可用: {gpu_reason}"
    return True, "依赖满足，GPU可用"


def _check_mineru_deps() -> tuple[bool, str]:
    """
    检测MinerU引擎依赖
    需要: mineru + torch + NVIDIA GPU
    Returns:
        (可用, 原因说明)
    """
    if not _check_package("mineru"):
        return False, "未安装 mineru 包"
    if not _check_package("torch"):
        return False, "未安装 torch 包"
    gpu_ok, gpu_reason = _check_nvidia_gpu()
    if not gpu_ok:
        return False, f"GPU不可用: {gpu_reason}"
    return True, "依赖满足，GPU可用"


def _check_llm_deps() -> tuple[bool, str]:
    """
    检测LLM图片识别引擎依赖
    需要: openai + 已配置API Key + 模型支持vision
    Returns:
        (可用, 原因说明)
    """
    if not _check_package("openai"):
        return False, "未安装 openai 包"

    from app.config import settings
    if not settings.LLM_API_KEY:
        return False, "未配置 LLM API Key，请先在大模型配置中设置"

    # 尝试快速连接测试
    try:
        from app.llm.client import get_llm_client
        llm = get_llm_client()
        # 仅做轻量级检查，不实际发请求（避免耗时）
        if not llm.client or not llm.model:
            return False, "LLM客户端初始化失败"
    except Exception as e:
        return False, f"LLM客户端异常: {str(e)[:100]}"

    return True, "依赖满足，API Key已配置（图片识别能力需单独测试）"


@router.get("/check")
async def check_engines():
    """
    检测所有引擎的环境依赖和可用状态

    Returns:
        各引擎的可用状态、不可用原因、所需依赖列表
    """
    # 定义引擎检测规则
    engine_checks = [
        {
            "type": "markitdown",
            "name": "MarkItDown",
            "description": "微软开源库，支持广泛格式",
            "requires_gpu": False,
            "dependencies": ["markitdown"],
            "check_fn": lambda: (True, "依赖满足") if _check_package("markitdown") else (False, "未安装 markitdown 包"),
        },
        {
            "type": "pymupdf",
            "name": "PyMuPDF",
            "description": "高性能PDF文本提取",
            "requires_gpu": False,
            "dependencies": ["pymupdf (fitz)"],
            "check_fn": lambda: (True, "依赖满足") if _check_package("fitz") else (False, "未安装 pymupdf 包"),
        },
        {
            "type": "python-docx",
            "name": "python-docx",
            "description": "Word文档解析",
            "requires_gpu": False,
            "dependencies": ["python-docx"],
            "check_fn": lambda: (True, "依赖满足") if _check_package("docx") else (False, "未安装 python-docx 包"),
        },
        {
            "type": "paddleocr",
            "name": "PaddleOCR v6",
            "description": "本地GPU OCR，适合扫描件和图片型PDF",
            "requires_gpu": True,
            "dependencies": ["paddleocr", "paddlepaddle-gpu", "NVIDIA GPU + CUDA"],
            "check_fn": _check_paddleocr_deps,
        },
        {
            "type": "ppstructure",
            "name": "PP-StructureV3",
            "description": "版面分析+表格识别+公式识别+印章识别",
            "requires_gpu": True,
            "dependencies": ["paddleocr", "paddlepaddle-gpu", "NVIDIA GPU + CUDA"],
            "check_fn": _check_paddleocr_deps,
        },
        {
            "type": "ppchatocr",
            "name": "PP-ChatOCRv4",
            "description": "OCR+版面分析+可选LLM关键信息提取",
            "requires_gpu": True,
            "dependencies": ["paddleocr", "paddlepaddle-gpu", "NVIDIA GPU + CUDA"],
            "check_fn": _check_paddleocr_deps,
        },
        {
            "type": "mineru",
            "name": "MinerU",
            "description": "端到端文档理解：版面分析+OCR+公式+表格+图片",
            "requires_gpu": True,
            "dependencies": ["mineru", "torch", "NVIDIA GPU + CUDA"],
            "check_fn": _check_mineru_deps,
        },
        {
            "type": "llm",
            "name": "LLM图片识别",
            "description": "渲染图片后用多模态LLM识别，最准确但最慢",
            "requires_gpu": False,
            "dependencies": ["openai", "LLM API Key", "支持vision的模型"],
            "check_fn": _check_llm_deps,
        },
    ]

    results = []
    for engine in engine_checks:
        try:
            available, reason = engine["check_fn"]()
        except Exception as e:
            available = False
            reason = f"检测异常: {str(e)[:100]}"

        results.append({
            "type": engine["type"],
            "name": engine["name"],
            "description": engine["description"],
            "available": available,
            "reason": reason if not available else "",
            "requires_gpu": engine["requires_gpu"],
            "dependencies": engine["dependencies"],
        })

    return {"engines": results}
