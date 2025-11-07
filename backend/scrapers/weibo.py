# 微博热搜爬虫
from typing import List, Dict, Any
from .base import BaseScraper

class WeiboScraper(BaseScraper):
    """微博热搜榜爬虫"""
    
    def __init__(self):
        super().__init__(platform='weibo')
        # 微博热搜API
        self.api_url = 'https://weibo.com/ajax/side/hotSearch'
        # 更新请求头，添加Referer
        self.headers.update({
            'Referer': 'https://weibo.com/',
            'Accept-Language': 'zh-CN,zh;q=0.9'
        })
        
    def fetch_hot_list(self, limit: int = 30) -> List[Dict[str, Any]]:
        """
        抓取微博热搜榜
        
        文档说明：
        - API: https://weibo.com/ajax/side/hotSearch
        - 返回热搜列表，包含标题、摘要、热度值
        - 关键：需要Referer头部
        """
        try:
            response = self._make_request(self.api_url)
            data = response.json()
            
            if data.get('ok') != 1:
                raise Exception(f"API返回错误: {data}")
            
            hot_list = data.get('data', {}).get('realtime', [])
            
            results = []
            for item in hot_list[:limit]:
                # 提取关键字段
                result = {
                    'platform': self.platform,
                    'title': item.get('word', '').strip(),
                    'summary': item.get('word_scheme', '').strip() or item.get('word', '').strip(),
                    'url': f"https://s.weibo.com/weibo?q=%23{item.get('word', '')}%23",
                    'hot_value': item.get('num', 0),
                    'category': item.get('category', ''),
                    'rank': item.get('rank', 0),
                    'interactions': {
                        'hot_value': item.get('num', 0),
                        'icon_desc': item.get('icon_desc', ''),
                        'icon_desc_color': item.get('icon_desc_color', '')
                    },
                    'fetched_at': None  # 在run方法中会设置
                }
                results.append(result)
                
            return results
            
        except Exception as e:
            print(f"微博数据抓取失败: {e}")
            raise
