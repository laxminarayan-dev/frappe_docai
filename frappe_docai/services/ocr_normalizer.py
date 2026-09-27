"""Normalize raw Google Vision OCR output into a document model."""

from __future__ import annotations

from typing import Any


def _to_bbox(vertices):
    if not vertices:
        return {"left": 0, "top": 0, "right": 0, "bottom": 0, "width": 0, "height": 0}

    xs = [float(vertex.get("x", 0)) for vertex in vertices]
    ys = [float(vertex.get("y", 0)) for vertex in vertices]
    left = min(xs)
    top = min(ys)
    right = max(xs)
    bottom = max(ys)
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": max(right - left, 0),
        "height": max(bottom - top, 0),
    }


def normalize_vision_response(response: dict[str, Any]) -> dict[str, Any]:
    """Normalize Vision response into a document structure that preserves OCR spatial metadata."""
    responses = response.get("responses") if isinstance(response, dict) else []
    if not responses:
        return {"pages": [], "raw_text": "", "spatial": {}}

    pages: list[dict[str, Any]] = []
    text_parts: list[str] = []

    for response_item in responses:
        annotation = response_item.get("fullTextAnnotation") or {}
        text_parts.append(annotation.get("text") or "")
        for page in annotation.get("pages") or []:
            words: list[dict[str, Any]] = []
            blocks: list[dict[str, Any]] = []
            paragraphs: list[dict[str, Any]] = []
            symbols: list[dict[str, Any]] = []

            for block in page.get("blocks") or []:
                block_data = {
                    "block_index": len(blocks),
                    "boundingBox": _to_bbox((block.get("boundingBox") or {}).get("vertices") or []),
                    "paragraphs": [],
                }
                for paragraph in block.get("paragraphs") or []:
                    paragraph_data = {
                        "paragraph_index": len(block_data["paragraphs"]),
                        "boundingBox": _to_bbox((paragraph.get("boundingBox") or {}).get("vertices") or []),
                        "words": [],
                    }
                    for word in paragraph.get("words") or []:
                        word_text = word.get("text") or ""
                        vertices = (word.get("boundingBox") or {}).get("vertices") or []
                        word_norm = {
                            "text": word_text,
                            "confidence": word.get("confidence"),
                            "page_index": len(pages),
                            "bbox": _to_bbox(vertices),
                            "vertices": vertices,
                            "x_center": sum(v.get("x", 0) for v in vertices) / len(vertices) if vertices else 0,
                            "y_center": sum(v.get("y", 0) for v in vertices) / len(vertices) if vertices else 0,
                        }
                        words.append(word_norm)
                        paragraph_data["words"].append(word_norm)
                        for symbol in word.get("symbols") or []:
                            symbol_norm = {
                                "text": symbol.get("text") or "",
                                "confidence": symbol.get("confidence"),
                                "bbox": _to_bbox((symbol.get("boundingBox") or {}).get("vertices") or []),
                                "vertices": (symbol.get("boundingBox") or {}).get("vertices") or [],
                            }
                            symbols.append(symbol_norm)
                    paragraph_data["words"] = paragraph_data["words"]
                    paragraphs.append(paragraph_data)
                    block_data["paragraphs"].append(paragraph_data)
                blocks.append(block_data)

            normalized_page = {
                "page_index": len(pages),
                "width": page.get("width"),
                "height": page.get("height"),
                "blocks": blocks,
                "paragraphs": paragraphs,
                "words": words,
                "symbols": symbols,
            }
            pages.append(normalized_page)

    normalized = {
        "pages": pages,
        "raw_text": "\n".join(part for part in text_parts if part),
        "spatial": {
            "has_bbox": True,
            "page_count": len(pages),
        },
    }
    return normalized
