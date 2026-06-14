"""
PaddleOCR转换引擎
使用PaddleOCR 3.x在本地GPU上识别PDF页面，适合扫描件和图片型PDF
"""

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import fitz

from app.config import settings
from app.engines.base import BaseEngine

logger = logging.getLogger(__name__)


class PaddleOcrEngine(BaseEngine):
    """PaddleOCR本地GPU识别引擎，负责将PDF页面OCR为Markdown文本"""

    def __init__(self) -> None:
        """初始化PaddleOCR引擎，OCR实例按需惰性创建"""
        self._ocr = None

    @property
    def supported_extensions(self) -> list[str]:
        """返回PaddleOCR引擎支持的文件扩展名"""
        return [".pdf"]

    async def convert(self, file_path: str) -> str:
        """
        异步转换PDF为Markdown文本

        Args:
            file_path: PDF文件路径

        Returns:
            OCR识别后的Markdown文本
        """
        return await asyncio.to_thread(self.convert_sync, file_path)

    def convert_sync(self, file_path: str, file_id: str | None = None) -> str:
        """
        同步转换PDF为Markdown文本

        Args:
            file_path: PDF文件路径
            file_id: 文件ID，用于日志和后续扩展

        Returns:
            OCR识别后的Markdown文本
        """
        ocr = self._get_ocr()
        pdf_path = Path(file_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF文件不存在: {file_path}")

        with tempfile.TemporaryDirectory(prefix="transanything_paddleocr_") as temp_dir:
            image_paths = self._render_pdf_pages(pdf_path, Path(temp_dir))
            markdown_parts: list[str] = []

            for index, image_path in enumerate(image_paths, start=1):
                if index > 1:
                    markdown_parts.append("\n---\n\n")
                markdown_parts.append(f"## 第 {index} 页\n\n")
                page_text = self._recognize_image(ocr, image_path)
                markdown_parts.append(page_text or "<!-- 本页未识别到文本 -->")
                markdown_parts.append("\n")

        return "".join(markdown_parts).strip()

    def _get_ocr(self) -> Any:
        """
        获取PaddleOCR实例，优先使用配置中的GPU设备和模型目录

        Returns:
            PaddleOCR实例
        """
        if self._ocr is not None:
            return self._ocr

        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError("未安装paddleocr，请先在transanything环境中安装PaddleOCR 3.7") from exc

        kwargs = self._build_ocr_kwargs()
        try:
            self._ocr = PaddleOCR(**kwargs)
        except Exception as exc:
            raise RuntimeError(f"PaddleOCR初始化失败，请检查GPU版PaddlePaddle和模型配置: {exc}") from exc

        logger.info("PaddleOCR初始化成功，device=%s", settings.PADDLEOCR_DEVICE)
        self._log_gpu_status()
        return self._ocr

    def _log_gpu_status(self) -> None:
        """
        记录PaddlePaddle的GPU使用状态到日志
        """
        try:
            import paddle
            if paddle.device.is_compiled_with_cuda():
                device = paddle.device.get_device()
                logger.info("PaddlePaddle GPU确认: device=%s", device)
            else:
                logger.warning("PaddlePaddle未编译CUDA支持，将使用CPU推理")
        except Exception as e:
            logger.warning("无法确认PaddlePaddle GPU状态: %s", e)

    def _build_ocr_kwargs(self) -> dict[str, Any]:
        """
        构建兼容PaddleOCR 3.x的初始化参数

        Returns:
            PaddleOCR初始化参数字典
        """
        kwargs: dict[str, Any] = {
            "device": settings.PADDLEOCR_DEVICE,
            "lang": "ch",
        }

        rec_model_dir = settings.PADDLEOCR_REC_MODEL_DIR or self._download_modelscope_rec_model()
        model_dirs = {
            "text_detection_model_dir": settings.PADDLEOCR_DET_MODEL_DIR,
            "text_recognition_model_dir": rec_model_dir,
            "textline_orientation_model_dir": settings.PADDLEOCR_CLS_MODEL_DIR,
        }
        for key, value in model_dirs.items():
            if value:
                kwargs[key] = self._resolve_model_dir(value)

        return kwargs

    def _resolve_model_dir(self, model_dir: str) -> str:
        """
        将模型目录解析为绝对路径

        Args:
            model_dir: 模型目录，可为绝对路径或相对项目根目录的路径

        Returns:
            绝对模型目录路径
        """
        path = Path(model_dir)
        if path.is_absolute():
            return str(path)
        project_root = Path(__file__).resolve().parents[3]
        return str(project_root / path)

    def _download_modelscope_rec_model(self) -> str:
        """
        从ModelScope下载PP-OCRv6 medium识别模型

        Returns:
            ModelScope模型本地目录
        """
        cache_dir = Path(settings.PADDLEOCR_MODEL_CACHE_DIR)
        cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            from modelscope import snapshot_download
        except ImportError as exc:
            raise RuntimeError("未安装modelscope，无法下载PP-OCRv6 medium识别模型") from exc

        model_dir = snapshot_download(
            settings.PADDLEOCR_REC_MODEL_ID,
            cache_dir=str(cache_dir),
        )
        return os.path.abspath(model_dir)

    def _render_pdf_pages(self, pdf_path: Path, output_dir: Path) -> list[Path]:
        """
        将PDF每页渲染为PNG图片

        Args:
            pdf_path: PDF文件路径
            output_dir: 图片输出目录

        Returns:
            渲染后的图片路径列表
        """
        doc = fitz.open(str(pdf_path))
        image_paths: list[Path] = []
        zoom = 200 / 72
        mat = fitz.Matrix(zoom, zoom)

        try:
            for page_index in range(len(doc)):
                page = doc[page_index]
                pix = page.get_pixmap(matrix=mat, alpha=False)
                image_path = output_dir / f"page_{page_index + 1}.png"
                pix.save(str(image_path))
                image_paths.append(image_path)
        finally:
            doc.close()

        return image_paths

    def _recognize_image(self, ocr: Any, image_path: Path) -> str:
        """
        识别单页图片并整理为文本

        Args:
            ocr: PaddleOCR实例
            image_path: 页面图片路径

        Returns:
            识别出的文本，按页面顺序换行
        """
        result = self._run_predict(ocr, image_path)
        lines = self._extract_text_lines(result)
        if not lines:
            logger.warning("PaddleOCR未识别到文本: %s, result类型=%s", image_path, type(result).__name__)
        return "\n\n".join(lines)

    def _run_predict(self, ocr: Any, image_path: Path) -> Any:
        """
        调用PaddleOCR 3.x或兼容旧版接口执行识别

        Args:
            ocr: PaddleOCR实例
            image_path: 页面图片路径

        Returns:
            PaddleOCR原始识别结果
        """
        if hasattr(ocr, "predict"):
            return ocr.predict(str(image_path))
        if hasattr(ocr, "ocr"):
            return ocr.ocr(str(image_path), cls=True)
        raise RuntimeError("当前PaddleOCR实例没有可用的predict/ocr方法")

    def _extract_text_lines(self, result: Any) -> list[str]:
        """
        从PaddleOCR不同版本的结果结构中提取文本行
        支持PaddleOCR 3.x predict返回的OCRResult（继承dict）和旧版dict/tuple格式

        注意：PaddleOCR 3.x 的 OCRResult 继承自 dict，rec_texts 等字段
        必须通过 result["rec_texts"] 或 result.get("rec_texts") 访问，
        而非 getattr(result, "rec_texts")，因为 dict 的键不是对象属性。

        Args:
            result: PaddleOCR原始结果

        Returns:
            文本行列表
        """
        lines: list[str] = []

        if not result:
            return lines

        # PaddleOCR 3.x predict 返回列表，每个元素是 OCRResult 对象
        if isinstance(result, list):
            for item in result:
                lines.extend(self._extract_text_lines(item))
            return lines

        # 优先检查 dict 兼容接口（OCRResult 继承自 dict，必须用 [] 或 get 访问）
        # 这必须在 getattr 之前检查，因为 getattr 对 dict 子类的键无效
        if isinstance(result, dict) or hasattr(result, "get"):
            for key in ("rec_texts", "texts"):
                try:
                    values = result.get(key) if hasattr(result, "get") else None
                    if values is None and isinstance(result, dict):
                        values = result.get(key)
                    if isinstance(values, (list, tuple)) and values:
                        return [str(t).strip() for t in values if str(t).strip()]
                except Exception:
                    pass

        # 尝试从对象属性提取 rec_texts（某些自定义对象可能用属性）
        rec_texts = getattr(result, "rec_texts", None)
        if rec_texts and isinstance(rec_texts, (list, tuple)):
            return [str(t).strip() for t in rec_texts if str(t).strip()]

        # 尝试从对象属性提取 texts
        texts = getattr(result, "texts", None)
        if texts and isinstance(texts, (list, tuple)):
            return [str(t).strip() for t in texts if str(t).strip()]

        # 尝试从对象属性提取 rec_text（单条文本）
        rec_text = getattr(result, "rec_text", None)
        if rec_text and isinstance(rec_text, str) and rec_text.strip():
            return [rec_text.strip()]

        # 尝试从对象属性提取 text（单条文本）
        text_attr = getattr(result, "text", None)
        if text_attr and isinstance(text_attr, str) and text_attr.strip():
            return [text_attr.strip()]

        # dict格式：遍历值查找嵌套文本
        if isinstance(result, dict):
            for value in result.values():
                if isinstance(value, (list, tuple)) and value and all(isinstance(item, str) for item in value):
                    extracted = [str(t).strip() for t in value if str(t).strip()]
                    if extracted:
                        return extracted
                lines.extend(self._extract_text_lines(value))
            return lines

        # 旧版tuple格式: ([[box, (text, score)], ...],)
        if isinstance(result, tuple):
            if len(result) >= 2 and isinstance(result[1], (tuple, list)) and result[1]:
                text = result[1][0]
                if isinstance(text, str) and text.strip():
                    return [text.strip()]
            for item in result:
                lines.extend(self._extract_text_lines(item))
            return lines

        logger.debug("无法从结果对象提取文本, 类型=%s, 属性=%s",
                      type(result).__name__,
                      [a for a in dir(result) if not a.startswith('_')][:10])
        return lines
