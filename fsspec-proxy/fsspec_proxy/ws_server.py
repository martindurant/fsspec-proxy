from contextlib import asynccontextmanager
import json

from fastapi import FastAPI, WebSocket
import fsspec
import starlette.websockets

from fsspec_proxy import file_manager

app = FastAPI()
m = fsspec.filesystem("memory")
m.pipe_file("mytests/afile", b"hello world")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # start instances in async context
    app.manager = file_manager.FileSystemManager()
    yield


app = FastAPI(lifespan=lifespan)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        try:
            data = await websocket.receive_bytes()
            meta_length = int.from_bytes(data[:2], byteorder="big")
            meta = json.loads(data[2:2 + meta_length].decode())
            print(meta)
            uid = meta.pop("uid")
            result = await dispatch(**meta)
            if isinstance(result, dict):
                result["uid"] = uid
                await _send_bytes(websocket, result)
            else:
                await _send_bytes(websocket, {"uid": uid}, data=result)
        except starlette.websockets.WebSocketDisconnect:
            break
        except Exception as e:
            await _send_bytes(
                websocket,
              {"status": "error", "uid": uid, "error": str(e)}
            )


async def _send_bytes(ws, message, data=None):
    meta = json.dumps(message).encode()
    payload = len(meta).to_bytes(2, "little") + meta
    if data:
        payload += data
    await ws.send_bytes(payload)


routes = {}


def register_route(route: str):
    def wrapper(func):
        routes[route] = func
        return func
    return wrapper


async def dispatch(route, **op):
    print(route, op)
    return await routes[route](**op)


@register_route("list")
async def list_dir(key=None, path=""):
    if not key:
        keys = list(app.manager.filesystems)
        return {
            "status": "ok",
            "contents": [
                {"name": k, "size": 0, "type": "directory"} for k in keys
            ]
        }

    fs_info = app.manager.get_filesystem(key)
    if fs_info is None:
        raise FileNotFoundError(key)
    path = f"{fs_info['path'].rstrip('/')}/{path.lstrip('/')}"
    out = await fs_info["instance"]._ls(path, detail=True)
    out = [
        {"name": f"{key}/{o['name'].replace(fs_info['path'], '', 1).lstrip('/')}",
         "size": o["size"], "type": o["type"]}
        for o in out
    ]
    return {"status": "ok", "contents": out}


@app.delete("delete")
async def delete_file(key, path):
    fs_info = app.manager.get_filesystem(key)
    path = f"{fs_info['path'].rstrip('/')}/{path.lstrip('/')}"
    if fs_info is None:
        raise FileNotFoundError
    if fs_info.get("readonly"):
        raise PermissionError
    await fs_info["instance"]._rm_file(path)


@register_route("get")
async def get_bytes(key, path, start=None, end=None):
    fs_info = app.manager.get_filesystem(key)
    if fs_info is None:
        raise FileNotFoundError
    path = f"{fs_info['path'].rstrip('/')}/{path.lstrip('/')}"
    return await fs_info["instance"]._cat_file(path, start=start, end=end)


@app.post("put")
async def put_bytes(key, path, data=b""):
    fs_info = app.manager.get_filesystem(key)
    if fs_info is None:
        raise FileNotFoundError
    if fs_info.get("readonly"):
        raise PermissionError
    path = f"{fs_info['path'].rstrip('/')}/{path.lstrip('/')}"
    await fs_info["instance"]._pipe_file(path, data)
    return {"status": "ok"}


@register_route("health")
async def ok():
    return {"status": "ok"}

