"""API 级：确认瞬间固化色档；改街宽/挪柱后旧运行只读不回写；旧结构可读。

依赖 fastapi/sqlalchemy/httpx（requirements.txt），本地仅引擎单测时可缺。
"""
import json
import os
import tempfile

_DB_FD, _DB_PATH = tempfile.mkstemp(prefix="stallspan_test_", suffix=".db")
os.close(_DB_FD)
os.unlink(_DB_PATH)  # create_all 会建；留着文件句柄无意义
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("SEED_ON_EMPTY", "true")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.models import AllocationRun, Segment  # noqa: E402


def _tiers(payload):
    return [(g["start_m"], g["end_m"], g["length_m"], g["tier"]) for g in payload["margins"]]


def test_run_freeze_and_immutable_history():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as client:  # lifespan 播种东街段
        # 触发首次确认（latest 无记录时会自动确认一次）
        first = client.post("/api/allocate/run?segment_id=1").json()
        expected_margins = [
            (8.5, 9.75, 1.25, "tight"),
            (17.75, 19.75, 2.0, "medium"),
            (25.25, 30.0, 4.75, "loose"),
        ]
        assert _tiers(first) == expected_margins
        run1_id = first["id"]
        frozen1 = json.dumps(first, ensure_ascii=False, sort_keys=True)

        # 第二次确认正常建行
        second = client.post("/api/allocate/run?segment_id=1").json()
        assert second["id"] == run1_id + 1
        listed = client.get("/api/allocate/runs?segment_id=1").json()
        assert [r["id"] for r in listed] == [second["id"], run1_id]

        # 改街宽 30 -> 40：之后再现算，旧运行色档不得被改写
        db = SessionLocal()
        try:
            seg = db.get(Segment, 1)
            seg.width_m = 40.0
            db.commit()
        finally:
            db.close()

        old = client.get(f"/api/allocate/runs/{run1_id}").json()
        assert json.dumps(old, ensure_ascii=False, sort_keys=True) != frozen1  # 多了 created_at 外壳
        assert _tiers(old) == expected_margins  # 色档冻结不变
        assert old["segment"]["width_m"] == 30.0

        # 新运行按新街宽现算（40m 下第三空档 19.75m，12m 舞台车放得下）
        third = client.post("/api/allocate/run?segment_id=1").json()
        assert len(third["rejected"]) == 0
        assert third["id"] == run1_id + 2
        # 旧两行依旧原样
        old_again = client.get(f"/api/allocate/runs/{run1_id}").json()
        assert _tiers(old_again) == expected_margins
        second_again = client.get(f"/api/allocate/runs/{second['id']}").json()
        assert second_again["segment"]["width_m"] == 30.0

        # latest 指向最新
        latest = client.get("/api/allocate/latest?segment_id=1").json()
        assert latest["id"] == third["id"]


def test_legacy_run_with_only_free_spans_is_readable():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as client:
        client.post("/api/allocate/run?segment_id=1")  # 确保 segment 存在
        db = SessionLocal()
        try:
            legacy = {
                "placements": [], "rejected": [],
                "free_spans": [{"start_m": 0.0, "end_m": 1.25},
                               {"start_m": 8.0, "end_m": 10.0}],
            }
            run = AllocationRun(segment_id=1, result_json=json.dumps(legacy, ensure_ascii=False))
            db.add(run)
            db.commit()
            legacy_id = run.id
        finally:
            db.close()
        got = client.get(f"/api/allocate/runs/{legacy_id}").json()
        assert got["margins"] == [
            {"start_m": 0.0, "end_m": 1.25, "length_m": 1.25, "tier": "tight"},
            {"start_m": 8.0, "end_m": 10.0, "length_m": 2.0, "tier": "medium"},
        ]
        # 兼容派生不回写旧记录
        db = SessionLocal()
        try:
            stored = json.loads(db.get(AllocationRun, legacy_id).result_json)
            assert "margins" not in stored and "free_spans" in stored
        finally:
            db.close()
