#!/usr/bin/env python3
"""
Replaces sidebar + topbar with horizontal page-header in all HTML pages.
Run from the repo root: python3 tools/apply_page_header.py
"""
import re, sys, pathlib

FRONTEND = pathlib.Path(__file__).parent.parent / "frontend"

NAV_ITEMS = [
    ("index.html", '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>', "Dashboard"),
    ("painel.html", '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>', "Painel"),
    ("scada.html", '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg>', "SCADA"),
    ("analise.html", '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>', "Análise"),
    ("report.html", '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>', "Relatório"),
    ("hidraulica.html", '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><line x1="12" y1="2" x2="12" y2="8"/><line x1="12" y1="16" x2="12" y2="22"/><line x1="2" y1="12" x2="8" y2="12"/><line x1="16" y1="12" x2="22" y2="12"/></svg>', "Hidráulica"),
    ("dispositivos.html", '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="5" y="2" width="14" height="20" rx="2"/><line x1="12" y1="18" x2="12" y2="18"/></svg>', "Dispositivos"),
    ("documentacao.html", '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/><path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/></svg>', "Docs"),
]

THEME_BTN = '<button class="theme-btn" onclick="toggleTheme()" title="Alternar tema"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg></button>'


def make_header(active_page, gw_class=":class=\"gwStatus\"", gw_label="x-text=\"gwLabel\"", has_last_update=False):
    nav_html = ""
    for href, svg, label in NAV_ITEMS:
        cls = ' class="active"' if href == active_page else ""
        nav_html += f'      <a href="{href}"{cls}>\n        {svg}\n        {label}\n      </a>\n'

    last_update_span = ""
    if has_last_update:
        last_update_span = '\n        <span x-show="lastUpdate" x-text="\'· \'+timeAgo(lastUpdate)" style="color:var(--text3)"></span>'

    return (
        '  <header class="page-header">\n'
        '    <div class="ph-brand">\n'
        '      <div class="ph-logo">A</div>\n'
        '      <span class="ph-name">AGUADA</span>\n'
        '    </div>\n'
        '    <nav class="ph-nav">\n'
        + nav_html +
        '    </nav>\n'
        '    <div class="ph-right">\n'
        '      <div style="display:flex;align-items:center;gap:5px;font-size:11px;color:var(--text3)">\n'
        '        <span class="ws-dot" :class="wsConnected ? \'connected\':\'disconnected\'"></span>\n'
        '        <span x-text="wsConnected ? \'Ao vivo\':\'Desconectado\'"></span>'
        + last_update_span + '\n'
        '      </div>\n'
        '      <div style="display:flex;align-items:center;gap:5px;font-size:11px;color:var(--text3)">\n'
        f'        <span class="gw-dot" {gw_class}></span>\n'
        f'        <span {gw_label}></span>\n'
        '      </div>\n'
        f'      {THEME_BTN}\n'
        '    </div>\n'
        '  </header>\n'
    )


# Per-page config: (active_link, gw_class, gw_label, has_last_update)
PAGE_CONFIG = {
    "index.html":        ("index.html",       ':class="gwStatus"',          'x-text="gwLabel"',          True),
    "analise.html":      ("analise.html",      ':class="gwStatus"',          'x-text="gwLabel"',          False),
    "report.html":       ("report.html",       ':class="gwStatus"',          'x-text="gwLabel"',          False),
    "hidraulica.html":   ("hidraulica.html",   ':class="gwStatus"',          'x-text="gwLabel"',          False),
    "dispositivos.html": ("dispositivos.html", ':class="gwStatus"',          'x-text="gwLabel"',          False),
    "documentacao.html": ("documentacao.html", ':class="gwStatus"',          'x-text="gwLabel"',          False),
    "dados.html":        ("analise.html",      ':class="gwStatus"',          'x-text="gwLabel"',          False),
    "history.html":      ("analise.html",      ':class="gwStatus"',          'x-text="gwLabel"',          False),
    "consumption.html":  ("analise.html",      ':class="gwStatus"',          'x-text="gwLabel"',          False),
    "abastecimento.html":("analise.html",      ':class="gwStatus"',          'x-text="gwLabel"',          False),
    "scada.html":        ("scada.html",        ':class="gatewayClass()"',    'x-text="gatewayLabel()"',   True),
}


def process_file(path: pathlib.Path, active_page: str, gw_class: str, gw_label: str, has_last_update: bool):
    text = path.read_text(encoding="utf-8")
    original = text

    # 1. Add style="flex-direction:column;" to the layout div (only if not already present)
    text = re.sub(
        r'(<div class="layout"[^>]*?)( x-cloak>)',
        lambda m: m.group(1) + m.group(2).replace(" x-cloak>", ' x-cloak style="flex-direction:column;">'),
        text,
        count=1
    )

    # 2. Remove sidebar block (from <!-- Sidebar or <aside class="sidebar" through </aside>)
    text = re.sub(
        r'\n[ \t]*(?:<!--[^>]*?-->\n[ \t]*)?<aside class="sidebar"[^>]*>.*?</aside>\n',
        '\n',
        text,
        count=1,
        flags=re.DOTALL
    )

    # 3. Remove topbar block after <div class="main"> — matches the topbar div and its content
    #    We look for <div class="topbar"> ... </div> followed by blank/content line
    text = re.sub(
        r'(\n[ \t]*<div class="main">)\n[ \t]*<div class="topbar">.*?[ \t]*</div>\n',
        r'\1\n',
        text,
        count=1,
        flags=re.DOTALL
    )

    # 4. Insert header just before <div class="main">
    header = make_header(active_page, gw_class, gw_label, has_last_update)
    text = re.sub(
        r'(\n[ \t]*<div class="main">)',
        '\n' + header + r'\1',
        text,
        count=1
    )

    if text == original:
        print(f"  WARNING: no changes made to {path.name}")
        return False

    path.write_text(text, encoding="utf-8")
    print(f"  OK: {path.name}")
    return True


def main():
    print("Applying page-header to all HTML pages...\n")
    for filename, config in PAGE_CONFIG.items():
        path = FRONTEND / filename
        if not path.exists():
            print(f"  SKIP (not found): {filename}")
            continue
        process_file(path, *config)
    print("\nDone.")


if __name__ == "__main__":
    main()
