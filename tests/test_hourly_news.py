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
        self.assertEqual(summary, first + '\n' + second)

    def test_long_sentence_and_incomplete_tail_do_not_overflow(self):
        summary = news.compact_summary('가' * 250 + '. ' + '반도체 기업의 실적 개선 기대가 높아지고 있다. 미완성 문장')
        self.assertEqual(summary, '반도체 기업의 실적 개선 기대가 높아지고 있다.')
        self.assertLessEqual(len(summary), 240)

    def test_telegram_escapes_article_html(self):
        with patch.object(news, 'get_article_summary', return_value='실적 <개선> & 성장.\n두 번째 문장.'):
            msg = news.build_message(('반도체 <기업> & 실적', 'https://example.com/?a=1&b=2'))
        self.assertIn('&lt;기업&gt; &amp;', msg)
        self.assertIn('• 실적 &lt;개선&gt; &amp; 성장.', msg)
        self.assertIn('href="https://example.com/?a=1&amp;b=2"', msg)
        self.assertIn('원문 보기</a>', msg)

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
