# Modal OCR Service

Docker-based OCR service — converts PDFs to text using **DeepSeek-OCR-v2** model running on **Modal GPU** via REST API.

## Architecture

```
HTTP Request → Docker Container → Modal GPU → deepseek-ai/deepseek-ocr-v2
                                              ↓
                                     Extracted text → JSON Response
```

## Quick Start

### Build

```bash
docker build -t modal-ocr-api ~/DockerShared
```

### Run

```bash
docker run --rm \
  -p 7000:8000 \
  -e MODAL_TOKEN_ID=<your_token_id> \
  -e MODAL_TOKEN_SECRET=<your_token_secret> \
  modal-ocr-api
```

The container exposes a FastAPI REST server on port 8000 (mapped to host 7000).

## Get Modal Credentials

1. Sign up at [modal.com](https://modal.com)
2. Go to Settings → Tokens
3. Create a new token and copy the token ID and secret

## API Endpoints

### `POST /ocr`

Convert a PDF document to plain text using DeepSeek-OCR-v2 running on Modal GPU.

**Request (JSON):**
```json
{
  "pdf_data": "<base64-encoded PDF bytes>",
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

### `POST /ocr/file` (multipart)

Upload a PDF file directly for OCR processing.

**Request:** `multipart/form-data` with a `file` field containing the PDF.

**Response:** Same as `/ocr`.

### `GET /health`

Health check.

**Response:** `{"status": "ok", "service": "modal-ocr-api"}`

## Example Usage

```bash
# With JSON body
curl -X POST http://localhost:7000/ocr \
  -H "Content-Type: application/json" \
  -d '{"pdf_data": "'"$(base64 -w0 document.pdf)"'", "language": "auto"}'

# With file upload
curl -X POST http://localhost:7000/ocr/file \
  -F "file=@document.pdf"

# Health check
curl http://localhost:7000/health
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MODAL_TOKEN_ID` | Yes | Modal token ID (modal.com → Settings → Tokens) |
| `MODAL_TOKEN_SECRET` | Yes | Modal token secret |

## Container Ports

| Host | Container | Description |
|------|-----------|-------------|
| 7000 | 8000 | FastAPI REST server |

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
