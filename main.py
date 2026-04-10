#!/usr/bin/env python3

import argparse
import json
import logging
import os
from pathlib import Path

import shutil
from phone_agent.adb.cmd_executor import CommandExecutor, close_console
import sys
from typing import Optional
from urllib.parse import urlparse

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from openai import OpenAI

from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.config.apps import list_supported_apps
from phone_agent.device_factory import DeviceType, get_device_factory, set_device_type
from phone_agent.model import ModelConfig
from phone_agent.utils.logger import setup_logger, LOG_LEVELS

# Try to import pandas for batch mode
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

# Initialize logger
logger = setup_logger(__name__, level=logging.INFO)


def check_system_requirements(
    device_type: DeviceType = DeviceType.ADB,
    args: Optional[argparse.Namespace] = None,
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

            result = CommandExecutor.run_silent(
                version_cmd, timeout=10
            )
            if result.returncode == 0:
                version_line = result.stdout.strip().split("\n")[0]
                print(f"✅ OK ({version_line if version_line else 'installed'})")
            else:
                print("❌ FAILED")
                print(f"   Error: {tool_name} command failed to run.")
                all_passed = False
        except Exception as e:
            print("❌ FAILED")
            print(f"   Error: {tool_name} command not found.")
            all_passed = False

    # If ADB is not installed, skip remaining checks
    if not all_passed:
        print("-" * 50)
        print("❌ System check failed. Please fix the issues above.")
        return False

    # Check 2: Device connected
    logger.info("2. Checking connected devices...")
    devices = []
    try:
        if device_type == DeviceType.ADB:
            result = CommandExecutor.run_silent(
                ["adb", "devices"], timeout=10
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
            # Build adb command with device ID if specified or if multiple devices exist
            # Note: We need to check all devices (including offline) to avoid 'more than one device' error
            adb_cmd = ["adb"]

            # Determine which device to use
            target_device = None
            if args and args.device_id:
                target_device = args.device_id
            elif len(devices) >= 1:
                # Use first available device
                target_device = devices[0].split("\t")[0].strip()

            if target_device:
                adb_cmd.extend(["-s", target_device])

            adb_cmd.extend(["shell", "ime", "list", "-s"])
            result = CommandExecutor.run_silent(adb_cmd, timeout=10)
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
                print("     3. Enable it in Settings > System > Languages & Input > Virtual Keyboard"
                )
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


def run_batch_mode(args) -> None:
    """运行批量模式。"""
    from phone_agent.batch_runner import BatchQuestionRunner, BatchConfig

    print("=" * 60)
    print("Phone Agent - Batch Mode")
    print("=" * 60)

    # Set device type
    device_type = DeviceType.ADB
    set_device_type(device_type)

    # 加载配置
    config = load_config()
    model_config_dict = config.get('model', {})
    agent_config_dict = config.get('agent', {})

    # 创建模型配置
    model_cfg = ModelConfig(
        base_url=args.base_url or model_config_dict.get('base_url', 'http://localhost:11434/v1'),
        model_name=args.model or model_config_dict.get('model_name', 'qwen3.5:4b'),
        api_key=args.apikey or model_config_dict.get('api_key', 'ollama'),
        use_thinking=model_config_dict.get('use_thinking', False),
        lang=args.lang,
    )

    # 创建批量配置
    batch_cfg = BatchConfig(
        question_column=args.question_column,
        max_questions=args.max_questions,
        skip_existing=args.skip_existing,
        verbose=args.verbose or (not args.quiet),
        max_steps=agent_config_dict.get('max_steps', 50),
    )

    print(f"Input file:      {args.batch}")
    print(f"Output file:     {args.batch_output}")
    print(f"Question column: {args.question_column}")
    print(f"Max questions:   {args.max_questions if args.max_questions > 0 else 'All'}")
    print(f"Skip existing:   {args.skip_existing}")
    print(f"Model:           {model_cfg.model_name}")
    print("=" * 60)

    # 检查 pandas 是否可用
    if not PANDAS_AVAILABLE:
        print("\n⚠️  Warning: pandas not installed. Excel support requires pandas.")
        print("   Install with: pip install pandas openpyxl\n")

    # 创建执行器
    runner = BatchQuestionRunner(model_config=model_cfg, batch_config=batch_cfg)

    # 如果跳过已有答案，先加载现有结果
    if args.skip_existing and args.batch.lower().endswith(('.xlsx', '.xls')):
        print("\nLoading existing results...")
        # 这里可以扩展 batch_runner 支持从输入文件加载已有结果

    # 加载问题
    print(f"\nLoading questions from {args.batch}...")
    try:
        runner.load_questions(args.batch, column=args.question_column)
    except Exception as e:
        print(f"❌ Failed to load questions: {e}")
        return

    # 运行系统检查
    if not check_system_requirements(device_type, args):
        print("\n⚠️  System check failed, continuing anyway...")

    # 执行批量任务
    print("\nStarting batch execution...\n")
    try:
        results = runner.run_batch()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        # 保存进度
        runner._save_progress()
        print("Progress saved to batch_progress.json")
        return
    except Exception as e:
        print(f"\n❌ Batch execution failed: {e}")
        return

    # 导出结果
    print(f"\nExporting results to {args.batch_output}...")
    try:
        runner.export_results(args.batch_output, format="excel")
    except Exception as e:
        print(f"❌ Failed to export results: {e}")
        # 尝试导出为 JSON
        json_output = args.batch_output.rsplit('.', 1)[0] + '.json'
        runner.export_results(json_output, format="json")
        print(f"Results exported to {json_output} instead.")

    # 打印统计
    success_count = sum(1 for r in results if r.success)
    failed_count = len(results) - success_count

    print("\n" + "=" * 60)
    print("Batch Execution Summary")
    print("=" * 60)
    print(f"Total questions:  {len(results)}")
    print(f"Successful:       {success_count}")
    print(f"Failed:           {failed_count}")
    print(f"Success rate:     {success_count/len(results)*100:.1f}%" if results else "N/A")
    print("=" * 60)


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

    # Model options
    # When model type is 'local', prefer config over environment variables
    env_base_url = os.getenv("PHONE_AGENT_BASE_URL")
    env_model = os.getenv("PHONE_AGENT_MODEL")
    env_api_key = os.getenv("PHONE_AGENT_API_KEY")

    # Use config values for local model, env vars for remote model
    is_local = model_config.get('type', 'remote') == 'local'

    parser.add_argument(
        "--base-url",
        type=str,
        default=model_config.get('base_url', "http://localhost:8000/v1") if is_local or not env_base_url else env_base_url,
        help="Model API base URL",
    )

    parser.add_argument(
        "--model",
        type=str,
        default=model_config.get('model_name', "autoglm-phone-9b") if is_local or not env_model else env_model,
        help="Model name",
    )

    parser.add_argument(
        "--apikey",
        type=str,
        default=model_config.get('api_key', "ollama") if is_local or not env_api_key else env_api_key,
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
        "--verbose", "-v", action="store_true", help="Enable verbose output (show detailed execution logs)"
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
        "--config", action="store_true", help="Interactive configuration wizard for local model setup"
    )

    # Batch mode options
    parser.add_argument(
        "--batch",
        type=str,
        metavar="FILE",
        help="Run in batch mode with questions from file (Excel or TXT)",
    )
    parser.add_argument(
        "--batch-output",
        type=str,
        default="batch_results.xlsx",
        help="Output file for batch results (default: batch_results.xlsx)",
    )
    parser.add_argument(
        "--question-column",
        type=str,
        default="问题",
        help="Column name for questions in Excel (default: 问题)",
    )
    parser.add_argument(
        "--max-questions",
        type=int,
        default=0,
        help="Maximum number of questions to process (0=all)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip questions that already have answers in the input file",
    )

    # Timing options
    parser.add_argument(
        "--keyboard-switch-delay", type=float, default=None,
        help="Delay after switching to ADB keyboard (seconds)"
    )
    parser.add_argument(
        "--text-clear-delay", type=float, default=None,
        help="Delay after clearing text (seconds)"
    )
    parser.add_argument(
        "--text-input-delay", type=float, default=None,
        help="Delay after typing text (seconds)"
    )
    parser.add_argument(
        "--keyboard-restore-delay", type=float, default=None,
        help="Delay after restoring original keyboard (seconds)"
    )
    parser.add_argument(
        "--tap-delay", type=float, default=None,
        help="Default delay after tap (seconds)"
    )
    parser.add_argument(
        "--double-tap-delay", type=float, default=None,
        help="Default delay after double tap (seconds)"
    )
    parser.add_argument(
        "--double-tap-interval", type=float, default=None,
        help="Interval between two taps in double tap (seconds)"
    )
    parser.add_argument(
        "--long-press-delay", type=float, default=None,
        help="Default delay after long press (seconds)"
    )
    parser.add_argument(
        "--swipe-delay", type=float, default=None,
        help="Default delay after swipe (seconds)"
    )
    parser.add_argument(
        "--back-delay", type=float, default=None,
        help="Default delay after back button (seconds)"
    )
    parser.add_argument(
        "--home-delay", type=float, default=None,
        help="Default delay after home button (seconds)"
    )
    parser.add_argument(
        "--launch-delay", type=float, default=None,
        help="Default delay after launching app (seconds)"
    )
    parser.add_argument(
        "--adb-restart-delay", type=float, default=None,
        help="Wait time after enabling TCP/IP mode (seconds)"
    )
    parser.add_argument(
        "--server-restart-delay", type=float, default=None,
        help="Wait time between killing and starting ADB server (seconds)"
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


def check_ollama_service(base_url: str) -> bool:
    """
    Check if Ollama service is running.

    Args:
        base_url: Ollama API base URL

    Returns:
        True if service is available, False otherwise
    """
    import requests

    try:
        # First try the /api/tags endpoint (Ollama native)
        parsed = urlparse(base_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        response = requests.get(f"{base}/api/tags", timeout=3.0)
        if response.status_code == 200:
            return True
    except Exception:
        pass

    try:
        # Fallback: try /api/version endpoint
        parsed = urlparse(base_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        response = requests.get(f"{base}/api/version", timeout=3.0)
        if response.status_code == 200:
            return True
    except Exception:
        pass

    try:
        # Last resort: try OpenAI-compatible chat endpoint with empty model
        client = OpenAI(base_url=base_url, api_key="ollama", timeout=3.0)
        response = client.chat.completions.create(
            model="llama3.2",  # Use a common model name instead of "dummy"
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=1,
            stream=False,
        )
        return True
    except Exception:
        return False


def list_ollama_models(base_url: str) -> list[str]:
    """
    List available models in Ollama.

    Args:
        base_url: Ollama API base URL

    Returns:
        List of model names
    """
    try:
        client = OpenAI(base_url=base_url, api_key="ollama", timeout=5.0)
        models = client.models.list()
        return [model.id for model in models.data]
    except Exception:
        return []


def run_config_wizard():
    """Interactive configuration wizard for setting up model and agent."""
    print("=" * 50)
    print("Phone Agent - Configuration Wizard")
    print("=" * 50)
    print()

    config_path = Path(__file__).parent / "config.json"
    config = load_config()

    # Get current config
    model_config = config.get('model', {})
    agent_config = config.get('agent', {})
    device_config = config.get('device', {})

    # ========== Model Configuration ==========
    print("=" * 50)
    print("1. Model Configuration")
    print("=" * 50)
    print()
    print("Select model type:")
    print("  1. Remote API (ModelScope, etc.)")
    print("  2. Local Model (Ollama)")
    print()

    choice = input("Enter your choice (1 or 2): ").strip()

    if choice == "2":
        # Local model configuration
        print()
        print("Configuring Local Model (Ollama)")
        print("-" * 50)

        # Default values
        default_base_url = model_config.get('base_url', 'http://localhost:11434/v1')
        default_model = model_config.get('model_name', 'qwen3.5:4b')
        default_api_key = model_config.get('api_key', 'ollama')

        # Check if Ollama service is running
        print()
        print(f"Checking Ollama service at {default_base_url}...", end=" ")
        ollama_running = check_ollama_service(default_base_url)

        if ollama_running:
            print("✅ Running")
            print()
            # List available models
            models = list_ollama_models(default_base_url)
            if models:
                print("Available models:")
                for i, model in enumerate(models, 1):
                    print(f"  {i}. {model}")
                print()

                model_choice = input(f"Select a model (1-{len(models)}) or enter custom name: ").strip()
                if model_choice.isdigit() and 1 <= int(model_choice) <= len(models):
                    selected_model = models[int(model_choice) - 1]
                elif model_choice:
                    selected_model = model_choice
                else:
                    selected_model = default_model
            else:
                print("⚠️  No models found. You may need to pull a model first.")
                print("   Run: ollama pull qwen3.5:4b")
                selected_model = input(f"Enter model name [{default_model}]: ").strip() or default_model
        else:
            print("❌ Not running")
            print()
            print("Please start Ollama service:")
            print("  1. Install Ollama: https://ollama.com/download")
            print("  2. Run: ollama serve")
            print("  3. Pull a model: ollama pull qwen3.5:4b")
            print()

            base_url = input(f"Enter Ollama base URL [{default_base_url}]: ").strip() or default_base_url
            selected_model = input(f"Enter model name [{default_model}]: ").strip() or default_model
            api_key = input(f"Enter API key [{default_api_key}]: ").strip() or default_api_key
            config['model'] = {
                'type': 'local',
                'base_url': base_url,
                'model_name': selected_model,
                'api_key': api_key,
                'use_thinking': True
            }
            _save_config_interactive(config, config_path)
            _configure_agent_interactive(config, agent_config)
            _save_config_interactive(config, config_path)
            return

        # Enable thinking for local models
        enable_thinking = input("Enable thinking feature for local model? [Y/n]: ").strip().lower()
        use_thinking = enable_thinking != 'n' and enable_thinking != 'no'

        config['model'] = {
            'type': 'local',
            'base_url': default_base_url,
            'model_name': selected_model,
            'api_key': default_api_key,
            'use_thinking': use_thinking
        }

    else:
        # Remote API configuration
        print()
        print("Configuring Remote API")
        print("-" * 50)

        default_base_url = model_config.get('base_url', 'https://api-inference.modelscope.cn/v1')
        default_model = model_config.get('model_name', 'ZhipuAI/AutoGLM-Phone-9B')
        default_api_key = model_config.get('api_key', '')

        base_url = input(f"Enter API base URL [{default_base_url}]: ").strip() or default_base_url
        model_name = input(f"Enter model name [{default_model}]: ").strip() or default_model
        api_key = input(f"Enter API key [{default_api_key}]: ").strip() or default_api_key

        # Remote models don't support thinking feature
        config['model'] = {
            'type': 'remote',
            'base_url': base_url,
            'model_name': model_name,
            'api_key': api_key,
            'use_thinking': False
        }

    # Save config
    _save_config_interactive(config, config_path)

    # ========== Agent Configuration ==========
    _configure_agent_interactive(config, agent_config)

    # ========== Device Configuration ==========
    _configure_device_interactive(config, device_config)

    # ========== Advanced Configuration (Timing) ==========
    _configure_timing_interactive(config)

    # Save all configurations
    _save_config_interactive(config, config_path)

    # Print summary
    _print_config_summary(config)


def _save_config_interactive(config: dict, config_path: Path):
    """Save configuration to file."""
    print()
    print("Saving configuration...")
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print("✅ Configuration saved!")


def _configure_agent_interactive(config: dict, agent_config: dict):
    """Configure agent settings interactively."""
    print()
    print("=" * 50)
    print("2. Agent Configuration")
    print("=" * 50)
    print()

    # Max steps (default: unlimited/0)
    default_max_steps = agent_config.get('max_steps', 0)
    max_steps_input = input(f"Enter maximum steps per task (0=unlimited) [{default_max_steps}]: ").strip()
    max_steps = int(max_steps_input) if max_steps_input else default_max_steps

    # Language
    default_lang = agent_config.get('lang', 'cn')
    print("Select language:")
    print("  1. 中文 (Chinese)")
    print("  2. English")
    lang_choice = input(f"Enter choice (1/2) [{'1' if default_lang == 'cn' else '2'}]: ").strip()
    lang = 'cn' if lang_choice == '1' or (not lang_choice and default_lang == 'cn') else 'en'

    # Verbose output
    default_verbose = agent_config.get('verbose', True)
    verbose_input = input(f"Enable verbose output? [Y/n]: ").strip().lower()
    verbose = verbose_input not in ('n', 'no') if verbose_input else default_verbose

    config['agent'] = {
        'max_steps': max_steps,
        'device_id': agent_config.get('device_id'),
        'verbose': verbose,
        'lang': lang
    }

    print("✅ Agent configuration saved!")


def _configure_device_interactive(config: dict, device_config: dict):
    """Configure device settings interactively."""
    print()
    print("=" * 50)
    print("3. Device Configuration")
    print("=" * 50)
    print()

    # Auto-connect
    default_auto_connect = device_config.get('auto_connect', True)
    auto_connect_input = input(f"Auto-connect to device on startup? [Y/n]: ").strip().lower()
    auto_connect = auto_connect_input not in ('n', 'no') if auto_connect_input else default_auto_connect

    config['device'] = {
        'type': 'adb',
        'remote_address': device_config.get('remote_address'),
        'auto_connect': auto_connect
    }
    print("✅ Device configuration saved!")


def _configure_timing_interactive(config: dict):
    """Configure timing settings interactively."""
    print()
    print("=" * 50)
    print("4. Advanced Configuration (Timing)")
    print("=" * 50)
    print()

    timing_config = config.get('timing', {})

    # Ask if user wants to configure timing settings
    configure_timing = input("Would you like to configure timing settings? [y/N]: ").strip().lower()
    if configure_timing not in ('y', 'yes'):
        print("⏭️  Skipping advanced timing configuration.")
        return

    print()
    print("Timing settings control delays between actions.")
    print("You can accept defaults by pressing Enter for each option.")
    print()

    # Action timing
    action_config = timing_config.get('action', {})
    print("--- Action Timing ---")
    default_value = action_config.get('keyboard_switch_delay', 1.0)
    value = input(f"Keyboard switch delay (seconds) [{default_value}]: ").strip()
    keyboard_switch_delay = float(value) if value else default_value

    default_value = action_config.get('text_clear_delay', 1.0)
    value = input(f"Text clear delay (seconds) [{default_value}]: ").strip()
    text_clear_delay = float(value) if value else default_value

    default_value = action_config.get('text_input_delay', 1.0)
    value = input(f"Text input delay (seconds) [{default_value}]: ").strip()
    text_input_delay = float(value) if value else default_value

    default_value = action_config.get('keyboard_restore_delay', 1.0)
    value = input(f"Keyboard restore delay (seconds) [{default_value}]: ").strip()
    keyboard_restore_delay = float(value) if value else default_value

    config['timing'] = {
        'action': {
            'keyboard_switch_delay': keyboard_switch_delay,
            'text_clear_delay': text_clear_delay,
            'text_input_delay': text_input_delay,
            'keyboard_restore_delay': keyboard_restore_delay
        }
    }

    # Device timing
    device_config = timing_config.get('device', {})
    print()
    print("--- Device Timing ---")
    default_value = device_config.get('default_tap_delay', 1.0)
    value = input(f"Tap delay (seconds) [{default_value}]: ").strip()
    default_tap_delay = float(value) if value else default_value

    default_value = device_config.get('default_double_tap_delay', 1.0)
    value = input(f"Double tap delay (seconds) [{default_value}]: ").strip()
    default_double_tap_delay = float(value) if value else default_value

    default_value = device_config.get('double_tap_interval', 0.1)
    value = input(f"Double tap interval (seconds) [{default_value}]: ").strip()
    double_tap_interval = float(value) if value else default_value

    default_value = device_config.get('default_long_press_delay', 1.0)
    value = input(f"Long press delay (seconds) [{default_value}]: ").strip()
    default_long_press_delay = float(value) if value else default_value

    default_value = device_config.get('default_swipe_delay', 1.0)
    value = input(f"Swipe delay (seconds) [{default_value}]: ").strip()
    default_swipe_delay = float(value) if value else default_value

    default_value = device_config.get('default_back_delay', 1.0)
    value = input(f"Back delay (seconds) [{default_value}]: ").strip()
    default_back_delay = float(value) if value else default_value

    default_value = device_config.get('default_home_delay', 1.0)
    value = input(f"Home delay (seconds) [{default_value}]: ").strip()
    default_home_delay = float(value) if value else default_value

    default_value = device_config.get('default_launch_delay', 1.0)
    value = input(f"Launch delay (seconds) [{default_value}]: ").strip()
    default_launch_delay = float(value) if value else default_value

    config['timing']['device'] = {
        'default_tap_delay': default_tap_delay,
        'default_double_tap_delay': default_double_tap_delay,
        'double_tap_interval': double_tap_interval,
        'default_long_press_delay': default_long_press_delay,
        'default_swipe_delay': default_swipe_delay,
        'default_back_delay': default_back_delay,
        'default_home_delay': default_home_delay,
        'default_launch_delay': default_launch_delay
    }

    # Connection timing
    connection_config = timing_config.get('connection', {})
    print()
    print("--- Connection Timing ---")
    default_value = connection_config.get('adb_restart_delay', 2.0)
    value = input(f"ADB restart delay (seconds) [{default_value}]: ").strip()
    adb_restart_delay = float(value) if value else default_value

    default_value = connection_config.get('server_restart_delay', 1.0)
    value = input(f"Server restart delay (seconds) [{default_value}]: ").strip()
    server_restart_delay = float(value) if value else default_value

    config['timing']['connection'] = {
        'adb_restart_delay': adb_restart_delay,
        'server_restart_delay': server_restart_delay
    }

    print()
    print("✅ Timing configuration saved!")


def _apply_timing_config(timing_dict: dict, args) -> None:
    """Apply timing configuration from config file and command line args."""
    from phone_agent.config.timing import (
        ActionTimingConfig,
        DeviceTimingConfig,
        ConnectionTimingConfig,
        update_timing_config,
    )

    # Load from config file
    action = ActionTimingConfig.from_dict(timing_dict.get('action', {}))
    device = DeviceTimingConfig.from_dict(timing_dict.get('device', {}))
    connection = ConnectionTimingConfig.from_dict(timing_dict.get('connection', {}))

    # Override with command line args if provided
    if args.keyboard_switch_delay is not None:
        action.keyboard_switch_delay = args.keyboard_switch_delay
    if args.text_clear_delay is not None:
        action.text_clear_delay = args.text_clear_delay
    if args.text_input_delay is not None:
        action.text_input_delay = args.text_input_delay
    if args.keyboard_restore_delay is not None:
        action.keyboard_restore_delay = args.keyboard_restore_delay

    if args.tap_delay is not None:
        device.default_tap_delay = args.tap_delay
    if args.double_tap_delay is not None:
        device.default_double_tap_delay = args.double_tap_delay
    if args.double_tap_interval is not None:
        device.double_tap_interval = args.double_tap_interval
    if args.long_press_delay is not None:
        device.default_long_press_delay = args.long_press_delay
    if args.swipe_delay is not None:
        device.default_swipe_delay = args.swipe_delay
    if args.back_delay is not None:
        device.default_back_delay = args.back_delay
    if args.home_delay is not None:
        device.default_home_delay = args.home_delay
    if args.launch_delay is not None:
        device.default_launch_delay = args.launch_delay

    if args.adb_restart_delay is not None:
        connection.adb_restart_delay = args.adb_restart_delay
    if args.server_restart_delay is not None:
        connection.server_restart_delay = args.server_restart_delay

    # Update global timing config
    from phone_agent.config.timing import update_timing_config
    update_timing_config(action=action, device=device, connection=connection)


def _print_config_summary(config: dict):
    """Print configuration summary."""
    print()
    print("=" * 50)
    print("Configuration Summary")
    print("=" * 50)

    model = config.get('model', {})
    agent = config.get('agent', {})
    device = config.get('device', {})
    timing = config.get('timing', {})

    print(f"Model Type:      {model.get('type', 'unknown')}")
    print(f"Model Name:      {model.get('model_name', 'unknown')}")
    print(f"Base URL:        {model.get('base_url', 'unknown')}")
    if model.get('type') == 'local':
        print(f"Thinking:        {'Enabled' if model.get('use_thinking') else 'Disabled'}")
    print(f"Language:        {'中文 (Chinese)' if agent.get('lang') == 'cn' else 'English'}")
    print(f"Max Steps:       {agent.get('max_steps', 0) if agent.get('max_steps', 0) > 0 else 'Unlimited'}")
    print(f"Verbose Output:  {'Yes' if agent.get('verbose') else 'No'}")
    print(f"Auto-connect:    {'Yes' if device.get('auto_connect') else 'No'}")

    # Show timing summary if configured
    if timing:
        print()
        print("Timing Settings:")
        action = timing.get('action', {})
        device_timing = timing.get('device', {})
        connection = timing.get('connection', {})
        if action:
            print(f"  Action delays: keyboard={action.get('keyboard_switch_delay', 1.0)}s, "
                  f"text_input={action.get('text_input_delay', 1.0)}s")
        if device_timing:
            print(f"  Device delays: tap={device_timing.get('default_tap_delay', 1.0)}s, "
                  f"swipe={device_timing.get('default_swipe_delay', 1.0)}s")
        if connection:
            print(f"  Connection delays: adb_restart={connection.get('adb_restart_delay', 2.0)}s")

    print("=" * 50)
    print()
    print("You can now run the agent with:")
    print("  python main.py")
    print()


def main():
    """Main entry point."""
    args = parse_args()

    # Set device type globally based on args
    device_type = DeviceType.ADB

    # Set device type globally
    set_device_type(device_type)

    # Handle --config (interactive configuration wizard)
    if args.config:
        run_config_wizard()
        return

    # Handle --list-apps (no system check needed)
    if args.list_apps:
        print("Supported Android apps:")
        apps = list_supported_apps()

        for app in sorted(apps):
            print(f"  - {app}")

        return

    # Handle --batch mode
    if args.batch:
        run_batch_mode(args)
        return

    # Handle device commands (these may need partial system checks)
    if handle_device_commands(args):
        return

    # Run system requirements check before proceeding
    if not check_system_requirements(device_type, args):
        sys.exit(1)

    # Check model API connectivity and model availability
    if not check_model_api(args.base_url, args.model, args.apikey):
        sys.exit(1)

    # Load timing configuration from config file and apply command line overrides
    config = load_config()
    timing_dict = config.get('timing', {})
    _apply_timing_config(timing_dict, args)

    # Create configurations and agent based on device type
    # Load config from file for extra options
    model_config_dict = config.get('model', {})

    model_config = ModelConfig(
        base_url=args.base_url,
        model_name=args.model,
        api_key=args.apikey,
        lang=args.lang,
        use_thinking=model_config_dict.get('use_thinking', False),
    )

    # Create Android agent
    # Priority: --verbose > --quiet > config file
    verbose = args.verbose or (not args.quiet)
    agent_config = AgentConfig(
        max_steps=args.max_steps,
        device_id=args.device_id,
        verbose=verbose,
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

    # Close the console window
    close_console()


if __name__ == "__main__":
    main()
