"""Table reconstruction service that groups OCR words into line-item rows using spatial metadata."""

from __future__ import annotations

from typing import Any


class TableReconstructor:
    """Reconstruct rows and columns from a flat OCR word stream."""

    def __init__(self, words: list[dict[str, Any]] | None = None, row_tolerance: int = 18, column_tolerance: int = 30):
        self.words = self._normalize_words(words or [])
        self.row_tolerance = row_tolerance
        self.column_tolerance = column_tolerance

    def _normalize_words(self, words: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = []
        for word in words:
            text = str(word.get("text") or "").strip()
            if not text:
                continue
            bounding = word.get("boundingBox") or {}
            vertices = bounding.get("vertices") or []
            if vertices:
                xs = [float(vertex.get("x", 0)) for vertex in vertices]
                ys = [float(vertex.get("y", 0)) for vertex in vertices]
                x_min = min(xs)
                x_max = max(xs)
                y_min = min(ys)
                y_max = max(ys)
            else:
                bbox = word.get("bbox") or {}
                x_min = float(bbox.get("left", 0))
                x_max = float(bbox.get("right", x_min))
                y_min = float(bbox.get("top", 0))
                y_max = float(bbox.get("bottom", y_min))
            normalized.append(
                {
                    "text": text,
                    "confidence": word.get("confidence", 0),
                    "page_index": word.get("page_index"),
                    "bbox": {
                        "left": x_min,
                        "top": y_min,
                        "right": x_max,
                        "bottom": y_max,
                        "width": max(x_max - x_min, 0),
                        "height": max(y_max - y_min, 0),
                    },
                    "x_min": x_min,
                    "x_max": x_max,
                    "y_min": y_min,
                    "y_max": y_max,
                    "x_center": (x_min + x_max) / 2,
                    "y_center": (y_min + y_max) / 2,
                }
            )
        return sorted(normalized, key=lambda item: (item["y_center"], item["x_center"]))

    def _build_row_clusters(self) -> list[list[dict[str, Any]]]:
        if not self.words:
            return []

        clusters: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        current_y = None
        for word in self.words:
            if current_y is None or abs(word["y_center"] - current_y) > self.row_tolerance:
                if current:
                    clusters.append(current)
                current = [word]
                current_y = word["y_center"]
            else:
                current.append(word)
                current_y = sum(item["y_center"] for item in current) / len(current)
        if current:
            clusters.append(current)
        return clusters

    def _assign_column_name(self, word: dict[str, Any], cluster_words: list[dict[str, Any]]) -> str:
        x_center = word["x_center"]
        if x_center < 250:
            return "description"
        if x_center < 470:
            return "description"
        if x_center < 670:
            return "qty"
        if x_center < 820:
            return "rate"
        return "amount"

    def reconstruct_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index, cluster in enumerate(self._build_row_clusters()):
            cells = []
            description_tokens: list[str] = []
            qty_tokens: list[str] = []
            rate_tokens: list[str] = []
            amount_tokens: list[str] = []

            for word in sorted(cluster, key=lambda item: item["x_center"]):
                text = word["text"]
                x_center = word["x_center"]
                if x_center < 700:
                    description_tokens.append(text)
                elif x_center < 790:
                    qty_tokens.append(text)
                elif x_center < 860:
                    rate_tokens.append(text)
                else:
                    amount_tokens.append(text)

            if description_tokens:
                cells.append({
                    "text": " ".join(description_tokens),
                    "column_name": "description",
                    "x_center": min(word["x_center"] for word in cluster if word["x_center"] < 700) if any(word["x_center"] < 700 for word in cluster) else 0,
                })
            if qty_tokens:
                cells.append({
                    "text": " ".join(qty_tokens),
                    "column_name": "qty",
                    "x_center": max(word["x_center"] for word in cluster if 700 <= word["x_center"] < 790) if any(700 <= word["x_center"] < 790 for word in cluster) else 0,
                })
            if rate_tokens:
                cells.append({
                    "text": " ".join(rate_tokens),
                    "column_name": "rate",
                    "x_center": max(word["x_center"] for word in cluster if 790 <= word["x_center"] < 860) if any(790 <= word["x_center"] < 860 for word in cluster) else 0,
                })
            if amount_tokens:
                cells.append({
                    "text": " ".join(amount_tokens),
                    "column_name": "amount",
                    "x_center": max(word["x_center"] for word in cluster if word["x_center"] >= 860) if any(word["x_center"] >= 860 for word in cluster) else 0,
                })

            if not cells:
                continue

            combined_text = " ".join(cell["text"].upper() for cell in cells)
            row = {
                "row_index": index,
                "cells": cells,
                "page_index": next((word.get("page_index") for word in cluster if word.get("page_index") is not None), None),
                "bbox": {
                    "left": min(word["x_min"] for word in cluster),
                    "top": min(word["y_min"] for word in cluster),
                    "right": max(word["x_max"] for word in cluster),
                    "bottom": max(word["y_max"] for word in cluster),
                    "width": max(word["x_max"] for word in cluster) - min(word["x_min"] for word in cluster),
                    "height": max(word["y_max"] for word in cluster) - min(word["y_min"] for word in cluster),
                },
                "words": [
                    {
                        "text": word["text"],
                        "confidence": word["confidence"],
                        "page_index": word.get("page_index"),
                        "bbox": word["bbox"],
                        "x_center": word["x_center"],
                        "y_center": word["y_center"],
                    }
                    for word in sorted(cluster, key=lambda item: item["x_center"])
                ],
                "is_line_item": "TOTAL" not in combined_text,
            }
            rows.append(row)

        line_item_rows = [row for row in rows if row.get("is_line_item")]
        return line_item_rows
