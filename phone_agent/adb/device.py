"""用于 Android 自动化的设备控制工具。"""

import subprocess
import time
from subprocess import CompletedProcess

from phone_agent.adb.cmd_executor import CommandExecutor
from phone_agent.config.apps import APP_PACKAGES
from phone_agent.config.timing import TIMING_CONFIG


def get_current_app(device_id: str | None = None) -> str:
    """
    获取当前聚焦的应用名称。

    Args:
        device_id: 用于多设备设置的可选 ADB 设备 ID。

    Returns:
        如果识别到则返回应用名称，否则返回 "System Home"。
    """
    # If device_id not specified and multiple devices exist, use the first one
    if not device_id:
        devices = _get_connected_devices()
        if len(devices) == 0:
            raise ValueError("No connected devices")
        elif len(devices) >= 1:
            # Use first available device (even if only one exists)
            device_id = devices[0]

    adb_prefix = _get_adb_prefix(device_id)

    result: CompletedProcess[str] = subprocess.run(
        adb_prefix + ["shell", "dumpsys", "window"], capture_output=True, text=True, encoding="utf-8"
    )
    output = result.stdout
    if not output:
        # Check stderr for device error
        if result.stderr and "more than one device" in result.stderr:
            raise ValueError(f"Multiple devices connected, please specify device_id: {result.stderr.strip()}")
        raise ValueError("No output from dumpsys window")

    # Parse window focus info
    for line in output.split("\n"):
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            for app_name, package in APP_PACKAGES.items():
                if package in line:
                    return app_name

    return "System Home"


def _get_connected_devices() -> list[str]:
    """Get list of connected device IDs."""
    result = CommandExecutor.run_silent(["adb", "devices"], timeout=5)
    devices = []
    for line in result.stdout.strip().split("\n")[1:]:  # Skip header
        if line.strip() and "\tdevice" in line:
            devices.append(line.split("\t")[0].strip())
    return devices


def tap(
    x: int, y: int, device_id: str | None = None, delay: float | None = None
) -> None:
    """
    在指定坐标点击。

    Args:
        x: X 坐标。
        y: Y 坐标。
        device_id: 可选的 ADB 设备 ID。
        delay: 点击后的延迟时间（秒）。如果为 None，则使用配置的默认值。
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_tap_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "input", "tap", str(x), str(y)], capture_output=True
    )
    time.sleep(delay)


def double_tap(
    x: int, y: int, device_id: str | None = None, delay: float | None = None
) -> None:
    """
    在指定坐标双击。

    Args:
        x: X 坐标。
        y: Y 坐标。
        device_id: 可选的 ADB 设备 ID。
        delay: 双击后的延迟时间（秒）。如果为 None，则使用配置的默认值。
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_double_tap_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "input", "tap", str(x), str(y)], capture_output=True
    )
    time.sleep(TIMING_CONFIG.device.double_tap_interval)
    subprocess.run(
        adb_prefix + ["shell", "input", "tap", str(x), str(y)], capture_output=True
    )
    time.sleep(delay)


def long_press(
    x: int,
    y: int,
    duration_ms: int = 3000,
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    """
    在指定坐标长按。

    Args:
        x: X 坐标。
        y: Y 坐标。
        duration_ms: 按压持续时间（毫秒）。
        device_id: 可选的 ADB 设备 ID。
        delay: 长按后的延迟时间（秒）。如果为 None，则使用配置的默认值。
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_long_press_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix
        + ["shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration_ms)],
        capture_output=True,
    )
    time.sleep(delay)


def swipe(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration_ms: int | None = None,
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    """
    从起点滑动到终点。

    Args:
        start_x: 起始 X 坐标。
        start_y: 起始 Y 坐标。
        end_x: 结束 X 坐标。
        end_y: 结束 Y 坐标。
        duration_ms: 滑动持续时间（毫秒）（如果为 None 则自动计算）。
        device_id: 可选的 ADB 设备 ID。
        delay: 滑动后的延迟时间（秒）。如果为 None，则使用配置的默认值。
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_swipe_delay

    adb_prefix = _get_adb_prefix(device_id)

    if duration_ms is None:
        # Calculate duration based on distance
        dist_sq = (start_x - end_x) ** 2 + (start_y - end_y) ** 2
        duration_ms = int(dist_sq / 1000)
        duration_ms = max(1000, min(duration_ms, 2000))  # Clamp between 1000-2000ms

    subprocess.run(
        adb_prefix
        + [
            "shell",
            "input",
            "swipe",
            str(start_x),
            str(start_y),
            str(end_x),
            str(end_y),
            str(duration_ms),
        ],
        capture_output=True,
    )
    time.sleep(delay)


def back(device_id: str | None = None, delay: float | None = None) -> None:
    """
    按返回键。

    Args:
        device_id: 可选的 ADB 设备 ID。
        delay: 按返回键后的延迟时间（秒）。如果为 None，则使用配置的默认值。
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_back_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "input", "keyevent", "4"], capture_output=True
    )
    time.sleep(delay)


def home(device_id: str | None = None, delay: float | None = None) -> None:
    """
    按主页键。

    Args:
        device_id: 可选的 ADB 设备 ID。
        delay: 按主页键后的延迟时间（秒）。如果为 None，则使用配置的默认值。
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_home_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "input", "keyevent", "KEYCODE_HOME"], capture_output=True
    )
    time.sleep(delay)


def launch_app(
    app_name: str, device_id: str | None = None, delay: float | None = None
) -> bool:
    """
    启动应用。

    Args:
        app_name: 应用名称（必须在 APP_PACKAGES 中）。
        device_id: 可选的 ADB 设备 ID。
        delay: 启动后的延迟时间（秒）。如果为 None，则使用配置的默认值。

    Returns:
        如果应用启动成功返回 True，未找到返回 False。
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_launch_delay

    if app_name not in APP_PACKAGES:
        return False

    adb_prefix = _get_adb_prefix(device_id)
    package = APP_PACKAGES[app_name]

    subprocess.run(
        adb_prefix
        + [
            "shell",
            "monkey",
            "-p",
            package,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        ],
        capture_output=True,
    )
    time.sleep(delay)
    return True


def _get_adb_prefix(device_id: str | None) -> list[str]:
    """获取带有可选设备指定的 ADB 命令前缀。"""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]
