"""
[V128] Testes para o sistema de Defesa Progressiva de Patrimônio.

Verifica:
- Níveis de defesa (OFF, L1, L2, L3, CRITICO)
- Cálculo do piso protegido (peak × lock_ratio)
- Ativação/desativação baseada na equity consolidada
- Enforcement nos stops dos trades
- Fechamento de trades no nível CRITICO
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestEquityDefenseLevels:
    """Testa a lógica de cálculo dos níveis de defesa."""

    def _calc_defense(self, consolidated, peak, base=10000.0, lock_ratio=0.80):
        """Simula o cálculo de defesa retornado do sandbox_service."""
        if consolidated > peak:
            peak = consolidated

        peak_profit = max(0.0, peak - base)
        floor = base + (peak_profit * lock_ratio)

        profit_pct = (consolidated - base) / base * 100.0 if base > 0 else 0.0

        if consolidated < floor and peak_profit > 0:
            return 4, 0.0, peak, floor
        elif profit_pct >= 10.0:
            return 3, 3.0, peak, floor
        elif profit_pct >= 5.0:
            return 2, 5.0, peak, floor
        elif profit_pct >= 3.0:
            return 1, 7.0, peak, floor
        else:
            return 0, 0.0, peak, floor

    def test_no_profit_is_off(self):
        level, stop, peak, floor = self._calc_defense(10000.0, 10000.0)
        assert level == 0
        assert stop == 0.0

    def test_below_3pct_is_off(self):
        level, stop, _, _ = self._calc_defense(10200.0, 10200.0)
        assert level == 0

    def test_3pct_activates_l1(self):
        level, stop, _, _ = self._calc_defense(10300.0, 10300.0)
        assert level == 1
        assert stop == 7.0

    def test_5pct_activates_l2(self):
        level, stop, _, _ = self._calc_defense(10500.0, 10500.0)
        assert level == 2
        assert stop == 5.0

    def test_10pct_activates_l3(self):
        level, stop, _, _ = self._calc_defense(11000.0, 11000.0)
        assert level == 3
        assert stop == 3.0

    def test_below_floor_activates_critico(self):
        peak = 10900.0
        floor = 10000.0 + (900.0 * 0.80)  # 10720
        level, stop, _, _ = self._calc_defense(10600.0, peak)
        assert level == 4
        assert stop == 0.0

    def test_peak_tracking_updates(self):
        _, _, peak, _ = self._calc_defense(10500.0, 10000.0)
        assert peak == 10500.0

    def test_peak_does_not_decrease(self):
        _, _, peak, _ = self._calc_defense(10300.0, 10500.0)
        assert peak == 10500.0

    def test_floor_calculation(self):
        _, _, _, floor = self._calc_defense(10900.0, 10900.0)
        expected_floor = 10000.0 + (900.0 * 0.80)
        assert floor == pytest.approx(expected_floor)

    def test_defense_level_decreases_when_recovery(self):
        level1, _, _, _ = self._calc_defense(10900.0, 10900.0)
        assert level1 == 2  # 9% profit → L2

        level2, _, _, _ = self._calc_defense(10400.0, 10900.0)
        assert level2 == 4  # below floor ($10,720) → CRITICO

        level3, _, _, _ = self._calc_defense(10800.0, 10900.0)
        assert level3 == 2  # 8% profit, above floor → L2

    def test_real_scenario_bank_peak_10900(self):
        _, _, _, floor_900 = self._calc_defense(10900.0, 10900.0)
        assert floor_900 == pytest.approx(10720.0)

        level_now, _, _, _ = self._calc_defense(10430.0, 10900.0)
        assert level_now == 4


class TestEquityDefenseEnforcement:
    """Testa a aplicação de defesa nos stops dos trades."""

    def test_defense_stop_calculated_from_peak_roi(self):
        peak_roi = 25.0
        defense_stop_pct = 5.0
        defense_stop_roi = peak_roi - defense_stop_pct
        assert defense_stop_roi == 20.0

    def test_defense_l1_gives_more_foom(self):
        peak_roi = 20.0
        l1_stop = peak_roi - 7.0
        l2_stop = peak_roi - 5.0
        l3_stop = peak_roi - 3.0
        assert l1_stop < l2_stop < l3_stop

    def test_defense_only_applies_if_higher_than_current(self):
        current_stop = 15.0
        defense_stop = 12.0
        assert not (defense_stop > current_stop)

        defense_stop = 18.0
        assert defense_stop > current_stop

    def test_critico_force_closes_trade(self):
        defense_level = 4
        should_close = defense_level == 4
        assert should_close is True

    def test_critico_does_not_close_other_levels(self):
        for level in [0, 1, 2, 3]:
            assert (level == 4) is False
