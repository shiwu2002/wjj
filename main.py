#!/usr/bin/env python3

import argparse
import json
import logging
import os
from pathlib import Path

import shutil
import subprocess
import sys
from typing import Optional
from urllib.parse import urlparse

from openai import OpenAI

from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.config.apps import list_supported_apps
from phone_agent.device_factory import DeviceType, get_device_factory, set_device_type
from phone_agent.model import ModelConfig
from phone_agent.utils.logger import setup_logger, LOG_LEVELS

# 初始化 logger
logger = setup_logger(__name__, level=logging.INFO)


def check_system_requirements(
    device_type: DeviceType = DeviceType.ADB
) -> bool:
    """
    在运行代理之前检查系统要求。

    检查项：
    1. ADB 工具已安装
    2. 至少连接了一台设备
    3. 设备上安装了 ADB 键盘

    Args:
        device_type: 设备工具类型（ADB）。

    Returns:
        如果所有检查通过返回 True，否则返回 False。
    """
    logger.info("Checking system requirements...")
    logger.info("-" * 50)

    all_passed = True

    # Determine tool name and command
    tool_name = "ADB"
    tool_cmd = "adb"

    # Check 1: Tool installed
    logger.info(f"1. Checking {tool_name} installation...")
    if shutil.which(tool_cmd) is None:
        logger.critical("❌ FAILED")
        logger.error(f"   Error: {tool_name} is not installed or not in PATH.")
        logger.error(f"   Solution: Install {tool_name}:")
        if device_type == DeviceType.ADB:
            print("     - macOS: brew install android-platform-tools")
            print("     - Linux: sudo apt install android-tools-adb")
            print(
                "     - Windows: Download from https://developer.android.com/studio/releases/platform-tools"
            )
        all_passed = False
    else:
        # Double check by running version command
        try:
            if device_type == DeviceType.ADB:
                version_cmd = [tool_cmd, "version"]

            result = subprocess.run(
                version_cmd, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                version_line = result.stdout.strip().split("\n")[0]
                print(f"✅ OK ({version_line if version_line else 'installed'})")
            else:
                print("❌ FAILED")
                print(f"   Error: {tool_name} command failed to run.")
                all_passed = False
        except FileNotFoundError:
            print("❌ FAILED")
            print(f"   Error: {tool_name} command not found.")
            all_passed = False
        except subprocess.TimeoutExpired:
            print("❌ FAILED")
            print(f"   Error: {tool_name} command timed out.")
            all_passed = False

    # If ADB is not installed, skip remaining checks
    if not all_passed:
        print("-" * 50)
        print("❌ System check failed. Please fix the issues above.")
        return False

    # Check 2: Device connected
    logger.info("2. Checking connected devices...")
    try:
        if device_type == DeviceType.ADB:
            result = subprocess.run(
                ["adb", "devices"], capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.strip().split("\n")
            # Filter out header and empty lines, look for 'device' status
            devices = [
                line for line in lines[1:] if line.strip() and "\tdevice" in line
            ]
        if not devices:
            print("❌ FAILED")
            print("   Error: No devices connected.")
            print("   Solution:")
            print("     1. Enable USB debugging on your Android device")
            print("     2. Connect via USB and authorize the connection")
            print(
                "     3. Or connect remotely: python main.py --connect <ip>:<port>"
            )
            all_passed = False
        else:
            device_ids = [d.strip() for d in devices]
            print(
                f"✅ OK ({len(devices)} device(s): {', '.join(device_ids[:2])}{'...' if len(device_ids) > 2 else ''})"
            )
    except subprocess.TimeoutExpired:
        print("❌ FAILED")
        print(f"   Error: {tool_name} command timed out.")
        all_passed = False
    except Exception as e:
        print("❌ FAILED")
        print(f"   Error: {e}")
        all_passed = False

    # If no device connected, skip ADB Keyboard check
    if not all_passed:
        print("-" * 50)
        print("❌ System check failed. Please fix the issues above.")
        return False

    # Check 3: ADB Keyboard installed
    if device_type == DeviceType.ADB:
        logger.info("3. Checking ADB Keyboard...")
        try:
            result = subprocess.run(
                ["adb", "shell", "ime", "list", "-s"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            ime_list = result.stdout.strip()

            if "com.android.adbkeyboard/.AdbIME" in ime_list:
                print("✅ OK")
            else:
                print("❌ FAILED")
                print("   Error: ADB Keyboard is not installed on the device.")
                print("   Solution:")
                print("     1. Download ADB Keyboard APK from:")
                print(
                    "        https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk"
                )
                print("     2. Install it on your device: adb install ADBKeyboard.apk")
                print(
                    "     3. Enable it in Settings > System > Languages & Input > Virtual Keyboard"
                )
                all_passed = False
        except subprocess.TimeoutExpired:
            print("❌ FAILED")
            print("   Error: ADB command timed out.")
            all_passed = False
        except Exception as e:
            print("❌ FAILED")
            print(f"   Error: {e}")
            all_passed = False

    print("-" * 50)

    if all_passed:
        print("✅ All system checks passed!\n")
    else:
        print("❌ System check failed. Please fix the issues above.")

    return all_passed


def check_model_api(base_url: str, model_name: str, api_key: str = "EMPTY") -> bool:
    """
    检查模型 API 是否可访问且指定的模型是否存在。

    检查项：
    1. 到 API 端点的网络连接
    2. 模型存在于可用模型列表中

    Args:
        base_url: API 基础 URL
        model_name: 要检查的模型名称
        api_key: 认证用的 API 密钥

    Returns:
        如果所有检查通过返回 True，否则返回 False。
    """
    print("🔍 Checking model API...")
    print("-" * 50)

    all_passed = True

    # Check 1: Network connectivity using chat API
    print(f"1. Checking API connectivity ({base_url})...", end=" ")
    try:
        # Create OpenAI client
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=30.0)

        # Use chat completion to test connectivity (more universally supported than /models)
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5,
            temperature=0.0,
            stream=False,
        )

        # Check if we got a valid response
        if response.choices and len(response.choices) > 0:
            print("✅ OK")
        else:
            print("❌ FAILED")
            print("   Error: Received empty response from API")
            all_passed = False

    except Exception as e:
        print("❌ FAILED")
        error_msg = str(e)

        # Provide more specific error messages
        if "Connection refused" in error_msg or "Connection error" in error_msg:
            print(f"   Error: Cannot connect to {base_url}")
            print("   Solution:")
            print("     1. Check if the model server is running")
            print("     2. Verify the base URL is correct")
            print(f"     3. Try: curl {base_url}/chat/completions")
        elif "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
            print(f"   Error: Connection to {base_url} timed out")
            print("   Solution:")
            print("     1. Check your network connection")
            print("     2. Verify the server is responding")
        elif (
            "Name or service not known" in error_msg
            or "nodename nor servname" in error_msg
        ):
            print(f"   Error: Cannot resolve hostname")
            print("   Solution:")
            print("     1. Check the URL is correct")
            print("     2. Verify DNS settings")
        else:
            print(f"   Error: {error_msg}")

        all_passed = False

    print("-" * 50)

    if all_passed:
        print("✅ Model API checks passed!\n")
    else:
        print("❌ Model API check failed. Please fix the issues above.")

    return all_passed


def load_config() -> dict:
    """从配置文件加载配置。"""
    config_path = Path(__file__).parent / "config.json"
    
    if not config_path.exists():
        logger.warning("Config file not found, using default values")
        return {}
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        logger.info("Loaded configuration from config.json")
        return config
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing config.json: {e}, using default values")
        return {}
    except Exception as e:
        logger.error(f"Error loading config: {e}, using default values")
        return {}


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    # 先加载配置文件
    config = load_config()
    
    # 从配置中获取默认值
    model_config = config.get('model', {})
    agent_config = config.get('agent', {})
    device_config = config.get('device', {})
    
    parser = argparse.ArgumentParser(
        description="Phone Agent - AI-powered phone automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    #启动程序
    python main.py

    # 指定模型端点
    python main.py --base-url http://localhost:8000/v1

    # 使用 API 密钥进行身份验证
    python main.py --apikey sk-xxxxx

    # 使用特定设备运行
    python main.py --device-id emulator-5554

    # 连接到远程设备
    python main.py --connect 192.168.1.100:5555

    # 列出已连接的设备
    python main.py --list-devices

    # 启用 USB 设备上的 TCP/IP 并获取连接信息
    python main.py --enable-tcpip

    # 列出支持的应用
    python main.py --list-apps

        """,
    )

    # Model options (使用配置文件中的默认值)
    parser.add_argument(
        "--base-url",
        type=str,
        default=os.getenv("PHONE_AGENT_BASE_URL", model_config.get('base_url', "http://localhost:8000/v1")),
        help="Model API base URL",
    )

    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("PHONE_AGENT_MODEL", model_config.get('model_name', "autoglm-phone-9b")),
        help="Model name",
    )

    parser.add_argument(
        "--apikey",
        type=str,
        default=os.getenv("PHONE_AGENT_API_KEY", model_config.get('api_key', "EMPTY")),
        help="API key for model authentication",
    )

    parser.add_argument(
        "--max-steps",
        type=int,
        default=int(os.getenv("PHONE_AGENT_MAX_STEPS", agent_config.get('max_steps', 100))),
        help="Maximum steps per task",
    )

    # Device options
    parser.add_argument(
        "--device-id",
        "-d",
        type=str,
        default=os.getenv("PHONE_AGENT_DEVICE_ID", agent_config.get('device_id')),
        help="ADB device ID",
    )

    parser.add_argument(
        "--connect",
        "-c",
        type=str,
        metavar="ADDRESS",
        help="Connect to remote device (e.g., 192.168.1.100:5555)",
    )

    parser.add_argument(
        "--disconnect",
        type=str,
        nargs="?",
        const="all",
        metavar="ADDRESS",
        help="Disconnect from remote device (or 'all' to disconnect all)",
    )

    parser.add_argument(
        "--list-devices", action="store_true", help="List connected devices and exit"
    )

    parser.add_argument(
        "--enable-tcpip",
        type=int,
        nargs="?",
        const=5555,
        metavar="PORT",
        help="Enable TCP/IP debugging on USB device (default port: 5555)",
    )

    # Other options
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress verbose output"
    )

    parser.add_argument(
        "--list-apps", action="store_true", help="List supported apps and exit"
    )

    parser.add_argument(
        "--lang",
        type=str,
        choices=["cn", "en"],
        default=os.getenv("PHONE_AGENT_LANG", agent_config.get('lang', "cn")),
        help="Language for system prompt (cn or en, default: cn)",
    )

    parser.add_argument(
        "--device-type",
        type=str,
        choices=["adb"],
        default=device_config.get('type', "adb"),
        help="Device type: adb for Android (default: adb)",
    )

    parser.add_argument(
        "task",
        nargs="?",
        type=str,
        help="Task to execute (interactive mode if not provided)",
    )

    return parser.parse_args()


def handle_device_commands(args) -> bool:
    """
    Handle device-related commands.

    Returns:
        True if a device command was handled (should exit), False otherwise.
    """
    device_factory = get_device_factory()
    ConnectionClass = device_factory.get_connection_class()
    conn = ConnectionClass()

    # Handle --list-devices
    if args.list_devices:
        devices = device_factory.list_devices()
        if not devices:
            print("No devices connected.")
        else:
            print("Connected devices:")
            print("-" * 60)
            for device in devices:
                status_icon = "[OK]" if device.status == "device" else "[ERR]"
                conn_type = device.connection_type.value
                model_info = f" ({device.model})" if device.model else ""
                print(
                    f"  {status_icon} {device.device_id:<30} [{conn_type}]{model_info}"
                )
        return True

    # Handle --connect
    if args.connect:
        print(f"Connecting to {args.connect}...")
        success, message = conn.connect(args.connect)
        print(f"{'✓' if success else '✗'} {message}")
        if success:
            # Set as default device
            args.device_id = args.connect
        return not success  # Continue if connection succeeded

    # Handle --disconnect
    if args.disconnect:
        if args.disconnect == "all":
            print("Disconnecting all remote devices...")
            success, message = conn.disconnect()
        else:
            print(f"Disconnecting from {args.disconnect}...")
            success, message = conn.disconnect(args.disconnect)
        print(f"{'✓' if success else '✗'} {message}")
        return True

    # Handle --enable-tcpip
    if args.enable_tcpip:
        port = args.enable_tcpip
        print(f"Enabling TCP/IP debugging on port {port}...")

        success, message = conn.enable_tcpip(port, args.device_id)
        print(f"{'✓' if success else '✗'} {message}")

        if success:
            # Try to get device IP
            ip = conn.get_device_ip(args.device_id)
            if ip:
                print(f"\nYou can now connect remotely using:")
                print(f"  python main.py --connect {ip}:{port}")
                print(f"\nOr via ADB directly:")
                print(f"  adb connect {ip}:{port}")
            else:
                print("\nCould not determine device IP. Check device WiFi settings.")
        return True

    return False


def main():
    """Main entry point."""
    args = parse_args()

    # Set device type globally based on args
    device_type = DeviceType.ADB

    # Set device type globally
    set_device_type(device_type)

    # Handle --list-apps (no system check needed)
    if args.list_apps:
        print("Supported Android apps:")
        apps = list_supported_apps()

        for app in sorted(apps):
            print(f"  - {app}")

        return

    # Handle device commands (these may need partial system checks)
    if handle_device_commands(args):
        return

    # Run system requirements check before proceeding
    if not check_system_requirements(device_type):
        sys.exit(1)

    # Check model API connectivity and model availability
    if not check_model_api(args.base_url, args.model, args.apikey):
        sys.exit(1)

    # Create configurations and agent based on device type
    model_config = ModelConfig(
        base_url=args.base_url,
        model_name=args.model,
        api_key=args.apikey,
        lang=args.lang,
    )

    # Create Android agent
    agent_config = AgentConfig(
        max_steps=args.max_steps,
        device_id=args.device_id,
        verbose=not args.quiet,
        lang=args.lang,
    )

    agent = PhoneAgent(
        model_config=model_config,
        agent_config=agent_config,
    )

    # Print header
    print("=" * 50)
    print("Phone Agent - AI-powered phone automation")
    print("=" * 50)
    print(f"Model: {model_config.model_name}")
    print(f"Base URL: {model_config.base_url}")
    print(f"Max Steps: {agent_config.max_steps}")
    print(f"Language: {agent_config.lang}")
    print(f"Device Type: ADB")

    # Show device info
    device_factory = get_device_factory()
    devices = device_factory.list_devices()
    if agent_config.device_id:
        print(f"Device: {agent_config.device_id}")
    elif devices:
        print(f"Device: {devices[0].device_id} (auto-detected)")

    print("=" * 50)

    # Run with provided task or enter interactive mode
    if args.task:
        print(f"\nTask: {args.task}\n")
        result = agent.run(args.task)
        print(f"\nResult: {result}")
    else:
        # Interactive mode
        print("\nEntering interactive mode. Type 'quit' to exit.\n")

        while True:
            try:
                task = input("Enter your task: ").strip()

                if task.lower() in ("quit", "exit", "q"):
                    print("Goodbye!")
                    break

                if not task:
                    continue

                print()
                result = agent.run(task)
                print(f"\nResult: {result}\n")
                agent.reset()

            except KeyboardInterrupt:
                print("\n\nInterrupted. Goodbye!")
                break
            except Exception as e:
                print(f"\nError: {e}\n")


if __name__ == "__main__":
    main()
