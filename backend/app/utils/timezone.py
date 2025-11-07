"""
时区工具函数

统一管理项目中的时区处理
"""
from datetime import datetime
import pytz

# 中国时区
CN_TZ = pytz.timezone('Asia/Shanghai')


def now_cn() -> datetime:
    """
    获取中国时区的当前时间（naive datetime）
    
    Returns:
        中国时区的当前时间，不带时区信息
    """
    return datetime.now(CN_TZ).replace(tzinfo=None)


def utc_to_cn(utc_dt: datetime) -> datetime:
    """
    将UTC时间转换为中国时间
    
    Args:
        utc_dt: UTC时间（naive或aware）
        
    Returns:
        中国时区时间（naive）
    """
    if utc_dt.tzinfo is None:
        # 如果是naive datetime，假定为UTC
        utc_dt = pytz.UTC.localize(utc_dt)
    return utc_dt.astimezone(CN_TZ).replace(tzinfo=None)


def cn_to_utc(cn_dt: datetime) -> datetime:
    """
    将中国时间转换为UTC时间
    
    Args:
        cn_dt: 中国时区时间（naive或aware）
        
    Returns:
        UTC时间（naive）
    """
    if cn_dt.tzinfo is None:
        # 如果是naive datetime，假定为中国时区
        cn_dt = CN_TZ.localize(cn_dt)
    return cn_dt.astimezone(pytz.UTC).replace(tzinfo=None)

