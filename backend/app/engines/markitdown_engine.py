"""
MarkItDown转换引擎
使用微软MarkItDown库将各种文件转换为Markdown，支持PDF、DOCX、XLSX、PPTX等
"""

import logging
import re
from typing import Optional

from markitdown import MarkItDown

from app.engines.base import BaseEngine

logger = logging.getLogger(__name__)


class MarkitdownEngine(BaseEngine):
    """MarkItDown转换引擎，支持广泛的文件格式转换"""

    def __init__(self) -> None:
        """初始化MarkItDown引擎"""
        self._md = MarkItDown()

    @property
    def supported_extensions(self) -> list[str]:
        """返回MarkItDown引擎支持的扩展名"""
        return [".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
                ".txt", ".md", ".csv", ".html", ".htm", ".png", ".jpg", ".jpeg",
                ".mp3", ".wav", ".mp4"]

    async def convert(self, file_path: str) -> str:
        """
        使用MarkItDown将文件转换为Markdown格式（异步包装）

        Args:
            file_path: 源文件路径

        Returns:
            转换后的Markdown文本
        """
        return self.convert_sync(file_path)

    def convert_sync(self, file_path: str) -> str:
        """
        使用MarkItDown将文件转换为Markdown格式（同步版本，供线程池调用）

        Args:
            file_path: 源文件路径

        Returns:
            转换后的Markdown文本
        """
        try:
            result = self._md.convert(file_path)
            content = result.text_content
            if content and content.strip():
                return self._sanitize_markdown(content.strip())
            return ""
        except Exception as e:
            logger.error(f"MarkItDown转换失败: {file_path}, 错误: {str(e)}")
            raise RuntimeError(f"MarkItDown转换失败: {str(e)}")

    def _sanitize_markdown(self, markdown: str) -> str:
        """清理Markdown内容，移除可能导致渲染器崩溃的字符"""
        # 移除控制字符（保留换行符、制表符）
        result = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', markdown)
        # 移除过长的空行（超过3个连续空行压缩为2个）
        result = re.sub(r'\n{4,}', '\n\n\n', result)
        return result
