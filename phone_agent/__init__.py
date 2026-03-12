"""
PhoneAgent 包。

基于视觉语言模型的 Android 手机自动化工具。
"""

from phone_agent.agent import PhoneAgent, AgentConfig, StepResult
from phone_agent.model import ModelConfig
from phone_agent.history import TaskHistoryManager, get_history_manager
from phone_agent.utils.logger import setup_logger

__version__ = '1.0.0'
__author__ = 'Your Name'
__all__ = [
    'PhoneAgent',
    'AgentConfig', 
    'StepResult',
    'ModelConfig',
    'TaskHistoryManager',
    'get_history_manager',
    'setup_logger',
]
