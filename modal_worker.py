"""
Modal worker for PDF OCR using DeepSeek-OCR-2 model from HuggingFace.
Runs entirely on Modal GPU — no external API calls.

Model is cached at module level (one load per container) and reused for all pages.
"""
import base64, re
from io import BytesIO
import tempfile, os

import modal
from modal import App, Image as ModalImage, fastapi_endpoint

app = App("modal-ocr-mcp")
MODEL_NAME = "deepseek-ai/DeepSeek-OCR-2"

# Base image with GPU support and all dependencies
modal_image = (
    ModalImage.debian_slim(python_version="3.11")
    .apt_install("poppler-utils")
    .pip_install(
        "torch==2.6.0",
        "transformers==4.46.3",
        "huggingface-hub>=0.26.0,<0.30.0",
        "accelerate>=0.27.0",
        "pdf2image>=1.17.0,<2",
        "Pillow>=10.0.0",
        "sentencepiece>=0.1.99",
        "einops>=0.7.0",
        "addict>=2.4.0",
        "easydict>=1.10",
        "matplotlib>=3.0.0",
        "requests>=2.0.0",
        "torchvision>=0.15.0",
        "fastapi[standard]>=0.110.0",
    )
    .env({"FORCE_REBUILD": "17"})
)

# ─────────────────────────────────────────────────────────────────────────────
# Global model cache — loaded once per container, shared across all calls
# ─────────────────────────────────────────────────────────────────────────────
_cached_model = None
_cached_tokenizer = None


def _get_model():
    """Load model + tokenizer once; subsequent calls return cached instances."""
    global _cached_model, _cached_tokenizer
    if _cached_model is None:
        from transformers import AutoModel, AutoTokenizer
        print(f"Loading model {MODEL_NAME}...")
        _cached_tokenizer = AutoTokenizer.from_pretrained(
            MODEL_NAME, trust_remote_code=True
        )
        _cached_model = AutoModel.from_pretrained(
            MODEL_NAME,
            trust_remote_code=True,
            use_safetensors=True,
        )
        _cached_model = _cached_model.eval().cuda()
        print("Model loaded on GPU.")
    return _cached_model, _cached_tokenizer


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def pdf_bytes_to_images(pdf_bytes: bytes) -> list[bytes]:
    """
    Convert PDF bytes to PNG image bytes (one per page).

    Args:
        pdf_bytes: Raw PDF file bytes.

    Returns:
        List of PNG image bytes, one per page.
    """
    from pdf2image import convert_from_bytes
    images = convert_from_bytes(pdf_bytes, fmt="png", dpi=150)
    result = []
    for img in images:
        buf = BytesIO()
        img.save(buf, format="PNG")
        result.append(buf.getvalue())
    return result


def strip_ocr_markers(text: str) -> str:
    """
    Remove DeepSeek-OCR-2 output markers from text.

    Args:
        text: Raw model output string.

    Returns:
        Cleaned text with markers removed.
    """
    # Remove block-level markers (ref/det spans)
    text = re.sub(r'<\|ref\|>(.*?)<\|/ref\|>', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'<\|det\|>(.*?)<\|/det\|>', r'\1', text, flags=re.DOTALL)
    # Remove per-line bbox markers: text[[x,y,w,h]], title[[...]], etc.
    text = re.sub(r'^(?:text|title|sub_title|figure_title|table)\[\[.*?\]\]\n', '', text, flags=re.MULTILINE)
    return text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Modal GPU function — model reused across pages within same container call
# ─────────────────────────────────────────────────────────────────────────────

@app.function(image=modal_image, gpu="A100", timeout=900)
def ocr_pdf(pdf_bytes: bytes, language: str = "auto") -> dict:
    """
    Core OCR function — runs on Modal GPU.

    The model is loaded once when first called in a container, then reused
    for all subsequent pages within the same function call (same container).

    Args:
        pdf_bytes: Raw PDF file bytes.
        language: Target language or "auto" (default: "auto").

    Returns:
        Dict with keys:
            - text: Extracted plain text from all pages.
            - pages: Number of pages processed.
            - language_detected: Detected or specified language.
    """
    from PIL import Image as PILImage

    if not pdf_bytes:
        raise ValueError("No PDF data provided")

    images = pdf_bytes_to_images(pdf_bytes)
    if not images:
        raise ValueError("PDF has no pages")

    model, tokenizer = _get_model()

    prompt = (
        "<image>\n<|grounding|>Convert the document to markdown."
        if language == "auto"
        else f"<image>\n<|grounding|>Convert the document to markdown in {language}."
    )

    page_texts = []
    for i, img_bytes in enumerate(images):
        img = PILImage.open(BytesIO(img_bytes))
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            img.save(tmp.name)
            img_path = tmp.name
        try:
            result = model.infer(
                tokenizer,
                prompt=prompt,
                image_file=img_path,
                output_path="/tmp/ocr_out",
                base_size=1024,
                image_size=768,
                crop_mode=True,
                save_results=True,
                eval_mode=True,
            )
            if result:
                clean = strip_ocr_markers(result)
                page_texts.append(clean)
            print(f"Page {i+1}/{len(images)} done")
        finally:
            os.unlink(img_path)

    return {
        "text": "\n\n".join(page_texts),
        "pages": len(images),
        "language_detected": language if language != "auto" else "auto-detected",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Web endpoint (stateless FastAPI wrapper)
# ─────────────────────────────────────────────────────────────────────────────

@app.function(image=modal_image, timeout=900)
@fastapi_endpoint(method="POST")
def web_ocr(body: dict) -> dict:
    """
    FastAPI web endpoint — receives JSON, calls ocr_pdf on GPU, returns result.

    Args:
        body: JSON with keys:
            - pdf_data (str): Base64-encoded PDF bytes.
            - language (str, optional): Target language or "auto".

    Returns:
        Dict with keys:
            - text: Extracted plain text.
            - pages: Number of pages.
            - language_detected: Detected or specified language.
        Or dict with "error" key on failure.
    """
    import traceback

    pdf_b64 = body.get("pdf_data", "")
    language = body.get("language", "auto")

    if not pdf_b64:
        return {"error": "pdf_data is required"}

    try:
        pdf_bytes = base64.b64decode(pdf_b64)
    except Exception as e:
        return {"error": f"Invalid base64: {e}"}

    if pdf_bytes[:4] != b"%PDF":
        return {"error": "Data is not a valid PDF"}

    try:
        # ocr_pdf.remote() keeps the container alive between page iterations,
        # reusing the same model instance loaded by _get_model()
        result = ocr_pdf.remote(pdf_bytes, language=language)
        return result
    except Exception as e:
        return {"error": f"OCR failed: {e}\n{traceback.format_exc()}"}
