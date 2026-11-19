"""Plugin registry; operation keys are an explicit allowlist, never user imports."""

from app.domain.operations import Operation
from app.processors.pdf.basic import (
    CompressPDF,
    ExtractPages,
    ExtractText,
    InspectDocument,
    MergePDF,
    RenderPDF,
    RotatePDF,
    WatermarkPDF,
)
from app.processors.pdf.external import OCRPDF, LibreOfficeToPDF
from app.processors.pdf.images import ImageToPDF

OPERATIONS: dict[str, Operation] = {
    op.name: op
    for op in (
        InspectDocument(),
        CompressPDF(),
        ExtractText(),
        ExtractPages(),
        MergePDF(),
        RenderPDF(),
        RotatePDF(),
        WatermarkPDF(),
        OCRPDF(),
        LibreOfficeToPDF(),
        ImageToPDF(),
    )
}


def get_operation(name: str) -> Operation:
    try:
        return OPERATIONS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown operation: {name}") from exc
