"""notify.py の振り分け・要約ロジックのテスト（ネットワーク不要）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import notify  # noqa: E402
from fetch_feed import classify  # noqa: E402


def e(content, title="府県気象情報"):
    return {"content": content, "title": title, "author": "x", "updated": "2026-09-21T00:00:00Z"}


def test_topic_nested_brackets():
    assert notify.topic_of(e("【奄美地方（鹿児島県）気象解説情報（台風第２６号）】")) == "台風第２６号"
    assert notify.topic_of(e("【九州北部地方（山口県を含む）気象解説情報（大雨・落雷・突風）】")) == "大雨・落雷・突風"
    assert notify.topic_of(e("【千葉県レベル４土砂災害危険警報】", "土砂災害警戒情報")) == "土砂災害警戒情報"


def test_region_names():
    assert notify.region_of(e("【北海道地方気象解説情報（大雨）】", "地方気象情報")) == "北海道"
    assert notify.region_of(e("【沖縄本島地方気象解説情報（台風）】")) == "沖縄本島"
    assert notify.region_of(e("【神奈川県気象解説情報（台風）】")) == "神奈川"
    assert notify.region_of(e("【東京都気象解説情報（台風）】")) == "東京"


def test_hazard_levels():
    hz = notify.hazards_of("【静岡県気象解説情報（台風第２５号）】静岡県では、土砂災害に、暴風に厳重に警戒してください。"
                           "また、低い土地の浸水、河川の増水や氾濫に、高波に警戒してください。")
    assert hz["土砂"] == 3 and hz["暴風"] == 3
    assert hz["浸水"] == 2 and hz["河川"] == 2 and hz["高波"] == 2
    hz = notify.hazards_of("土砂災害に厳重に警戒し、浸水に警戒してください。特に、線状降水帯が発生する可能性があります。")
    assert hz["線状降水帯"] == 3 and hz["土砂"] == 3 and hz["浸水"] == 2


def test_bulletin_copy_is_dropped():
    # 府県気象情報として流れる気象防災速報の写しは、府県気象防災速報（段階C）と重複するので読まない
    assert classify("府県気象情報", "【福岡県気象防災速報（線状降水帯直前予測）】今後３時間以内に線状降水帯") is None
    assert classify("府県気象解説情報", "【静岡県気象解説情報（台風第２５号）】台風") is None


def test_typhoon_is_always_wide():
    st = {"topics": {}}
    assert notify.is_wide("台風第２６号", st)
    assert not notify.is_wide("大雨・落雷・突風", st)
    st["topics"]["大雨・落雷・突風"] = {"福岡": "t", "熊本": "t", "佐賀": "t", "長崎": "t"}
    assert notify.is_wide("大雨・落雷・突風", st)
