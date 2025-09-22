import os, sys, sqlite3, shutil
import imaplib, email
from email.header import decode_header
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, abort, jsonify
from concurrent.futures import ThreadPoolExecutor

APP_NAME = "MyMailerApp"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

# ---------- Helpers ----------
def resource_path(*parts):
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base, *parts)

def app_data_dir():
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, APP_NAME)
    else:
        d = os.path.join(os.path.expanduser("~"), f".{APP_NAME.lower()}")
    os.makedirs(d, exist_ok=True)
    return d

DB_FILE = os.path.join(app_data_dir(), "accounts.db")

def ensure_db():
    if not os.path.exists(DB_FILE):
        bundled = resource_path("accounts.db")
        if os.path.exists(bundled):
            shutil.copy(bundled, DB_FILE)

# ---------- DB ----------
def get_accounts():
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("SELECT id, email, label FROM accounts ORDER BY id DESC")
    rows = cur.fetchall()
    con.close()
    return rows

def get_account_by_id(acc_id):
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("SELECT id, email, app_password, label FROM accounts WHERE id=?", (acc_id,))
    row = cur.fetchone()
    con.close()
    return row

# ---------- Mail ----------
def clean_subject(raw_subj):
    if not raw_subj:
        return ""
    parts = decode_header(raw_subj)
    result = []
    for subj, enc in parts:
        if isinstance(subj, bytes):
            try:
                result.append(subj.decode(enc or "utf-8", errors="ignore"))
            except:
                result.append(subj.decode(errors="ignore"))
        else:
            result.append(str(subj))
    return "".join(result).strip()

def fetch_last_subjects(email_user, email_pass, limit=20):
    results = {"INBOX": [], "SPAM": [], "PROMOTIONS": [], "UPDATES": []}
    folders = {
        "INBOX": "INBOX",
        "SPAM": "[Gmail]/Spam",
        "PROMOTIONS": "[Gmail]/Promotions",
        "UPDATES": "[Gmail]/Updates"
    }
    try:
        with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
            imap.login(email_user, email_pass)
            today = datetime.now().strftime("%d-%b-%Y")
            for name, path in folders.items():
                try:
                    imap.select(path, readonly=True)
                    status, data = imap.search(None, f'(SINCE {today})')
                    if status == "OK" and data[0]:
                        ids = data[0].split()[-limit:]
                        for msg_id in reversed(ids):
                            res, msg_data = imap.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
                            if res == "OK" and msg_data and msg_data[0]:
                                msg = email.message_from_bytes(msg_data[0][1])
                                results[name].append(clean_subject(msg.get("Subject")))
                except Exception:
                    results[name].append("<error>")
            imap.logout()
    except Exception as e:
        return {"error": str(e)}
    return results

# ---------- Flask App ----------
def create_app():
    tpl = resource_path("templates")
    app = Flask(__name__, template_folder=tpl)
    app.secret_key = os.environ.get("FLASK_SECRET", "chg_me_now")
    ensure_db()

    # Routes
    @app.route("/")
    def index():
        return render_template("index.html", accounts=get_accounts())

    @app.route("/check/<int:acc_id>")
    def check(acc_id):
        row = get_account_by_id(acc_id)
        if not row:
            return "Account not found", 404
        _, email_addr, app_pass, _ = row
        results = fetch_last_subjects(email_addr, app_pass)
        return render_template("results.html", email=email_addr, results=results)

    # Multi-check API
    @app.route("/api/check_multi", methods=["POST"])
    def check_multi():
        ids = request.json.get("ids", [])[:5]
        results = {}

        def worker(acc_id):
            row = get_account_by_id(acc_id)
            if not row:
                return {"error": "Account not found"}
            _, email_addr, app_pass, _ = row
            return fetch_last_subjects(email_addr, app_pass)

        with ThreadPoolExecutor(max_workers=5) as executor:
            future_map = {executor.submit(worker, acc_id): acc_id for acc_id in ids}
            for f in future_map:
                acc_id = future_map[f]
                results[acc_id] = f.result()

        return jsonify(results)

    return app

if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=True)
