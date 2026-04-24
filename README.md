# Modal OCR Service

Docker-based OCR service — converts PDFs to text using **DeepSeek-OCR-v2** model running on **Modal GPU**.

## Architecture

```
HTTP Request → Docker Container → Modal GPU → deepseek-ai/deepseek-ocr-v2
                                              ↓
                                     Extracted text → JSON Response
```

## Quick Start

### 1. Build

```bash
docker build -t modal-ocr-api ~/DockerShared
```

### 2. Run

```bash
docker run --rm \
  -p 7000:8000 \
  -e MODAL_TOKEN_ID=<your_token_id> \
  -e MODAL_TOKEN_SECRET=<your_token_secret> \
  modal-ocr-api
```

### 3. Test

```bash
curl http://localhost:7000/health
```

## Get Modal Credentials

1. Sign up at [modal.com](https://modal.com)
2. Go to Settings → Tokens
3. Create a new token and copy the token ID and secret

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MODAL_TOKEN_ID` | Yes | — | Modal token ID |
| `MODAL_TOKEN_SECRET` | Yes | — | Modal token secret |
| `MODAL_ENDPOINT` | No | Modal web endpoint URL | Modal GPU inference URL |
| `PORT` | No | `7000` | Host port (container always uses 8000) |

---

## API Reference

Base URL: `http://localhost:7000`

---

### `GET /health`

Health check.

**Parameters:** None

**Response:**
```json
{
  "status": "ok",
  "service": "modal-ocr"
}
```

**Example:**
```bash
curl http://localhost:7000/health
```

---

### `POST /ocr`

Upload a PDF file and extract text.

**Content-Type:** `multipart/form-data`

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | Yes | PDF file |

**Response:**
```json
{
  "text": "Extracted text content...",
  "pages": 5,
  "language_detected": "en"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | Extracted plain text from all pages |
| `pages` | integer | Number of pages processed |
| `language_detected` | string | Detected or specified language |

**Error Responses:**

| Status | Body | Cause |
|--------|------|-------|
| 400 | `"File must be a PDF"` | Wrong file extension |
| 400 | `"Empty file"` | File is empty |
| 400 | `"Not a valid PDF file"` | Invalid PDF magic bytes |
| 502 | `"Modal returned N"` | Modal endpoint error |
| 503 | `"Cannot reach Modal endpoint"` | Modal unreachable |
| 504 | `"Modal OCR timed out (>5min)"` | OCR took too long |

**Example:**
```bash
curl -X POST http://localhost:7000/ocr -F "file=@document.pdf"
```

---

### `POST /ocr/json`

Send a base64-encoded PDF as JSON and extract text.

**Content-Type:** `application/json`

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pdf_data` | string | Yes | Base64-encoded PDF bytes |
| `language` | string | No | Language code or `"auto"` (default: `"auto"`) |

**Request Body:**
```json
{
  "pdf_data": "JVBERi0xLjQK...",
  "language": "auto"
}
```

**Response:**
```json
{
  "text": "Extracted text content...",
  "pages": 5,
  "language_detected": "en"
}
```

**Error Responses:**

| Status | Body | Cause |
|--------|------|-------|
| 400 | `"Empty PDF data"` | Empty base64 string |
| 400 | `"Not a valid PDF"` | Invalid base64 or not a PDF |
| 502 | `"Modal returned N"` | Modal endpoint error |
| 503 | `"Cannot reach Modal endpoint"` | Modal unreachable |
| 504 | `"Modal OCR timed out (>5min)"` | OCR took too long |

**Example:**
```bash
curl -X POST http://localhost:7000/ocr/json \
  -H "Content-Type: application/json" \
  -d '{"pdf_data": "'"$(base64 -w0 document.pdf)"'", "language": "auto"}'
```

---

## Container Details

| Host Port | Container Port | Protocol |
|-----------|----------------|----------|
| 7000 | 8000 | HTTP (FastAPI) |

Container port is fixed at 8000 inside the container. Map to any host port via `-p`.

---

## Project Structure

```
~/DockerShared/
├── app.py              # FastAPI REST server (runs in Docker)
├── modal_worker.py     # Modal GPU worker (deploy to Modal separately)
├── Dockerfile          # Docker image definition
├── requirements.txt    # Python dependencies for Docker
└── .env.example        # Environment variable template
```

---

## Deploy Modal Worker

The `modal_worker.py` must be deployed to Modal separately:

```bash
modal deploy modal_worker.py
```

After deployment, note the web endpoint URL and set it via `MODAL_ENDPOINT` env var, or use the default URL embedded in `app.py`.

---

## Troubleshooting

### "Modal authentication failed"
Ensure `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` are set correctly.

### Container exits immediately
Run with `-it` to see error output:
```bash
docker run -it --rm \
  -p 7000:8000 \
  -e MODAL_TOKEN_ID=<your_token_id> \
  -e MODAL_TOKEN_SECRET=<your_token_secret> \
  modal-ocr-api
```

### OCR returns empty text
- Check the PDF is not scanned/image-only (requires OCR-capable PDF)
- Try with a different PDF to confirm the service works
- Verify Modal endpoint is reachable from inside the container

### 502 from Modal
Modal GPU worker returned an error. Check Modal logs:
```bash
modal logs modal-ocr-mcp
```
