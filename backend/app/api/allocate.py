import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import AllocationRun, Pillar, Segment, Vendor
from app.services.first_fit_engine import (
    RunInvalidError,
    allocate_first_fit,
    normalize_stored_result,
    result_to_dict,
)
router = APIRouter(prefix="/allocate", tags=["allocate"])


def _compute(seg: Segment, pillars: list[dict], vendors: list[dict]) -> dict:
    """始终用当前街宽/挡柱/摊主现算——禁止吃历史色档缓存。"""
    result = result_to_dict(allocate_first_fit(seg.width_m, vendors, pillars))
    result["segment"] = {"id": seg.id, "name": seg.name, "width_m": seg.width_m}
    result["pillars"] = pillars
    return result


def _load_run(run: AllocationRun) -> dict:
    """历史运行只读：返回确认瞬间冻结的 JSON，仅做旧结构兼容，绝不重算或回写。"""
    data = normalize_stored_result(json.loads(run.result_json))
    return {
        "id": run.id,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        **data,
    }


@router.post("/run")
def run_allocate(segment_id: int = 1, db: Session = Depends(get_db)):
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    pillars = [{"position_m": p.position_m, "thickness_m": p.thickness_m}
               for p in db.scalars(select(Pillar).where(Pillar.segment_id == segment_id)).all()]
    vendors = [{"id": v.id, "name": v.name, "stall_width_m": v.stall_width_m, "priority": v.priority}
               for v in db.scalars(select(Vendor).where(Vendor.market_day_id == seg.market_day_id)).all()]
    try:
        result = _compute(seg, pillars, vendors)
    except RunInvalidError as exc:
        # 余量与放置相交：整次运行无效，行数不增。
        raise HTTPException(422, f"运行结果无效，已放弃落库：{exc}")
    run = AllocationRun(segment_id=segment_id, created_at=datetime.utcnow(),
                        result_json=json.dumps(result, ensure_ascii=False))
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"id": run.id, "created_at": run.created_at.isoformat(), **result}


@router.get("/latest")
def latest(segment_id: int = 1, db: Session = Depends(get_db)):
    run = db.scalars(select(AllocationRun).where(AllocationRun.segment_id == segment_id)
                     .order_by(AllocationRun.id.desc())).first()
    if not run:
        # 从无确认记录：现算一次并固化（仍是当前输入，不涉及缓存）。
        return run_allocate(segment_id=segment_id, db=db)
    return _load_run(run)


@router.get("/runs")
def list_runs(segment_id: int = 1, db: Session = Depends(get_db)):
    runs = db.scalars(select(AllocationRun).where(AllocationRun.segment_id == segment_id)
                      .order_by(AllocationRun.id.desc())).all()
    return [{"id": r.id, "segment_id": r.segment_id,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in runs]


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(AllocationRun, run_id)
    if not run:
        raise HTTPException(404, "运行记录不存在")
    return _load_run(run)
