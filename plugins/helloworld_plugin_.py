'''
This is the example of plugin.
Rename this file to helloworld_plugin.py to enable it.

To use it, go to http://127.0.0.1:8000/helloworld
'''
from modules.PluginInterface import AceProxyPlugin


class Helloworld(AceProxyPlugin):
    handlers = ('helloworld', )

    def __init__(self, AceConfig, AceProxy):
        pass

    def handle(self, connection, headers_only=False):
        connection.send_response(200)

        if headers_only:
            connection.send_header('Connection', 'close')
            connection.end_headers()
            return

        hello_world = b"""<html><body><h3>Hello world!</h3></body></html>"""

        connection.send_header('Content-type', 'text/html; charset=utf-8')
        connection.send_header('Content-Length', len(hello_world))
        connection.end_headers()

        connection.wfile.write(hello_world)
