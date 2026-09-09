import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hourly', ROOT / 'pharma-news/scripts/send_hourly_news.py')
news = importlib.util.module_from_spec(spec)
spec.loader.exec_module(news)


class HourlyNewsTests(unittest.TestCase):
    def test_summary_preserves_decimal_and_limits_sentences(self):
        first = 'SOL AI반도체소부장 ETF의 최근 1개월 수익률은 23.14%를 기록했다.'
        second = 'AI 인프라 투자 확대와 반도체 업황 회복이 영향을 줬다.'
        summary = news.compact_summary(first + ' ' + second + ' ' + second)
        self.assertEqual(summary, first + '\n\n' + second)

    def test_long_sentence_and_incomplete_tail_do_not_overflow(self):
        summary = news.compact_summary('반도체 기업의 실적 개선 기대가 높아지고 있다. 미완성 문장')
        self.assertEqual(summary, '반도체 기업의 실적 개선 기대가 높아지고 있다.')
        self.assertEqual(news.compact_summary('가' * 651 + '. 다음 문장은 앞 문장을 건너뛰어 발췌하지 않는다.'), '')
        self.assertLessEqual(len(summary), 650)

    def test_telegram_escapes_article_html(self):
        with patch.object(news, 'get_article_summary', return_value='실적 <개선> & 성장.\n\n두 번째 문장.'):
            msg = news.build_message(('반도체 <기업> & 실적', 'https://example.com/?a=1&b=2'))
        self.assertIn('&lt;기업&gt; &amp;', msg)
        self.assertEqual(msg, '🔜 <b>반도체 &lt;기업&gt; &amp; 실적</b>\n\n실적 &lt;개선&gt; &amp; 성장.\n\n두 번째 문장.\n\nhttps://example.com/?a=1&amp;b=2')

    def test_product_news_is_excluded_even_with_company_event(self):
        for title in ['신한운용 SOL AI반도체 ETF 순자산 1조 돌파',
                      '삼성자산운용, 반도체 신제품 etf 출시',
                      '반도체 수주 기업 담은 펀드 수익률 1위']:
            self.assertTrue(news.is_invalid(title), title)

    def test_company_events_include_small_companies_and_negative_events(self):
        for title in ['새빛테크, 글로벌 고객과 공급계약 체결',
                      '한미약품 신약 임상 3상 성공', '삼성전자 대규모 리콜 발표']:
            self.assertFalse(news.is_invalid(title), title)
            self.assertTrue(news.has_company_event(title), title)
        self.assertFalse(news.has_company_event('반도체 AI 기대감에 코스피 상승'))

    def test_no_matching_company_event_skips_round(self):
        with patch.object(news, 'fetch_articles', return_value=[('신한운용 반도체 ETF 수익률 1위', 'https://example.com', 99)]):
            self.assertIsNone(news.pick_best_article([]))

    def test_excerpt_uses_original_sentences_in_order(self):
        sentences = [f'기업은 신규 생산 시설에 대한 투자 계획 {i}단계를 공개했다.' for i in range(4)]
        self.assertEqual(news.compact_summary(' '.join(sentences)), sentences[0] + '\n\n' + ' '.join(sentences[1:3]))

    def test_naver_mobile_article_is_collected_but_external_host_is_not(self):
        from unittest.mock import Mock
        html = '<a href="https://n.news.naver.com/mnews/article/001/123">새빛테크, 글로벌 공급계약 체결</a><a href="https://example.com/news.naver.com/article">다른기업, 글로벌 공급계약 체결</a>'
        with patch.object(news.requests, 'get', return_value=Mock(text=html)):
            articles = news.fetch_articles('https://news.naver.com/list', 'https://news.naver.com', 'article')
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0][1], 'https://n.news.naver.com/mnews/article/001/123')

    def test_history_keeps_chronological_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sent.json'
            path.write_text(json.dumps(['old', 'middle', 'new']), encoding='utf-8')
            with patch.object(news, 'SENT_LOG_PATH', str(path)), patch.object(news, 'SENT_LOG_KEEP', 3):
                news.save_sent_titles(news.load_sent_titles(), 'latest')
                self.assertEqual(news.load_sent_titles(), ['middle', 'new', 'latest'])

    def test_workflow_runs_every_90_minutes_in_daytime(self):
        import re
        workflow = (ROOT / '.github/workflows/hourly_news.yml').read_text(encoding='utf-8')
        times = []
        for minute, hours in re.findall(r'cron: "(\d+) ([\d,]+) \* \* \*"', workflow):
            times.extend(((int(hour) + 9) % 24) * 60 + int(minute) for hour in hours.split(','))
        self.assertEqual(sorted(times), list(range(9 * 60, 21 * 60 + 1, 90)))


if __name__ == '__main__':
    unittest.main()
