#!/usr/bin/env python3
"""
测试SSE流式对话功能
"""
import httpx
import asyncio
import json


async def test_sse_stream():
    """测试SSE流式对话"""
    url = "http://localhost:8778/api/v1/chat/ask"
    
    payload = {
        "query": "最近有什么热点新闻？",
        "mode": "global",
        "stream": True
    }
    
    print("🚀 开始测试SSE流式对话...")
    print(f"📤 请求: {json.dumps(payload, ensure_ascii=False)}")
    print("-" * 60)
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    print(f"❌ 错误: HTTP {response.status_code}")
                    print(await response.aread())
                    return
                
                print("✅ 连接成功，开始接收事件流...\n")
                
                event_type = None
                full_answer = ""
                
                async for line in response.aiter_lines():
                    line = line.strip()
                    
                    # 跳过空行
                    if not line:
                        continue
                    
                    # 解析event类型
                    if line.startswith("event:"):
                        event_type = line.split(":", 1)[1].strip()
                        continue
                    
                    # 解析data
                    if line.startswith("data:"):
                        data_str = line.split(":", 1)[1].strip()
                        
                        try:
                            data = json.loads(data_str)
                            
                            if event_type == "token":
                                content = data.get("content", "")
                                full_answer += content
                                print(content, end="", flush=True)
                            
                            elif event_type == "citations":
                                print("\n\n📚 引用来源:")
                                citations = data.get("citations", [])
                                for i, cite in enumerate(citations, 1):
                                    print(f"  [{i}] {cite.get('platform', 'unknown')}: {cite.get('source_url', '')}")
                                    print(f"      {cite.get('snippet', '')[:100]}...")
                            
                            elif event_type == "done":
                                print("\n\n✅ 完成!")
                                diagnostics = data.get("diagnostics", {})
                                print(f"⏱️  延迟: {diagnostics.get('latency_ms', 0)}ms")
                                print(f"📊 Token (prompt): {diagnostics.get('tokens_prompt', 0)}")
                                print(f"📊 Token (completion): {diagnostics.get('tokens_completion', 0)}")
                                print(f"📄 使用的上下文块: {diagnostics.get('context_chunks', 0)}")
                            
                            elif event_type == "error":
                                print(f"\n\n❌ 错误: {data.get('message', 'Unknown error')}")
                        
                        except json.JSONDecodeError as e:
                            print(f"\n⚠️  无法解析JSON: {data_str}")
                
                print("\n" + "-" * 60)
                print(f"📝 完整回答长度: {len(full_answer)} 字符")
    
    except httpx.RequestError as e:
        print(f"❌ 请求失败: {e}")
    except Exception as e:
        print(f"❌ 未知错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("=" * 60)
    print("  SSE流式对话测试")
    print("=" * 60)
    print()
    
    asyncio.run(test_sse_stream())

