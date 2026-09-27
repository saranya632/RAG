"""Builds small, valid text PDFs in memory, so tests need no extra dependency."""


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[list[str]]) -> bytes:
    """Return PDF bytes; `pages` is a list of pages, each a list of text lines."""
    n = len(pages)
    font_id = 3 + 2 * n
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        (
            "<< /Type /Pages /Kids ["
            + " ".join(f"{3 + 2 * i} 0 R" for i in range(n))
            + f"] /Count {n} >>"
        ).encode(),
    ]
    for i, lines in enumerate(pages):
        content_id = 4 + 2 * i
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode()
        )
        ops = ["BT", "/F1 11 Tf", "14 TL", "50 750 Td"]
        for line in lines:
            ops.append(f"({_escape(line)}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(out)


def make_sample_pdf(page_count: int = 3, lines_per_page: int = 40) -> bytes:
    pages = [
        [
            f"Page {p} line {l}: enterprise retrieval augmented generation sample text."
            for l in range(1, lines_per_page + 1)
        ]
        for p in range(1, page_count + 1)
    ]
    return make_pdf(pages)
