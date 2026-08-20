GENERATE_VISUALIZATION_PYTHON_TEMPLATE = """
import io
import json
import base64
import matplotlib
import warnings
import pandas as pd
import numpy as np

matplotlib.use('Agg')
# Suppress all warnings from matplotlib
warnings.filterwarnings('ignore', category=UserWarning, module='matplotlib')
import matplotlib.pyplot as plt

plt.rcParams['font.family'] = ['Tahoma', 'Amiri', 'DejaVu Sans', 'Arial', 'SimSun', 'Noto Sans', 'Arial Unicode MS', 'MS Gothic']
fig, ax = plt.subplots(figsize=(6, 4))

{python_code}

# Matplotlib does not perform bidi reordering or Arabic glyph shaping, so RTL
# text (Arabic, Hebrew, Persian...) renders as disconnected left-to-right
# glyphs. Reshape every text object in the figure to visual order before saving.
try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    def _fix_rtl_text(text_obj):
        raw = text_obj.get_text()
        if raw and any('\\u0590' <= ch <= '\\u08ff' for ch in raw):
            text_obj.set_text(get_display(arabic_reshaper.reshape(raw)))

    for _ax in fig.get_axes():
        _targets = [_ax.title, _ax.xaxis.label, _ax.yaxis.label]
        _targets += _ax.get_xticklabels() + _ax.get_yticklabels() + list(_ax.texts)
        _legend = _ax.get_legend()
        if _legend:
            _targets += list(_legend.get_texts())
        for _t in _targets:
            _fix_rtl_text(_t)
    for _t in fig.texts:
        _fix_rtl_text(_t)
except ImportError:
    pass

fig.tight_layout()
my_stringIObytes = io.BytesIO()
fig.savefig(my_stringIObytes, format='svg', bbox_inches='tight')
my_stringIObytes.seek(0)
base64_string = base64.b64encode(my_stringIObytes.read()).decode()
print(f'data:image/svg+xml;base64,{{base64_string}}')
plt.close(fig)"""
