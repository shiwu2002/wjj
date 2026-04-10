"""Phone Agent 的时序配置。

此模块定义了应用程序中所有可配置的等待时间。
用户可以通过修改此文件或设置环境变量来自定义这些值。
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


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

    @classmethod
    def from_dict(cls, data: dict) -> "ActionTimingConfig":
        """从字典创建配置。"""
        if not data:
            return cls()
        return cls(
            keyboard_switch_delay=data.get('keyboard_switch_delay', 1.0),
            text_clear_delay=data.get('text_clear_delay', 1.0),
            text_input_delay=data.get('text_input_delay', 1.0),
            keyboard_restore_delay=data.get('keyboard_restore_delay', 1.0),
        )

    def to_dict(self) -> dict:
        """将配置转换为字典。"""
        return {
            'keyboard_switch_delay': self.keyboard_switch_delay,
            'text_clear_delay': self.text_clear_delay,
            'text_input_delay': self.text_input_delay,
            'keyboard_restore_delay': self.keyboard_restore_delay,
        }


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

    @classmethod
    def from_dict(cls, data: dict) -> "DeviceTimingConfig":
        """从字典创建配置。"""
        if not data:
            return cls()
        return cls(
            default_tap_delay=data.get('default_tap_delay', 1.0),
            default_double_tap_delay=data.get('default_double_tap_delay', 1.0),
            double_tap_interval=data.get('double_tap_interval', 0.1),
            default_long_press_delay=data.get('default_long_press_delay', 1.0),
            default_swipe_delay=data.get('default_swipe_delay', 1.0),
            default_back_delay=data.get('default_back_delay', 1.0),
            default_home_delay=data.get('default_home_delay', 1.0),
            default_launch_delay=data.get('default_launch_delay', 1.0),
        )

    def to_dict(self) -> dict:
        """将配置转换为字典。"""
        return {
            'default_tap_delay': self.default_tap_delay,
            'default_double_tap_delay': self.default_double_tap_delay,
            'double_tap_interval': self.double_tap_interval,
            'default_long_press_delay': self.default_long_press_delay,
            'default_swipe_delay': self.default_swipe_delay,
            'default_back_delay': self.default_back_delay,
            'default_home_delay': self.default_home_delay,
            'default_launch_delay': self.default_launch_delay,
        }


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

    @classmethod
    def from_dict(cls, data: dict) -> "ConnectionTimingConfig":
        """从字典创建配置。"""
        if not data:
            return cls()
        return cls(
            adb_restart_delay=data.get('adb_restart_delay', 2.0),
            server_restart_delay=data.get('server_restart_delay', 1.0),
        )

    def to_dict(self) -> dict:
        """将配置转换为字典。"""
        return {
            'adb_restart_delay': self.adb_restart_delay,
            'server_restart_delay': self.server_restart_delay,
        }


@dataclass
class TimingConfig:
    """组合所有时序设置的主时序配置。"""

    action: ActionTimingConfig
    device: DeviceTimingConfig
    connection: ConnectionTimingConfig

    def __init__(
        self,
        action: Optional[ActionTimingConfig] = None,
        device: Optional[DeviceTimingConfig] = None,
        connection: Optional[ConnectionTimingConfig] = None,
    ):
        """初始化所有时序配置。"""
        self.action = action or ActionTimingConfig()
        self.device = device or DeviceTimingConfig()
        self.connection = connection or ConnectionTimingConfig()

    @classmethod
    def from_dict(cls, data: dict) -> "TimingConfig":
        """从字典创建配置。"""
        if not data:
            return cls()
        return cls(
            action=ActionTimingConfig.from_dict(data.get('action', {})),
            device=DeviceTimingConfig.from_dict(data.get('device', {})),
            connection=ConnectionTimingConfig.from_dict(data.get('connection', {})),
        )

    def to_dict(self) -> dict:
        """将配置转换为字典。"""
        return {
            'action': self.action.to_dict(),
            'device': self.device.to_dict(),
            'connection': self.connection.to_dict(),
        }


def _find_config_file() -> Optional[Path]:
    """查找配置文件。"""
    # 可能的配置文件路径
    possible_paths = [
        Path(__file__).parent.parent.parent / "config.json",
        Path(__file__).parent / "config.json",
        Path.cwd() / "config.json",
    ]

    for path in possible_paths:
        if path.exists():
            return path
    return None


def load_timing_from_config(config_path: Optional[Path] = None) -> TimingConfig:
    """
    从配置文件加载时序配置。

    Args:
        config_path: 配置文件路径，如果为 None 则自动查找。

    Returns:
        加载的 TimingConfig 实例。
    """
    if config_path is None:
        config_path = _find_config_file()

    if config_path is None or not config_path.exists():
        return TimingConfig()

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        timing_data = config.get('timing', {})
        return TimingConfig.from_dict(timing_data)
    except (json.JSONDecodeError, IOError):
        return TimingConfig()


# 全局时序配置实例
# 用户可以通过环境变量、配置文件或在运行时修改这些值
TIMING_CONFIG = load_timing_from_config()


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
