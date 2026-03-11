"""
Phone Agent - 一个 AI 驱动的手机自动化框架。

此包提供用于使用 AI 模型进行视觉理解和决策来自动化 Android 和 iOS 手机交互的工具。
"""

from phone_agent.agent import PhoneAgent

# 尝试导入 iOS 代理（如果存在）
try:
    from phone_agent.agent_ios import IOSPhoneAgent
except ImportError:
    IOSPhoneAgent = None

# 尝试导入技能模块（如果存在）
try:
    from phone_agent.skill import PhoneAgentExecutor, create_executor
except ImportError:
    PhoneAgentExecutor = None
    create_executor = None

__version__ = "0.1.0"
__all__ = ["PhoneAgent", "IOSPhoneAgent", "PhoneAgentExecutor", "create_executor"]
