# 基础爬虫类
import time
import json
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.utils.timezone import now_cn

class BaseScraper(ABC):
    """所有平台爬虫的基类"""
    
    def __init__(self, platform: str, timeout: int = 10):
        self.platform = platform
        self.timeout = timeout
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        
    @abstractmethod
    def fetch_hot_list(self, limit: int = 30) -> List[Dict[str, Any]]:
        """
        抓取热榜数据
        
        Args:
            limit: 抓取条数限制
            
        Returns:
            包含热点数据的列表
        """
        pass
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _make_request(self, url: str, method: str = 'GET', **kwargs) -> httpx.Response:
        """
        发起HTTP请求，带重试机制
        
        Args:
            url: 请求URL
            method: HTTP方法
            **kwargs: 其他请求参数
            
        Returns:
            响应对象
        """
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            if method.upper() == 'GET':
                response = client.get(url, headers=self.headers, **kwargs)
            else:
                response = client.post(url, headers=self.headers, **kwargs)
            response.raise_for_status()
            return response
    
    def save_to_txt(self, data: List[Dict[str, Any]], output_path: str):
        """
        保存数据到txt文件
        
        Args:
            data: 要保存的数据
            output_path: 输出文件路径
        """
        timestamp = now_cn().strftime('%Y-%m-%d %H:%M:%S')
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"{'='*80}\n")
            f.write(f"平台: {self.platform}\n")
            f.write(f"抓取时间: {timestamp}\n")
            f.write(f"数据条数: {len(data)}\n")
            f.write(f"{'='*80}\n\n")
            
            for idx, item in enumerate(data, 1):
                f.write(f"[{idx}] {'-'*70}\n")
                for key, value in item.items():
                    if isinstance(value, dict):
                        f.write(f"{key}:\n")
                        for sub_key, sub_value in value.items():
                            f.write(f"  {sub_key}: {sub_value}\n")
                    else:
                        f.write(f"{key}: {value}\n")
                f.write('\n')
        
        print(f"✓ 数据已保存到: {output_path}")
    
    def run(self, limit: int = 30, output_dir: str = 'backend/output') -> List[Dict[str, Any]]:
        """
        运行爬虫并保存结果
        
        Args:
            limit: 抓取条数
            output_dir: 输出目录
            
        Returns:
            抓取到的数据列表
        """
        import os
        os.makedirs(output_dir, exist_ok=True)
        
        start_time = time.time()
        
        try:
            print(f"\n{'='*80}")
            print(f"开始抓取 {self.platform} 数据...")
            print(f"{'='*80}")
            
            data = self.fetch_hot_list(limit)
            
            if data:
                output_path = os.path.join(output_dir, f'{self.platform}_{now_cn().strftime("%Y%m%d_%H%M%S")}.txt')
                self.save_to_txt(data, output_path)
                
                print(f"✓ 成功抓取 {len(data)} 条数据")
            else:
                print(f"✗ 未获取到数据")
                data = []
                
        except Exception as e:
            print(f"✗ 抓取失败: {e}")
            data = []
        
        finally:
            duration_ms = int((time.time() - start_time) * 1000)
            print(f"耗时: {duration_ms}ms\n")
            
        return data
