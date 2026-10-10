"""공공데이터 결합 및 지도 시각화.

소셜 데이터에서 얻은 지역별 언급 분포를 등록외국인 통계와 결합해
"실제 거주 분포"와 "소셜상 생활권"의 차이를 본다.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Iterable

from ..models import Document
from ..public_data import RegionStat
from .compare import region_key

LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """표본 피어슨 상관계수. 표본이 3개 미만이거나 분산이 0이면 None."""
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    dx = [x - mean_x for x in xs]
    dy = [y - mean_y for y in ys]
    denom = math.sqrt(sum(d * d for d in dx) * sum(d * d for d in dy))
    if denom == 0:
        return None
    return round(sum(a * b for a, b in zip(dx, dy)) / denom, 4)


def regional_join(
    documents: Iterable[Document],
    region_stats: dict[str, RegionStat],
    segment_a: str,
    segment_b: str,
    min_mix_mentions: int = 4,
) -> dict:
    """지역별 언급 분포 × 등록외국인 통계 결합 결과.

    ``min_mix_mentions`` 미만인 지역은 교류 지수 순위에서 제외한다.
    언급이 1건씩만 있어도 지수가 1.0이 되어 상위권을 차지하기 때문이다.
    """
    mentions: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    places: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    for doc in documents:
        if not doc.region:
            continue
        key = region_key(doc.region)
        mentions[key][doc.segment] += 1
        if doc.place_name:
            places[key][doc.segment].add(doc.place_name)

    rows: list[dict] = []
    missing_stats: list[str] = []
    total_b_mentions = sum(counts.get(segment_b, 0) for counts in mentions.values())

    for region, counts in sorted(mentions.items()):
        a = counts.get(segment_a, 0)
        b = counts.get(segment_b, 0)
        total = a + b
        stat = region_stats.get(region)
        if stat is None:
            missing_stats.append(region)
        shared = places[region].get(segment_a, set()) & places[region].get(segment_b, set())
        rows.append(
            {
                "region": region,
                "mentions_a": a,
                "mentions_b": b,
                "mentions_total": total,
                # 지역 내부 구성비 (두 집단 중 B가 차지하는 비율)
                "segment_b_within_region": round(b / total * 100, 2) if total else 0.0,
                # 전체 B 언급 중 이 지역이 차지하는 비중 → 공공통계와 같은 축에서 비교 가능
                "mention_share_b": round(b / total_b_mentions * 100, 2) if total_b_mentions else 0.0,
                "mix_index": round(1 - abs(a - b) / total, 3) if total else 0.0,
                "shared_places": sorted(shared),
                "official_foreign_ratio": stat.foreign_ratio if stat else None,
                "population": stat.population if stat else None,
                "foreign_residents": stat.foreign_residents if stat else None,
                "lat": stat.lat if stat else None,
                "lon": stat.lon if stat else None,
            }
        )

    matched = [r for r in rows if r["official_foreign_ratio"] is not None]

    # 거주 분포와 언급 분포를 같은 축(전체 대비 비중, %)에 놓고 비교한다.
    total_residents = sum(r["foreign_residents"] or 0 for r in matched)
    for row in matched:
        official_share = (
            round((row["foreign_residents"] or 0) / total_residents * 100, 2)
            if total_residents
            else 0.0
        )
        row["resident_share"] = official_share
        row["gap"] = round(row["mention_share_b"] - official_share, 2)

    correlation = pearson(
        [r["resident_share"] for r in matched], [r["mention_share_b"] for r in matched]
    )

    return {
        "regions": rows,
        "matched_regions": len(matched),
        "missing_stats": missing_stats,
        "total_mentions_b": total_b_mentions,
        "correlation_resident_vs_mention_share": correlation,
        "min_mix_mentions": min_mix_mentions,
        "top_mix_regions": sorted(
            [r for r in rows if r["mentions_total"] >= min_mix_mentions],
            key=lambda r: (-r["mix_index"], -r["mentions_total"]),
        )[:10],
    }


def render_map_html(geo: dict, title: str, labels: tuple[str, str]) -> str:
    """Leaflet 기반 단일 HTML 지도. 외부 빌드 도구 없이 브라우저에서 바로 열린다."""
    points = [r for r in geo["regions"] if r["lat"] is not None and r["lon"] is not None]
    payload = json.dumps(points, ensure_ascii=False)
    label_a, label_b = labels
    center = (
        [sum(p["lat"] for p in points) / len(points), sum(p["lon"] for p in points) / len(points)]
        if points
        else [37.5665, 126.9780]
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title}</title>
<link rel="stylesheet" href="{LEAFLET_CSS}" />
<style>
  body {{ margin: 0; font-family: -apple-system, "Apple SD Gothic Neo", sans-serif; }}
  #map {{ height: 100vh; }}
  .legend {{
    background: rgba(255,255,255,0.92); padding: 10px 12px; border-radius: 6px;
    line-height: 1.6; font-size: 13px; box-shadow: 0 1px 4px rgba(0,0,0,0.3);
  }}
  .legend i {{ width: 12px; height: 12px; display: inline-block; margin-right: 6px; border-radius: 50%; }}
  .empty {{ padding: 24px; }}
</style>
</head>
<body>
<div id="map"></div>
<script src="{LEAFLET_JS}"></script>
<script>
const regions = {payload};
const map = L.map('map').setView({json.dumps(center)}, 10);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 18,
  attribution: '&copy; OpenStreetMap contributors'
}}).addTo(map);

function colorFor(mix) {{
  if (mix >= 0.7) return '#2a9d8f';
  if (mix >= 0.4) return '#e9c46a';
  return '#e76f51';
}}

regions.forEach(function (r) {{
  const radius = 8 + Math.sqrt(r.mentions_total) * 6;
  const marker = L.circleMarker([r.lat, r.lon], {{
    radius: radius,
    color: colorFor(r.mix_index),
    fillColor: colorFor(r.mix_index),
    fillOpacity: 0.55,
    weight: 2
  }}).addTo(map);
  const shared = r.shared_places.length ? r.shared_places.join(', ') : '없음';
  const official = r.official_foreign_ratio === null ? '통계 없음' : r.official_foreign_ratio + '%';
  const gap = (r.gap === undefined || r.gap === null) ? '-' : (r.gap > 0 ? '+' : '') + r.gap + '%p';
  marker.bindPopup(
    '<b>' + r.region + '</b><br/>' +
    '{label_a} 언급: ' + r.mentions_a + '건<br/>' +
    '{label_b} 언급: ' + r.mentions_b + '건<br/>' +
    '교류 지수: ' + r.mix_index + '<br/>' +
    '등록외국인 비율: ' + official + '<br/>' +
    '거주 대비 언급 격차: ' + gap + '<br/>' +
    '공유 장소: ' + shared
  );
}});

const legend = L.control({{ position: 'bottomright' }});
legend.onAdd = function () {{
  const div = L.DomUtil.create('div', 'legend');
  div.innerHTML =
    '<b>교류 지수</b><br/>' +
    '<i style="background:#2a9d8f"></i>0.7 이상 (균형)<br/>' +
    '<i style="background:#e9c46a"></i>0.4 ~ 0.7<br/>' +
    '<i style="background:#e76f51"></i>0.4 미만 (한쪽 치우침)<br/>' +
    '<span style="font-size:11px;color:#555">원 크기 = 전체 언급량</span>';
  return div;
}};
legend.addTo(map);
</script>
</body>
</html>
"""


def render_geo_report(geo: dict, labels: tuple[str, str]) -> str:
    label_a, label_b = labels
    corr = geo["correlation_resident_vs_mention_share"]
    out = ["# 생활권 × 공공데이터 결합 리포트\n"]

    out.append("## 1. 지역별 결합 결과\n")
    out.append(
        f"| 지역 | {label_a} 언급 | {label_b} 언급 | {label_b} 언급 분포(%) | "
        f"{label_b} 거주 분포(%) | 격차 | 교류 지수 | 공유 장소 |"
    )
    out.append("|---|---|---|---|---|---|---|---|")
    for row in sorted(geo["regions"], key=lambda r: -r["mentions_total"]):
        resident = row.get("resident_share")
        out.append(
            f"| {row['region']} | {row['mentions_a']} | {row['mentions_b']} | "
            f"{row['mention_share_b']} | {resident if resident is not None else '-'} | "
            f"{row.get('gap', '-')} | {row['mix_index']} | {len(row['shared_places'])} |"
        )
    out.append(
        f"\n> 분포(%)는 전체 {label_b} 언급 {geo['total_mentions_b']}건 / 전체 등록외국인 수를 "
        "100으로 둔 지역별 비중입니다. 두 값이 같은 축에 있어야 비교가 성립합니다."
    )

    out.append("\n## 2. 거주 분포 vs 활동(언급) 분포\n")
    if corr is None:
        out.append("- 표본 지역이 부족해 상관계수를 계산하지 못했습니다(3개 지역 이상 필요).")
    else:
        strength = "강한" if abs(corr) >= 0.7 else "중간" if abs(corr) >= 0.4 else "약한"
        direction = "양" if corr > 0 else "음"
        out.append(
            f"- 지역별 등록외국인 분포와 {label_b} 언급 분포의 상관계수: **{corr}** "
            f"({strength} {direction}의 상관)"
        )
        out.append(
            "- 상관이 높다면 소셜 데이터가 실제 거주 분포를 잘 반영한다는 뜻이고, "
            "낮다면 '사는 곳'과 '활동하는 곳'이 다르다는 신호입니다."
        )

    gaps = [r for r in geo["regions"] if r.get("gap") is not None]
    if gaps:
        over = sorted(gaps, key=lambda r: -r["gap"])[:3]
        under = sorted(gaps, key=lambda r: r["gap"])[:3]
        out.append(
            "\n- 거주 분포 대비 **언급이 과대**한 지역(활동·소비 중심지): "
            + ", ".join(f"{r['region']}({r['gap']:+})" for r in over)
        )
        out.append(
            "- 거주 분포 대비 **언급이 과소**한 지역(거주 중심, 소셜 노출 적음): "
            + ", ".join(f"{r['region']}({r['gap']:+})" for r in under)
        )

    out.append("\n## 3. 교류 지수 상위 지역\n")
    threshold = geo.get("min_mix_mentions", 1)
    out.append(
        "교류 지수 = 1 − |집단 간 언급 차| ÷ 전체 언급. 1에 가까울수록 두 집단이 고르게 언급한 지역입니다.\n"
    )
    out.append(f"언급이 {threshold}건 미만인 지역은 표본이 적어 순위에서 제외했습니다.\n")
    if geo["top_mix_regions"]:
        out.append("| 순위 | 지역 | 교류 지수 | 전체 언급 | 공유 장소 |")
        out.append("|---|---|---|---|---|")
        for index, row in enumerate(geo["top_mix_regions"], 1):
            out.append(
                f"| {index} | {row['region']} | {row['mix_index']} | {row['mentions_total']} | "
                f"{', '.join(row['shared_places']) or '-'} |"
            )
    else:
        out.append(
            f"> 언급 {threshold}건 이상인 지역이 없습니다. 수집량을 늘리거나 "
            "`sma geo --min-mentions` 로 기준을 낮추세요.\n"
        )

    if geo["missing_stats"]:
        out.append("\n## 4. 통계 누락 지역\n")
        out.append(
            "아래 지역은 공공데이터에 없어 상관분석과 지도에서 제외되었습니다. "
            "`data/public/foreign_residents.csv` 에 추가하세요.\n"
        )
        for region in geo["missing_stats"]:
            out.append(f"- {region}")

    out.append("\n---\n")
    out.append("> 공공데이터는 예시 값이 포함될 수 있습니다. `data/public/README.md` 의 출처 안내를 확인하세요.\n")
    return "\n".join(out)
