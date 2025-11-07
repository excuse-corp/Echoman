# 网易新闻热榜爬虫
import re
import time
import random
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from .base import BaseScraper

class NeteaseScraper(BaseScraper):
    """
    网易新闻热榜爬虫
    从网易新闻首页抓取"热点排行"栏目
    
    @class NeteaseScraper
    @extends BaseScraper
    """
    
    def __init__(self):
        """
        初始化网易新闻爬虫
        """
        super().__init__(platform='netease')
        
        # 网易新闻首页
        self.base_url = 'https://news.163.com/'
        
        # 更新请求头
        self.headers.update({
            'Referer': 'https://news.163.com/',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        
    def fetch_hot_list(self, limit: int = 30) -> List[Dict[str, Any]]:
        """
        抓取网易新闻热榜
        
        @param {int} limit - 抓取条数限制，默认30
        @returns {List[Dict[str, Any]]} 热榜数据列表
        
        说明：
        - 从网易新闻首页抓取"热点排行"栏目
        - 获取标题、链接、热度值
        - 访问详情页获取摘要和发布时间
        """
        try:
            print(f"正在抓取网易新闻首页热点排行...")
            response = self._make_request(self.base_url)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找热点排行区域
            hot_rank_div = soup.select_one('div.mod_hot_rank')
            
            if not hot_rank_div:
                print("未找到热点排行区域")
                return []
            
            # 获取所有热点排行项
            items = hot_rank_div.find_all('li')
            print(f"找到 {len(items)} 个热点排行项")
            
            results = []
            for item in items[:limit]:
                try:
                    # 获取排名
                    em_element = item.find('em')
                    rank = int(em_element.get_text(strip=True)) if em_element else len(results) + 1
                    
                    # 获取标题和链接
                    a_element = item.find('a')
                    if not a_element:
                        continue
                    
                    title = a_element.get('title', '').strip()
                    if not title:
                        title = a_element.get_text(strip=True)
                    
                    if not title:
                        continue
                    
                    url = a_element.get('href', '').strip()
                    if not url:
                        continue
                    
                    # 获取热度值并转换为数字
                    span_element = item.find('span')
                    hot_value_str = span_element.get_text(strip=True) if span_element else '0'
                    try:
                        # 移除非数字字符，只保留数字
                        hot_value_clean = re.sub(r'[^\d]', '', hot_value_str)
                        hot_value = float(hot_value_clean) if hot_value_clean else 0.0
                    except:
                        hot_value = 0.0
                    
                    print(f"正在处理第 {rank} 条: {title[:30]}...")
                    
                    # 访问详情页获取更多信息
                    summary, publish_time = self._fetch_article_details(url)
                    
                    result = {
                        'platform': self.platform,
                        'rank': rank,
                        'title': title,
                        'summary': summary if summary else title,
                        'url': url,
                        'doc_id': self._extract_doc_id(url),
                        'publish_time': publish_time,
                        'source': '网易新闻',
                        'image_url': '',
                        'hot_value': hot_value,
                        'interactions': {
                            'reply_count': 0,
                            'vote_count': 0,
                        },
                        'fetched_at': None
                    }
                    
                    results.append(result)
                    print(f"✓ 成功获取第 {rank} 条数据")
                    
                    # 添加随机延迟避免请求过快
                    time.sleep(random.uniform(0.5, 1.5))
                    
                except Exception as e:
                    print(f"处理热点排行项失败: {e}")
                    continue
            
            print(f"成功获取 {len(results)} 条网易新闻热榜数据")
            return results
            
        except Exception as e:
            print(f"抓取网易新闻热榜失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _fetch_article_details(self, url: str) -> tuple:
        """
        获取文章详情（摘要和发布时间）
        
        @param {str} url - 文章URL
        @returns {tuple} (摘要, 发布时间)
        """
        try:
            response = self._make_request(url)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 获取发布时间
            publish_time = ''
            
            # 尝试从meta标签获取
            meta_time = soup.select_one('meta[property="article:published_time"]')
            if meta_time:
                publish_time = meta_time.get('content', '')
            
            # 尝试从页面元素获取
            if not publish_time:
                post_info = soup.select_one('div.post_info')
                if post_info:
                    time_text = post_info.get_text(strip=True)
                    # 提取时间部分 (格式: 2025-10-29 01:42:44)
                    time_match = re.search(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}', time_text)
                    if time_match:
                        publish_time = time_match.group(0)
            
            # 获取摘要/正文
            summary = ''
            
            # 尝试从正文获取前200字作为摘要
            post_body = soup.select_one('div.post_body')
            if post_body:
                # 移除脚本和样式标签
                for tag in post_body.find_all(['script', 'style']):
                    tag.decompose()
                
                text = post_body.get_text(strip=True)
                # 清理文本
                text = re.sub(r'\s+', ' ', text)
                text = re.sub(r'（原标题：.*?）', '', text)
                text = re.sub(r'分享至.*?朋友圈', '', text)
                
                # 取前200个字符作为摘要
                summary = text[:200].strip()
            
            # 如果没有获取到正文，尝试其他选择器
            if not summary:
                content_div = soup.select_one('div#content')
                if content_div:
                    text = content_div.get_text(strip=True)
                    text = re.sub(r'\s+', ' ', text)
                    text = re.sub(r'（原标题：.*?）', '', text)
                    summary = text[:200].strip()
            
            return summary, publish_time
            
        except Exception as e:
            print(f"获取文章详情失败 {url}: {e}")
            return '', ''
    
    def _extract_doc_id(self, url: str) -> str:
        """
        从URL中提取文档ID
        
        @param {str} url - 文章URL
        @returns {str} 文档ID
        """
        try:
            # 从URL中提取文档ID
            # 例如: https://www.163.com/news/article/KD0J0TVP0001899O.html
            match = re.search(r'/article/([A-Z0-9]+)\.html', url)
            if match:
                return match.group(1)
            
            # 视频URL格式
            # 例如: https://www.163.com/v/video/VOC18BSGS.html
            match = re.search(r'/video/([A-Z0-9]+)\.html', url)
            if match:
                return match.group(1)
            
            return ''
        except Exception:
            return ''
