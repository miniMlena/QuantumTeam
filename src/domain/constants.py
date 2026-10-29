# Стандартная сетка теноров (в месяцах), в которые мы приводим кривую
STANDARD_TENORS_MONTHS: list[int] = [
    1, 3, 6, 12, 24, 36, 60, 84, 120, 240, 360,
]

# теноры, которые MOEX публикует (observed в бд) ??
MOEX_OBSERVED_TENORS_MONTHS: set[int] = {1, 3, 6, 12, 24, 36, 60, 84, 120}

# Параметры Nelson-Siegel, которые приходят из MOEX
NS_PARAM_NAMES = ("b1", "b2", "b3", "t1")