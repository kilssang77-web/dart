"""ml/prism.py 단위 테스트 — scan_prism_zones 10개 반환 및 floor 필터"""
import sys
from unittest.mock import MagicMock, patch
import numpy as np

# ML 라이브러리 미설치 환경 대응
for _mod in ("joblib", "lightgbm", "xgboost", "sklearn",
             "sklearn.cluster", "sklearn.preprocessing", "sklearn.impute"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest


# ── 픽스처 ───────────────────────────────────────────────────

BASE_AMOUNT = 500_000_000


def _make_db():
    db = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = None
    mock_result.fetchall.return_value = []
    db.execute.return_value = mock_result
    return db


def _fake_load_srate_stats(*_args, **_kwargs):
    return {
        "agency_srate_mean": 0.8900,
        "agency_srate_std":  0.012,
        "global_srate_mean": 0.8900,
        "global_srate_std":  0.012,
        "expected_competitor_count": 8,
        "global_comp_count": 8,
    }


def _fake_predict_srate(features, base_amount):
    return {
        "srate_range": {
            "p10":    0.875,
            "lower":  0.882,
            "center": 0.890,
            "upper":  0.898,
            "p90":    0.905,
        }
    }


# ── 테스트 ──────────────────────────────────────────────────

class TestScanPrismZones:
    def _run(self, inpo_rates=None):
        """scan_prism_zones 호출 헬퍼 (mock 주입)."""
        db = _make_db()
        with (
            patch("app.ml.prism.load_srate_stats", side_effect=_fake_load_srate_stats),
            patch("app.ml.prism.predict_srate",    side_effect=_fake_predict_srate),
            patch("app.ml.prism.get_inpo_raw_rates", return_value=inpo_rates),
        ):
            # import 후 scan_prism_zones 내부에서 assessment/rank_model 재참조하므로
            # 직접 import하여 호출
            from app.ml.prism import scan_prism_zones
            return scan_prism_zones(
                base_amount=BASE_AMOUNT,
                industry_name="토목공사업",
                agency_id=1,
                industry_id=1,
                db=db,
                n_sim=5_000,
            )

    def test_top10_returns_exactly_10(self):
        _, top10 = self._run()
        assert len(top10) == 10

    def test_all_zones_count(self):
        all_zones, _ = self._run()
        # 0.860 ~ 0.930 step 0.001 = 71점 = 70구간(endpoint 포함)
        assert len(all_zones) == 71

    def test_floor_not_ok_excluded_from_top10(self):
        _, top10 = self._run()
        assert all(z["floor_ok"] for z in top10)

    def test_floor_not_ok_win_prob_zero(self):
        all_zones, _ = self._run()
        for z in all_zones:
            if not z["floor_ok"]:
                assert z["win_prob"] == 0.0

    def test_top10_sorted_by_win_prob_desc(self):
        _, top10 = self._run()
        probs = [z["win_prob"] for z in top10]
        assert probs == sorted(probs, reverse=True)

    def test_zone_keys(self):
        all_zones, _ = self._run()
        required = {"rate", "win_prob", "floor_ok", "amount", "rank_est"}
        for z in all_zones:
            assert required.issubset(z.keys())

    def test_amount_equals_base_times_rate(self):
        all_zones, _ = self._run()
        for z in all_zones:
            assert z["amount"] == round(BASE_AMOUNT * z["rate"])

    def test_with_empirical_rates(self):
        emp = np.random.default_rng(0).uniform(0.860, 0.930, 500)
        _, top10 = self._run(inpo_rates=emp)
        assert len(top10) == 10

    def test_without_empirical_rates(self):
        _, top10 = self._run(inpo_rates=None)
        assert len(top10) == 10

    def test_rate_range_0860_to_0930(self):
        all_zones, _ = self._run()
        rates = [z["rate"] for z in all_zones]
        assert min(rates) == pytest.approx(0.860, abs=1e-4)
        assert max(rates) == pytest.approx(0.930, abs=1e-4)
