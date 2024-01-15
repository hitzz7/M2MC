

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import json
import sqlite3
import threading
import cgi
import uuid
import os
from PIL import Image
import mysql.connector

from shop import CustomHandler


if __name__ == '__main__':
    host = '127.0.0.1'
    port = 8080

    server = HTTPServer((host, port), CustomHandler)

    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()

    print(f'Starting server on http://{host}:{port}')

    try:
        server_thread.join()
    except KeyboardInterrupt:
        server.shutdown()
        print('Server stopped')