import html
import requests
from bs4 import BeautifulSoup
import os
import re
from datetime import datetime, timezone, timedelta

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
KST = timezone(timedelta(hours=9))

BROKER_KEYWORDS = [
    "미래에셋", "삼성", "키움", "한국투자", "NH투자", "KB", "신한",
    "하나", "메리츠", "대신", "유안타", "이베스트", "SK증권", "한화",
    "교보", "부국", "유진", "IBK투자", "DB", "BNK", "증권"
]

EXCLUDE_KEYWORDS = [
    "동영상", "재생시간", "포토", "[영상]", "[사진]",
    "성매매", "음주운전", "논란", "실형", "사과", "반박", "오보",
    "후보", "선거", "투표", "국민의힘", "민주당", "대통령", "정치",
    "교육감", "현수막", "봉사", "캠프", "여학생"
]

# 손실 없이 확정 수익을 낼 수 있다는 식으로 낚는 광고성/후킹성 제목 문구
AD_HOOK_KEYWORDS = [
    "무손실", "원금보장", "손실없이", "확정수익", "고정수익", "보장수익",
]

# "OO 안 했더니 수익률 1위" 처럼 반전을 미끼로 쓰는 낚시성 제목 패턴
AD_HOOK_PATTERNS = [
    r'안\s*했(더니|다가).{0,15}(1위|대박|수익률|성공)',
]

def is_ad_hook_title(title):
    for keyword in AD_HOOK_KEYWORDS:
        if keyword in title:
            return True
    for pattern in AD_HOOK_PATTERNS:
        if re.search(pattern, title):
            return True
    return False

# 실적/주가와 무관하게 "누가 대표가 됐다"는 인사 발표성 제목.
# 상장 여부를 직접 판별할 방법이 없어, 이런 순수 인사 소식 문구 자체를 걸러낸다
# (스몰캡 투자 다이제스트 취지상 비상장사·거래소 인사 공지가 섞여 들어오는 경우가 많음).
PERSONNEL_CHANGE_KEYWORDS = [
    "신임 대표", "신임 사장", "신임 회장", "신임 CEO", "신임 부회장",
    "대표이사 선임", "대표 선임", "사장 선임", "회장 선임", "CEO 선임",
    "대표 교체", "대표 취임", "경영진 개편", "인사 발령",
    # "OO 맡은 김나영…왜 그를 택했나" 류 인물 프로필/발탁 배경 분석 기사
    "택했나", "택했을까", "발탁", "낙점",
]

def is_personnel_change_title(title):
    for keyword in PERSONNEL_CHANGE_KEYWORDS:
        if keyword in title:
            return True
    return False

FINANCE_KEYWORDS = [
    "주가", "증시", "코스피", "코스닥", "주식", "종목", "매수", "매도",
    "상장", "공모", "청약", "ETF", "펀드", "채권", "금리", "환율",
    "외국인", "기관", "수급", "실적", "영업이익", "순이익", "매출",
    "반도체", "삼성전자", "SK하이닉스", "배당", "자사주", "공매도",
    "선물", "옵션", "IPO", "M&A", "인수", "합병", "지수", "시총",
    "달러", "원화", "Fed", "연준", "금통위", "한국은행", "기준금리",
    "무역", "수출", "수입", "경상수지", "GDP", "CPI", "물가", "고용",
    "유가", "원자재", "구리", "금값", "비트코인", "암호화폐",
    "레버리지", "인버스", "리츠", "부동산", "PER", "PBR", "ROE"
]

def is_invalid_title(title):
    for keyword in EXCLUDE_KEYWORDS:
        if keyword in title:
            return True
    if re.search(r'\d{2}:\d{2}', title):
        return True
    if is_ad_hook_title(title):
        return True
    if is_personnel_change_title(title):
        return True
    return False

def is_broker_article(title):
    for keyword in BROKER_KEYWORDS:
        if keyword in title:
            return True
    return False

def is_finance_related(title):
    for keyword in FINANCE_KEYWORDS:
        if keyword in title:
            return True
    return False

# 같은 사안을 여러 언론사가 각자 다른 제목으로 보도해 중복 게재되는 경우가 많아,
# "이슈 단위"로 묶어 한 회차 다이제스트에는 사안당 1건만 남긴다.
# 제목 텍스트 유사도(문자/단어 n-gram)로는 표현이 제각각이라 오탐/누락이 심해서
# 반복적으로 겹치는 이슈를 키워드 조합(AND)으로 직접 정의하는 방식을 쓴다.
TOPIC_SLOTS = [
    ("fed_rate", [["금리"], ["동결", "인상", "인하"]]),
    ("leverage_etf", [["레버리지"], ["ETF", "총량", "배율"]]),
    ("kospi_selloff", [["코스피", "증시", "지수", "시총"], ["급락", "폭락", "추락", "조정", "하락", "뚝"]]),
    ("won_fx", [["환율", "원화", "달러"], ["급등", "급락", "강세", "약세", "재돌파"]]),
    ("ny_stock", [["뉴욕증시", "뉴욕 증시"], ["하락", "급락", "상승", "랠리"]]),
    ("oil_price", [["국제유가", "브렌트유", "유가"], ["급등", "급락", "재돌파", "상승", "하락"]]),
]

def match_topic_slot(title):
    for name, groups in TOPIC_SLOTS:
        if all(any(kw in title for kw in group) for group in groups):
            return name
    return None

def normalize_url(href):
    article_id = re.search(r'article_id=(\d+)', href)
    office_id = re.search(r'office_id=(\d+)', href)
    if article_id and office_id:
        return f"https://n.news.naver.com/mnews/article/{office_id.group(1)}/{article_id.group(1)}"
    return None

def get_full_title(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            return og["content"].strip()
    except Exception:
        pass
    return None

def fetch_naver_finance(limit=15):
    articles = []
    seen = set()
    used_topic_slots = set()
    page = 1

    while len(articles) < limit and page <= 8:
        url = f"https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258&date=&page={page}"
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = "euc-kr"
        soup = BeautifulSoup(res.text, "html.parser")

        found_ids = False
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")

            if "article_id" not in href:
                continue
            found_ids = True

            clean_url = normalize_url(href)
            if not clean_url or clean_url in seen:
                continue

            title = get_full_title(clean_url)
            if not title:
                title = re.sub(r'^\d+', '', a.get_text(strip=True)).strip()

            if len(title) < 10 or len(title) > 150:
                continue
            if is_broker_article(title):
                continue
            if is_invalid_title(title):
                continue

            topic_slot = match_topic_slot(title)
            if topic_slot and topic_slot in used_topic_slots:
                continue  # 이미 같은 사안의 기사를 실었으므로 건너뜀

            seen.add(clean_url)
            if topic_slot:
                used_topic_slots.add(topic_slot)
            articles.append((title, clean_url))

            if len(articles) >= limit:
                break

        if not found_ids:
            break
        page += 1

    return articles

def build_message(news):
    now = datetime.now(KST)
    weekday = WEEKDAYS[now.weekday()]
    header = "<b>시장·기업 모닝 브리핑</b>\n" + now.strftime("%Y.%m.%d") + " (" + weekday + ")"
    msg = header + "\n\n"
    if not news:
        msg += "이번 회차에 수집된 시장·기업 기사가 없습니다."
        return msg
    items = []
    for title, url in news:
        safe_title = html.escape(title)
        safe_url = html.escape(url, quote=True)
        items.append('· <a href="' + safe_url + '">' + safe_title + '</a>')
    msg += "\n\n".join(items)
    msg += '\n\n기사 제목을 누르면 원문으로 연결됩니다.\n참고 채널: <a href="https://t.me/hanyangresearch">한양증권 스몰캡</a>'
    return msg

def send_telegram(message):
    api_url = "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    res = requests.post(api_url, json=payload, timeout=10)
    res.raise_for_status()
    print("전송 완료")

if __name__ == "__main__":
    print("뉴스 수집 중...")
    news = fetch_naver_finance(limit=15)
    print(str(len(news)) + "건")
    msg = build_message(news)
    print(msg)
    send_telegram(msg)
