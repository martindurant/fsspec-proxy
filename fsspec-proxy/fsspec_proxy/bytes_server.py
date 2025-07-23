from contextlib import asynccontextmanager
import io
import logging
import os

import fastapi
import fsspec
from fsspec_proxy.cors import CORSMiddleware
from starlette.responses import StreamingResponse

from fsspec_proxy import file_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    # start instances in async context
    app.manager = file_manager.FileSystemManager()
    yield


origin = os.getenv("FSPEC_PROXY_ORIGIN", 'https://martindurant.pyscriptapps.com')
app = fastapi.FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin],
    allow_methods=["GET", "POST", "DELETE", "OPTION", "PUT"],
    allow_credentials=True,
    allow_headers=["*"]
)
m = fsspec.filesystem('memory')
m.pipe_file("mytests/afile", b"hello world")


@app.get("/api/proxies/{key}/list/{path:path}")
async def list_dir(key, path):
    path = path.rstrip("/")
    logger.info(f"Listing {key} {path}")
    fs_info = app.manager.get_filesystem(key)
    if fs_info is None:
        raise fastapi.HTTPException(status_code=404, detail="fs not found")
    path = f"{fs_info['path'].rstrip('/')}/{path.lstrip('/')}"
    try:
        out = await fs_info["instance"]._ls(path, detail=True)
    except FileNotFoundError:
        raise fastapi.HTTPException(status_code=404, detail="path not found")
    out = [
        {"name": f"{key}/{o['name'].replace(fs_info['path'], '', 1).lstrip('/')}",
         "size": o["size"], "type": o["type"]}
        for o in out
    ]
    return {"status": "ok", "contents": out}


@app.delete("/api/proxies/{key}/delete/{path:path}")
async def delete_file(key, path, response: fastapi.Response):
    fs_info = app.manager.get_filesystem(key)
    path = f"{fs_info['path'].rstrip('/')}/{path.lstrip('/')}"
    if fs_info is None:
        raise fastapi.HTTPException(status_code=404, detail="Item not found")
    if fs_info.get("readonly"):
        raise fastapi.HTTPException(status_code=403, detail="Not Allowed")
    try:
        await fs_info["instance"]._rm_file(path)
    except FileNotFoundError:
        raise fastapi.HTTPException(status_code=404, detail="Item not found")
    except PermissionError:
        raise fastapi.HTTPException(status_code=403, detail="Not Allowed")
    response.status_code = 204


@app.get("/api/proxies/{key}/bytes/{path:path}")
async def get_bytes(key, path, request: fastapi.Request):
    start, end = _process_range(request.headers.get("Range"))
    fs_info = app.manager.get_filesystem(key)
    if fs_info is None:
        raise fastapi.HTTPException(status_code=404, detail="Item not found")
    path = f"{fs_info['path'].rstrip('/')}/{path.lstrip('/')}"
    try:
        out = await fs_info["instance"]._cat_file(path, start=start, end=end)
    except FileNotFoundError:
        raise fastapi.HTTPException(status_code=404, detail="Item not found")
    return StreamingResponse(io.BytesIO(out), media_type="application/octet-stream")


@app.post("/api/proxies/{key}/bytes/{path:path}")
async def put_bytes(key, path, request: fastapi.Request, response: fastapi.Response):
    fs_info = app.manager.get_filesystem(key)
    if fs_info is None:
        raise fastapi.HTTPException(status_code=404, detail="Item not found")
    if fs_info.get("readonly"):
        raise fastapi.HTTPException(status_code=403, detail="Not Allowed")
    path = f"{fs_info['path'].rstrip('/')}/{path.lstrip('/')}"
    data = await request.body()
    try:
        await fs_info["instance"]._pipe_file(path, data)
    except FileNotFoundError:
        raise fastapi.HTTPException(status_code=404, detail="Item not found")
    response.status_code = 201
    return {"contents": []}


def _process_range(range):
    if range and range.startswith("bytes=") and range.count("-") == 1:
        sstart, sstop = range.split("=")[1].split("-")
        if sstart == "":
            start = int(sstop)
            end = None
        elif sstop == "":
            start = int(sstart)
            end = None
        else:
            start = int(sstart)
            end = int(sstop) - 1
    else:
        start = end = None
    return start, end


@app.get("/health")
async def ok():
    return {"status": "ok", "contents": []}
