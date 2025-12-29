import re
import unicodedata

# 简单标题预处理：全角转半角、去标点、数字归一化、压空白

def normalize_title(text: str) -> str:
    if not text:
        return ""
    # 全角转半角
    def to_half_width(s: str) -> str:
        res = []
        for ch in s:
            code = ord(ch)
            # 全角空格
            if code == 0x3000:
                code = 0x20
            # 全角符号/字母/数字
            elif 0xFF01 <= code <= 0xFF5E:
                code -= 0xFEE0
            res.append(chr(code))
        return "".join(res)

    text = to_half_width(text)
    # 规范数字：中文数字一二三两四五六七八九〇零 -> 0-9，十/百/千不转换（避免变成日期语义错误），但常见“二胎”保持 2 胎
    cn_digit_map = {
        "〇": "0", "零": "0", "一": "1", "二": "2", "两": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9",
    }
    text = "".join(cn_digit_map.get(ch, ch) for ch in text)

    # 去除标点符号（保留字母数字汉字和空格）
    text = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", text)
    # 压缩多余空白
    text = re.sub(r"\s+", " ", text).strip()
    # 小写化
    text = text.lower()
    return text
