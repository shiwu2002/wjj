"""用于根据设备类型选择 ADB的设备工厂。"""

from enum import Enum
from typing import Any


class DeviceType(Enum):
    """设备连接工具的类型。"""

    ADB = "adb"


class DeviceFactory:
    """
    用于获取设备特定实现的工厂类。

    这允许系统使用 Android (ADB) 设备。
    """

    def __init__(self, device_type: DeviceType = DeviceType.ADB):
        """
        初始化设备工厂。

        Args:
            device_type: 要使用的设备类型（ADB）。
        """
        self.device_type = device_type
        self._module = None

    @property
    def module(self):
        """获取适当的设备模块（adb）。"""
        if self._module is None:
            if self.device_type == DeviceType.ADB:
                from phone_agent import adb

                self._module = adb
            else:
                raise ValueError(f"Unknown device type: {self.device_type}")
        return self._module

    def get_screenshot(self, device_id: str | None = None, timeout: int = 10):
        """从设备获取截图。"""
        return self.module.get_screenshot(device_id, timeout)

    def get_current_app(self, device_id: str | None = None) -> str:
        """获取当前应用名称。"""
        return self.module.get_current_app(device_id)

    def tap(
        self, x: int, y: int, device_id: str | None = None, delay: float | None = None
    ):
        """在坐标处点击。"""
        return self.module.tap(x, y, device_id, delay)

    def double_tap(
        self, x: int, y: int, device_id: str | None = None, delay: float | None = None
    ):
        """在坐标处双击。"""
        return self.module.double_tap(x, y, device_id, delay)

    def long_press(
        self,
        x: int,
        y: int,
        duration_ms: int = 3000,
        device_id: str | None = None,
        delay: float | None = None,
    ):
        """在坐标处长按。"""
        return self.module.long_press(x, y, duration_ms, device_id, delay)

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
        device_id: str | None = None,
        delay: float | None = None,
    ):
        """从起点滑动到终点。"""
        return self.module.swipe(
            start_x, start_y, end_x, end_y, duration_ms, device_id, delay
        )

    def back(self, device_id: str | None = None, delay: float | None = None):
        """按返回键。"""
        return self.module.back(device_id, delay)

    def home(self, device_id: str | None = None, delay: float | None = None):
        """按主页键。"""
        return self.module.home(device_id, delay)

    def launch_app(
        self, app_name: str, device_id: str | None = None, delay: float | None = None
    ) -> bool:
        """启动应用。"""
        return self.module.launch_app(app_name, device_id, delay)

    def type_text(self, text: str, device_id: str | None = None):
        """输入文本。"""
        return self.module.type_text(text, device_id)

    def clear_text(self, device_id: str | None = None):
        """清除文本。"""
        return self.module.clear_text(device_id)

    def detect_and_set_adb_keyboard(self, device_id: str | None = None) -> str:
        """检测并设置键盘。"""
        return self.module.detect_and_set_adb_keyboard(device_id)

    def restore_keyboard(self, ime: str, device_id: str | None = None):
        """恢复键盘。"""
        return self.module.restore_keyboard(ime, device_id)

    def list_devices(self):
        """列出已连接的设备。"""
        return self.module.list_devices()

    def get_connection_class(self):
        """获取连接类（ADBConnection）。"""
        from phone_agent.adb import ADBConnection

        return ADBConnection


# 全局设备工厂实例
_device_factory: DeviceFactory | None = None


def set_device_type(device_type: DeviceType = DeviceType.ADB):
    """
    设置全局设备类型。

    Args:
        device_type: 要使用的设备类型（ADB）。
    """
    global _device_factory
    _device_factory = DeviceFactory(device_type)


def get_device_factory() -> DeviceFactory:
    """
    获取全局设备工厂实例。

    Returns:
        设备工厂实例。
    """
    global _device_factory
    if _device_factory is None:
        _device_factory = DeviceFactory(DeviceType.ADB)
    return _device_factory
