"""Output methods shared by ``Chart`` and ``Grid``: SVG, PDF, PNG, HTML, notebooks."""

from __future__ import annotations

import os
from typing import Optional


class Renderable:
    """Mixin: anything with ``build(raster_scale) -> Scene`` gets every output format."""

    def build(self, raster_scale: float = 2.0):  # pragma: no cover - implemented by subclasses
        raise NotImplementedError

    def to_svg(self) -> str:
        from .backends import svg
        return svg.render(self.build())

    def to_pdf(self) -> bytes:
        from .backends import pdf
        return pdf.render(self.build())

    def to_png(self, scale: Optional[float] = None, dpi: Optional[float] = None) -> bytes:
        from .backends import png
        s = scale if scale is not None else (dpi / 96 if dpi else 2.0)
        return png.render(self.build(raster_scale=max(1.0, s)), s)

    def to_html(self, *, title: Optional[str] = None) -> str:
        """Standalone HTML page: styled hover tooltips, wheel/drag zoom, double-click to reset."""
        from .backends import html
        return html.render(self.to_svg(), title=title or getattr(self, "_page_title", None))

    def save(self, path: "str | os.PathLike", *, dpi: Optional[float] = None, scale: Optional[float] = None,
             format: Optional[str] = None) -> str:
        """Save to .svg, .pdf, .png or .html (format from the extension). Returns the path.

        PNG defaults to 2x resolution (192 dpi). ``dpi=300`` for print.
        """
        path = os.fspath(path)
        fmt = (format or os.path.splitext(path)[1].lstrip(".") or "svg").lower()
        if fmt == "svg":
            data = self.to_svg().encode("utf-8")
        elif fmt == "pdf":
            data = self.to_pdf()
        elif fmt == "png":
            data = self.to_png(scale=scale, dpi=dpi)
        elif fmt in ("html", "htm"):
            data = self.to_html().encode("utf-8")
        else:
            raise ValueError(f"Unsupported format {fmt!r}. Use .svg, .png, .pdf or .html.")
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def show(self) -> None:
        """Display in a notebook, or open an interactive page in the default browser."""
        try:
            from IPython import get_ipython
            from IPython.display import SVG, display
            if get_ipython() is not None:
                display(SVG(self.to_svg()))
                return
        except ImportError:
            pass
        import tempfile
        import webbrowser
        fd, path = tempfile.mkstemp(suffix=".html", prefix="lineova-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(self.to_html())
        webbrowser.open("file://" + path)

    def _repr_svg_(self) -> str:
        return self.to_svg()
