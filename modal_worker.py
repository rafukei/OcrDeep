"""
Modal worker for PDF OCR using DeepSeek-OCR-2 model from HuggingFace.
Runs entirely on Modal GPU — no external API calls.

Key insight from source code: model.infer(eval_mode=True) returns text directly.
"""
import base64, re
from io import BytesIO
import tempfile, os

import modal
from modal import App, Image as ModalImage, fastapi_endpoint

# Modal app name
app = App("modal-ocr-mcp")

# HuggingFace model
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
    .env({"FORCE_REBUILD": "15"})
)

# Global model/tokenizer cache
_cached_model = None
_cached_tokenizer = None


def pdf_bytes_to_images(pdf_bytes: bytes) -> list[bytes]:
    """Convert PDF bytes to PNG image bytes (one per page)."""
    from pdf2image import convert_from_bytes
    images = convert_from_bytes(pdf_bytes, fmt="png", dpi=150)
    result = []
    for img in images:
        buf = BytesIO()
        img.save(buf, format="PNG")
        result.append(buf.getvalue())
    return result


def get_model():
    """Load and cache model+tokenizer (called once per container)."""
    global _cached_model, _cached_tokenizer
    if _cached_model is None:
        import torch
        from transformers import AutoModel, AutoTokenizer

        _cached_tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
        _cached_model = AutoModel.from_pretrained(
            MODEL_NAME,
            trust_remote_code=True,
            use_safetensors=True,
        )
        _cached_model = _cached_model.eval().cuda()

    return _cached_model, _cached_tokenizer


def strip_ocr_markers(text: str) -> str:
    """
    DeepSeek-OCR-2 outputs text with <|ref|>...<|/ref|> and <|det|>...<|/det|> markers.
    Extract clean text by stripping these markers.
    """
    # Remove <|ref|>text content<|/ref|> pairs
    text = re.sub(r'<\|ref\|>(.*?)<\|/ref\|>', r'\1', text)
    # Remove <|det|>bbox coordinates<|/det|> pairs
    text = re.sub(r'<\|det\|>(.*?)<\|/det\|>', r'\1', text)
    return text.strip()


@app.function(image=modal_image, gpu="a10g", timeout=600)
def ocr_pdf(pdf_bytes: bytes, language: str = "auto") -> dict:
    """
    Core OCR function — runs on Modal GPU.
    Uses model.infer(eval_mode=True) which returns text directly.
    """
    from PIL import Image as PILImage

    if not pdf_bytes:
        raise ValueError("No PDF data provided")

    images = pdf_bytes_to_images(pdf_bytes)
    if not images:
        raise ValueError("PDF has no pages")

    model, tokenizer = get_model()

    if language == "auto":
        prompt = "<image>\n<|grounding|>Convert the document to markdown."
    else:
        prompt = f"<image>\n<|grounding|>Convert the document to markdown in {language}."

    page_texts = []
    for img_bytes in images:
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
        finally:
            os.unlink(img_path)

    return {
        "text": "\n\n".join(page_texts),
        "pages": len(images),
        "language_detected": language if language != "auto" else "auto-detected",
    }


@app.function(image=modal_image, timeout=600)
@fastapi_endpoint(method="POST")
def web_ocr(body: dict) -> dict:
    """
    Web endpoint for FastAPI to call.
    Accepts JSON: {"pdf_data": "base64...", "language": "auto"}
    Returns:      {"text": "...", "pages": N, "language_detected": "..."}
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
        result = ocr_pdf.remote(pdf_bytes, language=language)
        return result
    except Exception as e:
        return {"error": f"OCR failed: {e}\n{traceback.format_exc()}"}
