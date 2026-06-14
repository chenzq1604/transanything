"""
LLM统一客户端
使用OpenAI兼容接口调用火山方舟API，支持文本优化和图片识别
"""

import asyncio
import logging
from typing import Optional

from openai import AsyncOpenAI

from app.config import settings
from app.llm.prompts import OPTIMIZE_PROMPT, FIX_GARBLED_PROMPT, IMAGE_OCR_PROMPT

logger = logging.getLogger(__name__)

# LLM并发数（同时识别的页面数）
LLM_CONCURRENCY = 3


class LLMClient:
    """LLM客户端，封装OpenAI兼容接口调用逻辑，支持文本优化和图片识别"""

    def __init__(self) -> None:
        """初始化LLM客户端，使用配置中的API Key和Base URL"""
        self.client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )
        self.model = settings.LLM_MODEL
        # 并发信号量，控制同时请求LLM的数量
        self._semaphore = asyncio.Semaphore(LLM_CONCURRENCY)

    async def optimize_markdown(
        self,
        original_text: str,
        converted_markdown: str,
        file_type: str,
    ) -> str:
        """
        使用LLM优化基础转换得到的Markdown文本

        Args:
            original_text: 原始文件文本（用于参考）
            converted_markdown: 基础转换得到的Markdown文本
            file_type: 文件类型（如pdf、docx等）

        Returns:
            LLM优化后的Markdown文本
        """
        try:
            prompt = OPTIMIZE_PROMPT.format(
                file_type=file_type,
                converted_markdown=converted_markdown,
            )

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的文档格式优化助手，擅长将基础转换的Markdown文本优化为结构清晰、格式规范的Markdown文档。",
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=0.3,
                max_tokens=4096,
            )

            result = response.choices[0].message.content
            if result:
                return result.strip()

            logger.warning("LLM返回空结果，使用原始转换内容")
            return converted_markdown

        except Exception as e:
            logger.error(f"LLM优化失败: {str(e)}，使用原始转换内容")
            return converted_markdown

    async def fix_garbled_text(self, garbled_text: str, file_type: str = "pdf") -> str:
        """
        使用LLM修复乱码文本

        将乱码文本发给LLM，让它根据上下文推断正确内容

        Args:
            garbled_text: 乱码文本
            file_type: 文件类型

        Returns:
            修复后的Markdown文本
        """
        try:
            prompt = FIX_GARBLED_PROMPT.format(
                file_type=file_type,
                garbled_text=garbled_text,
            )

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的文档修复助手，擅长修复PDF提取中出现的中文乱码文本。你能根据上下文和残存信息推断出正确的中文内容。",
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=0.3,
                max_tokens=4096,
            )

            result = response.choices[0].message.content
            if result:
                return result.strip()

            return garbled_text

        except Exception as e:
            logger.error(f"LLM修复乱码失败: {str(e)}")
            return garbled_text

    async def recognize_image(self, image_base64: str, page_num: int = 1) -> str:
        """
        使用LLM识别图片内容并转为Markdown

        将PDF页面渲染的图片发给多模态LLM识别
        使用信号量控制并发数，避免同时发送过多请求

        Args:
            image_base64: base64编码的PNG图片
            page_num: 页码

        Returns:
            识别后的Markdown文本
        """
        async with self._semaphore:
            try:
                prompt = IMAGE_OCR_PROMPT.format(page_num=page_num)

                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "你是一个专业的OCR识别助手，擅长将图片中的文档内容识别并转换为结构清晰的Markdown格式。",
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": prompt,
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{image_base64}",
                                    },
                                },
                            ],
                        },
                    ],
                    temperature=0.3,
                    max_tokens=4096,
                )

                result = response.choices[0].message.content
                if result:
                    return result.strip()

                return f"<!-- 第{page_num}页识别失败 -->"

            except Exception as e:
                logger.error(f"LLM图片识别失败: {str(e)}")
                return f"<!-- 第{page_num}页识别失败: {str(e)} -->"

    async def check_connection(self) -> bool:
        """
        检查LLM API连接是否正常

        Returns:
            连接正常返回True，否则返回False
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "hello"}],
                max_tokens=10,
            )
            return bool(response.choices)
        except Exception as e:
            logger.error(f"LLM连接检查失败: {str(e)}")
            return False


# 全局LLM客户端实例
llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """
    获取LLM客户端单例

    Returns:
        LLMClient实例
    """
    global llm_client
    if llm_client is None:
        llm_client = LLMClient()
    return llm_client
