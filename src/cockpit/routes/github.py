"""GitHub-Routes: Repo-Bookmarks (CRUD) + Live-Daten via api.github.com."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from ..auth import client_ip, require_auth
from ..crud import github_repos as crud_repos
from ..db import get_session
from ..models import RepoCreate, RepoOut, RepoUpdate, repo_row_to_out
from ..services import github_client

router = APIRouter(prefix="/admin/api/github", tags=["github"])


@router.get("/repos", response_model=list[RepoOut])
async def list_repos(_=Depends(require_auth), session: Session = Depends(get_session)) -> list[RepoOut]:
    rows = crud_repos.list_repos(session)
    return [repo_row_to_out(r) for r in rows]


@router.post("/repos", response_model=RepoOut, status_code=201)
async def add_repo(
    payload: RepoCreate,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> RepoOut:
    try:
        row = crud_repos.create_repo(session, payload, ip=client_ip(request))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return repo_row_to_out(row)


@router.patch("/repos/{repo_id}", response_model=RepoOut)
async def update_repo(
    repo_id: str,
    patch: RepoUpdate,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> RepoOut:
    row = crud_repos.update_repo(session, repo_id, patch, ip=client_ip(request))
    if row is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    return repo_row_to_out(row)


@router.delete("/repos/{repo_id}", status_code=204)
async def delete_repo(
    repo_id: str,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> Response:
    ok = crud_repos.delete_repo(session, repo_id, ip=client_ip(request))
    if not ok:
        raise HTTPException(status_code=404, detail="Repo not found")
    return Response(status_code=204)


def _ensure_token() -> None:
    if not github_client.is_enabled():
        raise HTTPException(
            status_code=503,
            detail="GitHub-Integration deaktiviert: GITHUB_TOKEN nicht gesetzt",
        )


@router.get("/repos/{owner}/{name}/branches")
async def repo_branches(owner: str, name: str, _=Depends(require_auth)) -> list[dict]:
    _ensure_token()
    try:
        return github_client.list_branches(owner, name)
    except github_client.GitHubDisabledError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/repos/{owner}/{name}/prs")
async def repo_prs(
    owner: str,
    name: str,
    state: str = Query("open", pattern="^(open|closed|all)$"),
    _=Depends(require_auth),
) -> list[dict]:
    _ensure_token()
    try:
        return github_client.list_pull_requests(owner, name, state=state)
    except github_client.GitHubDisabledError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/repos/{owner}/{name}/runs")
async def repo_runs(
    owner: str,
    name: str,
    limit: int = Query(10, ge=1, le=50),
    _=Depends(require_auth),
) -> list[dict]:
    _ensure_token()
    try:
        return github_client.list_workflow_runs(owner, name, limit=limit)
    except github_client.GitHubDisabledError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/repos/{owner}/{name}/meta")
async def repo_meta(owner: str, name: str, _=Depends(require_auth)) -> dict:
    _ensure_token()
    try:
        return github_client.repo_meta(owner, name)
    except github_client.GitHubDisabledError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/repos/{owner}/{name}/dispatch")
async def repo_dispatch(
    owner: str,
    name: str,
    body: dict,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> dict:
    _ensure_token()
    workflow_id = body.get("workflow_id")
    ref = body.get("ref", "main")
    inputs = body.get("inputs") or None
    if not workflow_id:
        raise HTTPException(status_code=400, detail="workflow_id fehlt")
    from ..crud import audit
    try:
        ok = github_client.dispatch_workflow(owner, name, workflow_id, ref=ref, inputs=inputs)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"GitHub: {exc}") from exc
    audit.write(
        session,
        action="github.dispatch",
        target=f"{owner}/{name}",
        after={"workflow_id": workflow_id, "ref": ref, "ok": ok},
        ip=client_ip(request),
    )
    return {"ok": ok, "workflow_id": workflow_id, "ref": ref}
