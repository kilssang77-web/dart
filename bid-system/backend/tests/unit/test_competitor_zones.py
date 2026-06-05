"""CompetitorZoneService 단위 테스트 — 빈 결과 처리 검증"""
import sys
from unittest.mock import MagicMock

# ML 라이브러리 미설치 환경 대응
for _mod in ("joblib", "lightgbm", "xgboost", "sklearn",
             "sklearn.cluster", "sklearn.preprocessing", "sklearn.impute"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest
from app.services import CompetitorZoneService


class TestCompetitorZoneService:
    def setup_method(self):
        self.svc = CompetitorZoneService()

    def _make_db(self, competitor=None, rows=None):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = competitor
        db.execute.return_value.fetchall.return_value = rows or []
        return db

    def test_empty_when_competitor_not_found(self):
        db = self._make_db(competitor=None)
        result = self.svc.get_recent_zones(db, competitor_id=999)
        assert result["zones"] == []
        assert result["peak_zone"] is None
        assert result["total_count"] == 0
        db.execute.assert_not_called()

    def test_empty_when_no_biz_reg_no(self):
        competitor = MagicMock()
        competitor.biz_reg_no = None
        db = self._make_db(competitor=competitor)
        result = self.svc.get_recent_zones(db, competitor_id=1)
        assert result["zones"] == []
        assert result["total_count"] == 0
        db.execute.assert_not_called()

    def test_empty_when_no_inpo21c_data(self):
        competitor = MagicMock()
        competitor.biz_reg_no = "123-45-67890"
        db = self._make_db(competitor=competitor, rows=[])
        result = self.svc.get_recent_zones(db, competitor_id=1)
        assert result["zones"] == []
        assert result["peak_zone"] is None
        assert result["total_count"] == 0

    def test_zones_computed_correctly(self):
        competitor = MagicMock()
        competitor.biz_reg_no = "111-22-33333"
        rows = [(0.870,), (0.870,), (0.875,), (0.880,)]
        db = self._make_db(competitor=competitor, rows=rows)
        result = self.svc.get_recent_zones(db, competitor_id=2)
        assert result["total_count"] == 4
        assert len(result["zones"]) > 0
        # 피크 구간 = 0.870 버킷 (2건)
        assert result["peak_zone"] is not None
        assert result["peak_zone"]["count"] == 2
        # 모든 pct 합계는 100%
        total_pct = sum(z["pct"] for z in result["zones"])
        assert abs(total_pct - 100.0) < 0.5

    def test_days_param_accepted(self):
        competitor = MagicMock()
        competitor.biz_reg_no = "999-88-77777"
        db = self._make_db(competitor=competitor, rows=[(0.900,)])
        result_90  = self.svc.get_recent_zones(db, competitor_id=3, days=90)
        result_180 = self.svc.get_recent_zones(db, competitor_id=3, days=180)
        assert result_90["total_count"] == result_180["total_count"]
