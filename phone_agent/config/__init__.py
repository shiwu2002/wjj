"""Phone Agent 的配置模块。"""

from phone_agent.config.apps import APP_PACKAGES
from phone_agent.config.i18n import get_message, get_messages
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

SYSTEM_PROMPT_ZH 

try:
    from phone_agent.config.apps_harmonyos import list_supported_apps as list_harmonyos_apps
except ImportError:
    pass

try:
    from phone_agent.config.apps_ios import APP_PACKAGES_IOS, list_supported_apps as list_ios_apps
except ImportError:
    APP_PACKAGES_IOS = {}


def get_system_prompt(lang: str = "cn") -> str:
    """
    根据语言获取系统提示。
    Returns:
        系统提示字符串。
    """
    return SYSTEM_PROMPT_ZH


SYSTEM_PROMPT = SYSTEM_PROMPT_ZH

__all__ = [
    "APP_PACKAGES",
    "APP_PACKAGES_IOS",
    "SYSTEM_PROMPT",
    "SYSTEM_PROMPT_ZH",
    "get_system_prompt",
    "get_messages",
    "get_message",
    "TIMING_CONFIG",
    "TimingConfig",
    "ActionTimingConfig",
    "DeviceTimingConfig",
    "ConnectionTimingConfig",
    "get_timing_config",
    "update_timing_config",
]
