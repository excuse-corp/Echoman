"""
向量数据库服务

提供统一的向量存储和检索接口，支持Chroma等向量数据库
"""
import os
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import numpy as np

from app.config import settings


class VectorService:
    """向量数据库服务"""
    
    def __init__(self):
        """初始化向量服务"""
        self.db_type = settings.vector_db_type
        self.client = None
        self.collection = None
        
        if self.db_type == "chroma":
            self._init_chroma()
    
    def _init_chroma(self):
        """初始化Chroma客户端"""
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            
            # 确保持久化目录存在
            persist_dir = Path(settings.chroma_persist_directory)
            persist_dir.mkdir(parents=True, exist_ok=True)
            
            # 创建Chroma客户端（持久化模式）
            self.client = chromadb.PersistentClient(
                path=str(persist_dir),
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # 获取或创建集合
            self.collection = self.client.get_or_create_collection(
                name=settings.chroma_collection_name,
                metadata={"description": "Echoman事件向量嵌入"}
            )
            
            print(f"✅ Chroma向量数据库已初始化: {persist_dir}")
            print(f"   集合: {settings.chroma_collection_name}")
            print(f"   当前向量数: {self.collection.count()}")
            
        except Exception as e:
            print(f"⚠️  Chroma初始化失败: {e}")
            print("   将回退到PostgreSQL存储")
            self.db_type = "postgres"
            self.client = None
            self.collection = None
    
    def add_embeddings(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        documents: Optional[List[str]] = None
    ) -> bool:
        """
        添加向量到数据库
        
        Args:
            ids: 向量ID列表
            embeddings: 向量列表
            metadatas: 元数据列表
            documents: 文档内容列表（可选）
            
        Returns:
            是否成功
        """
        if self.db_type != "chroma" or not self.collection:
            return False
        
        try:
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents
            )
            return True
        except Exception as e:
            print(f"❌ Chroma添加向量失败: {e}")
            return False
    
    def search_similar(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        where: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[str], List[float], List[Dict[str, Any]]]:
        """
        搜索相似向量
        
        Args:
            query_embedding: 查询向量
            top_k: 返回数量
            where: 过滤条件
            
        Returns:
            (ids, distances, metadatas)
        """
        if self.db_type != "chroma" or not self.collection:
            return [], [], []
        
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where
            )
            
            if results and results['ids'] and len(results['ids']) > 0:
                ids = results['ids'][0]
                distances = results['distances'][0]
                metadatas = results['metadatas'][0] if results['metadatas'] else []
                
                return ids, distances, metadatas
            
            return [], [], []
            
        except Exception as e:
            print(f"❌ Chroma搜索失败: {e}")
            return [], [], []
    
    def delete_by_ids(self, ids: List[str]) -> bool:
        """
        根据ID删除向量
        
        Args:
            ids: 要删除的ID列表
            
        Returns:
            是否成功
        """
        if self.db_type != "chroma" or not self.collection:
            return False
        
        try:
            self.collection.delete(ids=ids)
            return True
        except Exception as e:
            print(f"❌ Chroma删除向量失败: {e}")
            return False
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """
        获取集合统计信息
        
        Returns:
            统计信息字典
        """
        if self.db_type != "chroma" or not self.collection:
            return {"type": self.db_type, "count": 0}
        
        try:
            return {
                "type": "chroma",
                "name": settings.chroma_collection_name,
                "count": self.collection.count(),
                "persist_directory": settings.chroma_persist_directory
            }
        except Exception as e:
            print(f"❌ 获取Chroma统计信息失败: {e}")
            return {"type": "chroma", "error": str(e)}
    
    def reset_collection(self) -> bool:
        """
        重置集合（删除所有数据）
        
        Returns:
            是否成功
        """
        if self.db_type != "chroma" or not self.client:
            return False
        
        try:
            # 删除现有集合
            self.client.delete_collection(name=settings.chroma_collection_name)
            
            # 重新创建集合
            self.collection = self.client.create_collection(
                name=settings.chroma_collection_name,
                metadata={"description": "Echoman事件向量嵌入"}
            )
            
            print(f"✅ Chroma集合已重置: {settings.chroma_collection_name}")
            return True
            
        except Exception as e:
            print(f"❌ Chroma集合重置失败: {e}")
            return False


# 全局向量服务实例（延迟初始化）
_vector_service_instance: Optional[VectorService] = None


def get_vector_service() -> VectorService:
    """
    获取全局向量服务实例
    
    Returns:
        VectorService实例
    """
    global _vector_service_instance
    
    if _vector_service_instance is None:
        _vector_service_instance = VectorService()
    
    return _vector_service_instance

