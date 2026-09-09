# 📰 제약·바이오 뉴스 자동 텔레그램 봇

## 주요 뉴스 정기 발송

`hourly_news.yml`은 한국시간 매일 09:00, 10:30, 12:00, 13:30,
15:00, 16:30, 18:00, 19:30, 21:00에 실행됩니다(90분 간격).
GitHub Actions 대기열 때문에 실제 발송 시각은 지연될 수 있습니다.
예약 실행이 22시 이후로 지연되면 건너뛰며, 수동 실행은 즉시 발송합니다.

회차마다 중복되지 않는 주요 기사 1건을 제목, 원문 발췌 최대 2문장(240자),
`원문 보기` 링크로 전송합니다. 적합한 새 기사가 없으면 발송하지 않습니다.
완결된 문장을 길이 제한 안에서 추출할 수 없으면 제목과 링크만 표시합니다.
최근 90건의 제목을 순서대로 보관해 중복 발송을 방지합니다.

시간 변경은 `.github/workflows/hourly_news.yml`의 UTC cron 두 줄에서,
본문 형식 변경은 `scripts/send_hourly_news.py`의 `compact_summary`와
`build_message`에서 할 수 있습니다.

매일 아침 8시, 약업닷컴 + 팜뉴스 최신 기사를 텔레그램으로 자동 전송합니다.

---

## ⚙️ 설정 방법 (5분이면 완료!)

### 1단계 — GitHub 저장소 만들기
1. [github.com](https://github.com) 로그인
2. 우상단 `+` → `New repository`
3. 이름 입력 (예: `pharma-news-bot`) → `Create repository`
4. 이 폴더의 파일들을 업로드 (또는 git push)

### 2단계 — 텔레그램 정보 입력 (Secrets 등록)
1. GitHub 저장소 → `Settings` 탭
2. 왼쪽 메뉴 `Secrets and variables` → `Actions`
3. `New repository secret` 버튼 클릭
4. 아래 두 개를 각각 추가:

| Name | Value |
|------|-------|
| `TELEGRAM_BOT_TOKEN` | 봇 토큰 (예: `123456:ABC-DEF...`) |
| `TELEGRAM_CHAT_ID` | 채팅 ID (예: `-1001234567890`) |

### 3단계 — Actions 활성화
1. 저장소 → `Actions` 탭
2. `I understand my workflows, go ahead and enable them` 클릭

### 4단계 — 테스트 실행
1. `Actions` 탭 → `매일 아침 제약 뉴스 전송` 클릭
2. `Run workflow` 버튼으로 즉시 테스트 가능

---

## 📬 결과물 예시
```
📰 제약·바이오 뉴스브리핑
2026년 05월 21일 오전 8시

━━━━━━━━━━━━━━━━
🔹 약업닷컴
[한올바이오 아이메로프루바트, 난치성 류마티스관절염 효능 확인](링크)
...

━━━━━━━━━━━━━━━━
🔹 팜뉴스
[식당 설명회는 죄가 없다...제약영업 합법의 선 지키는 10계명](링크)
...
```

---

## ❓ 채팅 ID 모르는 경우
텔레그램에서 `@userinfobot` 에게 아무 메시지나 보내면 ID를 알려줍니다.
그룹/채널에 봇을 추가한 경우, `@getidsbot` 을 그룹에 초대하면 그룹 ID를 알 수 있습니다.
