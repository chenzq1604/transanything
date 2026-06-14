"""
转换引擎工厂
根据文件类型和引擎类型选择合适的转换引擎
"""

from app.engines.base import BaseEngine
from app.engines.docx_engine import DocxEngine
from app.engines.markitdown_engine import MarkitdownEngine
from app.engines.mineru_engine import MineruEngine
from app.engines.paddleocr_engine import PaddleOcrEngine
from app.engines.pdf_engine import PdfEngine
from app.engines.ppchatocr_engine import PPChatOCREngine
from app.engines.ppstructure_engine import PPStructureEngine
from app.engines.xls_engine import XlsEngine
from app.engines.txt_engine import TxtEngine

# 引擎类型常量
ENGINE_PYMUPDF = "pymupdf"
ENGINE_MARKITDOWN = "markitdown"
ENGINE_PADDLEOCR = "paddleocr"
ENGINE_PPSTRUCTURE = "ppstructure"
ENGINE_PPCHATOCR = "ppchatocr"
ENGINE_MINERU = "mineru"
ENGINE_LLM = "llm"
ENGINE_AUTO = "auto"

# 惰性初始化各引擎实例
_pdf_engine = None
_docx_engine = None
_xls_engine = None
_txt_engine = None
_markitdown_engine = None
_paddleocr_engine = None
_ppstructure_engine = None
_ppchatocr_engine = None
_mineru_engine = None


def _get_pdf_engine() -> PdfEngine:
    """获取PDF引擎单例"""
    global _pdf_engine
    if _pdf_engine is None:
        _pdf_engine = PdfEngine()
    return _pdf_engine


def _get_docx_engine() -> DocxEngine:
    """获取DOCX引擎单例"""
    global _docx_engine
    if _docx_engine is None:
        _docx_engine = DocxEngine()
    return _docx_engine


def _get_xls_engine() -> XlsEngine:
    """获取XLS引擎单例"""
    global _xls_engine
    if _xls_engine is None:
        _xls_engine = XlsEngine()
    return _xls_engine


def _get_txt_engine() -> TxtEngine:
    """获取TXT引擎单例"""
    global _txt_engine
    if _txt_engine is None:
        _txt_engine = TxtEngine()
    return _txt_engine


def _get_markitdown_engine() -> MarkitdownEngine:
    """获取MarkItDown引擎单例"""
    global _markitdown_engine
    if _markitdown_engine is None:
        _markitdown_engine = MarkitdownEngine()
    return _markitdown_engine


def _get_paddleocr_engine() -> PaddleOcrEngine:
    """获取PaddleOCR引擎单例"""
    global _paddleocr_engine
    if _paddleocr_engine is None:
        _paddleocr_engine = PaddleOcrEngine()
    return _paddleocr_engine


def _get_mineru_engine() -> MineruEngine:
    """获取MinerU引擎单例"""
    global _mineru_engine
    if _mineru_engine is None:
        _mineru_engine = MineruEngine()
    return _mineru_engine


def _get_ppstructure_engine() -> PPStructureEngine:
    """获取PP-StructureV3引擎单例"""
    global _ppstructure_engine
    if _ppstructure_engine is None:
        _ppstructure_engine = PPStructureEngine()
    return _ppstructure_engine


def _get_ppchatocr_engine() -> PPChatOCREngine:
    """获取PP-ChatOCRv4引擎单例"""
    global _ppchatocr_engine
    if _ppchatocr_engine is None:
        _ppchatocr_engine = PPChatOCREngine()
    return _ppchatocr_engine


def get_engine(file_extension: str, engine_type: str = ENGINE_AUTO) -> BaseEngine | None:
    """
    根据文件扩展名和引擎类型获取对应的转换引擎

    Args:
        file_extension: 文件扩展名（如.pdf, .docx）
        engine_type: 引擎类型，可选值：
            - auto: 自动选择（默认）
            - pymupdf: 使用PyMuPDF引擎（仅PDF）
            - markitdown: 使用MarkItDown引擎
            - llm: 使用LLM图片识别（仅PDF）

    Returns:
        对应的转换引擎实例，不支持则返回None
    """
    ext = file_extension.lower()

    # 指定引擎类型
    if engine_type == ENGINE_MARKITDOWN:
        md_engine = _get_markitdown_engine()
        if ext in md_engine.supported_extensions:
            return md_engine
        return None

    if engine_type == ENGINE_PYMUPDF:
        if ext == ".pdf":
            return _get_pdf_engine()
        return None

    if engine_type == ENGINE_PADDLEOCR:
        if ext == ".pdf":
            return _get_paddleocr_engine()
        return None

    if engine_type == ENGINE_MINERU:
        if ext == ".pdf":
            return _get_mineru_engine()
        return None

    if engine_type == ENGINE_PPSTRUCTURE:
        if ext == ".pdf":
            return _get_ppstructure_engine()
        return None

    if engine_type == ENGINE_PPCHATOCR:
        if ext == ".pdf":
            return _get_ppchatocr_engine()
        return None

    if engine_type == ENGINE_LLM:
        # LLM引擎在convert_service中特殊处理
        return None

    # auto模式：按文件类型选择最优引擎
    if ext == ".pdf":
        return _get_pdf_engine()
    elif ext in (".docx", ".doc"):
        return _get_docx_engine()
    elif ext in (".xlsx", ".xls"):
        return _get_xls_engine()
    elif ext in (".txt", ".md", ".csv"):
        return _get_txt_engine()
    else:
        # 其他格式尝试MarkItDown
        md_engine = _get_markitdown_engine()
        if ext in md_engine.supported_extensions:
            return md_engine
        return None


def get_supported_extensions() -> set[str]:
    """
    获取所有支持的文件扩展名集合

    Returns:
        支持的扩展名集合
    """
    extensions = set()
    for engine in [_get_pdf_engine(), _get_docx_engine(), _get_xls_engine(),
                   _get_txt_engine(), _get_markitdown_engine(), _get_paddleocr_engine(),
                   _get_mineru_engine(), _get_ppstructure_engine(), _get_ppchatocr_engine()]:
        extensions.update(engine.supported_extensions)
    return extensions


def get_available_engines(file_extension: str) -> list[str]:
    """
    获取指定文件类型可用的引擎列表

    Args:
        file_extension: 文件扩展名

    Returns:
        可用引擎类型列表
    """
    ext = file_extension.lower()
    engines = []

    if ext == ".pdf":
        engines = [ENGINE_MARKITDOWN, ENGINE_PADDLEOCR, ENGINE_PPSTRUCTURE, ENGINE_PPCHATOCR, ENGINE_MINERU, ENGINE_LLM]
    elif ext in (".docx", ".doc"):
        engines = [ENGINE_MARKITDOWN]
    elif ext in (".xlsx", ".xls"):
        engines = [ENGINE_MARKITDOWN]
    else:
        md_engine = _get_markitdown_engine()
        if ext in md_engine.supported_extensions:
            engines = [ENGINE_MARKITDOWN]

    return engines
