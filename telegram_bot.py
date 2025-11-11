#!/usr/bin/env python3
import os
import json
import subprocess
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DATA_FILE = 'drone_data.json'

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {'sightings': []}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    try:
        subprocess.run(['git', 'add', DATA_FILE], check=True)
        subprocess.run(['git', 'commit', '-m', f'Update: {datetime.now().isoformat()}'], check=True)
        subprocess.run(['git', 'push'], check=True)
    except:
        pass

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text('Usage: /report <lat> <lon> <type>')
        return

    try:
        data = load_data()
        data['sightings'].append({
            'lat': float(context.args[0]),
            'lon': float(context.args[1]),
            'type': context.args[2],
            'description': ' '.join(context.args[3:]) if len(context.args) > 3 else '',
            'timestamp': datetime.utcnow().isoformat(),
            'reporter': update.effective_user.username or 'anonymous'
        })
        save_data(data)
        await update.message.reply_text('✅ Reported')
    except:
        await update.message.reply_text('❌ Error')

def main():
    Application.builder().token(BOT_TOKEN).build().add_handler(CommandHandler('report', report)).run_polling()

if __name__ == '__main__':
    main()
