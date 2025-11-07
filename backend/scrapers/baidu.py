# 百度热搜榜爬虫
import re
import time
import random
from typing import List, Dict, Any
from .base import BaseScraper

class BaiduScraper(BaseScraper):
    """
    百度热搜榜爬虫
    
    @class BaiduScraper
    @extends BaseScraper
    """
    
    def __init__(self):
        """
        初始化百度热搜爬虫
        使用多个API备选方案以提高稳定性
        """
        super().__init__(platform='baidu')
        
        # 多个API备选方案，按优先级排序
        self.api_urls = [
            {
                'url': 'https://top.baidu.com/api/board?platform=pc&tab=realtime',
                'type': 'official'
            },
            {
                'url': 'https://top.baidu.com/board/api/getHotSearchList',
                'type': 'official'
            },
            {
                'url': 'https://top.baidu.com/api/board',
                'type': 'official'
            }
        ]
        
        # 更新请求头
        self.headers.update({
            'Referer': 'https://top.baidu.com/board?tab=realtime',
            'Origin': 'https://top.baidu.com',
            'Accept': 'application/json, text/plain, */*'
        })
        
    def fetch_hot_list(self, limit: int = 30) -> List[Dict[str, Any]]:
        """
        抓取百度热搜榜
        
        @param {int} limit - 抓取条数限制，默认30
        @returns {List[Dict[str, Any]]} 热榜数据列表
        
        说明：
        - 尝试多个API接口，提高成功率
        - 支持官方API
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
                    
                    print(f"尝试API接口 ({api_type}): {api_url}")
                    
                    # 添加随机延迟避免被检测
                    if retry_count > 0:
                        delay = random.uniform(1, 3)
                        print(f"等待 {delay:.1f} 秒后重试...")
                        time.sleep(delay)
                    
                    # 发起请求
                    response = self._make_request(api_url)
                    
                    # 解析响应
                    data = response.json()
                    
                    # 解析API响应
                    results = self._parse_api_response(data, limit)
                    
                    if results:
                        print(f"成功获取 {len(results)} 条百度热搜榜数据")
                        return results
                    
                except Exception as e:
                    print(f"API接口异常: {e}, URL: {api_url}")
                    continue
            
            # 所有API都失败，重试
            retry_count += 1
            if retry_count < max_retries:
                print(f"重试 {retry_count}/{max_retries}...")
        
        # 达到最大重试次数，抛出异常
        raise Exception(f"百度数据抓取失败，已重试{max_retries}次，所有API接口都不可用")
    
    def _parse_api_response(self, data: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        """
        解析API响应数据
        
        @param {Dict[str, Any]} data - API返回的原始数据
        @param {int} limit - 处理条数限制
        @returns {List[Dict[str, Any]]} 解析后的热榜列表
        """
        results = []
        
        try:
            # 百度热搜API数据结构：data.data.cards[0].content
            if 'data' not in data:
                print("未找到data字段")
                return []
            
            cards = data['data'].get('cards', [])
            print(f"找到 {len(cards)} 个卡片")
            
            if not cards:
                print("cards为空")
                return []
            
            # 从第一个card中获取content数据
            if 'content' not in cards[0]:
                print("未找到content字段")
                return []
            
            content = cards[0]['content']
            print(f"找到 {len(content)} 个热搜条目")
            
            for idx, item in enumerate(content[:limit], 1):
                try:
                    # 提取标题 (word字段)
                    title = item.get('word', '').strip()
                    if not title:
                        continue
                    
                    # 提取URL (url字段)
                    url = item.get('url', '')
                    if url and not url.startswith('http'):
                        url = f"https://www.baidu.com{url}"
                    
                    # 提取热度值 (hotScore字段)
                    hot_value = item.get('hotScore', '')
                    
                    # 提取摘要 (desc字段)
                    summary = item.get('desc', '').strip() or title
                    
                    # 提取图片URL
                    image_url = item.get('img', '')
                    
                    # 提取标签
                    tag = item.get('hotTag', '') or item.get('label', '')
                    
                    # 构建结果
                    result = {
                        'platform': self.platform,
                        'rank': idx,
                        'title': title,
                        'summary': summary,
                        'url': url,
                        'hot_value': float(hot_value) if hot_value else 0.0,
                        'image_url': image_url,
                        'tag': tag,
                        'interactions': {
                            'hot_score': hot_value,
                        },
                        'fetched_at': None
                    }
                    
                    results.append(result)
                    
                except Exception as e:
                    print(f"处理第 {idx} 条数据时出错: {e}")
                    continue
            
        except Exception as e:
            print(f"解析API响应失败: {e}")
        
        return results
    
