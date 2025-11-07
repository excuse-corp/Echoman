#!/usr/bin/env python3
"""
Token Manager 测试脚本

测试 TokenManager 的各项功能
"""
import sys
sys.path.insert(0, '/root/ren/Echoman/backend')

from app.utils.token_manager import TokenManager, estimate_tokens_simple


def test_token_counting():
    """测试 Token 计数"""
    print("=" * 60)
    print("测试 1: Token 计数")
    print("=" * 60)
    
    tm = TokenManager(model="qwen3-32b")
    
    texts = [
        "Hello World",
        "你好世界",
        "This is a test 这是一个测试",
        "A" * 1000,
        "中" * 1000,
    ]
    
    for text in texts:
        token_count = tm.count_tokens(text)
        simple_estimate = estimate_tokens_simple(text)
        
        print(f"\n文本: {text[:50]}{'...' if len(text) > 50 else ''}")
        print(f"  长度: {len(text)} 字符")
        print(f"  精确计数: {token_count} tokens")
        print(f"  简单估算: {simple_estimate} tokens")
        print(f"  差异: {abs(token_count - simple_estimate)} tokens")


def test_text_truncation():
    """测试文本截断"""
    print("\n" + "=" * 60)
    print("测试 2: 文本截断")
    print("=" * 60)
    
    tm = TokenManager(model="qwen3-32b")
    
    long_text = "这是一段很长的文本。" * 100
    
    print(f"\n原始文本: {len(long_text)} 字符")
    print(f"原始tokens: {tm.count_tokens(long_text)}")
    
    # 截断到 100 tokens
    truncated = tm.truncate_text(long_text, max_tokens=100, keep_start=True)
    
    print(f"\n截断后文本: {len(truncated)} 字符")
    print(f"截断后tokens: {tm.count_tokens(truncated)}")
    print(f"截断内容预览: {truncated[:100]}...")


def test_context_optimization():
    """测试上下文优化"""
    print("\n" + "=" * 60)
    print("测试 3: RAG 上下文优化")
    print("=" * 60)
    
    tm = TokenManager(model="qwen3-32b")
    
    # 模拟检索结果
    context_chunks = [
        {"id": 1, "content": "新闻1: " + "这是第一条新闻的内容。" * 50},
        {"id": 2, "content": "新闻2: " + "这是第二条新闻的内容。" * 50},
        {"id": 3, "content": "新闻3: " + "这是第三条新闻的内容。" * 50},
        {"id": 4, "content": "新闻4: " + "这是第四条新闻的内容。" * 50},
        {"id": 5, "content": "新闻5: " + "这是第五条新闻的内容。" * 50},
    ]
    
    query = "最近有什么热点新闻？"
    system_prompt = "你是一个新闻助手，根据提供的新闻内容回答用户问题。"
    
    print(f"\n查询: {query}")
    print(f"系统Prompt: {system_prompt}")
    print(f"原始块数: {len(context_chunks)}")
    print(f"原始总tokens: {sum(tm.count_tokens(c['content']) for c in context_chunks)}")
    
    # 优化上下文
    optimized_chunks, stats = tm.optimize_rag_context(
        query=query,
        context_chunks=context_chunks,
        system_prompt_template=system_prompt,
        max_completion_tokens=2000
    )
    
    print(f"\n优化后块数: {len(optimized_chunks)}")
    print(f"优化后总tokens: {sum(tm.count_tokens(c['content']) for c in optimized_chunks)}")
    
    print("\nToken 统计:")
    for key, value in stats.items():
        print(f"  {key}: {value}")


def test_available_tokens():
    """测试可用 Token 计算"""
    print("\n" + "=" * 60)
    print("测试 4: 可用 Token 计算")
    print("=" * 60)
    
    tm = TokenManager(model="qwen3-32b")
    
    scenarios = [
        {
            "name": "简单问答",
            "system_prompt": "你是一个助手。",
            "query": "今天天气怎么样？",
            "max_completion": 500
        },
        {
            "name": "RAG对话",
            "system_prompt": "你是一个基于检索的问答助手。请根据提供的上下文回答问题。",
            "query": "请详细解释一下相关内容，并给出你的分析。",
            "max_completion": 2000
        },
        {
            "name": "长文本生成",
            "system_prompt": "你是一个文章生成助手。",
            "query": "请写一篇关于人工智能发展的文章。",
            "max_completion": 8000
        }
    ]
    
    for scenario in scenarios:
        available = tm.calculate_available_context_tokens(
            system_prompt=scenario["system_prompt"],
            user_query=scenario["query"],
            max_completion_tokens=scenario["max_completion"]
        )
        
        print(f"\n场景: {scenario['name']}")
        print(f"  系统Prompt tokens: {tm.count_tokens(scenario['system_prompt'])}")
        print(f"  查询 tokens: {tm.count_tokens(scenario['query'])}")
        print(f"  预留生成 tokens: {scenario['max_completion']}")
        print(f"  可用上下文 tokens: {available}")
        print(f"  占比: {available / tm.context_limit * 100:.1f}%")


def test_model_limits():
    """测试不同模型的限制"""
    print("\n" + "=" * 60)
    print("测试 5: 不同模型的上下文限制")
    print("=" * 60)
    
    models = [
        "qwen3-32b",
        "gpt-4",
        "gpt-4o",
        "claude-3-opus"
    ]
    
    for model in models:
        tm = TokenManager(model=model)
        print(f"\n模型: {model}")
        print(f"  上下文限制: {tm.context_limit:,} tokens")
        print(f"  安全边界: {tm.SAFETY_MARGIN:,} tokens")
        print(f"  可用上下文: {tm.context_limit - tm.SAFETY_MARGIN:,} tokens")


def main():
    """运行所有测试"""
    print("\n" + "🧪 " * 20)
    print("Token Manager 功能测试")
    print("🧪 " * 20)
    
    try:
        test_token_counting()
        test_text_truncation()
        test_context_optimization()
        test_available_tokens()
        test_model_limits()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试完成")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

