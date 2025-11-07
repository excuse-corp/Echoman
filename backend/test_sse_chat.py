#!/usr/bin/env python3
"""
SSE流式对话测试脚本

测试 POST /api/v1/chat/ask 的流式输出功能
"""
import asyncio
import httpx
import json


async def test_sse_stream():
    """测试SSE流式对话"""
    
    url = "http://localhost:8000/api/v1/chat/ask"
    
    # 测试请求
    payload = {
        "query": "请简单介绍一下最近的热点新闻",
        "mode": "global",
        "stream": True
    }
    
    print("🚀 开始测试SSE流式对话")
    print(f"📝 请求: {payload}\n")
    print("📨 接收流式响应:\n")
    print("-" * 60)
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", url, json=payload) as response:
            if response.status_code != 200:
                print(f"❌ 请求失败: {response.status_code}")
                print(await response.aread())
                return
            
            full_answer = ""
            citations = []
            diagnostics = {}
            
            async for line in response.aiter_lines():
                line = line.strip()
                
                # 跳过空行
                if not line:
                    continue
                
                # 解析SSE格式：event: <type>\ndata: <json>
                if line.startswith("event: "):
                    event_type = line[7:].strip()
                    continue
                
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    
                    try:
                        data = json.loads(data_str)
                        
                        # 处理不同类型的事件
                        if 'content' in data:
                            # token事件
                            content = data['content']
                            full_answer += content
                            print(content, end='', flush=True)
                        
                        elif 'citations' in data:
                            # citations事件
                            citations = data['citations']
                        
                        elif 'diagnostics' in data:
                            # done事件
                            diagnostics = data['diagnostics']
                        
                        elif 'message' in data:
                            # error事件
                            print(f"\n\n❌ 错误: {data['message']}")
                            return
                    
                    except json.JSONDecodeError as e:
                        print(f"\n⚠️  JSON解析错误: {e}")
                        continue
            
            # 输出统计信息
            print("\n")
            print("-" * 60)
            print("\n📊 响应统计:")
            print(f"  - 总字符数: {len(full_answer)}")
            print(f"  - 引用数量: {len(citations)}")
            if diagnostics:
                print(f"  - 延迟: {diagnostics.get('latency_ms', 0)}ms")
                print(f"  - Prompt Tokens: {diagnostics.get('tokens_prompt', 0)}")
                print(f"  - Completion Tokens: {diagnostics.get('tokens_completion', 0)}")
                print(f"  - 上下文块: {diagnostics.get('context_chunks', 0)}")
            
            if citations:
                print(f"\n📚 引用来源:")
                for i, cite in enumerate(citations[:3], 1):  # 只显示前3个
                    print(f"  {i}. [{cite.get('platform', '未知')}] {cite.get('snippet', '')[:50]}...")
                if len(citations) > 3:
                    print(f"  ... 还有 {len(citations) - 3} 个引用")
            
            print("\n✅ 测试完成!")


async def test_non_stream():
    """测试非流式对话（对比）"""
    
    url = "http://localhost:8000/api/v1/chat/ask"
    
    payload = {
        "query": "请简单介绍一下最近的热点新闻",
        "mode": "global",
        "stream": False
    }
    
    print("\n\n🚀 开始测试非流式对话（对比）")
    print(f"📝 请求: {payload}\n")
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload)
        
        if response.status_code != 200:
            print(f"❌ 请求失败: {response.status_code}")
            print(response.text)
            return
        
        data = response.json()
        
        print("📨 响应:")
        print("-" * 60)
        print(f"回答: {data.get('answer', '')}\n")
        
        print("📊 统计:")
        diagnostics = data.get('diagnostics', {})
        print(f"  - 延迟: {diagnostics.get('latency_ms', 0)}ms")
        print(f"  - Tokens: {diagnostics.get('tokens_prompt', 0)} + {diagnostics.get('tokens_completion', 0)}")
        print(f"  - 引用: {len(data.get('citations', []))}")
        
        print("\n✅ 测试完成!")


async def main():
    """主函数"""
    print("=" * 60)
    print("  SSE流式对话测试")
    print("=" * 60)
    print()
    
    # 测试流式输出
    await test_sse_stream()
    
    # 测试非流式输出（对比）
    await test_non_stream()
    
    print("\n" + "=" * 60)
    print("  所有测试完成")
    print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被中断")
    except Exception as e:
        print(f"\n\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

