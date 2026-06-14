"""
转换业务逻辑服务
包含文件上传、转换、保存、列表查询等核心业务逻辑
支持多引擎对比：每个引擎独立存储结果，互不影响
"""

import asyncio
import base64
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from app.config import settings
from app.engines.factory import (
    ENGINE_AUTO,
    ENGINE_LLM,
    ENGINE_MARKITDOWN,
    ENGINE_MINERU,
    ENGINE_PADDLEOCR,
    ENGINE_PPCHATOCR,
    ENGINE_PPSTRUCTURE,
    ENGINE_PYMUPDF,
    get_engine,
    get_available_engines,
    get_supported_extensions,
)
from app.engines.pdf_engine import PdfEngine, _is_garbled
from app.llm.client import get_llm_client
from app.models.schemas import ENGINE_NAMES, ConvertResponse, EngineResult, FileUpload
from app.services.progress import get_progress_tracker

logger = logging.getLogger(__name__)


class ConvertService:
    """文件转换服务，管理文件上传、转换和存储的完整生命周期，支持多引擎对比"""

    def __init__(self) -> None:
        """初始化转换服务，创建文件存储映射"""
        self._files: dict[str, FileUpload] = {}
        # 兼容旧接口：存储最后使用的引擎结果
        self._markdown_contents: dict[str, str] = {}
        # 多引擎结果存储：外层key是file_id，内层key是engine_type
        self._engine_results: dict[str, dict[str, EngineResult]] = {}

    async def upload_file(self, file: UploadFile) -> FileUpload:
        """
        上传文件到服务器

        Args:
            file: FastAPI上传文件对象

        Returns:
            文件上传信息

        Raises:
            ValueError: 不支持的文件类型
        """
        filename = file.filename or "unknown"
        ext = Path(filename).suffix.lower()

        if ext not in get_supported_extensions():
            raise ValueError(
                f"不支持的文件类型: {ext}，"
                f"支持的类型: {', '.join(sorted(get_supported_extensions()))}"
            )

        file_id = str(uuid.uuid4())
        stored_filename = f"{file_id}{ext}"
        file_path = Path(settings.UPLOAD_DIR) / stored_filename

        content = await file.read()
        file_size = len(content)

        with open(file_path, "wb") as f:
            f.write(content)

        file_info = FileUpload(
            id=file_id,
            filename=filename,
            file_type=ext,
            file_size=file_size,
            upload_time=datetime.now(),
            status="uploaded",
        )

        self._files[file_id] = file_info
        logger.info(f"文件上传成功: {filename} -> {file_id}")

        return file_info

    async def convert(
        self,
        file_id: str,
        use_llm_optimize: bool = True,
        engine_type: str = ENGINE_AUTO,
    ) -> ConvertResponse:
        """
        执行文件转换（单引擎，兼容旧接口）

        PDF支持四级策略（auto模式逐级降级）：
        1. PyMuPDF文本提取（快速）
        2. MarkItDown转换（中等）
        3. PaddleOCR本地识别（GPU OCR）
        4. LLM图片识别（最准确但最慢）

        手动指定引擎时只运行该引擎，不自动降级。
        同时将结果存入 _engine_results 以支持多引擎对比。

        Args:
            file_id: 文件ID
            use_llm_optimize: 是否使用LLM优化转换结果
            engine_type: 指定引擎类型，auto/pymupdf/markitdown/paddleocr/llm

        Returns:
            转换响应，包含Markdown内容和状态
        """
        if file_id not in self._files:
            raise ValueError(f"文件不存在: {file_id}")

        file_info = self._files[file_id]
        file_info.status = "converting"
        tracker = get_progress_tracker()
        tracker.init_progress(file_id, total_steps=4)

        try:
            stored_filename = f"{file_id}{file_info.file_type}"
            file_path = Path(settings.UPLOAD_DIR) / stored_filename

            markdown_content = ""
            actual_engine = engine_type  # 记录实际使用的引擎

            # PDF文件：支持四级策略
            if file_info.file_type == ".pdf":
                markdown_content, actual_engine = await self._convert_pdf(
                    file_id, str(file_path), engine_type
                )
            else:
                # 其他文件：使用引擎转换
                engine = get_engine(file_info.file_type, engine_type)
                if engine is None:
                    raise ValueError(f"不支持的文件类型或引擎: {file_info.file_type}/{engine_type}")
                markdown_content = await engine.convert(str(file_path), file_id)

            # LLM优化（可选，仅当实际引擎不是LLM时）
            if use_llm_optimize and actual_engine != ENGINE_LLM and markdown_content:
                try:
                    tracker.update(file_id, actual_engine, "LLM优化中", "使用LLM优化格式...", percentage=90)
                    await asyncio.sleep(0)
                    llm = get_llm_client()
                    markdown_content = await llm.optimize_markdown(
                        original_text=markdown_content,
                        converted_markdown=markdown_content,
                        file_type=file_info.file_type.lstrip("."),
                    )
                except Exception as e:
                    logger.warning(f"LLM优化失败，使用基础转换结果: {str(e)}")

            # 保存Markdown内容（兼容旧接口）
            self._markdown_contents[file_id] = markdown_content
            file_info.status = "completed"

            await self._save_to_output(file_id, markdown_content)

            # 同时存入 _engine_results 以支持多引擎对比
            engine_name = ENGINE_NAMES.get(actual_engine, actual_engine)
            self._set_engine_result(file_id, actual_engine, EngineResult(
                engine_type=actual_engine,
                engine_name=engine_name,
                markdown_content=markdown_content,
                status="completed",
                char_count=len(markdown_content),
                line_count=markdown_content.count("\n") + 1,
            ))
            # 保存引擎独立的Markdown文件
            await self._save_engine_output(file_id, actual_engine, markdown_content)

            logger.info(f"文件转换成功: {file_id}, 实际引擎: {actual_engine}")
            tracker.complete(file_id, actual_engine, "转换完成")
            return ConvertResponse(
                file_id=file_id,
                markdown_content=markdown_content,
                status="completed",
            )

        except Exception as e:
            file_info.status = "failed"
            tracker.fail(file_id, str(e))
            logger.error(f"文件转换失败: {file_id}, 错误: {str(e)}")
            return ConvertResponse(
                file_id=file_id,
                markdown_content="",
                status="failed",
                error_message=str(e),
            )

    async def convert_batch(self, file_id: str, engine_types: list[str], use_llm_optimize: bool = False) -> dict[str, EngineResult]:
        """
        批量转换多个引擎，并行执行，互不影响

        每个引擎独立追踪进度，一个引擎失败不影响其他引擎。
        结果存入 _engine_results，同时更新 _markdown_contents 为最后完成的引擎结果。

        Args:
            file_id: 文件ID
            engine_types: 要使用的引擎类型列表
            use_llm_optimize: 是否使用LLM优化转换结果

        Returns:
            各引擎的转换结果字典，key是engine_type

        Raises:
            ValueError: 文件不存在
        """
        if file_id not in self._files:
            raise ValueError(f"文件不存在: {file_id}")

        file_info = self._files[file_id]
        file_info.status = "converting"

        stored_filename = f"{file_id}{file_info.file_type}"
        file_path = str(Path(settings.UPLOAD_DIR) / stored_filename)
        tracker = get_progress_tracker()

        # 初始化各引擎的进度
        for engine_type in engine_types:
            tracker.init_engine_progress(file_id, engine_type)
            # 初始化引擎结果为pending状态
            engine_name = ENGINE_NAMES.get(engine_type, engine_type)
            self._set_engine_result(file_id, engine_type, EngineResult(
                engine_type=engine_type,
                engine_name=engine_name,
                status="pending",
            ))

        # 定义单引擎转换协程
        async def run_single_engine(engine_type: str) -> tuple[str, EngineResult]:
            """
            运行单个引擎的转换，返回(engine_type, EngineResult)

            Args:
                engine_type: 引擎类型标识

            Returns:
                (引擎类型, 引擎结果) 元组
            """
            engine_name = ENGINE_NAMES.get(engine_type, engine_type)
            start_time = time.time()

            try:
                # 更新进度为转换中
                tracker.update_engine_progress(file_id, engine_type, engine_name, f"{engine_name} 转换中...", 10)

                # 执行转换
                markdown_content = ""

                if file_info.file_type == ".pdf":
                    # PDF文件使用PDF专用引擎
                    markdown_content = await self._run_pdf_engine_step_for_batch(
                        file_id, file_path, engine_type
                    )
                else:
                    # 其他文件类型
                    engine = get_engine(file_info.file_type, engine_type)
                    if engine is None:
                        raise ValueError(f"不支持的引擎: {engine_type}")
                    markdown_content = await engine.convert(file_path, file_id)

                # LLM优化（可选）
                if use_llm_optimize and engine_type != ENGINE_LLM and markdown_content:
                    try:
                        tracker.update_engine_progress(file_id, engine_type, "LLM优化", f"{engine_name} LLM优化中...", 85)
                        await asyncio.sleep(0)
                        llm = get_llm_client()
                        markdown_content = await llm.optimize_markdown(
                            original_text=markdown_content,
                            converted_markdown=markdown_content,
                            file_type=file_info.file_type.lstrip("."),
                        )
                    except Exception as e:
                        logger.warning(f"{engine_name} LLM优化失败: {str(e)}")

                duration = time.time() - start_time
                result = EngineResult(
                    engine_type=engine_type,
                    engine_name=engine_name,
                    markdown_content=markdown_content,
                    status="completed",
                    duration=round(duration, 2),
                    char_count=len(markdown_content),
                    line_count=markdown_content.count("\n") + 1 if markdown_content else 0,
                )

                # 保存引擎独立的Markdown文件
                await self._save_engine_output(file_id, engine_type, markdown_content)

                tracker.complete_engine_progress(file_id, engine_type, f"{engine_name} 转换完成")
                logger.info(f"批量转换 - {engine_name} 完成: {file_id}, 耗时: {duration:.2f}s")
                return engine_type, result

            except Exception as e:
                duration = time.time() - start_time
                result = EngineResult(
                    engine_type=engine_type,
                    engine_name=engine_name,
                    markdown_content="",
                    status="failed",
                    duration=round(duration, 2),
                    error_message=str(e),
                )
                tracker.fail_engine_progress(file_id, engine_type, f"{engine_name} 转换失败: {str(e)}")
                logger.error(f"批量转换 - {engine_name} 失败: {file_id}, 错误: {str(e)}")
                return engine_type, result

        # 并行执行所有引擎
        tasks = [run_single_engine(et) for et in engine_types]
        results_list = await asyncio.gather(*tasks)

        # 汇总结果
        results: dict[str, EngineResult] = {}
        for engine_type, result in results_list:
            results[engine_type] = result
            self._set_engine_result(file_id, engine_type, result)

        # 更新文件状态和兼容旧接口
        all_completed = all(r.status == "completed" for r in results.values())
        any_completed = any(r.status == "completed" for r in results.values())

        if all_completed:
            file_info.status = "completed"
        elif any_completed:
            file_info.status = "completed"  # 至少有一个成功就算完成
        else:
            file_info.status = "failed"

        # 兼容旧接口：用第一个成功的引擎结果作为默认markdown_content
        for et in engine_types:
            if et in results and results[et].status == "completed":
                self._markdown_contents[file_id] = results[et].markdown_content
                await self._save_to_output(file_id, results[et].markdown_content)
                break

        return results

    async def _run_pdf_engine_step_for_batch(self, file_id: str, file_path: str, engine_type: str) -> str:
        """
        批量转换中执行单个PDF引擎步骤（带独立进度更新）

        与 _run_pdf_engine_step 类似，但使用 engine_progress 追踪进度

        Args:
            file_id: 文件ID
            file_path: PDF文件路径
            engine_type: 引擎类型

        Returns:
            当前引擎转换出的Markdown文本
        """
        tracker = get_progress_tracker()
        engine_name = ENGINE_NAMES.get(engine_type, engine_type)

        step_messages = {
            ENGINE_PYMUPDF: ("PyMuPDF文本提取", "快速文本提取中..."),
            ENGINE_MARKITDOWN: ("MarkItDown转换", "MarkItDown转换中..."),
            ENGINE_PADDLEOCR: ("PaddleOCR识别", "PaddleOCR GPU识别中..."),
            ENGINE_PPSTRUCTURE: ("PP-StructureV3版面分析", "PP-StructureV3版面分析+表格+公式中..."),
            ENGINE_PPCHATOCR: ("PP-ChatOCRv4识别", "PP-ChatOCRv4 OCR+版面分析中..."),
            ENGINE_MINERU: ("MinerU端到端识别", "MinerU版面分析+OCR中..."),
            ENGINE_LLM: ("LLM图片识别", "LLM图片识别中..."),
        }
        step, message = step_messages.get(engine_type, (engine_name, f"{engine_name}转换中..."))
        tracker.update_engine_progress(file_id, engine_type, step, message, percentage=20)
        await asyncio.sleep(0)

        if engine_type == ENGINE_PYMUPDF:
            return await self._convert_pdf_pymupdf(file_id, file_path)
        if engine_type == ENGINE_MARKITDOWN:
            return await self._convert_pdf_markitdown(file_id, file_path)
        if engine_type == ENGINE_PADDLEOCR:
            return await self._convert_pdf_paddleocr(file_id, file_path)
        if engine_type == ENGINE_PPSTRUCTURE:
            return await self._convert_pdf_ppstructure(file_id, file_path)
        if engine_type == ENGINE_PPCHATOCR:
            return await self._convert_pdf_ppchatocr(file_id, file_path)
        if engine_type == ENGINE_MINERU:
            return await self._convert_pdf_mineru(file_id, file_path)
        if engine_type == ENGINE_LLM:
            return await self._convert_pdf_llm(file_id, file_path)

        raise ValueError(f"不支持的PDF引擎类型: {engine_type}")

    async def get_engine_results(self, file_id: str) -> list[EngineResult]:
        """
        获取文件所有引擎的转换结果列表

        Args:
            file_id: 文件ID

        Returns:
            所有引擎的结果列表，按引擎类型排序
        """
        results = self._engine_results.get(file_id, {})
        return list(results.values())

    async def get_engine_result(self, file_id: str, engine_type: str) -> Optional[EngineResult]:
        """
        获取文件指定引擎的转换结果

        Args:
            file_id: 文件ID
            engine_type: 引擎类型标识

        Returns:
            该引擎的结果，不存在返回None
        """
        results = self._engine_results.get(file_id, {})
        return results.get(engine_type)

    async def save_engine_markdown(self, file_id: str, engine_type: str, content: str) -> str:
        """
        保存指定引擎的Markdown内容

        同时更新 _engine_results 和 _markdown_contents（兼容旧接口），
        并保存引擎独立的Markdown文件。

        Args:
            file_id: 文件ID
            engine_type: 引擎类型标识
            content: 用户编辑后的Markdown内容

        Returns:
            保存的文件路径

        Raises:
            ValueError: 文件不存在
        """
        if file_id not in self._files:
            raise ValueError(f"文件不存在: {file_id}")

        # 更新引擎结果
        existing = self._engine_results.get(file_id, {}).get(engine_type)
        engine_name = ENGINE_NAMES.get(engine_type, engine_type)

        result = EngineResult(
            engine_type=engine_type,
            engine_name=engine_name,
            markdown_content=content,
            status="completed",
            char_count=len(content),
            line_count=content.count("\n") + 1 if content else 0,
            duration=existing.duration if existing else 0.0,
        )
        self._set_engine_result(file_id, engine_type, result)

        # 兼容旧接口：更新默认markdown_content
        self._markdown_contents[file_id] = content
        await self._save_to_output(file_id, content)

        # 保存引擎独立的Markdown文件
        output_path = await self._save_engine_output(file_id, engine_type, content)

        logger.info(f"引擎Markdown保存成功: {file_id}/{engine_type}")
        return str(output_path)

    def _set_engine_result(self, file_id: str, engine_type: str, result: EngineResult) -> None:
        """
        设置指定文件的引擎结果

        Args:
            file_id: 文件ID
            engine_type: 引擎类型标识
            result: 引擎结果
        """
        if file_id not in self._engine_results:
            self._engine_results[file_id] = {}
        self._engine_results[file_id][engine_type] = result

    async def _convert_pdf(self, file_id: str, file_path: str, engine_type: str = ENGINE_AUTO) -> tuple[str, str]:
        """
        PDF文件转换，支持四级策略

        auto模式：PyMuPDF → MarkItDown → PaddleOCR → LLM（逐级降级）
        指定引擎模式：只使用指定引擎，便于对比不同引擎识别效果

        Args:
            file_id: 文件ID
            file_path: PDF文件路径
            engine_type: 引擎类型

        Returns:
            (转换后的Markdown文本, 实际使用的引擎名)
        """
        tracker = get_progress_tracker()

        # 全部手动模式：只运行用户选择的引擎
        # auto请求回退到pymupdf
        actual_engine = engine_type if engine_type in {ENGINE_PYMUPDF, ENGINE_MARKITDOWN, ENGINE_PADDLEOCR, ENGINE_PPSTRUCTURE, ENGINE_PPCHATOCR, ENGINE_MINERU, ENGINE_LLM} else ENGINE_MARKITDOWN
        result = await self._run_pdf_engine_step(file_id, file_path, actual_engine, 10)
        return result, actual_engine

    async def _run_pdf_engine_step(self, file_id: str, file_path: str, engine: str, percentage: int) -> str:
        """
        执行单个PDF引擎步骤并更新进度

        Args:
            file_id: 文件ID
            file_path: PDF文件路径
            engine: 引擎类型
            percentage: 当前步骤进度百分比

        Returns:
            当前引擎转换出的Markdown文本
        """
        tracker = get_progress_tracker()
        step_messages = {
            ENGINE_PYMUPDF: ("尝试PyMuPDF文本提取", "快速文本提取中..."),
            ENGINE_MARKITDOWN: ("尝试MarkItDown转换", "MarkItDown转换中..."),
            ENGINE_PADDLEOCR: ("使用PaddleOCR本地识别", "PaddleOCR GPU识别中..."),
            ENGINE_PPSTRUCTURE: ("使用PP-StructureV3版面分析", "PP-StructureV3版面分析+表格+公式中..."),
            ENGINE_PPCHATOCR: ("使用PP-ChatOCRv4识别", "PP-ChatOCRv4 OCR+版面分析中..."),
            ENGINE_MINERU: ("使用MinerU端到端识别", "MinerU版面分析+OCR中..."),
            ENGINE_LLM: ("使用LLM图片识别", "LLM图片识别中..."),
        }
        step, message = step_messages[engine]
        tracker.update(file_id, engine, step, message, percentage=percentage)
        await asyncio.sleep(0)

        if engine == ENGINE_PYMUPDF:
            return await self._convert_pdf_pymupdf(file_id, file_path)
        if engine == ENGINE_MARKITDOWN:
            return await self._convert_pdf_markitdown(file_id, file_path)
        if engine == ENGINE_PADDLEOCR:
            return await self._convert_pdf_paddleocr(file_id, file_path)
        if engine == ENGINE_PPSTRUCTURE:
            return await self._convert_pdf_ppstructure(file_id, file_path)
        if engine == ENGINE_PPCHATOCR:
            return await self._convert_pdf_ppchatocr(file_id, file_path)
        if engine == ENGINE_MINERU:
            return await self._convert_pdf_mineru(file_id, file_path)
        return await self._convert_pdf_llm(file_id, file_path)

    async def _extract_pdf_images(self, file_id: str, file_path: str) -> dict[int, list[dict]]:
        """
        提取PDF中嵌入的原始图片并保存到outputs目录

        遍历PDF每一页，提取所有嵌入图片（过滤小于2KB的装饰图片），
        保存到 outputs/{file_id}/images/ 目录

        Args:
            file_id: 文件ID（用于构建图片保存路径和URL）
            file_path: PDF文件路径

        Returns:
            字典，key为页码(0-based)，value为该页图片信息列表
            图片信息格式: {"name": "page1_img1.png", "index": 0}
        """
        import fitz

        images_dir = Path(settings.OUTPUT_DIR) / file_id / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        def _extract(path):
            doc = fitz.open(path)
            page_embedded = {}
            for i in range(len(doc)):
                page = doc[i]
                embedded = []
                img_list = page.get_images(full=True)
                for img_index, img_info in enumerate(img_list):
                    xref = img_info[0]
                    try:
                        base_image = doc.extract_image(xref)
                        if base_image and base_image.get("image"):
                            img_bytes = base_image["image"]
                            img_ext = base_image.get("ext", "png")
                            # 过滤太小的图片（图标、装饰等，小于2KB）
                            if len(img_bytes) < 2048:
                                continue
                            img_name = f"page{i+1}_img{img_index+1}.{img_ext}"
                            img_save_path = images_dir / img_name
                            with open(img_save_path, "wb") as f:
                                f.write(img_bytes)
                            embedded.append({"name": img_name, "index": img_index})
                    except Exception:
                        continue
                if embedded:
                    page_embedded[i] = embedded
            doc.close()
            return page_embedded

        return await asyncio.to_thread(_extract, file_path)

    def _append_images_to_markdown(self, file_id: str, markdown_content: str, page_images: dict[int, list[dict]]) -> str:
        """
        将提取的嵌入图片引用追加到Markdown内容中对应页面的位置

        优先尝试按"## 第 X 页"分页标记将图片插入到对应页面末尾；
        如果Markdown中没有分页标记，则在末尾按页码顺序追加所有图片

        Args:
            file_id: 文件ID（用于构建图片URL）
            markdown_content: 原始Markdown内容
            page_images: 页码(0-based)到图片列表的映射

        Returns:
            追加图片引用后的Markdown内容
        """
        if not page_images:
            return markdown_content

        # 检查是否有分页标记
        has_page_markers = "## 第 " in markdown_content

        if has_page_markers:
            # 按页分割内容，在每页末尾追加图片
            parts = markdown_content.split("## 第 ")
            result_parts = []

            for idx, part in enumerate(parts):
                if idx == 0:
                    # 第一部分是首页之前的内容（可能为空）
                    result_parts.append(part)
                    # 首页内容在第一个"## 第 "之后
                    continue

                # 解析页码: 格式 "1 页\n\n..."
                page_num = None
                if part and part[0].isdigit():
                    try:
                        space_idx = part.index(" ")
                        page_num = int(part[:space_idx]) - 1  # 转为0-based
                    except (ValueError, IndexError):
                        pass

                result_parts.append("## 第 " + part)

                # 如果该页有图片，追加图片引用
                if page_num is not None and page_num in page_images:
                    img_refs = []
                    for img_info in page_images[page_num]:
                        img_refs.append(f"![{img_info['name']}](/api/files/{file_id}/images/{img_info['name']})")
                    if img_refs:
                        result_parts.append("\n\n**原始图片：**\n\n" + "\n\n".join(img_refs) + "\n\n")

            return "".join(result_parts)
        else:
            # 没有分页标记，在Markdown末尾按页码顺序追加所有图片
            img_section_parts = ["\n\n---\n\n## 原始图片\n\n"]
            for page_num in sorted(page_images.keys()):
                for img_info in page_images[page_num]:
                    img_section_parts.append(f"![{img_info['name']}](/api/files/{file_id}/images/{img_info['name']})\n\n")
            return markdown_content + "".join(img_section_parts)

    async def _convert_pdf_pymupdf(self, file_id: str, file_path: str) -> str:
        """
        使用PyMuPDF提取PDF文本，同时按位置提取嵌入图片和矢量图形

        使用PdfEngine的convert_sync_with_images方法，按页面位置顺序
        交错输出文本、嵌入图片和矢量图形，解决图片错位和流程图缺失问题

        Args:
            file_id: 文件ID（用于图片保存和引用）
            file_path: PDF文件路径

        Returns:
            提取的Markdown文本（含图片引用）
        """
        try:
            engine = PdfEngine()
            images_dir = str(Path(settings.OUTPUT_DIR) / file_id / "images")
            # CPU密集操作，放到线程池避免阻塞事件循环
            text = await asyncio.to_thread(
                engine.convert_sync_with_images, file_path, file_id, images_dir
            )
            return text
        except Exception as e:
            logger.warning(f"PyMuPDF提取失败: {str(e)}")
            return ""

    async def _convert_pdf_paddleocr(self, file_id: str, file_path: str) -> str:
        """
        使用PaddleOCR本地GPU识别PDF，同时提取嵌入图片

        Args:
            file_id: 文件ID
            file_path: PDF文件路径

        Returns:
            PaddleOCR识别得到的Markdown文本（含嵌入图片引用）
        """
        try:
            from app.engines.paddleocr_engine import PaddleOcrEngine
            engine = PaddleOcrEngine()
            text = await asyncio.to_thread(engine.convert_sync, file_path, file_id)

            if not text:
                return ""

            # 提取嵌入图片并追加到Markdown中
            page_images = await self._extract_pdf_images(file_id, file_path)
            if page_images:
                text = self._append_images_to_markdown(file_id, text, page_images)

            return text
        except Exception as e:
            logger.error(f"PaddleOCR识别失败: {str(e)}", exc_info=True)
            return ""

    async def _convert_pdf_mineru(self, file_id: str, file_path: str) -> str:
        """
        使用MinerU端到端识别PDF（版面分析+OCR+公式+表格+图片）

        Args:
            file_id: 文件ID
            file_path: PDF文件路径

        Returns:
            MinerU识别得到的Markdown文本（含图片引用）
        """
        try:
            from app.engines.mineru_engine import MineruEngine
            engine = MineruEngine()
            text = await asyncio.to_thread(engine.convert_sync, file_path, file_id)
            return text
        except Exception as e:
            logger.warning(f"MinerU识别失败: {str(e)}")
            return ""

    async def _convert_pdf_ppstructure(self, file_id: str, file_path: str) -> str:
        """
        使用PP-StructureV3版面分析PDF（表格+公式+印章+Markdown）

        Args:
            file_id: 文件ID
            file_path: PDF文件路径

        Returns:
            PP-StructureV3生成的Markdown文本
        """
        try:
            engine = get_engine(".pdf", ENGINE_PPSTRUCTURE)
            if engine is None:
                return ""
            text = await asyncio.to_thread(engine.convert_sync, file_path, file_id)
            return text
        except Exception as e:
            logger.error(f"PP-StructureV3识别失败: {e}", exc_info=True)
            return f"\n> **错误**：PP-StructureV3 识别失败\n> {e}\n"

    async def _convert_pdf_ppchatocr(self, file_id: str, file_path: str) -> str:
        """
        使用PP-ChatOCRv4Doc识别PDF（OCR+版面分析）

        Args:
            file_id: 文件ID
            file_path: PDF文件路径

        Returns:
            PP-ChatOCRv4生成的Markdown文本
        """
        try:
            engine = get_engine(".pdf", ENGINE_PPCHATOCR)
            if engine is None:
                return ""
            text = await asyncio.to_thread(engine.convert_sync, file_path, file_id)
            return text
        except Exception as e:
            logger.error(f"PP-ChatOCRv4识别失败: {e}", exc_info=True)
            return f"\n> **错误**：PP-ChatOCRv4 识别失败\n> {e}\n"

    async def _convert_pdf_markitdown(self, file_id: str, file_path: str) -> str:
        """
        使用MarkItDown转换PDF，同时提取嵌入图片

        Args:
            file_id: 文件ID（用于图片保存和引用）
            file_path: PDF文件路径

        Returns:
            转换的Markdown文本（含图片引用）
        """
        try:
            from app.engines.markitdown_engine import MarkitdownEngine
            engine = MarkitdownEngine()
            text = await asyncio.to_thread(engine.convert_sync, file_path)

            if not text:
                return ""

            # 提取嵌入图片并追加到Markdown中
            page_images = await self._extract_pdf_images(file_id, file_path)
            if page_images:
                text = self._append_images_to_markdown(file_id, text, page_images)

            return text
        except Exception as e:
            logger.warning(f"MarkItDown转换失败: {str(e)}")
            return ""

    async def _convert_pdf_llm(self, file_id: str, file_path: str) -> str:
        """
        使用多模态LLM识别PDF内容（渲染图片方式）

        同时提取PDF中的原始嵌入图片保存到outputs目录，
        在LLM识别结果中嵌入图片引用，保留原图

        Args:
            file_id: 文件ID（用于进度追踪）
            file_path: PDF文件路径

        Returns:
            识别后的Markdown文本
        """
        import fitz
        from app.services.progress import get_progress_tracker

        tracker = get_progress_tracker()
        llm = get_llm_client()

        # 图片保存目录
        images_dir = Path(settings.OUTPUT_DIR) / file_id / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        # 在线程池中批量渲染所有页面为图片 + 提取嵌入图片
        def render_and_extract_pages(path):
            doc = fitz.open(path)
            total = len(doc)
            page_images = []  # 每页的渲染图片base64
            page_embedded = []  # 每页的嵌入图片信息 [{name, path}]

            zoom = 150 / 72
            mat = fitz.Matrix(zoom, zoom)

            for i in range(total):
                page = doc[i]

                # 渲染整页为图片
                pix = page.get_pixmap(matrix=mat)
                img_b64 = base64.b64encode(pix.tobytes("png")).decode("utf-8")
                page_images.append(img_b64)

                # 提取页面中嵌入的图片
                embedded = []
                img_list = page.get_images(full=True)
                for img_index, img_info in enumerate(img_list):
                    xref = img_info[0]
                    try:
                        base_image = doc.extract_image(xref)
                        if base_image and base_image.get("image"):
                            img_bytes = base_image["image"]
                            img_ext = base_image.get("ext", "png")
                            # 过滤太小的图片（图标、装饰等，小于2KB）
                            if len(img_bytes) < 2048:
                                continue
                            img_name = f"page{i+1}_img{img_index+1}.{img_ext}"
                            img_save_path = images_dir / img_name
                            with open(img_save_path, "wb") as f:
                                f.write(img_bytes)
                            embedded.append({"name": img_name, "index": img_index})
                    except Exception:
                        continue

                page_embedded.append(embedded)

            doc.close()
            return total, page_images, page_embedded

        tracker.update(file_id, ENGINE_LLM, "渲染PDF页面中...", "正在渲染PDF页面并提取图片...", percentage=10)
        await asyncio.sleep(0)

        total_pages, page_images, page_embedded = await asyncio.to_thread(
            render_and_extract_pages, file_path
        )

        tracker.update(file_id, ENGINE_LLM, f"共{total_pages}页，并发识别中", f"LLM识别PDF，共{total_pages}页，并发{min(total_pages, 3)}页...", percentage=15)
        await asyncio.sleep(0)

        # 并发识别所有页面
        completed = [0]  # 用列表以便闭包修改

        async def recognize_page(page_num, img_b64):
            """识别单页并更新进度"""
            try:
                page_md = await llm.recognize_image(img_b64, page_num + 1)
                completed[0] += 1
                pct = 15 + int(completed[0] / total_pages * 70)
                tracker.update(file_id, ENGINE_LLM, f"识别第{completed[0]}/{total_pages}页", f"LLM识别第 {completed[0]}/{total_pages} 页...", percentage=pct)
                await asyncio.sleep(0)
                return page_md
            except Exception as e:
                completed[0] += 1
                logger.error(f"第{page_num + 1}页识别失败: {str(e)}")
                return f"<!-- 第{page_num + 1}页识别失败 -->"

        # 使用asyncio.gather并发识别所有页面
        results = await asyncio.gather(*[
            recognize_page(i, page_images[i]) for i in range(total_pages)
        ])

        # 组装结果，在每页的LLM识别文本后追加原始嵌入图片
        markdown_parts = []
        for i, page_md in enumerate(results):
            markdown_parts.append(f"## 第 {i + 1} 页\n\n")
            markdown_parts.append(page_md)
            # 追加该页提取的原始图片
            if page_embedded[i]:
                markdown_parts.append("\n\n**原始图片：**\n\n")
                for img_info in page_embedded[i]:
                    # 使用相对路径引用图片
                    markdown_parts.append(f"![{img_info['name']}](/api/files/{file_id}/images/{img_info['name']})\n\n")
            markdown_parts.append("\n")
            if i < total_pages - 1:
                markdown_parts.append("---\n\n")

        return "".join(markdown_parts).strip()

    def _is_result_poor(self, result: str) -> bool:
        """
        判断转换结果是否质量差（需要降级到下一级引擎）

        质量差的标准：
        - 结果为空
        - 结果全是乱码
        - 结果只有页码标记/HTML注释标记，没有实质内容
        - 结果包含大量GARBLED_TEXT或IMAGE_PAGE标记（PyMuPDF的降级标记）

        Args:
            result: 转换结果文本

        Returns:
            True表示结果质量差，需要降级
        """
        if not result or not result.strip():
            return True

        import re

        clean = result
        # 去掉HTML注释标记（PyMuPDF的降级标记）
        clean = re.sub(r'<!--\s*GARBLED_TEXT_START\s*-->.*?<!--\s*GARBLED_TEXT_END\s*-->', '', clean, flags=re.DOTALL)
        clean = re.sub(r'<!--\s*IMAGE_PAGE:\d+\s*-->', '', clean)
        # 去掉页码标记和分隔线
        clean = re.sub(r'## 第 \d+ 页', '', clean)
        clean = re.sub(r'---', '', clean)
        # 去掉所有HTML注释
        clean = re.sub(r'<!--.*?-->', '', clean, flags=re.DOTALL)
        clean = clean.strip()

        if not clean:
            return True

        # 检查是否为乱码
        if _is_garbled(clean):
            return True

        return False

    async def save_markdown(self, file_id: str, content: str) -> str:
        """
        保存用户编辑后的Markdown内容（兼容旧接口）

        同时更新 _markdown_contents 和默认的输出文件。

        Args:
            file_id: 文件ID
            content: 用户编辑后的Markdown内容

        Returns:
            保存的文件路径

        Raises:
            ValueError: 文件不存在
        """
        if file_id not in self._files:
            raise ValueError(f"文件不存在: {file_id}")

        self._markdown_contents[file_id] = content
        output_path = await self._save_to_output(file_id, content)

        logger.info(f"Markdown保存成功: {file_id}")
        return str(output_path)

    async def list_files(self) -> list[FileUpload]:
        """
        获取所有文件列表

        Returns:
            文件信息列表
        """
        return list(self._files.values())

    async def get_file(self, file_id: str) -> Optional[FileUpload]:
        """
        获取指定文件信息

        Args:
            file_id: 文件ID

        Returns:
            文件信息，不存在返回None
        """
        return self._files.get(file_id)

    async def get_markdown_content(self, file_id: str) -> Optional[str]:
        """
        获取指定文件的Markdown内容（兼容旧接口，返回默认引擎结果）

        Args:
            file_id: 文件ID

        Returns:
            Markdown内容，不存在返回None
        """
        return self._markdown_contents.get(file_id)

    async def delete_file(self, file_id: str) -> bool:
        """
        删除指定文件及其相关资源

        同时清理上传文件、输出目录（含所有引擎的Markdown文件和图片）、内存中的数据。

        Args:
            file_id: 文件ID

        Returns:
            删除成功返回True，文件不存在返回False
        """
        if file_id not in self._files:
            return False

        file_info = self._files[file_id]

        try:
            stored_filename = f"{file_id}{file_info.file_type}"
            upload_path = Path(settings.UPLOAD_DIR) / stored_filename
            if upload_path.exists():
                upload_path.unlink()

            # 删除默认的Markdown输出文件
            output_path = Path(settings.OUTPUT_DIR) / f"{file_id}.md"
            if output_path.exists():
                output_path.unlink()

            # 删除引擎独立的Markdown输出文件和图片目录
            engine_output_dir = Path(settings.OUTPUT_DIR) / file_id
            if engine_output_dir.exists() and engine_output_dir.is_dir():
                import shutil
                shutil.rmtree(engine_output_dir, ignore_errors=True)

            self._files.pop(file_id, None)
            self._markdown_contents.pop(file_id, None)
            self._engine_results.pop(file_id, None)

            logger.info(f"文件删除成功: {file_id}")
            return True

        except Exception as e:
            logger.error(f"文件删除失败: {file_id}, 错误: {str(e)}")
            return False

    async def get_upload_file_path(self, file_id: str) -> Optional[Path]:
        """
        获取上传文件的完整路径（供预览使用）

        Args:
            file_id: 文件ID

        Returns:
            文件路径，不存在返回None
        """
        file_info = self._files.get(file_id)
        if file_info is None:
            return None

        stored_filename = f"{file_id}{file_info.file_type}"
        file_path = Path(settings.UPLOAD_DIR) / stored_filename

        if file_path.exists():
            return file_path
        return None

    async def _save_to_output(self, file_id: str, content: str) -> Path:
        """
        将Markdown内容保存到默认输出文件（兼容旧接口）

        保存路径: outputs/{file_id}.md

        Args:
            file_id: 文件ID
            content: Markdown内容

        Returns:
            保存的文件路径
        """
        output_path = Path(settings.OUTPUT_DIR) / f"{file_id}.md"
        output_path.write_text(content, encoding="utf-8")
        return output_path

    async def _save_engine_output(self, file_id: str, engine_type: str, content: str) -> Path:
        """
        将指定引擎的Markdown内容保存到引擎独立的输出文件

        保存路径: outputs/{file_id}/{engine_type}.md

        Args:
            file_id: 文件ID
            engine_type: 引擎类型标识
            content: Markdown内容

        Returns:
            保存的文件路径
        """
        output_dir = Path(settings.OUTPUT_DIR) / file_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{engine_type}.md"
        output_path.write_text(content, encoding="utf-8")
        return output_path


# 全局服务实例
_convert_service: Optional[ConvertService] = None


def get_convert_service() -> ConvertService:
    """
    获取转换服务单例

    Returns:
        ConvertService实例
    """
    global _convert_service
    if _convert_service is None:
        _convert_service = ConvertService()
    return _convert_service
