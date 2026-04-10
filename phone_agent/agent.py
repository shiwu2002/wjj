"""用于编排手机自动化的主 PhoneAgent 类。"""

import json
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from phone_agent.actions import ActionHandler
from phone_agent.actions.handler import finish, parse_action
from phone_agent.config import get_system_prompt
from phone_agent.config.i18n import get_messages
from phone_agent.device_factory import get_device_factory
from phone_agent.history import get_history_manager
from phone_agent.model import ModelClient, ModelConfig
from phone_agent.model.client import MessageBuilder
from phone_agent.utils.logger import setup_logger

# 初始化 logger
logger = setup_logger(__name__)


@dataclass
class AgentConfig:
    """PhoneAgent 的配置。"""

    max_steps: int = 100
    device_id: str | None = None
    lang: str = "cn"
    system_prompt: str | None = None
    verbose: bool = True

    def __post_init__(self):
        if self.system_prompt is None:
            self.system_prompt = get_system_prompt(self.lang)


@dataclass
class StepResult:
    """代理单步执行的结果。"""

    success: bool
    finished: bool
    action: dict[str, Any] | None
    thinking: str
    message: str | None = None


class PhoneAgent:
    """
    用于自动化 Android 手机交互的 AI 驱动代理。

    该代理使用视觉语言模型来理解屏幕内容
    并决定完成用户任务的操作。

    Args:
        model_config: AI 模型的配置。
        agent_config: 代理行为的配置。
        confirmation_callback: 用于敏感操作确认的可选回调。
        takeover_callback: 用于接管请求的可选回调。

    Example:
        >>> from phone_agent import PhoneAgent
        >>> from phone_agent.model import ModelConfig
        >>>
        >>> model_config = ModelConfig(base_url="http://localhost:8000/v1")
        >>> agent = PhoneAgent(model_config)
        >>> agent.run("打开微信并给 John 发送消息")
    """

    def __init__(
        self,
        model_config: ModelConfig | None = None,
        agent_config: AgentConfig | None = None,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
    ):
        self.model_config = model_config or ModelConfig()
        self.agent_config = agent_config or AgentConfig()

        self.model_client = ModelClient(self.model_config)
        self.action_handler = ActionHandler(
            device_id=self.agent_config.device_id,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
        )

        self._context: list[dict[str, Any]] = []
        self._step_count = 0
        self._max_context_rounds = 5  # 只保留最近 5 轮对话

    def run(self, task: str) -> str:
        """
        运行代理以完成任务。

        Args:
            task: 任务的自然语言描述。

        Returns:
            来自代理的最终消息。
        """
        self._context = []
        self._step_count = 0
        
        # 记录开始时间
        start_time = datetime.now()

        # First step with user prompt
        result = self._execute_step(task, is_first=True)

        if result.finished:
            end_time = datetime.now()
            self._save_history(task, result, start_time, end_time)
            return result.message or "Task completed"

        # Continue until finished or max steps reached
        # max_steps <= 0 means unlimited
        while self.agent_config.max_steps <= 0 or self._step_count < self.agent_config.max_steps:
            result = self._execute_step(is_first=False)

            if result.finished:
                end_time = datetime.now()
                self._save_history(task, result, start_time, end_time)
                return result.message or "Task completed"

        # Max steps reached
        end_time = datetime.now()
        self._save_history(
            task,
            result,
            start_time,
            end_time,
            error_message="Max steps reached"
        )
        return "Max steps reached"

    def step(self, task: str | None = None) -> StepResult:
        """
        执行代理的单步操作。

        适用于手动控制或调试。

        Args:
            task: 任务描述（仅第一步需要）。

        Returns:
            包含步骤详情的 StepResult。
        """
        is_first = len(self._context) == 0

        if is_first and not task:
            raise ValueError("Task is required for the first step")

        return self._execute_step(task, is_first)

    def reset(self) -> None:
        """重置代理状态以开始新任务。"""
        self._context = []
        self._step_count = 0

    def _trim_context(self) -> None:
        """修剪上下文，只保留 system prompt 和最近 N 轮对话。"""
        if len(self._context) <= 1:
            return  # 只有 system prompt 或更少，不需要修剪

        # 保留 system prompt（第一个）和最近 N 轮对话（每轮包含 user + assistant 两条消息）
        # 上下文结构：[system, user1, assistant1, user2, assistant2, ...]
        max_messages = 1 + (self._max_context_rounds * 2)  # 1 system + 5*2 = 11

        if len(self._context) > max_messages:
            # 保留 system prompt 和最近的消息
            self._context = [self._context[0]] + self._context[-(max_messages - 1):]
            logger.info(f"Context trimmed to {len(self._context)} messages (keeping last {self._max_context_rounds} rounds)")

    def _execute_step(
        self, user_prompt: str | None = None, is_first: bool = False
    ) -> StepResult:
        """执行代理循环的单步操作。"""
        self._step_count += 1

        # Capture current screen state
        device_factory = get_device_factory()
        screenshot = device_factory.get_screenshot(self.agent_config.device_id, enable_compression=True)
        current_app = device_factory.get_current_app(self.agent_config.device_id)

        # Build messages
        if is_first:
            # system_prompt 在 __post_init__ 中已确保不为 None
            assert self.agent_config.system_prompt is not None
            self._context.append(
                MessageBuilder.create_system_message(self.agent_config.system_prompt)
            )

            screen_info = MessageBuilder.build_screen_info(current_app)  # type: ignore[misc]
            text_content = f"{user_prompt}\n\n{screen_info}"

            self._context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=screenshot.base64_data
                )
            )
        else:
            screen_info = MessageBuilder.build_screen_info(current_app)  # type: ignore[misc]
            text_content = f"** Screen Info **\n\n{screen_info}"

            self._context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=screenshot.base64_data
                )
            )

        # Get model response
        try:
            msgs = get_messages(self.agent_config.lang)
            logger.info("=" * 50)
            logger.info(f"💭 {msgs['thinking']}:")
            logger.info("-" * 50)
            response = self.model_client.request(self._context)

            # Log thinking process if available
            if response.thinking and self.agent_config.verbose:
                logger.info(response.thinking)
        except Exception as e:
            logger.error(f"Model request failed: {e}", exc_info=True)
            # Remove the user message we just added to avoid duplicate requests on retry
            if not is_first:
                self._context.pop()
            return StepResult(
                success=False,
                finished=True,
                action=None,
                thinking="",
                message=f"Model error: {e}",
            )

        # Parse action from response
        try:
            action = parse_action(response.action)
        except ValueError:
            if self.agent_config.verbose:
                traceback.print_exc()
            action = finish(message=response.action)

        if self.agent_config.verbose:
            # Print thinking process
            logger.info("-" * 50)
            logger.info(f"🎯 {msgs['action']}:")
            logger.info(json.dumps(action, ensure_ascii=False, indent=2))
            logger.info("=" * 50 + "\n")

        # Remove image from context to save space
        self._context[-1] = MessageBuilder.remove_images_from_message(self._context[-1])

        # Execute action
        try:
            result = self.action_handler.execute(
                action, screenshot
            )
        except Exception as e:
            logger.error(f"Action request failed: {e}", exc_info=True)
            result = self.action_handler.execute(
                finish(message=str(e)), screenshot
            )

        # Add assistant response to context
        self._context.append(
            MessageBuilder.create_assistant_message(
                f"<think>{response.thinking}</think><answer>{response.action}</answer>"
            )
        )

        # Trim context to keep only recent rounds
        self._trim_context()

        # Check if finished
        finished = action.get("_metadata") == "finish" or result.should_finish

        if finished and self.agent_config.verbose:
            msgs = get_messages(self.agent_config.lang)
            logger.info("\n" + "🎉 " + "=" * 48)
            logger.info(
                f"✅ {msgs['task_completed']}: {result.message or action.get('message', msgs['done'])}"
            )
            logger.info("=" * 50 + "\n")

        return StepResult(
            success=result.success,
            finished=finished,
            action=action,
            thinking=response.thinking,
            message=result.message or action.get("message"),
        )

    @property
    def context(self) -> list[dict[str, Any]]:
        """获取当前对话上下文。"""
        return self._context.copy()

    @property
    def step_count(self) -> int:
        """获取当前步数。"""
        return self._step_count
    
    def _save_history(
        self,
        task: str,
        result: StepResult,
        start_time: datetime,
        end_time: datetime,
        error_message: str | None = None
    ) -> None:
        """
        保存任务执行历史。
        
        Args:
            task: 任务描述
            result: 执行结果
            start_time: 开始时间
            end_time: 结束时间
            error_message: 错误消息（可选）
        """
        try:
            history_mgr = get_history_manager()
            device_factory = get_device_factory()
            devices = device_factory.list_devices()
            device_id = devices[0].device_id if devices else None
            
            history_mgr.add_record(
                task=task,
                result=result.message or ("Success" if result.success else "Failed"),
                steps=self._step_count,
                success=result.success and not error_message,
                start_time=start_time,
                end_time=end_time,
                device_id=device_id,
                model_name=self.model_config.model_name,
                error_message=error_message or (None if result.success else result.message)
            )
            logger.info(f"Task history saved: {task[:50]}...")
        except Exception as e:
            logger.error(f"Failed to save task history: {e}")
