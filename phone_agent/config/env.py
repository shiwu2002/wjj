"""
环境变量配置模块。

提供从环境变量读取配置的辅助函数。
"""

import os
from typing import Optional


def get_env_str(name: str, default: str = "") -> str:
    """获取字符串类型的环境变量。
    
    Args:
        name: 环境变量名称
        default: 默认值
        
    Returns:
        环境变量值或默认值
    """
    return os.getenv(name, default)


def get_env_int(name: str, default: int = 0) -> int:
    """获取整数类型的环境变量。
    
    Args:
        name: 环境变量名称
        default: 默认值
        
    Returns:
        环境变量值或默认值
    """
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def get_env_bool(name: str, default: bool = False) -> bool:
    """获取布尔类型的环境变量。
    
    支持的值："true", "True", "TRUE", "1", "yes" -> True
            "false", "False", "FALSE", "0", "no" -> False
    
    Args:
        name: 环境变量名称
        default: 默认值
        
    Returns:
        转换后的布尔值
    """
    value = os.getenv(name, "").lower().strip()
    
    if not value:
        return default
    
    true_values = {"true", "1", "yes", "y"}
    false_values = {"false", "0", "no", "n"}
    
    if value in true_values:
        return True
    elif value in false_values:
        return False
    else:
        return default


def get_env_optional(name: str) -> Optional[str]:
    """获取可选的环境变量（可能为 None）。
    
    Args:
        name: 环境变量名称
        
    Returns:
        环境变量值或 None
    """
    value = os.getenv(name)
    return value.strip() if value and value.strip() else None


# 预定义的环境变量常量
ENV_KEYS = {
    'BASE_URL': 'PHONE_AGENT_BASE_URL',
    'MODEL_NAME': 'PHONE_AGENT_MODEL',
    'API_KEY': 'PHONE_AGENT_API_KEY',
    'MAX_STEPS': 'PHONE_AGENT_MAX_STEPS',
    'DEVICE_ID': 'PHONE_AGENT_DEVICE_ID',
    'LANG': 'PHONE_AGENT_LANG',
    'VERBOSE': 'PHONE_AGENT_VERBOSE',
    'LOG_LEVEL': 'PHONE_AGENT_LOG_LEVEL',
    'DB_PATH': 'PHONE_AGENT_DB_PATH',
}
