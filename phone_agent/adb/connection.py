"""用于本地和远程设备的 ADB 连接管理。"""

import subprocess
import time
from dataclasses import dataclass
from enum import Enum

from phone_agent.config.timing import TIMING_CONFIG
from subprocess import CompletedProcess


class ConnectionType(Enum):
    """ADB 连接的类型。"""

    USB = "usb"
    WIFI = "wifi"
    REMOTE = "remote"


@dataclass
class DeviceInfo:
    """有关已连接设备的信息。"""

    device_id: str
    status: str
    connection_type: ConnectionType
    model: str | None = None
    android_version: str | None = None


class ADBConnection:
    """
    管理与 Android 设备的 ADB 连接。

    支持 USB、WiFi 和远程 TCP/IP 连接。

    Example:
        >>> conn = ADBConnection()
        >>> # 连接到远程设备
        >>> conn.connect("192.168.1.100:5555")
        >>> # 列出设备
        >>> devices = conn.list_devices()
        >>> # 断开连接
        >>> conn.disconnect("192.168.1.100:5555")
    """

    def __init__(self, adb_path: str = "adb"):
        """
        初始化 ADB 连接管理器。

        Args:
            adb_path: ADB 可执行文件路径。
        """
        self.adb_path = adb_path

    def connect(self, address: str, timeout: int = 10) -> tuple[bool, str]:
        """
        通过 TCP/IP 连接到远程设备。

        Args:
            address: 设备地址，格式为 "host:port"（例如 "192.168.1.100:5555"）。
            timeout: 连接超时时间（秒）。

        Returns:
            (成功，消息) 元组。

        Note:
            远程设备必须启用 TCP/IP 调试。
            在设备上运行：adb tcpip 5555
        """
        # Validate address format
        if ":" not in address:
            address = f"{address}:5555"  # Default ADB port

        try:
            result: CompletedProcess[str] = subprocess.run(
                [self.adb_path, "connect", address],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            output = result.stdout + result.stderr

            if "connected" in output.lower():
                return True, f"Connected to {address}"
            elif "already connected" in output.lower():
                return True, f"Already connected to {address}"
            else:
                return False, output.strip()

        except subprocess.TimeoutExpired:
            return False, f"Connection timeout after {timeout}s"
        except Exception as e:
            return False, f"Connection error: {e}"

    def disconnect(self, address: str | None = None) -> tuple[bool, str]:
        """
        从远程设备断开连接。

        Args:
            address: 要断开的设备地址。如果为 None，则断开所有连接。

        Returns:
            (成功，消息) 元组。
        """
        try:
            cmd = [self.adb_path, "disconnect"]
            if address:
                cmd.append(address)

            result: CompletedProcess[str] = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=5)

            output = result.stdout + result.stderr
            return True, output.strip() or "Disconnected"

        except Exception as e:
            return False, f"Disconnect error: {e}"

    def list_devices(self) -> list[DeviceInfo]:
        """
        列出所有已连接的设备。

        Returns:
            DeviceInfo 对象列表。
        """
        try:
            result: CompletedProcess[str] = subprocess.run(
                [self.adb_path, "devices", "-l"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            devices: list[DeviceInfo] = []
            for line in result.stdout.strip().split("\n")[1:]:  # Skip header
                if not line.strip():
                    continue

                parts = line.split()
                if len(parts) >= 2:
                    device_id = parts[0]
                    status = parts[1]

                    # Determine connection type
                    if ":" in device_id:
                        conn_type = ConnectionType.REMOTE
                    elif "emulator" in device_id:
                        conn_type = ConnectionType.USB  # Emulator via USB
                    else:
                        conn_type = ConnectionType.USB

                    # Parse additional info
                    model = None
                    for part in parts[2:]:
                        if part.startswith("model:"):
                            model = part.split(":", 1)[1]
                            break

                    devices.append(
                        DeviceInfo(
                            device_id=device_id,
                            status=status,
                            connection_type=conn_type,
                            model=model,
                        )
                    )

            return devices

        except Exception as e:
            print(f"Error listing devices: {e}")
            return []

    def get_device_info(self, device_id: str | None = None) -> DeviceInfo | None:
        """
        获取设备的详细信息。

        Args:
            device_id: 设备 ID。如果为 None，则使用第一个可用设备。

        Returns:
            DeviceInfo 或 None（如果未找到）。
        """
        devices = self.list_devices()

        if not devices:
            return None

        if device_id is None:
            return devices[0]

        for device in devices:
            if device.device_id == device_id:
                return device

        return None

    def is_connected(self, device_id: str | None = None) -> bool:
        """
        检查设备是否已连接。

        Args:
            device_id: 要检查的设备 ID。如果为 None，则检查是否有设备已连接。

        Returns:
            如果已连接返回 True，否则返回 False。
        """
        devices = self.list_devices()

        if not devices:
            return False

        if device_id is None:
            return any(d.status == "device" for d in devices)

        return any(d.device_id == device_id and d.status == "device" for d in devices)

    def enable_tcpip(
        self, port: int = 5555, device_id: str | None = None
    ) -> tuple[bool, str]:
        """
        在 USB 连接的设备上启用 TCP/IP 调试。

        这允许后续的无线连接。

        Args:
            port: ADB 的 TCP 端口（默认：5555）。
            device_id: 设备 ID。如果为 None，则使用第一个可用设备。

        Returns:
            (成功，消息) 元组。

        Note:
            设备必须先通过 USB 连接。
            之后可以断开 USB 并通过 WiFi 连接。
        """
        try:
            cmd = [self.adb_path]
            if device_id:
                cmd.extend(["-s", device_id])
            cmd.extend(["tcpip", str(port)])

            result: CompletedProcess[str] = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=10)

            output = result.stdout + result.stderr

            if "restarting" in output.lower() or result.returncode == 0:
                time.sleep(TIMING_CONFIG.connection.adb_restart_delay)
                return True, f"TCP/IP mode enabled on port {port}"
            else:
                return False, output.strip()

        except Exception as e:
            return False, f"Error enabling TCP/IP: {e}"

    def get_device_ip(self, device_id: str | None = None) -> str | None:
        """
        获取已连接设备的 IP 地址。

        Args:
            device_id: 设备 ID。如果为 None，则使用第一个可用设备。

        Returns:
            IP 地址字符串或 None（如果未找到）。
        """
        try:
            cmd = [self.adb_path]
            if device_id:
                cmd.extend(["-s", device_id])
            cmd.extend(["shell", "ip", "route"])

            result: CompletedProcess[str] = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=5)

            # Parse IP from route output
            for line in result.stdout.split("\n"):
                if "src" in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "src" and i + 1 < len(parts):
                            return parts[i + 1]

            # Alternative: try wlan0 interface
            result: CompletedProcess[str] = subprocess.run(
                cmd[:-1] + ["shell", "ip", "addr", "show", "wlan0"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=5,
            )

            for line in result.stdout.split("\n"):
                if "inet " in line:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        return parts[1].split("/")[0]

            return None

        except Exception as e:
            print(f"Error getting device IP: {e}")
            return None

    def restart_server(self) -> tuple[bool, str]:
        """
        重启 ADB 服务器。

        Returns:
            (成功，消息) 元组。
        """
        try:
            # Kill server
            subprocess.run(
                [self.adb_path, "kill-server"], capture_output=True, timeout=5
            )

            time.sleep(TIMING_CONFIG.connection.server_restart_delay)

            # Start server
            subprocess.run(
                [self.adb_path, "start-server"], capture_output=True, timeout=5
            )

            return True, "ADB server restarted"

        except Exception as e:
            return False, f"Error restarting server: {e}"


def quick_connect(address: str) -> tuple[bool, str]:
    """
    快速连接到远程设备的辅助函数。

    Args:
        address: 设备地址（例如 "192.168.1.100" 或 "192.168.1.100:5555"）。

    Returns:
        (成功，消息) 元组。
    """
    conn = ADBConnection()
    return conn.connect(address)


def list_devices() -> list[DeviceInfo]:
    """
    列出已连接设备的辅助函数。

    Returns:
        DeviceInfo 对象列表。
    """
    conn = ADBConnection()
    return conn.list_devices()