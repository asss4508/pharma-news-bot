import html
import requests
from bs4 import BeautifulSoup
import os
import re
from datetime import datetime, timezone, timedelta

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
KST = timezone(timedelta(hours=9))

EXCLUDE_KEYWORDS = [
    "동영상", "재생시간", "포토", "[영상]", "[사진]",
    "부음", "빙부상", "빙모상", "부친상", "모친상", "장인상", "장모상",
    "별세", "화장품", "조문", "경조사", "결혼", "출산", "임신",
    "화장", "미용"
]

PHARMA_KEYWORDS = [
    "제약", "바이오", "신약", "임상", "FDA", "식약처", "의약품", "백신", "항암",
    "치료제", "의료", "병원", "헬스케어", "바이오시밀러", "항체", "유전자",
    "세포치료", "줄기세포", "mRNA", "희귀질환", "승인", "허가", "임상시험",
    "글로벌 임상", "파이프라인", "기술수출", "기술이전", "라이선스", "CMO", "CDMO",
    "인보사", "코로나", "독감", "당뇨", "암", "종양", "면역"
]

# 국내 상장 제약/바이오 회사명 (제목에 회사명만 있어도 수집)
LISTED_COMPANY_KEYWORDS = [
    # 대형주
    "삼성바이오로직스", "삼성바이오에피스", "셀트리온", "셀트리온제약",
    "SK바이오팜", "SK바이오사이언스", "SK팜테코",
    "유한양행", "한미약품", "한미사이언스", "녹십자", "GC녹십자",
    "대웅제약", "대웅", "종근당", "보령", "동아에스티", "동아ST", "동아쏘시오",
    "HK이노엔", "JW중외제약", "일동제약", "제일약품", "광동제약",
    # KOSDAQ 주요 바이오
    "알테오젠", "리가켐바이오", "레고켐", "에이비엘바이오", "ABL바이오",
    "HLB", "에이치엘비", "휴젤", "파마리서치", "클래시스", "메디톡스",
    "에스티팜", "오스코텍", "브릿지바이오", "한올바이오파마",
    "유바이오로직스", "바이넥스", "프레스티지바이오", "삼천당제약",
    "펩트론", "인벤티지랩", "디앤디파마텍", "지씨셀", "차바이오텍",
    "메지온", "네이처셀", "헬릭스미스", "제넥신", "신라젠", "엔케이맥스",
    "루닛", "뷰노", "제이엘케이", "딥노이드", "셀바스",
    "큐리언트", "압타바이오", "올릭스", "티움바이오", "지놈앤컴퍼니",
    "에이프릴바이오", "보로노이", "카나리아바이오", "젠큐릭스",
    "바이오플러스", "휴메딕스", "케어젠", "콜마비앤에이치",
    "동국제약", "휴온스", "환인제약", "하나제약", "신풍제약", "대원제약",
    "경보제약", "부광약품", "일양약품", "영진약품", "유나이티드제약",
    "안국약품", "삼진제약", "현대약품", "명문제약", "경동제약",
    "셀리드", "진원생명과학", "아이진", "큐라클", "샤페론",
    "에이프로젠", "강스템바이오텍", "코오롱티슈진", "코오롱생명과학",
    "마크로젠", "랩지노믹스", "씨젠", "에스디바이오센서", "바디텍메드",
    "아이센스", "인바디", "레이", "덴티움", "오스템임플란트",
    "메디아나", "원익", "큐렉소", "고영",
]

# 글로벌 제약사 (해외 업체 뉴스 수집)
GLOBAL_PHARMA_KEYWORDS = [
    "화이자", "머크", "MSD", "노바티스", "로슈", "아스트라제네카",
    "사노피", "GSK", "글락소", "릴리", "일라이릴리", "암젠",
    "길리어드", "바이오젠", "모더나", "BMS", "브리스톨",
    "애브비", "존슨앤드존슨", "J&J", "얀센", "다케다",
    "노보노디스크", "노보 노디스크", "베링거인겔하임", "바이엘",
    "리제네론", "버텍스", "다이이찌산쿄", "아스텔라스", "에자이",
    "테바", "비아트리스", "오가논", "론자", "우시", "WuXi",
    "카탈런트", "써모피셔", "일루미나",
]

def is_invalid_title(title):
    for keyword in EXCLUDE_KEYWORDS:
        if keyword in title:
            return True
    return False

def is_pharma_related(title):
    for keyword in PHARMA_KEYWORDS:
        if keyword in title:
            return True
    return False

def is_company_related(title):
    """국내 상장사 또는 글로벌 제약사 관련 기사 여부"""
    for keyword in LISTED_COMPANY_KEYWORDS:
        if keyword in title:
            return True
    for keyword in GLOBAL_PHARMA_KEYWORDS:
        if keyword in title:
            return True
    return False

def sort_by_priority(articles):
    """상장사/글로벌 제약사 기사를 앞쪽에 배치"""
    company_news = []
    general_news = []
    for item in articles:
        title = item[0]
        if is_company_related(title):
            company_news.append(item)
        else:
            general_news.append(item)
    return company_news + general_news

def fetch_yakup(limit=12):
    url = "https://www.yakup.com/news/index.html?cat=all"
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")
    today = datetime.now(KST).date()
    yesterday = today - timedelta(days=1)
    articles_today = []
    articles_yesterday = []
    seen = set()

    for a in soup.select('a[href*="mode=view"]'):
        href = a.get("href", "")

        title_el = a.select_one(".title_con span")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)

        if len(title) < 10 or len(title) > 150:
            continue
        if is_invalid_title(title):
            continue

        cat_el = a.select_one(".cat_con span")
        cat = cat_el.get_text(strip=True) if cat_el else ""
        is_pharma_cat = "제약" in cat or "바이오" in cat
        # 일반 키워드 또는 회사명 중 하나라도 매칭되면 수집
        if not is_pharma_cat and not is_pharma_related(title) and not is_company_related(title):
            continue

        date_el = a.select_one("span.date")
        if not date_el:
            continue
        date_str = date_el.get_text(strip=True)
        try:
            art_date = datetime.strptime(date_str, "%Y.%m.%d").date()
        except ValueError:
            continue

        if href.startswith("/"):
            full_url = "https://www.yakup.com" + href
        else:
            full_url = href

        if full_url in seen:
            continue
        seen.add(full_url)

        if art_date == today:
            articles_today.append((title, full_url))
        elif art_date == yesterday:
            articles_yesterday.append((title, full_url))

    # 상장사/해외 업체 기사가 limit에 잘리지 않도록 우선 배치
    articles_today = sort_by_priority(articles_today)
    articles_yesterday = sort_by_priority(articles_yesterday)

    articles = articles_today[:limit]
    if len(articles) < limit:
        for item in articles_yesterday:
            if item not in articles:
                articles.append(item)
            if len(articles) >= limit:
                break

    return articles

def fetch_pharmnews(limit=3):
    url = "https://www.pharmnews.com/news/articleList.html?view_type=sm"
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")
    articles = []
    seen = set()
    for a in soup.select("a"):
        href = a.get("href", "")
        title = a.get_text(strip=True)
        if "articleView" not in href:
            continue
        if len(title) < 10 or len(title) > 150:
            continue
        if is_invalid_title(title):
            continue
        if not is_pharma_related(title) and not is_company_related(title):
            continue
        if href.startswith("/"):
            full_url = "https://www.pharmnews.com" + href
        else:
            full_url = href
        if full_url in seen:
            continue
        seen.add(full_url)
        articles.append((title, full_url))
        if len(articles) >= limit:
            break
    return sort_by_priority(articles)

def build_message(yakup_news, pharmnews_news):
    now = datetime.now(KST)
    weekday = WEEKDAYS[now.weekday()]
    header = "<b>제약·바이오 모닝 브리핑</b>\n" + now.strftime("%Y.%m.%d") + " (" + weekday + ")"
    msg = header + "\n\n"
    all_news = yakup_news + pharmnews_news
    if not all_news:
        msg += "이번 회차에 수집된 제약·바이오 기사가 없습니다."
        return msg
    items = []
    for title, url in all_news:
        safe_title = html.escape(title)
        safe_url = html.escape(url, quote=True)
        items.append('· <a href="' + safe_url + '">' + safe_title + '</a>')
    msg += "\n\n".join(items)
    msg += '\n\n기사 제목을 누르면 원문으로 연결됩니다.\n참고 채널: <a href="https://t.me/bdragon0808">한양증권 제약·바이오</a>'
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
    yakup = fetch_yakup(limit=12)
    pharmnews = fetch_pharmnews(limit=3)
    print(str(len(yakup)) + "건 / " + str(len(pharmnews)) + "건")
    msg = build_message(yakup, pharmnews)
    print(msg)
    send_telegram(msg)
