import base64
import logging
import os
from datetime import datetime

from pathlib import Path
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def load_color_palettes():
    """Load color palettes from environment variables with fallback to defaults."""
    default_palettes = {
        'blue': {'primary': '#3182ce', 'text': '#ffffff', 'name': 'blue'},
        'black': {'primary': '#2d3748', 'text': '#ffffff', 'name': 'black'},
        'red': {'primary': '#c53030', 'text': '#ffffff', 'name': 'red'},
        'green': {'primary': '#38a169', 'text': '#ffffff', 'name': 'green'},
        'dark': {'primary': '#3b82c4', 'text': '#ffffff', 'name': 'dark'},
        'light': {'primary': '#a0aec0', 'text': '#1a202c', 'name': 'light'}
    }

    palettes = {}

    for color_name in ['blue', 'black', 'red', 'green', 'dark', 'light']:
        color_upper = color_name.upper()
        palettes[color_name] = {
            'primary': os.getenv(f'DEEPQUERY_REPORT_COLOR_SCHEME_{color_upper}_PRIMARY',
                               default_palettes[color_name]['primary']),
            'text': os.getenv(f'DEEPQUERY_REPORT_COLOR_SCHEME_{color_upper}_TEXT',
                            default_palettes[color_name]['text']),
            'name': color_name
        }

    return palettes

# Define color palettes for different themes
# Load from environment variables with fallback to defaults
COLOR_PALETTES = load_color_palettes()

# Surface variables (backgrounds, text and borders) shared by every theme of the same kind.
# The accent colors (--dq-primary / --dq-primary-text) come from COLOR_PALETTES.
LIGHT_SURFACE_VARIABLES = {
    '--dq-bg': '#ffffff',
    '--dq-fg': '#333333',
    '--dq-h1': '#1a365d',
    '--dq-h2': '#2d3748',
    '--dq-h3': '#4a5568',
    '--dq-strong': '#2d3748',
    '--dq-muted': '#6c757d',
    '--dq-meta': '#4a5568',
    '--dq-border': '#e2e8f0',
    '--dq-code-bg': '#f7fafc',
    '--dq-code-text': '#e53e3e',
    '--dq-pre-bg': '#f8f9fa',
    '--dq-pre-border': '#e9ecef',
    '--dq-pre-text': '#495057',
    '--dq-row-alt': '#f8f9fa',
    '--dq-sql': '#0066cc',
    '--dq-highlight': '#fef5e7',
    '--dq-img-bg': 'transparent',
}

DARK_SURFACE_VARIABLES = {
    '--dq-bg': '#121826',
    '--dq-fg': '#e2e8f0',
    '--dq-h1': '#f7fafc',
    '--dq-h2': '#e2e8f0',
    '--dq-h3': '#cbd5e0',
    '--dq-strong': '#f7fafc',
    '--dq-muted': '#a0aec0',
    '--dq-meta': '#cbd5e0',
    '--dq-border': '#2d3748',
    '--dq-code-bg': '#1e2638',
    '--dq-code-text': '#fc8181',
    '--dq-pre-bg': '#1a2233',
    '--dq-pre-border': '#2d3748',
    '--dq-pre-text': '#cbd5e0',
    '--dq-row-alt': '#1a2233',
    '--dq-sql': '#63b3ed',
    '--dq-highlight': '#3b3320',
    '--dq-img-bg': '#ffffff',
}

def _theme_variables_css(selector, palette):
    """Render the CSS custom properties of one theme under the given selector."""
    surface = DARK_SURFACE_VARIABLES if palette.get('name') == 'dark' else LIGHT_SURFACE_VARIABLES
    variables = {
        '--dq-primary': palette['primary'],
        '--dq-primary-text': palette['text'],
        **surface,
    }
    body = "\n".join(f"        {name}: {value};" for name, value in variables.items())
    return f"{selector} {{\n{body}\n    }}"

def get_denodo_logo():
    """Load the local Denodo logo and convert to base64 for embedding."""
    logo_path = Path("api/static/denodo_logo.png")

    try:
        if logo_path.exists():
            with open(logo_path, "rb") as f:
                logo_base64 = base64.b64encode(f.read()).decode('utf-8')
                return f"data:image/png;base64,{logo_base64}"
        else:
            print(f"Warning: Denodo logo not found at {logo_path}")
            return None
    except Exception as e:
        print(f"Warning: Could not load Denodo logo: {e}")
        return None

def get_css_styles(palette):
    """
    Generate comprehensive CSS styles for the report.

    All colors are CSS custom properties (--dq-*). ':root' holds the theme the
    report was generated with and html[data-theme="..."] blocks hold every
    available theme, so a viewer can switch themes just by changing the
    data-theme attribute of the <html> element, without regenerating the report.
    """
    theme_css = "\n\n    ".join(
        [_theme_variables_css(':root', palette)]
        + [_theme_variables_css(f'html[data-theme="{name}"]', theme) for name, theme in COLOR_PALETTES.items()]
    )

    return f"""
    /* Theme variables */
    {theme_css}

    /* Reset and base styles */
    * {{
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }}

    @page {{
        size: A4;
        margin: 2cm 1.5cm;
        @bottom-right {{
            content: "Page " counter(page) " of " counter(pages);
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 9pt;
            color: #666;
        }}
    }}

    body {{
        font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
        line-height: 1.6;
        color: var(--dq-fg);
        background-color: var(--dq-bg);
        font-size: 11pt;
        max-width: 900px;
        margin: 5px auto;
        padding: 16px;
    }}

    html {{
        background-color: var(--dq-bg);
    }}

    /* Center images */
    img {{
        display: block;
        margin: auto;
        max-width: 100%;
        height: auto;
        background-color: var(--dq-img-bg);
    }}

    /* In-flow header for first page */
    .report-header {{
        display: flex;
        flex-direction: column;
        align-items: center;
        margin-bottom: 30pt;
        page-break-after: avoid;
    }}

    .header-logo {{
        height: 30px;
        width: auto;
        margin-bottom: 8px;
    }}

    .header-text {{
        font-size: 9pt;
        color: var(--dq-muted);
    }}

    .header-meta {{
        font-size: 10pt;
        color: var(--dq-meta);
        margin-top: 5pt;
        font-style: italic;
    }}

    /* Typography */
    h1 {{
        font-size: 24pt;
        font-weight: 700;
        color: var(--dq-h1);
        margin-bottom: 30pt;
        padding-bottom: 15pt;
        border-bottom: 3px solid var(--dq-primary);
        page-break-after: avoid;
        text-align: center;
    }}

    h2 {{
        font-size: 18pt;
        font-weight: 600;
        color: var(--dq-h2);
        margin-top: 30pt;
        margin-bottom: 15pt;
        padding-top: 10pt;
        border-top: 2px solid var(--dq-border);
        page-break-after: avoid;
    }}

    h2:first-of-type {{
        border-top: none;
        margin-top: 0;
    }}

    h3 {{
        font-size: 14pt;
        font-weight: 600;
        color: var(--dq-h3);
        margin-top: 20pt;
        margin-bottom: 10pt;
        page-break-after: avoid;
    }}

    p {{
        margin-bottom: 12pt;
        text-align: justify;
        orphans: 2;
        widows: 2;
    }}

    /* Lists */
    ul, ol {{
        margin-bottom: 12pt;
        padding-left: 20pt;
    }}

    li {{
        margin-bottom: 6pt;
        orphans: 2;
        widows: 2;
    }}

    /* Strong text */
    strong {{
        font-weight: 600;
        color: var(--dq-strong);
    }}

    /* Inline code */
    code {{
        font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
        background-color: var(--dq-code-bg);
        color: var(--dq-code-text);
        padding: 2pt 4pt;
        border-radius: 3pt;
        font-size: 10pt;
        border: 1px solid var(--dq-border);
        direction: ltr !important;
        unicode-bidi: embed;
    }}

    /* Code blocks */
    pre {{
        background-color: var(--dq-pre-bg);
        border: 1px solid var(--dq-pre-border);
        border-radius: 6pt;
        padding: 15pt;
        margin: 15pt 0;
        font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
        font-size: 9pt;
        line-height: 1.4;
        overflow-x: auto;
        page-break-inside: auto; /* Allow code blocks to break to prevent large gaps */
        white-space: pre-wrap;
        word-wrap: break-word;
        direction: ltr !important;
        text-align: left !important;
        unicode-bidi: embed;
    }}

    pre code {{
        background-color: transparent;
        border: none;
        padding: 0;
        color: var(--dq-pre-text);
        font-size: inherit;
    }}

    /* Tables - Anti-overflow system */
    table {{
        width: 100%;
        border-collapse: collapse;
        margin: 20pt 0;
        page-break-inside: avoid;
        table-layout: fixed;
    }}

    /* Table headers */
    thead {{
        background-color: var(--dq-primary);
        color: var(--dq-primary-text);
    }}

    th {{
        text-align: left;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.3pt;
        border: 1px solid var(--dq-primary);
        hyphens: auto;
        overflow-wrap: break-word; /* Use safer wrapping */
        vertical-align: middle;
    }}

    /* Table body */
    tbody tr:nth-child(even) {{
        background-color: var(--dq-row-alt);
    }}

    td {{
        border: 1px solid var(--dq-border);
        vertical-align: top;
        hyphens: auto;
        overflow-wrap: break-word; /* Allow content in cells to wrap */
    }}

    table th, table td {{
        width: auto;
    }}

    /* Special case for 2-column definition tables */
    .definition-table th:nth-of-type(1), .definition-table td:nth-of-type(1) {{ width: 40%; }}
    .definition-table th:nth-of-type(2), .definition-table td:nth-of-type(2) {{ width: 60%; }}

    /* Responsive font and padding based on column count */
    /* 8+ columns - Very compressed */
    table.very-wide-table th, table.very-wide-table td {{
        font-size: 7pt;
        padding: 3pt 2pt;
        line-height: 1.1;
    }}
    /* 6-7 columns - Compressed */
    table.wide-table th, table.wide-table td {{
        font-size: 8pt;
        padding: 4pt 3pt;
        line-height: 1.2;
    }}
    /* 4-5 columns - Normal compression */
    table.medium-table th, table.medium-table td {{
        font-size: 9pt;
        padding: 6pt 4pt;
        line-height: 1.3;
    }}
    /* 1-3 columns - Comfortable spacing */
    table.narrow-table th, table.narrow-table td {{
        font-size: 10pt;
        padding: 8pt 6pt;
        line-height: 1.4;
    }}

    table.definition-table th {{ text-align: center; }}
    table.definition-table td:first-child {{ font-weight: 600; color: var(--dq-fg); }}
    table.definition-table td:last-child {{
        text-align: right;
    }}

    /* Default alignment for cells */
    td {{
        text-align: right;
        padding: 6pt 4pt; /* More compact default padding */
    }}

    /* First column (usually text) styling */
    td:first-child {{
        font-weight: 500;
        color: var(--dq-strong);
    }}

    [dir="rtl"] td, [dir="rtl"] th {{
        text-align: right !important;
    }}

    [dir="rtl"] td.numeric {{
        text-align: left !important;
        direction: ltr !important;
    }}

    .avoid-break {{
        page-break-inside: avoid;
    }}

    /* Executive summary styling */
    h2 + p strong {{
        color: var(--dq-primary);
    }}

    /* Methodology section specific styling */
    h2[id="methodology"] + * {{
        margin-top: 15pt;
    }}

    /* Print optimizations */
    @media print {{
        body {{
            print-color-adjust: exact;
        }}

        .page, .page-break {{ break-after: page; }}

        table {{
            page-break-inside: auto;
        }}

        tr {{
            page-break-inside: avoid;
            page-break-after: auto;
        }}

        thead {{
            display: table-header-group;
        }}

        tfoot {{
            display: table-footer-group;
        }}
    }}

    /* Highlight key metrics */
    strong:contains("2.06") {{
        background-color: var(--dq-highlight);
        padding: 2pt;
        border-radius: 3pt;
    }}

    /* Better spacing for bullet points */
    ul li {{
        margin-left: 5pt;
    }}

    /* SQL syntax highlighting hints */
    pre code[class*="language-sql"] {{
        color: var(--dq-sql);
    }}

    .appendix-ltr-container {{
        direction: ltr !important;
        text-align: left !important;
        padding-top: 20pt;
    }}

    .appendix-ltr-container h2,
    .appendix-ltr-container h3,
    .appendix-ltr-container p,
    .appendix-ltr-container ul,
    .appendix-ltr-container li,
    .appendix-ltr-container table,
    .appendix-ltr-container th,
    .appendix-ltr-container td {{
        text-align: left !important;
        direction: ltr !important;
    }}
    """

def prepare_html(html_content, logo_data_uri=None, username=None):
    """
    Processes raw HTML to add branding and responsive classes for styling.
    Returns the processed HTML for the 'body' of the document.
    """
    soup = BeautifulSoup(html_content, 'lxml')

    body = soup.find('body')
    if not body:
        body = soup

    appendix_header = body.find(
        lambda tag: tag.name == 'h2' and 'Appendix' in tag.get_text(strip=True)
    )

    if appendix_header:
        ltr_wrapper = soup.new_tag('div', dir='ltr')
        ltr_wrapper['class'] = 'appendix-ltr-container'
        siblings = appendix_header.find_next_siblings()
        appendix_header.wrap(ltr_wrapper)

        for sibling in siblings:
            ltr_wrapper.append(sibling)

    current_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    if username:
        meta_text = f"Generated by <strong>{username}</strong> on {current_date}"
    else:
        meta_text = f"Generated on {current_date}"

    if logo_data_uri:
        header_html = f"""
        <div class="report-header">
            <img src="{logo_data_uri}" alt="Denodo Logo" class="header-logo">
            <div class="header-text">Powered by the Denodo AI SDK</div>
            <div class="header-meta">{meta_text}</div>
        </div>
        """
    else:
        header_html = f"""
        <div class="report-header">
            <div class="header-text">Powered by the Denodo AI SDK</div>
            <div class="header-meta">{meta_text}</div>
        </div>
        """

    body.insert(0, BeautifulSoup(header_html, 'html.parser'))

    tables = soup.find_all('table')
    for table in tables:
        th_count = 0
        header_row = table.find('thead') or table.find('tr')
        if header_row:
            th_count = len(header_row.find_all(['th', 'td']))

        existing_classes = table.get('class', [])
        if isinstance(existing_classes, str): existing_classes = [existing_classes]

        width_classes = ['very-wide-table', 'wide-table', 'medium-table', 'narrow-table', 'definition-table']
        existing_classes = [cls for cls in existing_classes if cls not in width_classes]

        if th_count >= 8: existing_classes.append('very-wide-table')
        elif th_count >= 6: existing_classes.append('wide-table')
        elif th_count >= 4: existing_classes.append('medium-table')
        else: existing_classes.append('narrow-table')

        if th_count == 2 and header_row:
            existing_classes.append('definition-table')

        table['class'] = list(set(existing_classes))

        for row in table.find_all('tr'):
            if row.find('th'): continue

            for col_idx, cell in enumerate(row.find_all('td')):
                if col_idx == 0: continue

                cell_text = cell.get_text(strip=True)
                try:
                    float(cell_text.replace('%', '').replace('×', '').strip())
                    cell_classes = cell.get('class', [])
                    if isinstance(cell_classes, str): cell_classes = [cell_classes]
                    if 'numeric' not in cell_classes:
                        cell_classes.append('numeric')
                    cell['class'] = cell_classes
                except (ValueError, TypeError):
                    pass

    return str(body)

def build_styled_html(html_content: str, color_palette: dict, title: str, text_direction: str = "ltr", username: str = None) -> str:
    """
    Build a complete styled HTML document with Denodo branding and color palette,
    supporting RTL and LTR text directions dynamically.
    """
    logger.info(
        f"Building styled HTML document (input length: {len(html_content)}) "
        f"using '{color_palette['name']}' theme. Text direction: {text_direction}, user: {username}"
    )

    logo_data_uri = get_denodo_logo()
    processed_body_content = prepare_html(html_content, logo_data_uri, username)
    css_styles = get_css_styles(color_palette)

    final_html_doc = f"""
    <!DOCTYPE html>
    <html dir="{text_direction}" data-theme="{color_palette['name']}">
    <head>
        <meta charset="UTF-8">
        <title>{title}</title>
        <style>{css_styles}</style>
    </head>
    {processed_body_content}
    </html>
    """

    return final_html_doc
