"""用于 Android 设备文本输入的输入工具。"""

import base64
import subprocess
from typing import Optional

from phone_agent.adb.cmd_executor import CommandExecutor, is_console_mode_enabled


def type_text(text: str, device_id: str | None = None) -> None:
    """
    使用 ADB Keyboard 在当前聚焦的输入框中输入文本。

    Args:
        text: 要输入的文本。
        device_id: 用于多设备设置的可选 ADB 设备 ID。

    Note:
        需要设备上安装了 ADB Keyboard。
        参见：https://github.com/nicnocquee/AdbKeyboard
    """
    adb_prefix = _get_adb_prefix(device_id)
    encoded_text = base64.b64encode(text.encode("utf-8")).decode("utf-8")

    # 在命令窗口中执行文本输入命令
    CommandExecutor.run_in_console(
        adb_prefix
        + [
            "shell",
            "am",
            "broadcast",
            "-a",
            "ADB_INPUT_B64",
            "--es",
            "msg",
            encoded_text,
        ]
    )


def clear_text(device_id: str | None = None) -> None:
    """
    清除当前聚焦输入框中的文本。

    Args:
        device_id: 用于多设备设置的可选 ADB 设备 ID。
    """
    adb_prefix = _get_adb_prefix(device_id)

    # 在命令窗口中执行清除文本命令
    CommandExecutor.run_in_console(
        adb_prefix + ["shell", "am", "broadcast", "-a", "ADB_CLEAR_TEXT"]
    )


def detect_and_set_adb_keyboard(device_id: str | None = None) -> str:
    """
    检测当前键盘并在需要时切换到 ADB Keyboard。

    Args:
        device_id: 用于多设备设置的可选 ADB 设备 ID。

    Returns:
        原始键盘 IME 标识符以便后续恢复。
    """
    adb_prefix = _get_adb_prefix(device_id)

    # Get current IME - 需要获取输出，使用静默模式
    result = CommandExecutor.run_silent(
        adb_prefix + ["shell", "settings", "get", "secure", "default_input_method"],
        timeout=10
    )
    current_ime = (result.stdout + result.stderr).strip()

    # Switch to ADB Keyboard if not already set
    if "com.android.adbkeyboard/.AdbIME" not in current_ime:
        # 在命令窗口中执行切换命令
        CommandExecutor.run_in_console(
            adb_prefix + ["shell", "ime", "set", "com.android.adbkeyboard/.AdbIME"]
        )

    # Warm up the keyboard
    type_text("", device_id)

    return current_ime


def restore_keyboard(ime: str, device_id: str | None = None) -> None:
    """
    恢复原始键盘 IME。

    Args:
        ime: 要恢复的 IME 标识符。
        device_id: 用于多设备设置的可选 ADB 设备 ID。
    """
    adb_prefix = _get_adb_prefix(device_id)

    # 在命令窗口中执行恢复命令
    CommandExecutor.run_in_console(
        adb_prefix + ["shell", "ime", "set", ime]
    )


def _get_adb_prefix(device_id: str | None) -> list:
    """获取带有可选设备指定的 ADB 命令前缀。"""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]
