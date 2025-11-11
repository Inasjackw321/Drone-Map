#!/usr/bin/env python3
import os
import json
import subprocess
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
DATA_FILE = 'drone_data.json'

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {'sightings': []}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    # Auto-commit to GitHub
    try:
        subprocess.run(['git', 'add', DATA_FILE], check=True)
        subprocess.run(['git', 'commit', '-m', f'Update drone data: {datetime.now().isoformat()}'], check=True)
        subprocess.run(['git', 'push'], check=True)
    except:
        pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '🛰️ Drone Tracker Bot\n\n'
        'Report drone sightings:\n'
        '/report <lat> <lon> <type> <description>\n\n'
        'Example:\n'
        '/report 50.45 30.52 Quadcopter Spotted near city center\n\n'
        'View all sightings:\n'
        '/list'
    )

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 4:
        await update.message.reply_text(
            '❌ Usage: /report <lat> <lon> <type> <description>\n'
            'Example: /report 50.45 30.52 Quadcopter Spotted near Kyiv'
        )
        return

    try:
        lat = float(context.args[0])
        lon = float(context.args[1])
        drone_type = context.args[2]
        description = ' '.join(context.args[3:])

        data = load_data()

        sighting = {
            'id': len(data['sightings']) + 1,
            'lat': lat,
            'lon': lon,
            'type': drone_type,
            'description': description,
            'timestamp': datetime.utcnow().isoformat(),
            'reporter': update.effective_user.username or 'anonymous',
            'threat': 'medium'
        }

        data['sightings'].append(sighting)
        save_data(data)

        await update.message.reply_text(
            f'✅ Drone sighting reported!\n\n'
            f'📍 Location: {lat}, {lon}\n'
            f'🛸 Type: {drone_type}\n'
            f'📝 {description}\n\n'
            f'View live map: https://inasjackw321.github.io/Drone-Map/'
        )
    except ValueError:
        await update.message.reply_text('❌ Invalid coordinates. Use numbers for lat/lon.')
    except Exception as e:
        await update.message.reply_text(f'❌ Error: {str(e)}')

async def list_sightings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    sightings = data['sightings'][-10:]

    if not sightings:
        await update.message.reply_text('No drone sightings reported yet.')
        return

    msg = '📋 Recent Drone Sightings:\n\n'
    for s in reversed(sightings):
        msg += f"🛸 {s['type']} - {s['description']}\n"
        msg += f"📍 {s['lat']}, {s['lon']}\n"
        msg += f"🕐 {s['timestamp']}\n\n"

    await update.message.reply_text(msg)

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('report', report))
    app.add_handler(CommandHandler('list', list_sightings))

    print('🤖 Drone Tracker Bot running...')
    app.run_polling()

if __name__ == '__main__':
    main()
