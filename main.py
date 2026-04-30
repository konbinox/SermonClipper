# main.py - 主入口（V12 最终版 - 按钮可见）
import os
import sys
import re
import json
import time
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

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
# 导入模块
# ============================================================

from common import WORK_DIR, filter_worship, get_video_duration
from selector import select_segments

# ============================================================
# 配置
# ============================================================

PRESET_PASTORS = ["刘彤", "曾兴才", "卓尔君", "王亚辰", "郑春焕", "其他"]

# ============================================================
# 核心功能
# ============================================================

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
        cmd = [sys.executable, "-m", "yt_dlp", "-f", "best[height<=720]", 
               "-o", template, "--no-playlist", clean_url]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                if log_callback:
                    log_callback(f"   ❌ 下载失败: {result.stderr[:200]}")
                raise ValueError(f"下载失败")
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


def extract_audio(video_path: Path, log_callback=None) -> Path:
    if log_callback:
        log_callback("🎵 提取音频...")
    
    audio_path = WORK_DIR / "audio.wav"
    if audio_path.exists() and audio_path.stat().st_size > 5_000_000:
        if log_callback:
            log_callback(f"   音频已存在: {audio_path.stat().st_size/1024/1024:.1f}MB")
        return audio_path
    
    cmd = ["ffmpeg", "-y", "-i", str(video_path), "-ar", "16000", "-ac", "1", "-vn", str(audio_path)]
    subprocess.run(cmd, check=True, capture_output=True)
    return audio_path


def transcribe_audio(audio_path: Path, target_lang: str, log_callback=None) -> List[Dict]:
    if log_callback:
        log_callback("📝 转录中...")
    
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise ImportError("请安装: pip install faster-whisper")
    
    duration = get_video_duration(audio_path)
    if duration > 0 and log_callback:
        log_callback(f"   音频时长: {duration/60:.1f} 分钟")
    
    if log_callback:
        log_callback("   加载模型...")
    model = WhisperModel("base", device="cpu", compute_type="int8")
    
    if log_callback:
        log_callback("   转录中...")
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


def render_video(video_path: Path, segments: List[Dict], output_path: Path, 
                  log_callback=None) -> Path:
    if log_callback:
        log_callback("\n🎬 渲染视频...")
    
    if not video_path.exists():
        raise ValueError(f"源视频不存在")
    
    original_dir = os.getcwd()
    os.chdir(WORK_DIR)
    
    temp_files = []
    for i, seg in enumerate(segments):
        start = seg['start']
        dur = seg['end'] - seg['start']
        if dur < 1:
            continue
        tmp_file = WORK_DIR / f"temp_{i:03d}.mp4"
        cmd = ["ffmpeg", "-y", "-ss", str(start), "-i", str(video_path),
               "-t", str(dur), "-c:v", "libx264", "-c:a", "aac", 
               "-preset", "fast", "-crf", "23", str(tmp_file)]
        subprocess.run(cmd, check=True, capture_output=True)
        temp_files.append(tmp_file)
        if log_callback:
            log_callback(f"   片段 {i+1}: {start:.0f}s-{seg['end']:.0f}s ({dur:.0f}s)")
    
    if len(temp_files) == 0:
        raise ValueError("没有成功生成任何片段")
    
    if len(temp_files) == 1:
        import shutil
        shutil.copy(temp_files[0], output_path)
        if log_callback:
            log_callback(f"   单片段复制完成")
    else:
        concat_file = WORK_DIR / "concat.txt"
        with open(concat_file, "w", encoding='utf-8') as f:
            for tmp in temp_files:
                f.write(f"file '{tmp.name}'\n")
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", 
               "-i", str(concat_file), "-c", "copy", str(output_path)]
        subprocess.run(cmd, check=True, capture_output=True)
        concat_file.unlink(missing_ok=True)
        if log_callback:
            log_callback(f"   合并 {len(temp_files)} 个片段...")
    
    for f in temp_files:
        f.unlink(missing_ok=True)
    
    os.chdir(original_dir)
    
    if log_callback:
        out_size = output_path.stat().st_size / (1024 * 1024)
        out_dur = get_video_duration(output_path)
        log_callback(f"   ✅ 渲染完成，{out_size:.1f} MB，{out_dur/60:.1f} 分钟")
    
    return output_path


# ============================================================
# 主处理函数
# ============================================================

def generate_video(source: str, pastor: str, title: str, maker: str,
                    mode: str = "auto", target_lang: str = "simplified",
                    description: str = "", scriptures: List[str] = None,
                    log_callback=None, progress_callback=None) -> Path:
    start_time = time.time()
    target_sec = 600
    
    if log_callback:
        log_callback("=" * 50)
        log_callback(f"开始处理: {title}")
        log_callback(f"讲道人: {pastor} | 制作人: {maker}")
        log_callback(f"指定模式: {mode} | 目标时长: 10分钟")
    
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
        audio_path = extract_audio(video_path, log_callback)
        transcript = transcribe_audio(audio_path, target_lang, log_callback)
    
    transcript = filter_worship(transcript, log_callback)
    
    selected = select_segments(
        segments=transcript,
        mode=mode,
        target_sec=target_sec,
        description=description,
        scriptures=scriptures or [],
        log_callback=log_callback
    )
    
    if not selected:
        raise ValueError("没有提取到任何片段")
    
    elapsed = time.time() - start_time
    elapsed_str = f"{int(elapsed//60)}分{int(elapsed%60)}秒"
    total_out = sum(s['end'] - s['start'] for s in selected)
    
    if log_callback:
        log_callback(f"\n✅ 提取完成! 输出: {total_out:.0f}秒, 耗时: {elapsed_str}")
    
    safe_title = re.sub(r'[\\/*?:"<>|]', '_', title)
    safe_pastor = re.sub(r'[\\/*?:"<>|]', '_', pastor)
    safe_maker = re.sub(r'[\\/*?:"<>|]', '_', maker)
    mode_str = mode if mode != "auto" else "auto"
    output_filename = f"{datetime.now().strftime('%Y%m%d_%H%M')}_{safe_pastor}_{safe_title}_{mode_str}_{safe_maker}_{elapsed_str}.mp4"
    output_path = WORK_DIR / output_filename
    
    final_path = render_video(video_path, selected, output_path, log_callback)
    
    if progress_callback:
        progress_callback(100, "完成！")
    
    return final_path


# ============================================================
# GUI（带滚动条，按钮可见）
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


class SermonGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🎤 讲道精华提取系统 V12")
        self.root.geometry("750x700")
        self.root.minsize(700, 600)
        
        self.setup_ui()
    
    def setup_ui(self):
        # 主框架带滚动条
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True)
        
        scrollable = ScrollableFrame(main_frame)
        frame = scrollable.get_frame()
        
        # 标题
        title_label = ttk.Label(frame, text="🎤 讲道精华提取系统 V12", font=("微软雅黑", 14, "bold"))
        title_label.pack(pady=10)
        
        # ===== 模式选择 =====
        frame_mode = ttk.LabelFrame(frame, text="🎯 提取模式", padding=8)
        frame_mode.pack(fill="x", padx=15, pady=5)
        
        self.mode_var = tk.StringVar(value="auto")
        mode_row = ttk.Frame(frame_mode)
        mode_row.pack()
        
        ttk.Radiobutton(mode_row, text="🤖 自动识别", variable=self.mode_var, value="auto").pack(side="left", padx=10)
        ttk.Radiobutton(mode_row, text="📖 讲道模式", variable=self.mode_var, value="normal").pack(side="left", padx=10)
        ttk.Radiobutton(mode_row, text="📚 授课模式", variable=self.mode_var, value="lecture").pack(side="left", padx=10)
        ttk.Radiobutton(mode_row, text="⚡ 全AI模式", variable=self.mode_var, value="ai").pack(side="left", padx=10)
        
        ttk.Label(frame_mode, text="💡 自动识别会根据讲道内容智能选择最佳模式", font=("微软雅黑", 8), foreground="gray").pack(pady=5)
        
        # ===== 视频来源 =====
        frame_video = ttk.LabelFrame(frame, text="📺 视频来源", padding=8)
        frame_video.pack(fill="x", padx=15, pady=5)
        
        self.video_url = tk.StringVar()
        ttk.Entry(frame_video, textvariable=self.video_url, width=65).pack(fill="x")
        
        # ===== 讲道人 =====
        frame_pastor = ttk.LabelFrame(frame, text="👨‍🏫 讲道人", padding=8)
        frame_pastor.pack(fill="x", padx=15, pady=5)
        
        self.pastor_var = tk.StringVar()
        pastor_combo = ttk.Combobox(frame_pastor, textvariable=self.pastor_var, values=PRESET_PASTORS, width=20, state="readonly")
        pastor_combo.current(0)
        pastor_combo.pack()
        
        # ===== 讲道题目 =====
        frame_title = ttk.LabelFrame(frame, text="📖 讲道题目", padding=8)
        frame_title.pack(fill="x", padx=15, pady=5)
        
        self.title_entry = ttk.Entry(frame_title, width=65)
        self.title_entry.pack(fill="x")
        
        # ===== 大纲描述 =====
        frame_desc = ttk.LabelFrame(frame, text="📝 大纲描述（授课模式/自动模式会参考）", padding=8)
        frame_desc.pack(fill="x", padx=15, pady=5)
        
        self.desc_text = scrolledtext.ScrolledText(frame_desc, height=4, width=65)
        self.desc_text.pack(fill="x")
        ttk.Label(frame_desc, text="描述讲道的主要内容和要点（选填，可提高识别准确率）", font=("微软雅黑", 8), foreground="gray").pack()
        
        # ===== 参考经文 =====
        frame_scripture = ttk.LabelFrame(frame, text="📖 参考经文（可选）", padding=8)
        frame_scripture.pack(fill="x", padx=15, pady=5)
        
        scripture_row = ttk.Frame(frame_scripture)
        scripture_row.pack()
        
        self.scripture_entry = ttk.Entry(scripture_row, width=50)
        self.scripture_entry.pack(side="left", padx=5)
        ttk.Label(scripture_row, text="(如: 腓立比書4:11-13)", font=("微软雅黑", 8), foreground="gray").pack(side="left")
        
        # ===== 字幕语言 =====
        frame_subtitle = ttk.LabelFrame(frame, text="🌐 字幕语言", padding=8)
        frame_subtitle.pack(fill="x", padx=15, pady=5)
        
        self.subtitle_lang = ttk.Combobox(frame_subtitle, values=["简体中文", "繁体中文", "无字幕"], width=15, state="readonly")
        self.subtitle_lang.current(0)
        self.subtitle_lang.pack()
        
        # ===== 进度条 =====
        frame_progress = ttk.LabelFrame(frame, text="📊 处理进度", padding=8)
        frame_progress.pack(fill="x", padx=15, pady=5)
        
        self.progress_var = tk.IntVar()
        self.progress_bar = ttk.Progressbar(frame_progress, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x", pady=3)
        self.progress_label = ttk.Label(frame_progress, text="就绪")
        self.progress_label.pack()
        
        # ===== 日志 =====
        frame_log = ttk.LabelFrame(frame, text="📋 处理日志", padding=8)
        frame_log.pack(fill="both", expand=True, padx=15, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(frame_log, height=10, font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)
        
        # ===== 生成按钮 =====
        self.generate_btn = ttk.Button(frame, text="▶ 生成精华视频", command=self.generate_video, width=25)
        self.generate_btn.pack(pady=15)
        
        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w")
        status_bar.pack(side="bottom", fill="x")
    
    def log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def update_progress(self, value, message):
        self.progress_var.set(value)
        self.progress_label.config(text=message)
        self.root.update_idletasks()
    
    def generate_video(self):
        source = self.video_url.get().strip()
        if not source:
            messagebox.showwarning("提示", "请输入视频链接或路径")
            return
        
        pastor = self.pastor_var.get() or "讲员"
        title = self.title_entry.get().strip() or "讲道"
        maker = "同工"
        mode = self.mode_var.get()
        description = self.desc_text.get("1.0", tk.END).strip()
        scriptures = [s.strip() for s in self.scripture_entry.get().split(',') if s.strip()]
        
        lang_map = {"简体中文": "simplified", "繁体中文": "traditional", "无字幕": "none"}
        target_lang = lang_map.get(self.subtitle_lang.get(), "simplified")
        
        confirm = messagebox.askyesno("确认", f"请确认信息：\n\n讲道人：{pastor}\n题目：{title}\n模式：{mode}\n字幕：{self.subtitle_lang.get()}\n\n确认生成？")
        if not confirm:
            return
        
        self.generate_btn.config(state="disabled")
        self.update_progress(0, "开始处理...")
        self.log("=" * 50)
        self.log(f"开始处理: {title}")
        self.log(f"讲道人: {pastor}")
        self.log(f"模式: {mode}")
        
        def process():
            try:
                output_path = generate_video(
                    source=source, pastor=pastor, title=title, maker=maker,
                    mode=mode, target_lang=target_lang,
                    description=description, scriptures=scriptures,
                    log_callback=self.log, progress_callback=self.update_progress
                )
                if output_path.exists() and output_path.stat().st_size > 0:
                    self.root.after(0, lambda: messagebox.showinfo("成功", f"视频已生成！\n{output_path}\n\n大小: {output_path.stat().st_size/(1024*1024):.1f} MB"))
                    self.root.after(0, lambda: self.log(f"\n✅ 视频已生成: {output_path.name}"))
                else:
                    self.root.after(0, lambda: messagebox.showerror("失败", "视频生成失败"))
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: messagebox.showerror("失败", error_msg))
                self.root.after(0, lambda: self.log(f"\n❌ 生成失败: {error_msg}"))
            finally:
                self.root.after(0, lambda: self.generate_btn.config(state="normal"))
                self.root.after(0, lambda: self.update_progress(0, "就緒"))
        
        threading.Thread(target=process, daemon=True).start()


def main():
    root = tk.Tk()
    app = SermonGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()