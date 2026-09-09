import requests
from bs4 import BeautifulSoup
import os
import re
import json
from html import escape
from urllib.parse import urlparse, urljoin
from datetime import datetime, timezone, timedelta

# 매시간 실행되므로 최근에 이미 보낸 기사는 다시 보내지 않도록 이력을 저장한다.
SENT_LOG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "hourly_sent_log.json"
)
SENT_LOG_KEEP = 90  # 하루 9건 기준 약 10일치 보관

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

KST = timezone(timedelta(hours=9))
RANKING_URL = "https://news.naver.com/main/ranking/popularDay.naver"
# 경제·산업 전문 매체의 현재 많이 본 뉴스에서 기업 이벤트를 선별한다.
BUSINESS_PRESS = {"009", "015", "011", "014", "018", "277", "016", "008", "366", "030", "092"}


def in_send_window(now):
    return 8 <= now.astimezone(KST).hour < 17

# 상품 홍보·수익률 경쟁은 기업 이벤트와 구분해 제외한다(대소문자 무관).
PRODUCT_KEYWORDS = [
    "etf", "etn", "펀드", "자산운용", "신한운용", "삼성운용", "한투운용",
    "순자산", "운용자산", "수익률", "목표주가", "추천주", "특징주",
]
COMPANY_EVENTS = [
    "수주", "공급계약", "공급 계약", "계약 체결", "계약체결", "납품",
    "신제품", "신약", "기술이전", "기술 이전", "임상", "허가", "특허",
    "세계 최초", "세계최초", "상용화", "양산", "개발 성공", "개발성공",
    "인수", "합병", "m&a", "지분 매각", "지분 인수", "경영권",
    "공장 신설", "공장 증설", "착공", "준공", "생산 확대", "합작",
    "흑자전환", "흑자 전환", "적자전환", "적자 전환", "사상 최대 실적",
    "영업이익", "어닝 서프라이즈", "리콜", "소송", "횡령", "배임",
    "거래정지", "상장폐지", "유상증자", "자사주 소각",
]


def has_company_event(title):
    return any(keyword in title.casefold() for keyword in COMPANY_EVENTS)

BROKER_KEYWORDS = [
    "미래에셋", "삼성증권", "키움", "한국투자", "NH투자", "KB증권", "신한투자",
    "하나증권", "메리츠", "대신증권", "유안타", "이베스트", "SK증권", "한화투자",
    "교보증권", "부국증권", "유진투자", "IBK투자", "DB금융", "BNK투자",
    # "카카오페이증권", "토스증권"처럼 개별 리스트에 없는 증권사도
    # 이름 끝에 항상 "증권"이 붙으므로 이 한 단어로 다 걸러진다.
    # 헤드라인에서는 "카카오페이證"처럼 한자 약어로 줄여 쓰는 경우도 많다.
    "증권", "證"
]

EXCLUDE_KEYWORDS = [
    "동영상", "재생시간", "포토", "[영상]", "[사진]",
    "부음", "부고", "마감시황", "장마감", "시황",
    # 실제 산업/기업 뉴스가 아닌 "누가 얼마나 사고팔았다"류 기계적 매매동향 리포트
    "초고수", "매매동향", "매매일지", "고수의 매매", "순매수 상위", "순매도 상위"
]

HIGH_PRIORITY = [
    "금리", "환율", "코스피", "코스닥", "주가", "증시", "시장", "Fed", "연준",
    "금통위", "한국은행", "기준금리", "인플레", "CPI", "GDP", "무역",
    "수출", "반도체", "삼성전자", "SK하이닉스", "외국인", "기관", "매수", "매도",
    "IPO", "공매도", "선물", "옵션", "채권", "국채", "달러", "원화",
    "무역수지", "경상수지", "실업", "고용", "물가", "PER", "실적",
    "어닝", "배당", "자사주", "M&A", "인수", "합병", "상장", "상폐"
]

# 당일 핫이슈로 취급할 산업/빅테크 섹터 (반도체·이차전지·조선·방산·빅테크 등)
# 이 목록에 걸리면 HIGH_PRIORITY보다 가중치를 더 줘서 상단에 노출시킨다.
SECTOR_KEYWORDS = [
    # 반도체
    "반도체", "파운드리", "HBM", "메모리", "낸드", "D램", "DDR5", "웨이퍼",
    "삼성전자", "SK하이닉스", "TSMC", "엔비디아", "AMD", "ASML",
    # 이차전지
    "이차전지", "배터리", "2차전지", "양극재", "음극재", "전고체", "전해질",
    "LG에너지솔루션", "삼성SDI", "SK온", "에코프로", "포스코퓨처엠",
    # 조선
    "조선", "조선업", "선박", "수주", "LNG선", "컨테이너선", "HD현대",
    "삼성중공업", "한화오션", "현대미포조선",
    # 방산
    "방산", "방위산업", "무기수출", "K9", "천궁", "한화에어로스페이스",
    "KAI", "한국항공우주", "현대로템", "LIG넥스원",
    # 빅테크/AI
    "빅테크", "AI", "인공지능", "챗GPT", "생성형", "테슬라", "애플",
    "마이크로소프트", "구글", "아마존", "메타", "오픈AI", "데이터센터",
]

def clean_title(title):
    title = re.sub(r'^\d+[.\)]?\s*', '', title)
    title = re.sub(r'^영상\s+(?=\S)', '', title)  # "영상" 동영상 배지가 제목에 붙어 나오는 경우
    title = re.sub(r'\[.*?기자.*?\]', '', title)
    title = re.sub(r'\[.*?특파원.*?\]', '', title)
    title = re.sub(r'·\[.*?\]', '', title)
    return title.strip()

def is_invalid(title):
    if any(keyword in title.casefold() for keyword in PRODUCT_KEYWORDS):
        return True
    for keyword in EXCLUDE_KEYWORDS + BROKER_KEYWORDS:
        if keyword in title:
            return True
    if len(title) < 10 or len(title) > 120:
        return True
    if re.search(r'\d{2}:\d{2}', title):
        return True
    return False

def get_priority(title):
    # 실제 기업 이벤트를 섹터 키워드보다 우선한다.
    score = 20 * sum(keyword in title.casefold() for keyword in COMPANY_EVENTS)
    for keyword in HIGH_PRIORITY:
        if keyword in title:
            score += 1
    for keyword in SECTOR_KEYWORDS:
        if keyword in title:
            score += 2
    return score

def get_article_date(url):
    """기사 발행일을 og:article:published_time 또는 메타태그에서 추출"""
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(res.text, "html.parser")
        published = soup.select_one("._ARTICLE_DATE_TIME[data-date-time]")
        if published:
            return datetime.fromisoformat(published["data-date-time"]).date()
        for prop in ["article:published_time", "og:regDate", "og:pub_date", "datePublished"]:
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if tag and tag.get("content"):
                raw = tag["content"][:10]
                try:
                    return datetime.strptime(raw, "%Y-%m-%d").date()
                except Exception:
                    pass
        # 날짜 패턴 직접 탐색
        text = res.text
        m = re.search(r'(\d{4})[.\-/](\d{2})[.\-/](\d{2})', text[:3000])
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
            except Exception:
                pass
    except Exception:
        pass
    return None

# 사이트마다 툴바 문구 조합/순서가 달라 고정된 문구 정규식만으로는 다 못 잡는다.
# 본문 맨 앞에 이런 단어만 연달아 나오면(문장부호 없이) 사이트 UI 잔재로 보고 통째로 잘라낸다.
UI_NOISE_WORDS = {
    "뉴스", "듣기", "글자", "크기", "설정", "보통", "크게", "아주",
    "기사", "공유", "기사공유", "페이스북", "엑스", "카카오톡",
    "이메일", "주소복사", "북마크", "다크모드", "프린트", "네이버",
    "채널구독",
}

def strip_leading_ui_noise(text):
    words = text.split(" ")
    i = 0
    while i < len(words) and words[i] in UI_NOISE_WORDS:
        i += 1
    return " ".join(words[i:])

def cut_after_title_repeat(text, title):
    """카테고리/브레드크럼브 뒤에 제목이 그대로 반복되는 사이트가 있어,
    본문 앞부분에서 제목이 다시 나오면 그 뒤부터를 실제 본문으로 본다."""
    if not title or len(title) < 10:
        return text
    search_zone = text[:400]
    needle = title if len(title) <= 60 else title[:60]
    pos = search_zone.find(needle)
    if pos == -1:
        return text
    return text[pos + len(needle):].strip()

def get_article_summary(url, title=None):
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")

        # 불필요한 태그 제거
        for tag in soup(["script", "style", "header", "footer", "nav",
                         "aside", "iframe", "figure", "figcaption",
                         "button", "form", "input", "select"]):
            tag.decompose()

        # 사진 캡션, UI 버튼 영역 제거
        for tag in soup.select(
            ".image_caption, .caption, .img_desc, .photo_desc, .ImageCaption, "
            "[class*='caption'], [class*='Caption'], [class*='photo'], [class*='Photo'], "
            "[class*='share'], [class*='Share'], [class*='tool'], [class*='Tool'], "
            "[class*='font'], [class*='Font'], [class*='sns'], [class*='SNS'], "
            "[class*='subscribe'], [class*='Subscribe'], [class*='related'], "
            "[class*='button'], [class*='Button'], .article_util, .article-util"
        ):
            tag.decompose()

        content = None
        selectors = [
            "#dic_area", "#articleBody", "#article-view-content-div",
            ".article_body", ".news_body", "#newsct_article",
            "#articeBody", ".article-body", "#article_content",
            ".article_txt", "#news_body_area", ".news-article-body",
            "#cont_article", ".view_text", "#articleBodyContents",
            ".article-content", ".news_end_body", "article"
        ]
        for selector in selectors:
            content = soup.select_one(selector)
            if content:
                break

        # 본문 영역을 찾지 못하면 메뉴·광고를 발췌하지 않는다.
        if not content:
            return ""

        if content:
            for tag in content.select(
                "[class*='caption'], [class*='Caption'], [class*='photo'], "
                "[class*='Photo'], [class*='img'], [class*='Img'], "
                "[class*='share'], [class*='tool'], [class*='font'], "
                "[class*='sns'], [class*='button']"
            ):
                tag.decompose()

            text = content.get_text(separator=" ", strip=True)
            text = cut_after_title_repeat(text, title)

            # UI 버튼 텍스트 패턴 제거
            text = re.sub(r'뉴스\s*듣기.*?크기', '', text)
            text = re.sub(r'글자\s*크기\s*가\s*보통.*?크게', '', text)
            text = re.sub(r'기사\s*공유\s*페이스북.*?프린트', '', text)
            text = re.sub(r'페이스북\s*엑스\s*카카오톡.*?북마크', '', text)
            text = re.sub(r'채널구독\s*다음\s*채널구독', '', text)
            text = re.sub(r'다크모드\s*프린트\s*네이버', '', text)
            text = re.sub(r'이메일\s*주소복사', '', text)
            text = strip_leading_ui_noise(text.strip())

            # 'AI프리즘' 등 여러 이슈를 묶어 자동 요약하는 브리핑형 기사는
            # 목차/서비스 소개 문구가 실제 내용보다 앞서 나오므로 통째로 제거
            text = re.sub(r'■?\s*AI\s*프리즘.*?제공합니다\.', '', text)
            text = re.sub(r'^[▲\s]*\[[^\[\]]{1,20}\]\s*', '', text.strip())
            text = text.replace('■', ' ').replace('▲', ' ')

            # 기자 서명, 출처 제거
            text = re.sub(r'\S+@\S+\.\S+', '', text)
            text = re.sub(r'\d{4}-\d{2}-\d{2}\s*\d{2}:\d{2}:\d{2}', '', text)
            text = re.sub(r'\d{4}\.\d{2}\.\d{2}\s*[가-힣]+\s*기자', '', text)
            text = re.sub(r'[가-힣]+\s*기자\s*=?\s*', '', text)
            text = re.sub(r'\[.*?기자.*?\]', '', text)
            text = re.sub(r'\[.*?=.*?\]', '', text)
            text = re.sub(r'\d{4}\.\d{2}\.\d{2}', '', text)
            text = re.sub(r'서울\s*[가-힣]+\s*[가-힣]+\s*딜링룸.*?있다\.', '', text)
            text = re.sub(r'확대\s*축소\s*공유하기.*?(?=\S)', '', text)
            text = re.sub(r'©.*?(?=\S)', '', text)
            text = re.sub(r'무단\s*전재.*?(?=\S)', '', text)
            text = re.sub(r'저작권.*?(?=\S)', '', text)
            text = re.sub(r'\s+', ' ', text).strip()

            return compact_summary(text)

    except:
        pass
    return ""

def compact_summary(text):
    """원문 앞부분의 완결된 문장 최대 3개를 두 문단으로 발췌한다."""
    sentences = re.split(r'(?<=[.!?])\s+', re.sub(r'\s+', ' ', text).strip())
    result = []
    for sentence in sentences:
        if len(sentence) <= 20 or not sentence.endswith(('.', '!', '?')):
            continue
        if sentence in result:
            continue
        if len('\n\n'.join(result + [sentence])) > 650:
            break
        result.append(sentence)
        if len(result) == 3:
            break
    if len(result) > 1:
        return result[0] + '\n\n' + ' '.join(result[1:])
    return ' '.join(result)


def fetch_articles(url, domain, href_filter=None):
    articles = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")
        seen = set()
        for a in soup.select("a"):
            href = a.get("href", "")
            title = clean_title(a.get_text(separator=" ", strip=True))
            if len(title) < 10:
                continue
            if is_invalid(title):
                continue
            if not has_company_event(title):
                continue
            if href_filter and href_filter not in href:
                continue
            if "ranking" in href or "ntype=RANKING" in href:
                continue
            full_url = urljoin(domain, href)
            if urlparse(full_url).scheme not in ("http", "https"):
                continue
            base_domain = urlparse(domain).hostname
            host = urlparse(full_url).hostname or ""
            allowed = host == base_domain or host.endswith('.' + base_domain)
            if base_domain == "news.naver.com":
                allowed = host in ("news.naver.com", "n.news.naver.com")
            if not allowed:
                continue
            if full_url in seen:
                continue
            seen.add(full_url)
            articles.append((title, full_url, get_priority(title)))
    except:
        pass
    return articles

def normalize_title(title):
    return re.sub(r'[^\w]', '', title)

def load_sent_titles():
    try:
        with open(SENT_LOG_PATH, encoding="utf-8") as f:
            return list(dict.fromkeys(json.load(f)))
    except Exception:
        return []

def save_sent_titles(sent_titles, newly_sent_title):
    updated = [title for title in sent_titles if title != newly_sent_title]
    updated = updated[-(SENT_LOG_KEEP - 1):] + [newly_sent_title]
    os.makedirs(os.path.dirname(SENT_LOG_PATH), exist_ok=True)
    with open(SENT_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)

def fetch_popular_articles():
    """실행 시점의 매체별 인기 순위이며 전체 매체 통합 순위는 아니다."""
    articles = []
    try:
        res = requests.get(RANKING_URL, headers=HEADERS, timeout=10)
        res.raise_for_status()
        # 레거시 랭킹 페이지는 EUC-KR로 제공된다.
        res.encoding = "euc-kr"
        soup = BeautifulSoup(res.text, "html.parser")
        for item in soup.select('.rankingnews_box .rankingnews_list > li'):
            link = item.select_one('a.list_title')
            rank_tag = item.select_one('.list_ranking_num')
            if not link or not rank_tag:
                continue
            url = link.get('href', '')
            parsed = urlparse(url)
            match = re.fullmatch(r'/(?:mnews/)?article/(\d+)/(\d+)', parsed.path)
            if parsed.hostname != 'n.news.naver.com' or not match or match[1] not in BUSINESS_PRESS:
                continue
            title = clean_title(link.get_text(' ', strip=True))
            if is_invalid(title) or not has_company_event(title):
                continue
            rank_match = re.search(r'\d+', rank_tag.get_text())
            if not rank_match or not 1 <= int(rank_match[0]) <= 5:
                continue
            rank = int(rank_match[0])
            articles.append((title, 'https://n.news.naver.com' + parsed.path,
                             10000 + (6 - rank) * 1000 + get_priority(title)))
    except (requests.RequestException, ValueError) as exc:
        print(f"인기 기사 수집 실패: {type(exc).__name__}; 일반 기업 뉴스로 대체합니다.")
    return articles


def pick_best_article(sent_titles):
    # 매 실행마다 갱신된 인기 목록을 먼저 넣어 같은 제목의 일반 기사보다 우선한다.
    all_articles = fetch_popular_articles()
    all_articles += fetch_articles("https://news.naver.com/breakingnews/section/101/258", "https://news.naver.com", "article")
    all_articles += fetch_articles("https://news.naver.com/breakingnews/section/101/261", "https://news.naver.com", "article")
    all_articles += fetch_articles("https://www.fnnews.com/section/002001000", "https://www.fnnews.com")
    all_articles += fetch_articles("https://www.sedaily.com/market", "https://www.sedaily.com")
    all_articles += fetch_articles("https://www.sedaily.com/economy", "https://www.sedaily.com")
    all_articles += fetch_articles("https://www.businesspost.co.kr/BP?command=sub&sub=2", "https://www.businesspost.co.kr")

    seen_titles = set()
    unique = []
    for title, url, score in all_articles:
        if is_invalid(title) or not has_company_event(title):
            continue
        t = normalize_title(title)
        if t not in seen_titles:
            seen_titles.add(t)
            unique.append((title, url, score))

    unique.sort(key=lambda x: x[2], reverse=True)

    today = datetime.now(KST).date()
    for title, url, score in unique:
        if normalize_title(title) in sent_titles:
            continue
        # 섹션 목록 페이지엔 전날 기사가 계속 걸려있는 경우가 있어,
        # 실제 발행일을 확인해 오늘 기사가 아니면 건너뛴다.
        pub_date = get_article_date(url)
        if pub_date != today:
            continue
        return title, url

    return None

def build_message(article):
    title, url = article
    summary = get_article_summary(url, title)
    msg = "🔜 <b>" + escape(title) + "</b>\n\n"
    if summary:
        msg += escape(summary) + "\n\n"
    msg += escape(url)
    return msg

def send_telegram(message):
    api_url = "https://api.telegram.org/bot" + os.environ["TELEGRAM_BOT_TOKEN"] + "/sendMessage"
    payload = {
        "chat_id": os.environ["TELEGRAM_CHAT_ID"],
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    res = requests.post(api_url, json=payload, timeout=10)
    res.raise_for_status()
    print("전송 완료")

if __name__ == "__main__":
    # 늦어진 예약 실행은 야간에 보내지 않는다. 수동 실행은 즉시 전송한다.
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule" and not in_send_window(datetime.now(KST)):
        print("발송 시간대가 지나 이번 회차는 건너뜁니다.")
        raise SystemExit(0)
    print("뉴스 수집 중...")
    sent_titles = load_sent_titles()
    article = pick_best_article(sent_titles)
    if article is None:
        print("새로 보낼 핫뉴스가 없어 이번 회차는 건너뜁니다.")
        raise SystemExit(0)
    msg = build_message(article)
    print(msg)
    send_telegram(msg)
    save_sent_titles(sent_titles, normalize_title(article[0]))
