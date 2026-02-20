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

fig.tight_layout()
my_stringIObytes = io.BytesIO()
fig.savefig(my_stringIObytes, format='svg', bbox_inches='tight')
my_stringIObytes.seek(0)
base64_string = base64.b64encode(my_stringIObytes.read()).decode()
print(f'data:image/svg+xml;base64,{{base64_string}}')
plt.close(fig)"""
