# 知乎热榜爬虫
import os
import sys
import time
import random
from typing import List, Dict, Any

try:
    from .base import BaseScraper
except ImportError:  # pragma: no cover
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    from base import BaseScraper

class ZhihuScraper(BaseScraper):
    """知乎热榜爬虫"""
    
    def __init__(self):
        super().__init__(platform='zhihu')
        # 使用正确的知乎API端点
        self.api_url = 'https://api.zhihu.com/topstory/hot-lists/desktop'
        # 简化的请求头，基于成功案例
        self.headers.update({
            'Accept': 'application/json',
            'Referer': 'https://www.zhihu.com/hot',
        })
        
    def fetch_hot_list(self, limit: int = 30) -> List[Dict[str, Any]]:
        """
        抓取知乎热榜 - 使用正确的API端点
        """
        max_retries = 3
        retry_count = 0
        last_error = None
        
        while retry_count < max_retries:
            try:
                # 添加随机延迟避免被检测
                if retry_count > 0:
                    delay = random.uniform(1, 3)
                    print(f"等待 {delay:.1f} 秒后重试...")
                    time.sleep(delay)
                
                # 直接使用httpx请求
                import httpx
                
                # 创建新的headers，合并默认头部
                request_headers = self.headers.copy()
                request_headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Encoding': 'gzip, deflate',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Referer': 'https://www.zhihu.com/hot',
                    'Origin': 'https://www.zhihu.com',
                })
                
                with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                    response = client.get(self.api_url, headers=request_headers)
                    response.raise_for_status()
                    
                    # httpx 会自动根据 Content-Encoding 解压，这里直接解析 JSON
                    try:
                        data = response.json()
                    except Exception:
                        # 如果解析失败，记录部分响应内容用于调试
                        preview = response.text[:200]
                        raise ValueError(f"知乎响应JSON解析失败，响应前200字符: {preview}")
                
                # 检查API响应
                if 'error' in data:
                    error_msg = data['error'].get('message', '未知错误')
                    print(f"API错误: {error_msg}")
                    if retry_count < max_retries - 1:
                        retry_count += 1
                        continue
                    else:
                        raise Exception(f"API返回错误: {error_msg}")
                
                hot_list = data.get('data', [])
                
                if not hot_list:
                    print("未获取到热榜数据")
                    if retry_count < max_retries - 1:
                        retry_count += 1
                        continue
                    else:
                        raise Exception("未获取到热榜数据")
                
                results = []
                for item in hot_list[:limit]:
                    target = item.get('target', {})
                    title = target.get('title', '').strip()
                    
                    if not title:
                        continue
                    
                    # 提取关键字段
                    # 解析热度值（如"166万热度" -> 1660000）
                    hot_text = item.get('detail_text', '').replace('热度', '').strip()
                    hot_value = None
                    if hot_text:
                        try:
                            if '万' in hot_text:
                                hot_value = float(hot_text.replace('万', '')) * 10000
                            else:
                                hot_value = float(hot_text)
                        except:
                            hot_value = None
                    
                    result = {
                        'platform': self.platform,
                        'title': title,
                        'summary': target.get('excerpt', '').strip() or target.get('content', '').strip() or title,
                        'url': self._normalize_url(target),
                        'hot_value': hot_value,
                        'question_id': target.get('id', ''),
                        'type': target.get('type', 'question'),
                        'interactions': self._collect_interactions(target),
                        'fetched_at': self._resolve_datetime(
                            target.get('updated_time') or target.get('created') or target.get('published_time')
                        )
                    }
                    results.append(result)
                
                print(f"成功获取 {len(results)} 条知乎热榜数据")
                return results
                
            except Exception as e:
                last_error = e
                retry_count += 1
                print(f"知乎数据抓取失败 (尝试 {retry_count}/{max_retries}): {e}")
                
                if retry_count >= max_retries:
                    raise Exception(f"知乎数据抓取失败，已重试{max_retries}次: {last_error}")
        
        raise Exception(f"知乎数据抓取失败: {last_error}")
    
    def _normalize_url(self, target: Dict[str, Any]) -> str:
        """
        将API URL转换为公开URL
        """
        raw_url = target.get('url', '')
        target_type = target.get('type')
        target_id = target.get('id')
        
        if target_type == 'question' and target_id:
            return f'https://www.zhihu.com/question/{target_id}'
        
        if target_type in {'article', 'zvideo'} and target_id:
            prefix = 'zhuanlan.zhihu.com/p' if target_type == 'article' else 'www.zhihu.com/zvideo'
            return f'https://{prefix}/{target_id}'
        
        origin = target.get('origin', {})
        if isinstance(origin, dict):
            url = origin.get('url')
            if url:
                return url
        
        link = target.get('link')
        if isinstance(link, dict):
            url = link.get('url')
            if url:
                return url
        
        if raw_url:
            from urllib.parse import urlparse
            parsed = urlparse(raw_url)
            if parsed.netloc == 'api.zhihu.com':
                path_parts = [part for part in parsed.path.split('/') if part]
                if len(path_parts) >= 2:
                    resource, identifier = path_parts[0], path_parts[-1]
                    if resource == 'questions':
                        return f'https://www.zhihu.com/question/{identifier}'
                    if resource == 'articles':
                        return f'https://zhuanlan.zhihu.com/p/{identifier}'
            return raw_url
        
        return 'https://www.zhihu.com/hot'
    
    def _resolve_datetime(self, timestamp: Any) -> str:
        """
        解析时间戳为可读格式
        """
        try:
            if timestamp:
                from datetime import datetime
                return datetime.fromtimestamp(int(timestamp)).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
        return ''
    
    def _collect_interactions(self, target: Dict[str, Any]) -> Dict[str, Any]:
        """
        收集互动数据
        """
        metrics = {}
        for key in ('answer_count', 'follower_count', 'comment_count', 'hot_value', 'voteup_count'):
            value = target.get(key)
            if value:
                metrics[key] = value
        return metrics
    
    
    def _parse_hot_list_html(self, html_content: str, limit: int) -> List[Dict[str, Any]]:
        """
        解析知乎热榜HTML内容
        """
        try:
            from bs4 import BeautifulSoup
            import re
            
            soup = BeautifulSoup(html_content, 'html.parser')
            results = []
            
            # 尝试多种选择器来找到热榜项目
            selectors = [
                '.HotItem',
                '.HotList-item',
                '.HotList-itemContainer',
                '[data-za-detail-view-element_name="HotItem"]',
                '.css-1yuhvjn'
            ]
            
            hot_items = []
            for selector in selectors:
                items = soup.select(selector)
                if items:
                    hot_items = items
                    print(f"使用选择器 '{selector}' 找到 {len(items)} 个热榜项目")
                    break
            
            if not hot_items:
                # 如果没找到，尝试查找包含热榜数据的script标签
                script_tags = soup.find_all('script')
                for script in script_tags:
                    if script.string and 'HotList' in script.string:
                        # 尝试从script中提取JSON数据
                        json_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', script.string)
                        if json_match:
                            try:
                                import json
                                data = json.loads(json_match.group(1))
                                # 解析JSON数据
                                return self._parse_json_data(data, limit)
                            except:
                                continue
            
            # 解析HTML元素
            for idx, item in enumerate(hot_items[:limit]):
                try:
                    # 提取标题
                    title_elem = item.find(['h2', 'h3', '.HotItem-title', '.HotList-itemTitle'])
                    title = title_elem.get_text(strip=True) if title_elem else f"热榜项目 {idx+1}"
                    
                    # 提取链接
                    link_elem = item.find('a')
                    url = link_elem.get('href', '') if link_elem else ''
                    if url and not url.startswith('http'):
                        url = 'https://www.zhihu.com' + url
                    
                    # 提取热度值
                    hot_elem = item.find(['.HotItem-metrics', '.HotList-itemMetrics', '.HotItem-index'])
                    hot_value = hot_elem.get_text(strip=True) if hot_elem else ''
                    
                    # 提取摘要
                    summary_elem = item.find(['.HotItem-excerpt', '.HotList-itemExcerpt', 'p'])
                    summary = summary_elem.get_text(strip=True) if summary_elem else title
                    
                    result = {
                        'platform': self.platform,
                        'title': title,
                        'summary': summary,
                        'url': url,
                        'hot_value': hot_value,
                        'question_id': '',
                        'type': 'question',
                        'interactions': {
                            'answer_count': 0,
                            'comment_count': 0,
                            'follower_count': 0,
                        },
                        'fetched_at': None
                    }
                    results.append(result)
                    
                except Exception as e:
                    print(f"解析第 {idx+1} 个项目时出错: {e}")
                    continue
            
            return results
            
        except Exception as e:
            print(f"HTML解析失败: {e}")
            return []
    
    def _parse_json_data(self, data: dict, limit: int) -> List[Dict[str, Any]]:
        """
        从JSON数据中解析热榜信息
        """
        results = []
        try:
            # 尝试不同的JSON路径
            hot_lists = []
            if 'topstory' in data:
                hot_lists = data['topstory'].get('hotList', [])
            elif 'hotList' in data:
                hot_lists = data['hotList']
            
            for idx, item in enumerate(hot_lists[:limit]):
                try:
                    target = item.get('target', {})
                    result = {
                        'platform': self.platform,
                        'title': target.get('title', f"热榜项目 {idx+1}"),
                        'summary': target.get('excerpt', target.get('title', '')),
                        'url': target.get('url', ''),
                        'hot_value': item.get('detail_text', ''),
                        'question_id': target.get('id', ''),
                        'type': target.get('type', 'question'),
                        'interactions': {
                            'answer_count': target.get('answer_count', 0),
                            'comment_count': target.get('comment_count', 0),
                            'follower_count': target.get('follower_count', 0),
                        },
                        'fetched_at': None
                    }
                    results.append(result)
                except Exception as e:
                    print(f"解析JSON项目 {idx+1} 时出错: {e}")
                    continue
                    
        except Exception as e:
            print(f"JSON解析失败: {e}")
            
        return results


def main() -> None:
    """运行知乎热榜爬虫"""
    scraper = ZhihuScraper()
    results = scraper.fetch_hot_list()
    for item in results:
        print(f"{item['title']}\t{item['url']}")


if __name__ == "__main__":
    main()
