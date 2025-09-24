import imaplib
import email
from email.header import decode_header
from flask import Flask, render_template, request, session, redirect, url_for

app = Flask(__name__)
app.secret_key = "super_secret_key"

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


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


def fetch_emails(user, password, folder="INBOX", limit=20):
    results = []
    try:
        with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
            imap.login(user, password)
            imap.select(folder)
            status, data = imap.search(None, "ALL")
            if status != "OK":
                return []

            ids = data[0].split()[-limit:]
            for msg_id in reversed(ids):
                res, msg_data = imap.fetch(msg_id, "(RFC822)")
                if res != "OK":
                    continue
                msg = email.message_from_bytes(msg_data[0][1])

                # Prefer Received date (harder to spoof than Date)
                received = msg.get("Received")
                if received:
                    date = received.split(";")[-1].strip()
                else:
                    date = msg.get("Date", "")

                subj = clean_subject(msg.get("Subject"))
                sender = msg.get("From")

                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        ctype = part.get_content_type()
                        if ctype == "text/html":
                            body = part.get_payload(decode=True).decode(errors="ignore")
                            break
                        elif ctype == "text/plain":
                            body = part.get_payload(decode=True).decode(errors="ignore")
                else:
                    body = msg.get_payload(decode=True).decode(errors="ignore")

                results.append({
                    "subject": subj,
                    "from": sender,
                    "date": date,
                    "body": body
                })
            imap.logout()
    except Exception as e:
        print("Error:", e)
    return results


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        session["email"] = request.form["email"]
        session["password"] = request.form["password"]
        return redirect(url_for("mailbox"))
    return render_template("login.html")


@app.route("/mailbox")
def mailbox():
    if "email" not in session:
        return redirect(url_for("login"))

    user = session["email"]
    pw = session["password"]

    inbox = fetch_emails(user, pw, "INBOX", 20)
    spam = fetch_emails(user, pw, "[Gmail]/Spam", 20)

    return render_template("mailbox.html", email=user, inbox=inbox, spam=spam)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
