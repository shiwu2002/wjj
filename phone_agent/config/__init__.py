"""Phone Agent 的配置模块。"""

from phone_agent.config.apps import APP_PACKAGES
from phone_agent.config.i18n import get_message
from phone_agent.config.prompts import SYSTEM_PROMPT as SYSTEM_PROMPT_ZH
from phone_agent.config.timing import (
    TIMING_CONFIG,
    ActionTimingConfig,
    ConnectionTimingConfig,
    DeviceTimingConfig,
    TimingConfig,
    get_timing_config,
    update_timing_config,
)

SYSTEM_PROMPT = SYSTEM_PROMPT_ZH


def get_system_prompt(lang: str = "cn") -> str:
    """
    根据语言获取系统提示。
    Returns:
        系统提示字符串。
    """
    return SYSTEM_PROMPT_ZH


__all__ = [
    "APP_PACKAGES",
    "SYSTEM_PROMPT",
    "SYSTEM_PROMPT_ZH",
    "get_system_prompt",
    "get_message",
    "TIMING_CONFIG",
    "TimingConfig",
    "ActionTimingConfig",
    "DeviceTimingConfig",
    "ConnectionTimingConfig",
    "get_timing_config",
    "update_timing_config",
]
