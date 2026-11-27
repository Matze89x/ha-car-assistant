"""The application as the server runs it: the app, with the plugin-service proxy in front (proxy.py) and the request line of the log level debug around
both (logsetup.RequestLog)."""

from .logsetup import RequestLog
from .proxy import PluginProxy
from .web import app as _app

app = RequestLog(PluginProxy(_app))
