from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Bucket:
    """
    Временной бакет по стандарту Basel IRRBB.
      code        — короткое имя бакета (как в эталонном Excel: "1d", "3m", "10y")
      start_years — левая граница интервала, лет
      end_years   — правая граница интервала, лет (None — бакет открыт справа)
      tenor_years — середина бакета, лет: срок, на который относятся все потоки бакета
    """
    code: str
    start_years: float
    end_years: float | None
    tenor_years: float


# 19 бакетов Basel IRRBB. Середины бакетов совпадают с эталонным расчётом (лист «3108»)
BUCKETS: tuple[Bucket, ...] = (
    Bucket("1d",   0.0,    0.0028, 0.0028),
    Bucket("1m",   0.0028, 1 / 12, 0.0417),
    Bucket("3m",   1 / 12, 0.25,   0.1667),
    Bucket("6m",   0.25,   0.5,    0.375),
    Bucket("9m",   0.5,    0.75,   0.625),
    Bucket("1y",   0.75,   1.0,    0.875),
    Bucket("1.5y", 1.0,    1.5,    1.25),
    Bucket("2y",   1.5,    2.0,    1.75),
    Bucket("3y",   2.0,    3.0,    2.5),
    Bucket("4y",   3.0,    4.0,    3.5),
    Bucket("5y",   4.0,    5.0,    4.5),
    Bucket("6y",   5.0,    6.0,    5.5),
    Bucket("7y",   6.0,    7.0,    6.5),
    Bucket("8y",   7.0,    8.0,    7.5),
    Bucket("9y",   8.0,    9.0,    8.5),
    Bucket("10y",  9.0,    10.0,   9.5),
    Bucket("15y",  10.0,   15.0,   12.5),
    Bucket("20y",  15.0,   20.0,   17.5),
    Bucket("30y",  20.0,   None,   25.0),
)

BUCKETS_BY_CODE: dict[str, Bucket] = {b.code: b for b in BUCKETS}

# В какой точке бакета брать ставку с кривой: "end" — на конце (как в эталонном
# расчёте: бакет 3y — ставка на 3 года), "mid" — на середине (tenor_years).
# Срок дисконтирования от этого не зависит: всегда tenor_years.
RATE_POINT: Literal["end", "mid"] = "end"

# Срок ставки для последнего бакета при RATE_POINT="end": у него нет правой границы
OPEN_BUCKET_RATE_YEARS = 30.0

# Параметры Nelson-Siegel, которые приходят из MOEX
NS_PARAM_NAMES = ("b1", "b2", "b3", "t1")
