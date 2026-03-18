"""
任务历史记录模块。

提供任务执行历史的存储、查询和管理功能。
使用 SQLite 数据库进行持久化存储。
"""


import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TaskRecord:
    """任务记录数据类。"""
    
    id: int
    task: str
    result: str
    steps: int
    success: bool
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    device_id: str | None
    model_name: str | None
    error_message: str | None = None
    
    def to_dict(self) -> dict[str, int | str | bool | float | None]:
        """转换为字典格式。"""
        return {
            'id': self.id,
            'task': self.task,
            'result': self.result,
            'steps': self.steps,
            'success': self.success,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat(),
            'duration_seconds': self.duration_seconds,
            'device_id': self.device_id,
            'model_name': self.model_name,
            'error_message': self.error_message
        }
    
    @classmethod
    def from_row(cls, row: tuple[int, str, str, int, int, str, str, float, str | None, str | None, str | None]) -> 'TaskRecord':
        """从数据库行创建实例。"""
        return cls(
            id=row[0],
            task=row[1],
            result=row[2],
            steps=row[3],
            success=bool(row[4]),
            start_time=datetime.fromisoformat(row[5]),
            end_time=datetime.fromisoformat(row[6]),
            duration_seconds=row[7],
            device_id=row[8],
            model_name=row[9],
            error_message=row[10]
        )


class TaskHistoryManager:
    """
    任务历史管理器。
    
    负责任务的增删改查操作。
    """
    
    def __init__(self, db_path: str | None = None):
        """
        初始化历史管理器。
        
        Args:
            db_path: 数据库文件路径，默认在项目根目录创建 history.db
        """
        if db_path is None:
            # 默认在项目根目录创建数据库
            project_root = Path(__file__).parent.parent.parent
            db_path = str(project_root / "history.db")
        
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self) -> None:
        """初始化数据库表结构。"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT NOT NULL,
                result TEXT NOT NULL,
                steps INTEGER NOT NULL,
                success BOOLEAN NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                duration_seconds REAL NOT NULL,
                device_id TEXT,
                model_name TEXT,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 创建索引提高查询性能
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_success ON task_history(success)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_created_at ON task_history(created_at)
        ''')
        
        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {self.db_path}")
    
    def add_record(
        self,
        task: str,
        result: str,
        steps: int,
        success: bool,
        start_time: datetime,
        end_time: datetime,
        device_id: str | None = None,
        model_name: str | None = None,
        error_message: str | None = None
    ) -> int:
        """
        添加任务记录。
        
        Args:
            task: 任务描述
            result: 任务结果
            steps: 执行步数
            success: 是否成功
            start_time: 开始时间
            end_time: 结束时间
            device_id: 设备 ID
            model_name: 使用的模型名称
            error_message: 错误消息（如果失败）
            
        Returns:
            新记录的 ID
        """
        duration = (end_time - start_time).total_seconds()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO task_history 
            (task, result, steps, success, start_time, end_time, 
             duration_seconds, device_id, model_name, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            task, result, steps, success,
            start_time.isoformat(), end_time.isoformat(),
            duration, device_id, model_name, error_message
        ))
        
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Added task record #{record_id}: {task[:50]}...")
        return record_id if record_id is not None else 0
    
    def get_record(self, record_id: int) -> TaskRecord | None:
        """
        获取单条记录。
        
        Args:
            record_id: 记录 ID
            
        Returns:
            TaskRecord 对象或 None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM task_history WHERE id = ?
        ''', (record_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return TaskRecord.from_row(row)
        return None
    
    def get_all_records(self, limit: int = 100) -> list[TaskRecord]:
        """
        获取所有记录（默认最多 100 条）。
        
        Args:
            limit: 返回的最大记录数
            
        Returns:
            TaskRecord 列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM task_history 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [TaskRecord.from_row(row) for row in rows]
    
    def get_successful_records(self, limit: int = 50) -> list[TaskRecord]:
        """
        获取成功的任务记录。
        
        Args:
            limit: 返回的最大记录数
            
        Returns:
            TaskRecord 列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM task_history 
            WHERE success = 1 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [TaskRecord.from_row(row) for row in rows]
    
    def get_failed_records(self, limit: int = 50) -> list[TaskRecord]:
        """
        获取失败的任务记录。
        
        Args:
            limit: 返回的最大记录数
            
        Returns:
            TaskRecord 列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM task_history 
            WHERE success = 0 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [TaskRecord.from_row(row) for row in rows]
    
    def search_records(self, keyword: str, limit: int = 50) -> list[TaskRecord]:
        """
        搜索包含关键词的任务记录。
        
        Args:
            keyword: 搜索关键词
            limit: 返回的最大记录数
            
        Returns:
            TaskRecord 列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM task_history 
            WHERE task LIKE ? OR result LIKE ?
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (f'%{keyword}%', f'%{keyword}%', limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [TaskRecord.from_row(row) for row in rows]
    
    def get_statistics(self) -> dict[str, int | float]:
        """
        获取统计信息。
        
        Returns:
            包含统计数据的字典
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 总记录数
        cursor.execute('SELECT COUNT(*) FROM task_history')
        total = cursor.fetchone()[0]
        
        # 成功数
        cursor.execute('SELECT COUNT(*) FROM task_history WHERE success = 1')
        successful = cursor.fetchone()[0]
        
        # 失败数
        cursor.execute('SELECT COUNT(*) FROM task_history WHERE success = 0')
        failed = cursor.fetchone()[0]
        
        # 平均步数
        cursor.execute('SELECT AVG(steps) FROM task_history')
        avg_steps = cursor.fetchone()[0] or 0
        
        # 平均耗时
        cursor.execute('SELECT AVG(duration_seconds) FROM task_history')
        avg_duration = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return {
            'total_tasks': total,
            'successful_tasks': successful,
            'failed_tasks': failed,
            'success_rate': (successful / total * 100) if total > 0 else 0,
            'average_steps': round(avg_steps, 2),
            'average_duration_seconds': round(avg_duration, 2)
        }
    
    def delete_record(self, record_id: int) -> bool:
        """
        删除指定记录。
        
        Args:
            record_id: 记录 ID
            
        Returns:
            是否删除成功
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM task_history WHERE id = ?', (record_id,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        if deleted:
            logger.info(f"Deleted task record #{record_id}")
        return deleted
    
    def clear_all(self) -> bool:
        """
        清空所有记录。
        
        Returns:
            是否清空成功
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM task_history')
        cleared = cursor.rowcount >= 0
        
        conn.commit()
        conn.close()
        
        if cleared:
            logger.info("Cleared all task history")
        return cleared


# 全局单例
_history_manager: TaskHistoryManager | None = None


def get_history_manager(db_path: str | None = None) -> TaskHistoryManager:
    """
    获取全局历史管理器实例。
    
    Args:
        db_path: 数据库路径（可选）
        
    Returns:
        TaskHistoryManager 实例
    """
    global _history_manager
    if _history_manager is None:
        _history_manager = TaskHistoryManager(db_path)
    return _history_manager
