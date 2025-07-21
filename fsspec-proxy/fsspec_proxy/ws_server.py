from fastapi import FastAPI, WebSocket
import starlette.websockets

app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        try:
            data = await websocket.receive_bytes()
            uid = int.from_bytes(data[:4], "little")
            print(uid)
            await websocket.send_bytes(data)
        except starlette.websockets.WebSocketDisconnect:
            break


# example use in cpython
from websockets.asyncio.client import connect

async def run_one():
    async with connect("ws://localhost:8000/ws") as ws:
        await ws.send(b"test")
        print(await ws.recv())

"""
# example use in pyscript
from pyscript import WebSocket

def onopen(event):
    print(event.type)
    ws.send("hello")

def onmessage(event):
    print(event.type, event.data)
    ws.close()

def onclose(event):
    print(event.type)

ws = WebSocket(url="ws://localhost:8000/ws")
ws.onopen = onopen
ws.onmessage = onmessage
ws.onclose = onclose
"""
