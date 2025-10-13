from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Serve the static folder
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# simple in-memory command storage
latest_command = {"command": None}

@app.get("/")
def serve_frontend():
    return FileResponse("app/static/index.html")

@app.post("/api/command")
async def receive_command(request: Request):
    data = await request.json()
    command = data.get("command", "")
    latest_command["command"] = command
    print(f"Received command: {command}")
    return JSONResponse({"message": f"Command '{command}' received"})

@app.get("/api/latest")
def get_latest():
    return JSONResponse({"command": latest_command["command"]})
