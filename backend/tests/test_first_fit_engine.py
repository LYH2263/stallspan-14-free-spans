from app.services.first_fit_engine import (
    AllocResult,
    MarginBand,
    Placement,
    allocate_first_fit,
    free_spans_from_pillars,
    margin_bands_from_spans,
    tier_for_length,
    validate_margins,
)

def test_free_spans_with_pillars():
    spans = free_spans_from_pillars(30.0, [{"position_m": 10.0, "thickness_m": 0.5}, {"position_m": 20.0, "thickness_m": 0.5}])
    assert len(spans) == 3
    assert spans[0][0] == 0.0

def test_first_fit_no_cross_pillar():
    vendors = [
        {"id": 1, "name": "A", "stall_width_m": 4.0, "priority": 1},
        {"id": 2, "name": "B", "stall_width_m": 12.0, "priority": 1},
    ]
    pillars = [{"position_m": 10.0, "thickness_m": 0.5}]
    r = allocate_first_fit(30.0, vendors, pillars)
    assert any(p.vendor_name == "A" for p in r.placements)
    # 12m may fit in a free span after first placement depending on remainders
    assert len(r.placements) + len(r.rejected) == 2

def test_reject_oversized():
    vendors = [{"id": 1, "name": "Huge", "stall_width_m": 25.0, "priority": 1}]
    pillars = [{"position_m": 10.0, "thickness_m": 0.5}, {"position_m": 20.0, "thickness_m": 0.5}]
    r = allocate_first_fit(30.0, vendors, pillars)
    assert len(r.rejected) == 1
    assert r.rejected[0].vendor_name == "Huge"

# --- 余量色档：紧中松档位分界（锁死，勿改） ---

def test_tier_boundaries_locked():
    # 紧: < 3.0m
    assert tier_for_length(0.25) == "紧"
    assert tier_for_length(2.999) == "紧"
    # 中: [3.0, 6.0)m
    assert tier_for_length(3.0) == "中"
    assert tier_for_length(4.75) == "中"
    assert tier_for_length(5.999) == "中"
    # 松: >= 6.0m
    assert tier_for_length(6.0) == "松"
    assert tier_for_length(12.5) == "松"

def test_margin_bands_fields_and_empty():
    bands = margin_bands_from_spans([(0.0, 2.5), (4.0, 10.0)])
    assert [ (b.start_m, b.end_m, b.length_m, b.tier) for b in bands ] == [
        (0.0, 2.5, 2.5, "紧"),
        (4.0, 10.0, 6.0, "松"),
    ]
    # 无剩余时色档为空数组
    assert margin_bands_from_spans([]) == []

def test_bands_empty_when_street_filled_exactly():
    vendors = [{"id": 1, "name": "A", "stall_width_m": 10.0, "priority": 1}]
    r = allocate_first_fit(10.0, vendors, [])
    assert len(r.placements) == 1
    assert r.margin_bands == []

def test_seed_like_run_bands_cut_by_pillars():
    # 与种子数据一致：东街段 30m，灯柱 10m/20m（厚 0.5）→ 多段余量
    vendors = [
        {"id": 1, "name": "阿强烧烤", "stall_width_m": 4.0, "priority": 1},
        {"id": 2, "name": "林记糖水", "stall_width_m": 3.0, "priority": 1},
        {"id": 3, "name": "老周水果", "stall_width_m": 5.0, "priority": 2},
        {"id": 4, "name": "小美饰品", "stall_width_m": 2.5, "priority": 2},
        {"id": 5, "name": "大碗面", "stall_width_m": 6.0, "priority": 1},
        {"id": 6, "name": "手作皮具", "stall_width_m": 3.5, "priority": 3},
        {"id": 7, "name": "巨型舞台车", "stall_width_m": 12.0, "priority": 9},
    ]
    pillars = [{"position_m": 10.0, "thickness_m": 0.5}, {"position_m": 20.0, "thickness_m": 0.5}]
    r = allocate_first_fit(30.0, vendors, pillars)
    got = [(b.start_m, b.end_m, b.length_m, b.tier) for b in r.margin_bands]
    assert got == [(9.5, 9.75, 0.25, "紧"), (25.25, 30.0, 4.75, "中")]
    # 色档与剩余空档一一对应
    assert [(b.start_m, b.end_m) for b in r.margin_bands] == r.free_spans

def test_bands_never_intersect_placements_across_configs():
    configs = [
        (30.0, [4.0, 3.0, 5.0, 2.5, 6.0, 3.5, 12.0], [{"position_m": 10.0, "thickness_m": 0.5}, {"position_m": 20.0, "thickness_m": 0.5}]),
        (20.0, [7.5, 7.5, 7.5], [{"position_m": 6.0, "thickness_m": 1.0}]),
        (15.0, [2.0] * 20, []),
        (12.0, [12.0], [{"position_m": 0.0, "thickness_m": 0.0}]),
        (25.0, [5.0, 5.0, 5.0, 5.0, 5.0], [{"position_m": 12.5, "thickness_m": 0.4}]),
    ]
    for width, widths, pillars in configs:
        vendors = [{"id": i + 1, "name": f"V{i}", "stall_width_m": w, "priority": 1}
                   for i, w in enumerate(widths)]
        r = allocate_first_fit(width, vendors, pillars)
        assert validate_margins(r.placements, r.margin_bands) == []
        # 每段色档长度 = 止 - 起，档位与长度一致
        for b in r.margin_bands:
            assert b.length_m == round(b.end_m - b.start_m, 3)
            assert b.tier == tier_for_length(b.length_m)

def test_validate_margins_detects_positive_overlap():
    placements = [Placement(1, "A", 0.0, 4.0, 4.0)]
    # 正长度相交 → 违规
    bad = [MarginBand(2.0, 6.0, 4.0, "中")]
    assert validate_margins(placements, bad) != []
    # 端点相贴（闭区间共端点但无正长度交叠）→ 有效
    touching = [MarginBand(4.0, 9.0, 5.0, "中")]
    assert validate_margins(placements, touching) == []
    # 完全相离 → 有效
    apart = [MarginBand(5.0, 8.0, 3.0, "中")]
    assert validate_margins(placements, apart) == []
