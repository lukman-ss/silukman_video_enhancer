"""Offline SDK documentation and developer guide generator.

Phase 7, Task 12
SdkDocGenerator inspects Python source files in the pipeline/ package,
extracts module/class/function docstrings, and renders a self-contained
HTML developer reference that plugin authors can use without internet access.
"""

from __future__ import annotations

import ast
import html
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# AST-based docstring extractor
# ---------------------------------------------------------------------------


@dataclass
class FunctionDoc:
    name: str
    docstring: str
    args: List[str] = field(default_factory=list)
    is_async: bool = False


@dataclass
class ClassDoc:
    name: str
    docstring: str
    methods: List[FunctionDoc] = field(default_factory=list)
    bases: List[str] = field(default_factory=list)


@dataclass
class ModuleDoc:
    name: str
    path: str
    docstring: str
    classes: List[ClassDoc] = field(default_factory=list)
    functions: List[FunctionDoc] = field(default_factory=list)


def _get_docstring(node: ast.AST) -> str:
    return ast.get_docstring(node) or ""


def _extract_args(node: ast.FunctionDef | ast.AsyncFunctionDef) -> List[str]:
    args = []
    for arg in node.args.args:
        if arg.arg != "self":
            args.append(arg.arg)
    return args


def extract_module_doc(source: str, name: str, path: str = "") -> ModuleDoc:
    """Parse *source* and return a ``ModuleDoc`` with all classes/functions."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ModuleDoc(name=name, path=path, docstring="[parse error]")

    module_doc = _get_docstring(tree)
    classes: List[ClassDoc] = []
    functions: List[FunctionDoc] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            bases = [
                (b.id if isinstance(b, ast.Name) else ast.unparse(b))
                for b in node.bases
            ]
            methods: List[FunctionDoc] = []
            for item in ast.iter_child_nodes(node):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not item.name.startswith("__") or item.name == "__init__":
                        methods.append(FunctionDoc(
                            name=item.name,
                            docstring=_get_docstring(item),
                            args=_extract_args(item),
                            is_async=isinstance(item, ast.AsyncFunctionDef),
                        ))
            classes.append(ClassDoc(
                name=node.name,
                docstring=_get_docstring(node),
                methods=methods,
                bases=bases,
            ))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                functions.append(FunctionDoc(
                    name=node.name,
                    docstring=_get_docstring(node),
                    args=_extract_args(node),
                    is_async=isinstance(node, ast.AsyncFunctionDef),
                ))

    return ModuleDoc(
        name=name,
        path=path,
        docstring=module_doc,
        classes=classes,
        functions=functions,
    )


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------

_CSS = """
body{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;
     padding:0 1.5rem;line-height:1.6;color:#1a1a2e}
h1{border-bottom:3px solid #4f46e5;padding-bottom:.4rem;color:#4f46e5}
h2{margin-top:2rem;color:#3730a3;border-bottom:1px solid #c7d2fe}
h3{color:#5b21b6;margin-top:1.2rem}
h4{color:#7c3aed;margin:.6rem 0 .2rem}
pre{background:#f1f5f9;padding:.8rem 1rem;border-radius:6px;
    overflow-x:auto;font-size:.85rem}
code{background:#e0e7ff;padding:.1rem .3rem;border-radius:3px;font-size:.85rem}
.module{border:1px solid #c7d2fe;border-radius:8px;padding:1rem 1.5rem;
        margin-bottom:2rem;background:#fafafa}
.class-block{margin-left:1rem;border-left:3px solid #818cf8;
             padding-left:1rem;margin-top:1rem}
.fn{margin-left:1rem;margin-top:.5rem}
.tag{display:inline-block;padding:.1rem .5rem;border-radius:4px;
     font-size:.75rem;font-weight:600;margin-left:.4rem}
.async-tag{background:#fef3c7;color:#92400e}
.toc a{display:block;color:#4f46e5;text-decoration:none;padding:.15rem 0}
.toc a:hover{text-decoration:underline}
"""


def _h(text: str) -> str:
    return html.escape(text)


def _fmt_doc(doc: str) -> str:
    if not doc:
        return ""
    doc = textwrap.dedent(doc).strip()
    return f"<p>{_h(doc)}</p>"


def render_html(modules: List[ModuleDoc], title: str = "Plugin SDK Reference") -> str:
    """Render a list of ``ModuleDoc`` objects to a self-contained HTML string."""
    toc_items: List[str] = []
    module_blocks: List[str] = []

    for mod in modules:
        anchor = f"mod-{mod.name.replace('.', '-')}"
        toc_items.append(f'<a href="#{anchor}">{_h(mod.name)}</a>')

        parts = [f'<div class="module" id="{anchor}">']
        parts.append(f"<h2>{_h(mod.name)}</h2>")
        if mod.path:
            parts.append(f"<p><code>{_h(mod.path)}</code></p>")
        parts.append(_fmt_doc(mod.docstring))

        # Classes
        for cls in mod.classes:
            bases_str = f"({', '.join(_h(b) for b in cls.bases)})" if cls.bases else ""
            parts.append(f'<div class="class-block">')
            parts.append(f"<h3>class {_h(cls.name)}{bases_str}</h3>")
            parts.append(_fmt_doc(cls.docstring))
            for meth in cls.methods:
                async_tag = '<span class="tag async-tag">async</span>' if meth.is_async else ""
                sig = f"{_h(meth.name)}({', '.join(_h(a) for a in meth.args)})"
                parts.append(f'<div class="fn">')
                parts.append(f"<h4><code>{sig}</code>{async_tag}</h4>")
                parts.append(_fmt_doc(meth.docstring))
                parts.append("</div>")
            parts.append("</div>")

        # Module-level functions
        for fn in mod.functions:
            async_tag = '<span class="tag async-tag">async</span>' if fn.is_async else ""
            sig = f"{_h(fn.name)}({', '.join(_h(a) for a in fn.args)})"
            parts.append(f'<div class="fn">')
            parts.append(f"<h3><code>{sig}</code>{async_tag}</h3>")
            parts.append(_fmt_doc(fn.docstring))
            parts.append("</div>")

        parts.append("</div>")
        module_blocks.append("\n".join(parts))

    toc_html = '<div class="toc"><h2>Contents</h2>' + "\n".join(toc_items) + "</div>"
    body = "\n".join(module_blocks)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_h(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>{_h(title)}</h1>
{toc_html}
{body}
</body>
</html>"""


# ---------------------------------------------------------------------------
# SdkDocGenerator — discovers pipeline/ modules and writes HTML
# ---------------------------------------------------------------------------

# Modules relevant to plugin authors
_PLUGIN_MODULES = [
    "plugin_sdk",
    "plugin_sandbox",
    "workflow_profiles",
    "artifact_manifest",
    "config_backup",
    "audit_log",
    "preset_matrix",
    "update_manager",
    "model_verifier",
    "telemetry_collector",
    "db_compactor",
]


class SdkDocGenerator:
    """
    Scans the pipeline package and renders a self-contained HTML reference.

    Usage::

        gen = SdkDocGenerator(pipeline_dir=Path("pipeline"), output_dir=Path("docs/sdk"))
        path = gen.build()
        print(f"HTML written to {path}")
    """

    def __init__(
        self,
        pipeline_dir: Path,
        output_dir: Path,
        title: str = "SiLukman Video Enchancer — Plugin SDK Reference",
        module_names: Optional[List[str]] = None,
    ) -> None:
        self.pipeline_dir = Path(pipeline_dir)
        self.output_dir = Path(output_dir)
        self.title = title
        self.module_names = module_names or _PLUGIN_MODULES

    def collect(self) -> List[ModuleDoc]:
        """Parse source files and return a list of ModuleDocs."""
        docs: List[ModuleDoc] = []
        for name in self.module_names:
            path = self.pipeline_dir / f"{name}.py"
            if not path.exists():
                continue
            source = path.read_text(encoding="utf-8")
            mod_doc = extract_module_doc(source, name=name, path=str(path))
            docs.append(mod_doc)
        return docs

    def build(self, output_filename: str = "sdk_reference.html") -> Path:
        """Generate HTML and write to *output_dir/output_filename*. Returns path."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        modules = self.collect()
        html_content = render_html(modules, title=self.title)
        out_path = self.output_dir / output_filename
        out_path.write_text(html_content, encoding="utf-8")
        return out_path

    def build_index(self) -> Dict[str, Any]:
        """Return a lightweight index dict (for CLI/programmatic use)."""
        modules = self.collect()
        return {
            "title": self.title,
            "modules": [
                {
                    "name": m.name,
                    "classes": [c.name for c in m.classes],
                    "functions": [f.name for f in m.functions],
                }
                for m in modules
            ],
        }


def build_offline_sdk_docs(
    project_root: Path,
    output_dir: Path | None = None,
) -> Path:
    """Build the default offline SDK reference for this repository."""

    root = Path(project_root)
    target = output_dir or root / "docs" / "sdk"
    return SdkDocGenerator(
        pipeline_dir=root / "pipeline",
        output_dir=target,
    ).build()
