# selector.py - 模式选择器（支持自动检测）
from auto_mode import detect_mode

def select_segments(segments, mode=None, target_sec=600, 
                    description="", scriptures=None, log_callback=None):
    """统一调度器，支持自动检测模式"""
    
    # 如果没有指定模式，自动检测
    if mode is None or mode == "auto":
        mode = detect_mode(segments)
        if log_callback:
            log_callback(f"   🤖 自动识别模式: {mode}")
    
    if mode == "normal":
        from normal_mode import extract_normal
        return extract_normal(segments, target_sec, log_callback)
    
    elif mode == "lecture":
        from lecture_mode import extract_lecture
        return extract_lecture(segments, target_sec, description, scriptures, log_callback)
    
    elif mode == "ai":
        from ai_mode import extract_ai
        return extract_ai(segments, target_sec, log_callback)
    
    else:
        raise ValueError(f"未知模式: {mode}")