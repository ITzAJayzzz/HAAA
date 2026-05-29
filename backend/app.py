from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room  # type: ignore
from flask_cors import CORS  # type: ignore
from flask_limiter import Limiter  # type: ignore
from flask_limiter.util import get_remote_address  # type: ignore
import firebase_admin  # type: ignore
from firebase_admin import credentials, db as firebase_db  # type: ignore
import os
import hashlib
import string
import random
import time
import logging
import json
import re
from functools import wraps
from dotenv import load_dotenv  # type: ignore

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="../frontend", static_url_path="/")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "changeme-in-production")

CORS(app, resources={r"/api/*": {"origins": os.environ.get("ALLOWED_ORIGINS", "*")}})

socketio = SocketIO(
    app,
    cors_allowed_origins=os.environ.get("ALLOWED_ORIGINS", "*"),
    async_mode="threading",
    logger=False,
    engineio_logger=False,
)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per minute"],
    storage_uri=os.environ.get("REDIS_URL", "memory://"),
)

# ── Firebase init ──────────────────────────────────────────────────────────────
FIREBASE_DB_URL = os.environ.get(
    "FIREBASE_DB_URL",
    "https://global-chat-cfe60-default-rtdb.firebaseio.com",
)

_firebase_ready = False
try:
    cred_json = os.environ.get("FIREBASE_CRED_JSON")
    if cred_json:
        cred_dict = json.loads(cred_json)
        cred = credentials.Certificate(cred_dict)
    else:
        cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})
    _firebase_ready = True
    logger.info("Firebase Admin SDK initialised.")
except Exception as e:
    logger.warning(f"Firebase Admin SDK not initialised (running without it): {e}")

# ── Email config ───────────────────────────────────────────────────────────────
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
SENDER_NAME = os.environ.get("SENDER_NAME", "GlobalTalk")

# ── Helpers ────────────────────────────────────────────────────────────────────
SHORT_ID_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_EXPIRY_SECONDS = 600  # 10 minutes
REMEMBER_DEVICE_DAYS = 15


def gen_short_id(length: int = 6) -> str:
    return "GT-" + "".join(random.choices(SHORT_ID_CHARS, k=length))


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def gen_verification_code() -> str:
    return str(random.randint(100000, 999999))


def is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def send_email_code(to_email: str, code: str, purpose: str = "verification") -> bool:
    if not BREVO_API_KEY or not SENDER_EMAIL:
        logger.warning("Brevo credentials not configured")
        return False
    try:
        import http.client
        action = "complete your registration" if purpose == "register" else "log in to your account"
        html = f"""
        <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px;background:#0f0f1a;color:#fff;border-radius:12px;">
            <h2 style="color:#6c63ff;margin-bottom:8px;">GlobalTalk</h2>
            <p style="color:#aaa;margin-bottom:24px;">Your verification code to {action}:</p>
            <div style="background:#1a1a2e;border:2px solid #6c63ff;border-radius:10px;padding:24px;text-align:center;margin-bottom:24px;">
                <span style="font-size:40px;font-weight:bold;letter-spacing:12px;color:#fff;">{code}</span>
            </div>
            <p style="color:#aaa;font-size:13px;">This code expires in <strong style="color:#fff;">10 minutes</strong>.</p>
            <p style="color:#555;font-size:12px;margin-top:24px;">If you didn't request this, ignore this email.</p>
        </div>
        """
        payload = json.dumps({
            "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
            "to": [{"email": to_email}],
            "subject": f"GlobalTalk — Your {'verification' if purpose == 'register' else 'login'} code",
            "htmlContent": html
        }).encode("utf-8")
        conn = http.client.HTTPSConnection("api.brevo.com", timeout=10)
        conn.request("POST", "/v3/smtp/email", body=payload, headers={
            "api-key": BREVO_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
        resp = conn.getresponse()
        logger.info(f"Brevo response: {resp.status}")
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


def require_firebase(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not _firebase_ready:
            return jsonify({"error": "Firebase not configured on server"}), 503
        return f(*args, **kwargs)
    return wrapper


def fb_get(path: str):
    raw = firebase_db.reference(path).get()
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    return dict(raw)


def fb_get_or_empty(path: str) -> dict:
    return fb_get(path) or {}


# ── Health ─────────────────────────────────────────────────────────────────────
@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "firebase": _firebase_ready, "ts": int(time.time())})


# ── Auth: Send verification code ───────────────────────────────────────────────
@app.route("/api/auth/send-code", methods=["POST"])
@limiter.limit("5 per minute")
@require_firebase
def send_code():
    data: dict = request.get_json(silent=True) or {}
    purpose: str = data.get("purpose", "register")  # "register" or "login"
    email: str = data.get("email", "").strip().lower()
    username: str = data.get("username", "").strip().lower()

    if not email or not is_valid_email(email):
        return jsonify({"error": "Valid email required"}), 400

    if purpose == "register":
        if not username or len(username) < 2:
            return jsonify({"error": "Username required"}), 400
        existing = fb_get(f"users/{username}")
        if existing:
            return jsonify({"error": "Username already taken"}), 409
        email_exists = fb_get(f"email_index/{email.replace('.', ',')}")
        if email_exists:
            return jsonify({"error": "Email already registered"}), 409

    elif purpose == "login":
        if not username:
            return jsonify({"error": "Username required"}), 400
        user = fb_get(f"users/{username}")
        if not user:
            return jsonify({"error": "Account not found"}), 404
        if user.get("email", "").lower() != email:
            return jsonify({"error": "Email does not match account"}), 401

    code = gen_verification_code()
    expires_at = int(time.time()) + CODE_EXPIRY_SECONDS

    firebase_db.reference(f"verification_codes/{username}").set({
        "code": code,
        "email": email,
        "purpose": purpose,
        "expiresAt": expires_at,
    })

    import threading
    threading.Thread(target=send_email_code, args=(email, code, purpose), daemon=True).start()

    return jsonify({"message": "Code sent to email"}), 200


# ── Auth: Register ─────────────────────────────────────────────────────────────
@app.route("/api/auth/register", methods=["POST"])
@limiter.limit("10 per minute")
@require_firebase
def register():
    data: dict = request.get_json(silent=True) or {}
    username: str = data.get("username", "").strip()
    password: str = data.get("password", "")
    email: str = data.get("email", "").strip().lower()
    code: str = data.get("code", "").strip()
    lang: str = data.get("lang", "English")
    avatar_emoji: str = data.get("avatarEmoji", "😎")
    avatar_url = data.get("avatarUrl")

    if not username or len(username) < 2:
        return jsonify({"error": "Username must be at least 2 characters"}), 400
    if not all(c in string.ascii_letters + string.digits + "_-." for c in username):
        return jsonify({"error": "Invalid username characters"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if not email or not is_valid_email(email):
        return jsonify({"error": "Valid email required"}), 400
    if not code:
        return jsonify({"error": "Verification code required"}), 400

    stored = fb_get(f"verification_codes/{username.lower()}")
    if not stored:
        return jsonify({"error": "No verification code found. Request a new one."}), 400
    if stored.get("code") != code:
        return jsonify({"error": "Invalid verification code"}), 401
    if int(time.time()) > stored.get("expiresAt", 0):
        return jsonify({"error": "Code expired. Request a new one."}), 401
    if stored.get("purpose") != "register":
        return jsonify({"error": "Invalid code purpose"}), 400

    existing = fb_get(f"users/{username.lower()}")
    if existing:
        return jsonify({"error": "Username already taken"}), 409

    LANG_FLAGS = {
        "English": "🇺🇸", "Filipino": "🇵🇭", "Spanish": "🇪🇸",
        "Japanese": "🇯🇵", "French": "🇫🇷", "Arabic": "🇸🇦",
        "Hindi": "🇮🇳", "Korean": "🇰🇷", "Portuguese": "🇧🇷",
        "German": "🇩🇪", "Chinese": "🇨🇳", "Italian": "🇮🇹",
    }

    firebase_db.reference(f"users/{username.lower()}").set({
        "name": username,
        "email": email,
        "lang": lang,
        "flag": LANG_FLAGS.get(lang, "🌐"),
        "color": _string_to_color(username),
        "passHash": hash_password(password),
        "avatarEmoji": avatar_emoji,
        "avatarUrl": avatar_url,
        "createdAt": {".sv": "timestamp"},
    })

    firebase_db.reference(f"email_index/{email.replace('.', ',')}").set({"username": username.lower()})
    firebase_db.reference(f"verification_codes/{username.lower()}").delete()

    return jsonify({"message": "Account created"}), 201


# ── Auth: Login ────────────────────────────────────────────────────────────────
@app.route("/api/auth/login", methods=["POST"])
@limiter.limit("20 per minute")
@require_firebase
def login():
    data: dict = request.get_json(silent=True) or {}
    username: str = data.get("username", "").strip()
    password: str = data.get("password", "")
    code: str = data.get("code", "").strip()
    device_token: str = data.get("deviceToken", "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    user: dict = fb_get(f"users/{username.lower()}") or {}
    if not user:
        return jsonify({"error": "Account not found"}), 404
    if user.get("passHash") != hash_password(password):
        return jsonify({"error": "Wrong password"}), 401

    # Check remembered device
    if device_token:
        stored_token = fb_get(f"device_tokens/{username.lower()}/{_hash_token(device_token)}")
        if stored_token and int(time.time()) < stored_token.get("expiresAt", 0):
            return jsonify({
                "name": user.get("name", username),
                "lang": user.get("lang", "English"),
                "flag": user.get("flag", "🌐"),
                "color": user.get("color", "#6c63ff"),
                "avatarEmoji": user.get("avatarEmoji"),
                "avatarUrl": user.get("avatarUrl"),
                "dbKey": username.lower(),
                "requiresCode": False,
            })

    # No valid device token — need email code
    if not code:
        return jsonify({"requiresCode": True, "message": "Email verification required"}), 206

    stored = fb_get(f"verification_codes/{username.lower()}")
    if not stored:
        return jsonify({"error": "No verification code found. Request a new one."}), 400
    if stored.get("code") != code:
        return jsonify({"error": "Invalid verification code"}), 401
    if int(time.time()) > stored.get("expiresAt", 0):
        return jsonify({"error": "Code expired. Request a new one."}), 401
    if stored.get("purpose") != "login":
        return jsonify({"error": "Invalid code purpose"}), 400

    firebase_db.reference(f"verification_codes/{username.lower()}").delete()

    # Handle remember device
    new_device_token = None
    if data.get("rememberDevice"):
        new_device_token = _gen_device_token()
        expires_at = int(time.time()) + (REMEMBER_DEVICE_DAYS * 86400)
        firebase_db.reference(f"device_tokens/{username.lower()}/{_hash_token(new_device_token)}").set({
            "expiresAt": expires_at,
            "createdAt": {".sv": "timestamp"},
        })

    return jsonify({
        "name": user.get("name", username),
        "lang": user.get("lang", "English"),
        "flag": user.get("flag", "🌐"),
        "color": user.get("color", "#6c63ff"),
        "avatarEmoji": user.get("avatarEmoji"),
        "avatarUrl": user.get("avatarUrl"),
        "dbKey": username.lower(),
        "requiresCode": False,
        "deviceToken": new_device_token,
    })


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:32]


def _gen_device_token() -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=48))


# ── Rooms ──────────────────────────────────────────────────────────────────────
@app.route("/api/rooms", methods=["GET"])
@require_firebase
def list_rooms():
    rooms: dict = fb_get_or_empty("rooms")
    safe: dict = {}
    for rid, room in rooms.items():
        if not room or not isinstance(room, dict):
            continue
        r = dict(room)
        r.pop("passwordHash", None)
        r["isPrivate"] = bool(room.get("passwordHash"))
        safe[rid] = r
    return jsonify(safe)


@app.route("/api/rooms", methods=["POST"])
@limiter.limit("10 per minute")
@require_firebase
def create_room():
    data: dict = request.get_json(silent=True) or {}
    name: str = data.get("name", "").strip()
    icon: str = data.get("icon", "💬")
    password: str = data.get("password", "")
    permanent: bool = bool(data.get("permanent", False))
    admin_name: str = data.get("adminName", "")
    admin_color: str = data.get("adminColor", "#6c63ff")

    if not name:
        return jsonify({"error": "Room name required"}), 400
    if not admin_name:
        return jsonify({"error": "adminName required"}), 400

    short_id = gen_short_id()
    room_data = {
        "name": name,
        "icon": icon,
        "passwordHash": hash_password(password) if password else None,
        "adminName": admin_name,
        "adminColor": admin_color,
        "permanent": permanent,
        "shortId": short_id,
        "memberCount": 0,
        "createdAt": {".sv": "timestamp"},
    }
    ref = firebase_db.reference("rooms").push(room_data)
    return jsonify({"id": ref.key, "shortId": short_id}), 201


@app.route("/api/rooms/<room_id>", methods=["DELETE"])
@require_firebase
def delete_room(room_id: str):
    data: dict = request.get_json(silent=True) or {}
    requester: str = data.get("adminName", "")
    room: dict = fb_get(f"rooms/{room_id}") or {}
    if not room:
        return jsonify({"error": "Room not found"}), 404
    if room.get("adminName") != requester:
        return jsonify({"error": "Not authorized"}), 403
    firebase_db.reference(f"rooms/{room_id}").delete()
    return jsonify({"message": "Room deleted"})


@app.route("/api/rooms/join-private", methods=["POST"])
@require_firebase
def join_private():
    data: dict = request.get_json(silent=True) or {}
    short_id: str = data.get("shortId", "").strip().upper()
    password: str = data.get("password", "")

    if not short_id:
        return jsonify({"error": "Room ID required"}), 400

    rooms: dict = fb_get_or_empty("rooms")
    found_id = None
    found_room: dict = {}
    for rid, room in rooms.items():
        if isinstance(room, dict) and room.get("shortId") == short_id:
            found_id, found_room = rid, room
            break

    if not found_room:
        return jsonify({"error": "Room not found"}), 404
    if found_room.get("passwordHash") and found_room["passwordHash"] != hash_password(password):
        return jsonify({"error": "Wrong password"}), 401

    safe = dict(found_room)
    safe.pop("passwordHash", None)
    safe["id"] = found_id
    safe["isPrivate"] = bool(found_room.get("passwordHash"))
    return jsonify(safe)


# ── Translation proxy ──────────────────────────────────────────────────────────
@app.route("/api/translate", methods=["POST"])
@limiter.limit("60 per minute")
def translate():
    import urllib.request
    import urllib.parse
    import json as _json

    data: dict = request.get_json(silent=True) or {}
    text: str = data.get("text", "").strip()
    from_lang: str = data.get("from", "en")
    to_lang: str = data.get("to", "en")

    if not text:
        return jsonify({"error": "No text provided"}), 400
    if from_lang == to_lang:
        return jsonify({"translated": text})

    try:
        url = (
            "https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl={from_lang}&tl={to_lang}&dt=t&q={urllib.parse.quote(text)}"
        )
        with urllib.request.urlopen(url, timeout=5) as resp:
            result = _json.loads(resp.read())
        translated = "".join(s[0] for s in result[0] if s[0])
        return jsonify({"translated": translated})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Invites ────────────────────────────────────────────────────────────────────
@app.route("/api/invites", methods=["POST"])
@limiter.limit("30 per minute")
@require_firebase
def send_invite():
    data: dict = request.get_json(silent=True) or {}
    target_key: str = data.get("targetDbKey", "")
    room_id: str = data.get("roomId", "")
    room_name: str = data.get("roomName", "")
    room_icon: str = data.get("roomIcon", "💬")
    invited_by: str = data.get("invitedBy", "")
    invited_by_color: str = data.get("invitedByColor", "#6c63ff")

    if not target_key or not room_id:
        return jsonify({"error": "Missing fields"}), 400

    firebase_db.reference(f"invites/{target_key}/pending").push({
        "roomId": room_id,
        "roomName": room_name,
        "roomIcon": room_icon,
        "invitedBy": invited_by,
        "invitedByColor": invited_by_color,
        "preAuthorized": True,
        "timestamp": int(time.time() * 1000),
    })
    return jsonify({"message": "Invite sent"})


@app.route("/api/invites/poll", methods=["GET"])
@require_firebase
def poll_invites():
    user_key: str = request.args.get("user", "")
    since: int = int(request.args.get("since", 0))
    if not user_key:
        return jsonify([])

    pending: dict = fb_get_or_empty(f"invites/{user_key}/pending")
    results = []
    for key, inv in pending.items():
        if not isinstance(inv, dict):
            continue
        if inv.get("timestamp", 0) >= since:
            results.append({**inv, "_key": key})
            firebase_db.reference(f"invites/{user_key}/pending/{key}").delete()
    return jsonify(results)


# ── Users search ───────────────────────────────────────────────────────────────
@app.route("/api/users/search", methods=["GET"])
@require_firebase
def search_users():
    q: str = request.args.get("q", "").strip().lower()
    current: str = request.args.get("exclude", "")
    if not q:
        return jsonify([])

    all_users: dict = fb_get_or_empty("users")
    results = []
    for key, user in all_users.items():
        if not isinstance(user, dict) or key == current:
            continue
        if q in key or q in user.get("name", "").lower():
            results.append({
                "dbKey": key,
                "name": user.get("name"),
                "lang": user.get("lang"),
                "flag": user.get("flag"),
                "color": user.get("color"),
                "avatarEmoji": user.get("avatarEmoji"),
                "avatarUrl": user.get("avatarUrl"),
            })
        if len(results) >= 8:
            break
    return jsonify(results)


# ── Profile update ─────────────────────────────────────────────────────────────
@app.route("/api/users/<db_key>", methods=["PATCH"])
@require_firebase
def update_profile(db_key: str):
    data: dict = request.get_json(silent=True) or {}
    allowed = {"lang", "flag", "avatarEmoji", "avatarUrl"}
    update = {k: v for k, v in data.items() if k in allowed}
    if not update:
        return jsonify({"error": "Nothing to update"}), 400
    firebase_db.reference(f"users/{db_key}").update(update)
    return jsonify({"message": "Updated"})


# ── Socket.IO events ───────────────────────────────────────────────────────────
@socketio.on("connect")
def on_connect():
    logger.info(f"Client connected: {request.sid}")
    emit("connected", {"sid": request.sid})


@socketio.on("disconnect")
def on_disconnect():
    logger.info(f"Client disconnected: {request.sid}")


@socketio.on("join_room")
def on_join_room(data: dict):
    room_id: str = data.get("roomId", "global")
    user_name: str = data.get("userName", "Anonymous")
    join_room(room_id)
    emit("user_joined", {"user": user_name, "roomId": room_id}, to=room_id)


@socketio.on("leave_room")
def on_leave_room(data: dict):
    room_id: str = data.get("roomId", "global")
    user_name: str = data.get("userName", "Anonymous")
    leave_room(room_id)
    emit("user_left", {"user": user_name, "roomId": room_id}, to=room_id)


@socketio.on("new_message")
def on_new_message(data: dict):
    room_id: str = data.get("roomId", "global")
    emit("message_received", data, to=room_id, include_self=False)


@socketio.on("reaction")
def on_reaction(data: dict):
    room_id: str = data.get("roomId", "global")
    emit("reaction_update", data, to=room_id, include_self=False)


@socketio.on("typing")
def on_typing(data: dict):
    room_id: str = data.get("roomId", "global")
    emit("user_typing", data, to=room_id, include_self=False)


# ── Serve frontend ─────────────────────────────────────────────────────────────
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path: str):
    if path and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, "index.html")


# ── Util ───────────────────────────────────────────────────────────────────────
def _string_to_color(s: str) -> str:
    colors = [
        "#6c63ff", "#ff6584", "#43e97b", "#f7971e",
        "#2193b0", "#cc2b5e", "#42e695", "#667eea",
        "#f953c6", "#b91d73",
    ]
    h = 0
    for c in s:
        h = ord(c) + ((h << 5) - h)
    return colors[abs(h) % len(colors)]


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV", "production") == "development"
    socketio.run(app, host="0.0.0.0", port=port, debug=debug)