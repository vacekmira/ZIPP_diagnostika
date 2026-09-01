from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from reportlab.lib.pagesizes import A0, A1, A2, A3, A4, landscape


PageSize = Literal["A4", "A3", "A2", "A1", "A0"]
Orientation = Literal["landscape", "portrait"]
FontSize = Literal["auto", "7", "9", "10", "12", "14"]
FontSizeQuery = Literal[
    "auto", "7", "9", "10", "12", "14",
    "small", "normal", "larger", "large",
]

PAPER_SIZES = {"A4": A4, "A3": A3, "A2": A2, "A1": A1, "A0": A0}
PAPER_ORDER = tuple(PAPER_SIZES)
ORIENTATIONS = ("landscape", "portrait")
FONT_SIZES = (7, 9, 10, 12, 14)
AUTO_FONT_SIZES = (12, 10, 9, 7)
FONT_ALIASES = {
    # Backward-compatible API values from Alpha 4-6.
    "small": "7",
    "normal": "10",
    "larger": "12",
    "large": "14",
}


@dataclass(frozen=True)
class ExportOptions:
    """One validated export contract shared by project and bay PDFs."""

    page_size: str = "A3"
    orientation: str = "landscape"
    font_size: str = "auto"

    def __post_init__(self) -> None:
        paper = str(self.page_size).upper()
        orientation = str(self.orientation).lower()
        font = FONT_ALIASES.get(str(self.font_size).lower(), str(self.font_size).lower())
        if paper not in PAPER_SIZES:
            raise ValueError(f"Unsupported paper size: {self.page_size}")
        if orientation not in ORIENTATIONS:
            raise ValueError(f"Unsupported orientation: {self.orientation}")
        if font != "auto" and (not font.isdigit() or int(font) not in FONT_SIZES):
            raise ValueError(f"Unsupported font size: {self.font_size}")
        object.__setattr__(self, "page_size", paper)
        object.__setattr__(self, "orientation", orientation)
        object.__setattr__(self, "font_size", font)

    @property
    def page_dimensions(self) -> tuple[float, float]:
        portrait_size = PAPER_SIZES[self.page_size]
        return landscape(portrait_size) if self.orientation == "landscape" else portrait_size

    @property
    def requested_font_size(self) -> int | None:
        return None if self.font_size == "auto" else int(self.font_size)

