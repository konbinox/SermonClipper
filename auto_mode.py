# auto_mode.py - 自动检测讲道类型
def detect_mode(segments):
    """自动判断讲道类型: normal / lecture / ai"""
    total = len(segments)
    if total == 0:
        return "normal"

    text_all = " ".join([s["text"] for s in segments])

    # =====================
    # 1️⃣ 授课特征检测
    # =====================
    lecture_keywords = [
        "第一", "第二", "第三",
        "我们来看", "重点", "总结",
        "分为", "步骤", "原则",
        "首先", "其次", "最后"
    ]
    lecture_score = sum(text_all.count(k) for k in lecture_keywords)

    # =====================
    # 2️⃣ 讲道特征检测
    # =====================
    sermon_keywords = [
        "弟兄姐妹", "见证", "祷告",
        "神", "主", "感动",
        "我曾经", "我要分享", "阿们"
    ]
    sermon_score = sum(text_all.count(k) for k in sermon_keywords)

    # =====================
    # 3️⃣ 句子长度分析
    # =====================
    avg_len = sum(len(s["text"]) for s in segments) / total if total > 0 else 0

    # =====================
    # 4️⃣ 连续长段检测（判断AI型）
    # =====================
    long_segments = sum(1 for s in segments if (s["end"] - s["start"]) > 15)
    long_ratio = long_segments / total if total > 0 else 0

    # =====================
    # 🎯 决策逻辑
    # =====================

    # 授课型：结构词明显
    if lecture_score > sermon_score and lecture_score > 5:
        return "lecture"

    # AI型：句子长 + 长段多（没结构）
    if avg_len > 25 and long_ratio > 0.3:
        return "ai"

    # 默认：普通讲道
    return "normal"