"""공공데이터 로더.

시군구 단위 등록외국인 통계와 좌표를 읽어 소셜 분석 결과와 결합할 수 있게 한다.
CSV 형식만 맞추면 어떤 출처의 데이터로도 교체할 수 있다.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .config import PROJECT_ROOT

DEFAULT_STATS_PATH = PROJECT_ROOT / "data" / "public" / "foreign_residents.csv"
DEFAULT_COORDS_PATH = PROJECT_ROOT / "data" / "public" / "region_coords.csv"


@dataclass
class RegionStat:
    region: str
    population: int = 0
    foreign_residents: int = 0
    lat: float | None = None
    lon: float | None = None
    source: str = ""

    @property
    def foreign_ratio(self) -> float:
        """전체 인구 대비 등록외국인 비율(%)."""
        if not self.population:
            return 0.0
        return round(self.foreign_residents / self.population * 100, 3)

    def to_dict(self) -> dict:
        return {
            "region": self.region,
            "population": self.population,
            "foreign_residents": self.foreign_residents,
            "foreign_ratio": self.foreign_ratio,
            "lat": self.lat,
            "lon": self.lon,
            "source": self.source,
        }


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fp:
        return list(csv.DictReader(fp))


def _to_int(value: str | None) -> int:
    if not value:
        return 0
    return int(str(value).replace(",", "").strip() or 0)


def _to_float(value: str | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def load_region_stats(
    stats_path: str | Path | None = None,
    coords_path: str | Path | None = None,
) -> dict[str, RegionStat]:
    """시군구명 -> RegionStat 매핑."""
    stats_file = Path(stats_path) if stats_path else DEFAULT_STATS_PATH
    coords_file = Path(coords_path) if coords_path else DEFAULT_COORDS_PATH

    coords: dict[str, tuple[float | None, float | None]] = {}
    for row in _read_csv(coords_file):
        coords[row["region"].strip()] = (_to_float(row.get("lat")), _to_float(row.get("lon")))

    stats: dict[str, RegionStat] = {}
    for row in _read_csv(stats_file):
        region = row["region"].strip()
        lat, lon = coords.get(region, (None, None))
        stats[region] = RegionStat(
            region=region,
            population=_to_int(row.get("population")),
            foreign_residents=_to_int(row.get("foreign_residents")),
            lat=lat,
            lon=lon,
            source=(row.get("source") or "").strip(),
        )
    return stats
