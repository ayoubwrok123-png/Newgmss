# app.py
import os, sys, sqlite3, shutil
import imaplib, email
from email.header import decode_header
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, abort

APP_NAME = "MyMailerApp"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

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
    """If no DB in app data dir, copy bundled accounts.db"""
    if not os.path.exists(DB_FILE):
        bundled = resource_path("accounts.db")
        if os.path.exists(bundled):
            shutil.copy(bundled, DB_FILE)

def create_app():
    tpl = resource_path("templates")
    st = resource_path("static") if os.path.isdir(resource_path("static")) else None
    app = Flask(__name__, template_folder=tpl, static_folder=st)
    app.secret_key = os.environ.get("FLASK_SECRET", "chg_me_now")
    ensure_db()

    # ---- DB helpers ----
    def get_accounts():
        con = sqlite3.connect(DB_FILE); cur = con.cursor()
        cur.execute("SELECT id, email, label FROM accounts ORDER BY id DESC")
        rows = cur.fetchall(); con.close(); return rows

    def get_account_by_id(acc_id):
        con = sqlite3.connect(DB_FILE); cur = con.cursor()
        cur.execute("SELECT id, email, app_password, label FROM accounts WHERE id=?", (acc_id,))
        row = cur.fetchone(); con.close(); return row

    def add_account(email_addr, app_pass, label=None):
        con = sqlite3.connect(DB_FILE); cur = con.cursor()
        try:
            cur.execute("INSERT INTO accounts (email, app_password, label) VALUES (?, ?, ?)",
                        (email_addr, app_pass, label))
            con.commit(); return True, None
        except sqlite3.IntegrityError as e:
            return False, str(e)
        finally:
            con.close()

    def delete_account(acc_id):
        con = sqlite3.connect(DB_FILE); cur = con.cursor()
        cur.execute("DELETE FROM accounts WHERE id=?", (acc_id,))
        con.commit(); con.close()

    # ---- Mail helpers ----
    def clean_subject(raw_subj):
        if not raw_subj: return ""
        parts = decode_header(raw_subj); result = []
        for subj, enc in parts:
            if isinstance(subj, bytes):
                try: result.append(subj.decode(enc or "utf-8", errors="ignore"))
                except: result.append(subj.decode(errors="ignore"))
            else: result.append(str(subj))
        return "".join(result).strip()

    def fetch_last_subjects(email_user, email_pass, days=1, limit=5):
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
                for name, path in folders.items():
                    try:
                        imap.select(path, readonly=True)
                        date_since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
                        status, data = imap.search(None, f'(SINCE {date_since})')
                        if status == "OK" and data[0]:
                            ids = data[0].split()[-limit:]
                            for msg_id in ids:
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

    # ---- Routes ----
    def is_admin_ok(pw): return pw and pw == ADMIN_PASSWORD

    @app.route("/")
    def index():
        return render_template("index.html", accounts=get_accounts())

    @app.route("/check/<int:acc_id>")
    def check(acc_id):
        row = get_account_by_id(acc_id)
        if not row: return "Account not found", 404
        _, email_addr, app_pass, _ = row
        results = fetch_last_subjects(email_addr, app_pass)
        return render_template("results.html", email=email_addr, results=results)

    @app.route("/admin", methods=["GET","POST"])
    def admin():
        pw = request.args.get("pw") or request.form.get("pw")
        if not is_admin_ok(pw): return render_template("admin.html", authorized=False)
        if request.method == "POST":
            email_addr = request.form.get("email"); app_pass = request.form.get("app_password")
            label = request.form.get("label") or None
            if not email_addr or not app_pass:
                flash("Email and app password are required", "error")
                return redirect(url_for("admin", pw=pw))
            ok, err = add_account(email_addr.strip(), app_pass.strip(), label)
            flash("Account added" if ok else f"Error: {err}", "success" if ok else "error")
            return redirect(url_for("admin", pw=pw))
        return render_template("admin.html", authorized=True, accounts=get_accounts(), pw=pw)

    @app.route("/delete/<int:acc_id>", methods=["POST"])
    def do_delete(acc_id):
        pw = request.form.get("pw")
        if not is_admin_ok(pw): abort(403)
        delete_account(acc_id); flash("Deleted", "success")
        return redirect(url_for("admin", pw=pw))

    @app.route("/export")
    def export_db():
        pw = request.args.get("pw")
        if not is_admin_ok(pw): abort(403)
        return send_file(DB_FILE, as_attachment=True, download_name="accounts.db")

    return app
