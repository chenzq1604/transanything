"""
文件上传API
处理文件上传请求，支持多文件上传
"""

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.schemas import FileUpload
from app.services.convert_service import get_convert_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["上传"])


@router.post("/upload", response_model=list[FileUpload], summary="上传文件")
async def upload_files(files: list[UploadFile] = File(..., description="要上传的文件列表")) -> list[FileUpload]:
    """
    上传一个或多个文件到服务器

    Args:
        files: 上传文件列表

    Returns:
        上传成功的文件信息列表

    Raises:
        HTTPException: 文件类型不支持或上传失败
    """
    service = get_convert_service()
    uploaded_files: list[FileUpload] = []

    for file in files:
        try:
            file_info = await service.upload_file(file)
            uploaded_files.append(file_info)
        except ValueError as e:
            logger.warning(f"文件上传失败: {file.filename}, 原因: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"文件上传异常: {file.filename}, 错误: {str(e)}")
            raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")

    return uploaded_files
