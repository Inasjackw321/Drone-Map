#!/bin/bash

echo "======================================"
echo "🛰️  Drone Map Setup Script"
echo "======================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"

# Create virtual environment
echo ""
echo "📦 Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo ""
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env file and add your TELEGRAM_BOT_TOKEN"
else
    echo ""
    echo "✅ .env file already exists"
fi

# Initialize database
echo ""
echo "🗄️  Initializing database..."
python main.py --init-db

# Generate sample data
echo ""
read -p "Do you want to generate sample data? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    read -p "How many sample records to generate? (default: 20) " sample_count
    sample_count=${sample_count:-20}
    python main.py --generate-data $sample_count
    echo "✅ Generated $sample_count sample records"
fi

echo ""
echo "======================================"
echo "✅ Setup Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Edit .env file and add your Telegram Bot Token"
echo "2. Run: python main.py --start-bot"
echo "   OR"
echo "   Run: python web_server.py (for web interface)"
echo ""
echo "For more information, see README.md"
