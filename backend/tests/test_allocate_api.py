import json
import os

os.environ["DATABASE_URL"] = "sqlite://"  # 导入 app 前隔离 Postgres

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import AllocationRun, MarketDay, Pillar, Segment, Vendor
from app.services.first_fit_engine import AllocResult, MarginBand, Placement

engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                       poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)  # 不进入 lifespan：不连 Postgres、不自动种子

SEED_VENDORS = [
    ("阿强烧烤", 4.0, 1), ("林记糖水", 3.0, 1), ("老周水果", 5.0, 2),
    ("小美饰品", 2.5, 2), ("大碗面", 6.0, 1), ("手作皮具", 3.5, 3),
    ("巨型舞台车", 12.0, 9),
]

@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield

def make_segment(width=30.0, pillar_positions=(10.0, 20.0), vendors=SEED_VENDORS):
    db = TestingSessionLocal()
    try:
        day = MarketDay(name="周末夜市", day=__import__("datetime").date(2026, 9, 20))
        db.add(day); db.flush()
        seg = Segment(market_day_id=day.id, name="东街段", width_m=width)
        db.add(seg); db.flush()
        for pos in pillar_positions:
            db.add(Pillar(segment_id=seg.id, position_m=pos, thickness_m=0.5, label="灯柱"))
        for name, wdt, pri in vendors:
            db.add(Vendor(market_day_id=day.id, name=name, stall_width_m=wdt, priority=pri))
        db.commit()
        return seg.id
    finally:
        db.close()

def run_count():
    db = TestingSessionLocal()
    try:
        return db.scalar(select(func.count()).select_from(AllocationRun)) or 0
    finally:
        db.close()

def stored_run(run_id):
    db = TestingSessionLocal()
    try:
        return json.loads(db.get(AllocationRun, run_id).result_json)
    finally:
        db.close()

def test_run_returns_margin_bands_and_persists_frozen():
    seg_id = make_segment()
    res = client.post(f"/api/allocate/run?segment_id={seg_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["margin_bands"] == [
        {"start_m": 9.5, "end_m": 9.75, "length_m": 0.25, "tier": "紧"},
        {"start_m": 25.25, "end_m": 30.0, "length_m": 4.75, "tier": "中"},
    ]
    assert data["created_at"]
    assert run_count() == 1
    # 落库内容 = 响应内容（确认落库瞬间固化色档）
    stored = stored_run(data["id"])
    assert stored["margin_bands"] == data["margin_bands"]
    # latest 读同一次运行，色档一致
    latest = client.get(f"/api/allocate/latest?segment_id={seg_id}").json()
    assert latest["id"] == data["id"]
    assert latest["margin_bands"] == data["margin_bands"]

def test_old_run_frozen_after_width_and_pillar_change():
    seg_id = make_segment()
    first = client.post(f"/api/allocate/run?segment_id={seg_id}").json()
    bands_before = first["margin_bands"]
    # 改街宽 + 挪柱后再跑
    db = TestingSessionLocal()
    seg = db.get(Segment, seg_id)
    seg.width_m = 40.0
    for p in db.scalars(select(Pillar)).all():
        p.position_m += 5.0
    db.commit(); db.close()
    second = client.post(f"/api/allocate/run?segment_id={seg_id}").json()
    assert second["margin_bands"] != bands_before  # 禁止吃改前色档缓存
    assert run_count() == 2
    # 旧运行色档不被改写
    assert stored_run(first["id"])["margin_bands"] == bands_before
    # latest 返回新运行的新色档
    latest = client.get(f"/api/allocate/latest?segment_id={seg_id}").json()
    assert latest["id"] == second["id"]
    assert latest["margin_bands"] == second["margin_bands"]

def test_old_structure_json_readable_without_rewrite():
    seg_id = make_segment(vendors=[])
    old_payload = {
        "placements": [{"vendor_id": 1, "vendor_name": "旧摊", "start_m": 0.0, "end_m": 4.0, "width_m": 4.0}],
        "rejected": [],
        "free_spans": [{"start_m": 4.0, "end_m": 9.75}, {"start_m": 10.25, "end_m": 16.25}],
        "segment": {"id": seg_id, "name": "东街段", "width_m": 30.0},
        "pillars": [],
    }
    db = TestingSessionLocal()
    db.add(AllocationRun(segment_id=seg_id, result_json=json.dumps(old_payload, ensure_ascii=False)))
    db.commit(); db.close()
    res = client.get(f"/api/allocate/latest?segment_id={seg_id}")
    assert res.status_code == 200
    data = res.json()
    # 旧结构须可读该字段：由存档 free_spans 推导
    assert data["margin_bands"] == [
        {"start_m": 4.0, "end_m": 9.75, "length_m": 5.75, "tier": "中"},
        {"start_m": 10.25, "end_m": 16.25, "length_m": 6.0, "tier": "松"},
    ]
    # 读取不回写旧运行
    assert "margin_bands" not in stored_run(data["id"])

def test_intersection_invalidates_run_and_row_count_unchanged(monkeypatch):
    seg_id = make_segment()
    bad = AllocResult(
        placements=[Placement(1, "阿强烧烤", 0.0, 4.0, 4.0)],
        rejected=[],
        free_spans=[(2.0, 6.0)],
        margin_bands=[MarginBand(2.0, 6.0, 4.0, "中")],  # 与放置 [0,4] 正长度相交
    )
    monkeypatch.setattr("app.api.allocate.allocate_first_fit", lambda *a, **k: bad)
    before = run_count()
    res = client.post(f"/api/allocate/run?segment_id={seg_id}")
    assert res.status_code == 409
    assert "相交" in res.json()["detail"]
    assert run_count() == before  # 行数不增

def test_bands_empty_array_when_no_remainder():
    seg_id = make_segment(width=10.0, pillar_positions=(), vendors=[("满档", 10.0, 1)])
    data = client.post(f"/api/allocate/run?segment_id={seg_id}").json()
    assert data["margin_bands"] == []
    assert len(data["placements"]) == 1
