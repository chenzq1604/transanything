"""
转换进度追踪模块
管理转换过程中的进度状态，支持多引擎独立进度追踪和SSE推送
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConvertProgress:
    """转换进度数据类"""
    file_id: str
    current_engine: str = ""
    current_step: str = ""
    engines_tried: list[str] = field(default_factory=list)
    total_steps: int = 0
    current_step_num: int = 0
    status: str = "idle"  # idle/converting/completed/failed
    message: str = ""
    percentage: int = 0  # 0-100
    # 多引擎进度：key是engine_type，value是该引擎的进度
    engine_progresses: dict[str, "ConvertProgress"] = field(default_factory=dict)


class ProgressTracker:
    """转换进度追踪器，管理所有转换任务的进度状态，支持多引擎独立追踪"""

    def __init__(self) -> None:
        """初始化进度追踪器"""
        self._progress: dict[str, ConvertProgress] = {}
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def init_progress(self, file_id: str, total_steps: int = 4) -> None:
        """
        初始化转换进度

        Args:
            file_id: 文件ID
            total_steps: 总步骤数
        """
        self._progress[file_id] = ConvertProgress(
            file_id=file_id,
            total_steps=total_steps,
            status="converting",
        )
        self._notify(file_id)

    def update(self, file_id: str, engine: str, step: str, message: str = "", percentage: int = 0) -> None:
        """
        更新转换进度

        Args:
            file_id: 文件ID
            engine: 当前引擎名称
            step: 当前步骤描述
            message: 附加消息
            percentage: 进度百分比(0-100)
        """
        if file_id not in self._progress:
            self.init_progress(file_id)

        progress = self._progress[file_id]
        progress.current_engine = engine
        progress.current_step = step
        progress.message = message
        progress.status = "converting"
        progress.percentage = percentage

        # 如果是新引擎，添加到已尝试列表
        if engine and engine not in progress.engines_tried:
            progress.engines_tried.append(engine)
            progress.current_step_num = len(progress.engines_tried)

        self._notify(file_id)

    def complete(self, file_id: str, final_engine: str, message: str = "转换完成") -> None:
        """
        标记转换完成

        Args:
            file_id: 文件ID
            final_engine: 最终使用的引擎
            message: 完成消息
        """
        if file_id in self._progress:
            progress = self._progress[file_id]
            progress.status = "completed"
            progress.current_engine = final_engine
            progress.message = message
            progress.percentage = 100
            if final_engine and final_engine not in progress.engines_tried:
                progress.engines_tried.append(final_engine)
                progress.current_step_num = len(progress.engines_tried)
        self._notify(file_id)

    def fail(self, file_id: str, message: str = "转换失败") -> None:
        """
        标记转换失败

        Args:
            file_id: 文件ID
            message: 失败消息
        """
        if file_id in self._progress:
            self._progress[file_id].status = "failed"
            self._progress[file_id].message = message
        self._notify(file_id)

    def get_progress(self, file_id: str) -> Optional[ConvertProgress]:
        """
        获取转换进度

        Args:
            file_id: 文件ID

        Returns:
            进度信息，不存在返回None
        """
        return self._progress.get(file_id)

    def init_engine_progress(self, file_id: str, engine_type: str) -> None:
        """
        初始化单个引擎的进度

        如果文件的总进度不存在，会自动创建。同时在该文件进度下
        创建指定引擎的子进度对象。

        Args:
            file_id: 文件ID
            engine_type: 引擎类型标识
        """
        if file_id not in self._progress:
            self._progress[file_id] = ConvertProgress(
                file_id=file_id,
                status="converting",
            )

        progress = self._progress[file_id]
        progress.engine_progresses[engine_type] = ConvertProgress(
            file_id=file_id,
            current_engine=engine_type,
            status="converting",
            message=f"{engine_type} 准备中...",
            percentage=0,
        )
        # 更新整体状态
        progress.status = "converting"
        self._notify(file_id)

    def update_engine_progress(self, file_id: str, engine_type: str, step: str, message: str, percentage: int) -> None:
        """
        更新单个引擎的进度

        同时重新计算整体进度（所有引擎进度的平均值）。

        Args:
            file_id: 文件ID
            engine_type: 引擎类型标识
            step: 当前步骤描述
            message: 附加消息
            percentage: 该引擎的进度百分比(0-100)
        """
        if file_id not in self._progress:
            self.init_progress(file_id)

        progress = self._progress[file_id]

        if engine_type not in progress.engine_progresses:
            self.init_engine_progress(file_id, engine_type)

        engine_prog = progress.engine_progresses[engine_type]
        engine_prog.current_step = step
        engine_prog.message = message
        engine_prog.percentage = percentage
        engine_prog.status = "converting"

        # 更新整体进度为所有引擎进度的平均值
        self._recalculate_overall_progress(file_id)
        self._notify(file_id)

    def complete_engine_progress(self, file_id: str, engine_type: str, message: str = "转换完成") -> None:
        """
        标记单个引擎的进度为完成

        完成后重新计算整体进度和状态。

        Args:
            file_id: 文件ID
            engine_type: 引擎类型标识
            message: 完成消息
        """
        if file_id not in self._progress:
            return

        progress = self._progress[file_id]

        if engine_type in progress.engine_progresses:
            engine_prog = progress.engine_progresses[engine_type]
            engine_prog.status = "completed"
            engine_prog.message = message
            engine_prog.percentage = 100

        # 重新计算整体进度和状态
        self._recalculate_overall_progress(file_id)
        self._notify(file_id)

    def fail_engine_progress(self, file_id: str, engine_type: str, message: str = "转换失败") -> None:
        """
        标记单个引擎的进度为失败

        失败后重新计算整体进度和状态。

        Args:
            file_id: 文件ID
            engine_type: 引擎类型标识
            message: 失败消息
        """
        if file_id not in self._progress:
            return

        progress = self._progress[file_id]

        if engine_type in progress.engine_progresses:
            engine_prog = progress.engine_progresses[engine_type]
            engine_prog.status = "failed"
            engine_prog.message = message

        # 重新计算整体进度和状态
        self._recalculate_overall_progress(file_id)
        self._notify(file_id)

    def get_engine_progress(self, file_id: str, engine_type: str) -> Optional[ConvertProgress]:
        """
        获取单个引擎的进度

        Args:
            file_id: 文件ID
            engine_type: 引擎类型标识

        Returns:
            该引擎的进度信息，不存在返回None
        """
        progress = self._progress.get(file_id)
        if progress is None:
            return None
        return progress.engine_progresses.get(engine_type)

    def _recalculate_overall_progress(self, file_id: str) -> None:
        """
        重新计算文件的整体进度和状态

        整体进度 = 所有引擎进度的平均值
        整体状态：
        - 所有引擎完成 -> completed
        - 任一失败但还有在运行 -> converting
        - 全部失败 -> failed
        - 有引擎在运行 -> converting

        Args:
            file_id: 文件ID
        """
        progress = self._progress.get(file_id)
        if progress is None or not progress.engine_progresses:
            return

        engine_progs = list(progress.engine_progresses.values())
        total = len(engine_progs)

        # 计算平均进度
        avg_percentage = sum(ep.percentage for ep in engine_progs) // total
        progress.percentage = avg_percentage

        # 统计各状态数量
        completed_count = sum(1 for ep in engine_progs if ep.status == "completed")
        failed_count = sum(1 for ep in engine_progs if ep.status == "failed")
        converting_count = sum(1 for ep in engine_progs if ep.status == "converting")

        if completed_count == total:
            # 所有引擎都完成
            progress.status = "completed"
            progress.percentage = 100
            progress.message = "所有引擎转换完成"
        elif failed_count == total:
            # 所有引擎都失败
            progress.status = "failed"
            progress.message = "所有引擎转换失败"
        else:
            # 还有引擎在运行中
            progress.status = "converting"
            progress.message = f"转换中（{completed_count}完成/{failed_count}失败/{converting_count}进行中）"

    def subscribe(self, file_id: str) -> asyncio.Queue:
        """
        订阅转换进度更新（用于SSE）

        Args:
            file_id: 文件ID

        Returns:
            进度更新队列
        """
        if file_id not in self._subscribers:
            self._subscribers[file_id] = []

        queue = asyncio.Queue()
        self._subscribers[file_id].append(queue)
        return queue

    def unsubscribe(self, file_id: str, queue: asyncio.Queue) -> None:
        """
        取消订阅

        Args:
            file_id: 文件ID
            queue: 要移除的队列
        """
        if file_id in self._subscribers:
            try:
                self._subscribers[file_id].remove(queue)
            except ValueError:
                pass

    def _notify(self, file_id: str) -> None:
        """
        通知所有订阅者

        Args:
            file_id: 文件ID
        """
        progress = self._progress.get(file_id)
        if not progress:
            return

        queues = self._subscribers.get(file_id, [])
        dead_queues = []

        for queue in queues:
            try:
                queue.put_nowait(progress)
            except asyncio.QueueFull:
                dead_queues.append(queue)

        # 清理满的队列
        for q in dead_queues:
            try:
                self._subscribers[file_id].remove(q)
            except (ValueError, KeyError):
                pass


# 全局进度追踪器
_progress_tracker: Optional[ProgressTracker] = None


def get_progress_tracker() -> ProgressTracker:
    """
    获取进度追踪器单例

    Returns:
        ProgressTracker实例
    """
    global _progress_tracker
    if _progress_tracker is None:
        _progress_tracker = ProgressTracker()
    return _progress_tracker
