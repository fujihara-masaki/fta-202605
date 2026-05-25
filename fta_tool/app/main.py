import logging
import os
import pathlib
import time
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

# Load .env from fta_tool/.env, resolved relative to this file so that the
# location is correct regardless of which directory uvicorn is started from.
# override=True ensures .env values always win over pre-existing shell env vars.
_dotenv_path = pathlib.Path(__file__).parent.parent / ".env"
_dotenv_loaded = load_dotenv(dotenv_path=_dotenv_path, override=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if _dotenv_loaded:
    logger.info("dotenv loaded: %s", _dotenv_path)
else:
    logger.warning(
        "dotenv file not found at %s — relying on shell environment variables. "
        "Copy .env.example to .env and set your values.",
        _dotenv_path,
    )

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _get_factor_count(level_or_key) -> int:
    """Return the configured factor count for the given level or key."""
    defaults = {1: "4", 2: "3", 3: "2", "additional": "2"}
    env_keys = {
        1: "FTA_PRIMARY_FACTOR_COUNT",
        2: "FTA_SECONDARY_FACTOR_COUNT",
        3: "FTA_TERTIARY_FACTOR_COUNT",
        "additional": "FTA_ADDITIONAL_FACTOR_COUNT",
    }
    env_key = env_keys.get(level_or_key, "FTA_PRIMARY_FACTOR_COUNT")
    default  = defaults.get(level_or_key, "4")
    try:
        return max(1, int(os.environ.get(env_key, default)))
    except ValueError:
        return int(default)


def _log_startup_config() -> None:
    """Log effective configuration values at startup for easy diagnostics."""
    ai_provider = os.environ.get("AI_PROVIDER", "mock")
    logger.info("=== FTA Tool startup configuration ===")
    logger.info("  AI_PROVIDER                = %s", ai_provider)
    logger.info("  FTA_PRIMARY_FACTOR_COUNT   = %s", os.environ.get("FTA_PRIMARY_FACTOR_COUNT", "4"))
    logger.info("  FTA_SECONDARY_FACTOR_COUNT = %s", os.environ.get("FTA_SECONDARY_FACTOR_COUNT", "3"))
    logger.info("  FTA_TERTIARY_FACTOR_COUNT  = %s", os.environ.get("FTA_TERTIARY_FACTOR_COUNT", "2"))
    logger.info("  FTA_ADDITIONAL_FACTOR_COUNT= %s", os.environ.get("FTA_ADDITIONAL_FACTOR_COUNT", "2"))
    if ai_provider == "ollama":
        logger.info("  OLLAMA_BASE_URL            = %s", os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))
        logger.info("  OLLAMA_MODEL               = %s", os.environ.get("OLLAMA_MODEL", "gemma3:4b"))
        logger.info("  OLLAMA_TIMEOUT_SECONDS     = %s", os.environ.get("OLLAMA_TIMEOUT_SECONDS", "180"))
        logger.info("  OLLAMA_KEEP_ALIVE          = %s", os.environ.get("OLLAMA_KEEP_ALIVE", "10m"))
        logger.info("  OLLAMA_NUM_PREDICT         = %s", os.environ.get("OLLAMA_NUM_PREDICT", "768"))
        logger.info("  OLLAMA_TEMPERATURE         = %s", os.environ.get("OLLAMA_TEMPERATURE", "0.2"))
        logger.info("  OLLAMA_NUM_CTX             = %s", os.environ.get("OLLAMA_NUM_CTX", "4096"))
    elif ai_provider == "azure_openai":
        logger.info("  AZURE_OPENAI_ENDPOINT      = %s", os.environ.get("AZURE_OPENAI_ENDPOINT", "(not set)"))
        logger.info("  AZURE_OPENAI_DEPLOYMENT    = %s", os.environ.get("AZURE_OPENAI_DEPLOYMENT", "(not set)"))
        # API key intentionally omitted from logs
    logger.info("=======================================")


@asynccontextmanager
async def lifespan(app: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    _log_startup_config()
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
    additional = bool(data.get("additional", False))

    factor_count = _get_factor_count("additional" if additional else level)

    nodes = crud.get_nodes_by_analysis(db, analysis_id)
    node_map = {n.id: n for n in nodes}

    # Determine parent nodes to generate children for
    if level == 1:
        parent_nodes = [None]
    else:
        parent_level = level - 1
        if parent_id:
            parent_node = node_map.get(parent_id)
            parent_nodes = [parent_node] if parent_node else []
        else:
            parent_nodes = [n for n in nodes if n.level == parent_level and n.user_judgement == "yes"]

    if not parent_nodes:
        return JSONResponse({
            "success": False,
            "message": "生成対象の親要因がありません（Yes評価の要因がありません）",
            "created": 0,
            "skipped": 0,
            "elapsed_ms": 0,
            "parent_id": parent_id,
        })

    ai_provider = get_ai_provider()
    total_created = 0
    total_skipped = 0
    errors = []
    t_start = time.time()

    for parent_node in parent_nodes:
        # Build parent path
        path_nodes = []
        current = parent_node
        while current is not None:
            path_nodes.append(current.title)
            current = node_map.get(current.parent_id) if current.parent_id else None
        parent_path = list(reversed(path_nodes))

        parent_factor = parent_node.title if parent_node else None
        parent_id_val = parent_node.id if parent_node else None

        existing_titles = [
            n.title for n in nodes
            if n.level == level and n.parent_id == parent_id_val
        ]

        try:
            t_node_start = time.time()
            factors: list[GeneratedFactor] = ai_provider.generate_factors(
                analysis_title=analysis.title,
                top_event=analysis.top_event,
                target_level=level,
                parent_path=parent_path,
                parent_factor=parent_factor,
                context={
                    "analysis_id": analysis_id,
                    "factor_count": factor_count,
                    "existing_titles": existing_titles,
                    "additional": additional,
                },
            )
            elapsed_node_ms = int((time.time() - t_node_start) * 1000)
        except RuntimeError as e:
            logger.error("AI generation error | analysis=%d level=%d parent=%r: %s",
                         analysis_id, level, parent_factor or "(top event)", e)
            errors.append(str(e))
            continue

        existing_max_order = max(
            (n.display_order for n in nodes if n.level == level and n.parent_id == parent_id_val),
            default=-1,
        )

        created_this = 0
        skipped_dedup_this = 0
        for i, factor in enumerate(factors):
            if crud.node_title_exists(db, analysis_id, parent_id_val, level, factor.title):
                logger.info(
                    "dedup skip | level=%d parent=%r title=%r (already in DB)",
                    level, parent_factor or "(top event)", factor.title,
                )
                skipped_dedup_this += 1
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
            created_this += 1

        total_created += created_this
        total_skipped += skipped_dedup_this
        logger.info(
            "generate_factors summary | analysis=%d level=%d parent=%r "
            "limit=%d ai_returned=%d created=%d skipped_dedup=%d elapsed=%dms",
            analysis_id, level, parent_factor or "(top event)",
            factor_count, len(factors), created_this, skipped_dedup_this, elapsed_node_ms,
        )

    elapsed_ms = int((time.time() - t_start) * 1000)
    skip_note = f"（{total_skipped}件重複スキップ）" if total_skipped else ""

    if errors:
        return JSONResponse({
            "success": False,
            "message": f"一部でエラーが発生しました: {'; '.join(errors)}",
            "created": total_created,
            "skipped": total_skipped,
            "elapsed_ms": elapsed_ms,
            "parent_id": parent_id,
        })

    return JSONResponse({
        "success": True,
        "message": f"{total_created}件の要因を生成しました{skip_note}",
        "created": total_created,
        "skipped": total_skipped,
        "elapsed_ms": elapsed_ms,
        "parent_id": parent_id,
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
