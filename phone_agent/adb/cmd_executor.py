"""ADB 命令执行器 - 使用持久的命令窗口执行 ADB 命令。"""

import subprocess
import sys
import threading
import time
from typing import Optional


class ConsoleWindow:
    """
    持久命令窗口管理类。

    创建一个持久的命令窗口进程，所有 ADB 命令都通过同一个窗口执行，
    避免重复启动多个命令窗口。
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._process: Optional['subprocess.Popen[str]'] = None
        self._pipe = None
        self._window_title = "ADB Command Console"

    def start(self) -> bool:
        """
        启动持久命令窗口。

        Returns:
            True 如果启动成功，False 如果已经启动或启动失败
        """
        if self._process is not None:
            # 检查进程是否还在运行
            if self._process.poll() is None:
                return True  # 已经在运行
            else:
                self._process = None
                self._pipe = None

        if sys.platform != 'win32':
            return False  # 只支持 Windows

        try:
            # 创建一个临时 VBScript 来启动隐藏的 cmd 进程，并通过管道通信
            # 同时创建一个可见的窗口来显示输出
            import tempfile
            import os

            temp_dir = tempfile.gettempdir()

            # 创建一个批处理文件作为命令处理器
            bat_path = os.path.join(temp_dir, "adb_console.bat")
            bat_content = r"""@echo off
title ADB Command Console
echo ========================================
echo ADB Command Console - Ready
echo ========================================
echo.
:loop
set /p cmd=
if "%cmd%"=="__EXIT__" goto end
if "%cmd%"=="" goto loop
echo.
echo [CMD] %cmd%
echo ----------------------------------------
%cmd%
echo.
echo [DONE]
goto loop
:end
echo Console closed.
timeout /t 2 /nobreak >nul
"""
            with open(bat_path, 'w', encoding='utf-8') as f:
                f.write(bat_content)

            # 使用 start 命令在新窗口中启动批处理
            from subprocess import CREATE_NEW_CONSOLE, CREATE_NO_WINDOW

            # 启动进程，使用 PIPE 进行输入
            self._process = subprocess.Popen(
                ['cmd', '/c', bat_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                creationflags=CREATE_NEW_CONSOLE
            )

            # 等待进程启动
            time.sleep(0.5)

            return True

        except Exception as e:
            print(f"Failed to start console window: {e}")
            return False

    def execute(self, cmd: list[str]) -> bool:
        """
        在持久命令窗口中执行命令。

        Args:
            cmd: 命令列表

        Returns:
            True 如果命令成功发送到窗口
        """
        if not self.start():
            return False

        try:
            cmd_str = ' '.join(cmd)
            # 写入命令到进程的标准输入
            if self._process and self._process.stdin:
                self._process.stdin.write(cmd_str + '\n')
                self._process.stdin.flush()
            return True
        except Exception as e:
            print(f"Failed to execute command in console: {e}")
            # 尝试重启
            self._process = None
            self._initialized = False
            return False

    def close(self):
        """关闭持久命令窗口。"""
        if self._process is not None:
            try:
                if self._process.stdin:
                    self._process.stdin.write('__EXIT__\n')
                    self._process.stdin.flush()
                self._process.wait(timeout=3)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            finally:
                self._process = None
                self._pipe = None


# 全局单例
_console_window: Optional[ConsoleWindow] = None


def get_console_window() -> ConsoleWindow:
    """获取全局命令窗口单例。"""
    global _console_window
    if _console_window is None:
        _console_window = ConsoleWindow()
    return _console_window


class CommandExecutor:
    """
    命令执行器，支持在持久的命令窗口中执行 ADB 命令。
    """

    @staticmethod
    def run_in_console(
        cmd: list[str],
        console: bool = True,
        auto_close_delay: int = 1
    ) -> 'subprocess.CompletedProcess[str]':
        """
        在命令窗口中执行命令。

        使用持久命令窗口，如果窗口已存在则直接发送命令，
        否则创建新窗口。

        Args:
            cmd: 命令列表，例如 ["adb", "shell", "input", "tap", "100", "200"]
            console: 是否在可见的命令窗口中执行（仅 Windows 有效）
            auto_close_delay: 命令执行后窗口自动关闭的延迟（秒）- 现在此参数已废弃

        Returns:
            CompletedProcess 对象，包含返回码和输出
        """
        if sys.platform == 'win32' and console:
            return _run_in_persistent_console(cmd)
        else:
            return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")

    @staticmethod
    def run_silent(cmd: list[str], timeout: Optional[int] = None) -> 'subprocess.CompletedProcess[str]':
        """
        在后台静默执行命令（不显示窗口）。

        Args:
            cmd: 命令列表
            timeout: 超时时间（秒）

        Returns:
            CompletedProcess 对象，包含返回码和输出
        """
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout
        )

    @staticmethod
    def run_visible(cmd: list[str], timeout: Optional[int] = None) -> 'subprocess.CompletedProcess[str]':
        """
        在当前可见的终端窗口中执行命令（不创建新窗口）。

        Args:
            cmd: 命令列表
            timeout: 超时时间（秒）

        Returns:
            CompletedProcess 对象，包含返回码和输出
        """
        return subprocess.run(
            cmd,
            capture_output=False,
            text=True,
            encoding="utf-8",
            timeout=timeout
        )


def _run_in_persistent_console(cmd: list[str]) -> 'subprocess.CompletedProcess[str]':
    """
    在持久的 Windows 命令窗口中执行命令。

    命令窗口只创建一次，后续命令都复用同一个窗口。

    Args:
        cmd: 命令列表

    Returns:
        CompletedProcess 对象
    """
    console = get_console_window()

    success = console.execute(cmd)

    if success:
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="Command executed in persistent console window",
            stderr=""
        )
    else:
        # 如果持久窗口执行失败，回退到静默执行
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8"
        )


# 全局配置
_console_mode_enabled = True


def enable_console_mode(enabled: bool = True):
    """
    启用或禁用命令窗口模式。

    Args:
        enabled: True 启用命令窗口，False 使用静默模式
    """
    global _console_mode_enabled
    _console_mode_enabled = enabled


def is_console_mode_enabled() -> bool:
    """
    检查命令窗口模式是否已启用。

    Returns:
        True 如果命令窗口模式已启用
    """
    return _console_mode_enabled


def close_console():
    """
    关闭持久命令窗口。

    调用此函数会关闭已打开的命令窗口。
    """
    global _console_window
    if _console_window is not None:
        _console_window.close()
        _console_window = None


# 便捷函数
def run_adb_command(
    args: list[str],
    device_id: Optional[str] = None,
    console: bool = True
) -> 'subprocess.CompletedProcess[str]':
    """
    运行 ADB 命令的便捷函数。

    Args:
        args: ADB 命令参数列表（不包含 "adb"）
        device_id: 设备 ID
        console: 是否在命令窗口中执行

    Returns:
        CompletedProcess 对象
    """
    cmd = ["adb"]
    if device_id:
        cmd.extend(["-s", device_id])
    cmd.extend(args)

    if console and _console_mode_enabled:
        return CommandExecutor.run_in_console(cmd)
    else:
        return CommandExecutor.run_silent(cmd)
