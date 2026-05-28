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
    async_mode="eventlet",
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
FIREBASE_CRED_PATH = os.environ.get("FIREBASE_CRED_PATH", "serviceAccountKey.json")
FIREBASE_DB_URL = os.environ.get(
    "FIREBASE_DB_URL",
    "https://taskperformance1-ba66d781-default-rtdb.firebaseio.com",
)

_firebase_ready = False
try:
    cred = credentials.Certificate(FIREBASE_CRED_PATH)
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})
    _firebase_ready = True
    logger.info("Firebase Admin SDK initialised.")
except Exception as e:
    logger.warning(f"Firebase Admin SDK not initialised (running without it): {e}")

# ── Helpers ────────────────────────────────────────────────────────────────────
SHORT_ID_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def gen_short_id(length: int = 6) -> str:
    return "GT-" + "".join(random.choices(SHORT_ID_CHARS, k=length))


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def require_firebase(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not _firebase_ready:
            return jsonify({"error": "Firebase not configured on server"}), 503
        return f(*args, **kwargs)
    return wrapper


def fb_get(path: str):
    """Fetch a Firebase path and always return a plain dict or None."""
    raw = firebase_db.reference(path).get()
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    return dict(raw)  # fallback — should never happen for object nodes


def fb_get_or_empty(path: str) -> dict:
    return fb_get(path) or {}


# ── Health ─────────────────────────────────────────────────────────────────────
@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "firebase": _firebase_ready, "ts": int(time.time())})


# ── Auth ───────────────────────────────────────────────────────────────────────
@app.route("/api/auth/register", methods=["POST"])
@limiter.limit("10 per minute")
def register():
    data: dict = request.get_json(silent=True) or {}
    username: str = data.get("username", "").strip()
    password: str = data.get("password", "")
    lang: str = data.get("lang", "English")
    avatar_emoji: str = data.get("avatarEmoji", "😎")
    avatar_url = data.get("avatarUrl")

    if not username or len(username) < 2:
        return jsonify({"error": "Username must be at least 2 characters"}), 400
    if not all(c in string.ascii_letters + string.digits + "_-." for c in username):
        return jsonify({"error": "Invalid username characters"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    if not _firebase_ready:
        return jsonify({"error": "Firebase not configured"}), 503

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
        "lang": lang,
        "flag": LANG_FLAGS.get(lang, "🌐"),
        "color": _string_to_color(username),
        "passHash": hash_password(password),
        "avatarEmoji": avatar_emoji,
        "avatarUrl": avatar_url,
        "createdAt": {".sv": "timestamp"},
    })
    return jsonify({"message": "Account created"}), 201


@app.route("/api/auth/login", methods=["POST"])
@limiter.limit("20 per minute")
def login():
    data: dict = request.get_json(silent=True) or {}
    username: str = data.get("username", "").strip()
    password: str = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    if not _firebase_ready:
        return jsonify({"error": "Firebase not configured"}), 503

    user: dict = fb_get(f"users/{username.lower()}") or {}
    if not user:
        return jsonify({"error": "Account not found"}), 404
    if user.get("passHash") != hash_password(password):
        return jsonify({"error": "Wrong password"}), 401

    return jsonify({
        "name": user.get("name", username),
        "lang": user.get("lang", "English"),
        "flag": user.get("flag", "🌐"),
        "color": user.get("color", "#6c63ff"),
        "avatarEmoji": user.get("avatarEmoji"),
        "avatarUrl": user.get("avatarUrl"),
        "dbKey": username.lower(),
    })


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
            # consume it
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
