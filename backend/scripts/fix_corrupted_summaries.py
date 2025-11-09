"""
修复数据库中损坏的摘要

问题类型：
1. 摘要保存了完整的JSON字符串（如 {"summary": "...", "key_points": [...]}）
2. 摘要被截断（不完整的JSON或文本）

解决方案：
1. 提取JSON中的summary字段
2. 移除JSON格式标记
3. 清理转义字符
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import json
import re
from sqlalchemy import select, text, update, func
from app.core.database import get_async_session
from app.models.summary import Summary
from app.models.topic import Topic


async def identify_corrupted_summaries():
    """识别损坏的摘要"""
    async_session = get_async_session()
    async with async_session() as db:
        print("=" * 120)
        print("第1步：识别损坏的摘要")
        print("=" * 120)
        
        # 类型1：包含JSON格式字符的摘要
        result = await db.execute(
            select(func.count(Summary.id)).where(
                Summary.content.like('{%"summary"%')
            )
        )
        json_format_count = result.scalar()
        
        # 类型2：特别短的摘要（可能被截断）
        result = await db.execute(
            select(func.count(Summary.id)).where(
                func.length(Summary.content) < 100,
                Summary.method == 'full'  # 只统计full类型，placeholder除外
            )
        )
        truncated_count = result.scalar()
        
        # 类型3：以不完整JSON结尾的摘要（没有闭合的引号或大括号）
        result = await db.execute(
            text('''
                SELECT COUNT(*) 
                FROM summaries 
                WHERE content LIKE '{%"summary"%'
                AND content NOT LIKE '%}'
            ''')
        )
        incomplete_json_count = result.scalar()
        
        print(f"\n📊 损坏摘要统计:")
        print(f"   - JSON格式摘要: {json_format_count} 个")
        print(f"   - 过短摘要（<100字符）: {truncated_count} 个")
        print(f"   - 不完整JSON摘要: {incomplete_json_count} 个")
        print(f"   - 预计需修复: {json_format_count + incomplete_json_count} 个")
        
        return json_format_count + incomplete_json_count


async def fix_corrupted_summaries(dry_run: bool = True):
    """修复损坏的摘要"""
    async_session = get_async_session()
    async with async_session() as db:
        print("\n" + "=" * 120)
        print(f"第2步：修复损坏的摘要 {'（预览模式）' if dry_run else '（执行模式）'}")
        print("=" * 120)
        
        # 获取所有包含JSON格式字符的摘要
        result = await db.execute(
            select(Summary, Topic).join(
                Topic, Summary.topic_id == Topic.id
            ).where(
                Summary.content.like('{%"summary"%')
            ).order_by(Summary.id)
        )
        summaries = result.all()
        
        if not summaries:
            print("✅ 没有发现需要修复的摘要")
            return
        
        print(f"\n找到 {len(summaries)} 个需要修复的摘要\n")
        
        fixed_count = 0
        failed_count = 0
        
        for summary, topic in summaries:
            print(f"【Summary {summary.id}】Topic {topic.id}: {topic.title_key}")
            print(f"   原内容（前200字符）: {summary.content[:200]}...")
            
            # 尝试修复
            fixed_content = extract_summary_from_json(summary.content)
            
            if fixed_content and fixed_content != summary.content:
                print(f"   ✅ 修复后（前200字符）: {fixed_content[:200]}...")
                print(f"   📏 原长度: {len(summary.content)} → 修复后长度: {len(fixed_content)}")
                
                if not dry_run:
                    # 更新数据库
                    await db.execute(
                        update(Summary).where(
                            Summary.id == summary.id
                        ).values(
                            content=fixed_content
                        )
                    )
                    fixed_count += 1
                else:
                    fixed_count += 1
            else:
                print(f"   ❌ 无法自动修复，可能需要重新生成")
                failed_count += 1
            
            print("-" * 120)
        
        if not dry_run:
            await db.commit()
            print(f"\n✅ 已修复 {fixed_count} 个摘要")
        else:
            print(f"\n📋 预览完成，将修复 {fixed_count} 个摘要")
        
        if failed_count > 0:
            print(f"⚠️  {failed_count} 个摘要无法自动修复，建议重新生成")
        
        return fixed_count, failed_count


def extract_summary_from_json(content: str) -> str:
    """
    从JSON格式的内容中提取纯文本摘要
    
    处理三种情况：
    1. 完整的JSON：{"summary": "...", "key_points": [...]}
    2. 不完整的JSON：{"summary": "...（没有闭合）
    3. 已经是纯文本但包含JSON片段
    """
    # 情况1：尝试解析完整的JSON
    try:
        data = json.loads(content)
        if isinstance(data, dict) and "summary" in data:
            summary_text = data["summary"]
            if isinstance(summary_text, str):
                return summary_text.strip()
    except json.JSONDecodeError:
        pass
    
    # 情况2：使用正则提取summary字段（处理不完整的JSON）
    # 匹配 "summary": "..." 中的内容（支持跨行，支持内部引号）
    summary_match = re.search(
        r'"summary"\s*:\s*"((?:[^"\\]|\\.|"(?:[^"\\]|\\.)*")*)"',
        content,
        re.DOTALL
    )
    
    if summary_match:
        extracted = summary_match.group(1)
        # 处理转义字符
        extracted = extracted.replace('\\"', '"')
        extracted = extracted.replace('\\n', '\n')
        extracted = extracted.replace('\\t', '\t')
        extracted = extracted.strip()
        
        # 验证提取的内容是否合理
        if len(extracted) > 50:  # 至少50个字符才算有效
            return extracted
    
    # 情况3：使用更宽松的正则，移除JSON标记
    # 移除开头的 {"summary": "
    clean_text = re.sub(r'^\s*\{\s*"summary"\s*:\s*"', '', content)
    # 移除结尾的 ", "key_points": ... } （如果存在）
    clean_text = re.sub(r'"\s*,\s*"key_points".*$', '', clean_text, flags=re.DOTALL)
    # 移除孤立的结尾引号和大括号
    clean_text = re.sub(r'"\s*[,}]?\s*$', '', clean_text)
    
    clean_text = clean_text.strip()
    
    # 如果清理后的文本明显比原文短且长度合理，返回清理后的文本
    if len(clean_text) >= 50 and len(clean_text) < len(content):
        return clean_text
    
    # 如果都失败了，返回原文（让调用方决定是否需要重新生成）
    return content


async def mark_for_regeneration():
    """标记无法修复的摘要，建议重新生成"""
    async_session = get_async_session()
    async with async_session() as db:
        print("\n" + "=" * 120)
        print("第3步：统计需要重新生成的摘要")
        print("=" * 120)
        
        # 找出仍然包含JSON标记的摘要（修复失败的）
        result = await db.execute(
            select(Summary, Topic).join(
                Topic, Summary.topic_id == Topic.id
            ).where(
                Summary.content.like('{%"summary"%')
            ).order_by(Summary.id)
        )
        needs_regen = result.all()
        
        if needs_regen:
            print(f"\n以下 {len(needs_regen)} 个摘要建议重新生成：\n")
            for summary, topic in needs_regen:
                print(f"   - Summary {summary.id} (Topic {topic.id}): {topic.title_key}")
        else:
            print("\n✅ 所有摘要都已修复")


async def main(auto_confirm: bool = False):
    print("=" * 120)
    print("修复损坏的摘要")
    print("=" * 120)
    
    # 第1步：识别
    corrupted_count = await identify_corrupted_summaries()
    
    if corrupted_count == 0:
        print("\n✅ 没有发现损坏的摘要")
        return
    
    # 第2步：预览修复
    fixed_count, failed_count = await fix_corrupted_summaries(dry_run=True)
    
    # 第3步：确认执行
    if auto_confirm:
        print(f"\n自动确认模式：将修复 {fixed_count} 个摘要")
        confirm = True
    else:
        print("\n" + "=" * 120)
        try:
            user_input = input(f"确认修复 {fixed_count} 个摘要？(yes/no): ")
            confirm = user_input.lower() == "yes"
        except (EOFError, KeyboardInterrupt):
            print("\n❌ 已取消（非交互式环境）")
            return
    
    if confirm:
        fixed_count, failed_count = await fix_corrupted_summaries(dry_run=False)
        
        # 第4步：标记需要重新生成的
        if failed_count > 0:
            await mark_for_regeneration()
        
        print("\n" + "=" * 120)
        print("✅ 修复完成")
        print("=" * 120)
    else:
        print("\n❌ 已取消")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="修复损坏的摘要")
    parser.add_argument("--auto-confirm", action="store_true", help="自动确认，不需要交互式输入")
    args = parser.parse_args()
    
    asyncio.run(main(auto_confirm=args.auto_confirm))

