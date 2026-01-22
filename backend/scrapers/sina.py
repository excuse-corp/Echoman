# 新浪新闻热榜爬虫
import re
import time
import random
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from .base import BaseScraper

class SinaScraper(BaseScraper):
    """
    新浪新闻热榜爬虫
    
    @class SinaScraper
    @extends BaseScraper
    """
    
    def __init__(self):
        """
        初始化新浪新闻爬虫
        使用多个数据源以提高稳定性
        """
        super().__init__(platform='sina')
        
        # 多个API/数据源
        self.base_url = 'https://news.sina.com.cn/'
        self.api_urls = [
            'https://interface.sina.cn/news/wap/fymap2018_data.d.json',
            'https://top.news.sina.com.cn/ws/GetTopDataList.php?top_type=day&top_cat=www',
        ]
        
        # 更新请求头
        self.headers.update({
            'Referer': 'https://news.sina.com.cn/',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        })
        self._noise_titles = {
            "点击查看更多实时热点",
            "点击查看更多热点",
            "查看更多实时热点",
        }

    def _is_noise_item(self, title: str, url: str = "") -> bool:
        """
        过滤爬虫误操作产生的噪音项（如“点击查看更多实时热点”）
        """
        if not title:
            return True
        compact_title = re.sub(r"\s+", "", title)
        if compact_title in self._noise_titles:
            return True
        if "点击查看更多" in compact_title and ("热点" in compact_title or "热榜" in compact_title):
            return True
        if url and "top_news_list" in url:
            return True
        return False
        
    def fetch_hot_list(self, limit: int = 30) -> List[Dict[str, Any]]:
        """
        抓取新浪新闻热榜
        
        @param {int} limit - 抓取条数限制，默认30
        @returns {List[Dict[str, Any]]} 热榜数据列表
        
        说明：
        - 优先尝试API接口
        - 如果API失败，则从首页解析热榜
        - 包含详细的内容提取和互动数据
        """
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            # 1. 尝试API接口
            for api_url in self.api_urls:
                try:
                    print(f"尝试API接口: {api_url}")
                    response = self._make_request(api_url)
                    data = response.json()
                    
                    results = self._parse_api_response(data, limit)
                    if results:
                        print(f"成功获取 {len(results)} 条新浪新闻热榜数据")
                        return results
                        
                except Exception as e:
                    print(f"API接口异常: {e}, URL: {api_url}")
                    continue
            
            # 2. 尝试从首页抓取
            try:
                print(f"尝试从新浪首页抓取热榜...")
                results = self._fetch_from_homepage(limit)
                if results:
                    print(f"成功从首页获取 {len(results)} 条新浪新闻热榜数据")
                    return results
            except Exception as e:
                print(f"首页抓取失败: {e}")
            
            # 重试
            retry_count += 1
            if retry_count < max_retries:
                delay = random.uniform(1, 3)
                print(f"等待 {delay:.1f} 秒后重试 ({retry_count}/{max_retries})...")
                time.sleep(delay)
        
        # 所有方法都失败，抛出异常
        raise Exception(f"新浪数据抓取失败，已重试{max_retries}次，所有数据源都不可用")
    
    def _parse_api_response(self, data: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        """
        解析API响应数据
        
        @param {Dict[str, Any]} data - API返回的原始数据
        @param {int} limit - 处理条数限制
        @returns {List[Dict[str, Any]]} 解析后的热榜列表
        """
        results = []
        
        try:
            # 尝试不同的数据结构
            hot_list = []
            
            if 'data' in data:
                hot_list = data.get('data', {}).get('news', [])
                if not hot_list:
                    hot_list = data.get('data', [])
            elif 'result' in data:
                hot_list = data.get('result', {}).get('data', [])
            elif isinstance(data, list):
                hot_list = data
            
            if not hot_list:
                return []
            
            for idx, item in enumerate(hot_list[:limit], 1):
                try:
                    title = (item.get('title') or item.get('Title') or '').strip()
                    if not title:
                        continue
                    url = item.get('url') or item.get('link') or ''
                    if self._is_noise_item(title, url):
                        continue
                    
                    result = {
                        'platform': self.platform,
                        'rank': idx,
                        'title': title,
                        'summary': (
                            item.get('intro') or 
                            item.get('summary') or 
                            item.get('desc') or 
                            title
                        ).strip(),
                        'url': url,
                        'keywords': item.get('keywords') or '',
                        'ctime': item.get('ctime') or item.get('time') or '',
                        'media_name': item.get('media_name') or item.get('source') or '新浪新闻',
                        'interactions': {
                            'comment_count': item.get('comment_count') or item.get('comments') or 0,
                            'read_count': item.get('read_count') or 0,
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
    
    def _fetch_from_homepage(self, limit: int) -> List[Dict[str, Any]]:
        """
        从新浪首页抓取热榜
        
        @param {int} limit - 抓取条数限制
        @returns {List[Dict[str, Any]]} 热榜数据列表
        """
        try:
            response = self._make_request(self.base_url)
            html_content = response.text
            
            soup = BeautifulSoup(html_content, 'html.parser')
            results = []
            
            # 查找热榜区域
            hot_rank_selectors = [
                'div.blk_main_card',
                'div.hot-rank',
                'div.hot-list',
                'div.rank-list'
            ]
            
            hot_rank_div = None
            for selector in hot_rank_selectors:
                divs = soup.select(selector)
                for div in divs:
                    if '热榜' in str(div) or '热点' in str(div):
                        hot_rank_div = div
                        break
                if hot_rank_div:
                    break
            
            if not hot_rank_div:
                print("未找到热榜区域")
                return []
            
            # 解析热榜列表
            li_elements = hot_rank_div.find_all('li')
            print(f"找到 {len(li_elements)} 个热榜项")
            
            for li in li_elements[:limit]:
                try:
                    # 跳过广告
                    if 'ad' in li.get('class', []) or li.find('ins', class_='sinaads'):
                        continue
                    
                    a_element = li.find('a')
                    if not a_element:
                        continue
                    
                    title = a_element.get_text(strip=True)
                    url = a_element.get('href', '')
                    
                    if not title:
                        continue
                    
                    # 补全URL
                    if url and not url.startswith('http'):
                        url = urljoin(self.base_url, url)
                    if self._is_noise_item(title, url):
                        continue
                    
                    rank = len(results) + 1
                    
                    # 提取热度值
                    hot_value = 0
                    hot_elem = li.find(class_=re.compile('hot|count'))
                    if hot_elem:
                        hot_text = hot_elem.get_text()
                        match = re.search(r'(\d+)', hot_text)
                        if match:
                            hot_value = int(match.group(1))
                    
                    result = {
                        'platform': self.platform,
                        'rank': rank,
                        'title': title,
                        'summary': title,
                        'url': url,
                        'keywords': '',
                        'ctime': '',
                        'media_name': '新浪新闻',
                        'hot_value': hot_value,
                        'interactions': {
                            'comment_count': 0,
                            'read_count': 0,
                        },
                        'fetched_at': None
                    }
                    
                    results.append(result)
                    print(f"获取热榜第{rank}条: {title[:30]}...")
                    
                    # 添加随机延迟
                    time.sleep(random.uniform(0.3, 0.8))
                    
                except Exception as e:
                    print(f"解析热榜项失败: {e}")
                    continue
            
            return results
            
        except Exception as e:
            print(f"从首页抓取失败: {e}")
            return []
    
    def _extract_content(self, soup: BeautifulSoup) -> str:
        """
        提取文章内容
        
        @param {BeautifulSoup} soup - 解析后的HTML
        @returns {str} 提取的内容摘要
        """
        content_selectors = [
            'div.article-content',
            'div#artibody',
            'div.content',
            'div.article_content',
            'div.main-content',
            'div.text'
        ]
        
        for selector in content_selectors:
            content_div = soup.select_one(selector)
            if content_div:
                # 移除脚本和样式
                for script in content_div.find_all(['script', 'style', 'ins']):
                    script.decompose()
                
                content = content_div.get_text(strip=True)
                if len(content) > 100:
                    return content[:500]
        
        return ""
    
    def _extract_time(self, soup: BeautifulSoup, html_content: str) -> str:
        """
        提取时间信息
        
        @param {BeautifulSoup} soup - 解析后的HTML
        @param {str} html_content - 原始HTML内容
        @returns {str} 提取的时间信息
        """
        time_selectors = [
            'time',
            'span.date',
            'span.time',
            'div.date',
            'span.pub-date'
        ]
        
        for selector in time_selectors:
            time_elem = soup.select_one(selector)
            if time_elem:
                return time_elem.get_text(strip=True)
        
        # 正则表达式匹配
        time_patterns = [
            r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})',
            r'(\d{4}年\d{2}月\d{2}日)',
        ]
        
        for pattern in time_patterns:
            match = re.search(pattern, html_content)
            if match:
                return match.group(1)
        
        return ""
    
