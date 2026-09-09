import os
import re
import requests
from bs4 import BeautifulSoup
import anthropic
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

ARTICLE_SELECTORS = [
    "#dic_area", "#articleBodyContents", "#articeBody", "#articleBody",
    ".article_body", ".news_body", "#newsct_article", "article",
    ".article-body", "#article_content", ".article-content",
    "#article-view-content-div", ".article_txt", ".view_text"
]

def fetch_article(url):
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")

    og_title = soup.find("meta", property="og:title")
    title = og_title["content"].strip() if og_title and og_title.get("content") else ""

    for tag in soup(["script", "style", "header", "footer", "nav", "aside", "iframe"]):
        tag.decompose()

    content_el = None
    for sel in ARTICLE_SELECTORS:
        content_el = soup.select_one(sel)
        if content_el:
            break

    text = content_el.get_text(separator=" ", strip=True) if content_el else soup.get_text(separator=" ", strip=True)
    text = re.sub(r'\S+@\S+\.\S+', '', text)
    text = re.sub(r'\[.*?기자.*?\]', '', text)
    text = re.sub(r'[가-힣]+ 기자', '', text)
    text = re.sub(r'[가-힣]+ 특파원', '', text)
    text = re.sub(r'©.*?(?=\s)', '', text)
    text = re.sub(r'무단\s*전재.*?(?=\s)', '', text)
    text = re.sub(r'\s+', ' ', text).strip()

    return title, text[:3000]

def summarize(title, body, url):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""다음 기사를 읽고 아래 형식으로만 출력해. 다른 설명 없이 형식 그대로만.

규칙:
- 핵심 키워드는 2개 이내로 작성
- 핵심 내용은 3~5개. 정보가 적으면 더 적게 쓰고 개수를 채우기 위해 반복하지 않기
- 중요한 기업 이벤트를 먼저 쓰고 수치·일정·계약 상대방은 원문대로 유지
- 각 항목은 짧고 자연스러운 한국어 문장으로 작성. 과장·투자 권유·원문에 없는 해석 금지
- 기사에 담긴 전망이나 주장은 발표 주체를 밝혀 확정 사실과 구분
- HTML은 <b>만 사용하고 본문 속 &, <, >는 각각 &amp;, &lt;, &gt;로 이스케이프
- 마크다운 코드 블록이나 별표 강조는 사용하지 않기
- 번호 사이 빈 줄 한 칸씩

제목: {title}
본문: {body}

=== 출력 형식 (HTML, 이 형식 그대로) ===
🔜 <b>{title}</b>

핵심 키워드 · 키워드1, 키워드2

<b>주요 내용</b>
1. 가장 중요한 기업 이벤트와 핵심 수치.

2. 구체적인 내용과 배경.

3. 원문에서 확인되는 일정이나 후속 계획.
(원문에 근거가 있는 항목만 출력하고 이 안내 문장은 생략)"""

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text.strip() + f"\n\n{url}"

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    urls = re.findall(r'https?://[^\s]+', text)
    if not urls:
        return

    if not ANTHROPIC_API_KEY:
        await update.message.reply_text("요약 서비스 설정을 확인해야 합니다. 관리자에게 문의해 주세요.")
        return

    status = await update.message.reply_text("기사의 핵심 내용을 정리하고 있습니다.")
    try:
        title, body = fetch_article(urls[0])
        if not title and not body:
            await status.edit_text("기사 본문을 불러오지 못했습니다. 원문 링크가 열리는지 확인해 주세요.")
            return
        result = summarize(title, body, urls[0])
        await status.edit_text(result, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        print(f"링크 요약 실패: {type(e).__name__}")
        await status.edit_text("기사 요약을 완료하지 못했습니다. 잠시 후 링크를 다시 보내 주세요.")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'https?://'), on_message))
    print("링크 요약 봇 실행 중...")
    app.run_polling()

if __name__ == "__main__":
    main()
