"""Phone Agent 的时序配置。

此模块定义了应用程序中所有可配置的等待时间。
用户可以通过修改此文件或设置环境变量来自定义这些值。
"""

import os
from dataclasses import dataclass


@dataclass
class ActionTimingConfig:
    """动作处理器时序延迟的配置。"""

    # 文本输入相关延迟（秒）
    keyboard_switch_delay: float = 1.0  # Delay after switching to ADB keyboard
    text_clear_delay: float = 1.0  # Delay after clearing text
    text_input_delay: float = 1.0  # Delay after typing text
    keyboard_restore_delay: float = 1.0  # Delay after restoring original keyboard

    def __post_init__(self):
        """如果存在则从环境变量加载值。"""
        self.keyboard_switch_delay = float(
            os.getenv("PHONE_AGENT_KEYBOARD_SWITCH_DELAY", self.keyboard_switch_delay)
        )
        self.text_clear_delay = float(
            os.getenv("PHONE_AGENT_TEXT_CLEAR_DELAY", self.text_clear_delay)
        )
        self.text_input_delay = float(
            os.getenv("PHONE_AGENT_TEXT_INPUT_DELAY", self.text_input_delay)
        )
        self.keyboard_restore_delay = float(
            os.getenv("PHONE_AGENT_KEYBOARD_RESTORE_DELAY", self.keyboard_restore_delay)
        )


@dataclass
class DeviceTimingConfig:
    """设备操作时序延迟的配置。"""

    # 设备操作的默认延迟（秒）
    default_tap_delay: float = 1.0  # Default delay after tap
    default_double_tap_delay: float = 1.0  # Default delay after double tap
    double_tap_interval: float = 0.1  # Interval between two taps in double tap
    default_long_press_delay: float = 1.0  # Default delay after long press
    default_swipe_delay: float = 1.0  # Default delay after swipe
    default_back_delay: float = 1.0  # Default delay after back button
    default_home_delay: float = 1.0  # Default delay after home button
    default_launch_delay: float = 1.0  # Default delay after launching app

    def __post_init__(self):
        """如果存在则从环境变量加载值。"""
        self.default_tap_delay = float(
            os.getenv("PHONE_AGENT_TAP_DELAY", self.default_tap_delay)
        )
        self.default_double_tap_delay = float(
            os.getenv("PHONE_AGENT_DOUBLE_TAP_DELAY", self.default_double_tap_delay)
        )
        self.double_tap_interval = float(
            os.getenv("PHONE_AGENT_DOUBLE_TAP_INTERVAL", self.double_tap_interval)
        )
        self.default_long_press_delay = float(
            os.getenv("PHONE_AGENT_LONG_PRESS_DELAY", self.default_long_press_delay)
        )
        self.default_swipe_delay = float(
            os.getenv("PHONE_AGENT_SWIPE_DELAY", self.default_swipe_delay)
        )
        self.default_back_delay = float(
            os.getenv("PHONE_AGENT_BACK_DELAY", self.default_back_delay)
        )
        self.default_home_delay = float(
            os.getenv("PHONE_AGENT_HOME_DELAY", self.default_home_delay)
        )
        self.default_launch_delay = float(
            os.getenv("PHONE_AGENT_LAUNCH_DELAY", self.default_launch_delay)
        )


@dataclass
class ConnectionTimingConfig:
    """ADB 连接时序延迟的配置。"""

    # ADB 服务器和连接延迟（秒）
    adb_restart_delay: float = 2.0  # Wait time after enabling TCP/IP mode
    server_restart_delay: float = (
        1.0  # Wait time between killing and starting ADB server
    )

    def __post_init__(self):
        """如果存在则从环境变量加载值。"""
        self.adb_restart_delay = float(
            os.getenv("PHONE_AGENT_ADB_RESTART_DELAY", self.adb_restart_delay)
        )
        self.server_restart_delay = float(
            os.getenv("PHONE_AGENT_SERVER_RESTART_DELAY", self.server_restart_delay)
        )


@dataclass
class TimingConfig:
    """组合所有时序设置的主时序配置。"""

    action: ActionTimingConfig
    device: DeviceTimingConfig
    connection: ConnectionTimingConfig

    def __init__(self):
        """初始化所有时序配置。"""
        self.action = ActionTimingConfig()
        self.device = DeviceTimingConfig()
        self.connection = ConnectionTimingConfig()


# 全局时序配置实例
# 用户可以通过环境变量或在运行时修改这些值
TIMING_CONFIG = TimingConfig()


def get_timing_config() -> TimingConfig:
    """
    获取全局时序配置。

    Returns:
        全局 TimingConfig 实例。
    """
    return TIMING_CONFIG


def update_timing_config(
    action: ActionTimingConfig | None = None,
    device: DeviceTimingConfig | None = None,
    connection: ConnectionTimingConfig | None = None,
) -> None:
    """
    更新全局时序配置。

    Args:
        action: 新的动作时序配置。
        device: 新的设备时序配置。
        connection: 新的连接时序配置。

    Example:
        >>> from phone_agent.config.timing import update_timing_config, ActionTimingConfig
        >>> custom_action = ActionTimingConfig(
        ...     keyboard_switch_delay=0.5,
        ...     text_input_delay=0.5
        ... )
        >>> update_timing_config(action=custom_action)
    """
    global TIMING_CONFIG
    if action is not None:
        TIMING_CONFIG.action = action
    if device is not None:
        TIMING_CONFIG.device = device
    if connection is not None:
        TIMING_CONFIG.connection = connection


__all__ = [
    "ActionTimingConfig",
    "DeviceTimingConfig",
    "ConnectionTimingConfig",
    "TimingConfig",
    "TIMING_CONFIG",
    "get_timing_config",
    "update_timing_config",
]
