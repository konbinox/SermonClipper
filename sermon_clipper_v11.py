#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
讲道精华提取系统 V11.0 - 最终稳定版
- 三模式选择（讲道/授课/全AI）
- 按钮在顶部，行间距压缩
- 修复所有已知错误
"""

import os
import sys
import re
import json
import time
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from enum import Enum

# ============================================================
# 简繁转换
# ============================================================

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


# ============================================================
# 配置
# ============================================================

WORK_DIR = Path(__file__).parent / "output"
WORK_DIR.mkdir(parents=True, exist_ok=True)

PRESET_PASTORS = ["刘彤", "曾兴才", "卓尔君", "王亚辰", "郑春焕", "其他"]

BIBLE_BOOKS_LIST = [
    "创世记", "出埃及记", "利未记", "民数记", "申命记",
    "约书亚记", "士师记", "路得记", "撒母耳记上", "撒母耳记下",
    "列王纪上", "列王纪下", "历代志上", "历代志下", "以斯拉记",
    "尼希米记", "以斯帖记", "约伯记", "诗篇", "箴言",
    "传道书", "雅歌", "以赛亚书", "耶利米书", "耶利米哀歌",
    "以西结书", "但以理书", "何西阿书", "约珥书", "阿摩司书",
    "俄巴底亚书", "约拿书", "弥迦书", "那鸿书", "哈巴谷书",
    "西番雅书", "哈该书", "撒迦利亚书", "玛拉基书",
    "马太福音", "马可福音", "路加福音", "约翰福音", "使徒行传",
    "罗马书", "哥林多前书", "哥林多后书", "加拉太书", "以弗所书",
    "腓立比书", "歌罗西书", "帖撒罗尼迦前书", "帖撒罗尼迦后书",
    "提摩太前书", "提摩太后书", "提多书", "腓利门书", "希伯来书",
    "雅各书", "彼得前书", "彼得后书", "约翰一书", "约翰二书",
    "约翰三书", "犹大书", "启示录"
]

BIBLE_BOOKS = set(BIBLE_BOOKS_LIST)

WORSHIP_KEYWORDS = [
    '赞美', '敬拜', '唱歌', '诗歌', '唱诗', '颂赞', '歌颂',
    '哈利路亚', '阿们', '我们一起唱', '会众唱',
    '祷告', '我们祷告', '一起祷告', '同心祷告',
    '主啊', '神啊', '天父', '求祢', '求你', '求主', '奉主的名',
    '奉献', '收款', '扫码', '二维码', '十一奉献',
    '讚美', '敬拜', '唱歌', '詩歌', '哈利路亞', '阿們', '禱告', '奉獻'
]


class ExtractMode(Enum):
    SERMON = "sermon"
    TEACHING = "teaching"
    AI_FULL = "ai_full"


DEFAULT_DURATION_MINUTES = 10


def has_scripture(text: str) -> bool:
    for book in BIBLE_BOOKS:
        if book in text:
            return True
    if re.search(r'\d+[章节]', text):
        return True
    return False

def get_video_duration(video_path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=30
        )
        return float(result.stdout.strip())
    except:
        return 0


def get_video(source: str, log_callback=None, progress_callback=None) -> Path:
    if log_callback:
        log_callback("📥 获取视频...")
    if progress_callback:
        progress_callback(5, "获取视频...")
    
    if Path(source).exists():
        if log_callback:
            log_callback(f"   使用本地文件: {source}")
        return Path(source)
    
    if "youtube.com" in source or "youtu.be" in source:
        clean_url = source.split('&')[0]
        if log_callback:
            log_callback(f"   清理后链接: {clean_url}")
        
        template = str(WORK_DIR / "%(title)s.%(ext)s")
        
        # 关键修复：使用当前 Python 解释器的完整路径
        python_exe = sys.executable
        cmd = [python_exe, "-m", "yt_dlp", "-f", "best[height<=720]", "-o", template, "--no-playlist", clean_url]
        
        if log_callback:
            log_callback(f"   执行命令: {python_exe} -m yt_dlp ...")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                if log_callback:
                    log_callback(f"   ❌ 下载失败: {result.stderr[:300]}")
                # 备用方案：不使用格式限制
                cmd2 = [python_exe, "-m", "yt_dlp", "-o", template, "--no-playlist", clean_url]
                result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=300)
                if result2.returncode != 0:
                    raise ValueError(f"下载失败: {result2.stderr[:200]}")
        except subprocess.TimeoutExpired:
            raise ValueError("下载超时")
        
        videos = list(WORK_DIR.glob("*.mp4")) + list(WORK_DIR.glob("*.webm"))
        if not videos:
            raise ValueError("未找到下载的视频")
        video_path = max(videos, key=lambda f: f.stat().st_ctime)
        if log_callback:
            log_callback(f"   ✅ 下载完成: {video_path.name}")
        return video_path
    
    raise ValueError(f"无法识别: {source}")


def extract_audio(video_path: Path, log_callback=None, progress_callback=None) -> Path:
    if log_callback:
        log_callback("🎵 提取音频...")
    if progress_callback:
        progress_callback(10, "提取音频...")
    
    audio_path = WORK_DIR / "audio.wav"
    if audio_path.exists() and audio_path.stat().st_size > 5_000_000:
        return audio_path
    
    cmd = ["ffmpeg", "-y", "-i", str(video_path), "-ar", "16000", "-ac", "1", "-vn", str(audio_path)]
    subprocess.run(cmd, check=True, capture_output=True)
    return audio_path


def transcribe_audio(audio_path: Path, target_lang: str, log_callback=None, progress_callback=None) -> List[Dict]:
    if log_callback:
        log_callback("📝 转录中...")
    
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise ImportError("请安装: pip install faster-whisper")
    
    duration = get_video_duration(audio_path)
    if duration > 0 and log_callback:
        log_callback(f"   音频时长: {duration/60:.1f} 分钟")
    
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(audio_path), language="zh", beam_size=5)
    
    transcript = []
    for seg in segments:
        text = seg.text.strip()
        if HAS_ZHCONV:
            if target_lang == "simplified":
                text = to_simplified(text)
            elif target_lang == "traditional":
                text = to_traditional(text)
        transcript.append({"start": seg.start, "end": seg.end, "text": text})
    
    if log_callback:
        log_callback(f"   完成: {len(transcript)} 段")
    
    with open(WORK_DIR / "transcript.json", "w", encoding="utf-8") as f:
        json.dump(transcript, f, ensure_ascii=False, indent=2)
    
    return transcript


def is_worship_segment(seg: Dict, total_duration: float) -> bool:
    text = seg['text']
    duration = max(seg['end'] - seg['start'], 0.1)
    wps = len(text) / duration
    
    for kw in WORSHIP_KEYWORDS:
        if kw in text:
            return True
    
    if text.count('哈利路亚') + text.count('哈利路亞') > 1:
        return True
    if text.count('阿们') + text.count('阿門') > 1:
        return True
    
    if wps < 1.5:
        return True
    
    if seg['start'] > total_duration * 0.85:
        if wps < 2.0 or (len(text) < 30 and duration < 10):
            return True
    
    return False


def filter_worship(transcript: List[Dict], log_callback=None) -> List[Dict]:
    if not transcript:
        return []
    
    total_duration = transcript[-1]['end']
    filtered = []
    for seg in transcript:
        if not is_worship_segment(seg, total_duration):
            filtered.append(seg)
    
    removed = len(transcript) - len(filtered)
    if log_callback and removed > 0:
        log_callback(f"   🗑️ 过滤敬拜: {len(transcript)} -> {len(filtered)} 段")
    
    return filtered


def generate_srt_subtitles(segments: List[Dict], output_path: Path) -> Path:
    srt_path = output_path.with_suffix('.srt')
    
    def format_time(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        millis = int((secs - int(secs)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{int(secs):02d},{millis:03d}"
    
    with open(srt_path, 'w', encoding='utf-8') as f:
        idx = 1
        for seg in segments:
            text = seg.get('text', '')
            if not text:
                continue
            
            sentences = re.split(r'[。！？；]', text)
            current_start = seg['start']
            total_duration = seg['end'] - seg['start']
            
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                
                sentence_duration = len(sentence) / len(text) * total_duration if len(text) > 0 else 3
                sentence_end = min(current_start + sentence_duration, seg['end'])
                
                f.write(f"{idx}\n")
                f.write(f"{format_time(current_start)} --> {format_time(sentence_end)}\n")
                f.write(f"{sentence}\n\n")
                
                idx += 1
                current_start = sentence_end
    
    return srt_path


def render_video(video_path: Path, segments: List[Dict], output_path: Path, 
                  log_callback=None, progress_callback=None) -> Path:
    if log_callback:
        log_callback("\n🎬 渲染视频...")
    
    if not video_path.exists():
        raise ValueError(f"源视频不存在: {video_path}")
    
    src_size = video_path.stat().st_size
    if src_size < 1024 * 1024:
        raise ValueError(f"源视频过小 ({src_size} bytes)")
    
    if log_callback:
        log_callback(f"   源视频: {video_path.name} ({src_size/(1024*1024):.1f} MB)")
    
    original_dir = os.getcwd()
    os.chdir(WORK_DIR)
    
    valid_segments = []
    for seg in segments:
        dur = seg['end'] - seg['start']
        if dur >= 1.0:
            valid_segments.append(seg)
            if log_callback:
                log_callback(f"   片段: ({seg['start']:.0f}s-{seg['end']:.0f}s, {dur:.0f}s)")
    
    if not valid_segments:
        raise ValueError("没有有效片段")
    
    try:
        temp_files = []
        for i, seg in enumerate(valid_segments):
            start = seg['start']
            dur = seg['end'] - seg['start']
            tmp_file = WORK_DIR / f"temp_{i:03d}.mp4"
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-i", str(video_path),
                "-t", str(dur),
                "-c:v", "libx264",
                "-c:a", "aac",
                "-preset", "fast",
                "-crf", "23",
                str(tmp_file)
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            temp_files.append(tmp_file)
        
        concat_file = WORK_DIR / "concat.txt"
        with open(concat_file, "w") as f:
            for tmp in temp_files:
                f.write(f"file '{tmp.name}'\n")
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            "-movflags", "+faststart",
            str(output_path)
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        
        for f in temp_files:
            f.unlink(missing_ok=True)
        concat_file.unlink(missing_ok=True)
        
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise ValueError("合并后文件为空")
        
        if log_callback:
            out_size = output_path.stat().st_size / (1024 * 1024)
            log_callback(f"   ✅ 渲染完成，文件大小: {out_size:.1f} MB")
        
        os.chdir(original_dir)
        return output_path
        
    except Exception as e:
        os.chdir(original_dir)
        raise


def add_soft_subtitles(video_path: Path, subtitle_path: Path, output_path: Path, log_callback=None) -> Path:
    if log_callback:
        log_callback("📝 添加软字幕...")
    
    if not video_path.exists() or video_path.stat().st_size == 0:
        return video_path
    
    if not subtitle_path.exists():
        return video_path
    
    final_output = output_path.with_suffix('.mp4')
    temp_output = WORK_DIR / f"{output_path.stem}_with_sub.mp4"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(subtitle_path),
        "-c:v", "copy",
        "-c:a", "copy",
        "-c:s", "mov_text",
        "-metadata:s:s:0", "language=chi",
        "-movflags", "+faststart",
        str(temp_output)
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        if temp_output.exists() and temp_output.stat().st_size > 0:
            shutil.move(str(temp_output), str(final_output))
            return final_output
        else:
            shutil.copy(video_path, final_output)
            return final_output
    except:
        shutil.copy(video_path, final_output)
        return final_output


# ============================================================
# 提取模式函数
# ============================================================

def extract_sermon_mode(transcript: List[Dict], topics: List[Dict], target_seconds: int, log_callback=None) -> List[Dict]:
    if log_callback:
        log_callback("\n📖 讲道模式提取...")
        log_callback(f"   主题数: {len(topics)}")
    
    selected = []
    total = 0
    
    for i, topic in enumerate(topics):
        topic_title = topic.get('title', '')
        if not topic_title:
            continue
        
        if log_callback:
            log_callback(f"\n   处理主题 {i+1}: {topic_title[:40]}")
        
        best_match = None
        best_score = 0
        for seg in transcript:
            if topic_title in seg['text']:
                score = len(seg['text'])
                if score > best_score:
                    best_score = score
                    best_match = seg
        
        if best_match:
            dur = best_match['end'] - best_match['start']
            if total + dur <= target_seconds:
                selected.append(best_match)
                total += dur
                if log_callback:
                    log_callback(f"      ✓ 找到匹配段落 ({dur:.0f}s)")
            else:
                remaining = target_seconds - total
                if remaining > 10:
                    partial = best_match.copy()
                    partial['end'] = best_match['start'] + remaining
                    selected.append(partial)
                    total = target_seconds
                    if log_callback:
                        log_callback(f"      ✓ 部分取用 ({remaining:.0f}s)")
                    break
        else:
            if log_callback:
                log_callback(f"      ⚠️ 未找到匹配段落")
    
    if total < target_seconds:
        if log_callback:
            log_callback(f"\n   📝 补充片段...")
        transcript.sort(key=lambda x: x['start'])
        for seg in transcript:
            if seg not in selected:
                dur = seg['end'] - seg['start']
                if total + dur <= target_seconds:
                    selected.append(seg)
                    total += dur
                elif total < target_seconds:
                    remaining = target_seconds - total
                    if remaining > 5:
                        partial = seg.copy()
                        partial['end'] = seg['start'] + remaining
                        selected.append(partial)
                        total = target_seconds
                    break
            if total >= target_seconds:
                break
    
    selected.sort(key=lambda x: x['start'])
    
    if log_callback:
        log_callback(f"\n   ✅ 讲道模式完成：{len(selected)}段，{total:.0f}秒")
    
    return selected


def extract_teaching_mode(transcript: List[Dict], description: str, scriptures: List[str],
                           target_seconds: int, log_callback=None) -> List[Dict]:
    """授课模式：累积选取片段直到满额"""
    if log_callback:
        log_callback("\n📚 授课模式提取...")

    if not transcript:
        return []

    total_duration = transcript[-1]['end']
    # 将视频按时间均匀切分成几个大段
    segment_count = max(3, min(8, target_seconds // 30))
    slice_size = total_duration / segment_count
    # 每个大段的目标时长
    per_slice_target = target_seconds // segment_count

    if log_callback:
        log_callback(f"   视频总时长: {total_duration/60:.1f} 分钟")
        log_callback(f"   目标时长: {target_seconds} 秒")
        log_callback(f"   切分为 {segment_count} 个段落，每段目标 {per_slice_target} 秒")

    selected = []
    total = 0

    for i in range(segment_count):
        # 定义第 i 个大段的时间范围
        start = i * slice_size
        end = (i + 1) * slice_size
        slice_segments = [s for s in transcript if start <= s['start'] < end]

        if not slice_segments:
            continue

        # 1. 给这个大段里的每个小片段打分
        scored = []
        for seg in slice_segments:
            score = 0
            text = seg['text']
            if description and description in text:
                score += 15
            for s in scriptures:
                if s in text:
                    score += 20
            scored.append((seg, score))

        # 2. 按分数从高到低排序
        scored.sort(key=lambda x: x[1], reverse=True)

        # 3. 关键改动：在这个大段内，从高分到低分，**累积选取**片段，直到凑满 `per_slice_target` 秒
        topic_total = 0
        for seg, score in scored:
            dur = seg['end'] - seg['start']
            if topic_total + dur <= per_slice_target:
                selected.append(seg)
                topic_total += dur
                total += dur
                if log_callback:
                    log_callback(f"   段落 {i+1}: 选取片段 {dur:.0f}s (累计 {topic_total:.0f}/{per_slice_target}s)")
            elif topic_total < per_slice_target:
                remaining = per_slice_target - topic_total
                if remaining >= 3:
                    # 如果最后一个片段太长，就只取一部分
                    partial = seg.copy()
                    partial['end'] = seg['start'] + remaining
                    selected.append(partial)
                    topic_total += remaining
                    total += remaining
                    if log_callback:
                        log_callback(f"   段落 {i+1}: 部分取用 {remaining:.0f}s")
                    break
            if topic_total >= per_slice_target:
                break

        if total >= target_seconds:
            break

    # 4. 如果所有大段处理完，总时长还不够，就从视频开头按顺序补充片段
    if total < target_seconds:
        if log_callback:
            log_callback(f"   📝 总时长不足，从视频中补充...")
        remaining = target_seconds - total
        transcript_sorted = sorted(transcript, key=lambda x: x['start'])
        for seg in transcript_sorted:
            if seg in selected:
                continue
            dur = seg['end'] - seg['start']
            if total + dur <= target_seconds:
                selected.append(seg)
                total += dur
            elif total < target_seconds:
                remaining = target_seconds - total
                if remaining >= 3:
                    partial = seg.copy()
                    partial['end'] = seg['start'] + remaining
                    selected.append(partial)
                    total = target_seconds
                break
            if total >= target_seconds:
                break

    selected.sort(key=lambda x: x['start'])

    if log_callback:
        log_callback(f"\n   ✅ 授课模式完成：{len(selected)}段，{total:.0f}/{target_seconds}秒")

    return selected


def extract_ai_mode(transcript: List[Dict], target_seconds: int, log_callback=None) -> List[Dict]:
    if log_callback:
        log_callback("\n🤖 全AI模式提取...")
    
    selected = []
    total = 0
    
    for seg in sorted(transcript, key=lambda x: x['start']):
        dur = seg['end'] - seg['start']
        if total + dur <= target_seconds:
            selected.append(seg)
            total += dur
        elif total < target_seconds:
            remaining = target_seconds - total
            if remaining >= 5:
                partial = seg.copy()
                partial['end'] = seg['start'] + remaining
                selected.append(partial)
                total = target_seconds
            break
        if total >= target_seconds:
            break
    
    selected.sort(key=lambda x: x['start'])
    
    if log_callback:
        log_callback(f"\n   ✅ 全AI模式完成：{len(selected)}段，{total:.0f}秒")
    
    return selected


# ============================================================
# 主处理函数
# ============================================================

def generate_video(source: str, pastor: str, title: str, maker: str,
                    mode: ExtractMode,
                    topics: List[Dict] = None,
                    teaching_description: str = None,
                    teaching_scriptures: List[str] = None,
                    target_lang: str = "simplified",
                    log_callback=None, progress_callback=None) -> Tuple[Path, dict]:
    start_time = time.time()
    target_seconds = DEFAULT_DURATION_MINUTES * 60
    
    mode_names = {
        ExtractMode.SERMON: "讲道模式",
        ExtractMode.TEACHING: "授课模式",
        ExtractMode.AI_FULL: "全AI模式"
    }
    
    if log_callback:
        log_callback("=" * 50)
        log_callback(f"开始处理: {title}")
        log_callback(f"讲道人: {pastor} | 制作人: {maker}")
        log_callback(f"模式: {mode_names.get(mode, '未知')} | 目标时长: {DEFAULT_DURATION_MINUTES}分钟")
    
    video_path = get_video(source, log_callback, progress_callback)
    
    trans_path = WORK_DIR / "transcript.json"
    if trans_path.exists():
        if log_callback:
            log_callback("\n📝 使用已有转录...")
        with open(trans_path, 'r', encoding='utf-8') as f:
            transcript = json.load(f)
        if log_callback:
            log_callback(f"   加载 {len(transcript)} 段")
    else:
        audio_path = extract_audio(video_path, log_callback, progress_callback)
        transcript = transcribe_audio(audio_path, target_lang, log_callback, progress_callback)
    
    transcript = filter_worship(transcript, log_callback)
    
    if mode == ExtractMode.SERMON:
        selected = extract_sermon_mode(transcript, topics or [], target_seconds, log_callback)
    elif mode == ExtractMode.TEACHING:
        selected = extract_teaching_mode(transcript, teaching_description or "", 
                                          teaching_scriptures or [], target_seconds, log_callback)
    else:
        selected = extract_ai_mode(transcript, target_seconds, log_callback)
    
    if not selected:
        raise ValueError("没有提取到任何片段")
    
    output_duration = sum(s['end'] - s['start'] for s in selected)
    elapsed = time.time() - start_time
    elapsed_str = f"{int(elapsed//60)}分{int(elapsed%60)}秒"
    
    if log_callback:
        log_callback(f"\n✅ 提取完成! 输出时长: {output_duration:.0f}秒, 耗时: {elapsed_str}")
    
    safe_pastor = re.sub(r'[\\/*?:"<>|]', '_', pastor)
    safe_title = re.sub(r'[\\/*?:"<>|]', '_', title)
    safe_maker = re.sub(r'[\\/*?:"<>|]', '_', maker)
    elapsed_short = elapsed_str.replace("分", "m").replace("秒", "s")
    mode_suffix = {"sermon": "讲道", "teaching": "授课", "ai_full": "AI"}.get(mode.value, "精华")
    output_filename = f"{datetime.now().strftime('%Y%m%d_%H%M')}_{safe_pastor}_{safe_title}_{mode_suffix}_{safe_maker}_{elapsed_short}.mp4"
    output_path = WORK_DIR / output_filename
    
    temp_video = render_video(video_path, selected, output_path, log_callback, progress_callback)
    
    final_path = output_path
    if target_lang != "none" and temp_video.exists() and temp_video.stat().st_size > 0:
        srt_path = generate_srt_subtitles(selected, output_path)
        if srt_path and srt_path.exists():
            final_path = add_soft_subtitles(temp_video, srt_path, output_path, log_callback)
            srt_path.unlink(missing_ok=True)
    
    if not final_path.exists() or final_path.stat().st_size < 1024:
        raise ValueError("视频生成失败")
    
    metadata = {
        "title": title, "pastor": pastor, "maker": maker,
        "mode": mode.value, "elapsed": elapsed_str, "output_duration": f"{output_duration:.0f}秒"
    }
    with open(WORK_DIR / f"{output_path.stem}.info.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    if progress_callback:
        progress_callback(100, "完成！")
    
    return final_path, metadata


# ============================================================
# 对话框类
# ============================================================

class ScrollableFrame:
    def __init__(self, parent):
        self.canvas = tk.Canvas(parent, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.canvas.yview)
        self.frame = ttk.Frame(self.canvas)
        
        self.frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
    
    def get_frame(self):
        return self.frame


class ModeSelectionDialog:
    def __init__(self, parent, callback):
        self.parent = parent
        self.callback = callback
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("选择提取模式")
        self.dialog.geometry("500x450")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        x = parent.winfo_x() + (parent.winfo_width() - 500) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 450) // 2
        self.dialog.geometry(f"+{x}+{y}")
        
        self.setup_ui()
    
    def setup_ui(self):
        ttk.Label(self.dialog, text="🎤 讲道精华提取系统 V11", font=("微软雅黑", 14, "bold")).pack(pady=10)
        ttk.Label(self.dialog, text="请选择提取模式", font=("微软雅黑", 10)).pack(pady=5)
        
        scrollable = ScrollableFrame(self.dialog)
        frame = scrollable.get_frame()
        
        self.mode_var = tk.StringVar(value="")
        
        # 讲道模式
        f1 = ttk.LabelFrame(frame, text="正常讲道模式", padding=10)
        f1.pack(fill="x", padx=10, pady=5)
        ttk.Label(f1, text="适用于主日讲道，需要输入主题及对应经文", font=("微软雅黑", 9)).pack(anchor="w")
        ttk.Radiobutton(f1, text="选择此模式", variable=self.mode_var, value="sermon").pack(anchor="w", pady=5)
        
        # 授课模式
        f2 = ttk.LabelFrame(frame, text="授课模式", padding=10)
        f2.pack(fill="x", padx=10, pady=5)
        ttk.Label(f2, text="适用于专题课程、查经班，输入大纲描述和参考经文", font=("微软雅黑", 9)).pack(anchor="w")
        ttk.Radiobutton(f2, text="选择此模式", variable=self.mode_var, value="teaching").pack(anchor="w", pady=5)
        
        # 全AI模式
        f3 = ttk.LabelFrame(frame, text="全AI提取模式", padding=10)
        f3.pack(fill="x", padx=10, pady=5)
        ttk.Label(f3, text="自动识别经文段落，无需输入任何大纲", font=("微软雅黑", 9)).pack(anchor="w")
        ttk.Radiobutton(f3, text="选择此模式", variable=self.mode_var, value="ai_full").pack(anchor="w", pady=5)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="下一步", command=self.on_next, width=15).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="取消", command=self.on_cancel, width=15).pack(side="left", padx=10)
    
    def on_next(self):
        mode_val = self.mode_var.get()
        if not mode_val:
            messagebox.showwarning("提示", "请先选择一个模式")
            return
        
        if mode_val == "sermon":
            mode = ExtractMode.SERMON
        elif mode_val == "teaching":
            mode = ExtractMode.TEACHING
        elif mode_val == "ai_full":
            mode = ExtractMode.AI_FULL
        else:
            return
        
        self.dialog.destroy()
        
        if mode == ExtractMode.SERMON:
            SermonInputDialog(self.parent, mode, self.callback)
        elif mode == ExtractMode.TEACHING:
            TeachingInputDialog(self.parent, mode, self.callback)
        else:
            AIFullDialog(self.parent, mode, self.callback)
    
    def on_cancel(self):
        self.dialog.destroy()
        self.callback(None)


class SermonInputDialog:
    def __init__(self, parent, mode, callback):
        self.parent = parent
        self.mode = mode
        self.callback = callback
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("讲道模式 - 输入信息")
        self.dialog.geometry("700x600")
        self.dialog.resizable(True, True)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        x = parent.winfo_x() + (parent.winfo_width() - 700) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 600) // 2
        self.dialog.geometry(f"+{x}+{y}")
        
        self.setup_ui()
    
    def setup_ui(self):
        scrollable = ScrollableFrame(self.dialog)
        frame = scrollable.get_frame()
        
        # 按钮放在顶部
        btn_frame_top = ttk.Frame(frame)
        btn_frame_top.pack(fill="x", pady=5)
        ttk.Button(btn_frame_top, text="开始生成", command=self.on_submit, width=12).pack(side="left", padx=5)
        ttk.Button(btn_frame_top, text="返回", command=self.on_back, width=12).pack(side="left", padx=5)
        
        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=5)
        
        # 视频来源
        f1 = ttk.LabelFrame(frame, text="📺 视频来源", padding=5)
        f1.pack(fill="x", pady=2)
        self.video_url = ttk.Entry(f1, width=70)
        self.video_url.pack(fill="x", padx=5, pady=2)
        
        # 讲道人
        f2 = ttk.LabelFrame(frame, text="👨‍🏫 讲道人", padding=5)
        f2.pack(fill="x", pady=2)
        self.pastor_var = tk.StringVar()
        self.pastor_combo = ttk.Combobox(f2, values=PRESET_PASTORS, width=20, state="readonly")
        self.pastor_combo.current(0)
        self.pastor_combo.pack(pady=2)
        self.other_pastor = ttk.Entry(f2, width=20)
        self.other_pastor.pack(pady=2)
        self.other_pastor.pack_forget()
        
        def on_change(e):
            if self.pastor_var.get() == "其他":
                self.other_pastor.pack(pady=2)
            else:
                self.other_pastor.pack_forget()
        self.pastor_combo.bind("<<ComboboxSelected>>", on_change)
        
        # 讲道题目
        f3 = ttk.LabelFrame(frame, text="📖 讲道题目", padding=5)
        f3.pack(fill="x", pady=2)
        self.title_entry = ttk.Entry(f3, width=70)
        self.title_entry.pack(fill="x", padx=5, pady=2)
        
        # 制作人
        f4 = ttk.LabelFrame(frame, text="👤 制作人", padding=5)
        f4.pack(fill="x", pady=2)
        self.maker_entry = ttk.Entry(f4, width=70)
        self.maker_entry.pack(fill="x", padx=5, pady=2)
        self.maker_entry.insert(0, "同工")
        
        # 主题列表
        f5 = ttk.LabelFrame(frame, text="📝 主题与经文（4个）", padding=5)
        f5.pack(fill="x", pady=2)
        self.topic_entries = []
        for i in range(4):
            row = ttk.Frame(f5)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=f"{i+1}.", width=3).pack(side="left")
            title_entry = ttk.Entry(row, width=25)
            title_entry.pack(side="left", padx=2)
            book_combo = ttk.Combobox(row, values=BIBLE_BOOKS_LIST, width=12)
            book_combo.current(0)
            book_combo.pack(side="left")
            ttk.Label(row, text="章").pack(side="left")
            ch_entry = ttk.Entry(row, width=4)
            ch_entry.insert(0, "1")
            ch_entry.pack(side="left")
            ttk.Label(row, text="节").pack(side="left")
            vs_entry = ttk.Entry(row, width=6)
            vs_entry.insert(0, "1")
            vs_entry.pack(side="left")
            self.topic_entries.append((title_entry, book_combo, ch_entry, vs_entry))
        
        # 字幕语言
        f6 = ttk.LabelFrame(frame, text="🌐 字幕语言", padding=5)
        f6.pack(fill="x", pady=2)
        self.subtitle_lang = ttk.Combobox(f6, values=["简体中文", "繁体中文", "无字幕"], width=15, state="readonly")
        self.subtitle_lang.current(0)
        self.subtitle_lang.pack(pady=2)
    
    def get_topics(self):
        topics = []
        for title_entry, book_combo, ch_entry, vs_entry in self.topic_entries:
            title = title_entry.get().strip()
            if not title:
                continue
            book = book_combo.get()
            chapter = ch_entry.get().strip()
            verse = vs_entry.get().strip()
            scripture = f"{book}{chapter}章{verse}节" if chapter and verse else ""
            topics.append({"title": title, "scripture": scripture})
        return topics
    
    def on_submit(self):
        source = self.video_url.get().strip()
        if not source:
            messagebox.showwarning("提示", "请输入视频链接或路径")
            return
        
        pastor = self.pastor_var.get()
        if pastor == "其他":
            pastor = self.other_pastor.get().strip()
            if not pastor:
                pastor = "讲员"
        elif not pastor:
            pastor = "讲员"
        
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showwarning("提示", "请输入讲道题目")
            return
        
        maker = self.maker_entry.get().strip()
        if not maker:
            maker = "同工"
        
        topics = self.get_topics()
        if len(topics) < 1:
            messagebox.showwarning("提示", "请至少输入一个主题")
            return
        
        lang_map = {"简体中文": "simplified", "繁体中文": "traditional", "无字幕": "none"}
        target_lang = lang_map.get(self.subtitle_lang.get(), "simplified")
        
        self.dialog.destroy()
        self.callback({
            "mode": self.mode,
            "source": source,
            "pastor": pastor,
            "title": title,
            "maker": maker,
            "target_lang": target_lang,
            "topics": topics
        })
    
    def on_back(self):
        self.dialog.destroy()
        ModeSelectionDialog(self.parent, self.callback)


class TeachingInputDialog:
    def __init__(self, parent, mode, callback):
        self.parent = parent
        self.mode = mode
        self.callback = callback
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("授课模式 - 输入信息")
        self.dialog.geometry("700x600")
        self.dialog.resizable(True, True)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        x = parent.winfo_x() + (parent.winfo_width() - 700) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 600) // 2
        self.dialog.geometry(f"+{x}+{y}")
        
        self.setup_ui()
    
    def setup_ui(self):
        scrollable = ScrollableFrame(self.dialog)
        frame = scrollable.get_frame()
        
        # 按钮放在顶部
        btn_frame_top = ttk.Frame(frame)
        btn_frame_top.pack(fill="x", pady=5)
        ttk.Button(btn_frame_top, text="开始生成", command=self.on_submit, width=12).pack(side="left", padx=5)
        ttk.Button(btn_frame_top, text="返回", command=self.on_back, width=12).pack(side="left", padx=5)
        
        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=5)
        
        # 视频来源
        f1 = ttk.LabelFrame(frame, text="📺 视频来源", padding=5)
        f1.pack(fill="x", pady=2)
        self.video_url = ttk.Entry(f1, width=70)
        self.video_url.pack(fill="x", padx=5, pady=2)
        
        # 讲道人
        f2 = ttk.LabelFrame(frame, text="👨‍🏫 讲道人", padding=5)
        f2.pack(fill="x", pady=2)
        self.pastor_var = tk.StringVar()
        self.pastor_combo = ttk.Combobox(f2, values=PRESET_PASTORS, width=20, state="readonly")
        self.pastor_combo.current(0)
        self.pastor_combo.pack(pady=2)
        self.other_pastor = ttk.Entry(f2, width=20)
        self.other_pastor.pack(pady=2)
        self.other_pastor.pack_forget()
        
        def on_change(e):
            if self.pastor_var.get() == "其他":
                self.other_pastor.pack(pady=2)
            else:
                self.other_pastor.pack_forget()
        self.pastor_combo.bind("<<ComboboxSelected>>", on_change)
        
        # 课程题目
        f3 = ttk.LabelFrame(frame, text="📖 课程题目", padding=5)
        f3.pack(fill="x", pady=2)
        self.title_entry = ttk.Entry(f3, width=70)
        self.title_entry.pack(fill="x", padx=5, pady=2)
        
        # 制作人
        f4 = ttk.LabelFrame(frame, text="👤 制作人", padding=5)
        f4.pack(fill="x", pady=2)
        self.maker_entry = ttk.Entry(f4, width=70)
        self.maker_entry.pack(fill="x", padx=5, pady=2)
        self.maker_entry.insert(0, "同工")
        
        # 课程大纲
        f5 = ttk.LabelFrame(frame, text="📝 课程大纲描述", padding=5)
        f5.pack(fill="x", pady=2)
        self.desc_text = scrolledtext.ScrolledText(f5, height=6, width=65)
        self.desc_text.pack(fill="x", padx=5, pady=2)
        ttk.Label(f5, text="请用文字描述课程的主要内容和要点", font=("微软雅黑", 8), foreground="gray").pack()
        
        # 参考经文
        f6 = ttk.LabelFrame(frame, text="📖 参考经文（可选）", padding=5)
        f6.pack(fill="x", pady=2)
        
        self.scriptures_frame = ttk.Frame(f6)
        self.scriptures_frame.pack(fill="x", padx=5, pady=2)
        
        self.scripture_entries = []
        self.add_scripture_row()
        ttk.Button(f6, text="+ 添加经文", command=self.add_scripture_row).pack(pady=2)
        
        # 字幕语言
        f7 = ttk.LabelFrame(frame, text="🌐 字幕语言", padding=5)
        f7.pack(fill="x", pady=2)
        self.subtitle_lang = ttk.Combobox(f7, values=["简体中文", "繁体中文", "无字幕"], width=15, state="readonly")
        self.subtitle_lang.current(0)
        self.subtitle_lang.pack(pady=2)
    
    def add_scripture_row(self):
        row = ttk.Frame(self.scriptures_frame)
        row.pack(fill="x", pady=1)
        book_combo = ttk.Combobox(row, values=BIBLE_BOOKS_LIST, width=12)
        book_combo.current(0)
        book_combo.pack(side="left", padx=2)
        ttk.Label(row, text="章").pack(side="left")
        ch_entry = ttk.Entry(row, width=4)
        ch_entry.insert(0, "1")
        ch_entry.pack(side="left", padx=2)
        ttk.Label(row, text="节").pack(side="left")
        vs_entry = ttk.Entry(row, width=6)
        vs_entry.insert(0, "1")
        vs_entry.pack(side="left", padx=2)
        ttk.Button(row, text="✖", width=2, command=lambda: (row.destroy(), self.scripture_entries.remove((book_combo, ch_entry, vs_entry)))).pack(side="right")
        self.scripture_entries.append((book_combo, ch_entry, vs_entry))
    
    def get_scriptures(self):
        result = []
        for book_combo, ch_entry, vs_entry in self.scripture_entries:
            book = book_combo.get()
            ch = ch_entry.get().strip()
            vs = vs_entry.get().strip()
            if ch and vs:
                result.append(f"{book}{ch}章{vs}节")
        return result
    
    def on_submit(self):
        source = self.video_url.get().strip()
        if not source:
            messagebox.showwarning("提示", "请输入视频链接或路径")
            return
        
        pastor = self.pastor_var.get()
        if pastor == "其他":
            pastor = self.other_pastor.get().strip()
            if not pastor:
                pastor = "讲员"
        elif not pastor:
            pastor = "讲员"
        
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showwarning("提示", "请输入课程题目")
            return
        
        maker = self.maker_entry.get().strip()
        if not maker:
            maker = "同工"
        
        description = self.desc_text.get("1.0", tk.END).strip()
        if not description:
            messagebox.showwarning("提示", "请输入课程大纲描述")
            return
        
        scriptures = self.get_scriptures()
        lang_map = {"简体中文": "simplified", "繁体中文": "traditional", "无字幕": "none"}
        target_lang = lang_map.get(self.subtitle_lang.get(), "simplified")
        
        self.dialog.destroy()
        self.callback({
            "mode": self.mode,
            "source": source,
            "pastor": pastor,
            "title": title,
            "maker": maker,
            "target_lang": target_lang,
            "description": description,
            "scriptures": scriptures
        })
    
    def on_back(self):
        self.dialog.destroy()
        ModeSelectionDialog(self.parent, self.callback)


class AIFullDialog:
    def __init__(self, parent, mode, callback):
        self.parent = parent
        self.mode = mode
        self.callback = callback
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("全AI模式 - 输入信息")
        self.dialog.geometry("550x500")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        x = parent.winfo_x() + (parent.winfo_width() - 550) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 500) // 2
        self.dialog.geometry(f"+{x}+{y}")
        
        self.setup_ui()
    
    def setup_ui(self):
        scrollable = ScrollableFrame(self.dialog)
        frame = scrollable.get_frame()
        
        # 按钮放在顶部
        btn_frame_top = ttk.Frame(frame)
        btn_frame_top.pack(fill="x", pady=5)
        ttk.Button(btn_frame_top, text="开始生成", command=self.on_submit, width=12).pack(side="left", padx=5)
        ttk.Button(btn_frame_top, text="返回", command=self.on_back, width=12).pack(side="left", padx=5)
        
        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=5)
        
        # 说明
        info = ttk.LabelFrame(frame, text="🤖 全AI自动提取", padding=10)
        info.pack(fill="x", pady=5)
        ttk.Label(info, text="系统将自动识别并提取以下内容：", font=("微软雅黑", 10)).pack(anchor="w")
        ttk.Label(info, text="• 经文引用（书卷名、章节号）", font=("微软雅黑", 9)).pack(anchor="w", padx=20)
        ttk.Label(info, text="• 讲道重点段落", font=("微软雅黑", 9)).pack(anchor="w", padx=20)
        ttk.Label(info, text="⏱️ 默认时长：10分钟", font=("微软雅黑", 9), foreground="blue").pack(anchor="w", padx=20, pady=5)
        ttk.Label(info, text="无需输入提纲和经文，直接生成", font=("微软雅黑", 9), foreground="green").pack(anchor="w", padx=20)
        
        # 视频来源
        f1 = ttk.LabelFrame(frame, text="📺 视频来源", padding=5)
        f1.pack(fill="x", pady=5)
        self.video_url = ttk.Entry(f1, width=55)
        self.video_url.pack(fill="x", padx=5, pady=2)
        
        # 讲道人
        f2 = ttk.LabelFrame(frame, text="👨‍🏫 讲道人", padding=5)
        f2.pack(fill="x", pady=5)
        self.pastor_var = tk.StringVar()
        self.pastor_combo = ttk.Combobox(f2, values=PRESET_PASTORS, width=20, state="readonly")
        self.pastor_combo.current(0)
        self.pastor_combo.pack(pady=2)
        self.other_pastor = ttk.Entry(f2, width=20)
        self.other_pastor.pack(pady=2)
        self.other_pastor.pack_forget()
        
        def on_change(e):
            if self.pastor_var.get() == "其他":
                self.other_pastor.pack(pady=2)
            else:
                self.other_pastor.pack_forget()
        self.pastor_combo.bind("<<ComboboxSelected>>", on_change)
        
        # 讲道题目
        f3 = ttk.LabelFrame(frame, text="📖 讲道题目", padding=5)
        f3.pack(fill="x", pady=5)
        self.title_entry = ttk.Entry(f3, width=55)
        self.title_entry.pack(fill="x", padx=5, pady=2)
        
        # 制作人
        f4 = ttk.LabelFrame(frame, text="👤 制作人", padding=5)
        f4.pack(fill="x", pady=5)
        self.maker_entry = ttk.Entry(f4, width=55)
        self.maker_entry.pack(fill="x", padx=5, pady=2)
        self.maker_entry.insert(0, "同工")
        
        # 字幕语言
        f5 = ttk.LabelFrame(frame, text="🌐 字幕语言", padding=5)
        f5.pack(fill="x", pady=5)
        self.subtitle_lang = ttk.Combobox(f5, values=["简体中文", "繁体中文", "无字幕"], width=15, state="readonly")
        self.subtitle_lang.current(0)
        self.subtitle_lang.pack(pady=2)
    
    def on_submit(self):
        source = self.video_url.get().strip()
        if not source:
            messagebox.showwarning("提示", "请输入视频链接或路径")
            return
        
        pastor = self.pastor_var.get()
        if pastor == "其他":
            pastor = self.other_pastor.get().strip()
            if not pastor:
                pastor = "讲员"
        elif not pastor:
            pastor = "讲员"
        
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showwarning("提示", "请输入讲道题目")
            return
        
        maker = self.maker_entry.get().strip()
        if not maker:
            maker = "同工"
        
        lang_map = {"简体中文": "simplified", "繁体中文": "traditional", "无字幕": "none"}
        target_lang = lang_map.get(self.subtitle_lang.get(), "simplified")
        
        self.dialog.destroy()
        self.callback({
            "mode": self.mode,
            "source": source,
            "pastor": pastor,
            "title": title,
            "maker": maker,
            "target_lang": target_lang
        })
    
    def on_back(self):
        self.dialog.destroy()
        ModeSelectionDialog(self.parent, self.callback)


# ============================================================
# 主界面
# ============================================================

class SermonGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🎤 讲道精华提取系统 V11")
        self.root.geometry("800x600")
        
        self.result = None
        self.setup_ui()
        self.root.after(100, self.start_new_task)
    
    def setup_ui(self):
        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True, padx=20, pady=15)
        
        f1 = ttk.LabelFrame(main, text="📊 处理进度", padding=8)
        f1.pack(fill="x", pady=5)
        self.progress_var = tk.IntVar()
        self.progress_bar = ttk.Progressbar(f1, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x", pady=3)
        self.progress_label = ttk.Label(f1, text="就绪")
        self.progress_label.pack()
        
        f2 = ttk.LabelFrame(main, text="📋 处理日志", padding=8)
        f2.pack(fill="both", expand=True, pady=5)
        self.log_text = scrolledtext.ScrolledText(f2, height=12, font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)
        
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w").pack(side="bottom", fill="x")
        
        self.start_btn = ttk.Button(self.root, text="▶ 开始新任务", command=self.start_new_task, width=20)
        self.start_btn.pack(pady=10)
    
    def start_new_task(self):
        self.start_btn.config(state="disabled")
        self.log_text.delete(1.0, tk.END)
        self.progress_var.set(0)
        self.progress_label.config(text="就绪")
        ModeSelectionDialog(self.root, self.on_mode_selected)
    
    def on_mode_selected(self, result):
        self.start_btn.config(state="normal")
        if result is None:
            return
        
        self.result = result
        self.log("=" * 50)
        self.log("开始处理...")
        self.start_extraction()
    
    def log(self, msg):
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def update_progress(self, value, msg):
        self.progress_var.set(value)
        self.progress_label.config(text=msg)
        self.root.update_idletasks()
    
    def start_extraction(self):
        self.start_btn.config(state="disabled")
        
        def process():
            try:
                result = self.result
                mode = result["mode"]
                
                if mode == ExtractMode.SERMON:
                    output_path, meta = generate_video(
                        source=result["source"], pastor=result["pastor"],
                        title=result["title"], maker=result["maker"],
                        mode=mode, topics=result.get("topics", []),
                        target_lang=result.get("target_lang", "simplified"),
                        log_callback=self.log, progress_callback=self.update_progress
                    )
                elif mode == ExtractMode.TEACHING:
                    output_path, meta = generate_video(
                        source=result["source"], pastor=result["pastor"],
                        title=result["title"], maker=result["maker"],
                        mode=mode, teaching_description=result.get("description", ""),
                        teaching_scriptures=result.get("scriptures", []),
                        target_lang=result.get("target_lang", "simplified"),
                        log_callback=self.log, progress_callback=self.update_progress
                    )
                else:
                    output_path, meta = generate_video(
                        source=result["source"], pastor=result["pastor"],
                        title=result["title"], maker=result["maker"],
                        mode=mode, target_lang=result.get("target_lang", "simplified"),
                        log_callback=self.log, progress_callback=self.update_progress
                    )
                
                if output_path.exists() and output_path.stat().st_size > 0:
                    self.root.after(0, lambda: messagebox.showinfo("成功", f"视频已生成！\n{output_path}\n大小: {output_path.stat().st_size/(1024*1024):.1f} MB"))
                    self.root.after(0, lambda: self.log(f"\n✅ 视频已生成: {output_path.name}"))
                else:
                    self.root.after(0, lambda: messagebox.showerror("失败", "视频生成失败"))
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: messagebox.showerror("失败", error_msg))
                self.root.after(0, lambda: self.log(f"\n❌ 生成失败: {error_msg}"))
                import traceback
                traceback.print_exc()
            finally:
                self.root.after(0, lambda: self.start_btn.config(state="normal"))
                self.root.after(0, lambda: self.update_progress(0, "就绪"))
        
        threading.Thread(target=process, daemon=True).start()


def main():
    root = tk.Tk()
    app = SermonGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()