"""Build the font subsets bundled for the native PNG writer.

    python tools/make_fonts.py PATH/TO/liberation-fonts-ttf-2.1.5

The bundled faces are Liberation Sans, Serif and Mono, which are metric-compatible with the Helvetica, Times
and Courier widths that the layout code uses, so text drawn by the native writer lines up with the layout.
Each face is cut down to Basic Latin, Latin-1 and the symbols the charts use, renamed (the SIL Open Font
License reserves the name "Liberation" for unmodified fonts), and gzip-compressed. Needs ``fonttools``.
"""

from __future__ import annotations

import gzip
import io
import shutil
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

OUT = Path(__file__).resolve().parent.parent / "src" / "lineova" / "backends" / "fonts"
FACES = {
    "LiberationSans-Regular": "Lineova Sans", "LiberationSans-Bold": "Lineova Sans", "LiberationSans-Italic": "Lineova Sans",
    "LiberationSerif-Regular": "Lineova Serif", "LiberationSerif-Bold": "Lineova Serif", "LiberationSerif-Italic": "Lineova Serif",
    "LiberationMono-Regular": "Lineova Mono", "LiberationMono-Bold": "Lineova Mono",
}
UNICODES = (list(range(0x20, 0x7F)) + list(range(0xA0, 0x100)) +
            [0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2026, 0x2030, 0x2190, 0x2191, 0x2192, 0x2193,
             0x2212, 0x2264, 0x2265, 0x20AC, 0x2248, 0x00D7, 0x0394, 0x03BC, 0x25B2, 0x25BC])


def rename(font: TTFont, family: str, style: str) -> None:
    name = font["name"]
    for rec in list(name.names):
        if rec.nameID in (1, 2, 3, 4, 6, 16, 17, 21, 22):
            name.removeNames(nameID=rec.nameID)
    full = f"{family} {style}".replace(" Regular", "")
    for pid, eid, lid in ((3, 1, 0x409), (1, 0, 0)):
        name.setName(family, 1, pid, eid, lid)
        name.setName(style, 2, pid, eid, lid)
        name.setName(f"{family} {style} (subset of Liberation, SIL OFL 1.1)", 3, pid, eid, lid)
        name.setName(full, 4, pid, eid, lid)
        name.setName((family + "-" + style).replace(" ", ""), 6, pid, eid, lid)


def main(src: Path) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for stem, family in FACES.items():
        opts = subset.Options()
        opts.layout_features = ["kern"]
        opts.hinting = False
        opts.desubroutinize = True
        opts.name_IDs = ["*"]
        opts.notdef_outline = True
        opts.drop_tables += ["DSIG", "GDEF", "GPOS", "GSUB", "kern", "gasp", "FFTM", "meta", "hdmx", "VDMX", "LTSH"]
        font = TTFont(src / f"{stem}.ttf")
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=UNICODES)
        sub.subset(font)
        rename(font, family, stem.split("-")[1])
        buf = io.BytesIO()
        font.save(buf)
        target = OUT / f"{stem.replace('Liberation', 'Lineova')}.ttf.gz"
        target.write_bytes(gzip.compress(buf.getvalue(), 9, mtime=0))
        print(f"{target.name}: {target.stat().st_size / 1000:.1f} kB")
    shutil.copy(src / "LICENSE", OUT / "LICENSE-Liberation-OFL.txt")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
