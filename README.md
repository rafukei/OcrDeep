# Modal OCR MCP Service

Docker-based OCR service with MCP interface — converts PDFs to text using **DeepSeek-OCR-v2** model running entirely on **Modal GPU** (no external API calls).

## Architecture

```
MCP Request (stdio) → Docker Container → Modal GPU → deepseek-ai/deepseek-ocr-v2
                                             ↓
                                    Extracted text → MCP Response
```

## Quick Start

### Build

```bash
docker build -t modal-ocr-mcp:latest /tmp/modal-ocr-mcp
```

### Run

```bash
docker run --rm \
  -e MODAL_TOKEN_ID=<your_modal_token_id> \
  -e MODAL_TOKEN_SECRET=<your_modal_token_secret> \
  modal-ocr-mcp
```

The container starts an MCP stdio server. Connect to it using any MCP client (Hermès Agent, Claude Desktop, etc.).

## Get Modal Credentials

1. Sign up at [modal.com](https://modal.com)
2. Go to Settings → Tokens
3. Create a new token and copy the token ID and secret

## MCP Tools

### `pdf_to_text`

Convert a PDF document to plain text using DeepSeek-OCR-v2 running on Modal GPU.

**Input:**
```json
{
  "pdf_data": "<base64-encoded PDF bytes>",
  "language": "auto"
}
```

**Output:**
```json
{
  "text": "Extracted text content...",
  "pages": 5,
  "language_detected": "en"
}
```

### `health`

Health check.

**Output:** `{"status": "ok", "service": "modal-ocr-mcp"}`

## Hermès Agent Integration

Add this to your `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  modal-ocr:
    command: "docker"
    args: ["run", "--rm", "-i",
           "-e", "MODAL_TOKEN_ID=<your_token_id>",
           "-e", "MODAL_TOKEN_SECRET=<your_token_secret>",
           "modal-ocr-mcp"]
```

Restart Hermès Agent and the `pdf_to_text` tool will be available.

## Health Check (Quick Test)

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' > /tmp/mcp_in
echo '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"health","arguments":{}}}' >> /tmp/mcp_in
docker run --rm -i \
  -e MODAL_TOKEN_ID=<your_token_id> \
  -e MODAL_TOKEN_SECRET=<your_token_secret> \
  modal-ocr-mcp < /tmp/mcp_in
```

## Troubleshooting

### "Modal authentication failed"
Ensure `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` are set correctly.

### Container exits immediately
Run with `-it` to see error output:
```bash
docker run -it --rm \
  -e MODAL_TOKEN_ID=<your_token_id> \
  -e MODAL_TOKEN_SECRET=<your_token_secret> \
  modal-ocr-mcp
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MODAL_TOKEN_ID` | Yes | Modal token ID (modal.com → Settings → Tokens) |
| `MODAL_TOKEN_SECRET` | Yes | Modal token secret |
