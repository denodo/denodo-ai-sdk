"""
Flask extensions module.
"""

import threading
from flask_login import LoginManager

# Flask-Login setup
login_manager = LoginManager()

# Thread lock for report file operations
report_lock = threading.Lock()
