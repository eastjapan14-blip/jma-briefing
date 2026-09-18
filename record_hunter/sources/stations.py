"""地点マスタ。

amedastable.json（気象庁）: 観測所番号 → 名前・緯度経度・標高。
data/etrn_index.json（tools/build_etrn_index.py で一度だけ生成）: 観測所番号 → 過去の気象データ検索の prec_no / block_no。
"""
import json
from pathlib import Path
from typing import Optional

from ..log import log

ETRN_INDEX = Path(__file__).resolve().parent.parent / "data" / "etrn_index.json"
AMEDAS_TABLE_URL = "https://www.jma.go.jp/bosai/amedas/const/amedastable.json"
ETRN_VIEW = "https://www.data.jma.go.jp/stats/etrn/view"

# etrn の prec_no → 都道府県（北海道は地方区分をまとめて「北海道」）。select/prefecture00.php の表記より。
PREC_PREF = {**{str(n): "北海道" for n in range(11, 25)},
             "31": "青森県", "32": "秋田県", "33": "岩手県", "34": "宮城県", "35": "山形県", "36": "福島県",
             "40": "茨城県", "41": "栃木県", "42": "群馬県", "43": "埼玉県", "44": "東京都", "45": "千葉県", "46": "神奈川県",
             "48": "長野県", "49": "山梨県", "50": "静岡県", "51": "愛知県", "52": "岐阜県", "53": "三重県", "54": "新潟県",
             "55": "富山県", "56": "石川県", "57": "福井県", "60": "滋賀県", "61": "京都府", "62": "大阪府", "63": "兵庫県",
             "64": "奈良県", "65": "和歌山県", "66": "岡山県", "67": "広島県", "68": "島根県", "69": "鳥取県",
             "71": "徳島県", "72": "香川県", "73": "愛媛県", "74": "高知県", "81": "山口県", "82": "福岡県", "83": "大分県",
             "84": "長崎県", "85": "佐賀県", "86": "熊本県", "87": "宮崎県", "88": "鹿児島県", "91": "沖縄県", "99": "南極"}


class Stations:
    def __init__(self, table: Optional[dict] = None, index: Optional[dict] = None):
        self.table = table or {}
        self.index = index if index is not None else self._load_index()
        self.by_name = {}
        for sid, row in self.table.items():
            self.by_name.setdefault(row.get("kjName", ""), []).append(sid)
        for sid, row in self.index.items():
            if row.get("name") and sid not in self.by_name.get(row["name"], []):
                self.by_name.setdefault(row["name"], []).append(sid)
        self.pref_of = {sid: PREC_PREF.get(row.get("prec", ""), "") for sid, row in self.index.items()}

    @staticmethod
    def _load_index() -> dict:
        if ETRN_INDEX.exists():
            return json.loads(ETRN_INDEX.read_text(encoding="utf-8"))
        return {}

    @classmethod
    def load(cls, fetcher):
        r = fetcher.get(AMEDAS_TABLE_URL)
        table = {}
        if r.ok:
            try:
                table = json.loads(r.body.decode("utf-8"))
            except ValueError:
                log("parse", "parser_warning", source="amedastable", reason="invalid json")
        return cls(table)

    def register(self, obs_list):
        for o in obs_list:
            if o.station_id:
                self.pref_of[o.station_id] = o.pref   # CSV の都道府県を優先
                if o.name and o.station_id not in self.by_name.get(o.name, []):
                    self.by_name.setdefault(o.name, []).append(o.station_id)

    def find_id(self, name: str, pref: str) -> Optional[str]:
        ids = self.by_name.get(name, [])
        if len(ids) == 1:
            return ids[0]
        for sid in ids:
            if self.pref_of.get(sid) == pref:
                return sid
        return None

    def etrn(self, station_id: str) -> Optional[dict]:
        return self.index.get(station_id)

    def rank_url(self, station_id: str, month: Optional[int] = None) -> Optional[str]:
        e = self.etrn(station_id)
        if not e:
            return None
        m = f"{month}" if month else ""
        view = "h0" if month else ""
        return f'{ETRN_VIEW}/rank_{e["kind"]}.php?prec_no={e["prec"]}&block_no={e["block"]}&year=&month={m}&day=&view={view}'

    def meta(self, station_id: str) -> dict:
        row = self.table.get(station_id) or {}
        out = {}
        if "lat" in row:
            out["latitude"] = round(row["lat"][0] + row["lat"][1] / 60, 4)
            out["longitude"] = round(row["lon"][0] + row["lon"][1] / 60, 4)
            out["elevation"] = row.get("alt")
        return out
