# common.py - 公共函数
import os
import re
import json
import subprocess
from pathlib import Path
from typing import List, Dict

WORK_DIR = Path(__file__).parent / "output"
WORK_DIR.mkdir(parents=True, exist_ok=True)

# 简繁转换
try:
    from zhconv import convert
    HAS_ZHCONV = True
except ImportError:
    HAS_ZHCONV = False

def to_simplified(text: str) -> str:
    if HAS_ZHCONV:
        return convert(text, 'zh-cn')
    return text

def to_traditional(text: str) -> str:
    if HAS_ZHCONV:
        return convert(text, 'zh-tw')
    return text

def get_video_duration(video_path: Path) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=30
        )
        return float(result.stdout.strip())
    except:
        return 0

def filter_worship(transcript: List[Dict], log_callback=None) -> List[Dict]:
    WORSHIP_KEYWORDS = [
        '赞美', '敬拜', '唱歌', '诗歌', '唱诗', '颂赞', '歌颂',
        '哈利路亚', '阿们', '我们一起唱', '会众唱',
        '祷告', '我们祷告', '一起祷告', '同心祷告',
        '主啊', '神啊', '天父', '求祢', '求你', '求主', '奉主的名',
        '奉献', '收款', '扫码', '二维码', '十一奉献',
        '讚美', '敬拜', '唱歌', '詩歌', '哈利路亞', '阿們', '禱告', '奉獻'
    ]
    
    if not transcript:
        return []
    
    filtered = []
    for seg in transcript:
        text = seg['text']
        is_worship = any(kw in text for kw in WORSHIP_KEYWORDS)
        if not is_worship:
            filtered.append(seg)
    
    if log_callback:
        removed = len(transcript) - len(filtered)
        log_callback(f"   🗑️ 过滤敬拜: {len(transcript)} -> {len(filtered)} 段")
    
    return filtered