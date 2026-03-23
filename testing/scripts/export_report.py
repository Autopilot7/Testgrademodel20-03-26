"""Usage: python scripts/export_report.py
Converts report/report.md to a self-contained HTML file with
embedded images (base64) and print-ready CSS.
Output: report/report.html

Optional PDF export via weasyprint (if installed):
  pip install weasyprint
  python scripts/export_report.py --pdf
"""

from __future__ import annotations

import argparse
import base64
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
REPORT_MD = ROOT_DIR / "report" / "report.md"
REPORT_HTML = ROOT_DIR / "report" / "report.html"
REPORT_PDF = ROOT_DIR / "report" / "report.pdf"

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: 'Inter', 'Segoe UI', sans-serif;
  font-size: 14px;
  line-height: 1.7;
  color: #1a1a2e;
  background: #ffffff;
  max-width: 960px;
  margin: 0 auto;
  padding: 48px 48px 80px;
}

h1 {
  font-size: 2em;
  font-weight: 700;
  color: #0d1b2a;
  border-bottom: 3px solid #2563eb;
  padding-bottom: 12px;
  margin: 0 0 20px;
}

h2 {
  font-size: 1.35em;
  font-weight: 700;
  color: #1e3a5f;
  border-bottom: 1px solid #dbeafe;
  padding-bottom: 6px;
  margin: 40px 0 16px;
  page-break-after: avoid;
}

h3 {
  font-size: 1.1em;
  font-weight: 600;
  color: #1e40af;
  margin: 28px 0 10px;
  page-break-after: avoid;
}

h4 {
  font-size: 1em;
  font-weight: 600;
  color: #374151;
  margin: 20px 0 8px;
}

p { margin: 10px 0; }

a { color: #2563eb; }

strong { font-weight: 600; color: #0d1b2a; }

em { font-style: italic; }

hr {
  border: none;
  border-top: 1px solid #e5e7eb;
  margin: 36px 0;
}

/* Tables */
table {
  width: 100%;
  border-collapse: collapse;
  margin: 16px 0;
  font-size: 13px;
  page-break-inside: avoid;
}

thead tr {
  background: #1e3a5f;
  color: #ffffff;
}

thead th {
  padding: 10px 14px;
  text-align: left;
  font-weight: 600;
  letter-spacing: 0.02em;
}

tbody tr:nth-child(even) { background: #f0f4ff; }
tbody tr:nth-child(odd)  { background: #ffffff; }

tbody td {
  padding: 8px 14px;
  border-bottom: 1px solid #e5e7eb;
  vertical-align: top;
}

/* Code blocks */
pre {
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 8px;
  padding: 20px 24px;
  overflow-x: auto;
  margin: 16px 0;
  font-size: 12.5px;
  line-height: 1.6;
  page-break-inside: avoid;
}

code {
  font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
}

p code, li code, td code {
  background: #eff6ff;
  color: #1d4ed8;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12.5px;
}

/* Lists */
ul, ol {
  margin: 10px 0 10px 24px;
}
li { margin: 4px 0; }

/* Blockquotes */
blockquote {
  border-left: 4px solid #2563eb;
  background: #eff6ff;
  padding: 12px 20px;
  margin: 16px 0;
  border-radius: 0 6px 6px 0;
  color: #1e40af;
}

/* Images */
img {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 20px auto;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.08);
  page-break-inside: avoid;
}

/* Print / PDF styles */
@media print {
  body { max-width: 100%; padding: 20px 30px; font-size: 12px; }
  h1 { font-size: 1.6em; }
  h2 { font-size: 1.2em; margin-top: 28px; }
  h3 { font-size: 1em; }
  pre { font-size: 11px; padding: 14px; }
  table { font-size: 11px; }
  img { max-width: 88%; }
  h2, h3 { page-break-after: avoid; }
  pre, table, img { page-break-inside: avoid; }
}

/* Header meta block */
.meta-block {
  background: #f0f4ff;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  padding: 16px 20px;
  margin: 0 0 32px;
  font-size: 13px;
  color: #374151;
}
.meta-block p { margin: 3px 0; }
"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>{css}</style>
</head>
<body>
{body}
</body>
</html>"""


def embed_images(html: str, base_dir: Path) -> str:
    """Replace <img src="..."> with base64-embedded data URIs."""
    def replacer(m: re.Match) -> str:
        src = m.group(1)
        if src.startswith("data:") or src.startswith("http"):
            return m.group(0)
        img_path = (base_dir / src).resolve()
        if not img_path.exists():
            print(f"  WARNING: image not found: {img_path}", file=sys.stderr)
            return m.group(0)
        ext = img_path.suffix.lower().lstrip(".")
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png",
                "gif": "gif", "svg": "svg+xml"}.get(ext, "png")
        data = base64.b64encode(img_path.read_bytes()).decode()
        return f'<img src="data:image/{mime};base64,{data}"'

    return re.sub(r'<img src="([^"]+)"', replacer, html)


def md_to_html(md_text: str) -> str:
    try:
        import markdown
        extensions = ["tables", "fenced_code", "codehilite",
                      "toc", "nl2br", "attr_list"]
        md = markdown.Markdown(extensions=extensions,
                               extension_configs={
                                   "codehilite": {"guess_lang": False}
                               })
        return md.convert(md_text)
    except ImportError:
        print("  markdown package not found, using fallback converter.", file=sys.stderr)
        return _fallback_md_to_html(md_text)


def _fallback_md_to_html(md_text: str) -> str:
    """Minimal markdown converter when 'markdown' package is unavailable."""
    import html as html_mod
    lines = md_text.split("\n")
    out: list[str] = []
    in_code = False
    in_table = False

    def flush_table():
        nonlocal in_table
        if in_table:
            out.append("</tbody></table>")
            in_table = False

    for line in lines:
        # Fenced code blocks
        if line.startswith("```"):
            if not in_code:
                lang = line[3:].strip()
                out.append(f'<pre><code class="language-{lang}">')
                in_code = True
            else:
                out.append("</code></pre>")
                in_code = False
            continue
        if in_code:
            out.append(html_mod.escape(line))
            continue

        # Tables
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not in_table:
                out.append('<table><thead><tr>')
                out.extend(f"<th>{html_mod.escape(c)}</th>" for c in cells)
                out.append("</tr></thead><tbody>")
                in_table = True
            elif all(set(c) <= {"-", ":"} for c in cells if c):
                pass  # separator row
            else:
                out.append("<tr>")
                out.extend(f"<td>{html_mod.escape(c)}</td>" for c in cells)
                out.append("</tr>")
            continue
        else:
            flush_table()

        # Headings
        if line.startswith("######"):
            out.append(f"<h6>{html_mod.escape(line[6:].strip())}</h6>")
        elif line.startswith("#####"):
            out.append(f"<h5>{html_mod.escape(line[5:].strip())}</h5>")
        elif line.startswith("####"):
            out.append(f"<h4>{html_mod.escape(line[4:].strip())}</h4>")
        elif line.startswith("###"):
            out.append(f"<h3>{html_mod.escape(line[3:].strip())}</h3>")
        elif line.startswith("##"):
            out.append(f"<h2>{html_mod.escape(line[2:].strip())}</h2>")
        elif line.startswith("#"):
            out.append(f"<h1>{html_mod.escape(line[1:].strip())}</h1>")
        elif line.startswith("---"):
            out.append("<hr>")
        elif line.startswith("> "):
            out.append(f"<blockquote><p>{html_mod.escape(line[2:])}</p></blockquote>")
        elif line.startswith("- ") or line.startswith("* "):
            out.append(f"<ul><li>{html_mod.escape(line[2:])}</li></ul>")
        elif line.strip() == "":
            out.append("<br>")
        else:
            # Inline: bold, italic, code, images, links
            text = html_mod.escape(line)
            text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
            text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
            text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
            text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r'<img alt="\1" src="\2">', text)
            text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
            out.append(f"<p>{text}</p>")

    flush_table()
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export report.md to HTML (and optionally PDF).")
    parser.add_argument("--pdf", action="store_true", help="Also generate PDF via weasyprint.")
    parser.add_argument("--input", type=Path, default=REPORT_MD)
    parser.add_argument("--output-html", type=Path, default=REPORT_HTML)
    parser.add_argument("--output-pdf", type=Path, default=REPORT_PDF)
    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: {args.input} not found.", file=sys.stderr)
        return 1

    print(f"Reading {args.input}...")
    md_text = args.input.read_text(encoding="utf-8")

    print("Converting Markdown to HTML...")
    body_html = md_to_html(md_text)

    print("Embedding images...")
    body_html = embed_images(body_html, base_dir=args.input.parent)

    title = "Vietnamese Phoneme / Alignment Pipeline Benchmark Report"
    html_content = HTML_TEMPLATE.format(title=title, css=CSS, body=body_html)

    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    args.output_html.write_text(html_content, encoding="utf-8")
    print(f"HTML saved to: {args.output_html}")

    if args.pdf:
        try:
            from weasyprint import HTML as WeasyprintHTML
            print("Generating PDF with weasyprint...")
            WeasyprintHTML(filename=str(args.output_html)).write_pdf(str(args.output_pdf))
            print(f"PDF saved to: {args.output_pdf}")
        except ImportError:
            print("\nweasyprint not installed. Install it with:", file=sys.stderr)
            print("  pip install weasyprint", file=sys.stderr)
            print("\nAlternatively, open the HTML file in Edge or Chrome", file=sys.stderr)
            print("and use Ctrl+P → Save as PDF.", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
