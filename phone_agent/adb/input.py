"""用于 Android 设备文本输入的输入工具。"""

import base64
import subprocess


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

    subprocess.run(
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
        ],
        capture_output=True,
        text=True,
    )


def clear_text(device_id: str | None = None) -> None:
    """
    清除当前聚焦输入框中的文本。

    Args:
        device_id: 用于多设备设置的可选 ADB 设备 ID。
    """
    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "am", "broadcast", "-a", "ADB_CLEAR_TEXT"],
        capture_output=True,
        text=True,
    )


def input_text_direct(text: str, device_id: str | None = None) -> None:
    """
    使用原生 ADB input text 命令输入文本。

    与 type_text 不同，此方法不依赖 ADB Keyboard，而是直接使用
    ADB 的原生 input 命令输入文本。适合不支持 ADB Keyboard 的场景。

    Args:
        text: 要输入的文本（仅支持 ASCII 字符和简单符号）。
        device_id: 用于多设备设置的可选 ADB 设备 ID。

    Note:
        此方法有局限性：
        1. 不支持中文等非 ASCII 字符
        2. 特殊字符需要转义
        3. 某些应用可能限制直接输入
        对于复杂文本输入，建议优先使用 type_text() 方法。
    """
    adb_prefix = _get_adb_prefix(device_id)

    # 对特殊字符进行转义处理
    escaped_text = text.replace('"', '\\"').replace(' ', '%s')

    subprocess.run(
        adb_prefix + ["shell", "input", "text", escaped_text],
        capture_output=True,
        text=True,
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

    # 获取当前默认的输入方法编辑器（IME）
    result = subprocess.run(
        adb_prefix + ["shell", "settings", "get", "secure", "default_input_method"],
        capture_output=True,
        text=True,
    )
    current_ime = (result.stdout + result.stderr).strip()

    # 如果当前不是 ADB Keyboard，则进行切换
    if "com.android.adbkeyboard/.AdbIME" not in current_ime:
        subprocess.run(
            adb_prefix + ["shell", "ime", "set", "com.android.adbkeyboard/.AdbIME"],
            capture_output=True,
            text=True,
        )

    # 预热键盘以确保其就绪
    input_text_direct("", device_id)

    return current_ime


def restore_keyboard(ime: str, device_id: str | None = None) -> None:
    """
    恢复原始键盘 IME。

    Args:
        ime: 要恢复的 IME 标识符。
        device_id: 用于多设备设置的可选 ADB 设备 ID。
    """
    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "ime", "set", ime], capture_output=True, text=True
    )


def _get_adb_prefix(device_id: str | None) -> list[str]:
    """获取带有可选设备指定的 ADB 命令前缀。"""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]
