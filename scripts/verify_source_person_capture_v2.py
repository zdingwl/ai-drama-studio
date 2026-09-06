"""在数据库副本上验证真实原片人物提取；原库与原片只读，不提交人工身份。

示例：python scripts/verify_source_person_capture_v2.py --episode EPISODE_x --shot 3 --output .runtime/person-acceptance
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode", required=True)
    parser.add_argument("--shot", type=int)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--reuse", action="store_true")
    args = parser.parse_args()
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from engine.app import studio_v2 as studio
    from engine.app.main import app
    from engine.app.source_person_capture_v2 import capture, SourcePersonImage
    from engine.app.source_person_assets_v1 import inventory
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    destination = root / "acceptance.sqlite3"
    if destination == studio.DB_PATH.resolve():
        raise ValueError("验收副本不能覆盖原库")
    if not args.reuse:
        with sqlite3.connect(f"file:{studio.DB_PATH.as_posix()}?mode=ro", uri=True) as source, sqlite3.connect(destination) as copy:
            source.backup(copy)
    studio.ENGINE = create_engine(f"sqlite:///{destination.as_posix()}", connect_args={"check_same_thread": False})
    studio.SessionLocal = sessionmaker(bind=studio.ENGINE, autoflush=False, expire_on_commit=False)
    studio.Base.metadata.create_all(studio.ENGINE)
    start = time.monotonic()
    if not args.reuse:
        result = capture(args.episode, shot_ordinal=args.shot, progress=lambda current,total,message: print(f"{current}/{total} {message}", flush=True))
        project = studio.get_episode(args.episode)["project_id"]
        workspace = inventory(project)
        result.update(elapsed_seconds=round(time.monotonic()-start, 2), database=str(destination),
                      summary=workspace["summary"], characters=[dict(id=c["id"], name=c["name"], cover_url=c["cover_url"], shot_count=c["shot_count"]) for c in workspace["characters"]])
        (root / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        with studio.get_session() as session:
            for index, image in enumerate(session.scalars(select(SourcePersonImage).where(SourcePersonImage.episode_id == args.episode)).all()[:6]):
                (root / f"person-{index+1}.png").write_bytes(image.image)
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    if args.serve:
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles
        import uvicorn
        dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
        app.mount("/assets", StaticFiles(directory=dist / "assets"))
        @app.get("/{path:path}")
        def frontend(path: str):
            return FileResponse(dist / "index.html")
        uvicorn.run(app, host="127.0.0.1", port=8001, lifespan="off")


if __name__ == "__main__":
    main()
