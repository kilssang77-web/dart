"""ml/a_value.py 단위 테스트 — 경계값 및 공종별 하한율"""
import pytest
from app.ml.a_value import (
    calc_a_value,
    calc_floor_price,
    calc_floor_rate,
    calc_bid_range,
    DEFAULT_FLOOR_RATE,
)


class TestCalcAValue:
    def test_basic(self):
        assert calc_a_value(1_000_000_000, 0.9000) == 900_000_000

    def test_rounding(self):
        # 반올림 확인
        result = calc_a_value(100_000_001, 0.88)
        assert isinstance(result, int)
        assert result == round(100_000_001 * 0.88)

    def test_zero_srate(self):
        assert calc_a_value(500_000_000, 0.0) == 0

    def test_large_amount(self):
        assert calc_a_value(10_000_000_000, 0.8850) == 8_850_000_000


class TestCalcFloorPrice:
    def test_default_rate(self):
        a_val = 900_000_000
        result = calc_floor_price(a_val, DEFAULT_FLOOR_RATE)
        assert result == round(a_val * DEFAULT_FLOOR_RATE)

    def test_electric_rate(self):
        # 전기공사업: 86.745%
        result = calc_floor_price(1_000_000_000, 0.86745)
        assert result == 867_450_000

    def test_zero_a_value(self):
        assert calc_floor_price(0, DEFAULT_FLOOR_RATE) == 0


class TestCalcFloorRate:
    def test_default_industry(self):
        assert calc_floor_rate("토목공사업") == DEFAULT_FLOOR_RATE

    def test_electric(self):
        assert calc_floor_rate("전기공사업") == 0.86745

    def test_telecom(self):
        assert calc_floor_rate("정보통신공사업") == 0.86745

    def test_fire(self):
        assert calc_floor_rate("소방시설공사업") == 0.86745

    def test_empty_string(self):
        assert calc_floor_rate("") == DEFAULT_FLOOR_RATE

    def test_partial_match(self):
        # 공종명에 키워드 포함 시 매칭
        assert calc_floor_rate("(주)전기공사업체") == 0.86745


class TestCalcBidRange:
    def test_structure(self):
        res = calc_bid_range(
            base_amount=1_000_000_000,
            srate_center=0.9000,
            srate_std=0.012,
            industry_name="토목공사업",
        )
        assert "a_value" in res
        assert "floor_price" in res
        assert "floor_rate" in res
        assert "srate_center" in res
        assert "srate_range" in res
        for key in ("p10", "p25", "p50", "p75", "p90"):
            assert key in res["srate_range"]

    def test_a_value_correct(self):
        res = calc_bid_range(1_000_000_000, 0.9000, 0.012, "토목공사업")
        assert res["a_value"] == 900_000_000

    def test_floor_price_correct(self):
        res = calc_bid_range(1_000_000_000, 0.9000, 0.012, "토목공사업")
        assert res["floor_price"] == round(900_000_000 * DEFAULT_FLOOR_RATE)

    def test_percentile_order(self):
        res = calc_bid_range(500_000_000, 0.8850, 0.012, "일반건설업")
        sr = res["srate_range"]
        assert sr["p10"] <= sr["p25"] <= sr["p50"] <= sr["p75"] <= sr["p90"]

    def test_explicit_percentiles(self):
        res = calc_bid_range(
            base_amount=1_000_000_000,
            srate_center=0.885,
            srate_std=0.012,
            industry_name="토목",
            srate_p10=0.870,
            srate_p25=0.878,
            srate_p75=0.892,
            srate_p90=0.900,
        )
        assert res["srate_range"]["p10"] == pytest.approx(0.870, abs=1e-6)
        assert res["srate_range"]["p90"] == pytest.approx(0.900, abs=1e-6)
