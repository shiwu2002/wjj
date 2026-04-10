"""批量问题执行器 - 从 Excel/TXT 读取问题并批量执行。"""

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.device_factory import get_device_factory
from phone_agent.model import ModelConfig
from phone_agent.utils.logger import setup_logger

logger = setup_logger(__name__)

# Try to import pandas for Excel support
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    logger.warning("pandas not installed. Excel support will be limited.")


@dataclass
class BatchResult:
    """单个问题的执行结果。"""
    question: str
    answer: str
    screenshot_path: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    steps: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """转换为字典。"""
        return {
            "question": self.question,
            "answer": self.answer,
            "screenshot_path": self.screenshot_path or "",
            "success": self.success,
            "error_message": self.error_message or "",
            "steps": self.steps,
            "start_time": self.start_time.isoformat() if self.start_time else "",
            "end_time": self.end_time.isoformat() if self.end_time else "",
            **self.metadata
        }


@dataclass
class BatchConfig:
    """批量执行的配置。"""
    # 文件相关
    question_column: str = "问题"  # Excel 中问题所在的列名
    answer_column: str = "答案"  # 答案列名
    screenshot_column: str = "截图路径"  # 截图路径列名
    status_column: str = "状态"  # 状态列名

    # 执行相关
    max_questions: int = 0  # 最大执行问题数，0 表示全部
    skip_existing: bool = True  # 跳过已有答案的问题
    continue_on_error: bool = True  # 出错时继续执行下一个

    # 截图相关
    save_screenshot: bool = True  # 是否保存截图
    screenshot_dir: str = "./batch_screenshots"  # 截图保存目录

    # 进度保存
    save_progress: bool = True  # 是否保存进度
    progress_interval: int = 1  # 每执行几个问题保存一次进度

    # Agent 相关
    max_steps: int = 50  # 每个问题的最大步数
    verbose: bool = False  # 是否显示详细输出


class BatchQuestionRunner:
    """
    批量问题执行器。

    从 Excel 或 TXT 文件读取问题列表，逐个使用 PhoneAgent 执行，
    并将结果和截图保存回 Excel 文件。

    Example:
        >>> runner = BatchQuestionRunner()
        >>> runner.load_questions("questions.xlsx")
        >>> results = runner.run_batch()
        >>> runner.export_results("results.xlsx")
    """

    def __init__(
        self,
        model_config: Optional[ModelConfig] = None,
        batch_config: Optional[BatchConfig] = None,
    ):
        """
        初始化批量执行器。

        Args:
            model_config: 模型配置
            batch_config: 批量执行配置
        """
        self.model_config = model_config or ModelConfig()
        self.batch_config = batch_config or BatchConfig()

        self.questions: list[str] = []
        self.results: list[BatchResult] = []
        self.progress_file: Optional[str] = None

        # 创建截图保存目录
        if self.batch_config.save_screenshot:
            os.makedirs(self.batch_config.screenshot_dir, exist_ok=True)

    def load_questions(
        self,
        file_path: str,
        column: Optional[str] = None,
    ) -> list[str]:
        """
        从文件加载问题列表。

        Args:
            file_path: 文件路径（支持 .xlsx, .xls, .txt）
            column: 问题所在的列名（Excel 文件需要）

        Returns:
            问题列表

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件格式不支持或列名无效
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        column = column or self.batch_config.question_column

        if path.suffix.lower() in [".xlsx", ".xls"]:
            self.questions = self._load_from_excel(path, column)
        elif path.suffix.lower() == ".txt":
            self.questions = self._load_from_txt(path)
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}")

        logger.info(f"Loaded {len(self.questions)} questions from {file_path}")
        return self.questions

    def _load_from_excel(self, path: Path, column: str) -> list[str]:
        """从 Excel 文件加载问题。"""
        if not PANDAS_AVAILABLE:
            raise ImportError(
                "pandas is required for Excel support. "
                "Install with: pip install pandas openpyxl"
            )

        df = pd.read_excel(path)

        if column not in df.columns:
            raise ValueError(
                f"Column '{column}' not found. Available columns: {list(df.columns)}"
            )

        # 过滤空值
        questions = df[column].dropna().astype(str).tolist()
        return [q.strip() for q in questions if q.strip() and q.strip() != "nan"]

    def _load_from_txt(self, path: Path) -> list[str]:
        """从 TXT 文件加载问题（每行一个）。"""
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        questions = [line.strip() for line in lines if line.strip()]
        return questions

    def load_existing_results(
        self,
        file_path: str,
    ) -> dict[str, BatchResult]:
        """
        从现有的 Excel 文件加载已有结果（用于断点续跑）。

        Args:
            file_path: Excel 文件路径

        Returns:
            已有问题到结果的映射
        """
        if not PANDAS_AVAILABLE:
            return {}

        path = Path(file_path)
        if not path.exists():
            return {}

        try:
            df = pd.read_excel(path)
            results = {}

            question_col = self.batch_config.question_column
            answer_col = self.batch_config.answer_column
            status_col = self.batch_config.status_column
            screenshot_col = self.batch_config.screenshot_column

            for _, row in df.iterrows():
                question = str(row.get(question_col, "")).strip()
                if not question or question == "nan":
                    continue

                status = str(row.get(status_col, "")).strip() if status_col in df.columns else ""
                answer = str(row.get(answer_col, "")).strip() if answer_col in df.columns else ""
                screenshot = str(row.get(screenshot_col, "")).strip() if screenshot_col in df.columns else ""

                # 如果已有答案或状态为成功，则认为是已完成的
                if status == "成功" or (answer and answer != "nan"):
                    results[question] = BatchResult(
                        question=question,
                        answer=answer if answer != "nan" else "",
                        screenshot_path=screenshot if screenshot != "nan" else None,
                        success=(status == "成功"),
                        error_message="" if status == "成功" else status,
                    )

            return results
        except Exception as e:
            logger.warning(f"Failed to load existing results: {e}")
            return {}

    def run_batch(
        self,
        questions: Optional[list[str]] = None,
        agent_config: Optional[AgentConfig] = None,
        confirmation_callback: Optional[Callable[[str], bool]] = None,
    ) -> list[BatchResult]:
        """
        批量执行问题。

        Args:
            questions: 问题列表，如果为 None 则使用已加载的问题
            agent_config: Agent 配置
            confirmation_callback: 确认回调

        Returns:
            结果列表
        """
        if questions is None:
            questions = self.questions

        if not questions:
            raise ValueError("No questions to process")

        # 限制问题数量
        max_q = self.batch_config.max_questions
        if max_q > 0:
            questions = questions[:max_q]

        logger.info(f"Starting batch execution of {len(questions)} questions")

        self.results = []
        completed = 0
        failed = 0

        for i, question in enumerate(questions, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"Question {i}/{len(questions)}: {question[:50]}...")
            logger.info(f"{'='*60}")

            try:
                result = self._run_single_question(
                    question, agent_config, confirmation_callback
                )
                self.results.append(result)

                if result.success:
                    completed += 1
                else:
                    failed += 1

            except Exception as e:
                logger.error(f"Question failed with error: {e}")
                failed += 1

                if not self.batch_config.continue_on_error:
                    raise

                # 记录失败
                self.results.append(BatchResult(
                    question=question,
                    answer="",
                    success=False,
                    error_message=str(e),
                ))

            # 保存进度
            if self.batch_config.save_progress and i % self.batch_config.progress_interval == 0:
                self._save_progress()

            logger.info(f"Progress: {completed} completed, {failed} failed")

        logger.info(f"\nBatch execution finished: {completed} completed, {failed} failed")
        return self.results

    def _run_single_question(
        self,
        question: str,
        agent_config: Optional[AgentConfig] = None,
        confirmation_callback: Optional[Callable[[str], bool]] = None,
    ) -> BatchResult:
        """
        执行单个问题。

        Args:
            question: 问题
            agent_config: Agent 配置
            confirmation_callback: 确认回调

        Returns:
            执行结果
        """
        start_time = datetime.now()

        # 创建新的 Agent 实例（确保上下文隔离）
        agent = PhoneAgent(
            model_config=self.model_config,
            agent_config=agent_config or AgentConfig(
                max_steps=self.batch_config.max_steps,
                verbose=self.batch_config.verbose,
            ),
            confirmation_callback=confirmation_callback,
        )

        try:
            # 执行任务
            answer = agent.run(question)

            # 获取截图
            screenshot_path = None
            if self.batch_config.save_screenshot:
                screenshot_path = self._save_screenshot(question)

            end_time = datetime.now()

            return BatchResult(
                question=question,
                answer=answer,
                screenshot_path=screenshot_path,
                success=True,
                steps=agent.step_count,
                start_time=start_time,
                end_time=end_time,
            )

        except Exception as e:
            logger.error(f"Question execution failed: {e}", exc_info=True)
            end_time = datetime.now()

            return BatchResult(
                question=question,
                answer="",
                success=False,
                error_message=str(e),
                start_time=start_time,
                end_time=end_time,
            )

    def _save_screenshot(self, question: str) -> str:
        """
        保存当前屏幕截图。

        Args:
            question: 问题（用于生成文件名）

        Returns:
            截图文件路径
        """
        try:
            device_factory = get_device_factory()
            screenshot = device_factory.get_screenshot(enable_compression=False)

            # 生成文件名（使用时间戳和问题摘要）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            question_hash = abs(hash(question)) % 10000
            filename = f"screenshot_{timestamp}_{question_hash}.png"
            filepath = os.path.join(self.batch_config.screenshot_dir, filename)

            # 保存截图
            with open(filepath, "wb") as f:
                f.write(screenshot.data)

            logger.info(f"Screenshot saved: {filepath}")
            return filepath

        except Exception as e:
            logger.warning(f"Failed to save screenshot: {e}")
            return None

    def _save_progress(self) -> None:
        """保存进度到临时文件。"""
        if not self.results:
            return

        progress_data = {
            "completed": [r.to_dict() for r in self.results],
            "timestamp": datetime.now().isoformat(),
        }

        progress_file = self.progress_file or "./batch_progress.json"
        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Progress saved to {progress_file}")

    def export_results(
        self,
        output_path: str,
        format: str = "excel",
    ) -> None:
        """
        导出结果到文件。

        Args:
            output_path: 输出文件路径
            format: 输出格式（excel 或 json）
        """
        if not self.results:
            logger.warning("No results to export")
            return

        if format == "json":
            self._export_to_json(output_path)
        elif format == "excel":
            self._export_to_excel(output_path)
        else:
            raise ValueError(f"Unsupported format: {format}")

        logger.info(f"Results exported to {output_path}")

    def _export_to_json(self, output_path: str) -> None:
        """导出结果为 JSON。"""
        data = {
            "export_time": datetime.now().isoformat(),
            "total": len(self.results),
            "success": sum(1 for r in self.results if r.success),
            "results": [r.to_dict() for r in self.results],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _export_to_excel(self, output_path: str) -> None:
        """导出结果为 Excel。"""
        if not PANDAS_AVAILABLE:
            raise ImportError(
                "pandas is required for Excel export. "
                "Install with: pip install pandas openpyxl"
            )

        # 准备数据
        data = []
        for r in self.results:
            row = {
                self.batch_config.question_column: r.question,
                self.batch_config.answer_column: r.answer,
                self.batch_config.screenshot_column: r.screenshot_path or "",
                self.batch_config.status_column: "成功" if r.success else f"失败：{r.error_message}",
                "执行步数": r.steps,
                "开始时间": r.start_time.strftime("%Y-%m-%d %H:%M:%S") if r.start_time else "",
                "结束时间": r.end_time.strftime("%Y-%m-%d %H:%M:%S") if r.end_time else "",
            }
            data.append(row)

        df = pd.DataFrame(data)

        # 保存到 Excel
        df.to_excel(output_path, index=False, engine="openpyxl")

        # 调整列宽
        self._adjust_excel_column_widths(output_path)

    def _adjust_excel_column_widths(self, file_path: str) -> None:
        """调整 Excel 列宽。"""
        if not PANDAS_AVAILABLE:
            return

        try:
            from openpyxl import load_workbook

            wb = load_workbook(file_path)
            ws = wb.active

            # 设置列宽
            column_widths = {
                "A": 10,  # 序号
                "B": 50,  # 问题
                "C": 80,  # 答案
                "D": 40,  # 截图路径
                "E": 10,  # 状态
                "F": 10,  # 执行步数
                "G": 20,  # 开始时间
                "H": 20,  # 结束时间
            }

            for col, width in column_widths.items():
                ws.column_dimensions[col].width = width

            wb.save(file_path)
        except Exception as e:
            logger.warning(f"Failed to adjust column widths: {e}")


def run_batch_from_config(
    config_path: str,
    input_file: str,
    output_file: str,
) -> list[BatchResult]:
    """
    从配置文件运行批量任务。

    Args:
        config_path: config.json 路径
        input_file: 输入问题文件
        output_file: 输出结果文件

    Returns:
        结果列表
    """
    # 加载配置
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    model_config = config.get("model", {})
    agent_config_dict = config.get("agent", {})

    # 创建模型配置
    model_cfg = ModelConfig(
        base_url=model_config.get("base_url", "http://localhost:11434/v1"),
        model_name=model_config.get("model_name", "qwen3.5:4b"),
        api_key=model_config.get("api_key", "ollama"),
        use_thinking=model_config.get("use_thinking", False),
    )

    # 创建批量配置
    batch_cfg = BatchConfig(
        max_steps=agent_config_dict.get("max_steps", 50),
        verbose=agent_config_dict.get("verbose", False),
    )

    # 创建执行器
    runner = BatchQuestionRunner(model_config=model_cfg, batch_config=batch_cfg)

    # 加载问题
    runner.load_questions(input_file)

    # 执行批量任务
    results = runner.run_batch()

    # 导出结果
    runner.export_results(output_file)

    return results
