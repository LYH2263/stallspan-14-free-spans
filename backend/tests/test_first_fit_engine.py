import pytest

from app.services.first_fit_engine import (
    MEDIUM_MAX_M,
    TIGHT_MAX_M,
    RunInvalidError,
    allocate_first_fit,
    free_spans_from_pillars,
    normalize_stored_result,
    result_to_dict,
    tier_for_length,
    validate_margins,
)

SEED_PILLARS = [
    {"position_m": 10.0, "thickness_m": 0.5},
    {"position_m": 20.0, "thickness_m": 0.5},
]
SEED_VENDORS = [
    {"id": 1, "name": "阿强烧烤", "stall_width_m": 3.5, "priority": 1},
    {"id": 2, "name": "林记糖水", "stall_width_m": 3.0, "priority": 1},
    {"id": 3, "name": "大碗面", "stall_width_m": 6.0, "priority": 1},
    {"id": 4, "name": "老周水果", "stall_width_m": 5.0, "priority": 2},
    {"id": 5, "name": "小美饰品", "stall_width_m": 2.0, "priority": 2},
    {"id": 6, "name": "手作皮具", "stall_width_m": 1.5, "priority": 3},
    {"id": 7, "name": "巨型舞台车", "stall_width_m": 12.0, "priority": 9},
]


def test_free_spans_with_pillars():
    spans = free_spans_from_pillars(30.0, SEED_PILLARS)
    assert len(spans) == 3
    assert spans[0][0] == 0.0
    assert spans == [(0.0, 9.75), (10.25, 19.75), (20.25, 30.0)]


def test_first_fit_no_cross_pillar():
    vendors = [
        {"id": 1, "name": "A", "stall_width_m": 4.0, "priority": 1},
        {"id": 2, "name": "B", "stall_width_m": 12.0, "priority": 1},
    ]
    pillars = [{"position_m": 10.0, "thickness_m": 0.5}]
    r = allocate_first_fit(30.0, vendors, pillars)
    assert any(p.vendor_name == "A" for p in r.placements)
    assert len(r.placements) + len(r.rejected) == 2


def test_reject_oversized():
    vendors = [{"id": 1, "name": "Huge", "stall_width_m": 25.0, "priority": 1}]
    r = allocate_first_fit(30.0, vendors, SEED_PILLARS)
    assert len(r.rejected) == 1
    assert r.rejected[0].vendor_name == "Huge"


# ---------- 档位分界（锁死，改分界须同步改本测例） ----------

def test_tier_boundaries_locked():
    assert TIGHT_MAX_M == 1.5
    assert MEDIUM_MAX_M == 3.0
    assert tier_for_length(0.01) == "tight"
    assert tier_for_length(1.5) == "tight"          # 分界值归紧
    assert tier_for_length(1.5001) == "medium"
    assert tier_for_length(3.0) == "medium"         # 分界值归中
    assert tier_for_length(3.0001) == "loose"
    assert tier_for_length(99.0) == "loose"


# ---------- 种子场景：灯柱切开的多段余量，三档各一 ----------

def test_seed_margins_split_by_pillars_three_tiers():
    r = allocate_first_fit(30.0, SEED_VENDORS, SEED_PILLARS)
    assert len(r.margins) == 3
    got = [(g.start_m, g.end_m, g.length_m, g.tier) for g in r.margins]
    assert got == [
        (8.5, 9.75, 1.25, "tight"),
        (17.75, 19.75, 2.0, "medium"),
        (25.25, 30.0, 4.75, "loose"),
    ]
    # 三段余量必须分别落在不同柱间空档（被灯柱切开），不穿柱
    for g in r.margins:
        in_span = (g.end_m <= 9.75 or
                   (g.start_m >= 10.25 and g.end_m <= 19.75) or
                   g.start_m >= 20.25)
        assert in_span
    assert [g for g in r.margins if g.end_m <= 9.75]
    assert [g for g in r.margins if 10.25 <= g.start_m and g.end_m <= 19.75]
    assert [g for g in r.margins if g.start_m >= 20.25]


def test_margins_do_not_overlap_placements_in_seed():
    d = result_to_dict(allocate_first_fit(30.0, SEED_VENDORS, SEED_PILLARS))
    for g in d["margins"]:
        for p in d["placements"]:
            overlap = min(g["end_m"], p["end_m"]) - max(g["start_m"], p["start_m"])
            assert overlap <= 1e-6


# ---------- 塞满时色档为空数组 ----------

def test_margins_empty_when_fully_packed():
    vendors = [
        {"id": 1, "name": "P", "stall_width_m": 9.75, "priority": 1},
        {"id": 2, "name": "Q", "stall_width_m": 9.5, "priority": 1},
        {"id": 3, "name": "R", "stall_width_m": 9.75, "priority": 1},
    ]
    d = result_to_dict(allocate_first_fit(30.0, vendors, SEED_PILLARS))
    assert d["margins"] == []
    assert d["rejected"] == []


# ---------- 相交无效：端点相接允许，正长度相交作废 ----------

def test_validate_touching_endpoints_allowed():
    placements = [{"vendor_name": "A", "start_m": 0.0, "end_m": 4.0}]
    validate_margins(placements, [{"start_m": 4.0, "end_m": 6.0}])  # 不抛


def test_validate_overlap_invalidates_run():
    placements = [{"vendor_name": "A", "start_m": 0.0, "end_m": 5.0}]
    with pytest.raises(RunInvalidError):
        validate_margins(placements, [{"start_m": 4.0, "end_m": 6.0}])


def test_result_to_dict_self_validates():
    r = allocate_first_fit(30.0, SEED_VENDORS, SEED_PILLARS)
    d = result_to_dict(r)  # 合法结果不抛
    assert "margins" in d
    with pytest.raises(RunInvalidError):
        validate_margins(
            [{"vendor_name": "X", "start_m": 0.0, "end_m": 10.0}],
            [{"start_m": 5.0, "end_m": 7.0}],
        )


# ---------- 旧结构可读 ----------

def test_normalize_legacy_free_spans():
    legacy = {
        "placements": [],
        "rejected": [],
        "free_spans": [{"start_m": 0.0, "end_m": 1.25}, {"start_m": 8.0, "end_m": 10.0}],
    }
    out = normalize_stored_result(legacy)
    assert out["margins"] == [
        {"start_m": 0.0, "end_m": 1.25, "length_m": 1.25, "tier": "tight"},
        {"start_m": 8.0, "end_m": 10.0, "length_m": 2.0, "tier": "medium"},
    ]


def test_normalize_passthrough_and_empty():
    fresh = {"placements": [], "rejected": [], "margins": []}
    assert normalize_stored_result(fresh)["margins"] == []
    out = normalize_stored_result({})
    assert out["placements"] == [] and out["rejected"] == [] and out["margins"] == []
