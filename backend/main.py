from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def index():
    return {"message": "Backend is running"}

@app.get("/health")
def health():
    return {"status": "healthy"}