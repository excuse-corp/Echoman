# 虎扑热榜爬虫
import re
import time
import random
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from .base import BaseScraper

class HupuScraper(BaseScraper):
    """
    虎扑热榜爬虫
    
    @class HupuScraper
    @extends BaseScraper
    """
    
    def __init__(self):
        """
        初始化虎扑热榜爬虫
        抓取篮球热榜和足球热榜
        """
        super().__init__(platform='hupu')
        
        # 虎扑首页
        self.base_url = 'https://www.hupu.com/'
        
        # 更新请求头
        self.headers.update({
            'Referer': 'https://www.hupu.com/',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        })
        
    def fetch_hot_list(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        抓取虎扑热榜（篮球+足球）
        
        @param {int} limit - 每个榜单抓取条数限制，默认20
        @returns {List[Dict[str, Any]]} 热榜数据列表
        
        说明：
        - 从虎扑首页抓取篮球热榜和足球热榜
        - 包含标题、URL、排名等信息
        """
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                print(f"尝试从虎扑首页抓取热榜...")
                results = self._fetch_from_homepage(limit)
                
                if results:
                    print(f"成功获取 {len(results)} 条虎扑热榜数据")
                    return results
                    
            except Exception as e:
                print(f"抓取失败: {e}")
            
            # 重试
            retry_count += 1
            if retry_count < max_retries:
                delay = random.uniform(1, 3)
                print(f"等待 {delay:.1f} 秒后重试 ({retry_count}/{max_retries})...")
                time.sleep(delay)
        
        # 所有尝试都失败，抛出异常
        raise Exception(f"虎扑数据抓取失败，已重试{max_retries}次")
    
    def _fetch_from_homepage(self, limit: int) -> List[Dict[str, Any]]:
        """
        从虎扑首页抓取热榜
        
        @param {int} limit - 抓取条数限制
        @returns {List[Dict[str, Any]]} 热榜数据列表
        """
        try:
            response = self._make_request(self.base_url)
            html_content = response.text
            
            soup = BeautifulSoup(html_content, 'html.parser')
            results = []
            seen_urls = set()  # 用于去重的URL集合
            
            # 查找篮球热榜和足球热榜区域
            hot_sections = [
                ('篮球热榜', 'basketball'),
                ('足球热榜', 'football')
            ]
            
            for section_name, section_type in hot_sections:
                print(f"\n查找{section_name}...")
                
                # 查找包含热榜标题的元素
                section_div = None
                
                # 尝试多种方式查找
                all_text_elements = soup.find_all(text=re.compile(section_name))
                for text_elem in all_text_elements:
                    parent = text_elem.parent
                    if parent:
                        # 向上查找包含列表的容器
                        for i in range(5):  # 最多向上找5层
                            if parent:
                                # 查找是否有列表项
                                items = parent.find_all(['li', 'div', 'a'])
                                if len(items) >= 5:
                                    section_div = parent
                                    print(f"找到{section_name}区域，包含 {len(items)} 个元素")
                                    break
                                parent = parent.parent
                    if section_div:
                        break
                
                if not section_div:
                    print(f"未找到{section_name}，尝试备用查找方式")
                    continue
                
                # 解析热榜列表
                items = section_div.find_all(['li', 'div', 'a'])
                item_count = 0
                
                for item in items:
                    try:
                        if item_count >= limit:
                            break
                        
                        # 获取标题
                        title = ''
                        url = ''
                        
                        # 如果是<a>标签
                        if item.name == 'a':
                            title = item.get_text(strip=True)
                            url = item.get('href', '')
                        else:
                            # 查找内部的<a>标签
                            a_elem = item.find('a')
                            if a_elem:
                                title = a_elem.get_text(strip=True)
                                url = a_elem.get('href', '')
                        
                        # 过滤无效数据
                        if not title or len(title) < 5:
                            continue
                        
                        # 过滤重复或无关内容
                        if title in [section_name, '更多']:
                            continue
                        
                        # 补全URL
                        if url and not url.startswith('http'):
                            url = 'https://www.hupu.com' + url if url.startswith('/') else self.base_url + url
                        
                        # 跳过重复的URL
                        if url in seen_urls:
                            continue
                        seen_urls.add(url)
                        
                        # 获取排名（如果有）
                        rank_elem = item.find(['span', 'em'], class_=re.compile('rank|num|index'))
                        rank = item_count + 1
                        if rank_elem:
                            rank_text = rank_elem.get_text(strip=True)
                            if rank_text.isdigit():
                                rank = int(rank_text)
                        
                        # 提取摘要（如果有）
                        summary = title
                        desc_elem = item.find(['p', 'div'], class_=re.compile('desc|summary|intro|content'))
                        if desc_elem:
                            summary = desc_elem.get_text(strip=True)[:200]
                        
                        # 提取时间（如果有）
                        time_str = ''
                        time_elem = item.find(['span', 'time'], class_=re.compile('time|date'))
                        if time_elem:
                            time_str = time_elem.get_text(strip=True)
                        
                        # 提取热度值（如果有）并转换为数字
                        hot_value = 0.0
                        hot_elem = item.find(['span', 'em'], class_=re.compile('hot|count|num'))
                        if hot_elem:
                            hot_text = hot_elem.get_text(strip=True)
                            # 提取数字
                            numbers = re.findall(r'\d+', hot_text)
                            if numbers:
                                try:
                                    hot_value = float(numbers[0])
                                except:
                                    hot_value = 0.0
                        
                        result = {
                            'platform': self.platform,
                            'category': section_name,
                            'rank': rank,
                            'title': title,
                            'summary': summary,
                            'url': url,
                            'hot_value': hot_value,
                            'time': time_str,
                            'source': '虎扑',
                            'interactions': {},
                            'fetched_at': None
                        }
                        
                        results.append(result)
                        item_count += 1
                        print(f"获取{section_name}第{rank}条: {title[:50]}...")
                        
                    except Exception as e:
                        print(f"解析项失败: {e}")
                        continue
                
                print(f"{section_name}共获取 {item_count} 条数据")
            
            return results
            
        except Exception as e:
            print(f"从首页抓取失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
