from datetime import date
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.models import MarketDay, Pillar, Segment, Vendor

def seed_if_empty(db: Session) -> None:
    if (db.scalar(select(func.count()).select_from(MarketDay)) or 0) > 0:
        return
    day = MarketDay(name="周末夜市", day=date(2026, 9, 20))
    db.add(day); db.flush()
    # 东街段 30m，两盏灯柱切成三个柱间空档：
    # [0,9.75] / [10.25,19.75] / [20.25,30]（柱体各 0.5m）。
    seg = Segment(market_day_id=day.id, name="东街段", width_m=30.0)
    db.add(seg); db.flush()
    db.add(Pillar(segment_id=seg.id, position_m=10.0, thickness_m=0.5, label="灯柱A"))
    db.add(Pillar(segment_id=seg.id, position_m=20.0, thickness_m=0.5, label="灯柱B"))
    # First-fit 落位后余量（被灯柱切开，各居一档）：
    #   柱间一 [8.5,9.75]   剩 1.25m 紧
    #   柱间二 [17.75,19.75] 剩 2.0m 中
    #   柱间三 [25.25,30]    剩 4.75m 松
    vendors = [
        ("阿强烧烤", 3.5, 1), ("林记糖水", 3.0, 1), ("大碗面", 6.0, 1),
        ("老周水果", 5.0, 2), ("小美饰品", 2.0, 2),
        ("手作皮具", 1.5, 3),
        ("巨型舞台车", 12.0, 9),
    ]
    for name, wdt, pri in vendors:
        db.add(Vendor(market_day_id=day.id, name=name, stall_width_m=wdt, priority=pri))
    db.commit()
