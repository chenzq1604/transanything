"""
PDF转换引擎
使用PyMuPDF(fitz)提取PDF文本，支持表格提取、乱码修复、图片位置保留和矢量图形渲染
"""

import base64
import io
import logging
from pathlib import Path
from typing import Optional

import fitz

from app.engines.base import BaseEngine

logger = logging.getLogger(__name__)


def _is_garbled(text: str) -> bool:
    """
    检测文本是否为乱码

    通过统计不可读字符比例判断，如果大量字符在常见中文/ASCII范围外则判定为乱码

    Args:
        text: 待检测文本

    Returns:
        True表示文本为乱码
    """
    if not text or not text.strip():
        return False

    # 去掉数字、标点、空格等常见字符
    clean = text.strip()
    # 统计连续乱码片段的比例
    readable_count = 0
    total_count = 0
    for ch in clean:
        if ch in '\n\r\t ':
            continue
        total_count += 1
        # 可读字符：ASCII可打印字符、常见中文Unicode范围
        code = ord(ch)
        if (0x20 <= code <= 0x7E  # ASCII可打印
            or 0x4E00 <= code <= 0x9FFF  # CJK统一汉字
            or 0x3000 <= code <= 0x303F  # CJK标点
            or 0xFF00 <= code <= 0xFFEF  # 全角字符
            or 0x2000 <= code <= 0x206F  # 通用标点
            or 0x00C0 <= code <= 0x024F  # 拉丁字母扩展
            or code in (0x2014, 0x2018, 0x2019, 0x201C, 0x201D)  # 破折号、引号
        ):
            readable_count += 1

    if total_count == 0:
        return False

    # 可读字符比例低于70%判定为乱码
    readable_ratio = readable_count / total_count
    return readable_ratio < 0.7


class PdfEngine(BaseEngine):
    """PDF文件转换引擎，支持文本提取、表格提取、乱码修复、图片位置保留和矢量图形渲染"""

    @property
    def supported_extensions(self) -> list[str]:
        """返回PDF引擎支持的扩展名"""
        return [".pdf"]

    async def convert(self, file_path: str) -> str:
        """
        将PDF文件转换为Markdown格式（异步包装）

        Args:
            file_path: PDF文件路径

        Returns:
            转换后的Markdown文本
        """
        return self.convert_sync(file_path)

    def convert_sync(self, file_path: str) -> str:
        """
        将PDF文件转换为Markdown格式（同步版本，不含图片提取）

        优先使用PyMuPDF提取文本，如果文本为乱码或为空，
        则将页面标记为需要LLM识别

        Args:
            file_path: PDF文件路径

        Returns:
            转换后的Markdown文本
        """
        doc = fitz.open(file_path)
        markdown_parts: list[str] = []

        try:
            for page_num in range(len(doc)):
                page = doc[page_num]

                # 添加页面分隔标记
                if page_num > 0:
                    markdown_parts.append("\n---\n\n")
                markdown_parts.append(f"## 第 {page_num + 1} 页\n\n")

                # 尝试提取文本
                page_text = page.get_text("text")

                if page_text.strip() and not _is_garbled(page_text):
                    # 文本正常，直接提取
                    markdown_parts.append(self._extract_page_with_tables(page))
                elif page_text.strip() and _is_garbled(page_text):
                    # 有文本但是乱码，标记需要LLM修复
                    logger.info(f"第{page_num + 1}页文本为乱码，将使用LLM修复")
                    garbled_text = self._extract_page_with_tables(page)
                    markdown_parts.append(f"<!-- GARBLED_TEXT_START -->\n{garbled_text}\n<!-- GARBLED_TEXT_END -->\n")
                else:
                    # 无文本（图片型PDF），标记需要LLM识别
                    logger.info(f"第{page_num + 1}页无文本，为图片型页面")
                    markdown_parts.append(f"<!-- IMAGE_PAGE:{page_num + 1} -->\n")

        finally:
            doc.close()

        result = "".join(markdown_parts).strip()

        # 如果全部是乱码或图片，返回带标记的内容让LLM处理
        return result

    def convert_sync_with_images(self, file_path: str, file_id: str, images_dir: str) -> str:
        """
        将PDF文件转换为Markdown格式（含图片提取，按位置顺序交错输出）

        与convert_sync不同，此方法会：
        1. 提取嵌入图片并按页面位置插入到对应位置（解决图片错位问题）
        2. 检测矢量图形（如流程图）并渲染为图片（解决矢量图缺失问题）

        Args:
            file_path: PDF文件路径
            file_id: 文件ID（用于构建图片URL）
            images_dir: 图片保存目录路径

        Returns:
            转换后的Markdown文本（含图片引用）
        """
        images_path = Path(images_dir)
        images_path.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(file_path)
        markdown_parts: list[str] = []

        try:
            for page_num in range(len(doc)):
                page = doc[page_num]

                # 添加页面分隔标记
                if page_num > 0:
                    markdown_parts.append("\n---\n\n")
                markdown_parts.append(f"## 第 {page_num + 1} 页\n\n")

                # 尝试提取文本
                page_text = page.get_text("text")

                if page_text.strip() and not _is_garbled(page_text):
                    # 文本正常，按位置顺序提取文本+图片+矢量图形
                    markdown_parts.append(
                        self._extract_page_with_position(page, doc, page_num, file_id, images_path)
                    )
                elif page_text.strip() and _is_garbled(page_text):
                    # 有文本但是乱码，标记需要LLM修复
                    logger.info(f"第{page_num + 1}页文本为乱码，将使用LLM修复")
                    garbled_text = self._extract_page_with_tables(page)
                    markdown_parts.append(f"<!-- GARBLED_TEXT_START -->\n{garbled_text}\n<!-- GARBLED_TEXT_END -->\n")
                else:
                    # 无文本（图片型PDF），标记需要LLM识别
                    logger.info(f"第{page_num + 1}页无文本，为图片型页面")
                    markdown_parts.append(f"<!-- IMAGE_PAGE:{page_num + 1} -->\n")

        finally:
            doc.close()

        return "".join(markdown_parts).strip()

    def _extract_page_with_position(
        self, page: fitz.Page, doc: fitz.Document, page_num: int,
        file_id: str, images_path: Path
    ) -> str:
        """
        按位置顺序提取页面内容（文本+嵌入图片+矢量图形）

        将文本块、嵌入图片和矢量图形按垂直位置排序后交错输出，
        确保图片出现在正确的位置

        Args:
            page: PyMuPDF页面对象
            doc: PyMuPDF文档对象（用于提取图片数据）
            page_num: 页码（0-based，用于命名图片）
            file_id: 文件ID
            images_path: 图片保存目录

        Returns:
            页面的Markdown文本（含图片引用）
        """
        items = []

        # 1. 收集文本块（按位置）
        page_dict = page.get_text("dict")
        for block in page_dict.get("blocks", []):
            if block["type"] == 0:  # 文本块
                text = self._extract_text_from_block(block)
                if text.strip():
                    items.append({
                        "type": "text",
                        "y": block["bbox"][1],  # 顶部y坐标
                        "x": block["bbox"][0],  # 左侧x坐标
                        "content": text,
                    })

        # 2. 收集嵌入图片（按位置，使用xref提取原始图片数据）
        seen_xrefs = set()
        try:
            image_infos = page.get_image_info(xrefs=True)
            for img_info in image_infos:
                xref = img_info.get("number")
                bbox = img_info.get("bbox")
                if not xref or not bbox or xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                # 过滤太小的图片（图标、装饰等）
                width = bbox[2] - bbox[0]
                height = bbox[3] - bbox[1]
                if width < 20 or height < 20:
                    continue
                items.append({
                    "type": "image",
                    "y": bbox[1],
                    "x": bbox[0],
                    "xref": xref,
                })
        except Exception as e:
            logger.warning(f"获取图片信息失败: {e}")

        # 3. 收集矢量图形区域（流程图等）
        try:
            drawings = page.get_drawings()
            if drawings:
                # 计算所有绘图命令的合并边界框
                draw_rects = []
                for d in drawings:
                    rect = d.get("rect")
                    if rect:
                        r = fitz.Rect(rect)
                        # 过滤太小的矩形（线条、下划线等）
                        if r.width > 30 and r.height > 30:
                            draw_rects.append(r)

                if draw_rects:
                    # 合并相邻/重叠的矩形区域
                    merged_regions = self._merge_nearby_rects(draw_rects, gap=30)
                    for idx, region in enumerate(merged_regions):
                        # 裁剪到页面范围
                        clip = region & page.rect
                        if not clip.is_empty and clip.width > 30 and clip.height > 30:
                            items.append({
                                "type": "vector",
                                "y": clip.y0,
                                "x": clip.x0,
                                "region": clip,
                                "index": idx,
                            })
        except Exception as e:
            logger.warning(f"获取矢量图形失败: {e}")

        # 4. 按垂直位置排序（y坐标优先，y相同时按x坐标）
        items.sort(key=lambda item: (item["y"], item["x"]))

        # 5. 按顺序输出
        parts = []
        img_count = 0

        for item in items:
            if item["type"] == "text":
                parts.append(item["content"] + "\n\n")
            elif item["type"] == "image":
                img_md = self._save_embedded_image(
                    doc, item["xref"], page_num, img_count, file_id, images_path
                )
                if img_md:
                    img_count += 1
                    parts.append(img_md + "\n\n")
            elif item["type"] == "vector":
                img_md = self._render_vector_region(
                    page, item["region"], page_num, item["index"], file_id, images_path
                )
                if img_md:
                    img_count += 1
                    parts.append(img_md + "\n\n")

        return "".join(parts)

    def _extract_text_from_block(self, block: dict) -> str:
        """
        从文本块中提取纯文本

        Args:
            block: get_text("dict")返回的文本块

        Returns:
            提取的文本
        """
        block_text = ""
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                block_text += span.get("text", "")
            block_text += "\n"
        return block_text.strip()

    def _save_embedded_image(
        self, doc: fitz.Document, xref: int, page_num: int,
        img_count: int, file_id: str, images_path: Path
    ) -> str:
        """
        提取并保存嵌入图片，返回Markdown图片引用

        Args:
            doc: PyMuPDF文档对象
            xref: 图片的xref引用
            page_num: 页码（0-based）
            img_count: 当前页面的图片序号
            file_id: 文件ID
            images_path: 图片保存目录

        Returns:
            Markdown图片引用字符串，失败返回空字符串
        """
        try:
            base_image = doc.extract_image(xref)
            if not base_image or not base_image.get("image"):
                return ""
            img_bytes = base_image["image"]
            img_ext = base_image.get("ext", "png")
            # 过滤太小的图片（图标、装饰等，小于2KB）
            if len(img_bytes) < 2048:
                return ""
            img_name = f"page{page_num + 1}_img{img_count + 1}.{img_ext}"
            img_path = images_path / img_name
            with open(img_path, "wb") as f:
                f.write(img_bytes)
            return f"![{img_name}](/api/files/{file_id}/images/{img_name})"
        except Exception as e:
            logger.warning(f"提取嵌入图片失败(xref={xref}): {e}")
            return ""

    def _render_vector_region(
        self, page: fitz.Page, region: fitz.Rect, page_num: int,
        index: int, file_id: str, images_path: Path
    ) -> str:
        """
        渲染矢量图形区域为图片并保存，返回Markdown图片引用

        用于处理流程图、示意图等矢量绘制的图形，
        这些图形不是嵌入的光栅图片，需要渲染才能捕获

        Args:
            page: PyMuPDF页面对象
            region: 要渲染的区域矩形
            page_num: 页码（0-based）
            index: 矢量图形序号
            file_id: 文件ID
            images_path: 图片保存目录

        Returns:
            Markdown图片引用字符串，失败返回空字符串
        """
        try:
            zoom = 150 / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, clip=region)
            img_name = f"page{page_num + 1}_vector{index + 1}.png"
            img_path = images_path / img_name
            pix.save(str(img_path))
            return f"![矢量图形](/api/files/{file_id}/images/{img_name})"
        except Exception as e:
            logger.warning(f"渲染矢量图形失败: {e}")
            return ""

    def _merge_nearby_rects(self, rects: list, gap: int = 30) -> list:
        """
        合并相邻或重叠的矩形区域

        将距离小于gap的矩形合并为一个更大的区域，
        用于将分散的矢量绘图命令合并为完整的图形区域

        Args:
            rects: 矩形列表
            gap: 合并间距阈值（像素）

        Returns:
            合并后的矩形列表
        """
        if not rects:
            return []

        # 按y坐标排序
        sorted_rects = sorted(rects, key=lambda r: (r.y0, r.x0))
        merged = [sorted_rects[0]]

        for rect in sorted_rects[1:]:
            last = merged[-1]
            # 如果当前矩形与上一个合并的矩形距离小于gap，则合并
            expanded = fitz.Rect(
                last.x0 - gap, last.y0 - gap,
                last.x1 + gap, last.y1 + gap
            )
            if rect.intersects(expanded):
                merged[-1] = last | rect
            else:
                merged.append(rect)

        return merged

    def _extract_page_with_tables(self, page: fitz.Page) -> str:
        """
        提取页面文本，处理表格

        Args:
            page: PyMuPDF页面对象

        Returns:
            页面的Markdown文本
        """
        parts: list[str] = []

        # 尝试提取表格
        tables = page.find_tables()
        if tables and tables.tables:
            # 提取页面文本（表格区域外的文本）
            text_blocks = page.get_text("dict")["blocks"]
            for block in text_blocks:
                if block["type"] == 0:  # 文本块
                    block_text = ""
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            block_text += span.get("text", "")
                        block_text += "\n"
                    block_text = block_text.strip()
                    if block_text:
                        parts.append(block_text + "\n\n")

            # 提取表格并转为Markdown格式
            for table in tables.tables:
                md_table = self._table_to_markdown(table)
                if md_table:
                    parts.append(md_table + "\n\n")
        else:
            # 无表格，直接提取文本
            page_text = page.get_text("text")
            if page_text.strip():
                parts.append(page_text + "\n\n")

        return "".join(parts)

    def _table_to_markdown(self, table) -> str:
        """
        将PDF表格转换为Markdown表格格式

        Args:
            table: PyMuPDF提取的表格对象

        Returns:
            Markdown格式的表格字符串
        """
        try:
            table_data = table.extract()
            if not table_data or len(table_data) < 1:
                return ""

            lines: list[str] = []

            # 表头
            header = table_data[0]
            header = [str(cell) if cell else "" for cell in header]
            lines.append("| " + " | ".join(header) + " |")
            lines.append("| " + " | ".join(["---"] * len(header)) + " |")

            # 表体
            for row in table_data[1:]:
                row = [str(cell) if cell else "" for cell in row]
                lines.append("| " + " | ".join(row) + " |")

            return "\n".join(lines)
        except Exception:
            return ""

    def render_page_to_base64(self, file_path: str, page_num: int, dpi: int = 150) -> Optional[str]:
        """
        将PDF指定页面渲染为图片并返回base64编码

        Args:
            file_path: PDF文件路径
            page_num: 页码（从0开始）
            dpi: 渲染DPI

        Returns:
            base64编码的PNG图片，失败返回None
        """
        try:
            doc = fitz.open(file_path)
            if page_num >= len(doc):
                return None

            page = doc[page_num]
            # 计算缩放矩阵
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)

            # 转为PNG bytes
            img_bytes = pix.tobytes("png")
            doc.close()

            # base64编码
            return base64.b64encode(img_bytes).decode("utf-8")
        except Exception as e:
            logger.error(f"渲染PDF页面失败: {str(e)}")
            return None
