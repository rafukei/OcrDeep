# Docker-based MCP OCR Service — Specification

## 1. Project Overview

**Name:** modal-ocr-mcp

**Type:** Docker container with MCP server

**Summary:** A containerized OCR service that receives PDF files via MCP tool calls and returns extracted plain text using DeepSeek V3 vision capabilities running on Modal compute.

**Target Users:** AI agent frameworks (Hermes, OpenClaw, Flowise) that need PDF-to-text capability via MCP protocol.

---

## 2. Container Specification

### Base Image
- `python:3.11-slim`

### System Dependencies
- `poppler-utils` (provides `pdftoppm` used by pdf2image)
- `libsm6`, `libxext6`, `libxrender1`, `libjpeg62-turbo` (required by Pillow)

### Python Dependencies
- `modal` — Modal client for launching remote functions
- `mcp[server]` — MCP SDK with server support
- `pdf2image` — PDF → PIL Image conversion
- `Pillow` — image handling
- `openai` — OpenAI-compatible API client (DeepSeek is OpenAI-compatible)
- `python-dotenv` — environment variable loading
- `pydantic` — request/response models
- `uvicorn[standard]` — ASGI server

### Files
- `app.py` — MCP server + Modal integration (main entry point)
- `modal_worker.py` — Modal app with `@modal.function()` OCR function
- `requirements.txt` — pinned Python dependencies
- `Dockerfile` — container build
- `.env.example` — template for credentials
- `README.md` — usage docs

---

## 3. Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MODAL_TOKEN_ID` | Yes | Modal token ID for authentication |
| `MODAL_TOKEN_SECRET` | Yes | Modal token secret for authentication |
| `DEEPSEEK_API_KEY` | Yes | DeepSeek API key |
| `DEEPSEEK_BASE_URL` | No | DeepSeek API base URL (default: `https://api.deepseek.com`) |

---

## 4. Modal Worker

### App Name
`modal-ocr-mcp`

### Remote Function
`ocr_pdf(image_bytes: list[bytes]) -> str`

Takes a list of image bytes (one per PDF page), sends each to DeepSeek V3 with a vision prompt requesting OCR text extraction, concatenates results, returns full text.

### Model Used
`deepseek-ai/deepseek-v3-chat` via OpenAI-compatible API

### Prompt Template
```
You are an OCR system. Examine the image of a document page and extract ALL text content exactly as it appears, preserving paragraphs. If the image appears to be a photo or scan, still extract all visible text. Output only the extracted text, nothing else.
```

### Concurrency
Process up to 5 pages in parallel using `asyncio.gather`.

---

## 5. MCP Server

### Transport
Stdio (stdin/stdout) — standard MCP server pattern

### Server Name
`modal-ocr`

### Tools

#### `pdf_to_text`
- **Description:** Convert a PDF document to plain text using DeepSeek OCR running on Modal.
- **Input schema:**
  ```json
  {
    "pdf_data": "string (base64-encoded PDF bytes)",
    "language": "string (optional, default: 'auto')"
  }
  ```
- **Output schema:**
  ```json
  {
    "text": "string (extracted text)",
    "pages": "integer (number of pages processed)",
    "language_detected": "string"
  }
  ```

#### `health`
- **Description:** Health check for the MCP OCR service.
- **Input schema:** `{}`
- **Output:** `{"status": "ok", "service": "modal-ocr-mcp"}`

---

## 6. Data Flow

```
MCP Request (pdf_to_text)
    ↓
app.py: pdf_to_text tool handler
    ↓ base64 decode → PDF bytes
modal_worker.ocr_pdf.remote()  ← Modal cloud
    ↓ pdf2image (1 img per page)
    ↓ DeepSeek V3 vision API (page by page, max 5 concurrent)
    ↓ concatenate page texts
Extracted text string
    ↓
MCP Response: {"text": "...", "pages": N, "language_detected": "en"}
```

---

## 7. Docker Container

### Entrypoint
`python app.py` — starts the MCP stdio server

### Build
```bash
docker build -t modal-ocr-mcp:latest /tmp/modal-ocr-mcp
```

### Run
```bash
docker run --rm \
  -e MODAL_TOKEN_ID=<token_id> \
  -e MODAL_TOKEN_SECRET=<token_secret> \
  -e DEEPSEEK_API_KEY=<api_key> \
  modal-ocr-mcp
```

---

## 8. Error Handling

| Error | Behavior |
|-------|----------|
| Invalid base64 | Return `{"error": "Invalid base64 encoding"}` |
| PDF decode failure | Return `{"error": "Failed to decode PDF: ..."}` |
| Modal auth failure | Return `{"error": "Modal authentication failed"}` |
| DeepSeek API error | Return `{"error": "DeepSeek API error: ..."}` |
| Empty PDF (0 pages) | Return `{"error": "PDF has no pages"}` |

---

## 9. Acceptance Criteria

- [ ] Container builds successfully with `docker build`
- [ ] MCP server starts and responds to `initialize` handshake
- [ ] `health` tool returns `{"status": "ok"}`
- [ ] `pdf_to_text` with a valid PDF returns extracted text
- [ ] Invalid input returns appropriate error JSON
- [ ] Container works with only env vars — no additional setup needed
