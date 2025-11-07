# 今日头条热榜爬虫
import time
import random
from typing import List, Dict, Any
from .base import BaseScraper

class ToutiaoScraper(BaseScraper):
    """
    今日头条热榜爬虫
    
    @class ToutiaoScraper
    @extends BaseScraper
    """
    
    def __init__(self):
        """
        初始化今日头条爬虫
        使用多个API备选方案以提高稳定性
        """
        super().__init__(platform='toutiao')
        
        # 多个API备选方案，按优先级排序
        self.api_urls = [
            # 官方API
            {
                'url': 'https://www.toutiao.com/hot-event/hot-board/',
                'type': 'official',
                'params': {'origin': 'toutiao_pc'}
            },
            # 第三方聚合API
            {
                'url': 'https://dabenshi.cn/other/api/hot.php',
                'type': 'third_party',
                'params': {'type': 'toutiaoHot'}
            },
            {
                'url': 'https://api.guiguiya.com/api/hotlist/toutiao',
                'type': 'third_party',
                'params': {}
            },
            {
                'url': 'https://hot.imsyy.top/toutiao',
                'type': 'third_party',
                'params': {}
            }
        ]
        
        # 更新请求头
        self.headers.update({
            'Referer': 'https://www.toutiao.com/',
            'Origin': 'https://www.toutiao.com'
        })
        
    def fetch_hot_list(self, limit: int = 30) -> List[Dict[str, Any]]:
        """
        抓取今日头条热榜
        
        @param {int} limit - 抓取条数限制，默认30
        @returns {List[Dict[str, Any]]} 热榜数据列表
        
        说明：
        - 尝试多个API接口，提高成功率
        - 支持官方API和第三方聚合API
        - 带有重试机制和随机延迟
        """
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            # 遍历所有API接口
            for api_config in self.api_urls:
                try:
                    api_url = api_config['url']
                    api_type = api_config['type']
                    params = api_config['params']
                    
                    print(f"尝试API接口 ({api_type}): {api_url}")
                    
                    # 添加随机延迟避免被检测
                    if retry_count > 0:
                        delay = random.uniform(1, 3)
                        print(f"等待 {delay:.1f} 秒后重试...")
                        time.sleep(delay)
                    
                    # 发起请求
                    if params:
                        response = self._make_request(api_url, params=params)
                    else:
                        response = self._make_request(api_url)
                    
                    # 解析响应
                    data = response.json()
                    
                    # 根据不同API类型解析数据
                    hot_list = self._parse_api_response(data, api_type)
                    
                    if hot_list:
                        results = self._process_hot_list(hot_list, limit)
                        if results:
                            print(f"成功获取 {len(results)} 条今日头条热榜数据")
                            return results
                    
                except Exception as e:
                    print(f"API接口异常: {e}, URL: {api_url}")
                    continue
            
            # 所有API都失败，重试
            retry_count += 1
            if retry_count < max_retries:
                print(f"重试 {retry_count}/{max_retries}...")
        
        # 达到最大重试次数，抛出异常
        raise Exception(f"今日头条数据抓取失败，已重试{max_retries}次，所有API接口都不可用")
    
    def _parse_api_response(self, data: Dict[str, Any], api_type: str) -> List[Dict[str, Any]]:
        """
        解析API响应数据
        
        @param {Dict[str, Any]} data - API返回的原始数据
        @param {str} api_type - API类型（official/third_party）
        @returns {List[Dict[str, Any]]} 解析后的热榜列表
        """
        try:
            if api_type == 'official':
                # 官方API格式
                if data.get('status') == 0:
                    return data.get('data', [])
            else:
                # 第三方API格式
                if 'code' in data and data.get('code') == 200:
                    return data.get('data', [])
                elif 'data' in data and isinstance(data.get('data'), list):
                    return data.get('data', [])
                elif isinstance(data, list):
                    return data
        except Exception as e:
            print(f"解析API响应失败: {e}")
        
        return []
    
    def _parse_hot_value(self, hot_value: Any) -> float:
        """
        解析热度值，将字符串格式转换为数字
        
        @param {Any} hot_value - 热度值（可能是字符串或数字）
        @returns {float} 解析后的数字热度值
        """
        if not hot_value:
            return 0.0
        
        # 如果已经是数字，直接返回
        if isinstance(hot_value, (int, float)):
            return float(hot_value)
        
        # 如果是字符串，需要解析
        if isinstance(hot_value, str):
            try:
                # 移除中文字符，只保留数字和小数点
                import re
                # 先提取数字和"万"、"亿"等单位
                match = re.search(r'([\d.]+)\s*(万|亿|w|W)?', hot_value)
                if match:
                    num_str = match.group(1)
                    unit = match.group(2)
                    
                    num = float(num_str)
                    
                    # 根据单位转换
                    if unit in ['万', 'w', 'W']:
                        return num * 10000
                    elif unit in ['亿']:
                        return num * 100000000
                    else:
                        return num
            except:
                pass
        
        return 0.0
    
    def _process_hot_list(self, hot_list: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        """
        处理热榜列表数据
        
        @param {List[Dict[str, Any]]} hot_list - 原始热榜列表
        @param {int} limit - 处理条数限制
        @returns {List[Dict[str, Any]]} 标准化后的热榜数据
        """
        results = []
        
        for idx, item in enumerate(hot_list[:limit], 1):
            try:
                # 兼容不同API的字段名
                title = (
                    item.get('Title') or 
                    item.get('title') or 
                    item.get('word') or 
                    ''
                ).strip()
                
                if not title:
                    continue
                
                # 提取URL
                url = (
                    item.get('Url') or 
                    item.get('url') or 
                    item.get('link') or 
                    f'https://www.toutiao.com/search/?keyword={title}'
                )
                
                # 提取热度值并解析
                hot_value_raw = (
                    item.get('HotValue') or 
                    item.get('hot_value') or 
                    item.get('hot') or 
                    item.get('hot_score') or 
                    0
                )
                hot_value = self._parse_hot_value(hot_value_raw)
                
                # 提取摘要
                summary = (
                    item.get('Abstract') or 
                    item.get('summary') or 
                    item.get('desc') or 
                    title
                ).strip()
                
                # 提取图片URL
                image_url = ''
                if 'Image' in item and isinstance(item['Image'], dict):
                    image_url = item['Image'].get('url', '')
                else:
                    image_url = item.get('image_url') or item.get('pic') or ''
                
                # 构建结果
                result = {
                    'platform': self.platform,
                    'rank': idx,
                    'title': title,
                    'summary': summary,
                    'url': url,
                    'hot_value': hot_value,
                    'image_url': image_url,
                    'cluster_id': item.get('ClusterId') or item.get('cluster_id') or '',
                    'label': item.get('LabelUrl') or item.get('label') or '',
                    'interactions': {
                        'hot_value': hot_value,
                        'hot_rank': item.get('HotRank') or item.get('index') or idx,
                    },
                    'fetched_at': None
                }
                
                results.append(result)
                
            except Exception as e:
                print(f"处理第 {idx} 条数据时出错: {e}")
                continue
        
        return results
    
