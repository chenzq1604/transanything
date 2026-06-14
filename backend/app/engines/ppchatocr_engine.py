"""
PP-ChatOCRv4转换引擎
底层使用PPStructureV3管道（PP-ChatOCRv4-doc的visual部分与其同源）。
RT-DETR-H模型在PaddlePaddle 3.3.1 + oneDNN下存在PIR兼容性问题，
因此使用已验证可运行的PPStructureV3管道替代。
"""
import asyncio
import logging
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

import fitz

from app.config import settings
from app.engines.base import BaseEngine

logger = logging.getLogger(__name__)


class PPChatOCREngine(BaseEngine):
    """PP-ChatOCRv4文档理解引擎，OCR+版面分析"""

    def __init__(self) -> None:
        self._pipeline = None
        self._lock = threading.Lock()
        self._last_regions: list[dict] = []

    @property
    def supported_extensions(self) -> list[str]:
        return [".pdf"]

    @property
    def last_regions(self) -> list[dict]:
        return self._last_regions

    async def convert(self, file_path: str, file_id: str | None = None) -> str:
        return await asyncio.to_thread(self.convert_sync, file_path, file_id)

    def convert_sync(self, file_path: str, file_id: str | None = None) -> str:
        pipeline = self._get_pipeline()
        pdf_path = Path(file_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF文件不存在: {file_path}")

        self._last_regions = []

        # 准备图片输出目录
        if file_id:
            images_dir = Path(settings.OUTPUT_DIR) / file_id / "images"
            images_dir.mkdir(parents=True, exist_ok=True)
        else:
            images_dir = None

        with tempfile.TemporaryDirectory(prefix="transanything_ppchatocr_") as temp_dir:
            image_paths = self._render_pdf_pages(pdf_path, Path(temp_dir))
            markdown_pages: list[Any] = []

            for page_idx, image_path in enumerate(image_paths):
                results = pipeline.predict(str(image_path))
                for result in results:
                    self._collect_regions(result, page_idx)
                    md_dict = result.markdown
                    # 保存markdown中引用的图片到输出目录
                    if file_id and images_dir is not None:
                        md_dict = self._save_markdown_images(md_dict, images_dir, page_idx)
                    markdown_pages.append(md_dict)

        full_result = pipeline.concatenate_markdown_pages(markdown_pages)

        if not full_result:
            logger.warning("PP-ChatOCRv4返回内容为空")
            return ""

        full_markdown = full_result.get("markdown_texts", "") if hasattr(full_result, "get") else str(full_result)

        if not full_markdown or not full_markdown.strip():
            logger.warning("PP-ChatOCRv4返回空白Markdown")
            return ""

        if file_id:
            full_markdown = self._rewrite_image_paths(full_markdown, file_id)

        if self._last_regions:
            import json
            full_markdown += f"\n\n<!-- REGIONS:{json.dumps(self._last_regions, ensure_ascii=False)} -->"

        return full_markdown

    def _collect_regions(self, result: Any, page_idx: int) -> None:
        """收集一页的bbox区域数据"""
        try:
            parsing_res_list = result.get("parsing_res_list") if hasattr(result, "get") else getattr(result, "parsing_res_list", None)
            if not parsing_res_list:
                return

            for block in parsing_res_list:
                bbox = getattr(block, "bbox", None)
                label = getattr(block, "label", "unknown")
                order = getattr(block, "order_index", 0)
                block_id = getattr(block, "index", 0)
                content = getattr(block, "content", "") or ""

                if not bbox or len(bbox) < 4:
                    continue
                if label in ("header", "footer", "reference", "page_number"):
                    continue

                region_id = len(self._last_regions)

                self._last_regions.append({
                    "id": region_id,
                    "page": page_idx,
                    "type": label,
                    "bbox": [round(float(bbox[0]), 1), round(float(bbox[1]), 1),
                             round(float(bbox[2]), 1), round(float(bbox[3]), 1)],
                    "order": int(order) if order is not None else 0,
                    "blockId": int(block_id) if block_id is not None else 0,
                    "contentPreview": content[:80] if isinstance(content, str) else "",
                })
        except Exception as e:
            logger.debug("收集regions数据失败: %s", e)

    def _get_pipeline(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline

        with self._lock:
            if self._pipeline is not None:
                return self._pipeline

            try:
                from paddleocr import PPStructureV3
            except ImportError as exc:
                raise RuntimeError("未安装paddleocr，请安装paddleocr>=3.7") from exc

            import os
            os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

            try:
                self._pipeline = PPStructureV3(
                    device=settings.PADDLEOCR_DEVICE,
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_table_recognition=True,
                    use_seal_recognition=False,
                    use_formula_recognition=False,
                )
            except Exception as exc:
                raise RuntimeError(f"PP-ChatOCRv4（底层PPStructureV3）初始化失败: {exc}") from exc

            logger.info("PP-ChatOCRv4（底层PPStructureV3）初始化成功，device=%s", settings.PADDLEOCR_DEVICE)
            return self._pipeline

    def _render_pdf_pages(self, pdf_path: Path, output_dir: Path) -> list[Path]:
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

    def _save_markdown_images(self, md_dict: dict, images_dir: Path, page_idx: int) -> dict:
        """保存markdown_dict中的图片到输出目录，并更新markdown_texts中的图片路径"""
        markdown_images = md_dict.get("markdown_images", {})
        markdown_texts = md_dict.get("markdown_texts", "")

        for src_path, img_obj in markdown_images.items():
            try:
                img_name = Path(src_path).name
                # 添加页码前缀避免重名
                img_name = f"p{page_idx + 1}_{img_name}"
                dst_path = images_dir / img_name
                if hasattr(img_obj, "save"):
                    img_obj.save(str(dst_path))
                elif isinstance(img_obj, bytes):
                    dst_path.write_bytes(img_obj)
                # 替换markdown中的图片路径
                markdown_texts = markdown_texts.replace(
                    str(src_path), str(dst_path)
                )
            except Exception as e:
                logger.debug("保存图片失败 %s: %s", src_path, e)

        md_dict["markdown_texts"] = markdown_texts
        return md_dict

    def _rewrite_image_paths(self, markdown: str, file_id: str) -> str:
        """将Markdown中的本地图片路径转换为API路径，并将HTML img/div标签转为标准Markdown语法"""
        # 处理标准markdown图片语法 ![alt](url)
        def replace_md_img(match):
            alt_text = match.group(1) or ""
            img_path = match.group(2)
            img_name = Path(img_path).name
            return f"![{alt_text}](/api/files/{file_id}/images/{img_name})"

        result = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', replace_md_img, markdown)

        # 将 <div...><img src="..." ...></div> 整体替换为标准Markdown图片语法
        def replace_div_img(match):
            src = match.group(1)
            alt = match.group(2) or ""
            img_name = Path(src).name
            return f"![{alt}](/api/files/{file_id}/images/{img_name})"

        result = re.sub(
            r'<div[^>]*>\s*<img\s+[^>]*src=["\']([^"\']+)["\'][^>]*alt=["\']([^"\']*)["\'][^>]*/?\s*>\s*</div>',
            replace_div_img, result
        )
        result = re.sub(
            r'<div[^>]*>\s*<img\s+[^>]*alt=["\']([^"\']*)["\'][^>]*src=["\']([^"\']+)["\'][^>]*/?\s*>\s*</div>',
            lambda m: f"![{m.group(1)}](/api/files/{file_id}/images/{Path(m.group(2)).name})", result
        )

        # 处理独立的 <img src="..." ...> 标签（不在div中的）
        def replace_html_img(match):
            src = match.group(1)
            alt = match.group(2) or ""
            img_name = Path(src).name
            return f"![{alt}](/api/files/{file_id}/images/{img_name})"

        result = re.sub(
            r'<img\s+[^>]*src=["\']([^"\']+)["\'][^>]*alt=["\']([^"\']*)["\'][^>]*/?\s*>',
            replace_html_img, result
        )
        result = re.sub(
            r'<img\s+[^>]*alt=["\']([^"\']*)["\'][^>]*src=["\']([^"\']+)["\'][^>]*/?\s*>',
            lambda m: f"![{m.group(1)}](/api/files/{file_id}/images/{Path(m.group(2)).name})", result
        )

        # 清理残留的空div标签
        result = re.sub(r'<div[^>]*>\s*</div>', '', result)

        return result
