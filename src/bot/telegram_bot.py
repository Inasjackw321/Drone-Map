import sys
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from datetime import datetime, timedelta
import asyncio

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from database.models import DroneSighting, TelegramSubscriber, SessionLocal
from utils.data_ingestion import DroneDataIngestion
from utils.map_generator import MapGenerator

class DroneTelegramBot:
    def __init__(self):
        if not config.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN not set in environment variables")

        self.application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
        self.db = SessionLocal()
        self.data_ingestion = DroneDataIngestion()
        self.map_generator = MapGenerator()

        # Register command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("track", self.track_command))
        self.application.add_handler(CommandHandler("map", self.map_command))
        self.application.add_handler(CommandHandler("subscribe", self.subscribe_command))
        self.application.add_handler(CommandHandler("unsubscribe", self.unsubscribe_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("report", self.report_command))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /start command
        """
        welcome_message = """
🛰️ **Welcome to Drone Map - Europe & Ukraine Tracker**

This bot helps you track drone activity in Europe and Ukraine regions.

**Available Commands:**
/help - Show all commands
/track - Get recent drone sightings
/map - Get interactive map (last 24h)
/stats - View statistics
/subscribe - Subscribe to alerts
/unsubscribe - Unsubscribe from alerts
/report - Report a drone sighting

Stay informed about drone activity in your region! 🚁
        """
        await update.message.reply_text(welcome_message, parse_mode='Markdown')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /help command
        """
        help_text = """
📚 **Drone Map Bot - Help**

**Commands:**

🔍 **/track** [hours] - Get recent drone sightings
   Example: `/track 12` (last 12 hours)
   Default: last 24 hours

🗺️ **/map** [hours] - Get interactive map with drone locations
   Example: `/map 6` (last 6 hours)
   Default: last 24 hours

📊 **/stats** - View current statistics
   - Total sightings
   - Active alerts
   - Regional breakdown

🔔 **/subscribe** - Get real-time alerts
   Subscribe to notifications for new drone sightings

🔕 **/unsubscribe** - Stop receiving alerts

📝 **/report** <lat> <lon> <type> <description>
   Report a drone sighting
   Example: `/report 50.45 30.52 Quadcopter Hovering near building`

For more information, visit our documentation.
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def track_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /track command - show recent sightings
        """
        # Parse hours parameter
        hours = 24
        if context.args and len(context.args) > 0:
            try:
                hours = int(context.args[0])
                hours = min(hours, 168)  # Max 7 days
            except:
                pass

        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        sightings = self.db.query(DroneSighting).filter(
            DroneSighting.timestamp >= cutoff_time
        ).order_by(DroneSighting.timestamp.desc()).limit(10).all()

        if not sightings:
            await update.message.reply_text(
                f"No drone sightings in the last {hours} hours."
            )
            return

        message = f"🛸 **Recent Drone Sightings** (Last {hours}h)\n\n"

        for i, sighting in enumerate(sightings, 1):
            threat_emoji = {
                'low': '🟢',
                'medium': '🟡',
                'high': '🔴',
                'critical': '🔴🔴'
            }.get(sighting.threat_level, '⚪')

            time_ago = self.get_time_ago(sighting.timestamp)

            message += f"{i}. {threat_emoji} **{sighting.drone_type or 'Unknown'}**\n"
            message += f"   📍 {sighting.region or 'Unknown region'}\n"
            message += f"   🕐 {time_ago}\n"
            message += f"   ⬆️ {sighting.altitude or '?'}m | 🧭 {sighting.direction or '?'}\n"
            if sighting.verified:
                message += f"   ✅ Verified\n"
            message += "\n"

        await update.message.reply_text(message, parse_mode='Markdown')

    async def map_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /map command - generate and send map
        """
        await update.message.reply_text("🗺️ Generating map... Please wait.")

        # Parse hours parameter
        hours = 24
        if context.args and len(context.args) > 0:
            try:
                hours = int(context.args[0])
                hours = min(hours, 168)  # Max 7 days
            except:
                pass

        # Generate map
        map_file = f"static/maps/drone_map_{update.effective_chat.id}.html"
        os.makedirs("static/maps", exist_ok=True)

        try:
            self.map_generator.save_map(
                filename=map_file,
                hours=hours
            )

            # Send map file
            with open(map_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f'drone_map_{hours}h.html',
                    caption=f"🗺️ Drone activity map (last {hours} hours)\n\nDownload and open in your browser."
                )
        except Exception as e:
            await update.message.reply_text(
                f"❌ Error generating map: {str(e)}"
            )

    async def subscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /subscribe command
        """
        chat_id = update.effective_chat.id
        username = update.effective_user.username

        # Check if already subscribed
        subscriber = self.db.query(TelegramSubscriber).filter_by(chat_id=chat_id).first()

        if subscriber and subscriber.active:
            await update.message.reply_text(
                "✅ You are already subscribed to drone alerts!"
            )
            return

        if subscriber:
            subscriber.active = True
            self.db.commit()
        else:
            new_subscriber = TelegramSubscriber(
                chat_id=chat_id,
                username=username,
                active=True
            )
            self.db.add(new_subscriber)
            self.db.commit()

        await update.message.reply_text(
            "🔔 **Subscribed!**\n\n"
            "You will now receive real-time alerts about drone activity in Europe and Ukraine.\n\n"
            "Use /unsubscribe to stop receiving alerts."
        )

    async def unsubscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /unsubscribe command
        """
        chat_id = update.effective_chat.id

        subscriber = self.db.query(TelegramSubscriber).filter_by(chat_id=chat_id).first()

        if not subscriber or not subscriber.active:
            await update.message.reply_text(
                "❌ You are not currently subscribed."
            )
            return

        subscriber.active = False
        self.db.commit()

        await update.message.reply_text(
            "🔕 Unsubscribed from alerts.\n\n"
            "Use /subscribe to reactivate notifications."
        )

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /stats command
        """
        # Get statistics
        total_sightings = self.db.query(DroneSighting).count()
        last_24h = self.db.query(DroneSighting).filter(
            DroneSighting.timestamp >= datetime.utcnow() - timedelta(hours=24)
        ).count()
        verified_count = self.db.query(DroneSighting).filter_by(verified=True).count()
        critical_count = self.db.query(DroneSighting).filter_by(threat_level='critical').count()

        stats_message = f"""
📊 **Drone Tracking Statistics**

**Total Sightings:** {total_sightings}
**Last 24 Hours:** {last_24h}
**Verified Sightings:** {verified_count}
**Critical Threats:** {critical_count}

**Subscribers:** {self.db.query(TelegramSubscriber).filter_by(active=True).count()}

Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
        """

        await update.message.reply_text(stats_message, parse_mode='Markdown')

    async def report_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /report command - allow users to report sightings
        """
        if not context.args or len(context.args) < 4:
            await update.message.reply_text(
                "❌ Invalid format!\n\n"
                "**Usage:** /report <latitude> <longitude> <type> <description>\n\n"
                "**Example:**\n"
                "`/report 50.45 30.52 Quadcopter Spotted near Kyiv`"
            )
            return

        try:
            lat = float(context.args[0])
            lon = float(context.args[1])
            drone_type = context.args[2]
            description = ' '.join(context.args[3:])

            # Add sighting
            sighting = self.data_ingestion.add_sighting(
                latitude=lat,
                longitude=lon,
                drone_type=drone_type,
                description=description,
                source=f"telegram_user_{update.effective_user.id}",
                verified=False,
                threat_level="low"
            )

            if sighting:
                await update.message.reply_text(
                    "✅ **Sighting Reported!**\n\n"
                    "Thank you for your report. It will be reviewed and verified.\n\n"
                    f"📍 Location: {lat}, {lon}\n"
                    f"🛸 Type: {drone_type}\n"
                    f"📝 Description: {description}"
                )
            else:
                await update.message.reply_text(
                    "❌ Error saving report. Please try again."
                )

        except ValueError:
            await update.message.reply_text(
                "❌ Invalid coordinates! Latitude and longitude must be numbers."
            )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle button callbacks
        """
        query = update.callback_query
        await query.answer()

    def get_time_ago(self, timestamp):
        """
        Get human-readable time ago string
        """
        if not timestamp:
            return "Unknown"

        now = datetime.utcnow()
        diff = now - timestamp

        if diff.days > 0:
            return f"{diff.days}d ago"
        elif diff.seconds >= 3600:
            return f"{diff.seconds // 3600}h ago"
        elif diff.seconds >= 60:
            return f"{diff.seconds // 60}m ago"
        else:
            return "Just now"

    async def send_alert(self, sighting):
        """
        Send alert to all subscribers
        """
        subscribers = self.db.query(TelegramSubscriber).filter_by(active=True).all()

        threat_emoji = {
            'low': '🟢',
            'medium': '🟡',
            'high': '🔴',
            'critical': '🚨'
        }.get(sighting.threat_level, '⚪')

        alert_message = f"""
{threat_emoji} **DRONE ALERT** {threat_emoji}

**Type:** {sighting.drone_type or 'Unknown'}
**Region:** {sighting.region or 'Unknown'}
**Threat Level:** {sighting.threat_level.upper()}

📍 Location: {sighting.latitude}, {sighting.longitude}
⬆️ Altitude: {sighting.altitude or '?'}m
🧭 Direction: {sighting.direction or '?'}
💨 Speed: {sighting.speed or '?'} km/h

🕐 Detected: {sighting.timestamp.strftime('%H:%M:%S UTC')}

Use /track for more details.
        """

        for subscriber in subscribers:
            try:
                await self.application.bot.send_message(
                    chat_id=subscriber.chat_id,
                    text=alert_message,
                    parse_mode='Markdown'
                )
            except Exception as e:
                print(f"Error sending to {subscriber.chat_id}: {e}")

    def run(self):
        """
        Start the bot
        """
        print("🤖 Starting Drone Map Telegram Bot...")
        print(f"📡 Monitoring Europe and Ukraine regions")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

    def close(self):
        self.db.close()
        self.data_ingestion.close()
        self.map_generator.close()
