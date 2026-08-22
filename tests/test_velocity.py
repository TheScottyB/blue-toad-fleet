from src.velocity import (
    CADENCE_DAYS, WINDOW_DAYS, clears_within_cadence, days_of_supply,
)


class TestDaysOfSupply:
    def test_100_active_900_sold_in_90_days_is_10_days(self):
        assert days_of_supply(900, 100, 90) == 10.0

    def test_no_sales_is_unknown_not_zero(self):
        assert days_of_supply(0, 100) is None

    def test_empty_active_with_sales_is_zero_days(self):
        assert days_of_supply(10, 0) == 0.0


class TestFourteenDayCadence:
    def test_10_day_supply_clears_in_two_weeks(self):
        assert clears_within_cadence(900, 100) is True

    def test_30_day_supply_misses_the_cadence(self):
        # 100 active, 300 sold in 90 days → 30 days of supply
        assert days_of_supply(300, 100, 90) == 30.0
        assert clears_within_cadence(300, 100) is False

    def test_threshold_is_window_over_cadence(self):
        # sold/active == 90/14 exactly → 14.0 days
        sold = 100 * WINDOW_DAYS / CADENCE_DAYS
        assert abs(days_of_supply(sold, 100, 90) - 14.0) < 1e-9
        assert clears_within_cadence(sold, 100) is True
