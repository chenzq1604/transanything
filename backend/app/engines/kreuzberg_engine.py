"""
Kreuzberg转换引擎
使用Kreuzberg库进行OCR识别，支持PDF、图片等多种格式
自动调用Tesseract进行OCR，适合图片型PDF
"""

import logging
import os
from typing import Optional

from app.engines.base import BaseEngine

logger = logging.getLogger(__name__)


def _ensure_tessdata() -> None:
    """
    确保TESSDATA_PREFIX环境变量已设置

    Kreuzberg依赖Tesseract进行OCR，需要tessdata目录
    """
    if not os.environ.get("TESSDATA_PREFIX"):
        tessdata_dir = os.path.join(os.path.expanduser("~"), ".kreuzberg", "tessdata")
        if os.path.isdir(tessdata_dir):
            os.environ["TESSDATA_PREFIX"] = tessdata_dir


class KreuzbergEngine(BaseEngine):
    """Kreuzberg转换引擎，使用Tesseract OCR识别图片型PDF和其他文件"""

    @property
    def supported_extensions(self) -> list[str]:
        """返回Kreuzberg引擎支持的扩展名"""
        return [".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif", ".webp"]

    async def convert(self, file_path: str) -> str:
        """
        使用Kreuzberg将文件转换为Markdown格式

        自动调用Tesseract进行OCR识别，适合图片型PDF

        Args:
            file_path: 源文件路径

        Returns:
            转换后的Markdown文本
        """
        _ensure_tessdata()

        try:
            from kreuzberg import extract_file, ExtractionConfig, OcrConfig, TesseractConfig

            config = ExtractionConfig(
                ocr=OcrConfig(
                    backend="tesseract",
                    language="chi_sim+eng",
                    tesseract_config=TesseractConfig(language="chi_sim+eng"),
                ),
                force_ocr=True,
            )

            result = await extract_file(file_path, config=config)
            content = result.content

            if content and content.strip():
                return content.strip()
            return ""

        except Exception as e:
            logger.error(f"Kreuzberg转换失败: {file_path}, 错误: {str(e)}")
            raise RuntimeError(f"Kreuzberg转换失败: {str(e)}")

    def convert_sync(self, file_path: str) -> str:
        """
        同步版本（供线程池调用）

        在新的事件循环中运行async convert

        Args:
            file_path: 源文件路径

        Returns:
            转换后的Markdown文本
        """
        import asyncio
        _ensure_tessdata()

        try:
            from kreuzberg import extract_file, ExtractionConfig, OcrConfig, TesseractConfig

            config = ExtractionConfig(
                ocr=OcrConfig(
                    backend="tesseract",
                    language="chi_sim+eng",
                    tesseract_config=TesseractConfig(language="chi_sim+eng"),
                ),
                force_ocr=True,
            )

            # 在新事件循环中运行
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(extract_file(file_path, config=config))
            finally:
                loop.close()

            content = result.content
            if content and content.strip():
                return content.strip()
            return ""

        except Exception as e:
            logger.error(f"Kreuzberg转换失败: {file_path}, 错误: {str(e)}")
            raise RuntimeError(f"Kreuzberg转换失败: {str(e)}")
