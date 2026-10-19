"""Deployment entry point for hosted environments (Streamlit Community Cloud, Render, ...).

Streamlit Cloud looks for ``streamlit_app.py`` by default; local users can keep using
``Start DES Lab.cmd`` which runs ``Hello.py`` directly. Both end up in the same app.
"""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).parent / "Hello.py"), run_name="__main__")
