import subprocess
import sys
import os
import telebot
import json
import threading
import time
import random
import string
import re
import requests
import zipfile
import hashlib
import base64
import shutil
import psutil
import resource
from telebot import types
from datetime import datetime, timedelta
from html import escape
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes

required_modules = {
    'telebot': 'pyTelegramBotAPI',
    'requests': 'requests',
    'Crypto': 'pycryptodome',
    'psutil': 'psutil'
}
missing_packages = []
for module, package in required_modules.items():
    try:
        __import__(module)
    except ImportError:
        missing_packages.append(package)

if missing_packages:
    print(f"Installing missing packages: {missing_packages}")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing_packages)
        print("Installation successful. Please restart the script.")
        sys.exit(0)
    except subprocess.CalledProcessError as e:
        print(f"Installation failed: {e}")
        sys.exit(1)

TOKEN = '8942555911:AAFMmfhu27A0uJ4UWEnN0amVPAqywo9bPlM'
ADMIN_ID = 5563013498
HIDDEN_LONG = "ㅤ" * 50
bot = telebot.TeleBot(TOKEN, threaded=True, parse_mode="HTML")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUNNING_DIR = os.path.join(BASE_DIR, 'active_bots')
LOGS_DIR = os.path.join(BASE_DIR, 'bot_logs')
DB_DIR = os.path.join(BASE_DIR, 'database')
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
STORE_DIR = os.path.join(BASE_DIR, 'store_files')
THUMBS_DIR = os.path.join(ASSETS_DIR, 'thumbs')
MARKET_DIR = os.path.join(BASE_DIR, 'market')
ENV_DIR = os.path.join(BASE_DIR, 'bot_environments')
ENCRYPTED_DIR = os.path.join(BASE_DIR, 'encrypted_files')
TEMP_DIR = os.path.join(BASE_DIR, 'temp')

for d in [RUNNING_DIR, LOGS_DIR, DB_DIR, ASSETS_DIR, STORE_DIR, THUMBS_DIR, MARKET_DIR, ENV_DIR, ENCRYPTED_DIR, TEMP_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)

USERS_DB = os.path.join(DB_DIR, 'users.json')
FILES_DB = os.path.join(DB_DIR, 'files.json')
SETTINGS_DB = os.path.join(DB_DIR, 'settings.json')
STORE_DB = os.path.join(DB_DIR, 'store.json')
ADMINS_DB = os.path.join(DB_DIR, 'admins.json')
MARKET_DB = os.path.join(DB_DIR, 'market.json')
SECURITY_DB = os.path.join(DB_DIR, 'security.json')

db_lock = threading.Lock()
cancel_states = {}
last_bot_messages = {}
active_processes = {}
process_hours = {}
user_notifications = {}
process_resources = {}

RESOURCE_LIMITS = {
    'max_cpu_percent': 80,
    'max_memory_mb': 256,
    'max_disk_usage_mb': 100,
    'max_processes': 20,
    'max_log_size_mb': 5
}

def read_json(path):
    with db_lock:
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except:
            return {}

def write_json(path, data):
    with db_lock:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except:
            pass

class DatabaseManager:
    @staticmethod
    def get_users():
        return read_json(USERS_DB)

    @staticmethod
    def save_users(data):
        write_json(USERS_DB, data)

    @staticmethod
    def get_files():
        return read_json(FILES_DB)

    @staticmethod
    def save_files(data):
        write_json(FILES_DB, data)

    @staticmethod
    def get_settings():
        return read_json(SETTINGS_DB)

    @staticmethod
    def save_settings(data):
        write_json(SETTINGS_DB, data)

    @staticmethod
    def get_store():
        return read_json(STORE_DB)

    @staticmethod
    def save_store(data):
        write_json(STORE_DB, data)

    @staticmethod
    def get_admins():
        data = read_json(ADMINS_DB)
        return data.get("admins", [ADMIN_ID])

    @staticmethod
    def save_admins(data):
        write_json(ADMINS_DB, {"admins": data})

    @staticmethod
    def get_market():
        return read_json(MARKET_DB)

    @staticmethod
    def save_market(data):
        write_json(MARKET_DB, data)

    @staticmethod
    def get_security():
        return read_json(SECURITY_DB)

    @staticmethod
    def save_security(data):
        write_json(SECURITY_DB, data)

class EncryptionManager:
    @staticmethod
    def get_master_key():
        security = DatabaseManager.get_security()
        master_key = security.get('master_key')
        if not master_key:
            master_key = base64.b64encode(get_random_bytes(32)).decode('utf-8')
            security['master_key'] = master_key
            DatabaseManager.save_security(security)
        return base64.b64decode(master_key)

    @staticmethod
    def generate_file_key(fid, user_id):
        security = DatabaseManager.get_security()
        file_keys = security.get('file_keys', {})
        if fid not in file_keys:
            combined = f"{fid}:{user_id}:{ADMIN_ID}:{TOKEN}"
            salt = hashlib.sha256(combined.encode()).digest()[:16]
            master_key = EncryptionManager.get_master_key()
            kdf = hashlib.pbkdf2_hmac('sha256', master_key, salt, 100000, dklen=32)
            file_keys[fid] = {
                'key': base64.b64encode(kdf).decode('utf-8'),
                'salt': base64.b64encode(salt).decode('utf-8'),
                'user_id': user_id
            }
            security['file_keys'] = file_keys
            DatabaseManager.save_security(security)
        return file_keys[fid]

    @staticmethod
    def get_file_key(fid):
        security = DatabaseManager.get_security()
        return security.get('file_keys', {}).get(fid)

    @staticmethod
    def encrypt_content(content, fid, user_id):
        try:
            file_key_info = EncryptionManager.generate_file_key(fid, user_id)
            key = base64.b64decode(file_key_info['key'])
            salt = base64.b64decode(file_key_info['salt'])
            cipher = AES.new(key, AES.MODE_CBC)
            ct_bytes = cipher.encrypt(pad(content.encode('utf-8'), AES.block_size))
            encrypted_data = {
                'iv': base64.b64encode(cipher.iv).decode('utf-8'),
                'ciphertext': base64.b64encode(ct_bytes).decode('utf-8'),
                'salt': base64.b64encode(salt).decode('utf-8'),
                'fid': fid,
                'user_id': user_id,
                'timestamp': datetime.now().isoformat()
            }
            return json.dumps(encrypted_data)
        except Exception as e:
            print(f"Encryption error: {e}")
            return None

    @staticmethod
    def decrypt_content(encrypted_json, fid):
        try:
            data = json.loads(encrypted_json)
            file_key_info = EncryptionManager.get_file_key(fid)
            if not file_key_info:
                return None
            key = base64.b64decode(file_key_info['key'])
            iv = base64.b64decode(data['iv'])
            ct = base64.b64decode(data['ciphertext'])
            cipher = AES.new(key, AES.MODE_CBC, iv)
            pt = unpad(cipher.decrypt(ct), AES.block_size)
            return pt.decode('utf-8')
        except Exception as e:
            print(f"Decryption error: {e}")
            return None

    @staticmethod
    def save_encrypted_file(fid, content, user_id):
        encrypted_content = EncryptionManager.encrypt_content(content, fid, user_id)
        if encrypted_content:
            encrypted_path = os.path.join(ENCRYPTED_DIR, f"{fid}.enc")
            with open(encrypted_path, 'w', encoding='utf-8') as f:
                f.write(encrypted_content)
            return True
        return False

    @staticmethod
    def load_encrypted_file(fid):
        encrypted_path = os.path.join(ENCRYPTED_DIR, f"{fid}.enc")
        if os.path.exists(encrypted_path):
            with open(encrypted_path, 'r', encoding='utf-8') as f:
                encrypted_content = f.read()
            return EncryptionManager.decrypt_content(encrypted_content, fid)
        return None

class ProcessManager:
    @staticmethod
    def start_script(fid):
        files = DatabaseManager.get_files()
        if fid not in files:
            return False
        file_info = files[fid]
        user_id = file_info.get('user_id')
        if not Utilities.verify_file_access(fid, user_id):
            return False
        encrypted_content = EncryptionManager.load_encrypted_file(fid)
        if not encrypted_content:
            return False
        env_dir = os.path.join(ENV_DIR, fid)
        if not os.path.exists(env_dir):
            os.makedirs(env_dir)
        env_file_path = os.path.join(env_dir, f"{fid}.py")
        if fid in active_processes and active_processes[fid].poll() is None:
            return True
        if len(active_processes) >= RESOURCE_LIMITS['max_processes']:
            return False
        try:
            with open(env_file_path, 'w', encoding='utf-8') as f:
                f.write(encrypted_content)
        except:
            return False
        log_path = os.path.join(LOGS_DIR, f"{fid}.log")
        try:
            log_file = open(log_path, "a", encoding="utf-8")
            proc = subprocess.Popen(
                [sys.executable, "-u", env_file_path],
                stdout=log_file,
                stderr=log_file,
                stdin=subprocess.PIPE,
                cwd=env_dir,
                start_new_session=True,
                env={**os.environ, "PYTHONPATH": env_dir}
            )
            active_processes[fid] = proc
            process_resources[fid] = {
                'pid': proc.pid,
                'start_time': time.time(),
                'cpu_usage': 0,
                'memory_usage': 0
            }
            return True
        except:
            return False

    @staticmethod
    def stop_script(fid):
        if fid in active_processes:
            proc = active_processes[fid]
            try:
                os.killpg(os.getpgid(proc.pid), 9)
            except:
                try:
                    proc.terminate()
                except:
                    pass
            del active_processes[fid]
            if fid in process_hours:
                del process_hours[fid]
            if fid in process_resources:
                del process_resources[fid]
            return True
        return False

    @staticmethod
    def stop_all():
        for fid in list(active_processes.keys()):
            ProcessManager.stop_script(fid)
        return True

    @staticmethod
    def write_stdin(fid, cmd):
        if fid in active_processes and active_processes[fid].poll() is None:
            try:
                proc = active_processes[fid]
                if proc.stdin:
                    proc.stdin.write(cmd.encode('utf-8') + b'\n')
                    proc.stdin.flush()
                    return True
            except:
                pass
        return False

    @staticmethod
    def get_resource_usage(fid):
        if fid not in process_resources:
            return None
        try:
            proc = psutil.Process(process_resources[fid]['pid'])
            cpu = proc.cpu_percent(interval=0.1)
            mem = proc.memory_info().rss / (1024 * 1024)
            return {'cpu': cpu, 'memory': mem}
        except:
            return None

class Utilities:
    @staticmethod
    def gen_id(length=8):
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    @staticmethod
    def get_user_lang(user_id):
        users = DatabaseManager.get_users()
        u = users.get(str(user_id), {})
        return u.get('lang', 'en')

    @staticmethod
    def get_user_style(user_id):
        users = DatabaseManager.get_users()
        u = users.get(str(user_id), {})
        return u.get('button_style', 'default')

    @staticmethod
    def set_user_lang(user_id, lang):
        users = DatabaseManager.get_users()
        if str(user_id) in users:
            users[str(user_id)]['lang'] = lang
            DatabaseManager.save_users(users)

    @staticmethod
    def set_user_style(user_id, style):
        users = DatabaseManager.get_users()
        if str(user_id) in users:
            users[str(user_id)]['button_style'] = style
            DatabaseManager.save_users(users)

    @staticmethod
    def get_text(user_id, key, **kwargs):
        lang = Utilities.get_user_lang(user_id)
        text_dict = TRANSLATIONS.get(key, {})
        text = text_dict.get(lang, text_dict.get('en', key))
        if kwargs:
            text = text.format(**kwargs)
        return text

    @staticmethod
    def create_button(text, callback_data, user_id, style_override=None, url=None):
        style = style_override or Utilities.get_user_style(user_id) or 'default'
        if url:
            btn = types.InlineKeyboardButton(text=text, url=url)
        else:
            btn = types.InlineKeyboardButton(text=text, callback_data=callback_data)
        if style != 'default' and hasattr(btn, 'style'):
            btn.style = style
        return btn

    @staticmethod
    def format_border(user_id, title_key, content_key, **kwargs):
        title = Utilities.get_text(user_id, title_key, **kwargs)
        content = Utilities.get_text(user_id, content_key, **kwargs)
        settings = DatabaseManager.get_settings()
        name = settings.get('bot_name', 'Hosting Bot')
        return (f"┌─⊷『 {title} 』\n│\n├ {content}\n│\n└─⊷ <b>{name}</b>\n"
                f"<code>White Wolf t.me/j49_c</code>\n"
                f"<code>channel t.me/bshshshkk</code>\n{HIDDEN_LONG}")

    @staticmethod
    def delete_last_message(chat_id):
        if chat_id in last_bot_messages:
            try:
                bot.delete_message(chat_id, last_bot_messages[chat_id])
            except:
                pass

    @staticmethod
    def save_message(chat_id, msg_id):
        last_bot_messages[chat_id] = msg_id

    @staticmethod
    def send_message(chat_id, user_id, text, markup=None):
        Utilities.delete_last_message(chat_id)
        settings = DatabaseManager.get_settings()
        try:
            if settings.get('bot_image'):
                msg = bot.send_photo(chat_id, settings['bot_image'], caption=text, parse_mode="HTML", reply_markup=markup)
            else:
                msg = bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)
            Utilities.save_message(chat_id, msg.message_id)
            return msg
        except:
            msg = bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)
            Utilities.save_message(chat_id, msg.message_id)
            return msg

    @staticmethod
    def edit_message(call, user_id, text, markup):
        try:
            if call.message.content_type == 'photo':
                bot.edit_message_caption(text[:4096], call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
            else:
                bot.edit_message_text(text[:4096], call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
            Utilities.save_message(call.message.chat.id, call.message.message_id)
        except:
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            settings = DatabaseManager.get_settings()
            try:
                if settings.get('bot_image'):
                    msg = bot.send_photo(call.message.chat.id, settings['bot_image'], caption=text[:4096], parse_mode="HTML", reply_markup=markup)
                else:
                    msg = bot.send_message(call.message.chat.id, text[:4096], parse_mode="HTML", reply_markup=markup)
                Utilities.save_message(call.message.chat.id, msg.message_id)
            except:
                msg = bot.send_message(call.message.chat.id, text[:4096], parse_mode="HTML", reply_markup=markup)
                Utilities.save_message(call.message.chat.id, msg.message_id)

    @staticmethod
    def delete_messages(chat_id, *msg_ids):
        for msg_id in msg_ids:
            if msg_id:
                try:
                    bot.delete_message(chat_id, msg_id)
                except:
                    pass

    @staticmethod
    def is_user_pro(uid):
        if uid == ADMIN_ID or Utilities.is_admin(uid):
            return True
        users = DatabaseManager.get_users()
        u = users.get(str(uid), {})
        expiry = u.get('expiry')
        if not expiry or expiry == 'null':
            return False
        if expiry == 'LIFETIME' or expiry == 0:
            return True
        try:
            exp_date = datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")
            if datetime.now() < exp_date:
                return True
            else:
                u['expiry'] = None
                users[str(uid)] = u
                DatabaseManager.save_users(users)
                return False
        except:
            return False

    @staticmethod
    def check_subscription(user_id):
        if user_id == ADMIN_ID or Utilities.is_admin(user_id):
            return True
        settings = DatabaseManager.get_settings()
        channels = settings.get('channels', [])
        if not channels:
            return True
        try:
            for ch in channels:
                member = bot.get_chat_member(ch["username"], user_id)
                if member.status in ['left', 'kicked']:
                    return False
            return True
        except:
            return True

    @staticmethod
    def is_admin(user_id):
        if user_id == ADMIN_ID:
            return True
        admins = DatabaseManager.get_admins()
        return user_id in admins

    @staticmethod
    def is_main_admin(user_id):
        return user_id == ADMIN_ID

    @staticmethod
    def add_admin(user_id):
        admins = DatabaseManager.get_admins()
        if user_id not in admins:
            admins.append(user_id)
            DatabaseManager.save_admins(admins)
            return True
        return False

    @staticmethod
    def remove_admin(user_id):
        if user_id == ADMIN_ID:
            return False
        admins = DatabaseManager.get_admins()
        if user_id in admins:
            admins.remove(user_id)
            DatabaseManager.save_admins(admins)
            return True
        return False

    @staticmethod
    def get_thumb():
        settings = DatabaseManager.get_settings()
        thumb = settings.get('file_thumb')
        if thumb and os.path.exists(thumb):
            return thumb
        return None

    @staticmethod
    def verify_file_access(fid, user_id):
        files = DatabaseManager.get_files()
        if fid not in files:
            return False
        file_info = files[fid]
        file_user_id = file_info.get('user_id')
        if user_id == ADMIN_ID or Utilities.is_admin(user_id):
            return True
        if file_user_id == user_id:
            return True
        if file_info.get('type') == 'store':
            store = DatabaseManager.get_store()
            if fid in store:
                return True
        return False

    @staticmethod
    def get_logs(fid, lines=40):
        log_path = os.path.join(LOGS_DIR, f"{fid}.log")
        try:
            if os.path.exists(log_path) and os.path.getsize(log_path) > 0:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    all_lines = f.readlines()
                    last = all_lines[-lines:] if len(all_lines) > lines else all_lines
                    output = "".join(last)
                    safe = escape(output)
                    if len(safe) > 3000:
                        safe = safe[:3000] + "\n..."
                    return f"<pre><code>{safe}</code></pre>"
            return "No output available."
        except:
            return "Error reading logs."

    @staticmethod
    def update_token_in_memory(content, new_token):
        try:
            keywords = ["TOKEN", "bot_token", "api_key", "tok", "TKN", "BOT_TKN", "API_TOKEN"]
            pattern = r"(['\"])\d{8,12}:[a-zA-Z0-9_-]{35,}(['\"])"
            new_content = re.sub(pattern, f"\\1{new_token}\\2", content)
            for kw in keywords:
                kw_pattern = rf"{kw}\s*=\s*(['\"])[^'\"]+(['\"])"
                new_content = re.sub(kw_pattern, f"{kw} = \\1{new_token}\\2", new_content)
            return new_content
        except:
            return None

    @staticmethod
    def check_token(token):
        try:
            url = f"https://api.telegram.org/bot{token}/getMe"
            res = requests.get(url, timeout=15).json()
            if res.get("ok"):
                return True, res["result"]
            return False, res.get("description")
        except Exception as e:
            return False, str(e)

    @staticmethod
    def auto_fix_code(code):
        fixes = [
            (r'print\s+(\S+)', r'print(\1)'),
            (r'raw_input', 'input'),
            (r'xrange', 'range'),
            (r'\.iteritems\(\)', '.items()'),
            (r'\.itervalues\(\)', '.values()'),
            (r'\.iterkeys\(\)', '.keys()'),
        ]
        for pattern, replacement in fixes:
            code = re.sub(pattern, replacement, code)
        return code

    @staticmethod
    def create_zip(files_list, zip_name):
        zip_path = os.path.join(TEMP_DIR, zip_name)
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for file_path in files_list:
                if os.path.exists(file_path):
                    zipf.write(file_path, os.path.basename(file_path))
        return zip_path

    @staticmethod
    def set_cancel(uid, state=True):
        cancel_states[uid] = state

    @staticmethod
    def is_cancelled(uid):
        return cancel_states.get(uid, False)

    @staticmethod
    def clear_cancel(uid):
        if uid in cancel_states:
            del cancel_states[uid]

    @staticmethod
    def cleanup_temp_files():
        try:
            for f in os.listdir(TEMP_DIR):
                path = os.path.join(TEMP_DIR, f)
                if os.path.isfile(path):
                    os.remove(path)
        except:
            pass

    @staticmethod
    def cleanup_old_logs():
        try:
            now = time.time()
            for f in os.listdir(LOGS_DIR):
                path = os.path.join(LOGS_DIR, f)
                if os.path.isfile(path):
                    if os.path.getsize(path) > RESOURCE_LIMITS['max_log_size_mb'] * 1024 * 1024:
                        with open(path, 'w') as fp:
                            fp.truncate(0)
                    if now - os.path.getmtime(path) > 7 * 86400:
                        os.remove(path)
        except:
            pass

TRANSLATIONS = {
    'welcome': {
        'en': 'Welcome {name}!\n\nRank: {rank}\nPoints: {points}\nMember since: {date}',
        'ar': 'أهلاً {name}!\n\nالرتبة: {rank}\nالنقاط: {points}\nعضو منذ: {date}'
    },
    'main_menu_title': {'en': 'Main Menu', 'ar': 'القائمة الرئيسية'},
    'main_menu_rank': {'en': 'Rank: {rank}', 'ar': 'الرتبة: {rank}'},
    'main_menu_points': {'en': 'Points: {points}', 'ar': 'النقاط: {points}'},
    'upload': {'en': 'Upload New File', 'ar': 'رفع ملف جديد'},
    'my_files': {'en': 'My Files', 'ar': 'ملفاتي'},
    'store': {'en': 'Store', 'ar': 'المتجر'},
    'wallet': {'en': 'Wallet', 'ar': 'المحفظة'},
    'profile': {'en': 'Profile', 'ar': 'الملف الشخصي'},
    'install_library': {'en': 'Install Library', 'ar': 'تثبيت مكتبة'},
    'settings': {'en': 'Settings', 'ar': 'الإعدادات'},
    'contact_dev': {'en': 'Contact Developer', 'ar': 'تواصل مع المطور'},
    'admin_panel': {'en': 'Admin Panel', 'ar': 'لوحة الإدارة'},
    'pro_panel': {'en': 'Pro Panel', 'ar': 'لوحة Pro'},
    'download_all': {'en': 'Download All', 'ar': 'تحميل الكل'},
    'auto_fix': {'en': 'Auto Fix', 'ar': 'إصلاح تلقائي'},
    'test_run': {'en': 'Test Run', 'ar': 'تشغيل تجريبي'},
    'sell_store': {'en': 'Sell in Store', 'ar': 'بيع في المتجر'},
    'back': {'en': 'Back', 'ar': 'رجوع'},
    'cancel': {'en': 'Cancel', 'ar': 'إلغاء'},
    'bot_locked': {'en': 'Bot Locked', 'ar': 'البوت مغلق'},
    'bot_locked_desc': {'en': 'Service is temporarily paused.\nContact support via the button below.', 'ar': 'الخدمة موقفة مؤقتاً.\nتواصل مع الدعم عبر الزر أدناه.'},
    'subscription_required': {'en': 'Subscription Required', 'ar': 'اشتراك مطلوب'},
    'subscription_desc': {'en': 'Please join the following channels to continue:', 'ar': 'يرجى الاشتراك في القنوات التالية للمتابعة:'},
    'verify': {'en': 'Verify', 'ar': 'تحقق'},
    'join': {'en': 'Join {name}', 'ar': 'انضم {name}'},
    'language_selection': {'en': 'Select Language', 'ar': 'اختر اللغة'},
    'choose_lang': {'en': 'Please choose your preferred language:', 'ar': 'يرجى اختيار لغتك المفضلة:'},
    'english': {'en': 'English', 'ar': 'الإنجليزية'},
    'arabic': {'en': 'Arabic', 'ar': 'العربية'},
    'settings_title': {'en': 'Settings', 'ar': 'الإعدادات'},
    'change_lang': {'en': 'Change Language', 'ar': 'تغيير اللغة'},
    'change_style': {'en': 'Change Button Color', 'ar': 'تغيير لون الأزرار'},
    'style_default': {'en': 'Default', 'ar': 'افتراضي'},
    'style_primary': {'en': 'Blue (Primary)', 'ar': 'أزرق (رئيسي)'},
    'style_success': {'en': 'Green (Success)', 'ar': 'أخضر (نجاح)'},
    'style_danger': {'en': 'Red (Danger)', 'ar': 'أحمر (خطر)'},
    'style_updated': {'en': 'Button color updated.', 'ar': 'تم تحديث لون الأزرار.'},
    'lang_updated': {'en': 'Language updated.', 'ar': 'تم تحديث اللغة.'},
    'wallet_title': {'en': 'Wallet', 'ar': 'المحفظة'},
    'balance': {'en': 'Balance: {balance}', 'ar': 'الرصيد: {balance}'},
    'rank': {'en': 'Rank: {rank}', 'ar': 'الرتبة: {rank}'},
    'vip_expiry': {'en': 'VIP expiry: {expiry}', 'ar': 'صلاحية VIP: {expiry}'},
    'points_info': {'en': 'Each point = 1 hour of hosting.', 'ar': 'كل نقطة = ساعة استضافة.'},
    'daily_bonus': {'en': 'Daily Bonus', 'ar': 'المكافأة اليومية'},
    'referral_link': {'en': 'Referral Link', 'ar': 'رابط الإحالة'},
    'daily_claimed': {'en': 'Already claimed today!', 'ar': 'تم المطالبة اليوم!'},
    'daily_earned': {'en': 'You earned {points} points!', 'ar': 'لقد حصلت على {points} نقاط!'},
    'referral_text': {'en': 'Your referral link:\n<code>{link}</code>\n\nYou earn 10 points for each new user!', 'ar': 'رابط الإحالة الخاص بك:\n<code>{link}</code>\n\nتكسب 10 نقاط لكل مستخدم جديد!'},
    'help_title': {'en': 'Help', 'ar': 'المساعدة'},
    'help_text': {'en': 'Help Guide\n\nUpload a .py file and choose hosting type.\nFree hosting consumes points (1 point per hour).\nVIP hosting is unlimited.\n\nEarn points via daily bonus and referrals.\nManage your files from the "My Files" section.\nUse the terminal to interact with running bots.', 'ar': 'دليل المساعدة\n\nارفع ملف .py واختر نوع الاستضافة.\nالاستضافة المجانية تستهلك نقاط (نقطة لكل ساعة).\nاستضافة VIP غير محدودة.\n\nاحصل على نقاط عبر المكافأة اليومية والإحالات.\nأدر ملفاتك من قسم "ملفاتي".\nاستخدم الطرفية للتفاعل مع البوتات العاملة.'},
    'upload_choice': {'en': 'Choose hosting type:', 'ar': 'اختر نوع الاستضافة:'},
    'free_host': {'en': 'Free (points)', 'ar': 'مجاني (نقاط)'},
    'vip_host': {'en': 'VIP (unlimited)', 'ar': 'VIP (غير محدود)'},
    'send_file': {'en': 'Send your .py file:', 'ar': 'أرسل ملف .py الخاص بك:'},
    'invalid_file': {'en': 'Please send a .py file.', 'ar': 'يرجى إرسال ملف .py.'},
    'set_duration': {'en': 'Set Duration', 'ar': 'تحديد المدة'},
    'duration_prompt': {'en': 'File: <b>{name}</b>\n\nYour points: <code>{points}</code>\n\nEnter number of hours (max {max}):', 'ar': 'الملف: <b>{name}</b>\n\nنقاطك: <code>{points}</code>\n\nأدخل عدد الساعات (الحد الأقصى {max}):'},
    'invalid_number': {'en': 'Please enter a number.', 'ar': 'يرجى إدخال رقم.'},
    'min_hour': {'en': 'Minimum 1 hour.', 'ar': 'ساعة واحدة على الأقل.'},
    'insufficient_points': {'en': 'Required: {required}\nAvailable: {available}', 'ar': 'المطلوب: {required}\nالمتوفر: {available}'},
    'file_uploaded': {'en': 'File uploaded.\n\n{name}\n{type}\n{duration}\n\nWaiting for approval.', 'ar': 'تم رفع الملف.\n\n{name}\n{type}\n{duration}\n\nفي انتظار الموافقة.'},
    'file_accepted': {'en': 'File accepted automatically!\n\n{name}\n{duration}\nNow running.', 'ar': 'تم قبول الملف تلقائياً!\n\n{name}\n{duration}\nيعمل الآن.'},
    'file_approved': {'en': 'Your file has been approved!\n\n{name}\n{duration}\nNow running.', 'ar': 'تمت الموافقة على ملفك!\n\n{name}\n{duration}\nيعمل الآن.'},
    'file_rejected': {'en': 'Your file \'{name}\' has been rejected.', 'ar': 'تم رفض ملفك \'{name}\'.'},
    'my_files_title': {'en': 'My Files', 'ar': 'ملفاتي'},
    'files_count': {'en': 'Files: {count}', 'ar': 'الملفات: {count}'},
    'running_count': {'en': 'Running: {count}', 'ar': 'يعمل: {count}'},
    'stopped_count': {'en': 'Stopped: {count}', 'ar': 'متوقف: {count}'},
    'no_files': {'en': 'No files.', 'ar': 'لا توجد ملفات.'},
    'file_manager': {'en': 'File Manager', 'ar': 'إدارة الملف'},
    'file_status': {'en': 'Status: {status}', 'ar': 'الحالة: {status}'},
    'file_remaining': {'en': 'Remaining: {remaining}', 'ar': 'المتبقي: {remaining}'},
    'file_type': {'en': 'Type: {type}', 'ar': 'النوع: {type}'},
    'file_created': {'en': 'Created: {created}', 'ar': 'تاريخ الإنشاء: {created}'},
    'start': {'en': 'Start', 'ar': 'تشغيل'},
    'stop': {'en': 'Stop', 'ar': 'إيقاف'},
    'terminal': {'en': 'Terminal', 'ar': 'الطرفية'},
    'change_token': {'en': 'Change Token', 'ar': 'تغيير التوكن'},
    'token_info': {'en': 'Token Info', 'ar': 'معلومات التوكن'},
    'download': {'en': 'Download', 'ar': 'تحميل'},
    'delete': {'en': 'Delete', 'ar': 'حذف'},
    'confirm_delete': {'en': 'Are you sure you want to delete this file?', 'ar': 'هل أنت متأكد من حذف هذا الملف؟'},
    'yes': {'en': 'Yes', 'ar': 'نعم'},
    'no': {'en': 'No', 'ar': 'لا'},
    'deleted': {'en': 'Deleted: {name}', 'ar': 'تم الحذف: {name}'},
    'terminal_title': {'en': 'Terminal', 'ar': 'الطرفية'},
    'terminal_output': {'en': 'File: {name}\nStatus: {status}\n\nTerminal:\n{output}', 'ar': 'الملف: {name}\nالحالة: {status}\n\nالطرفية:\n{output}'},
    'refresh': {'en': 'Refresh', 'ar': 'تحديث'},
    'input': {'en': 'Input', 'ar': 'إدخال'},
    'input_sent': {'en': 'Sent: <code>{cmd}</code>', 'ar': 'تم الإرسال: <code>{cmd}</code>'},
    'process_not_running': {'en': 'Process not running.', 'ar': 'العملية لا تعمل.'},
    'token_updated': {'en': 'Token updated. Please restart the file.', 'ar': 'تم تحديث التوكن. يرجى إعادة تشغيل الملف.'},
    'token_failed': {'en': 'Failed to update token.', 'ar': 'فشل تحديث التوكن.'},
    'token_valid': {'en': 'Token is valid.', 'ar': 'التوكن صالح.'},
    'token_invalid': {'en': 'Token is invalid.', 'ar': 'التوكن غير صالح.'},
    'no_token': {'en': 'No token found.', 'ar': 'لم يتم العثور على توكن.'},
    'bot_name': {'en': 'Bot name: {name}', 'ar': 'اسم البوت: {name}'},
    'bot_image': {'en': 'Bot image: {state}', 'ar': 'صورة البوت: {state}'},
    'file_thumb': {'en': 'File thumbnail: {state}', 'ar': 'صورة مصغرة للملف: {state}'},
    'auto_approve': {'en': 'Auto-approve: {state}', 'ar': 'موافقة تلقائية: {state}'},
    'enabled': {'en': 'Enabled', 'ar': 'مفعل'},
    'disabled': {'en': 'Disabled', 'ar': 'معطل'},
    'change_name': {'en': 'Change Name', 'ar': 'تغيير الاسم'},
    'change_image': {'en': 'Change Image', 'ar': 'تغيير الصورة'},
    'remove_image': {'en': 'Remove Image', 'ar': 'إزالة الصورة'},
    'add_image': {'en': 'Add Image', 'ar': 'إضافة صورة'},
    'change_thumb': {'en': 'Change Thumbnail', 'ar': 'تغيير الصورة المصغرة'},
    'remove_thumb': {'en': 'Remove Thumbnail', 'ar': 'إزالة الصورة المصغرة'},
    'add_thumb': {'en': 'Add Thumbnail', 'ar': 'إضافة صورة مصغرة'},
    'name_set': {'en': 'Name set to: {name}', 'ar': 'تم تعيين الاسم: {name}'},
    'image_updated': {'en': 'Image updated.', 'ar': 'تم تحديث الصورة.'},
    'thumb_updated': {'en': 'Thumbnail updated.', 'ar': 'تم تحديث الصورة المصغرة.'},
    'admin_panel_title': {'en': 'Admin Panel', 'ar': 'لوحة الإدارة'},
    'admin_stats': {'en': 'Users: {users}\nFiles: {files}\nPending: {pending}\nActive: {active}\nAdmins: {admins}\n\nBot state: {state}\nAuto-approve: {auto}', 'ar': 'المستخدمين: {users}\nالملفات: {files}\nالمعلقة: {pending}\nالنشطة: {active}\nالأدمن: {admins}\n\nحالة البوت: {state}\nالموافقة التلقائية: {auto}'},
    'unlock': {'en': 'Unlock', 'ar': 'فتح'},
    'lock': {'en': 'Lock', 'ar': 'قفل'},
    'auto_approve_toggle': {'en': 'Auto-approve', 'ar': 'موافقة تلقائية'},
    'manual_approve': {'en': 'Manual approve', 'ar': 'موافقة يدوية'},
    'users_list': {'en': 'Users', 'ar': 'المستخدمين'},
    'admins_list': {'en': 'Admins', 'ar': 'الأدمن'},
    'store_management': {'en': 'Store Management', 'ar': 'إدارة المتجر'},
    'pending_files': {'en': 'Pending Files', 'ar': 'الملفات المعلقة'},
    'broadcast': {'en': 'Broadcast', 'ar': 'إذاعة'},
    'channels': {'en': 'Channels', 'ar': 'القنوات'},
    'all_files': {'en': 'All Files', 'ar': 'جميع الملفات'},
    'stop_all': {'en': 'Stop All', 'ar': 'إيقاف الكل'},
    'pending_count': {'en': 'Pending: {count}', 'ar': 'المعلقة: {count}'},
    'file_review': {'en': 'Review', 'ar': 'مراجعة'},
    'file_owner': {'en': 'Owner: {owner}', 'ar': 'المالك: {owner}'},
    'approve': {'en': 'Approve', 'ar': 'قبول'},
    'reject': {'en': 'Reject', 'ar': 'رفض'},
    'user_management': {'en': 'User Management', 'ar': 'إدارة المستخدم'},
    'user_id': {'en': 'ID: {id}', 'ar': 'المعرف: {id}'},
    'user_username': {'en': 'Username: @{username}', 'ar': 'اسم المستخدم: @{username}'},
    'user_joined': {'en': 'Joined: {date}', 'ar': 'انضم: {date}'},
    'user_points': {'en': 'Points: {points}', 'ar': 'النقاط: {points}'},
    'user_rank': {'en': 'Rank: {rank}', 'ar': 'الرتبة: {rank}'},
    'user_expiry': {'en': 'VIP expiry: {expiry}', 'ar': 'صلاحية VIP: {expiry}'},
    'user_files': {'en': 'Files: {files}', 'ar': 'الملفات: {files}'},
    'user_status': {'en': 'Status: {status}', 'ar': 'الحالة: {status}'},
    'active': {'en': 'Active', 'ar': 'نشط'},
    'banned': {'en': 'Banned', 'ar': 'محظور'},
    'ban': {'en': 'Ban', 'ar': 'حظر'},
    'unban': {'en': 'Unban', 'ar': 'فك الحظر'},
    'grant_vip': {'en': 'Grant VIP', 'ar': 'منح VIP'},
    'remove_vip': {'en': 'Remove VIP', 'ar': 'إزالة VIP'},
    'charge': {'en': 'Charge', 'ar': 'شحن'},
    'message_user': {'en': 'Message', 'ar': 'رسالة'},
    'charge_points': {'en': 'Enter points to add:', 'ar': 'أدخل النقاط للإضافة:'},
    'charge_success': {'en': 'Added {amount} points.', 'ar': 'تم إضافة {amount} نقاط.'},
    'message_sent': {'en': 'Message sent.', 'ar': 'تم إرسال الرسالة.'},
    'grant_vip_prompt': {'en': 'Enter days (0 for lifetime):', 'ar': 'أدخل عدد الأيام (0 مدى الحياة):'},
    'grant_vip_success': {'en': 'VIP granted for {duration}.', 'ar': 'تم منح VIP لمدة {duration}.'},
    'remove_vip_success': {'en': 'VIP removed.', 'ar': 'تم إزالة VIP.'},
    'add_admin': {'en': 'Add Admin', 'ar': 'إضافة أدمن'},
    'add_admin_prompt': {'en': 'Enter the user ID:', 'ar': 'أدخل معرف المستخدم:'},
    'admin_added': {'en': 'Admin added: {id}', 'ar': 'تم إضافة الأدمن: {id}'},
    'admin_exists': {'en': 'User is already an admin.', 'ar': 'المستخدم أدمن بالفعل.'},
    'admin_removed': {'en': 'Admin removed.', 'ar': 'تم إزالة الأدمن.'},
    'cannot_remove_owner': {'en': 'Cannot remove the main owner!', 'ar': 'لا يمكن إزالة المالك الرئيسي!'},
    'only_owner': {'en': 'Only the main owner can do this.', 'ar': 'فقط المالك الرئيسي يمكنه فعل هذا.'},
    'store_item': {'en': 'File: {name}\nPrice: {price}', 'ar': 'الملف: {name}\nالسعر: {price}'},
    'add_store_file': {'en': 'Add Store File', 'ar': 'إضافة ملف للمتجر'},
    'set_price': {'en': 'Set Price', 'ar': 'تحديد السعر'},
    'price_prompt': {'en': 'Enter price in points:', 'ar': 'أدخل السعر بالنقاط:'},
    'store_added': {'en': 'Added: {name}\nPrice: {price}', 'ar': 'تم الإضافة: {name}\nالسعر: {price}'},
    'price_updated': {'en': 'Price updated to {price}.', 'ar': 'تم تحديث السعر إلى {price}.'},
    'store_deleted': {'en': 'Deleted: {name}', 'ar': 'تم الحذف: {name}'},
    'broadcast_sending': {'en': 'Sending to {count} users...', 'ar': 'جاري الإرسال لـ {count} مستخدم...'},
    'broadcast_complete': {'en': 'Broadcast complete.\n\nSuccessful: {success}\nFailed: {failed}\nTotal: {total}', 'ar': 'اكتملت الإذاعة.\n\nنجح: {success}\nفشل: {failed}\nالإجمالي: {total}'},
    'channels_list': {'en': 'Channels: {count}', 'ar': 'القنوات: {count}'},
    'add_channel': {'en': 'Add Channel', 'ar': 'إضافة قناة'},
    'add_channel_prompt': {'en': 'Send the channel username (e.g., @channel):', 'ar': 'أرسل معرف القناة (مثال: @channel):'},
    'channel_added': {'en': 'Added: {name}', 'ar': 'تم الإضافة: {name}'},
    'channel_not_found': {'en': 'Channel not found.', 'ar': 'القناة غير موجودة.'},
    'channel_removed': {'en': 'Removed: {name}', 'ar': 'تم الإزالة: {name}'},
    'library_install': {'en': 'Installing library: {lib}', 'ar': 'جاري تثبيت المكتبة: {lib}'},
    'library_installed': {'en': 'Installed: {lib}', 'ar': 'تم التثبيت: {lib}'},
    'library_timeout': {'en': 'Timeout: {lib}', 'ar': 'انتهت المهلة: {lib}'},
    'library_failed': {'en': 'Failed: {lib}', 'ar': 'فشل: {lib}'},
    'edit_store': {'en': 'Edit Store Item', 'ar': 'تعديل عنصر المتجر'},
    'change_price': {'en': 'Change Price', 'ar': 'تغيير السعر'},
    'buy': {'en': 'Buy', 'ar': 'شراء'},
    'buy_confirm_text': {'en': 'File: {name}\nPrice: {price}\nYour balance: <code>{balance}</code>\n\n{status}', 'ar': 'الملف: {name}\nالسعر: {price}\nرصيدك: <code>{balance}</code>\n\n{status}'},
    'sufficient': {'en': 'Sufficient points!', 'ar': 'نقاط كافية!'},
    'insufficient': {'en': 'Insufficient points!', 'ar': 'نقاط غير كافية!'},
    'purchase_success': {'en': 'Purchase successful!', 'ar': 'تم الشراء بنجاح!'},
    'purchase_failed': {'en': 'Purchase failed.', 'ar': 'فشل الشراء.'},
    'store_empty': {'en': 'Store is empty.', 'ar': 'المتجر فارغ.'},
    'test_run_select': {'en': 'Select a file to test:', 'ar': 'اختر ملفاً للتشغيل التجريبي:'},
    'test_run_success': {'en': 'Test run successful!', 'ar': 'تم التشغيل التجريبي بنجاح!'},
    'test_run_error': {'en': 'Error: {error}', 'ar': 'خطأ: {error}'},
    'access_denied': {'en': 'Access denied!', 'ar': 'ممنوع الوصول!'},
    'file_not_found': {'en': 'File not found!', 'ar': 'الملف غير موجود!'},
    'download_failed': {'en': 'Download failed!', 'ar': 'فشل التحميل!'},
    'no_files_to_download': {'en': 'No files to download!', 'ar': 'لا توجد ملفات للتحميل!'},
    'vip_only': {'en': 'VIP only!', 'ar': 'VIP فقط!'},
    'insufficient_points_short': {'en': 'Insufficient points!', 'ar': 'نقاط غير كافية!'},
    'file_saved': {'en': 'File saved successfully.', 'ar': 'تم حفظ الملف بنجاح.'},
    'save_failed': {'en': 'Failed to save file.', 'ar': 'فشل حفظ الملف.'},
    'new_user_notify': {'en': 'New user registered!\n\nName: {name}\nID: <code>{id}</code>\nUsername: {username}\nDate: {date}', 'ar': 'مستخدم جديد!\n\nالاسم: {name}\nالمعرف: <code>{id}</code>\nاسم المستخدم: {username}\nالتاريخ: {date}'},
    'user_banned_notify': {'en': 'You have been banned.', 'ar': 'لقد تم حظرك.'},
    'user_unbanned_notify': {'en': 'Your ban has been lifted.', 'ar': 'تم رفع الحظر عنك.'},
    'vip_granted_notify': {'en': 'You have been upgraded to VIP for {duration}.', 'ar': 'تم ترقيتك إلى VIP لمدة {duration}.'},
    'vip_removed_notify': {'en': 'Your VIP status has been removed.', 'ar': 'تم إلغاء صلاحية VIP الخاصة بك.'},
    'points_added_notify': {'en': '<b>{amount}</b> points have been added to your balance.', 'ar': 'تم إضافة <b>{amount}</b> نقاط إلى رصيدك.'},
    'admin_promoted_notify': {'en': 'You have been made an admin!', 'ar': 'لقد تم تعيينك أدمن!'},
    'file_upload_notify': {'en': 'New file upload\n\nUser: {user}\nID: <code>{id}</code>\nFile: {file}\nType: {type}\nDuration: {duration}', 'ar': 'رفع ملف جديد\n\nالمستخدم: {user}\nالمعرف: <code>{id}</code>\nالملف: {file}\nالنوع: {type}\nالمدة: {duration}'},
    'time_expired_notify': {'en': 'Your bot \'{name}\' has reached its time limit.', 'ar': 'انتهت مدة البوت \'{name}\'.'},
    'stopped_subscription_notify': {'en': 'Your bot \'{name}\' was stopped due to missing subscription.', 'ar': 'تم إيقاف البوت \'{name}\' بسبب عدم الاشتراك.'},
    'resource_limit_notify': {'en': 'Your bot \'{name}\' was stopped due to exceeding resource limits.', 'ar': 'تم إيقاف البوت \'{name}\' بسبب تجاوز حدود الموارد.'},
    'system_usage': {'en': 'System Usage:\nCPU: {cpu}%\nMemory: {mem_mb} MB\nActive processes: {processes}', 'ar': 'استخدام النظام:\nCPU: {cpu}%\nالذاكرة: {mem_mb} ميجابايت\nالعمليات النشطة: {processes}'},
    'not_subscribed': {'en': 'You are not subscribed.', 'ar': 'أنت غير مشترك.'},
    'subscribe_first': {'en': 'Please subscribe first.', 'ar': 'يرجى الاشتراك أولاً.'},
    'previous': {'en': 'Previous', 'ar': 'السابق'},
    'next': {'en': 'Next', 'ar': 'التالي'},
    'locked': {'en': 'Locked', 'ar': 'مقفل'},
    'unlocked': {'en': 'Unlocked', 'ar': 'مفتوح'},
    'enter_library_name': {'en': 'Enter the library name to install:', 'ar': 'أدخل اسم المكتبة للتثبيت:'},
    'enter_message': {'en': 'Enter the message to send:', 'ar': 'أدخل الرسالة للإرسال:'},
    'send_token': {'en': 'Send the new token:', 'ar': 'أرسل التوكن الجديد:'},
    'enter_name': {'en': 'Enter the new bot name:', 'ar': 'أدخل اسم البوت الجديد:'},
    'send_image': {'en': 'Send an image:', 'ar': 'أرسل صورة:'},
    'error': {'en': 'Error', 'ar': 'خطأ'},
    'success': {'en': 'Success', 'ar': 'نجاح'},
    'invalid_user_id': {'en': 'Invalid user ID.', 'ar': 'معرف المستخدم غير صالح.'},
    'failed': {'en': 'Operation failed.', 'ar': 'فشلت العملية.'},
    'invalid_price': {'en': 'Invalid price.', 'ar': 'سعر غير صالح.'},
    'referral_bonus': {'en': 'Referral Bonus', 'ar': 'مكافأة الإحالة'},
    'approved': {'en': 'Approved', 'ar': 'تم القبول'},
    'rejected': {'en': 'Rejected', 'ar': 'تم الرفض'},
    'no_pending': {'en': 'No pending files.', 'ar': 'لا توجد ملفات معلقة.'},
    'running': {'en': 'Running', 'ar': 'يعمل'},
    'stopped': {'en': 'Stopped', 'ar': 'متوقف'},
    'pending_review': {'en': 'Pending Review', 'ar': 'قيد المراجعة'},
    'accepted': {'en': 'Accepted', 'ar': 'تم القبول'},
    'file': {'en': 'File: {name}', 'ar': 'الملف: {name}'},
    'duration': {'en': 'Duration: {duration}', 'ar': 'المدة: {duration}'},
    'unbanned': {'en': 'Unbanned', 'ar': 'تم رفع الحظر'},
    'done': {'en': 'Done', 'ar': 'تم'},
    'downloaded': {'en': 'Downloaded', 'ar': 'تم التحميل'},
    'started': {'en': 'Started', 'ar': 'تم التشغيل'},
    'start_failed': {'en': 'Failed to start', 'ar': 'فشل التشغيل'},
    'all_stopped': {'en': 'All processes stopped.', 'ar': 'تم إيقاف جميع العمليات.'},
    'image_removed': {'en': 'Image removed.', 'ar': 'تم إزالة الصورة.'},
    'thumb_removed': {'en': 'Thumbnail removed.', 'ar': 'تم إزالة الصورة المصغرة.'},
    'invalid_username': {'en': 'Invalid username.', 'ar': 'اسم المستخدم غير صالح.'},
    'time_expired': {'en': 'Time Expired', 'ar': 'انتهى الوقت'},
    'vip_removed': {'en': 'VIP removed.', 'ar': 'تم إزالة VIP.'},
}

def init_database():
    default_channels = [
        {"username": "@F7_7G", "name": "F7_7G"},
        {"username": "@H_U_VB", "name": "H_U_VB"},
        {"username": "@seed_1k", "name": "seed_1k"},
        {"username": "@TERBO_CODE", "name": "TERBO_CODE"},
        {"username": "@BQBOOB1", "name": "BQBOOB1"},
        {"username": "@bshshshkk", "name": "bshshshkk"},
        {"username": "@EQJ_1", "name": "EQJ_1"},
        {"username": "@HAMO_X_OT3", "name": "HAMO_X_OT3"}
    ]
    settings = DatabaseManager.get_settings()
    if 'channels' not in settings:
        settings['channels'] = default_channels
    defaults = {
        "bot_name": "Hosting Bot",
        "bot_image": None,
        "file_thumb": None,
        "bot_locked": False,
        "auto_approve": True
    }
    for key, value in defaults.items():
        if key not in settings:
            settings[key] = value
    DatabaseManager.save_settings(settings)
    for path in [USERS_DB, FILES_DB, STORE_DB, MARKET_DB, SECURITY_DB]:
        if not os.path.exists(path):
            write_json(path, {})
    admins = DatabaseManager.get_admins()
    if ADMIN_ID not in admins:
        admins.append(ADMIN_ID)
        DatabaseManager.save_admins(admins)
    security = DatabaseManager.get_security()
    if 'master_key' not in security:
        master_key = base64.b64encode(get_random_bytes(32)).decode('utf-8')
        security['master_key'] = master_key
        security['file_keys'] = {}
        DatabaseManager.save_security(security)

def build_main_keyboard(uid):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(Utilities.create_button(Utilities.get_text(uid, 'upload'), "nav_upload", uid))
    kb.row(
        Utilities.create_button(Utilities.get_text(uid, 'my_files'), "nav_files", uid),
        Utilities.create_button(Utilities.get_text(uid, 'store'), "nav_store", uid)
    )
    kb.row(
        Utilities.create_button(Utilities.get_text(uid, 'wallet'), "nav_wallet", uid),
        Utilities.create_button(Utilities.get_text(uid, 'profile'), "nav_stats", uid)
    )
    kb.row(
        Utilities.create_button(Utilities.get_text(uid, 'install_library'), "nav_lib", uid),
        Utilities.create_button(Utilities.get_text(uid, 'settings'), "nav_settings", uid)
    )
    if Utilities.is_user_pro(uid):
        kb.row(
            Utilities.create_button(Utilities.get_text(uid, 'pro_panel'), "nav_pro", uid)
        )
    kb.add(Utilities.create_button(Utilities.get_text(uid, 'contact_dev'), None, uid, url=f"tg://user?id={ADMIN_ID}"))
    if Utilities.is_admin(uid):
        kb.add(Utilities.create_button(Utilities.get_text(uid, 'admin_panel'), "nav_admin", uid))
    return kb

def build_pro_keyboard(uid):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(Utilities.create_button(Utilities.get_text(uid, 'download_all'), "pro_download_all", uid))
    kb.add(Utilities.create_button(Utilities.get_text(uid, 'auto_fix'), "pro_auto_fix", uid))
    kb.add(Utilities.create_button(Utilities.get_text(uid, 'test_run'), "pro_test_run", uid))
    kb.add(Utilities.create_button(Utilities.get_text(uid, 'sell_store'), "pro_sell", uid))
    kb.add(Utilities.create_button(Utilities.get_text(uid, 'back'), "nav_main", uid))
    return kb

def build_cancel_keyboard(uid, data="cancel"):
    kb = types.InlineKeyboardMarkup()
    kb.add(Utilities.create_button(Utilities.get_text(uid, 'cancel'), data, uid))
    return kb

def build_back_keyboard(uid, data="nav_main"):
    kb = types.InlineKeyboardMarkup()
    kb.add(Utilities.create_button(Utilities.get_text(uid, 'back'), data, uid))
    return kb

def build_language_keyboard(uid):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(Utilities.create_button("English", "set_lang_en", uid))
    kb.add(Utilities.create_button("العربية", "set_lang_ar", uid))
    return kb

def build_style_keyboard(uid):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(Utilities.create_button(Utilities.get_text(uid, 'style_default'), "set_style_default", uid, style_override='default'))
    kb.add(Utilities.create_button(Utilities.get_text(uid, 'style_primary'), "set_style_primary", uid, style_override='primary'))
    kb.add(Utilities.create_button(Utilities.get_text(uid, 'style_success'), "set_style_success", uid, style_override='success'))
    kb.add(Utilities.create_button(Utilities.get_text(uid, 'style_danger'), "set_style_danger", uid, style_override='danger'))
    kb.add(Utilities.create_button(Utilities.get_text(uid, 'back'), "nav_settings", uid))
    return kb

def build_settings_keyboard(uid):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(Utilities.create_button(Utilities.get_text(uid, 'change_lang'), "nav_change_lang", uid))
    kb.add(Utilities.create_button(Utilities.get_text(uid, 'change_style'), "nav_change_style", uid))
    kb.add(Utilities.create_button(Utilities.get_text(uid, 'back'), "nav_main", uid))
    return kb

@bot.message_handler(commands=['start'])
def start_command(msg):
    try:
        uid = msg.from_user.id
        settings = DatabaseManager.get_settings()
        if settings.get('bot_locked', False) and not Utilities.is_admin(uid):
            try:
                bot.delete_message(msg.chat.id, msg.message_id)
            except:
                pass
            Utilities.send_message(msg.chat.id, uid, Utilities.format_border(uid, 'bot_locked', 'bot_locked_desc'),
                                   types.InlineKeyboardMarkup().add(Utilities.create_button(Utilities.get_text(uid, 'contact_dev'), None, uid, url=f"tg://user?id={ADMIN_ID}")))
            return
        users = DatabaseManager.get_users()
        Utilities.clear_cancel(uid)
        if str(uid) not in users:
            if len(msg.text.split()) > 1:
                ref = msg.text.split()[1]
                if ref.isdigit() and int(ref) != uid:
                    udb = DatabaseManager.get_users()
                    if str(ref) in udb:
                        udb[str(ref)]['points'] = udb[str(ref)].get('points', 0) + 10
                        DatabaseManager.save_users(udb)
                        try:
                            bot.send_message(int(ref), Utilities.format_border(uid, 'referral_bonus', 'You earned 10 points for referring a new user!'))
                        except:
                            pass
            users[str(uid)] = {
                'username': msg.from_user.username,
                'first_name': msg.from_user.first_name,
                'last_name': msg.from_user.last_name,
                'points': 10,
                'join_date': str(datetime.now().date()),
                'is_banned': 0,
                'expiry': None,
                'last_daily': None,
                'notifications': True,
                'lang': 'en',
                'button_style': 'default'
            }
            DatabaseManage
