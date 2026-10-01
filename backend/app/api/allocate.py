import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import AllocationRun, Pillar, Segment, Vendor
from app.services.first_fit_engine import (
    allocate_first_fit,
    bands_payload_from_free_spans,
    result_to_dict,
    validate_margins,
)
router = APIRouter(prefix="/allocate", tags=["allocate"])

@router.post("/run")
def run_allocate(segment_id: int = 1, db: Session = Depends(get_db)):
    seg = db.get(Segment, segment_id)
    if not seg: raise HTTPException(404, "街段不存在")
    pillars = [{"position_m": p.position_m, "thickness_m": p.thickness_m}
               for p in db.scalars(select(Pillar).where(Pillar.segment_id == segment_id)).all()]
    vendors = [{"id": v.id, "name": v.name, "stall_width_m": v.stall_width_m, "priority": v.priority}
               for v in db.scalars(select(Vendor).where(Vendor.market_day_id == seg.market_day_id)).all()]
    result = allocate_first_fit(seg.width_m, vendors, pillars)
    # 余量闭区间不得与任一成功放置相交：相交则整次运行无效，不落库（行数不增），
    # 不修色档放过放置，也不把相交改写成放不下混记。
    violations = validate_margins(result.placements, result.margin_bands)
    if violations:
        raise HTTPException(status_code=409,
                            detail="运行结果无效：余量色档与成功放置相交，未落库；" + "；".join(violations))
    payload = result_to_dict(result)
    payload["segment"] = {"id": seg.id, "name": seg.name, "width_m": seg.width_m}
    payload["pillars"] = pillars
    # 确认落库瞬间固化色档：margin_bands 随 result_json 一并写入，之后改街宽/挪柱不回写。
    run = AllocationRun(segment_id=segment_id, created_at=datetime.utcnow(),
                        result_json=json.dumps(payload, ensure_ascii=False))
    db.add(run); db.commit(); db.refresh(run)
    return {"id": run.id, "created_at": run.created_at.isoformat(), **payload}

@router.get("/latest")
def latest(segment_id: int = 1, db: Session = Depends(get_db)):
    run = db.scalars(select(AllocationRun).where(AllocationRun.segment_id == segment_id)
                     .order_by(AllocationRun.id.desc())).first()
    if not run:
        return run_allocate(segment_id=segment_id, db=db)
    data = json.loads(run.result_json)
    # 旧结构（无 margin_bands 字段）须可读：由该次运行自身存档的 free_spans 推导，
    # 不按当前街宽/挡柱重算，也不回写旧运行。
    if "margin_bands" not in data:
        data["margin_bands"] = bands_payload_from_free_spans(data.get("free_spans", []))
    return {"id": run.id, "created_at": run.created_at.isoformat(), **data}
