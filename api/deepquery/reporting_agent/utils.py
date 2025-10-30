import sys
import base64
import logging
import os
import asyncio

from pathlib import Path
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

def load_color_palettes():
    """Load color palettes from environment variables with fallback to defaults."""
    default_palettes = {
        'blue': {'primary': '#3182ce', 'text': '#ffffff', 'name': 'blue'},
        'black': {'primary': '#2d3748', 'text': '#ffffff', 'name': 'black'},
        'red': {'primary': '#c53030', 'text': '#ffffff', 'name': 'red'},
        'green': {'primary': '#38a169', 'text': '#ffffff', 'name': 'green'}
    }

    palettes = {}

    for color_name in ['blue', 'black', 'red', 'green']:
        color_upper = color_name.upper()
        palettes[color_name] = {
            'primary': os.getenv(f'DEEPQUERY_PDF_COLOR_SCHEME_{color_upper}_PRIMARY',
                               default_palettes[color_name]['primary']),
            'text': os.getenv(f'DEEPQUERY_PDF_COLOR_SCHEME_{color_upper}_TEXT',
                            default_palettes[color_name]['text']),
            'name': color_name
        }

    return palettes

# Define color palettes for different themes
# Load from environment variables with fallback to defaults
COLOR_PALETTES = load_color_palettes()

def get_denodo_logo():
    """Load the local Denodo logo and convert to base64 for embedding."""
    logo_path = Path("api/static/denodo-logo.png")

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
    """Generate comprehensive CSS styles for the report."""

    return f"""
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
        color: #333;
        background-color: #fff;
        font-size: 11pt;
    }}

    /* Center images */
    img {{
        display: block;
        margin: auto;
        max-width: 100%;
        height: auto;
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
        color: #6c757d;
    }}

    /* Typography */
    h1 {{
        font-size: 24pt;
        font-weight: 700;
        color: #1a365d;
        margin-bottom: 30pt;
        padding-bottom: 15pt;
        border-bottom: 3px solid {palette['primary']};
        page-break-after: avoid;
        text-align: center;
    }}

    h2 {{
        font-size: 18pt;
        font-weight: 600;
        color: #2d3748;
        margin-top: 30pt;
        margin-bottom: 15pt;
        padding-top: 10pt;
        border-top: 2px solid #e2e8f0;
        page-break-after: avoid;
    }}

    h2:first-of-type {{
        border-top: none;
        margin-top: 0;
    }}

    h3 {{
        font-size: 14pt;
        font-weight: 600;
        color: #4a5568;
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
        color: #2d3748;
    }}

    /* Inline code */
    code {{
        font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
        background-color: #f7fafc;
        color: #e53e3e;
        padding: 2pt 4pt;
        border-radius: 3pt;
        font-size: 10pt;
        border: 1px solid #e2e8f0;
    }}

    /* Code blocks */
    pre {{
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
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
    }}

    pre code {{
        background-color: transparent;
        border: none;
        padding: 0;
        color: #495057;
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
        background-color: {palette['primary']};
        color: {palette['text']};
    }}

    th {{
        text-align: left;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.3pt;
        border: 1px solid {palette['primary']};
        hyphens: auto;
        overflow-wrap: break-word; /* Use safer wrapping */
        vertical-align: middle;
    }}

    /* Table body */
    tbody tr:nth-child(even) {{
        background-color: #f8f9fa;
    }}

    td {{
        border: 1px solid #e2e8f0;
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
    table.definition-table td:first-child {{ font-weight: 600; color: #333; }}
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
        color: #2d3748;
    }}

    .avoid-break {{
        page-break-inside: avoid;
    }}

    /* Executive summary styling */
    h2 + p strong {{
        color: {palette['primary']};
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
        background-color: #fef5e7;
        padding: 2pt;
        border-radius: 3pt;
    }}

    /* Better spacing for bullet points */
    ul li {{
        margin-left: 5pt;
    }}

    /* SQL syntax highlighting hints */
    pre code[class*="language-sql"] {{
        color: #0066cc;
    }}
    """

def prepare_html_for_pdf(html_content, logo_data_uri=None):
    """
    Processes raw HTML to add branding and responsive classes for styling.
    Returns the processed HTML for the 'body' of the document.
    """
    soup = BeautifulSoup(html_content, 'lxml')

    body = soup.find('body')
    if not body:
        body = soup

    if logo_data_uri:
        header_html = f"""
        <div class="report-header">
            <img src="{logo_data_uri}" alt="Denodo Logo" class="header-logo">
            <div class="header-text">Powered by the Denodo AI SDK</div>
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

        # Only apply definition-table class if the table has exactly 2 columns
        # AND the headers are specifically 'Parameter' and 'Value'
        if th_count == 2 and header_row:
            headers = [th.get_text(strip=True).lower() for th in header_row.find_all(['th', 'td'])]
            if len(headers) == 2 and 'parameter' in headers and 'value' in headers:
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


async def convert_html_to_pdf(html_content, output_file, color_palette, title):
    """Convert HTML file to PDF using Playwright with professional styling."""
    output_path = Path(output_file)

    logger.info(f"Converting the provided html_content (length: {len(html_content)}) to {output_file} using '{color_palette['name']}' theme with Playwright...")

    logo_data_uri = get_denodo_logo()

    processed_body_content = prepare_html_for_pdf(html_content, logo_data_uri)

    css_styles = get_css_styles(color_palette)

    final_html_doc = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>{title}</title>
        <style>{css_styles}</style>
    </head>
    {processed_body_content}
    </html>
    """

    async def _convert_with_playwright():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content(final_html_doc)

            # Generate PDF with A4 format and background graphics
            await page.pdf(
                path=output_path,
                format='A4',
                print_background=True,
                margin={
                    'top': '2cm',
                    'right': '1.5cm',
                    'bottom': '2cm',
                    'left': '1.5cm'
                }
            )

            await browser.close()

    try:
        await _convert_with_playwright()
        logger.info(f"Successfully generated PDF using Playwright: {output_path}")
    except NotImplementedError as e:
        if sys.platform == 'win32':
            logger.info("NotImplementedError detected on Windows, trying with WindowsSelectorEventLoopPolicy...")
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            try:
                await _convert_with_playwright()
                logger.info(f"Successfully generated PDF using Playwright after changing Windows event loop policy: {output_path}")
            except Exception as retry_e:
                logger.error(f"Error converting HTML to PDF with Playwright after changing Windows event loop policy: {retry_e}")
                raise
        else:
            logger.error(f"NotImplementedError on non-Windows platform: {e}")
            raise
    except Exception as e:
        logger.error(f"Error converting HTML to PDF with Playwright: {e}")
        raise