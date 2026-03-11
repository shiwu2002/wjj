"""Phone Agent UI 消息的国际化和多语言支持模块。"""

# 中文消息
MESSAGES_ZH = {
    "thinking": "思考过程",
    "action": "执行动作",
    "task_completed": "任务完成",
    "done": "完成",
    "starting_task": "开始执行任务",
    "final_result": "最终结果",
    "task_result": "任务结果",
    "confirmation_required": "需要确认",
    "continue_prompt": "是否继续？(y/n)",
    "manual_operation_required": "需要人工操作",
    "manual_operation_hint": "请手动完成操作...",
    "press_enter_when_done": "完成后按回车继续",
    "connection_failed": "连接失败",
    "connection_successful": "连接成功",
    "step": "步骤",
    "task": "任务",
    "result": "结果",
    "performance_metrics": "性能指标",
    "time_to_first_token": "首 Token 延迟 (TTFT)",
    "time_to_thinking_end": "思考完成延迟",
    "total_inference_time": "总推理时间",
}



def get_messages(lang: str = "cn") -> dict:
    """
    Returns:
        UI 消息字典。
    """
    if lang == "en":
        return MESSAGES_EN
    return MESSAGES_ZH


def get_message(key: str, lang: str = "cn") -> str:
    """
    根据键和语言获取单个 UI 消息。

    Args:
        key: 消息键。
        lang: 语言代码，'cn' 表示中文。

    Returns:
        消息字符串。
    """
    messages = get_messages(lang)
    return messages.get(key, key)
