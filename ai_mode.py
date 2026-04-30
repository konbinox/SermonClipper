# ai_mode.py - 全AI模式
def extract_ai(transcript, target_sec=600, log_callback=None):
    """全AI模式：自动识别高价值段落"""
    if log_callback:
        log_callback("\n🤖 全AI模式提取...")
    
    if not transcript:
        return []
    
    # 按信息密度取前 target_sec 秒
    # 这里放你原有的全AI模式逻辑
    # 暂时返回空，后续完善
    
    if log_callback:
        log_callback(f"   全AI模式待完善")
    
    return []