#!/bin/bash
# GlobalTalk — one-shot local setup
set -e

echo "🌐 GlobalTalk Setup"
echo "==================="

cd "$(dirname "$0")/backend"

# 1. Create virtual environment
echo ""
echo "📦 Creating Python virtual environment..."
python3 -m venv venv

# 2. Activate and install
echo "📥 Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

# 3. Copy .env if missing
if [ ! -f .env ]; then
  cp .env.example .env
  echo "⚙️  Created backend/.env — fill in your Firebase credentials"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Put your Firebase service account key at:  backend/serviceAccountKey.json"
echo "  2. Edit backend/.env if needed"
echo "  3. Run:  ./run.sh"
