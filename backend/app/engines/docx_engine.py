"""
DOCX转换引擎
使用python-docx提取段落、表格、列表，保留标题层级
"""

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.engines.base import BaseEngine


class DocxEngine(BaseEngine):
    """DOCX文件转换引擎，提取段落、表格、列表并转为Markdown"""

    @property
    def supported_extensions(self) -> list[str]:
        """返回DOCX引擎支持的扩展名"""
        return [".docx"]

    async def convert(self, file_path: str) -> str:
        """
        将DOCX文件转换为Markdown格式

        Args:
            file_path: DOCX文件路径

        Returns:
            转换后的Markdown文本，保留标题层级和表格格式
        """
        doc = Document(file_path)
        markdown_parts: list[str] = []

        for element in doc.element.body:
            # 处理段落
            if element.tag.endswith("}p"):
                paragraph = Paragraph(element, doc)
                md_text = self._paragraph_to_markdown(paragraph)
                if md_text:
                    markdown_parts.append(md_text + "\n\n")
            # 处理表格
            elif element.tag.endswith("}tbl"):
                table = Table(element, doc)
                md_table = self._table_to_markdown(table)
                if md_table:
                    markdown_parts.append(md_table + "\n\n")

        return "".join(markdown_parts).strip()

    def _paragraph_to_markdown(self, paragraph: Paragraph) -> str:
        """
        将DOCX段落转换为Markdown格式

        Args:
            paragraph: python-docx的Paragraph对象

        Returns:
            Markdown格式的段落文本
        """
        text = paragraph.text.strip()
        if not text:
            return ""

        style_name = paragraph.style.name if paragraph.style else ""

        # 处理标题层级
        if style_name.startswith("Heading"):
            try:
                level = int(style_name.replace("Heading", "").strip())
                return f"{'#' * level} {text}"
            except ValueError:
                pass

        # 处理列表
        if style_name.startswith("List"):
            indent_level = 0
            if paragraph.paragraph_format and paragraph.paragraph_format.left_indent:
                try:
                    indent_level = int(paragraph.paragraph_format.left_indent.pt // 360)
                except (TypeError, AttributeError):
                    indent_level = 0
            return f"{'  ' * indent_level}- {text}"

        # 普通段落
        return text

    def _table_to_markdown(self, table: Table) -> str:
        """
        将DOCX表格转换为Markdown表格格式

        Args:
            table: python-docx的Table对象

        Returns:
            Markdown格式的表格字符串
        """
        if not table.rows:
            return ""

        lines: list[str] = []

        # 表头
        header_cells = table.rows[0].cells
        header = [cell.text.strip().replace("\n", " ") for cell in header_cells]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] * len(header)) + " |")

        # 表体
        for row in table.rows[1:]:
            cells = row.cells
            row_data = [cell.text.strip().replace("\n", " ") for cell in cells]
            lines.append("| " + " | ".join(row_data) + " |")

        return "\n".join(lines)
