"""Constrained child process. No application/database configuration is loaded."""
import csv
import json
import resource
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def extract(source, media_type, limits, timezone):
    warnings, pages, candidates = [], [], []
    if media_type == "text/csv":
        with source.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        if len(rows) > 500:
            raise ValueError("CSV row limit")
        from ...api.schemas import TransactionRequest
        for i, r in enumerate(rows):
            data = {k: v for k, v in r.items() if v not in {"", None}}
            try:
                # CSV dates still require an explicit offset. Ambiguous data remains
                # in the proposal; the owner must supply a reviewed timestamp.
                record = TransactionRequest(**data)
                candidates.append({"row_index": i, "transaction": record.model_dump(mode="json"), "confidence": 1,
                                   "source": {"row": i+2}, "errors": []})
            except (ValueError, TypeError):
                candidates.append({"row_index": i, "recognized": data, "confidence": 0,
                                   "source": {"row": i+2}, "errors": ["Invalid or ambiguous transaction; review fields before confirming"]})
    else:
        from PIL import Image
        import pytesseract
        Image.MAX_IMAGE_PIXELS = limits["image_pixels"]
        def ocr(path, page):
            with Image.open(path) as image:
                if image.width*image.height > limits["image_pixels"]:
                    raise ValueError("Image pixel limit")
                image.load()
                recognized = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT,
                                                      timeout=min(60, limits["task_timeout_seconds"]))
                words = [{"text": text, "confidence": max(0, float(recognized["conf"][i]))/100,
                          "box": [recognized[k][i] for k in ["left", "top", "width", "height"]]}
                         for i, text in enumerate(recognized["text"]) if text.strip()]
                return {"page": page, "text": " ".join(w["text"] for w in words), "words": words}
        if media_type in {"image/jpeg", "image/png"}:
            pages.append(ocr(source, 1))
        elif media_type == "application/pdf":
            from pypdf import PdfReader
            reader = PdfReader(source, strict=True)
            if reader.is_encrypted or len(reader.pages) > limits["pdf_pages"]:
                raise ValueError("Encrypted PDF or page limit")
            for i, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append({"page": i, "text": text[:200000], "confidence": None})
                else:
                    image = source.parent/f"ocr-page-{i}"
                    subprocess.run(["pdftoppm", "-f", str(i), "-l", str(i), "-scale-to", "2000", "-singlefile", "-png",
                                    str(source), str(image)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
                    pages.append(ocr(image.with_suffix(".png"), i))
                    image.with_suffix(".png").unlink(missing_ok=True)
        warnings.append("OCR/PDF text is evidence for manual review, not verified transactions. Use reviewed rows or the documented CSV schema to confirm.")
        pattern = re.compile(r"\b(BUY|BOUGHT|SELL|SOLD)\s+([A-Z][A-Z0-9.\-]{0,14})\s+(\d+(?:[.,]\d+)?)\s+(?:SHARES?\s+)?(?:AT|@)\s+\$?(\d+(?:[.,]\d+)?)\s*(USD)?", re.I)
        for page in pages:
            for match in pattern.finditer(page["text"]):
                action, symbol, quantity, price, currency = match.groups()
                errors = ["Transaction timestamp and account context require user review"]
                if "," in quantity or "," in price:
                    errors.append("Ambiguous numeric separator; do not infer decimal or thousands format")
                if not currency:
                    errors.append("Currency was not established")
                candidates.append({"row_index": len(candidates), "recognized": {"type": "buy" if action.lower() in {"buy","bought"} else "sell",
                                   "symbol": symbol.upper(), "quantity": quantity, "price": price, "currency": currency},
                                   "confidence": None, "source": {"page": page["page"], "text_span": list(match.span())}, "errors": errors})
    return {"version": 1, "pages": pages, "rows": candidates, "warnings": warnings,
            "timestamp_policy": "Reviewed transactions require explicit timezones", "suggested_timezone": timezone,
            "requires_confirmation": True}


if __name__ == "__main__":
    source, media_type, destination = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    limits = json.loads(sys.argv[4])
    resource.setrlimit(resource.RLIMIT_CPU, (limits["task_timeout_seconds"], limits["task_timeout_seconds"]+5))
    resource.setrlimit(resource.RLIMIT_AS, (2_000_000_000, 2_000_000_000))
    resource.setrlimit(resource.RLIMIT_FSIZE, (max(limits["task_output_bytes"], limits["upload_bytes"]),)*2)
    result = extract(source, media_type, limits, sys.argv[5])
    b = json.dumps(result, allow_nan=False).encode()
    if len(b) > limits["task_output_bytes"]:
        raise ValueError("Extraction output limit")
    destination.write_bytes(b)
    destination.chmod(0o600)
