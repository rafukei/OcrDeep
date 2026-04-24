"""
FastAPI server for Docker-based OCR service using Modal + DeepSeek-OCR-2.
Receives PDF via HTTP, forwards to Modal GPU endpoint, returns extracted text.

Architecture:
  Client → FastAPI (Docker) → Modal Web Endpoint (GPU) → DeepSeek-OCR-2
"""
import base64
import os
import subprocess
from contextlib import asynccontextmanager

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Load .env if present
load_dotenv()

# Modal endpoint (deployed via modal_worker.py)
MODAL_ENDPOINT = os.environ.get(
    "MODAL_ENDPOINT",
    "https://raafael-keikko--modal-ocr-mcp-web-ocr.modal.run"
)


class OCRRequest(BaseModel):
    pdf_data: str  # base64-encoded PDF
    language: str = "auto"


class OCRResponse(BaseModel):
    text: str
    pages: int
    language_detected: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure Modal CLI is in PATH
    modal_path = "/usr/local/bin/modal"
    if os.path.exists(modal_path) and modal_path not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"/usr/local/bin:{os.environ.get('PATH', '')}"
    yield


app = FastAPI(
    title="Docker OCR Service",
    description="PDF OCR via Modal + DeepSeek-OCR-2",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "modal-ocr"}


@app.post("/ocr", response_model=OCRResponse)
def ocr_pdf(file: UploadFile = File(...)):
    """
    Upload a PDF file and get extracted text.

    Usage:
      curl -X POST http://localhost:7000/ocr -F "file=@document.pdf"

    Or with base64 JSON:
      curl -X POST http://localhost:7000/ocr/json \\
           -H "Content-Type: application/json" \\
           -d '{"pdf_data": "...base64...", "language": "auto"}'
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "File must be a PDF")

    pdf_bytes = file.file.read()
    if len(pdf_bytes) == 0:
        raise HTTPException(400, "Empty file")

    # Validate PDF magic bytes
    if pdf_bytes[:4] != b"%PDF":
        raise HTTPException(400, "Not a valid PDF file")

    # Encode to base64 for Modal
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")

    try:
        resp = requests.post(
            MODAL_ENDPOINT,
            json={"pdf_data": pdf_b64, "language": "auto"},
            timeout=300,
        )
    except requests.exceptions.Timeout:
        raise HTTPException(504, "Modal OCR timed out (>5min)")
    except requests.exceptions.ConnectionError:
        raise HTTPException(503, "Cannot reach Modal endpoint")

    if resp.status_code != 200:
        raise HTTPException(502, f"Modal returned {resp.status_code}: {resp.text[:500]}")

    result = resp.json()

    if "error" in result:
        raise HTTPException(500, f"OCR error: {result['error']}")

    return OCRResponse(
        text=result.get("text", ""),
        pages=result.get("pages", 0),
        language_detected=result.get("language_detected", "unknown"),
    )


@app.post("/ocr/json", response_model=OCRResponse)
def ocr_pdf_json(body: OCRRequest):
    """
    POST JSON with base64-encoded PDF directly.

    Usage:
      curl -X POST http://localhost:7000/ocr/json \\
           -H "Content-Type: application/json" \\
           -d '{"pdf_data": "...base64...", "language": "auto"}'
    """
    pdf_bytes = base64.b64decode(body.pdf_data)

    if len(pdf_bytes) == 0:
        raise HTTPException(400, "Empty PDF data")

    if pdf_bytes[:4] != b"%PDF":
        raise HTTPException(400, "Not a valid PDF")

    try:
        resp = requests.post(
            MODAL_ENDPOINT,
            json={"pdf_data": body.pdf_data, "language": body.language},
            timeout=300,
        )
    except requests.exceptions.Timeout:
        raise HTTPException(504, "Modal OCR timed out (>5min)")
    except requests.exceptions.ConnectionError:
        raise HTTPException(503, "Cannot reach Modal endpoint")

    if resp.status_code != 200:
        raise HTTPException(502, f"Modal returned {resp.status_code}")

    result = resp.json()

    if "error" in result:
        raise HTTPException(500, f"OCR error: {result['error']}")

    return OCRResponse(
        text=result.get("text", ""),
        pages=result.get("pages", 0),
        language_detected=result.get("language_detected", "unknown"),
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "7000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
