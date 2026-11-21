"""The application as the server runs it: the app, with the plugin-service proxy in front (proxy.py)."""

from .proxy import PluginProxy
from .web import app as _app

app = PluginProxy(_app)
