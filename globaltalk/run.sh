#!/bin/bash
# GlobalTalk — start the Flask development server
set -e

echo "🌐 Starting GlobalTalk..."

cd "$(dirname "$0")/backend"

if [ ! -d venv ]; then
  echo "❌ Virtual environment not found. Run ./setup.sh first."
  exit 1
fi

source venv/bin/activate

export FLASK_ENV=development

echo "🐍 Flask server → http://localhost:5000"
echo "   Press Ctrl+C to stop"
echo ""

python app.py
