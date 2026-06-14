"""
TXT/MD转换引擎
直接读取文本文件内容，Markdown文件直接返回
"""

from pathlib import Path

from app.engines.base import BaseEngine


class TxtEngine(BaseEngine):
    """文本文件转换引擎，支持TXT和MD格式"""

    @property
    def supported_extensions(self) -> list[str]:
        """返回TXT引擎支持的扩展名"""
        return [".txt", ".md", ".markdown", ".csv", ".log"]

    async def convert(self, file_path: str) -> str:
        """
        将文本文件转换为Markdown格式

        对于.md/.markdown文件直接返回内容，
        对于其他文本文件尝试以代码块形式包裹

        Args:
            file_path: 文本文件路径

        Returns:
            文本内容（Markdown文件直接返回，其他格式包裹在代码块中）
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        # 尝试多种编码读取文件
        content = self._read_file_with_encoding(file_path)

        # Markdown文件直接返回
        if ext in (".md", ".markdown"):
            return content

        # CSV文件特殊处理
        if ext == ".csv":
            return self._csv_to_markdown(content)

        # 其他文本文件包裹在代码块中
        lang = ext.lstrip(".") if ext else "text"
        return f"```{lang}\n{content}\n```"

    def _read_file_with_encoding(self, file_path: str) -> str:
        """
        尝试多种编码读取文件内容

        Args:
            file_path: 文件路径

        Returns:
            文件文本内容
        """
        encodings = ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]

        for encoding in encodings:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    return f.read()
            except (UnicodeDecodeError, UnicodeError):
                continue

        # 所有编码都失败，使用二进制模式并替换错误
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    def _csv_to_markdown(self, content: str) -> str:
        """
        将CSV内容转换为Markdown表格

        Args:
            content: CSV格式的文本内容

        Returns:
            Markdown格式的表格字符串
        """
        import csv
        from io import StringIO

        lines: list[str] = []
        reader = csv.reader(StringIO(content))

        for row_idx, row in enumerate(reader):
            if not row:
                continue
            lines.append("| " + " | ".join(cell.strip() for cell in row) + " |")
            if row_idx == 0:
                lines.append("| " + " | ".join(["---"] * len(row)) + " |")

        return "\n".join(lines)
