"""
LLM配置管理API
支持获取/保存LLM配置、测试连接、测试图片识别能力
配置持久化到llm_config.json文件，重启后自动加载
"""

import base64
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm", tags=["LLM配置"])

# 配置文件路径（与backend/app同级目录下的llm_config.json）
_CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "llm_config.json")


def _load_persisted_config():
    """从配置文件加载LLM配置到settings"""
    if not os.path.exists(_CONFIG_FILE):
        return
    try:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("api_key"):
            settings.LLM_API_KEY = data["api_key"]
        if data.get("base_url"):
            settings.LLM_BASE_URL = data["base_url"]
        if data.get("model"):
            settings.LLM_MODEL = data["model"]
        logger.info(f"已从配置文件加载LLM配置: model={settings.LLM_MODEL}")
    except Exception as e:
        logger.warning(f"加载LLM配置文件失败: {e}")


def _save_persisted_config(api_key: str, base_url: str, model: str):
    """将LLM配置持久化到配置文件"""
    try:
        data = {
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
        }
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"LLM配置已持久化到: {_CONFIG_FILE}")
    except Exception as e:
        logger.warning(f"持久化LLM配置失败: {e}")


# 模块加载时自动读取持久化配置
_load_persisted_config()


class LLMConfigRequest(BaseModel):
    """LLM配置请求体"""
    api_key: str
    base_url: str
    model: str


class LLMConfigResponse(BaseModel):
    """LLM配置响应"""
    api_key: str
    base_url: str
    model: str
    # 运行时状态
    supports_vision: Optional[bool] = None
    connection_ok: Optional[bool] = None


class LLMTestResponse(BaseModel):
    """LLM测试响应"""
    success: bool
    message: str
    supports_vision: Optional[bool] = None


@router.get("/config", response_model=LLMConfigResponse)
async def get_llm_config():
    """
    获取当前LLM配置

    API Key会脱敏显示（仅显示前8位和后4位）
    """
    api_key = settings.LLM_API_KEY
    masked_key = api_key
    if len(api_key) > 12:
        masked_key = api_key[:8] + "****" + api_key[-4:]

    return LLMConfigResponse(
        api_key=masked_key,
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
    )


@router.post("/config", response_model=LLMConfigResponse)
async def save_llm_config(req: LLMConfigRequest):
    """
    保存LLM配置（运行时生效并持久化到配置文件）

    保存后立即生效，重启后自动加载
    """
    # 如果api_key是脱敏的（包含****），则保留原值
    if "****" in req.api_key:
        req.api_key = settings.LLM_API_KEY

    # 更新运行时配置
    settings.LLM_API_KEY = req.api_key
    settings.LLM_BASE_URL = req.base_url
    settings.LLM_MODEL = req.model

    # 持久化到配置文件
    _save_persisted_config(req.api_key, req.base_url, req.model)

    # 重置LLM客户端实例，使新配置生效
    from app.llm.client import llm_client
    if llm_client is not None:
        import app.llm.client as client_module
        client_module.llm_client = None

    logger.info(f"LLM配置已更新: model={req.model}, base_url={req.base_url}")

    # 返回脱敏后的配置
    masked_key = req.api_key
    if len(req.api_key) > 12:
        masked_key = req.api_key[:8] + "****" + req.api_key[-4:]

    return LLMConfigResponse(
        api_key=masked_key,
        base_url=req.base_url,
        model=req.model,
    )


@router.post("/test-connection", response_model=LLMTestResponse)
async def test_llm_connection():
    """
    测试LLM API连接是否正常

    发送一个简单的文本请求验证API Key和Base URL是否有效
    """
    try:
        from app.llm.client import get_llm_client
        llm = get_llm_client()
        ok = await llm.check_connection()

        if ok:
            return LLMTestResponse(
                success=True,
                message="连接成功，LLM API可用",
            )
        else:
            return LLMTestResponse(
                success=False,
                message="连接失败，LLM API返回异常",
            )
    except Exception as e:
        logger.error(f"LLM连接测试失败: {str(e)}")
        return LLMTestResponse(
            success=False,
            message=f"连接失败: {str(e)}",
        )


@router.post("/test-vision", response_model=LLMTestResponse)
async def test_llm_vision():
    """
    测试LLM是否支持图片识别（多模态）

    发送一个1x1像素的PNG图片给LLM，检查是否能处理图片输入
    """
    try:
        from app.llm.client import get_llm_client
        llm = get_llm_client()

        # 生成一个最小的1x1白色PNG图片
        import struct
        import zlib

        def create_minimal_png():
            """创建最小的1x1白色PNG图片的base64编码"""
            # PNG签名
            signature = b'\x89PNG\r\n\x1a\n'
            # IHDR chunk: 1x1, 8-bit RGB
            ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
            ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff
            ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)
            # IDAT chunk: 单个白色像素
            raw_data = b'\x00\xff\xff\xff'  # filter byte + RGB
            compressed = zlib.compress(raw_data)
            idat_crc = zlib.crc32(b'IDAT' + compressed) & 0xffffffff
            idat = struct.pack('>I', len(compressed)) + b'IDAT' + compressed + struct.pack('>I', idat_crc)
            # IEND chunk
            iend_crc = zlib.crc32(b'IEND') & 0xffffffff
            iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
            return base64.b64encode(signature + ihdr + idat + iend).decode('utf-8')

        img_b64 = create_minimal_png()

        # 尝试发送图片识别请求
        try:
            response = await llm.client.chat.completions.create(
                model=llm.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "请描述这张图片的内容，只需回答'测试成功'即可。"},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                            },
                        ],
                    }
                ],
                max_tokens=50,
            )
            result = response.choices[0].message.content
            return LLMTestResponse(
                success=True,
                message=f"图片识别测试成功，模型支持多模态输入。模型回复: {result[:50]}",
                supports_vision=True,
            )
        except Exception as vision_err:
            error_msg = str(vision_err).lower()
            # 常见的不支持图片的错误关键词
            if any(kw in error_msg for kw in ['image', 'vision', 'multimodal', 'not support', 'unsupported', 'invalid', 'content type']):
                return LLMTestResponse(
                    success=False,
                    message=f"当前模型不支持图片识别（多模态），错误: {str(vision_err)[:200]}",
                    supports_vision=False,
                )
            # 其他错误可能是API问题
            return LLMTestResponse(
                success=False,
                message=f"图片识别测试失败: {str(vision_err)[:200]}",
                supports_vision=False,
            )
    except Exception as e:
        logger.error(f"LLM图片识别测试失败: {str(e)}")
        return LLMTestResponse(
            success=False,
            message=f"测试异常: {str(e)[:200]}",
            supports_vision=False,
        )


@router.get("/status")
async def get_llm_status():
    """
    获取LLM当前状态（连接状态+图片识别支持情况）

    轻量级接口，用于前端展示LLM开关的tooltip信息
    """
    connection_ok = False
    supports_vision = None

    try:
        from app.llm.client import get_llm_client
        llm = get_llm_client()
        connection_ok = await llm.check_connection()
    except Exception:
        connection_ok = False

    # 如果连接正常，检查图片识别支持（用缓存的配置判断）
    if connection_ok:
        try:
            from app.llm.client import get_llm_client
            llm = get_llm_client()
            # 快速检查：发送一个极小的图片请求
            import struct
            import zlib

            def create_minimal_png():
                """创建最小的1x1白色PNG图片的base64编码"""
                signature = b'\x89PNG\r\n\x1a\n'
                ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
                ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff
                ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)
                raw_data = b'\x00\xff\xff\xff'
                compressed = zlib.compress(raw_data)
                idat_crc = zlib.crc32(b'IDAT' + compressed) & 0xffffffff
                idat = struct.pack('>I', len(compressed)) + b'IDAT' + compressed + struct.pack('>I', idat_crc)
                iend_crc = zlib.crc32(b'IEND') & 0xffffffff
                iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
                return base64.b64encode(signature + ihdr + idat + iend).decode('utf-8')

            img_b64 = create_minimal_png()
            response = await llm.client.chat.completions.create(
                model=llm.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "描述图片，只回答OK"},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                        ],
                    }
                ],
                max_tokens=10,
            )
            supports_vision = True
        except Exception:
            supports_vision = False

    return {
        "connection_ok": connection_ok,
        "supports_vision": supports_vision,
        "model": settings.LLM_MODEL,
        "base_url": settings.LLM_BASE_URL,
    }
