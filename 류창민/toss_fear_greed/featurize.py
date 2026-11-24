"""학습·적용 공통 전처리. 멘션 → @사용자, 종목명 → 종목, 숫자 → 0."""
import os
import json, re
D = os.path.dirname(os.path.abspath(__file__))  # 이 폴더
MENTION = re.compile(r"#\[[^\]]*\]\(\d+\)")
_names = sorted({n for v in json.load(open(f"{D}/sectors.json")).values() for n in v.values()}, key=len, reverse=True)
NAME = re.compile("|".join(map(re.escape, _names + "삼전 하닉 하이닉스 에코프로 엘지 현차".split())))
def clean(s):
    return re.sub(r"\d+", "0", NAME.sub("종목", MENTION.sub("@사용자", s or "")))
THRESHOLD = 0.7
