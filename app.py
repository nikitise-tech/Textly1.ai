import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, hmac, hashlib, json
from dotenv import load_dotenv

load_dotenv()

def db():
    con = sqlite3.connect(os.environ.get("SQLITE_PATH", "textly.db"), check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db(); cur = con.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            email_verified INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan TEXT,
            status TEXT,
            current_period_end TEXT,
            auto_renew INTEGER DEFAULT 1,
            provider TEXT,
            provider_subscription_id TEXT,
            is_lifetime INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS usage_quota (
            user_id INTEGER PRIMARY KEY,
            free_generated INTEGER DEFAULT 0,
            free_reset_at TEXT
        );
        """
    )
    con.commit(); con.close()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret')

init_db()

def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    con = db(); cur = con.cursor()
    cur.execute("SELECT id, email FROM users WHERE id=?", (uid,))
    row = cur.fetchone(); con.close()
    if not row: return None
    return {"id": row["id"], "email": row["email"]}

def is_pro(user_id):
    con = db(); cur = con.cursor()
    cur.execute("""SELECT plan,status,current_period_end,is_lifetime
                   FROM subscriptions WHERE user_id=? ORDER BY id DESC LIMIT 1""", (user_id,))
    row = cur.fetchone(); con.close()
    if not row:
        return False
    plan, status, cpe, lifetime = row
    if lifetime == 1:
        return True
    if status != "active":
        return False
    try:
        return datetime.fromisoformat(cpe) > datetime.utcnow()
    except Exception:
        return False

@app.context_processor
def inject_user():
    return {"current_user": current_user()}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/pricing")
def pricing():
    return render_template("pricing.html")

@app.route("/app")
def app_page():
    if not current_user():
        return redirect(url_for("login"))
    return render_template("app.html")

@app.route("/auth/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        pw = request.form.get("password","")
        if not email or not pw:
            flash("Bitte E-Mail und Passwort angeben.", "error")
            return redirect(url_for("register"))
        con = db(); cur = con.cursor()
        try:
            cur.execute("INSERT INTO users(email,password_hash,email_verified,created_at) VALUES(?,?,0,?)",
                        (email, generate_password_hash(pw), datetime.utcnow().isoformat()))
            con.commit()
            session["uid"] = cur.lastrowid
            flash("Konto erstellt. Willkommen bei Textly!", "success")
            return redirect(url_for("app_page"))
        except sqlite3.IntegrityError:
            flash("Diese E-Mail ist bereits registriert.", "error")
            return redirect(url_for("register"))
        finally:
            con.close()
    return render_template("register.html")

@app.route("/auth/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        pw = request.form.get("password","")
        con = db(); cur = con.cursor()
        cur.execute("SELECT id,password_hash FROM users WHERE email=?", (email,))
        row = cur.fetchone(); con.close()
        if not row or not check_password_hash(row["password_hash"], pw):
            flash("Ungültige Zugangsdaten.", "error")
            return redirect(url_for("login"))
        session["uid"] = row["id"]
        flash("Erfolgreich angemeldet.", "success")
        return redirect(url_for("app_page"))
    return render_template("login.html")

@app.route("/auth/logout")
def logout():
    session.clear()
    flash("Abgemeldet.", "info")
    return redirect(url_for("index"))

@app.post("/api/generate")
def api_generate():
    user = current_user()
    if not user:
        return jsonify({"ok": False, "error": "auth_required"}), 401

    # Pro users: unlimited
    if is_pro(user["id"]):
        return jsonify({"ok": True, "text": "Hier kommt dein generierter Text ✨ (Demo)"})

    # Free tier: 3 per day
    con = db(); cur = con.cursor()
    cur.execute("SELECT free_generated, free_reset_at FROM usage_quota WHERE user_id=?", (user["id"],))
    row = cur.fetchone()
    now = datetime.utcnow()
    if not row:
        cur.execute("INSERT INTO usage_quota(user_id, free_generated, free_reset_at) VALUES(?,?,?)",
                    (user["id"], 1, (now + timedelta(days=1)).isoformat()))
        con.commit(); con.close()
        return jsonify({"ok": True, "text": "Hier kommt dein generierter Text ✨ (Demo)"})
    used, reset_at = row
    try:
        reset_dt = datetime.fromisoformat(reset_at) if reset_at else now
    except Exception:
        reset_dt = now
    if now > reset_dt:
        used = 0
        cur.execute("UPDATE usage_quota SET free_generated=?, free_reset_at=? WHERE user_id=?",
                    (0, (now + timedelta(days=1)).isoformat(), user["id"]))
    if used >= 3:
        con.commit(); con.close()
        return jsonify({"ok": False, "error": "paywall"}), 402
    cur.execute("UPDATE usage_quota SET free_generated=? WHERE user_id=?", (used+1, user["id"]))
    con.commit(); con.close()
    return jsonify({"ok": True, "text": "Hier kommt dein generierter Text ✨ (Demo)"})

@app.post("/webhooks/payhip")
def webhook_payhip():
    raw = request.data
    signature = request.headers.get("X-Payhip-Signature", "")
    secret = os.environ.get("PAYHIP_WEBHOOK_SECRET", "").encode()
    if not secret:
        return "missing secret", 400
    check = hmac.new(secret, raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, check):
        return "bad signature", 400

    event = json.loads(raw.decode("utf-8"))

    kind  = event.get("type", "")
    customer_email = event.get("customer", {}).get("email", "").lower()
    product_handle = (event.get("product", {}) or {}).get("handle", "")
    subscription = event.get("subscription", {}) or {}
    sub_id = subscription.get("id", "")
    cpe    = subscription.get("current_period_end", None)

    con = db(); cur = con.cursor()
    cur.execute("SELECT id FROM users WHERE email=?", (customer_email,))
    u = cur.fetchone()
    if not u:
        con.close()
        return "user not found", 200
    uid = u["id"]

    is_lifetime = (product_handle == "lifetime")
    status = "active" if kind in ("subscription.created", "subscription.renewed", "order.completed") else "canceled"

    cur.execute(
        "INSERT INTO subscriptions(user_id,plan,status,current_period_end,auto_renew,provider,provider_subscription_id,is_lifetime)          VALUES(?,?,?,?,?,?,?,?)",
        (uid, product_handle, status, cpe, 0 if is_lifetime else 1, "payhip", sub_id, 1 if is_lifetime else 0)
    )
    con.commit(); con.close()
    return "ok", 200

if __name__ == "__main__":
    app.run(debug=True)
