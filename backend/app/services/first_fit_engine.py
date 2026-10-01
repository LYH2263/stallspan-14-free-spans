"""1D First-Fit stall placement along a street segment; stalls cannot cross pillars.

运行结果除 placements / rejected 外，稳定带回 margins（柱间余量色档）：
每段剩余空档的 start_m / end_m / length_m / tier（tight 紧 / medium 中 / loose 松）。
余量为闭区间语义：端点相接（如 [a,b] 与 [b,c]）不算相交；正长度重叠才无效。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# 紧/中/松分界（测例锁死）：length <= TIGHT_MAX 紧；<= MEDIUM_MAX 中；再大松。
TIGHT_MAX_M = 1.5
MEDIUM_MAX_M = 3.0

TIER_TIGHT = "tight"
TIER_MEDIUM = "medium"
TIER_LOOSE = "loose"


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
class MarginGap:
    start_m: float
    end_m: float
    length_m: float
    tier: str


@dataclass
class AllocResult:
    placements: list[Placement]
    rejected: list[Rejected]
    margins: list[MarginGap]


class RunInvalidError(ValueError):
    """余量闭区间与成功放置正长度相交——整次运行结果无效。"""


def tier_for_length(length_m: float) -> str:
    if length_m <= TIGHT_MAX_M + 1e-9:
        return TIER_TIGHT
    if length_m <= MEDIUM_MAX_M + 1e-9:
        return TIER_MEDIUM
    return TIER_LOOSE


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


def margins_from_remain(remain: list[list[float]]) -> list[MarginGap]:
    gaps: list[MarginGap] = []
    for a, b in remain:
        length = b - a
        if length <= 1e-6:
            continue
        start = round(a, 3)
        end = round(b, 3)
        length_r = round(length, 3)
        gaps.append(MarginGap(start, end, length_r, tier_for_length(length_r)))
    gaps.sort(key=lambda g: g.start_m)
    return gaps


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
    margins = margins_from_remain(remain)
    return AllocResult(placements, rejected, margins)


def validate_margins(placements: list[dict], margins: list[dict]) -> None:
    """余量为闭区间：与任一成功放置正长度相交即整次运行无效。端点相接（重叠长度 0）允许。"""
    for g in margins:
        g_lo, g_hi = float(g["start_m"]), float(g["end_m"])
        if g_hi < g_lo:
            raise RunInvalidError(f"余量方向反转: {g_lo} > {g_hi}")
        for p in placements:
            overlap = min(g_hi, float(p["end_m"])) - max(g_lo, float(p["start_m"]))
            if overlap > 1e-6:
                raise RunInvalidError(
                    f"余量[{g_lo}, {g_hi}]与放置 {p.get('vendor_name')}"
                    f"[{p['start_m']}, {p['end_m']}]正长度相交 {round(overlap, 3)}m"
                )


def result_to_dict(r: AllocResult) -> dict:
    data = {
        "placements": [asdict(p) for p in r.placements],
        "rejected": [asdict(x) for x in r.rejected],
        "margins": [asdict(g) for g in r.margins],
    }
    # 落库前自检：余量与放置相交则本次结果作废，不得落库。
    validate_margins(data["placements"], data["margins"])
    return data


def normalize_stored_result(data: dict) -> dict:
    """读取历史运行时的兼容层：旧结构只有 free_spans，无 margins——
    按相同分界从冻结的 free_spans 派生（仅展示用，不回写旧记录）；新结构原样返回。"""
    if not isinstance(data, dict):
        return {"placements": [], "rejected": [], "margins": []}
    data.setdefault("placements", [])
    data.setdefault("rejected", [])
    if "margins" not in data:
        derived: list[dict] = []
        for span in data.get("free_spans") or []:
            start = round(float(span["start_m"]), 3)
            end = round(float(span["end_m"]), 3)
            length = round(end - start, 3)
            if length > 1e-6:
                derived.append({"start_m": start, "end_m": end,
                                "length_m": length, "tier": tier_for_length(length)})
        data["margins"] = derived
    return data
