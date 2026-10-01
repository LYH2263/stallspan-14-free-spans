"""1D First-Fit stall placement along a street segment; stalls cannot cross pillars."""
from __future__ import annotations
from dataclasses import asdict, dataclass

# 余量色档档位分界（锁死，勿改——分界测例依赖）:
#   剩余长度 < 3.0m        → 紧 (tight)
#   3.0m ≤ 剩余长度 < 6.0m → 中 (medium)
#   剩余长度 ≥ 6.0m        → 松 (loose)
TIER_TIGHT_MAX_M = 3.0
TIER_MEDIUM_MAX_M = 6.0
TIER_TIGHT = "紧"
TIER_MEDIUM = "中"
TIER_LOOSE = "松"

@dataclass
class Placement:
    vendor_id: int
    vendor_name: str
    start_m: float
    end_m: float
    width_m: float

@dataclass
class Rejected:
    vendor_id: int
    vendor_name: str
    width_m: float
    reason: str

@dataclass
class MarginBand:
    """一段剩余空档的色档：起止米、剩余长度、紧中松档位。"""
    start_m: float
    end_m: float
    length_m: float
    tier: str

@dataclass
class AllocResult:
    placements: list[Placement]
    rejected: list[Rejected]
    free_spans: list[tuple[float, float]]
    margin_bands: list[MarginBand]

def tier_for_length(length_m: float) -> str:
    """紧中松档位分界：3.0 → 中，6.0 → 松（闭区间归上档）。"""
    if length_m < TIER_TIGHT_MAX_M:
        return TIER_TIGHT
    if length_m < TIER_MEDIUM_MAX_M:
        return TIER_MEDIUM
    return TIER_LOOSE

def margin_bands_from_spans(spans: list[tuple[float, float]]) -> list[MarginBand]:
    """由剩余空档 (start, end) 生成色档；无剩余时为空数组。"""
    bands: list[MarginBand] = []
    for a, b in spans:
        length = round(b - a, 3)
        if length <= 1e-6:
            continue
        bands.append(MarginBand(round(a, 3), round(b, 3), length, tier_for_length(length)))
    return bands

def validate_margins(placements: list[Placement], bands: list[MarginBand],
                     eps: float = 1e-9) -> list[str]:
    """余量闭区间不得与任一成功放置相交（正长度交叠即相交；端点相贴不算）。
    返回违规描述列表，空列表表示有效。"""
    violations: list[str] = []
    for band in bands:
        for p in placements:
            overlap = min(band.end_m, p.end_m) - max(band.start_m, p.start_m)
            if overlap > eps:
                violations.append(
                    f"余量[{band.start_m},{band.end_m}]与放置[{p.start_m},{p.end_m}]"
                    f"（{p.vendor_name}）相交 {round(overlap, 3)}m"
                )
    return violations

def free_spans_from_pillars(width_m: float, pillars: list[dict]) -> list[tuple[float, float]]:
    """pillars: position_m, thickness_m — treated as blocked intervals."""
    blocked = []
    for p in pillars:
        half = p.get("thickness_m", 0.4) / 2.0
        lo = max(0.0, p["position_m"] - half)
        hi = min(width_m, p["position_m"] + half)
        if hi > lo:
            blocked.append((lo, hi))
    blocked.sort()
    merged = []
    for lo, hi in blocked:
        if not merged or lo > merged[-1][1]:
            merged.append([lo, hi])
        else:
            merged[-1][1] = max(merged[-1][1], hi)
    spans = []
    cursor = 0.0
    for lo, hi in merged:
        if lo > cursor:
            spans.append((cursor, lo))
        cursor = hi
    if cursor < width_m:
        spans.append((cursor, width_m))
    return [(round(a, 3), round(b, 3)) for a, b in spans if b - a > 1e-6]

def allocate_first_fit(width_m: float, vendors: list[dict], pillars: list[dict]) -> AllocResult:
    """vendors sorted by priority ascending then id; each needs stall_width_m contiguous in one free span (no pillar cross)."""
    spans = free_spans_from_pillars(width_m, pillars)
    # mutable remaining capacity per span
    remain = [[a, b] for a, b in spans]
    ordered = sorted(vendors, key=lambda v: (v.get("priority", 1), v["id"]))
    placements: list[Placement] = []
    rejected: list[Rejected] = []
    for v in ordered:
        need = float(v["stall_width_m"])
        placed = False
        for span in remain:
            avail = span[1] - span[0]
            if avail + 1e-9 >= need:
                start = span[0]
                end = start + need
                placements.append(Placement(v["id"], v["name"], round(start, 3), round(end, 3), need))
                span[0] = end
                placed = True
                break
        if not placed:
            rejected.append(Rejected(v["id"], v["name"], need, "无连续空档可放下且不跨越挡柱"))
    free = [(round(a, 3), round(b, 3)) for a, b in remain if b - a > 1e-6]
    return AllocResult(placements, rejected, free, margin_bands_from_spans(free))

def result_to_dict(r: AllocResult) -> dict:
    return {
        "placements": [asdict(p) for p in r.placements],
        "rejected": [asdict(x) for x in r.rejected],
        "free_spans": [{"start_m": a, "end_m": b} for a, b in r.free_spans],
        "margin_bands": [asdict(b) for b in r.margin_bands],
    }

def bands_payload_from_free_spans(free_spans: list[dict]) -> list[dict]:
    """旧结构 result_json 读取回退：由存档的 free_spans 推导色档（不重算、不写库）。"""
    spans = [(float(s["start_m"]), float(s["end_m"])) for s in free_spans or []]
    return [asdict(b) for b in margin_bands_from_spans(spans)]
