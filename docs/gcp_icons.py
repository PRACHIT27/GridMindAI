"""Embed official Google Cloud product icons into a single SVG document.

The icons ship from cloud.google.com/icons as standalone 24x24 SVGs that style
themselves with an internal stylesheet:

    <style>.cls-1{fill:#aecbfa;}.cls-2{fill:#4285f4;}</style>
    <polygon class="cls-1" .../>

Inlining several of those into ONE document silently breaks them. CSS class
names are global to the document, so every icon's `.cls-1` collides and the
last definition wins -- nine icons all render in whichever palette happened to
be declared last, which looks like a colour-scheme choice rather than a bug.

So each icon is flattened first: the stylesheet is parsed, its declarations are
written onto the elements as presentation attributes, and the <style> block is
dropped. Nothing then depends on document-wide state.

Icons are emitted as <symbol> definitions and drawn with <use>, so the same
icon appearing eight times costs one copy of its geometry.
"""
from __future__ import annotations

import re
from pathlib import Path

ICON_DIR = Path(__file__).resolve().parent / "icons"

# Files present in docs/icons -> the id used in the diagram.
ICONS: dict[str, str] = {
    "cloud_run": "cloud-run",
    "firestore": "firestore",
    "vertexai": "vertex-ai",
    "virtual_private_cloud": "vpc",
    "cloud_logging": "logging",
    "cloud_nat": "nat",
    "cloud_armor": "armor",
    "identity_and_access_management": "iam",
    "artifact_registry": "registry",
}


def _parse_style(css: str) -> dict[str, dict[str, str]]:
    """class name -> {property: value}, honouring multi-selector rules."""
    out: dict[str, dict[str, str]] = {}
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        decls = {}
        for decl in body.split(";"):
            if ":" in decl:
                k, v = decl.split(":", 1)
                decls[k.strip()] = v.strip()
        for sel in selectors.split(","):
            sel = sel.strip().lstrip(".")
            if sel:
                # A later rule for the same class overrides an earlier one,
                # which is what the browser would have done.
                out.setdefault(sel, {}).update(decls)
    return out


def _flatten(svg: str) -> str:
    """Inline the stylesheet onto elements and return the icon's inner markup."""
    style_blocks = re.findall(r"<style[^>]*>(.*?)</style>", svg, re.S)
    rules: dict[str, dict[str, str]] = {}
    for block in style_blocks:
        for cls, decls in _parse_style(block).items():
            rules.setdefault(cls, {}).update(decls)

    svg = re.sub(r"<style[^>]*>.*?</style>", "", svg, flags=re.S)
    svg = re.sub(r"<title>.*?</title>", "", svg, flags=re.S)

    def sub_class(m: re.Match) -> str:
        names = m.group(1).split()
        attrs: dict[str, str] = {}
        for n in names:
            attrs.update(rules.get(n, {}))
        if not attrs:
            return ""
        return " ".join(f'{k}="{v}"' for k, v in attrs.items())

    svg = re.sub(r'class="([^"]*)"', sub_class, svg)

    # Some icons (vertexai) never use classes at all -- they carry
    # style="fill:#669df6" inline. Those are safe as-is, but presentation
    # attributes survive SVG->PDF and SVG->PNG conversion more reliably than
    # inline CSS, so normalise them to the same form as everything else.
    def style_to_attrs(m: re.Match) -> str:
        decls = [d for d in m.group(1).split(";") if ":" in d]
        parts = []
        for d in decls:
            k, v = d.split(":", 1)
            parts.append(f'{k.strip()}="{v.strip()}"')
        return " ".join(parts)

    svg = re.sub(r'style="([^"]*)"', style_to_attrs, svg)

    # Keep only what is inside the root <svg> element.
    inner = re.sub(r"^.*?<svg[^>]*>", "", svg, flags=re.S)
    inner = re.sub(r"</svg>\s*$", "", inner, flags=re.S)
    # <defs> is now empty in every one of these files; drop it.
    inner = re.sub(r"<defs>\s*</defs>", "", inner)
    return inner.strip()


def symbols() -> str:
    """All available icons as <symbol> defs, ready to drop inside <defs>."""
    out: list[str] = []
    for fname, sid in ICONS.items():
        path = ICON_DIR / f"{fname}.svg"
        if not path.exists():
            continue
        out.append(f'<symbol id="ic-{sid}" viewBox="0 0 24 24">'
                   f'{_flatten(path.read_text(encoding="utf-8"))}</symbol>')
    return "".join(out)


def available() -> set[str]:
    return {sid for f, sid in ICONS.items() if (ICON_DIR / f"{f}.svg").exists()}


def use(sid: str, x: float, y: float, size: float = 22) -> str:
    """Draw an icon. Silently no-ops for a missing id so the diagram still builds."""
    if sid not in available():
        return ""
    return f'<use href="#ic-{sid}" x="{x}" y="{y}" width="{size}" height="{size}"/>'


if __name__ == "__main__":
    got = available()
    print(f"{len(got)} icons available: {', '.join(sorted(got))}")
    for sid in sorted(got):
        body = symbols()
        print(f"  ic-{sid}: ok")
    # Sanity: no class attributes should survive flattening.
    assert 'class="' not in symbols(), "a stylesheet class survived flattening"
    print("no residual class attributes — icons will not collide")
