"""
分辨率转换工具模块
提供截屏图片分辨率转换和坐标映射功能
"""
from typing import Tuple, Optional, Dict, Any
from PIL import Image
import io


class ResolutionConverter:
    """
    分辨率转换器
    将截屏图片等比压缩为1920x1080的标准1K分辨率
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
        将图片等比压缩到1920x1080范围内
        
        Args:
            image: PIL Image对象
            
        Returns:
            压缩后的PIL Image对象
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
        
        # 执行等比缩放
        compressed_image = image.resize(  # type: ignore[misc]
            (self.scaled_width, self.scaled_height),
            resample=Image.Resampling.LANCZOS
        )
        
        return compressed_image
    
    def compress_from_path(self, image_path: str, output_path: Optional[str] = None) -> Image.Image:
        """
        从文件路径读取图片并压缩
        
        Args:
            image_path: 输入图片路径
            output_path: 输出图片路径（可选）
            
        Returns:
            压缩后的PIL Image对象
        """
        image = Image.open(image_path)
        compressed_image = self.compress_to_1k(image)
        
        if output_path:
            compressed_image.save(output_path)
        
        return compressed_image
    
    def compress_from_bytes(self, image_bytes: bytes) -> Tuple[Image.Image, bytes]:
        """
        从字节数据压缩图片
        
        Args:
            image_bytes: 图片字节数据
            
        Returns:
            (压缩后的PIL Image对象, 压缩后的字节数据)
        """
        image = Image.open(io.BytesIO(image_bytes))
        compressed_image = self.compress_to_1k(image)
        
        # 转换为字节
        output_bytes = io.BytesIO()
        compressed_image.save(output_bytes, format=image.format or 'PNG')
        output_bytes.seek(0)
        
        return compressed_image, output_bytes.getvalue()
    
    def get_conversion_info(self) -> Dict[str, Any]:
        """
        获取转换信息
        
        Returns:
            包含原始尺寸、缩放后尺寸和缩放比例的字典
        """
        return {
            'original_size': (self.original_width, self.original_height),
            'scaled_size': (self.scaled_width, self.scaled_height),
            'scale_ratio': self.scale_ratio,
            'target_size': (self.TARGET_WIDTH, self.TARGET_HEIGHT)
        }


class CoordinateMapper:
    """
    坐标映射器
    在1K分辨率和原始分辨率之间转换坐标点
    """
    
    def __init__(self, original_width: int, original_height: int, 
                 scaled_width: int, scaled_height: int):
        """
        初始化坐标映射器
        
        Args:
            original_width: 原始图片宽度
            original_height: 原始图片高度
            scaled_width: 缩放后图片宽度
            scaled_height: 缩放后图片高度
        """
        self.original_width = original_width
        self.original_height = original_height
        self.scaled_width = scaled_width
        self.scaled_height = scaled_height
        
        # 计算缩放比例
        self.scale_x = scaled_width / original_width
        self.scale_y = scaled_height / original_height
        
        # 计算逆向缩放比例
        self.inverse_scale_x = original_width / scaled_width
        self.inverse_scale_y = original_height / scaled_height
    
    @classmethod
    def from_converter(cls, converter: ResolutionConverter) -> 'CoordinateMapper':
        """
        从ResolutionConverter创建CoordinateMapper
        
        Args:
            converter: ResolutionConverter实例
            
        Returns:
            CoordinateMapper实例
        """
        if (converter.original_width is None or 
            converter.original_height is None or
            converter.scaled_width is None or
            converter.scaled_height is None):
            raise ValueError("ResolutionConverter尚未处理任何图片")
        
        return cls(
            converter.original_width,
            converter.original_height,
            converter.scaled_width,
            converter.scaled_height
        )
    
    def to_1k_coordinate(self, x: float, y: float) -> Tuple[int, int]:
        """
        将原始分辨率的坐标转换为1K分辨率的坐标
        
        Args:
            x: 原始分辨率的x坐标
            y: 原始分辨率的y坐标
            
        Returns:
            (1K分辨率的x坐标, 1K分辨率的y坐标)
        """
        scaled_x = int(x * self.scale_x)
        scaled_y = int(y * self.scale_y)
        
        # 确保坐标在有效范围内
        scaled_x = max(0, min(scaled_x, self.scaled_width - 1))
        scaled_y = max(0, min(scaled_y, self.scaled_height - 1))
        
        return scaled_x, scaled_y
    
    def to_original_coordinate(self, x: float, y: float) -> Tuple[int, int]:
        """
        将1K分辨率的坐标转换为原始分辨率的坐标
        
        Args:
            x: 1K分辨率的x坐标
            y: 1K分辨率的y坐标
            
        Returns:
            (原始分辨率的x坐标, 原始分辨率的y坐标)
        """
        # 使用 round 四舍五入代替 int 截断，减少精度损失
        original_x = round(x * self.inverse_scale_x)
        original_y = round(y * self.inverse_scale_y)
        
        # 确保坐标在有效范围内
        original_x = max(0, min(original_x, self.original_width - 1))
        original_y = max(0, min(original_y, self.original_height - 1))
        
        return original_x, original_y
    
    def to_1k_region(self, x1: float, y1: float, x2: float, y2: float) -> Tuple[int, int, int, int]:
        """
        将原始分辨率的矩形区域转换为1K分辨率
        
        Args:
            x1, y1: 左上角坐标
            x2, y2: 右下角坐标
            
        Returns:
            (scaled_x1, scaled_y1, scaled_x2, scaled_y2)
        """
        scaled_x1, scaled_y1 = self.to_1k_coordinate(x1, y1)
        scaled_x2, scaled_y2 = self.to_1k_coordinate(x2, y2)
        return scaled_x1, scaled_y1, scaled_x2, scaled_y2
    
    def to_original_region(self, x1: float, y1: float, x2: float, y2: float) -> Tuple[int, int, int, int]:
        """
        将1K分辨率的矩形区域转换为原始分辨率
        
        Args:
            x1, y1: 左上角坐标
            x2, y2: 右下角坐标
            
        Returns:
            (original_x1, original_y1, original_x2, original_y2)
        """
        original_x1, original_y1 = self.to_original_coordinate(x1, y1)
        original_x2, original_y2 = self.to_original_coordinate(x2, y2)
        return original_x1, original_y1, original_x2, original_y2
    
    def get_pixel_offset(self, x_1k: float, y_1k: float) -> Tuple[float, float]:
        """
        计算1K分辨率坐标点转换到原始分辨率时的像素偏移量
        
        Args:
            x_1k: 1K分辨率的x坐标
            y_1k: 1K分辨率的y坐标
            
        Returns:
            (x方向偏移量, y方向偏移量)
        """
        # 精确计算原始坐标（不取整）
        original_x_precise = x_1k * self.inverse_scale_x
        original_y_precise = y_1k * self.inverse_scale_y
        
        # 取整后的坐标
        original_x_int = int(original_x_precise)
        original_y_int = int(original_y_precise)
        
        # 计算偏移量
        offset_x = original_x_precise - original_x_int
        offset_y = original_y_precise - original_y_int
        
        return offset_x, offset_y
    
    def get_mapping_info(self) -> Dict[str, Any]:
        """
        获取映射信息
        
        Returns:
            包含分辨率和缩放比例的字典
        """
        return {
            'original_resolution': (self.original_width, self.original_height),
            'scaled_resolution': (self.scaled_width, self.scaled_height),
            'scale_ratio': (self.scale_x, self.scale_y),
            'inverse_scale_ratio': (self.inverse_scale_x, self.inverse_scale_y)
        }


# 便捷函数
def create_converter_and_mapper(image: Image.Image) -> Tuple[ResolutionConverter, CoordinateMapper]:
    """
    创建转换器和映射器的便捷函数
    
    Args:
        image: PIL Image对象
        
    Returns:
        (ResolutionConverter实例, CoordinateMapper实例)
    """
    converter = ResolutionConverter()
    converter.compress_to_1k(image)
    mapper = CoordinateMapper.from_converter(converter)
    return converter, mapper
