# 🌐 GlobalTalk — Full Stack

Real-time multilingual chat app.  
**Backend:** Python Flask + Flask-SocketIO  
**Frontend:** Vanilla HTML/CSS/JS  
**Database:** Firebase Realtime Database  
**Infra:** Docker + Nginx + Terraform (AWS)

---

## Project Structure

```
globaltalk/
├── backend/
│   ├── app.py               ← Flask app (API + Socket.IO)
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── .env.example
│   └── serviceAccountKey.json  ← YOU ADD THIS
├── frontend/
│   └── index.html           ← Single-page app
├── nginx/
│   └── nginx.conf
├── terraform/
│   ├── main.tf              ← AWS EC2 infra
│   ├── variables.tf
│   ├── outputs.tf
│   └── user_data.sh.tpl
├── docker-compose.yml
├── setup.sh                 ← Local dev setup
├── run.sh                   ← Start dev server
└── README.md
```

---

## 🔑 Prerequisites

1. **Firebase project** — you need:
   - A Firebase Realtime Database enabled
   - A service account key (`serviceAccountKey.json`)
   - Download from: Firebase Console → Project Settings → Service Accounts → Generate new private key

2. **Python 3.10+**

---

## 🚀 Local Development

### 1. Install dependencies

```bash
chmod +x setup.sh run.sh
./setup.sh
```

This creates `backend/venv/` and installs all packages.

### 2. Add your Firebase key

```bash
# Copy your downloaded service account key
cp ~/Downloads/your-key.json backend/serviceAccountKey.json
```

### 3. Configure environment

```bash
# backend/.env is already created by setup.sh
# Edit if needed:
nano backend/.env
```

### 4. Run the server

```bash
./run.sh
# App runs at http://localhost:5000
```

### Fix VSCode import squiggles

Open VS Code **from the project root** so it picks up `.vscode/settings.json`:

```bash
code .
```

Then bottom-left of VSCode → click the Python version → select:
`backend/venv/bin/python`

The red underlines disappear immediately — they were just VSCode not knowing which Python environment to use.

---

## 🐳 Docker (local full-stack)

```bash
# Copy your Firebase key first
cp ~/Downloads/your-key.json backend/serviceAccountKey.json
cp backend/.env.example backend/.env

# Build and run
docker-compose up --build

# App runs at http://localhost:80
```

---

## ☁️ AWS Deployment (Terraform)

### Prerequisites
- AWS CLI configured (`aws configure`)
- Terraform installed (`brew install terraform` / `apt install terraform`)
- SSH key pair

### Deploy

```bash
cd terraform

# Initialize
terraform init

# Preview
terraform plan -var="ssh_public_key_path=~/.ssh/id_rsa.pub"

# Apply
terraform apply -var="ssh_public_key_path=~/.ssh/id_rsa.pub"
```

### Upload app to server

```bash
# Get server IP from Terraform output
SERVER_IP=$(terraform output -raw public_ip)

# Copy project files
scp -r ../backend ../frontend ../nginx ../docker-compose.yml ubuntu@$SERVER_IP:/opt/globaltalk/

# SSH in and start
ssh ubuntu@$SERVER_IP
cd /opt/globaltalk
cp backend/serviceAccountKey.json .  # upload your key first
docker-compose up -d
```

### Destroy

```bash
terraform destroy
```

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Server health check |
| POST | `/api/auth/register` | Create account |
| POST | `/api/auth/login` | Sign in |
| GET | `/api/rooms` | List all rooms |
| POST | `/api/rooms` | Create a room |
| DELETE | `/api/rooms/:id` | Delete a room (admin only) |
| POST | `/api/rooms/join-private` | Join private room by ID |
| POST | `/api/translate` | Translate text via proxy |
| POST | `/api/invites` | Send room invite |
| GET | `/api/users/search?q=` | Search users |
| PATCH | `/api/users/:dbKey` | Update profile |

---

## 🔒 Security Notes

- Passwords are SHA-256 hashed before storage
- Rate limiting on all auth and sensitive endpoints
- CORS restricted to `ALLOWED_ORIGINS` env var
- Firebase service account key is never exposed to the frontend
- SSH access in Terraform defaults to open — **set `ssh_allowed_cidr` to your IP** in production
