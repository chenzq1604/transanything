"""
转换引擎抽象基类
定义所有文件转换引擎的统一接口
"""

from abc import ABC, abstractmethod


class BaseEngine(ABC):
    """转换引擎抽象基类，所有具体引擎必须继承此类"""

    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """返回该引擎支持的文件扩展名列表"""
        ...

    @abstractmethod
    async def convert(self, file_path: str) -> str:
        """
        将文件转换为Markdown格式

        Args:
            file_path: 源文件路径

        Returns:
            转换后的Markdown文本内容
        """
        ...
