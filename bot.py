import os
import asyncio
import aiohttp
import json
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode
import logging

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Konfigurasi
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '0'))  # ID Telegram admin
PORT = int(os.environ.get('PORT', 8080))  # Port untuk Render.com

# Storage untuk user data (dalam production sebaiknya gunakan database)
user_emails = {}
user_domains = {}
custom_domains = set()

# API TempMail default
TEMPMAIL_API = "https://www.1secmail.com/api/v1/"

class TempMailBot:
    def __init__(self):
        self.session = None
    
    async def get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close_session(self):
        if self.session:
            await self.session.close()
    
    async def get_domains(self):
        """Ambil daftar domain yang tersedia"""
        try:
            session = await self.get_session()
            async with session.get(f"{TEMPMAIL_API}?action=getDomainList") as response:
                if response.status == 200:
                    domains = await response.json()
                    return list(set(domains + list(custom_domains)))
                return list(custom_domains) if custom_domains else ["1secmail.com"]
        except Exception as e:
            logger.error(f"Error getting domains: {e}")
            return list(custom_domains) if custom_domains else ["1secmail.com"]
    
    async def generate_email(self, domain=None):
        """Generate email baru"""
        import random
        import string
        
        username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        
        if domain is None:
            domains = await self.get_domains()
            domain = random.choice(domains) if domains else "1secmail.com"
        
        return f"{username}@{domain}"
    
    async def get_messages(self, email):
        """Ambil pesan dari email"""
        try:
            login, domain = email.split('@')
            session = await self.get_session()
            
            async with session.get(
                f"{TEMPMAIL_API}?action=getMessages&login={login}&domain={domain}"
            ) as response:
                if response.status == 200:
                    messages = await response.json()
                    return messages
                return []
        except Exception as e:
            logger.error(f"Error getting messages: {e}")
            return []
    
    async def read_message(self, email, message_id):
        """Baca detail pesan"""
        try:
            login, domain = email.split('@')
            session = await self.get_session()
            
            async with session.get(
                f"{TEMPMAIL_API}?action=readMessage&login={login}&domain={domain}&id={message_id}"
            ) as response:
                if response.status == 200:
                    message = await response.json()
                    return message
                return None
        except Exception as e:
            logger.error(f"Error reading message: {e}")
            return None

tempmail = TempMailBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start"""
    user = update.effective_user
    
    welcome_text = f"""
🌟 <b>Selamat Datang di TempMail Bot</b> 🌟

Halo {user.first_name}! 👋

Bot ini membantu Anda membuat email temporary untuk melindungi privasi Anda.

<b>📋 Fitur Utama:</b>
• 📧 Generate email temporary
• 📬 Cek inbox otomatis
• 🔄 Refresh email baru
• 🌐 Custom domain (Premium)
• 💾 History email
• ⏱ Auto-check setiap 30 detik

<b>🚀 Perintah:</b>
/new - Buat email baru
/inbox - Cek inbox
/refresh - Generate email baru
/domains - Lihat domain tersedia
/help - Bantuan lengkap

Mulai dengan /new untuk membuat email pertama Anda!
"""
    
    keyboard = [
        [InlineKeyboardButton("📧 Buat Email Baru", callback_data="new_email")],
        [InlineKeyboardButton("📖 Panduan", callback_data="help"),
         InlineKeyboardButton("🌐 Domain", callback_data="domains")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )

async def new_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buat email baru"""
    user_id = update.effective_user.id
    
    domains = await tempmail.get_domains()
    
    keyboard = []
    for i in range(0, len(domains), 2):
        row = []
        row.append(InlineKeyboardButton(
            f"📧 {domains[i]}", 
            callback_data=f"domain_{domains[i]}"
        ))
        if i + 1 < len(domains):
            row.append(InlineKeyboardButton(
                f"📧 {domains[i+1]}", 
                callback_data=f"domain_{domains[i+1]}"
            ))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🎲 Random", callback_data="domain_random")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = "🌐 <b>Pilih Domain untuk Email Anda:</b>"
    
    if update.callback_query:
        await update.callback_query.message.edit_text(
            message,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk inline button"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    if data == "new_email":
        await new_email(update, context)
    
    elif data.startswith("domain_"):
        domain = data.replace("domain_", "")
        
        if domain == "random":
            email = await tempmail.generate_email()
        else:
            email = await tempmail.generate_email(domain)
        
        user_emails[user_id] = email
        user_domains[user_id] = email.split('@')[1]
        
        keyboard = [
            [InlineKeyboardButton("📬 Cek Inbox", callback_data="check_inbox")],
            [InlineKeyboardButton("🔄 Email Baru", callback_data="new_email"),
             InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = f"""
✅ <b>Email Berhasil Dibuat!</b>

📧 <b>Email:</b> <code>{email}</code>

<i>Tap untuk copy email di atas</i>

Email ini akan menerima pesan dalam beberapa detik.
Gunakan tombol di bawah untuk mengecek inbox.
"""
        
        await query.message.edit_text(
            message,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
        
        # Auto-check inbox setelah 5 detik
        await asyncio.sleep(5)
        if user_id in user_emails:
            context.job_queue.run_once(
                check_inbox_job,
                0,
                data={'user_id': user_id, 'chat_id': query.message.chat_id}
            )
    
    elif data == "check_inbox":
        await check_inbox(update, context)
    
    elif data == "refresh_inbox":
        await query.message.edit_text("🔄 <i>Memuat ulang inbox...</i>", parse_mode=ParseMode.HTML)
        await asyncio.sleep(1)
        await check_inbox(update, context)
    
    elif data.startswith("read_"):
        message_id = data.replace("read_", "")
        await read_message_detail(update, context, int(message_id))
    
    elif data == "domains":
        await show_domains(update, context)
    
    elif data == "help":
        await help_command(update, context, from_callback=True)
    
    elif data == "main_menu":
        await start(update, context)
    
    elif data == "add_domain" and user_id == ADMIN_ID:
        await query.message.edit_text(
            "🌐 <b>Tambah Custom Domain</b>\n\n"
            "Kirim domain dalam format:\n"
            "<code>/adddomain example.com</code>",
            parse_mode=ParseMode.HTML
        )

async def check_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cek inbox email"""
    user_id = update.effective_user.id
    
    if user_id not in user_emails:
        keyboard = [[InlineKeyboardButton("📧 Buat Email", callback_data="new_email")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = "❌ Anda belum memiliki email aktif.\nBuat email terlebih dahulu!"
        
        if update.callback_query:
            await update.callback_query.message.edit_text(
                message,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(message, reply_markup=reply_markup)
        return
    
    email = user_emails[user_id]
    messages = await tempmail.get_messages(email)
    
    if not messages:
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_inbox")],
            [InlineKeyboardButton("📧 Email Baru", callback_data="new_email"),
             InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        inbox_text = f"""
📬 <b>Inbox Kosong</b>

📧 <b>Email Aktif:</b> <code>{email}</code>

<i>Belum ada pesan masuk. Inbox akan ter-update otomatis.</i>

⏰ Terakhir dicek: {datetime.now().strftime('%H:%M:%S')}
"""
        
        if update.callback_query:
            await update.callback_query.message.edit_text(
                inbox_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                inbox_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        return
    
    # Format pesan
    inbox_text = f"""
📬 <b>Inbox - {len(messages)} Pesan</b>

📧 <b>Email:</b> <code>{email}</code>

"""
    
    keyboard = []
    for msg in messages[:10]:  # Limit 10 pesan terbaru
        subject = msg.get('subject', 'No Subject')[:40]
        sender = msg.get('from', 'Unknown')
        date = msg.get('date', '')
        
        inbox_text += f"📨 <b>{subject}</b>\n"
        inbox_text += f"👤 {sender}\n"
        inbox_text += f"🕐 {date}\n\n"
        
        keyboard.append([
            InlineKeyboardButton(
                f"📖 {subject[:30]}...", 
                callback_data=f"read_{msg['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data="refresh_inbox")])
    keyboard.append([
        InlineKeyboardButton("📧 Email Baru", callback_data="new_email"),
        InlineKeyboardButton("🏠 Menu", callback_data="main_menu")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.message.edit_text(
            inbox_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            inbox_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

async def read_message_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int):
    """Baca detail pesan"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in user_emails:
        await query.message.edit_text("❌ Email tidak ditemukan!")
        return
    
    email = user_emails[user_id]
    message = await tempmail.read_message(email, message_id)
    
    if not message:
        await query.message.edit_text("❌ Pesan tidak dapat dimuat!")
        return
    
    subject = message.get('subject', 'No Subject')
    sender = message.get('from', 'Unknown')
    date = message.get('date', '')
    body = message.get('textBody', message.get('htmlBody', 'No content'))
    
    # Bersihkan HTML tags
    body = re.sub('<[^<]+?>', '', body)
    body = body[:1000]  # Limit 1000 karakter
    
    detail_text = f"""
📧 <b>{subject}</b>

👤 <b>Dari:</b> {sender}
🕐 <b>Tanggal:</b> {date}

📄 <b>Isi Pesan:</b>
{body}

<i>{'...(dipotong)' if len(body) >= 1000 else ''}</i>
"""
    
    keyboard = [
        [InlineKeyboardButton("⬅️ Kembali ke Inbox", callback_data="check_inbox")],
        [InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        detail_text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )

async def check_inbox_job(context: ContextTypes.DEFAULT_TYPE):
    """Background job untuk auto-check inbox"""
    data = context.job.data
    user_id = data['user_id']
    chat_id = data['chat_id']
    
    if user_id not in user_emails:
        return
    
    email = user_emails[user_id]
    messages = await tempmail.get_messages(email)
    
    if messages:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📬 <b>Pesan Baru!</b>\n\n"
                 f"Anda mendapat {len(messages)} pesan di <code>{email}</code>\n"
                 f"Gunakan /inbox untuk melihat.",
            parse_mode=ParseMode.HTML
        )

async def show_domains(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan daftar domain"""
    domains = await tempmail.get_domains()
    
    domain_text = "🌐 <b>Domain Tersedia</b>\n\n"
    
    for i, domain in enumerate(domains, 1):
        status = "⭐ Custom" if domain in custom_domains else "📧 Public"
        domain_text += f"{i}. {domain} {status}\n"
    
    keyboard = [
        [InlineKeyboardButton("📧 Buat Email", callback_data="new_email")],
        [InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]
    ]
    
    if update.effective_user.id == ADMIN_ID:
        keyboard.insert(0, [InlineKeyboardButton("➕ Tambah Domain", callback_data="add_domain")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.message.edit_text(
            domain_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            domain_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

async def add_domain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tambah custom domain (admin only)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Perintah ini hanya untuk admin!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Format salah!\n\n"
            "Gunakan: <code>/adddomain example.com</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    domain = context.args[0].lower()
    custom_domains.add(domain)
    
    await update.message.reply_text(
        f"✅ Domain <code>{domain}</code> berhasil ditambahkan!",
        parse_mode=ParseMode.HTML
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    """Tampilkan bantuan"""
    help_text = """
📖 <b>Panduan TempMail Bot</b>

<b>🎯 Cara Menggunakan:</b>
1. Gunakan /new untuk membuat email
2. Pilih domain yang diinginkan
3. Copy email yang dihasilkan
4. Gunakan email untuk registrasi
5. Cek /inbox untuk melihat pesan

<b>⚡ Perintah:</b>
/start - Mulai bot
/new - Buat email baru
/inbox - Cek inbox
/refresh - Generate email baru
/domains - Lihat domain
/help - Bantuan ini

<b>🔧 Fitur Admin:</b>
/adddomain - Tambah custom domain

<b>💡 Tips:</b>
• Email akan menerima pesan dalam hitungan detik
• Bot akan notifikasi jika ada pesan baru
• Email temporary biasanya aktif 1-2 jam
• Gunakan untuk verifikasi akun sementara

<b>⚠️ Perhatian:</b>
Email ini bersifat public dan temporary. Jangan gunakan untuk data sensitif!
"""
    
    keyboard = [[InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if from_callback:
        await update.callback_query.message.edit_text(
            help_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

async def inbox_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command untuk cek inbox"""
    await check_inbox(update, context)

async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command untuk generate email baru"""
    await new_email(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")

async def post_init(application: Application):
    """Setup setelah bot start"""
    await application.bot.set_my_commands([
        ("start", "Mulai bot"),
        ("new", "Buat email baru"),
        ("inbox", "Cek inbox"),
        ("refresh", "Email baru"),
        ("domains", "Lihat domain"),
        ("help", "Bantuan")
    ])

def main():
    """Main function"""
    # Buat application
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("new", new_email))
    application.add_handler(CommandHandler("inbox", inbox_command))
    application.add_handler(CommandHandler("refresh", refresh_command))
    application.add_handler(CommandHandler("domains", show_domains))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("adddomain", add_domain))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_error_handler(error_handler)
    
    # Start bot
    logger.info("🚀 Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
