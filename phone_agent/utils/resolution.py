"""
分辨率转换工具模块
提供截屏图片分辨率转换和坐标映射功能

优化说明：
- 使用高精度浮点计算减少累积误差
- 添加点击偏移量提高容错率（针对小参数模型定位不准）
- 支持区域点击而非精确点点击
"""
from typing import Tuple, Optional
from PIL import Image
import json
from pathlib import Path


# 全局配置（可从 config.json 加载）
COORDINATE_OPTIMIZATION_CONFIG = {
    'enabled': True,
    'click_offset_x': 8,
    'click_offset_y': 8,
    'use_region_click': True,
    'min_click_region': 30
}


def load_coordinate_config() -> dict:
    """从 config.json 加载坐标优化配置"""
    config_paths = [
        Path(__file__).parent.parent.parent / "config.json",
        Path(__file__).parent / "config.json",
        Path.cwd() / "config.json",
    ]

    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                return config.get('coordinate_optimization', COORDINATE_OPTIMIZATION_CONFIG)
            except (json.JSONDecodeError, IOError):
                pass

    return COORDINATE_OPTIMIZATION_CONFIG


# 加载配置
COORDINATE_OPTIMIZATION_CONFIG = load_coordinate_config()


class ResolutionConverter:
    """
    分辨率转换器
    将截屏图片等比压缩至 1920x1080 的标准 1K 分辨率
    """

    TARGET_WIDTH = 1920
    TARGET_HEIGHT = 1080

    def __init__(self):
        """初始化分辨率转换器"""
        self.original_width: Optional[int] = None
        self.original_height: Optional[int] = None
        self.scale_ratio: Optional[float] = None
        self.scaled_width: Optional[int] = None
        self.scaled_height: Optional[int] = None

    def compress_to_1k(self, image: Image.Image) -> Image.Image:
        """
        将图片等比压缩到 1920x1080 范围内

        Args:
            image: PIL Image 对象

        Returns:
            压缩后的 PIL Image 对象
        """
        # 记录原始分辨率
        self.original_width, self.original_height = image.size

        # 计算缩放比例（保持宽高比）
        width_ratio = self.TARGET_WIDTH / self.original_width
        height_ratio = self.TARGET_HEIGHT / self.original_height

        # 选择较小的比例以确保图片完全适配目标分辨率
        self.scale_ratio = min(width_ratio, height_ratio, 1.0)  # 不放大，只缩小

        # 计算缩放后的尺寸
        self.scaled_width = int(self.original_width * self.scale_ratio)
        self.scaled_height = int(self.original_height * self.scale_ratio)

        # 如果不需要缩放，直接返回原图
        if self.scale_ratio >= 1.0:
            return image.copy()

        # 执行等比缩放，使用 LANCZOS 重采样保证质量
        compressed_image = image.resize(
            (self.scaled_width, self.scaled_height),
            resample=Image.Resampling.LANCZOS
        )

        return compressed_image


class CoordinateMapper:
    """
    坐标映射器
    在 1K 分辨率和原始分辨率之间转换坐标点

    优化策略：
    1. 使用高精度浮点计算，最后再取整
    2. 添加点击偏移量提高容错率
    3. 针对小参数模型，返回区域中心点而非精确点
    """

    def __init__(self, original_width: int, original_height: int,
                 scaled_width: int, scaled_height: int,
                 config: Optional[dict] = None):
        """
        初始化坐标映射器

        Args:
            original_width: 原始图片宽度
            original_height: 原始图片高度
            scaled_width: 缩放后图片宽度
            scaled_height: 缩放后图片高度
            config: 可选的优化配置字典
        """
        self.original_width = original_width
        self.original_height = original_height
        self.scaled_width = scaled_width
        self.scaled_height = scaled_height

        # 加载配置（优先使用传入的 config）
        self.config = config or COORDINATE_OPTIMIZATION_CONFIG
        self.enabled = self.config.get('enabled', True)
        self.click_offset_x = self.config.get('click_offset_x', 8)
        self.click_offset_y = self.config.get('click_offset_y', 8)
        self.min_click_region = self.config.get('min_click_region', 30)

        # 计算缩放比例（高精度浮点数）
        self.scale_x = scaled_width / original_width
        self.scale_y = scaled_height / original_height

        # 计算逆向缩放比例（高精度浮点数）
        self.inverse_scale_x = original_width / scaled_width
        self.inverse_scale_y = original_height / scaled_height

    @classmethod
    def from_converter(cls, converter: ResolutionConverter) -> 'CoordinateMapper':
        """从 ResolutionConverter 创建 CoordinateMapper"""
        if (converter.original_width is None or
            converter.original_height is None or
            converter.scaled_width is None or
            converter.scaled_height is None):
            raise ValueError("ResolutionConverter 尚未处理任何图片")

        return cls(
            converter.original_width,
            converter.original_height,
            converter.scaled_width,
            converter.scaled_height
        )

    def to_original_coordinate(self, x: float, y: float,
                               add_click_offset: bool = True) -> Tuple[int, int]:
        """
        将 1K 坐标转换为原始坐标

        优化：
        1. 高精度浮点计算，最后统一取整
        2. 添加点击偏移量，提高容错率
        3. 边界检查

        Args:
            x: 1K 分辨率的 x 坐标
            y: 1K 分辨率的 y 坐标
            add_click_offset: 是否添加点击偏移量（针对小参数模型）

        Returns:
            (原始分辨率的 x 坐标，原始分辨率的 y 坐标)
        """
        # 高精度浮点计算
        original_x_precise = x * self.inverse_scale_x
        original_y_precise = y * self.inverse_scale_y

        # 添加点击偏移量（向区域中心偏移）
        if add_click_offset and self.enabled:
            offset_x, offset_y = self.get_pixel_offset(x, y)

            # 如果偏移量较大，说明取整误差大，手动调整
            if offset_x > 0.3:
                original_x_precise += self.click_offset_x
            if offset_y > 0.3:
                original_y_precise += self.click_offset_y

            # 额外添加固定偏移，让点击更靠近元素中心
            original_x_precise += self.click_offset_x * 0.5
            original_y_precise += self.click_offset_y * 0.5

        # 四舍五入取整
        original_x = int(original_x_precise + 0.5)
        original_y = int(original_y_precise + 0.5)

        # 边界检查
        original_x = max(0, min(original_x, self.original_width - 1))
        original_y = max(0, min(original_y, self.original_height - 1))

        return original_x, original_y

    def to_original_region(self, x: float, y: float,
                           size_1k: Optional[float] = None) -> Tuple[int, int, int, int]:
        """
        将 1K 坐标点转换为原始分辨率下的矩形区域
        用于小参数模型：点击一个区域而非精确点

        Args:
            x: 1K 分辨率的 x 坐标
            y: 1K 分辨率的 y 坐标
            size_1k: 1K 分辨率下的区域大小（默认 40 像素）

        Returns:
            (original_x1, original_y1, original_x2, original_y2)
        """
        if size_1k is None:
            size_1k = 40

        # 计算原始分辨率下的区域大小
        region_size_x = size_1k * self.inverse_scale_x
        region_size_y = size_1k * self.inverse_scale_y

        # 计算中心点（带偏移）
        center_x, center_y = self.to_original_coordinate(x, y, add_click_offset=True)

        # 计算区域边界
        half_size_x = max(region_size_x / 2, self.min_click_region / 2)
        half_size_y = max(region_size_y / 2, self.min_click_region / 2)

        x1 = max(0, int(center_x - half_size_x))
        y1 = max(0, int(center_y - half_size_y))
        x2 = min(self.original_width - 1, int(center_x + half_size_x))
        y2 = min(self.original_height - 1, int(center_y + half_size_y))

        return x1, y1, x2, y2

    def get_pixel_offset(self, x_1k: float, y_1k: float) -> Tuple[float, float]:
        """计算 1K 坐标转换到原始分辨率时的像素偏移量"""
        original_x_precise = x_1k * self.inverse_scale_x
        original_y_precise = y_1k * self.inverse_scale_y

        offset_x = original_x_precise - int(original_x_precise)
        offset_y = original_y_precise - int(original_y_precise)

        return offset_x, offset_y
