"""用于 OpenAI 兼容 API 的 AI 推理模型客户端。"""

import json
import time
import httpx
from dataclasses import dataclass, field
from typing import Any, Dict

from openai import OpenAI, Stream
from openai.types.chat import ChatCompletionChunk

from phone_agent.config.i18n import get_message

# Try to import ollama SDK (optional, for enhanced thinking support)
try:
    import ollama
    OLLAMA_SDK_AVAILABLE = True
except ImportError:
    OLLAMA_SDK_AVAILABLE = False


@dataclass
class ModelConfig:
    """AI 模型的配置。"""

    base_url: str = "http://localhost:8000/v1"
    api_key: str = "EMPTY"
    model_name: str = "autoglm-phone-9b"
    max_tokens: int = 3000
    temperature: float = 0.0
    top_p: float = 0.85
    frequency_penalty: float = 0.2
    extra_body: Dict[str, Any] = field(default_factory=dict)
    lang: str = "cn"  # Language for UI messages: 'cn' or 'en'
    use_thinking: bool = False  # Whether to use model's built-in thinking feature (Ollama)


@dataclass
class ModelResponse:
    """来自 AI 模型的响应。"""

    thinking: str
    action: str
    raw_content: str
    # Performance metrics
    time_to_first_token: float | None = None  # Time to first token (seconds)
    time_to_thinking_end: float | None = None  # Time to thinking end (seconds)
    total_time: float | None = None  # Total inference time (seconds)


class ModelClient:
    """
    用于与 OpenAI 兼容的视觉语言模型交互的客户端。

    Args:
        config: 模型配置。
    """

    def __init__(self, config: ModelConfig | None = None):
        self.config = config or ModelConfig()

        # Determine if we should use Ollama thinking
        # Use thinking if explicitly enabled OR if using localhost/127.0.0.1
        self._use_ollama_thinking = (
            self.config.use_thinking or
            "localhost" in self.config.base_url or
            "127.0.0.1" in self.config.base_url
        )

        # Create HTTP client with SSL verification disabled for local development
        http_client = httpx.Client(verify=False)

        self.client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            http_client=http_client
        )

    def request(self, messages: list[dict[str, Any]]) -> ModelResponse:
        """
        向模型发送请求。

        Args:
            messages: OpenAI 格式的消息字典列表。

        Returns:
            包含思考和动作的 ModelResponse。

        Raises:
            ValueError: 如果响应无法解析。
        """
        # Start timing
        start_time = time.time()
        time_to_first_token = None
        time_to_thinking_end = None

        # Check if we should use Ollama native API for thinking feature
        if self._use_ollama_thinking:
            return self._request_with_thinking(messages, start_time)

        stream = self.client.chat.completions.create(
            messages=messages,
            model=self.config.model_name,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            frequency_penalty=self.config.frequency_penalty,
            extra_body=self.config.extra_body,  # type: ignore[arg-type]
            stream=True,
        )

        raw_content = ""
        reasoning_content = ""  # Store reasoning/thinking content for Qwen models
        buffer = ""  # Buffer to hold content that might be part of a marker
        action_markers = ["finish(message=", "do(action="]
        in_action_phase = False  # Track if we've entered the action phase
        first_token_received = False
        in_reasoning_phase = True  # Track if we're still in reasoning phase

        for chunk in stream:  # type: ignore[attr-defined]
            if len(chunk.choices) == 0:  # type: ignore[arg-type]
                continue

            choice = chunk.choices[0]  # type: ignore[attr-defined]

            # Handle reasoning_content (Qwen models thinking process)
            if hasattr(choice.delta, 'reasoning_content') and choice.delta.reasoning_content is not None:
                reasoning_part = choice.delta.reasoning_content  # type: ignore[union-attr]
                reasoning_content += reasoning_part

                # Record time to first token (reasoning counts as first token)
                if not first_token_received:
                    time_to_first_token = time.time() - start_time
                    first_token_received = True

                # Print reasoning content in real-time
                print(reasoning_part, end="", flush=True)

            # Handle regular content
            if choice.delta.content is not None:  # type: ignore[union-attr]
                content: str = choice.delta.content  # type: ignore[union-attr]
                raw_content += content

                # Record time to first token
                if not first_token_received:
                    time_to_first_token = time.time() - start_time
                    first_token_received = True

                # Transition from reasoning to content phase
                if in_reasoning_phase and reasoning_content:
                    print()  # Newline after reasoning
                    in_reasoning_phase = False
                    # Record time to thinking end
                    if time_to_thinking_end is None:
                        time_to_thinking_end = time.time() - start_time

                if in_action_phase:
                    # Already in action phase, just accumulate content without printing
                    continue

                buffer += content

                # Check if any marker is fully present in buffer
                marker_found = False
                for marker in action_markers:
                    if marker in buffer:
                        # Marker found, print everything before it
                        thinking_part = buffer.split(marker, 1)[0]
                        # Clean up thinking part (remove XML tags if present)
                        thinking_part = thinking_part.replace("<think>", "").replace("</think>", "").strip()
                        if thinking_part:
                            print(thinking_part, end="", flush=True)
                            print()  # Print newline after thinking is complete
                        in_action_phase = True
                        marker_found = True

                        # Record time to thinking end
                        if time_to_thinking_end is None:
                            time_to_thinking_end = time.time() - start_time

                        break

                if marker_found:
                    continue  # Continue to collect remaining content

                # Check if buffer contains XML closing tag (legacy format)
                if "</think>" in buffer and "<answer>" in buffer:
                    # Legacy XML format: <think>...</think><answer>...
                    thinking_end_idx = buffer.find("</think>")
                    answer_start_idx = buffer.find("<answer>")
                    thinking_part = buffer[:thinking_end_idx].replace("<think>", "").strip()
                    if thinking_part:
                        print(thinking_part, end="", flush=True)
                        print()
                    in_action_phase = True

                    if time_to_thinking_end is None:
                        time_to_thinking_end = time.time() - start_time
                    continue

                # Check if buffer ends with a prefix of any marker
                # If so, don't print yet (wait for more content)
                is_potential_marker = False
                for marker in action_markers:
                    for i in range(1, len(marker)):
                        if buffer.endswith(marker[:i]):
                            is_potential_marker = True
                            break
                    if is_potential_marker:
                        break

                if not is_potential_marker:
                    # Safe to print the buffer
                    print(buffer, end="", flush=True)
                    buffer = ""

        # Calculate total time
        total_time = time.time() - start_time

        # Use reasoning_content as thinking if available, otherwise parse from raw_content
        if reasoning_content:
            thinking = reasoning_content
            _, action = self._parse_response(raw_content)
        else:
            # Parse thinking and action from response
            thinking, action = self._parse_response(raw_content)

        # Print performance metrics
        lang = self.config.lang
        print()
        print("=" * 50)
        print(f"⏱️  {get_message('performance_metrics', lang)}:")
        print("-" * 50)
        if time_to_first_token is not None:
            print(
                f"{get_message('time_to_first_token', lang)}: {time_to_first_token:.3f}s"
            )
        if time_to_thinking_end is not None:
            print(
                f"{get_message('time_to_thinking_end', lang)}:        {time_to_thinking_end:.3f}s"
            )
        print(
            f"{get_message('total_inference_time', lang)}:          {total_time:.3f}s"
        )
        print("=" * 50)

        return ModelResponse(
            thinking=thinking,
            action=action,
            raw_content=raw_content,
            time_to_first_token=time_to_first_token,
            time_to_thinking_end=time_to_thinking_end,
            total_time=total_time,
        )

    def _request_with_thinking(self, messages: list[dict[str, Any]], start_time: float) -> ModelResponse:
        """
        Request using Ollama SDK with thinking support.
        This supports both text-only and multimodal (image + text) messages.

        Args:
            messages: Message list
            start_time: Request start time

        Returns:
            ModelResponse with thinking and action
        """
        # Always use Ollama SDK with think=True for thinking support
        return self._request_with_fallback(messages, start_time)

    def _request_with_fallback(self, messages: list[dict[str, Any]], start_time: float) -> ModelResponse:
        """
        Request using Ollama SDK with thinking support (for images and text).
        Falls back to OpenAI-compatible API if Ollama SDK is not available.

        Args:
            messages: Message list (OpenAI format)
            start_time: Request start time

        Returns:
            ModelResponse with thinking and action
        """
        # Try Ollama SDK first (supports thinking with images)
        if OLLAMA_SDK_AVAILABLE:
            try:
                # Initialize Ollama client with the same host as OpenAI client
                ollama_client = ollama.Client(host=self.config.base_url.replace('/v1', ''))

                # Convert OpenAI format to Ollama format
                ollama_messages = []
                for msg in messages:
                    ollama_msg = {'role': msg['role']}
                    content = msg.get('content', '')
                    if isinstance(content, list):
                        # Handle multimodal content
                        text_parts = []
                        images = []
                        for item in content:
                            if item.get('type') == 'text':
                                text_parts.append(item.get('text', ''))
                            elif item.get('type') == 'image_url':
                                img_url = item.get('image_url', {}).get('url', '')
                                if img_url.startswith('data:'):
                                    # Extract base64 from data URL
                                    img_data = img_url.split(',', 1)[1]
                                    images.append(img_data)
                        ollama_msg['content'] = ' '.join(text_parts)
                        if images:
                            ollama_msg['images'] = images
                    else:
                        ollama_msg['content'] = content
                    ollama_messages.append(ollama_msg)

                # Call Ollama SDK with thinking enabled (streaming)
                stream = ollama_client.chat(
                    model=self.config.model_name,
                    messages=ollama_messages,
                    think=True,  # Enable thinking feature
                    stream=True,
                    options={
                        'temperature': self.config.temperature,
                        'top_p': self.config.top_p,
                    }
                )

                # Process streaming response
                thinking = ""
                content = ""
                in_thinking = False
                thinking_complete = False
                time_to_thinking_end = None

                for chunk in stream:
                    if hasattr(chunk.message, 'thinking') and chunk.message.thinking:
                        if not in_thinking:
                            in_thinking = True
                            print("Thinking:")
                        print(chunk.message.thinking, end='', flush=True)
                        thinking += chunk.message.thinking
                    elif hasattr(chunk.message, 'content') and chunk.message.content:
                        if in_thinking and not thinking_complete:
                            print("\n")
                            thinking_complete = True
                            time_to_thinking_end = time.time() - start_time
                        print(chunk.message.content, end='', flush=True)
                        content += chunk.message.content

                print()  # Newline after streaming complete
                total_time = time.time() - start_time

                # Parse action from content
                _, action = self._parse_response(content)

                # Print performance metrics
                print()
                print("=" * 50)
                print("Performance metrics:")
                print("-" * 50)
                if time_to_thinking_end:
                    print(f"Thinking time: {time_to_thinking_end:.3f}s")
                print(f"Total inference time: {total_time:.3f}s")
                print("=" * 50)

                return ModelResponse(
                    thinking=thinking,
                    action=action,
                    raw_content=content,
                    time_to_first_token=None,
                    time_to_thinking_end=time_to_thinking_end,
                    total_time=total_time,
                )
            except Exception as e:
                print(f"Ollama SDK failed: {e}, falling back to OpenAI API...")

        # Fallback to OpenAI-compatible API (non-streaming)
        try:
            response = self.client.chat.completions.create(
                messages=messages,
                model=self.config.model_name,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                frequency_penalty=self.config.frequency_penalty,
                extra_body=self.config.extra_body,
                stream=False,
            )

            total_time = time.time() - start_time

            # Extract content and reasoning/thinking from response
            choice = response.choices[0]
            message = choice.message

            # Try multiple fields for thinking/reasoning (Qwen uses 'reasoning_content', Ollama uses 'reasoning')
            thinking = (
                getattr(message, 'reasoning_content', None) or  # Qwen models
                getattr(message, 'reasoning', None) or  # Ollama models
                getattr(message, 'thinking', None) or  # Other models
                ''
            )
            content = message.content or ''

            # If no reasoning field, try to parse from content
            if not thinking:
                thinking, content = self._parse_response(content)

            time_to_thinking_end = time.time() - start_time if thinking else None

            # Parse action from content
            _, action = self._parse_response(content)

            # Print thinking if available
            if thinking:
                print(thinking, flush=True)
                print()

            # Print performance metrics
            print()
            print("=" * 50)
            print("Performance metrics:")
            print("-" * 50)
            if time_to_thinking_end:
                print(f"Thinking time: {time_to_thinking_end:.3f}s")
            print(f"Total inference time: {total_time:.3f}s")
            print("=" * 50)

            return ModelResponse(
                thinking=thinking,
                action=action,
                raw_content=content,
                time_to_first_token=None,
                time_to_thinking_end=time_to_thinking_end,
                total_time=total_time,
            )
        except Exception as e:
            # Final fallback to streaming
            print(f"OpenAI API failed: {e}, using streaming...")
            return self._request_with_streaming(messages, start_time)

    def _request_with_streaming(self, messages: list[dict[str, Any]], start_time: float) -> ModelResponse:
        """
        Original streaming implementation (without reasoning/thinking extraction).

        Args:
            messages: Message list
            start_time: Request start time

        Returns:
            ModelResponse with thinking and action
        """
        stream = self.client.chat.completions.create(
            messages=messages,
            model=self.config.model_name,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            frequency_penalty=self.config.frequency_penalty,
            extra_body=self.config.extra_body,
            stream=True,
        )

        raw_content = ""
        reasoning_content = ""  # Store reasoning/thinking content for Qwen models
        buffer = ""
        action_markers = ["finish(message=", "do(action="]
        in_action_phase = False
        first_token_received = False
        time_to_first_token = None
        time_to_thinking_end = None
        in_reasoning_phase = True  # Track if we're still in reasoning phase

        for chunk in stream:
            if len(chunk.choices) == 0:
                continue

            choice = chunk.choices[0]

            # Handle reasoning_content (Qwen models thinking process)
            if hasattr(choice.delta, 'reasoning_content') and choice.delta.reasoning_content is not None:
                reasoning_part = choice.delta.reasoning_content
                reasoning_content += reasoning_part

                # Record time to first token
                if not first_token_received:
                    time_to_first_token = time.time() - start_time
                    first_token_received = True

                # Print reasoning content in real-time
                print(reasoning_part, end="", flush=True)

            # Handle regular content
            if choice.delta.content is not None:
                content = choice.delta.content
                raw_content += content

                if not first_token_received:
                    time_to_first_token = time.time() - start_time
                    first_token_received = True

                # Transition from reasoning to content phase
                if in_reasoning_phase and reasoning_content:
                    print()  # Newline after reasoning
                    in_reasoning_phase = False
                    if time_to_thinking_end is None:
                        time_to_thinking_end = time.time() - start_time

                if in_action_phase:
                    continue

                buffer += content

                marker_found = False
                for marker in action_markers:
                    if marker in buffer:
                        thinking_part = buffer.split(marker, 1)[0]
                        thinking_part = self._clean_thinking(thinking_part)
                        if thinking_part:
                            print(thinking_part, end="", flush=True)
                            print()
                        in_action_phase = True
                        marker_found = True
                        if time_to_thinking_end is None:
                            time_to_thinking_end = time.time() - start_time
                        break

                if marker_found:
                    continue

                if "</think>" in buffer and "<answer>" in buffer:
                    thinking_end_idx = buffer.find("</think>")
                    thinking_part = buffer[:thinking_end_idx].replace("<think>", "").strip()
                    if thinking_part:
                        print(thinking_part, end="", flush=True)
                        print()
                    in_action_phase = True
                    if time_to_thinking_end is None:
                        time_to_thinking_end = time.time() - start_time
                    continue

                is_potential_marker = False
                for marker in action_markers:
                    for i in range(1, len(marker)):
                        if buffer.endswith(marker[:i]):
                            is_potential_marker = True
                            break
                    if is_potential_marker:
                        break

                if not is_potential_marker:
                    print(buffer, end="", flush=True)
                    buffer = ""

        total_time = time.time() - start_time

        # Use reasoning_content as thinking if available, otherwise parse from raw_content
        if reasoning_content:
            thinking = reasoning_content
            _, action = self._parse_response(raw_content)
        else:
            thinking, action = self._parse_response(raw_content)

        print()
        print("=" * 50)
        print("Performance metrics:")
        print("-" * 50)
        if time_to_first_token:
            print(f"Time to first token: {time_to_first_token:.3f}s")
        if time_to_thinking_end:
            print(f"Thinking time: {time_to_thinking_end:.3f}s")
        print(f"Total inference time: {total_time:.3f}s")
        print("=" * 50)

        return ModelResponse(
            thinking=thinking,
            action=action,
            raw_content=raw_content,
            time_to_first_token=time_to_first_token,
            time_to_thinking_end=time_to_thinking_end,
            total_time=total_time,
        )

    def _parse_response(self, content: str) -> tuple[str, str]:
        """
        将模型响应解析为思考和动作部分。

        解析规则（按优先级）：
        1. XML 标签格式：<think>...</think><answer>...</answer>（最高优先级）
        2. finish(message= 格式
        3. do(action= 格式
        4. 简化格式：...</think> action
        5. 无标记：全部作为动作

        Args:
            content: 原始响应内容。

        Returns:
            (思考，动作) 元组。
        """
        # Rule 1: XML tag parsing (highest priority)
        if "<answer>" in content:
            parts = content.split("<answer>", 1)
            thinking = self._clean_thinking(parts[0])
            action = parts[1].replace("</answer>", "").strip()
            return thinking, action

        # Rule 2: Check for finish(message=
        if "finish(message=" in content:
            parts = content.split("finish(message=", 1)
            thinking = self._clean_thinking(parts[0].strip())
            action = "finish(message=" + parts[1]
            action = self._clean_action(action)
            return thinking, action

        # Rule 3: Check for do(action=
        if "do(action=" in content:
            parts = content.split("do(action=", 1)
            thinking = self._clean_thinking(parts[0].strip())
            action = "do(action=" + parts[1]
            action = self._clean_action(action)
            return thinking, action

        # Rule 4: Simplified format ...</think> action
        if "</think>" in content:
            parts = content.split("</think>", 1)
            thinking = self._clean_thinking(parts[0])
            action = parts[1].strip()
            return thinking, action

        # Rule 5: No markers found, return content as action
        return "", content

    def _clean_thinking(self, thinking: str) -> str:
        """
        清理思考内容，移除 XML 标签和其他标记。

        Args:
            thinking: 原始思考内容。

        Returns:
            清理后的思考内容。
        """
        thinking = thinking.replace("<think>", "").replace("</think>", "")
        thinking = thinking.replace("{think}", "").replace("</think>", "")
        thinking = thinking.replace("<answer>", "").replace("</answer>", "")
        return thinking.strip()
    
    def _clean_action(self, action: str) -> str:
        """
        通过移除 XML 标签和其他伪影来清理动作字符串。
        
        Args:
            action: 原始动作字符串。
            
        Returns:
            清理后的动作字符串。
        """
        # Remove </answer> tag if present
        action = action.replace("</answer>", "")
        
        # Remove any trailing whitespace
        action = action.strip()
        
        # If action ends with ) and has proper structure, keep it
        # But remove any content after the closing parenthesis
        if action.startswith("do("):
            # Find the last closing parenthesis
            last_paren = action.rfind(")")
            if last_paren != -1:
                action = action[:last_paren + 1]
        elif action.startswith("finish("):
            # Find the last closing parenthesis
            last_paren = action.rfind(")")
            if last_paren != -1:
                action = action[:last_paren + 1]
        
        return action


class MessageBuilder:
    """用于构建对话消息的辅助类。"""

    @staticmethod
    def create_system_message(content: str) -> dict[str, Any]:
        """创建系统消息。"""
        return {"role": "system", "content": content}

    @staticmethod
    def create_user_message(
        text: str, image_base64: str | None = None
    ) -> dict[str, Any]:
        """
        创建带有可选图片的用户消息。

        Args:
            text: 文本内容。
            image_base64: 可选的 base64 编码图片。

        Returns:
            消息字典。
        """
        content = []

        if image_base64:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                }
            )

        content.append({"type": "text", "text": text})

        return {"role": "user", "content": content}

    @staticmethod
    def create_assistant_message(content: str) -> dict[str, Any]:
        """创建助手消息。"""
        return {"role": "assistant", "content": content}

    @staticmethod
    def remove_images_from_message(message: dict[str, Any]) -> dict[str, Any]:
        """
        从消息中移除图片内容以节省上下文空间。

        Args:
            message: 消息字典。

        Returns:
            移除了图片的消息。
        """
        if isinstance(message.get("content"), list):
            message["content"] = [
                item for item in message["content"] if item.get("type") == "text"
            ]
        return message

    @staticmethod
    def build_screen_info(current_app: str, **extra_info) -> str:  # type: ignore[no-untyped-def]
        """
        为模型构建屏幕信息字符串。

        Args:
            current_app: 当前应用名称。
            **extra_info: 要包含的额外信息。

        Returns:
            包含屏幕信息的 JSON 字符串。
        """
        info = {"current_app": current_app, **extra_info}
        return json.dumps(info, ensure_ascii=False)
