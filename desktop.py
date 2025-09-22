# desktop.py
import threading, socket, time
import webview   # pip install pywebview
from app import create_app

def find_free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]; s.close(); return port

def run_server(app, host, port):
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)

def start():
    port = find_free_port(); host = "127.0.0.1"
    flask_app = create_app()
    threading.Thread(target=run_server, args=(flask_app, host, port), daemon=True).start()
    time.sleep(0.8)
    url = f"http://{host}:{port}/"
    window = webview.create_window("MyMailerApp", url, width=1000, height=700)
    webview.start()

if __name__ == "__main__":
    start()
