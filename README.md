# 🌐 GlobalTalk — Full Stack

Real-time multilingual chat app with email verification and auto-translation.

**Backend:** Python Flask + Flask-SocketIO  
**Frontend:** Vanilla HTML/CSS/JS  
**Database:** Firebase Realtime Database  
**Email:** Brevo API  
**Deployed:** Render (backend) + Vercel (frontend)  
**Infra (optional):** Terraform (AWS EC2)

---

## ✨ Features

- 🔐 Email verification on register and login
- 📱 Remember device for 15 days
- 💬 Real-time chat via Socket.IO
- 🌍 Auto-translation between 12 languages
- 🏠 Public and private password-protected rooms
- ⏱️ Temporary rooms auto-delete when empty
- 📨 Room invites between users
- 😀 Message reactions
- 🔒 Rate limiting and CORS protection

---

## 📁 Project Structure

```
globaltalk/
├── backend/
│   ├── app.py               ← Flask app (API + Socket.IO)
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── .env.example
│   └── serviceAccountKey.json  ← YOU ADD THIS (not committed)
├── frontend/
│   └── index.html           ← Single-page app
├── nginx/
│   └── nginx.conf
├── docker-compose.yml
├── setup.sh
├── run.sh
└── README.md
```

---

## 🚀 Live Deployment

| Service | Platform | URL |
|---------|----------|-----|
| Backend | Render | `https://haaa-anfb.onrender.com` |
| Frontend | Vercel | `https://gchatsss.vercel.app` |

---

## 🔑 Environment Variables

### Backend (Render)

| Key | Description |
|-----|-------------|
| `SECRET_KEY` | Flask secret key |
| `FIREBASE_DB_URL` | Firebase Realtime Database URL |
| `FIREBASE_CRED_JSON` | Firebase service account JSON (full contents) |
| `BREVO_API_KEY` | Brevo API key for sending emails |
| `SENDER_EMAIL` | Email address to send verification codes from |
| `SENDER_NAME` | Display name for sender (e.g. GlobalTalk) |
| `ALLOWED_ORIGINS` | Allowed CORS origins (your Vercel URL) |
| `FLASK_ENV` | `production` or `development` |

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Server health check |
| POST | `/api/auth/send-code` | Send email verification code |
| POST | `/api/auth/register` | Create account (requires email code) |
| POST | `/api/auth/login` | Sign in (requires email code if device not remembered) |
| GET | `/api/rooms` | List all rooms |
| POST | `/api/rooms` | Create a room |
| DELETE | `/api/rooms/:id` | Delete a room (admin only) |
| POST | `/api/rooms/join-private` | Join private room by short ID |
| POST | `/api/translate` | Translate text (Google Translate proxy) |
| POST | `/api/invites` | Send room invite to user |
| GET | `/api/invites/poll` | Poll for pending invites |
| GET | `/api/users/search?q=` | Search users |
| PATCH | `/api/users/:dbKey` | Update profile |

---

## 🌍 Supported Languages

English, Filipino, Spanish, Japanese, French, Arabic, Hindi, Korean, Portuguese, German, Chinese, Italian

---

## 🔒 Security

- Passwords are **SHA-256 hashed** before storage
- Email **verification codes** expire after 10 minutes
- **Device tokens** hashed before storing in Firebase
- **Rate limiting** on all auth and sensitive endpoints
- **CORS** restricted to Vercel frontend URL
- Firebase service account key stored as environment variable (never in code)

---

## ⚡ Socket.IO Events

| Event | Direction | Description |
|-------|-----------|-------------|
| `join_room` | Client → Server | Join a chat room |
| `leave_room` | Client → Server | Leave a chat room |
| `new_message` | Client → Server | Send a message |
| `reaction` | Client → Server | Add reaction to message |
| `typing` | Client → Server | Typing indicator |
| `user_joined` | Server → Client | User joined notification |
| `user_left` | Server → Client | User left notification |
| `message_received` | Server → Client | New message broadcast |
| `reaction_update` | Server → Client | Reaction update broadcast |
| `user_typing` | Server → Client | Typing indicator broadcast |

---

## 🛠️ Local Development

### 1. Clone the repo

```bash
git clone https://github.com/ITzAJayzzz/HAAA.git
cd HAAA
```

### 2. Install backend dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Add your Firebase key

```bash
cp ~/Downloads/your-key.json backend/serviceAccountKey.json
```

### 4. Configure environment

```bash
cp backend/.env.example backend/.env
# Edit backend/.env with your values
```

### 5. Run the server

```bash
cd backend
python app.py
# App runs at http://localhost:5000
```


## 📦 Tech Stack

| Technology | Purpose |
|------------|---------|
| Python Flask | Backend web framework |
| Flask-SocketIO | Real-time WebSocket events |
| Firebase Realtime DB | Stores users, rooms, messages |
| Firebase Admin SDK | Server-side Firebase access |
| Brevo API | Sends verification emails |
| Google Translate API | Free translation proxy |
| Gunicorn | Production WSGI server |
| Render | Backend hosting |
| Vercel | Frontend hosting |
