# lecture_mode.py - 授课模式（段落级合并）
def extract_lecture(transcript, target_sec=600, description="", scriptures=None, log_callback=None):
    """授课模式：合并为段落级（20-60秒/段）"""
    if log_callback:
        log_callback("\n📚 授课模式提取...")
    
    if not transcript:
        return []
    
    scriptures = scriptures or []
    
    # ========== 第一步：合并短句为段落（至少20秒）==========
    merged_segments = []
    buffer = []
    buffer_duration = 0
    
    for seg in transcript:
        dur = seg['end'] - seg['start']
        buffer.append(seg)
        buffer_duration += dur
        
        if buffer_duration >= 20:
            merged_segments.append({
                'start': buffer[0]['start'],
                'end': buffer[-1]['end'],
                'text': ' '.join([s['text'] for s in buffer]),
                'duration': buffer_duration
            })
            buffer = []
            buffer_duration = 0
    
    if buffer:
        merged_segments.append({
            'start': buffer[0]['start'],
            'end': buffer[-1]['end'],
            'text': ' '.join([s['text'] for s in buffer]),
            'duration': buffer_duration
        })
    
    if log_callback:
        log_callback(f"   合并后段落数: {len(merged_segments)}")
    
    # ========== 第二步：给每个段落打分 ==========
    def score_segment(seg):
        text = seg['text']
        score = 0
        keywords = ['所以', '因此', '重点', '记住', '结论', '第一', '第二', '第三', '最后']
        for kw in keywords:
            if kw in text:
                score += 5
        if description and description in text:
            score += 15
        for s in scriptures:
            if s in text:
                score += 20
        dur = seg['duration']
        if 30 <= dur <= 90:
            score += 10
        return score
    
    for seg in merged_segments:
        seg['score'] = score_segment(seg)
    
    # 按分数排序
    merged_segments.sort(key=lambda x: x['score'], reverse=True)
    
    # ========== 第三步：贪心选择 ==========
    selected = []
    total = 0
    
    for seg in merged_segments:
        dur = seg['duration']
        if total + dur <= target_sec:
            selected.append(seg)
            total += dur
            if log_callback:
                log_callback(f"   选取段落: {dur:.0f}s (分:{seg['score']})")
        if total >= target_sec:
            break
    
    selected.sort(key=lambda x: x['start'])
    
    if log_callback:
        log_callback(f"\n   ✅ 授课模式完成：{len(selected)}段，{total:.0f}/{target_sec}秒")
    
    return selected