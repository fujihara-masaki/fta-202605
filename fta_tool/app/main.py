import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import crud, models, schemas
from .database import SessionLocal, engine, get_db
from .services.ai_provider import GeneratedFactor, get_ai_provider
from .services.export_service import export_csv, export_json, export_markdown

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@asynccontextmanager
async def lifespan(app: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="FTA分析支援ツール", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# --- Analysis endpoints ---

@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    analyses = crud.get_analyses(db)
    return templates.TemplateResponse("index.html", {"request": request, "analyses": analyses})


@app.get("/analyses/new", response_class=HTMLResponse)
def new_analysis_form(request: Request):
    return templates.TemplateResponse("analysis_form.html", {"request": request})


@app.post("/analyses")
def create_analysis(
    title: str = Form(...),
    top_event: str = Form(""),
    db: Session = Depends(get_db),
):
    analysis_data = schemas.AnalysisCreate(title=title, top_event=top_event)
    analysis = crud.create_analysis(db, analysis_data)
    return RedirectResponse(url=f"/analyses/{analysis.id}", status_code=303)


@app.get("/analyses/{analysis_id}", response_class=HTMLResponse)
def analysis_detail(request: Request, analysis_id: int, db: Session = Depends(get_db)):
    analysis = crud.get_analysis(db, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="分析が見つかりません")

    nodes = crud.get_nodes_by_analysis(db, analysis_id)

    # Build tree structure for template
    node_map = {n.id: n for n in nodes}
    # level1: top level factors, grouped by parent
    level1_nodes = [n for n in nodes if n.level == 1]
    level2_nodes = [n for n in nodes if n.level == 2]
    level3_nodes = [n for n in nodes if n.level == 3]

    # Build parent->children dict for levels
    children_of: dict[int, list] = {}
    for node in nodes:
        if node.parent_id:
            children_of.setdefault(node.parent_id, []).append(node)

    ai_provider_name = os.environ.get("AI_PROVIDER", "mock")

    return templates.TemplateResponse(
        "analysis_detail.html",
        {
            "request": request,
            "analysis": analysis,
            "nodes": nodes,
            "level1_nodes": level1_nodes,
            "level2_nodes": level2_nodes,
            "level3_nodes": level3_nodes,
            "children_of": children_of,
            "node_map": node_map,
            "ai_provider_name": ai_provider_name,
        },
    )


@app.post("/analyses/{analysis_id}/top-event")
async def update_top_event(analysis_id: int, request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    top_event = data.get("top_event", "")
    analysis = crud.update_top_event(db, analysis_id, top_event)
    if not analysis:
        raise HTTPException(status_code=404, detail="分析が見つかりません")
    return {"success": True, "top_event": analysis.top_event}


@app.post("/analyses/{analysis_id}/generate/level/{level}")
async def generate_factors(
    analysis_id: int,
    level: int,
    request: Request,
    db: Session = Depends(get_db),
):
    if level not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="レベルは1、2、3のいずれかを指定してください")

    analysis = crud.get_analysis(db, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="分析が見つかりません")

    data = await request.json()
    parent_id = data.get("parent_id")

    nodes = crud.get_nodes_by_analysis(db, analysis_id)
    node_map = {n.id: n for n in nodes}

    # Determine parent nodes to generate children for
    if level == 1:
        # Generate first-level factors from top event (no parent node)
        parent_nodes = [None]
    else:
        # Generate children for yes-judged nodes of the previous level
        parent_level = level - 1
        if parent_id:
            parent_node = node_map.get(parent_id)
            parent_nodes = [parent_node] if parent_node else []
        else:
            parent_nodes = [n for n in nodes if n.level == parent_level and n.user_judgement == "yes"]

    if not parent_nodes:
        return JSONResponse({"success": False, "message": "生成対象の親要因がありません（Yes評価の要因がありません）", "created": 0})

    ai_provider = get_ai_provider()
    total_created = 0
    errors = []

    for parent_node in parent_nodes:
        # Build parent path
        parent_path: list[str] = []
        current = parent_node
        path_nodes = []
        while current is not None:
            path_nodes.append(current.title)
            current = node_map.get(current.parent_id) if current.parent_id else None
        parent_path = list(reversed(path_nodes))

        parent_factor = parent_node.title if parent_node else None

        try:
            factors: list[GeneratedFactor] = ai_provider.generate_factors(
                analysis_title=analysis.title,
                top_event=analysis.top_event,
                target_level=level,
                parent_path=parent_path,
                parent_factor=parent_factor,
                context={"analysis_id": analysis_id},
            )
        except RuntimeError as e:
            logger.error(f"AI generation error: {e}")
            errors.append(str(e))
            continue

        parent_id_val = parent_node.id if parent_node else None
        existing_max_order = max(
            (n.display_order for n in nodes if n.level == level and n.parent_id == parent_id_val),
            default=-1,
        )

        for i, factor in enumerate(factors):
            # Dedup by title
            if crud.node_title_exists(db, analysis_id, parent_id_val, level, factor.title):
                continue

            node_data = {
                "parent_id": parent_id_val,
                "level": level,
                "title": factor.title,
                "description": factor.description,
                "ai_generated": True,
                "user_judgement": "unknown",
                "direct_cause_status": "unknown",
                "display_order": existing_max_order + i + 1,
            }
            crud.create_node(db, analysis_id, node_data)
            total_created += 1

    if errors:
        return JSONResponse({
            "success": False,
            "message": f"一部でエラーが発生しました: {'; '.join(errors)}",
            "created": total_created,
        })

    return JSONResponse({
        "success": True,
        "message": f"{total_created}件の要因を生成しました",
        "created": total_created,
    })


# --- Node endpoints ---

@app.post("/nodes/{node_id}/update")
async def update_node(node_id: int, request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    update_data = schemas.NodeUpdate(**data)
    node = crud.update_node(db, node_id, update_data)
    if not node:
        raise HTTPException(status_code=404, detail="ノードが見つかりません")
    return {"success": True}


@app.post("/nodes/{node_id}/delete")
def delete_node(node_id: int, db: Session = Depends(get_db)):
    node = crud.delete_node(db, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="ノードが見つかりません")
    return {"success": True}


@app.post("/nodes/{parent_id}/children")
async def add_child_node(parent_id: int, request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    parent_node = crud.get_node(db, parent_id)
    if not parent_node:
        raise HTTPException(status_code=404, detail="親ノードが見つかりません")

    title = data.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="タイトルを入力してください")

    level = parent_node.level + 1
    if level > 3:
        raise HTTPException(status_code=400, detail="これ以上の階層は作成できません")

    if crud.node_title_exists(db, parent_node.analysis_id, parent_id, level, title):
        raise HTTPException(status_code=409, detail="同名の要因が既に存在します")

    node_data = {
        "parent_id": parent_id,
        "level": level,
        "title": title,
        "description": data.get("description", ""),
        "ai_generated": False,
        "user_judgement": "unknown",
        "direct_cause_status": "unknown",
        "display_order": 999,
    }
    node = crud.create_node(db, parent_node.analysis_id, node_data)
    return {"success": True, "node_id": node.id}


@app.post("/analyses/{analysis_id}/nodes/add-level1")
async def add_level1_node(analysis_id: int, request: Request, db: Session = Depends(get_db)):
    analysis = crud.get_analysis(db, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="分析が見つかりません")

    data = await request.json()
    title = data.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="タイトルを入力してください")

    if crud.node_title_exists(db, analysis_id, None, 1, title):
        raise HTTPException(status_code=409, detail="同名の要因が既に存在します")

    node_data = {
        "parent_id": None,
        "level": 1,
        "title": title,
        "description": data.get("description", ""),
        "ai_generated": False,
        "user_judgement": "unknown",
        "direct_cause_status": "unknown",
        "display_order": 999,
    }
    node = crud.create_node(db, analysis_id, node_data)
    return {"success": True, "node_id": node.id}


# --- Export endpoints ---

@app.get("/analyses/{analysis_id}/export/json")
def export_analysis_json(analysis_id: int, db: Session = Depends(get_db)):
    content = export_json(db, analysis_id)
    return PlainTextResponse(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=fta_{analysis_id}.json"},
    )


@app.get("/analyses/{analysis_id}/export/csv")
def export_analysis_csv(analysis_id: int, db: Session = Depends(get_db)):
    content = export_csv(db, analysis_id)
    return PlainTextResponse(
        content=content,
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename=fta_{analysis_id}.csv"},
    )


@app.get("/analyses/{analysis_id}/export/markdown")
def export_analysis_markdown(analysis_id: int, db: Session = Depends(get_db)):
    content = export_markdown(db, analysis_id)
    return PlainTextResponse(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=fta_{analysis_id}.md"},
    )
