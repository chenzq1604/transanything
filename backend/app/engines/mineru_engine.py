"""
MinerU转换引擎
使用MinerU(mineru)端到端识别PDF，支持版面分析、OCR、公式识别、表格识别和图片提取
PyPI包名: mineru (3.3.1+)
"""

import asyncio
import json
import logging
import re
import shutil
import tempfile
from pathlib import Path

from app.engines.base import BaseEngine

logger = logging.getLogger(__name__)


class MineruEngine(BaseEngine):
    """MinerU端到端文档理解引擎，集成版面分析+OCR+公式+表格+图片"""

    def __init__(self) -> None:
        """初始化MinerU引擎"""
        self._last_regions: list[dict] = []

    @property
    def supported_extensions(self) -> list[str]:
        """返回MinerU引擎支持的文件扩展名"""
        return [".pdf"]

    @property
    def last_regions(self) -> list[dict]:
        """获取最近一次转换的region数据，用于前端左右联动"""
        return self._last_regions

    async def convert(self, file_path: str, file_id: str | None = None) -> str:
        """
        异步转换PDF为Markdown文本

        Args:
            file_path: PDF文件路径
            file_id: 文件ID，用于构建图片保存路径

        Returns:
            MinerU识别后的Markdown文本
        """
        return await asyncio.to_thread(self.convert_sync, file_path, file_id)

    def convert_sync(self, file_path: str, file_id: str | None = None) -> str:
        """
        同步转换PDF为Markdown文本

        Args:
            file_path: PDF文件路径
            file_id: 文件ID，用于构建图片保存路径

        Returns:
            MinerU识别后的Markdown文本
        """
        from app.config import settings

        pdf_path = Path(file_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF文件不存在: {file_path}")

        self._last_regions = []

        # 确定输出目录（MinerU输出结构: output_dir/{stem}/{parse_method}/）
        if file_id:
            output_dir = Path(settings.OUTPUT_DIR) / file_id / "mineru"
        else:
            output_dir = Path(tempfile.mkdtemp(prefix="transanything_mineru_"))
        output_dir.mkdir(parents=True, exist_ok=True)

        # 调用MinerU pipeline
        parse_method = self._run_pipeline(pdf_path, output_dir)

        # 读取生成的Markdown文件
        # 输出目录结构: {output_dir}/{pdf_stem}/{parse_method}/{pdf_stem}.md
        md_file = output_dir / pdf_path.stem / parse_method / f"{pdf_path.stem}.md"
        if not md_file.exists():
            logger.warning("MinerU未生成Markdown文件: %s", md_file)
            return ""

        markdown = md_file.read_text(encoding="utf-8")

        # 从content_list.json中提取regions数据
        content_list_file = output_dir / pdf_path.stem / parse_method / f"{pdf_path.stem}_content_list.json"
        if content_list_file.exists():
            self._extract_regions(content_list_file)

        # 将MinerU输出的图片复制到统一images目录并重写路径
        if file_id:
            markdown = self._rewrite_image_paths(markdown, output_dir / pdf_path.stem / parse_method, file_id)

        # 将regions数据附到markdown末尾（不可见JSON，前端解析后移除）
        if self._last_regions:
            markdown += f"\n\n<!-- REGIONS:{json.dumps(self._last_regions, ensure_ascii=False)} -->"

        return markdown

    def _extract_regions(self, content_list_file: Path) -> None:
        """
        从MinerU的content_list.json中提取region数据

        content_list.json结构: 按页分组，每页包含多个block，每个block有type和bbox

        Args:
            content_list_file: content_list.json文件路径
        """
        try:
            with open(content_list_file, "r", encoding="utf-8") as f:
                content_list = json.load(f)

            # content_list是按页的列表，每页是一个列表
            for page_idx, page_blocks in enumerate(content_list):
                if not isinstance(page_blocks, list):
                    continue

                for block in page_blocks:
                    if not isinstance(block, dict):
                        continue

                    bbox = block.get("bbox")
                    block_type = block.get("type", "unknown")

                    # 跳过没有bbox的块
                    if not bbox or not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
                        continue

                    # 跳过无意义的块类型
                    skip_types = {"header", "footer", "page_number", "reference"}
                    if block_type in skip_types:
                        continue

                    region_id = len(self._last_regions)

                    # 提取内容预览
                    content = ""
                    if block.get("text"):
                        content = block["text"][:80]
                    elif block.get("html"):
                        content = block["html"][:80]

                    self._last_regions.append({
                        "id": region_id,
                        "page": page_idx,
                        "type": block_type,
                        "bbox": [round(float(bbox[0]), 1), round(float(bbox[1]), 1),
                                 round(float(bbox[2]), 1), round(float(bbox[3]), 1)],
                        "order": region_id,
                        "blockId": region_id,
                        "contentPreview": content,
                    })

            logger.info("从content_list.json提取了 %d 个regions", len(self._last_regions))

        except Exception as e:
            logger.debug("提取regions数据失败: %s", e)

    def _run_pipeline(self, pdf_path: Path, output_dir: Path) -> str:
        """
        调用MinerU do_parse执行文档解析

        Args:
            pdf_path: PDF文件路径
            output_dir: 输出根目录

        Returns:
            使用的解析方法名称（"auto"/"txt"/"ocr"）
        """
        from mineru.cli.common import do_parse, read_fn

        parse_method = "auto"

        try:
            pdf_bytes = read_fn(str(pdf_path))
        except Exception as exc:
            raise RuntimeError(f"读取PDF文件失败: {exc}") from exc

        try:
            do_parse(
                output_dir=str(output_dir),
                pdf_file_names=[pdf_path.stem],
                pdf_bytes_list=[pdf_bytes],
                p_lang_list=["ch"],
                backend="pipeline",
                parse_method=parse_method,
                formula_enable=True,
                table_enable=True,
                f_dump_md=True,
                f_dump_middle_json=False,
                f_dump_model_output=False,
                f_dump_orig_pdf=False,
                f_dump_content_list=True,
                f_draw_layout_bbox=False,
                f_draw_span_bbox=False,
            )
        except Exception as exc:
            raise RuntimeError(f"MinerU解析失败: {exc}") from exc

        logger.info("MinerU解析成功，输出目录: %s", output_dir)
        return parse_method

    def _rewrite_image_paths(self, markdown: str, mineru_output_dir: Path, file_id: str) -> str:
        """
        将MinerU输出的本地图片路径转换为项目API路径

        MinerU输出的Markdown中图片引用类似:
        - ![](images/page_1_img_0.png)
        需要转换为: ![page_1_img_0.png](/api/files/{file_id}/images/page_1_img_0.png)

        同时将图片从mineru子目录复制到统一的images目录

        Args:
            markdown: 原始Markdown文本
            mineru_output_dir: MinerU输出目录（包含images/子目录）
            file_id: 文件ID

        Returns:
            重写图片路径后的Markdown文本
        """
        from app.config import settings

        images_dir = Path(settings.OUTPUT_DIR) / file_id / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        # 查找MinerU输出目录中的所有图片文件
        mineru_images = (
            list(mineru_output_dir.rglob("*.png"))
            + list(mineru_output_dir.rglob("*.jpg"))
            + list(mineru_output_dir.rglob("*.jpeg"))
        )

        # 将图片复制到统一images目录
        for img_path in mineru_images:
            target = images_dir / img_path.name
            if not target.exists():
                shutil.copy2(str(img_path), str(target))

        # 重写Markdown中的图片引用
        def replace_img(match):
            alt_text = match.group(1) or ""
            img_path = match.group(2)
            img_name = Path(img_path).name
            return f"![{alt_text}](/api/files/{file_id}/images/{img_name})"

        result = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', replace_img, markdown)
        return result
