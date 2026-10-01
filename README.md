# StallSpan 市集摊档开间

沿街段一维 First-Fit 开间分配，挡柱不可被摊位跨越，输出分配图与放不下清单。

技术栈：Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL / Vue 3 / TypeScript / Vite

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4700 |
| API | http://localhost:9700 |
| API 文档 | http://localhost:9700/docs |
| Postgres | localhost:5448 |

健康检查：`GET http://localhost:9700/api/health`

## 使用说明

1. 在「集日」「街段」确认开市日与可用宽度。
2. 在「摊主」「挡柱」维护需求宽度与障碍位置。
3. 打开「分配图」执行一维开间分配；主图下方色带与右侧栏展示柱间余量色档（起止米、剩余长度、紧<3m / 中3–6m / 松≥6m），「运行抽屉」可查看当次运行详情。
4. 在「放不下」查看无法安置的摊位及其可摆提示（与主图同一套余量色档）。

余量色档在运行落库瞬间固化进 `result_json`；之后改街宽或挪柱再跑只会产生新运行，旧运行色档不回写。色档闭区间与任一成功放置发生正长度相交时，整次运行无效（409），运行行数不增。

## 开发与测试

```bash
docker compose exec api pytest -q
```
