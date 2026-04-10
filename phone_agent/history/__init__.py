"""历史记录模块。"""

from phone_agent.history.manager import (
    TaskHistoryManager,
    TaskRecord,
    get_history_manager
)

__all__ = ['TaskHistoryManager', 'TaskRecord', 'get_history_manager']
