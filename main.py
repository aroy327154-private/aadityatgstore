import os
import sqlite3
import re
import asyncio
import time
import logging
import csv
import zipfile
import shutil
import sys
import unicodedata
import html
import imaplib
import email
import urllib.request
import urllib.error
import json
import ssl
import hashlib
import inspect
import uuid
import subprocess
import signal
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode

# App code folder (repo). Captured BEFORE any chdir, so paths to bundled files
# (docs-index.html, logs) stay correct on Render where DATA_DIR is a mounted disk.
_APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Render: run from the persistent disk so database, sessions and backups survive redeploys.
_DATA_DIR = os.environ.get("DATA_DIR", "").strip()
if _DATA_DIR:
  sys.argv[0] = os.path.abspath(sys.argv[0])
  os.makedirs(_DATA_DIR, exist_ok=True)
  os.chdir(_DATA_DIR)

# ---- AUTO-INSTALL Telethon-MCUB (needed for custom emoji + coloured buttons) ----
MCUB_LOG = os.path.join(_APP_DIR, "mcub_install.log")

def _mcub_log(txt):
  for _p in (MCUB_LOG, "/tmp/mcub_install.log"):
    try:
      with open(_p, "a", encoding="utf-8") as _f: _f.write(txt + "\n")
      return
    except Exception:
      continue

def _mcub_ok():
  """Real functional test: does the loaded Telethon create custom-emoji entities?"""
  try:
    from telethon.extensions import html as _h
    from telethon.tl.types import MessageEntityCustomEmoji
    _, _e = _h.parse('<tg-emoji emoji-id="5348035934870849516">\u2705</tg-emoji>')
    return any(isinstance(x, MessageEntityCustomEmoji) for x in _e)
  except Exception:
    return False

def _ensure_mcub():
  if os.environ.get("_MCUB_TRIED"):
    return
  ok = _mcub_ok()
  try:
    import telethon as _t0
    _ver0 = getattr(_t0, "__version__", "?")
  except Exception:
    _ver0 = "import failed"
  _mcub_log("[%s] check: telethon=%s custom_emoji_ok=%s" % (time.strftime("%H:%M:%S"), _ver0, ok))
  if ok:
    return
  os.environ["_MCUB_TRIED"] = "1"
  print("Telethon-MCUB missing/inactive -> installing (one time, wait 1-2 min)...", flush=True)
  _pip = [sys.executable, "-m", "pip"]
  def _run(args):
    try:
      r = subprocess.run(_pip + args, capture_output=True, text=True, timeout=900)
      return r.returncode, ((r.stdout or "") + (r.stderr or ""))[-1200:]
    except Exception as e:
      return 99, "EXC: %r" % (e,)
  rc0, o0 = _run(["uninstall", "-y", "telethon", "Telethon-MCUB", "telethon-mcub"])
  rc, o1 = _run(["install", "--force-reinstall", "--no-cache-dir", "Telethon-MCUB>=1.42.11"])
  _mcub_log("UNINSTALL rc=%s\n%s\nINSTALL rc=%s\n%s" % (rc0, o0, rc, o1))
  print("MCUB install rc=%s" % rc, flush=True)
  if rc != 0:
    rc2, o2 = _run(["install", "telethon"])
    _mcub_log("RESTORE telethon rc=%s\n%s" % (rc2, o2))
    return
  os.execv(sys.executable, [sys.executable] + sys.argv)

_ensure_mcub()

from telethon import TelegramClient, events, Button

# ================= GLOBAL BUTTON STYLE (COLOURED + CUSTOM EMOJI) =================
# Telegram MTProto KeyboardButtonStyle supports primary (blue), success (green),
# and danger (red). We attach the style to the raw TL button so this also works
# with Telethon builds whose Button.inline helper has no `style=` parameter.
_ORIGINAL_BUTTON = Button

_SMALL_CAPS = {
    'a': '\u1d00', 'b': '\u0299', 'c': '\u1d04', 'd': '\u1d05', 'e': '\u1d07',
    'f': '\ua730', 'g': '\u0262', 'h': '\u029c', 'i': '\u026a', 'j': '\u1d0a',
    'k': '\u1d0b', 'l': '\u029f', 'm': '\u1d0d', 'n': '\u0274', 'o': '\u1d0f',
    'p': '\u1d18', 'q': '\u01eb', 'r': '\u0280', 's': '\ua731', 't': '\u1d1b',
    'u': '\u1d1c', 'v': '\u1d20', 'w': '\u1d21', 'x': 'x', 'y': '\u028f',
    'z': '\u1d22',
}


def _button_font(text):
    text = unicodedata.normalize('NFKC', str(text))
    try:
        text = _hide_provider(text)
    except NameError:
        pass
    return ''.join(_SMALL_CAPS.get(ch, ch) if 'a' <= ch <= 'z' else ch for ch in text)


# Custom emoji IDs used by the existing bot. Keep these alongside button colors.
# App logo premium emoji (from @TgEmojis). Change an id here and it updates everywhere.
LOGO_TG_ID = "6325529375718510567"    # Telegram logo
LOGO_WA_ID = "6325847375097106376"    # WhatsApp logo
LOGO_IG_ID = "6325734348737746326"    # Instagram logo
LOGO_MORE_ID = "6325681795517911186"  # "More apps" logo

BUTTON_ICONS = {
  "profile": "5832281029204775089", "refer": "5834807908788867114",
  "store": "5834918366757786311", "tk acc": "5832418158920602346",
  "tg acc": "5832418158920602346", "server 2 [ manually added ]": "5832418158920602346",
  "manual acc": "5832418158920602346", "smm": "5834694603256632485",
  "tk acccount": "5832418158920602346", "add funds": "5834557460655904825",
  "deposit funds": "5834557460655904825", "orders history": "5834617968155168912",
  "my orders": "5834617968155168912", "refill": "5834807281723642144",
  "redeem code": "5832411746534429224", "redeem codes": "5832411746534429224",
  "selling logs": "5834519235446968809", "support": "5834461137424356807",
  "updates": "5834588100952594301", "server 1 [cheap account]": "5832269497217585375",
  "digital shop": "5834918366757786311", "shop": "5834918366757786311",
  "back to shop": "5834918366757786311", "social media services": "5834694603256632485",
  "back to main": "5832249985181160265", "back to main menu": "5832249985181160265",
  "back": "5832249985181160265", "back to admin": "5832249985181160265",
  "back to store": "5834918366757786311", "back to countries": "5832249985181160265",
  "back to categories": "5832249985181160265", "back to details": "5832249985181160265",
  "back to digital shop": "5834918366757786311", "back to payment methods": "5834557460655904825",
  "back to profile": "5832281029204775089", "back to servers apis": "5832538679997895284",
  "servers apis": "5832538679997895284", "smm api": "5832538679997895284",
  "refresh": "5834807281723642144", "try again": "5834807281723642144",
  "check again": "5834807281723642144", "generate qr again": "5834807281723642144",
  "get code": "5832432319427776896", "check code": "5832432319427776896",
  "get otp again": "5832432319427776896", "my numbers": "5834694603256632485",
  "buy a number": "5834918366757786311", "buy now": "5834918366757786311",
  "yes, buy now": "5834918366757786311", "buy single": "5834918366757786311",
  "buy bulk": "5834918366757786311", "prev": "5834792099014251507",
  "next": "5834699366375362698", "cancel": "5834870091325378855",
  "no, cancel": "5834870091325378855", "confirm": "5834600569242654097",
  "yes": "5834600569242654097", "delete": "5834870091325378855",
  "remove admin": "5834870091325378855", "remove channel": "5834870091325378855",
  "remove code": "5834870091325378855", "remove product": "5834870091325378855",
  "remove category": "5834870091325378855", "reject": "5834870091325378855",
  "verify payment": "5834600569242654097", "verify joined": "5834600569242654097",
  "add admin": "5834812242410869159", "edit admin": "5834812242410869159",
  "manage admins": "5834812242410869159", "user info": "5834812242410869159",
  "ban user": "5834870091325378855", "change balance": "5832530897517154496",
  "statistics": "5834519235446968809", "status": "5834519235446968809",
  "accept": "5834600569242654097", "choose year": "5832625820589363805",
  "set profit margin": "5832530897517154496", "settings": "5832712733547564784",
  "payments history": "5834519235446968809", "broadcast": "5834588100952594301",
  "add channel": "5832538679997895284", "channels": "5832538679997895284",
  "payment methods": "5834557460655904825", "upi manual": "5834557460655904825",
  "usdt manual": "5834557460655904825", "set usdt address & network": "5834557460655904825",
  "send screenshot": "5832705019786302198", "fampay automatic": "5834557460655904825", "bharatpe automatic": "5834557460655904825",
  "set bharatpe upi & name": "5834557460655904825", "set bharatpe sender": "5834557460655904825", "test bharatpe connection": "5834807281723642144",
  "fampay / imap": "5834557460655904825", "configure imap (gmail)": "5834557460655904825",
  "set manual upi & name": "5834557460655904825", "set fampay upi & name": "5834557460655904825",
  "change manual upi & name": "5834557460655904825", "change fampay upi & name": "5834557460655904825",
  "change logs channel": "5834886399316201457", "support channel": "5834461137424356807",
  "support user": "5834461137424356807", "update welcome photo": "5832705019786302198", "update welcome media": "5832705019786302198",
  "backup users": "5834886399316201457", "backup": "5834886399316201457",
  "restore": "5834807281723642144", "restore users": "5834807281723642144",
  "discount": "5832530897517154496", "usdt rate": "5832530897517154496",
  "auto price": "5832530897517154496", "set common price": "5832530897517154496",
  "edit common price (all years)": "5832530897517154496", "add product": "5834918366757786311",
  "add service": "5834918366757786311", "add single acc": "5834918366757786311",
  "bulk add": "5834918366757786311", "add zip": "5834886399316201457",
  "manage stock": "5834886399316201457", "manage": "5832712733547564784",
  "categories": "5834886399316201457", "create category": "5834886399316201457",
  "add custom country": "5832538679997895284", "edit country name": "5832538679997895284",
  "create code": "5832411746534429224", "test again": "5834807281723642144",
  "finish & logout": "5834791785481638087", "server 2 [ whatsapp accounts ]": "5832418158920602346",
  "server 3 [ manually added accounts ]": "5832418158920602346", "server 4 [ manually added accounts ]": "5832418158920602346",
  "server 3 [ all app otp ]": "5832418158920602346", "manually added accounts": "5832418158920602346",
  "server 2 [whatsapp accounts]": "5832418158920602346", "whatsapp": "5832418158920602346",
  "whatsapp accounts": "5832418158920602346", "buy whatsapp number": "5834557460655904825",
  "buy for": "5834557460655904825", "function management": "5832712733547564784",
  "provider balance": "5834557460655904825", "home": "5832249985181160265",
  "countries": "5834918366757786311", "country": "5834918366757786311",
  "retry": "5834807281723642144", "noop": "5834699366375362698",
}

BUTTON_ICONS.update({
  "server 1 [ cheap tg accounts ]": "5832269497217585375",
  "start": "5834600569242654097", "start all": "5834600569242654097",
  "stop": "5834870091325378855", "stop all": "5834870091325378855",
  "restart": "5834807281723642144", "restart all": "5834807281723642144",
  "view logs": "5834519235446968809", "all logs": "5834519235446968809",
  "errors only": "5834519235446968809", "download log": "5834886399316201457",
  "clear logs": "5834870091325378855", "backup all": "5834886399316201457",
  "manage cloned bots": "5832712733547564784", "clone new bot": "5834918366757786311",
  "change bot token": "5832538679997895284", "change owner id": "5834812242410869159",
  "rename store": "5832712733547564784", "change api id / hash": "5832538679997895284",
  "delete bot": "5834870091325378855", "backup & delete": "5834886399316201457",
  "yes, delete": "5834870091325378855", "yes, stop all": "5834870091325378855",
  "back to cloned bots": "5832249985181160265",
})

# App-logo icons on store buttons: Telegram -> TG logo, WhatsApp -> WA logo, all-app OTP -> apps logo.
BUTTON_ICONS.update({
  "server 1 [ cheap tg accounts ]": LOGO_TG_ID,
  "server 1 [cheap account]": LOGO_TG_ID,
  "server 2 [ whatsapp accounts ]": LOGO_WA_ID,
  "server 2 [whatsapp accounts]": LOGO_WA_ID,
  "whatsapp": LOGO_WA_ID,
  "whatsapp accounts": LOGO_WA_ID,
  "buy whatsapp number": LOGO_WA_ID,
})

_BUTTON_KEYWORD_ICONS = [
  ("unfreeze", "5834600569242654097"), ("unban", "5834600569242654097"),
  ("freeze", "5834870091325378855"),
  ("back", "5832249985181160265"), ("cancel", "5834870091325378855"),
  ("remove", "5834870091325378855"), ("delete", "5834870091325378855"),
  ("reject", "5834870091325378855"), ("buy", "5834918366757786311"),
  ("add funds", "5834557460655904825"), ("deposit", "5834557460655904825"),
  ("balance", "5832530897517154496"), ("price", "5832530897517154496"),
  ("stock", "5834886399316201457"), ("code", "5832432319427776896"),
  ("otp", "5832432319427776896"), ("number", "5834694603256632485"),
  ("order", "5834617968155168912"), ("profile", "5832281029204775089"),
  ("admin", "5834812242410869159"), ("user", "5834812242410869159"),
  ("channel", "5832538679997895284"), ("api", "5832538679997895284"),
  ("test", "5834807281723642144"), ("refresh", "5834807281723642144"),
  ("stats", "5834519235446968809"), ("accept", "5834600569242654097"),
  ("year", "5832625820589363805"), ("profit", "5832530897517154496"),
  ("margin", "5832530897517154496"), ("setting", "5832712733547564784"),
  ("del:", "5834870091325378855"), ("edit:", "5832712733547564784"),
]


def _button_icon_id(text):
    raw = unicodedata.normalize('NFKC', str(text or ''))
    plain = re.sub(r'^[^\w\u0900-\u097F]+', '', raw).strip().lower()
    if plain in BUTTON_ICONS:
        return BUTTON_ICONS[plain]
    for key, emoji_id in BUTTON_ICONS.items():
        if key and key in plain:
            return emoji_id
    for key, emoji_id in _BUTTON_KEYWORD_ICONS:
        if key in plain:
            return emoji_id
    return None


def _strip_leading_emoji(text):
    return re.sub(r'^[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D\s]+', '', str(text))


def _button_style_for(text, explicit=None):
    """Choose a meaningful color for every button; explicit style always wins."""
    if explicit in ('danger', 'primary', 'success'):
        return explicit
    label = unicodedata.normalize('NFKC', str(text or '')).lower()
    danger = ('cancel', 'delete', 'remove', 'reject', 'ban ', 'close chat',
              'close order', 'stop ', 'decline', 'deny', 'reset', 'logout',
              'refund', 'discard', 'disable', 'block ')
    success = ('buy', 'confirm', 'verify', 'accept', 'approve', 'deliver',
               'save', 'submit', 'finish', 'complete', 'activate', 'enable',
               'pay ', 'purchase', 'yes', 'done', 'add funds', 'deposit')
    nav = ('back', 'prev', 'next', 'home', 'menu', 'refresh', 'profile', 'support', 'updates')
    money = ('funds', 'balance', 'wallet', 'price', 'profit', 'usdt', 'upi', 'payment')
    if any(word in label for word in danger):
        return 'danger'
    if any(word in label for word in success) or any(word in label for word in money):
        return 'success'
    if any(word in label for word in nav):
        return 'primary'

    # Balanced blue/green palette for neutral inline actions. Stable by label.
    neutral_palette = ('primary', 'success')
    digest = hashlib.sha256(label.encode('utf-8')).digest()
    return neutral_palette[digest[0] % len(neutral_palette)]


def _factory_caps(factory):
    """Return (supports_style, supports_icon) for the installed Telethon Button helper."""
    try:
        params = inspect.signature(factory).parameters
    except (TypeError, ValueError):
        return True, True
    var_kw = any(p.kind is p.VAR_KEYWORD for p in params.values())
    return ('style' in params or var_kw), ('icon' in params or var_kw)


class _StyledButtonProxy:
    """Button factory applying small-caps labels, native colors and custom-emoji icons.

    Telethon-MCUB's Button.inline/url take style as a *string*
    ('primary' | 'success' | 'danger') and icon as a custom emoji id.
    Passing a KeyboardButtonStyle object crashes (`.lower()` error), so we only pass strings.
    """

    @staticmethod
    def _build(kind, text, target, icon_custom_emoji_id=None, icon=None, **kwargs):
        explicit_style = kwargs.pop('style', None)
        if not isinstance(explicit_style, str):
            explicit_style = None
        style_name = _button_style_for(text, explicit_style)
        original_label = str(text)
        emoji_id = icon_custom_emoji_id or icon or _button_icon_id(text)
        try:
            emoji_id = int(emoji_id) if emoji_id else None
        except (TypeError, ValueError):
            emoji_id = None

        factory = (_ORIGINAL_BUTTON.inline if kind == 'inline' else _ORIGINAL_BUTTON.url)
        sup_style, sup_icon = _factory_caps(factory)

        full_label = _button_font(original_label)
        icon_label = _button_font(_strip_leading_emoji(original_label) or original_label)

        # (label, extra kwargs) - best first, plain button last.
        attempts = []
        if emoji_id and sup_style and sup_icon:
            attempts.append((icon_label, {'style': style_name, 'icon': emoji_id}))
            attempts.append((icon_label, {'style': style_name, 'icon': str(emoji_id)}))
        if sup_style:
            attempts.append((full_label, {'style': style_name}))
        attempts.append((full_label, {}))

        last_exc = None
        for label, extra in attempts:
            try:
                return factory(label, target, **extra, **kwargs)
            except (TypeError, ValueError, AttributeError) as exc:
                last_exc = exc
                logging.getLogger(__name__).debug('Button attempt %s failed: %s', extra, exc)
        logging.getLogger(__name__).warning('Styled button failed (%s); using plain button', last_exc)
        return factory(full_label, target)

    @staticmethod
    def inline(text, data=None, icon_custom_emoji_id=None, icon=None, **kwargs):
        return _StyledButtonProxy._build('inline', text, data,
            icon_custom_emoji_id=icon_custom_emoji_id, icon=icon, **kwargs)

    @staticmethod
    def url(text, url, icon_custom_emoji_id=None, icon=None, **kwargs):
        return _StyledButtonProxy._build('url', text, url,
            icon_custom_emoji_id=icon_custom_emoji_id, icon=icon, **kwargs)

    def __getattr__(self, name):
        return getattr(_ORIGINAL_BUTTON, name)


Button = _StyledButtonProxy
from telethon.errors import (
  FloodWaitError,
  SessionPasswordNeededError, 
  MessageNotModifiedError,
  UserNotParticipantError,
  ChatAdminRequiredError,
  UserIsBlockedError,
  InputUserDeactivatedError,
  PeerIdInvalidError
)
from telethon.tl.types import MessageMediaWebPage
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.functions.messages import ExportChatInviteRequest
from telethon.tl.types import ChannelParticipantAdmin, ChannelParticipantCreator
from telethon.tl.functions.account import GetPasswordRequest
try:
  from telethon.sessions import StringSession as _TGStringSession
except Exception:
  _TGStringSession = None
try:
  from telethon.tl.functions.account import (
    GetAuthorizationsRequest as _TGGetAuthorizations,
    ResetAuthorizationRequest as _TGResetAuthorization,
  )
except Exception:
  _TGGetAuthorizations = None
  _TGResetAuthorization = None

# ================= CONFIGURATION =================
# Render / Docker pe secrets environment se aate hain; agar env set nahi hai to
# neeche wali default values use hoti hain (local run ke liye).
def _env_int(name, default):
  try:
    return int(str(os.environ.get(name) or default).strip())
  except Exception:
    return int(default)


API_ID = _env_int("API_ID", 31535678)
API_HASH = (os.environ.get("API_HASH") or "18682b75e0e6e1a7c5bb11fb65452153").strip()
BOT_TOKEN = (os.environ.get("BOT_TOKEN") or "9047470943:AAFdiY5EPsQP0APCQ6648dBTcnbQT9rhHCY").strip()
ADMIN_ID = _env_int("ADMIN_ID", 6914205738)

# ================= CLONE MODE =================
# A cloned bot runs THIS SAME script from its own folder (cloned_bots/<bot_id>/) with a
# clone_config.json next to it. Token / API / owner come from that file, and every
# other file (database, sessions, welcome photo, logs) is created inside that folder,
# so the clone never shares data with the main bot.
CLONES_ROOT = os.path.join(os.environ.get("DATA_DIR") or os.path.dirname(os.path.abspath(__file__)), "cloned_bots")
CLONE_CONFIG_FILE = "clone_config.json"
CLONE_CONFIG = {}
IS_CLONE = False
# Main bot Reseller API / docs base — used ONLY inside cloned bots (Server 1/2/3 upstream + admin docs link).
MAIN_API_DOCS_URL = (os.environ.get("MAIN_API_DOCS_URL") or "https://aaditya-store-bot.onrender.com").strip().rstrip("/")
if os.path.isfile(CLONE_CONFIG_FILE):
  try:
    with open(CLONE_CONFIG_FILE, "r", encoding="utf-8") as _cf:
      CLONE_CONFIG = json.load(_cf)
    API_ID = int(CLONE_CONFIG["api_id"])
    API_HASH = str(CLONE_CONFIG["api_hash"])
    BOT_TOKEN = str(CLONE_CONFIG["bot_token"])
    ADMIN_ID = int(CLONE_CONFIG["owner_id"])
    IS_CLONE = True
  except Exception as _cex:
    print("Invalid clone_config.json: %s" % _cex)
    sys.exit(1)

# Store name shown everywhere in a cloned bot (asked while cloning, editable in Manage Cloned Bots).
STORE_NAME = str(CLONE_CONFIG.get("store_name") or "").strip() if IS_CLONE else ""
STORE_DISPLAY = STORE_NAME or "Aaditya Tg Store"


def _bold(text):
  """Letters/digits -> Unicode bold sans-serif (e.g. AADITYA TG STORE -> bold font)."""
  out = []
  for ch in str(text):
    o = ord(ch)
    if 65 <= o <= 90:
      out.append(chr(0x1D5D4 + o - 65))
    elif 97 <= o <= 122:
      out.append(chr(0x1D5EE + o - 97))
    elif 48 <= o <= 57:
      out.append(chr(0x1D7EC + o - 48))
    else:
      out.append(ch)
  return "".join(out)


BRAND_TITLE = _bold(STORE_DISPLAY.upper())

# ================= TELEGRAM CUSTOM EMOJI CONSTANTS (UPDATED) =================
# Premium custom emoji (Telegram <tg-emoji>) used across the main menu,
# store, profile, wallet and admin panels. Country flags are handled
# separately by COUNTRY_FLAGS so the country section stays untouched.

P_YES = '<tg-emoji emoji-id="5348035934870849516">✅</tg-emoji>'
P_NO = '<tg-emoji emoji-id="5352909795038880233">❌</tg-emoji>'
P_PKG = '<tg-emoji emoji-id="5352718875152639926">🛒</tg-emoji>'
P_MONEY = '<tg-emoji emoji-id="5348418461838098123">💰</tg-emoji>'
P_USDT = '<tg-emoji emoji-id="5350290466283744905">💲</tg-emoji>'
P_INR = '₹'
P_TG = f'<tg-emoji emoji-id="{LOGO_TG_ID}">✈️</tg-emoji>'
P_WA = f'<tg-emoji emoji-id="{LOGO_WA_ID}">📞</tg-emoji>'
P_IG = f'<tg-emoji emoji-id="{LOGO_IG_ID}">📸</tg-emoji>'
P_APPS = f'<tg-emoji emoji-id="{LOGO_MORE_ID}">🌐</tg-emoji>'
P_GIFT = '<tg-emoji emoji-id="5353049621994173706">🎁</tg-emoji>'
P_STATS = '<tg-emoji emoji-id="5350613306090482956">📊</tg-emoji>'
P_CARD = '<tg-emoji emoji-id="5350312748574076353">💳</tg-emoji>'
P_USERS = '<tg-emoji emoji-id="5348136664738839786">👤</tg-emoji>'
P_CAL = '<tg-emoji emoji-id="5350595795508814391">🕓</tg-emoji>'
P_PC = '<tg-emoji emoji-id="5454079785510660283">💻</tg-emoji>'
P_EYE = '<tg-emoji emoji-id="5350803525897054388">👀</tg-emoji>'
P_CW = '<tg-emoji emoji-id="5452002073606384268">🔄</tg-emoji>'
P_ON = '<tg-emoji emoji-id="5348125643852758491">🔔</tg-emoji>'
P_OFF = '<tg-emoji emoji-id="5348296085334934565">🔕</tg-emoji>'
P_ID = '<tg-emoji emoji-id="5454419255430767770">📎</tg-emoji>'
P_KEY = '<tg-emoji emoji-id="5454386656628991407">🔑</tg-emoji>'
P_GLOBE = '<tg-emoji emoji-id="5348540950010412359">🌐</tg-emoji>'
P_CART = '<tg-emoji emoji-id="5352718875152639926">🛒</tg-emoji>'
P_STORE = '<tg-emoji emoji-id="5350295774863311434">💼</tg-emoji>'
P_OTP = '<tg-emoji emoji-id="5350781673103453057">🔐</tg-emoji>'
P_2FA = '<tg-emoji emoji-id="5350806480834553770">🛡</tg-emoji>'
P_FLAG = '<tg-emoji emoji-id="5454310635707853545">🚩</tg-emoji>'
P_PHONE = '<tg-emoji emoji-id="5350280858441903578">📞</tg-emoji>'
P_WAIT = '<tg-emoji emoji-id="5352940967911517739">⏳</tg-emoji>'
P_TIME = '<tg-emoji emoji-id="5348090777308251395">⏰</tg-emoji>'
P_WARN = '<tg-emoji emoji-id="5350477112677515642">⚠️</tg-emoji>'
P_DOC = '<tg-emoji emoji-id="5350727535040684495">📔</tg-emoji>'
P_ASST = '<tg-emoji emoji-id="5350635725819768084">🤖</tg-emoji>'
P_ACC = '<tg-emoji emoji-id="5350763436672305153">👤</tg-emoji>'
P_FIRE = '<tg-emoji emoji-id="5348529413728256481">🔥</tg-emoji>'
P_STAR = '<tg-emoji emoji-id="5350439235360932475">⭐</tg-emoji>'
P_DIAMOND = '<tg-emoji emoji-id="5350431598909089381">💎</tg-emoji>'
P_BELL = '<tg-emoji emoji-id="5352874632141628924">🔔</tg-emoji>'
P_CROWN = '<tg-emoji emoji-id="5352670019899652428">👑</tg-emoji>'
P_LIGHTNING = '<tg-emoji emoji-id="5350618807943576963">⚡</tg-emoji>'
P_ROCKET = '<tg-emoji emoji-id="5350490470025816976">🚀</tg-emoji>'
P_PARTY = '<tg-emoji emoji-id="5350593231413341402">🎉</tg-emoji>'
P_FOLDER = '<tg-emoji emoji-id="5350685478720924701">🗂</tg-emoji>'
P_GEAR = '<tg-emoji emoji-id="5348412779596365405">⚙️</tg-emoji>'
P_PIN = '<tg-emoji emoji-id="5348498060466996739">📌</tg-emoji>'
P_SEARCH = '<tg-emoji emoji-id="5350776428948381533">🔍</tg-emoji>'
P_LINK = '<tg-emoji emoji-id="5350695039318114023">🔗</tg-emoji>'
P_TITLE = '<tg-emoji emoji-id="5350333514740951883">✨</tg-emoji>'
P_DESC = '<tg-emoji emoji-id="5348471079482441278">💬</tg-emoji>'
P_RATE = '<tg-emoji emoji-id="5350613306090482956">📊</tg-emoji>'
P_MIN = '<tg-emoji emoji-id="5350700390847365132">⏬</tg-emoji>'
P_MAX = '<tg-emoji emoji-id="5350305520144106741">⏫</tg-emoji>'
P_QTY = '<tg-emoji emoji-id="5350778250014515913">1️⃣</tg-emoji>'

def strip_custom_emoji(text):
  """Convert <tg-emoji ...>X</tg-emoji> blocks into their plain emoji fallback X."""
  if text is None:
    return text
  return re.sub(r'<tg-emoji\b[^>]*>(.*?)</tg-emoji>', r'\1', str(text),
                flags=re.DOTALL | re.IGNORECASE)


def _telethon_supports_custom_emoji():
  """True when the installed Telethon understands <tg-emoji emoji-id="...">."""
  try:
    from telethon.extensions import html as _tl_html
    from telethon.tl.types import MessageEntityCustomEmoji
    # A custom-emoji entity must wrap an emoji glyph, not a plain letter.
    _, _ents = _tl_html.parse(
        '<tg-emoji emoji-id="5348035934870849516">✅</tg-emoji>'
    )
    return any(isinstance(en, MessageEntityCustomEmoji) for en in _ents)
  except Exception:
    return False


# Runtime capability flag. Telethon-MCUB (not an old stock Telethon build) is
# required for Telegram's February 2026 custom-emoji entity and button schema.
# If the parser cannot create MessageEntityCustomEmoji, retain readable fallback
# emoji instead of stripping them from messages.
CUSTOM_EMOJI_ENABLED = _telethon_supports_custom_emoji()
if not CUSTOM_EMOJI_ENABLED:
  logging.getLogger(__name__).error(
    'Custom emoji HTML entities are unavailable in this Telethon install. '
    'Install Telethon-MCUB >= 1.42.11 and restart the bot.')


# ---- STARTUP DIAGNOSTIC (shows why emoji/colours are missing) ----
try:
  import telethon as _tlv
  _fac = _factory_caps(_ORIGINAL_BUTTON.inline)
  print("=" * 50)
  print("TELETHON VERSION      :", getattr(_tlv, "__version__", "?"))
  print("TELETHON PATH         :", getattr(_tlv, "__file__", "?"))
  print("CUSTOM EMOJI ENABLED  :", CUSTOM_EMOJI_ENABLED)
  print("BUTTON style/icon OK  :", _fac)
  print("=" * 50)
except Exception as _dex:
  print("Diagnostic failed:", _dex)

# Button icon ids (were referenced but never defined -> NameError on Payment Methods / Server 1 filters).
_ICON_OK = "5834600569242654097"
_ICON_NO = "5834870091325378855"

_EMOJI_ID_MAP = {}
_EMOJI_ID_RE = None


def _build_emoji_map():
  """plain emoji -> custom emoji id, built from the P_* constants of this file."""
  global _EMOJI_ID_RE
  found = {}
  for _k, _v in list(globals().items()):
    if _k.startswith('P_') and isinstance(_v, str):
      _m = re.fullmatch(r'<tg-emoji emoji-id="(\d+)">(.*?)</tg-emoji>', _v, re.S)
      if _m:
        found.setdefault(_m.group(2).replace('\ufe0f', ''), _m.group(1))
  _EMOJI_ID_MAP.clear()
  _EMOJI_ID_MAP.update(found)
  keys = sorted(found, key=len, reverse=True)
  _EMOJI_ID_RE = re.compile('(' + '|'.join(re.escape(k) for k in keys) + ')\ufe0f?') if keys else None


def emoji_to_custom(text):
  """Turn normal emoji in a message into Telegram custom emoji (known ids only)."""
  if not isinstance(text, str) or not text or not CUSTOM_EMOJI_ENABLED:
    return text
  try:
    if _EMOJI_ID_RE is None:
      _build_emoji_map()
    if _EMOJI_ID_RE is None:
      return text
    parts = re.split(r'(<tg-emoji\b[^>]*>.*?</tg-emoji>)', text, flags=re.S | re.I)
    for _i in range(0, len(parts), 2):
      parts[_i] = _EMOJI_ID_RE.sub(
        lambda m: '<tg-emoji emoji-id="%s">%s</tg-emoji>' % (_EMOJI_ID_MAP[m.group(1)], m.group(1)), parts[_i])
    return ''.join(parts)
  except Exception:
    return text


def custom_emoji_text(text):
  out = _custom_emoji_text_impl(text)
  try:
    return _scrub_private_hosts(out)
  except NameError:
    return out


def _custom_emoji_text_impl(text):
  """Return message text with plain emoji removed but <tg-emoji> kept intact.

  Country flags are rendered with Telegram custom emoji
  (``<tg-emoji emoji-id="...">fallback</tg-emoji>``). The plain-emoji scrubber
  below would otherwise delete the fallback flag inside that tag and leave an
  invalid/empty custom-emoji entity, so every <tg-emoji> block is protected
  first and restored at the very end.
  """
  if text is None:
    return text
  text = str(text)

  # If custom emoji are unavailable, keep the plain emoji fallbacks instead of
  # deleting them (otherwise every icon would disappear from the UI).
  if not CUSTOM_EMOJI_ENABLED:
    return strip_custom_emoji(text)

  protected = []

  def _keep(match):
    protected.append(match.group(0))
    return f"\x00TGEMOJI{len(protected) - 1}\x00"

  text = re.sub(r'<tg-emoji\b[^>]*>.*?</tg-emoji>', _keep, text,
                flags=re.DOTALL | re.IGNORECASE)
  text = re.sub(r'<emoji\s+id=["\'][^"\']+["\']>(.*?)</emoji>', r'\1', text, flags=re.DOTALL | re.IGNORECASE)
  # Remove emoji/pictograph/symbol ranges while retaining ordinary text and currency symbols.
  text = re.sub(r'[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]', '', text)

  for index, block in enumerate(protected):
    text = text.replace(f"\x00TGEMOJI{index}\x00", block)
  return text


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

os.makedirs("sessions", exist_ok=True)

# Always have an event loop before Telethon is created (Python 3.10+ / 3.12+ / 3.14 safe).
try:
  asyncio.get_running_loop()
except RuntimeError:
  # Python 3.12+ no longer implicitly creates a loop in this situation.
  asyncio.set_event_loop(asyncio.new_event_loop())

session_name = f"bot_session_{BOT_TOKEN.split(':')[0]}"
from telethon.sessions import StringSession as _BotStringSession
bot = TelegramClient(
  _BotStringSession(), API_ID, API_HASH,
  connection_retries=None, retry_delay=3, auto_reconnect=True, request_retries=5,
  flood_sleep_threshold=60,
)
bot.parse_mode = 'html'


def _looks_like_custom_emoji_error(exc):
  msg = str(exc).lower()
  return ('custom emoji' in msg or 'custom_emoji' in msg or 'emoji' in msg) and (
    'invalid' in msg or 'not allowed' in msg or 'only be used' in msg or 'premium' in msg
  )


def _patch_custom_emoji_fallback(client):
  """Re-send messages without <tg-emoji> if Telegram rejects custom emoji.

  This keeps the bot fully functional on older Telethon builds or on bot
  accounts that are not allowed to use custom emoji: the first rejected send
  disables custom emoji globally and the same message is retried with the
  plain emoji fallbacks.
  """
  import functools
  for name in ('send_message', 'edit_message', 'send_file', 'send_photo', 'send_document'):
    original = getattr(client, name, None)
    if original is None:
      continue

    @functools.wraps(original)
    async def wrapper(*args, __orig=original, **kwargs):
      global CUSTOM_EMOJI_ENABLED
      args = tuple(_scrub_private_hosts(a) if isinstance(a, str) else a for a in args)
      kwargs = {k: (_scrub_private_hosts(v) if isinstance(v, str) else v) for k, v in kwargs.items()}
      try:
        return await __orig(*args, **kwargs)
      except Exception as ex:
        if not CUSTOM_EMOJI_ENABLED or not _looks_like_custom_emoji_error(ex):
          raise
        # Only THIS message falls back to plain emoji. The global flag is no
        # longer switched off, otherwise one bad emoji id made every later
        # message in the bot lose its premium emoji.
        logger.warning(f"Custom emoji rejected ({ex}); retrying this message with plain emoji.")
        new_args = tuple(strip_custom_emoji(a) if isinstance(a, str) else a for a in args)
        new_kwargs = {k: (strip_custom_emoji(v) if isinstance(v, str) else v)
                      for k, v in kwargs.items()}
        return await __orig(*new_args, **new_kwargs)

    setattr(client, name, wrapper)


_patch_custom_emoji_fallback(bot)

db = sqlite3.connect(os.environ.get("DB_PATH", "otp_bot_final.db"), check_same_thread=False, timeout=20)
db.execute("PRAGMA journal_mode=WAL;")
cur = db.cursor()

active_orders = {}   
waiting_proof = {}   
deposit_input = {} 
admin_dep_state = {}  
user_spam_cooldown = {} 
session_buy_state = {}   
smm_order_state = {}
refill_state = {}
redeem_state = {}
digital_shop_state = {}

# Telegram callback_data is limited to 64 UTF-8 bytes. Country/account names
# can contain fancy Unicode characters which make callback_data exceed that
# limit. Always use a short stable token in buttons and resolve it back to the
# real database value when clicked. This keeps display names fully Unicode-safe.
def _country_token(country):
  return hashlib.sha256(str(country).encode("utf-8")).hexdigest()[:10]

def _resolve_country_ref(ref):
  ref = str(ref or "")
  # New compact token format.
  if re.fullmatch(r"[0-9a-f]{10}", ref):
    rows = cur.execute("SELECT DISTINCT country_name FROM stock").fetchall()
    for (name,) in rows:
      if _country_token(name) == ref:
        return name
  # Backward compatibility for old buttons which stored the literal name.
  return ref

user_locks = {}

def get_user_lock(uid):
  if uid not in user_locks:
    user_locks[uid] = asyncio.Lock()
  return user_locks[uid]

def setup_db():
  cur.executescript("""
  CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    total_deposited INTEGER DEFAULT 0,
    joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    banned INTEGER DEFAULT 0,
    discount INTEGER DEFAULT 0,
    terms_accepted INTEGER DEFAULT 1,
    username TEXT DEFAULT '',
    first_name TEXT DEFAULT '',
    frozen INTEGER DEFAULT 0
  );
  CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
  CREATE TABLE IF NOT EXISTS stock (
    phone TEXT PRIMARY KEY,
    session_file TEXT,
    country_name TEXT,
    country_icon TEXT DEFAULT '',
    account_year INTEGER,
    category TEXT DEFAULT 'Good',
    price INTEGER,
    available INTEGER DEFAULT 1,
    twofa TEXT DEFAULT 'None',
    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );
  CREATE TABLE IF NOT EXISTS auto_prices (
    country TEXT,
    year TEXT,
    price INTEGER,
    PRIMARY KEY (country, year)
  );
  CREATE TABLE IF NOT EXISTS deposits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount INTEGER,
    method_name TEXT,
    status TEXT, 
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );
  CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    country TEXT,
    year INTEGER,
    price INTEGER,
    phone TEXT,
    otp TEXT,
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );
  CREATE TABLE IF NOT EXISTS smm_orders (
    bot_order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    service_id INTEGER,
    link TEXT,
    quantity INTEGER,
    total_price REAL,
    smm_order_id TEXT,
    status TEXT DEFAULT 'Completed',
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );
  CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY,
    p_add_stock INTEGER DEFAULT 1,
    p_manage_stock INTEGER DEFAULT 1,
    p_stats INTEGER DEFAULT 1,
    p_bal INTEGER DEFAULT 1,
    p_settings INTEGER DEFAULT 1
  );
  CREATE TABLE IF NOT EXISTS custom_countries (
    code TEXT PRIMARY KEY,
    name TEXT,
    flag TEXT DEFAULT ''
  );
  CREATE TABLE IF NOT EXISTS force_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT,
    invite_url TEXT,
    title TEXT
  );
  CREATE TABLE IF NOT EXISTS force_join_requests (
    channel_id TEXT,
    user_id INTEGER,
    PRIMARY KEY (channel_id, user_id)
  );
  CREATE TABLE IF NOT EXISTS smm_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT
  );
  CREATE TABLE IF NOT EXISTS smm_services (
    service_id INTEGER PRIMARY KEY,
    category_id INTEGER,
    name TEXT,
    rate REAL,
    min INTEGER,
    max INTEGER,
    description TEXT
  );
  CREATE TABLE IF NOT EXISTS redeem_codes (
    code TEXT PRIMARY KEY,
    amount INTEGER NOT NULL,
    max_users INTEGER NOT NULL DEFAULT 1,
    used_count INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    active INTEGER DEFAULT 1
  );
  CREATE TABLE IF NOT EXISTS redeem_claims (
    code TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    claimed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (code, user_id)
  );
  CREATE TABLE IF NOT EXISTS s2_orders (
    order_id TEXT PRIMARY KEY,
    user_id INTEGER,
    country_code TEXT DEFAULT '',
    country_name TEXT DEFAULT '',
    number TEXT DEFAULT '',
    price INTEGER DEFAULT 0,
    status TEXT DEFAULT 'waiting',
    code TEXT DEFAULT '',
    password TEXT DEFAULT '',
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );
  CREATE TABLE IF NOT EXISTS digital_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    price INTEGER NOT NULL,
    photo_file_id TEXT DEFAULT '',
    photo_path TEXT DEFAULT '',
    file_path TEXT DEFAULT '',
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    active INTEGER DEFAULT 1
  );
  """)
  
  # Shop migration: optional preview image + separate required delivery file.
  try:
    cur.execute("ALTER TABLE digital_products ADD COLUMN file_path TEXT DEFAULT ''")
  except sqlite3.OperationalError:
    pass

  # Server 1 (Nobelots) migration: batch -> account number + one-time charge flag.
  try:
    cur.execute("ALTER TABLE s2_orders ADD COLUMN account_no TEXT DEFAULT ''")
  except sqlite3.OperationalError:
    pass
  try:
    cur.execute("ALTER TABLE s2_orders ADD COLUMN charged INTEGER DEFAULT 0")
  except sqlite3.OperationalError:
    pass

  # Server 1 terms gate: a user must tap "Agree and Continue" once.
  cur.execute(
    "CREATE TABLE IF NOT EXISTS s1_terms ("
    "user_id INTEGER PRIMARY KEY, accepted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")

  # Migration for payment UTR tracking / duplicate protection.
  try:
    cur.execute("ALTER TABLE deposits ADD COLUMN utr TEXT DEFAULT ''")
  except sqlite3.OperationalError:
    pass
  try:
    cur.execute("CREATE INDEX IF NOT EXISTS idx_deposits_utr ON deposits(utr)")
  except Exception:
    pass

  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('imap_server', 'imap.gmail.com')")
  _seed_imap_email = CLONE_CONFIG.get('gmail', '') if IS_CLONE else 'aroy327154@gmail.com'
  _seed_imap_pass = CLONE_CONFIG.get('gmail_app_password', '') if IS_CLONE else 'rerg jyiu dhyx fciq'
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('imap_email', ?)", (_seed_imap_email,))
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('imap_password', ?)", (_seed_imap_pass,))
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('fampay_upi', 'fampay@upi')")
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('fampay_name', ?)", (STORE_DISPLAY,))
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bharatpe_upi', '')")
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bharatpe_name', ?)", (STORE_DISPLAY,))
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bharatpe_enabled', 'off')")
  _bp_def_mid = '' if IS_CLONE else '64727736'
  _bp_def_tok = '' if IS_CLONE else '74951044d18f4cf397955c4a52a78375'
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bharatpe_merchant_id', ?)", (_bp_def_mid,))
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bharatpe_token', ?)", (_bp_def_tok,))
  # Fill the defaults if an earlier run left these empty (owner bot only).
  if _bp_def_mid:
    cur.execute("UPDATE settings SET value=? WHERE key='bharatpe_merchant_id' AND TRIM(COALESCE(value,''))=''", (_bp_def_mid,))
    cur.execute("UPDATE settings SET value=? WHERE key='bharatpe_token' AND TRIM(COALESCE(value,''))=''", (_bp_def_tok,))
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bharatpe_trusted_senders', 'bharatpe')")
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('manual_upi', 'manual@upi')")
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('manual_name', ?)", (STORE_DISPLAY + ' Manual',))
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('fampay_enabled', 'on')")
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('manual_enabled', 'on')")
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('usdt_enabled', 'on')")
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('usdt_address', '')")
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('usdt_network', 'TRC20')")
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('log_channel_id', ?)", ('' if IS_CLONE else '-1003940330621',))
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('support_url', ?)", ('' if IS_CLONE else 'https://t.me/AADITYAXOFFICAL',))
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('support_channel_url', ?)", ('' if IS_CLONE else 'https://t.me/+yhaYNpSyF5U3Y2Q9',))
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('smm_api_url', '')")
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('smm_api_key', '')")
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('server1_api_url', 'https://api.lzt.market')")
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('server1_api_key', '')")
  cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('server1_margin', '0')")

  # Cloned bots only: store the MAIN bot API *docs* URL for the admin panel.
  # Do NOT overwrite server1/s2/s3 API base URLs — those clients speak LZT / Tiger,
  # not the Reseller docs host. API keys are created/stored on the MAIN bot only.
  if IS_CLONE and MAIN_API_DOCS_URL:
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('api_docs_url', ?)", (MAIN_API_DOCS_URL,))
    cur.execute(
      "UPDATE settings SET value=? WHERE key='api_docs_url' AND TRIM(COALESCE(value,''))=''",
      (MAIN_API_DOCS_URL,))
    # Heal bad seed from an earlier build that pointed provider URLs at the docs host.
    for _k, _default in (
      ("server1_api_url", "https://api.lzt.market"),
      ("s2_wa_url", "https://api.tiger-sms.com/stubs/handler_api.php"),
      ("s3_api_url", "https://api.tiger-sms.com/stubs/handler_api.php"),
    ):
      cur.execute(
        "UPDATE settings SET value=? WHERE key=? AND ("
        "value LIKE '%aaditya-store-bot.onrender.com%' OR value LIKE '%/docs%')",
        (_default, _k))

  # Migrate an existing install off the old Phantom / Nobelots API to Lolzteam Market API.
  cur.execute(
    "UPDATE settings SET value='https://api.lzt.market' "
    "WHERE key='server1_api_url' AND (value LIKE '%phantomtg%' OR value LIKE '%nobelots%' OR value='')")
  cur.execute(
    "UPDATE settings SET value='' WHERE key='server1_api_key' AND (value LIKE 'ph_%' OR value LIKE 'nbl_live_%')")
  db.commit()

setup_db()
# Admin dashboard/user lookup migrations (safe for existing databases).
for _stmt in (
  "ALTER TABLE users ADD COLUMN username TEXT DEFAULT ''",
  "ALTER TABLE users ADD COLUMN first_name TEXT DEFAULT ''",
  "ALTER TABLE users ADD COLUMN frozen INTEGER DEFAULT 0",
  "ALTER TABLE users ADD COLUMN freeze_until INTEGER DEFAULT 0",
  "ALTER TABLE users ADD COLUMN freeze_reason TEXT DEFAULT ''",
  "ALTER TABLE users ADD COLUMN restricted_by INTEGER DEFAULT 0",
  "ALTER TABLE users ADD COLUMN restricted_at INTEGER DEFAULT 0",
):
  try: cur.execute(_stmt)
  except sqlite3.OperationalError: pass
cur.execute("""CREATE TABLE IF NOT EXISTS moderation_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  target_id INTEGER, actor_id INTEGER, action TEXT, note TEXT DEFAULT '',
  created_at INTEGER)""")
# Self-heal: the owner and every admin can never stay frozen/banned.
try:
  cur.execute("UPDATE users SET frozen=0, banned=0, freeze_until=0 WHERE user_id=? OR user_id IN (SELECT user_id FROM admins)", (ADMIN_ID,))
except sqlite3.OperationalError: pass
db.commit()

# One public/global order number shared by every selling service.
cur.execute("""CREATE TABLE IF NOT EXISTS global_orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  service TEXT NOT NULL,
  local_ref TEXT NOT NULL,
  user_id INTEGER NOT NULL,
  amount REAL DEFAULT 0,
  status TEXT DEFAULT 'PROCESSING',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(service, local_ref)
)""")
cur.execute("CREATE INDEX IF NOT EXISTS idx_global_orders_user ON global_orders(user_id)")
try: cur.execute("ALTER TABLE global_orders ADD COLUMN refunded INTEGER NOT NULL DEFAULT 0")
except sqlite3.OperationalError: pass
db.commit()

def _global_order_register(service, local_ref, user_id, amount, status='PROCESSING'):
  """Create/reuse a single global ID for a service's native order reference."""
  service = str(service or 'unknown').lower()
  local_ref = str(local_ref)
  cur.execute("INSERT OR IGNORE INTO global_orders(service,local_ref,user_id,amount,status) VALUES(?,?,?,?,?)",
              (service, local_ref, int(user_id), float(amount or 0), str(status or 'PROCESSING')))
  row = cur.execute("SELECT id FROM global_orders WHERE service=? AND local_ref=?", (service, local_ref)).fetchone()
  db.commit()
  gid = f"ATS-{int(row[0]):08d}" if row else ""
  if gid:
    logger.info("GLOBAL_ORDER_CREATED id=%s service=%s local_ref=%s user_id=%s amount=%.2f status=%s",
                gid, service, local_ref, int(user_id), float(amount or 0), str(status or 'PROCESSING'))
  return gid

def _global_order_id_for(service, local_ref):
  row = cur.execute("SELECT id FROM global_orders WHERE service=? AND local_ref=?",
                    (str(service or '').lower(), str(local_ref))).fetchone()
  return f"ATS-{int(row[0]):08d}" if row else ""

def _global_order_row(global_id):
  raw = str(global_id or '').strip().upper().replace('#','')
  if raw.startswith('ATS-'): raw = raw[4:]
  if not raw.isdigit(): return None
  return cur.execute("SELECT id,service,local_ref,user_id,amount,status,created_at FROM global_orders WHERE id=?", (int(raw),)).fetchone()

def _spam_status_text(value):
  if isinstance(value, dict):
    # Some API responses wrap the spam flag in an object.
    for key in ("blocked", "is_blocked", "spam_block", "value", "status"):
      if key in value:
        value = value.get(key)
        break
  if isinstance(value, str):
    label = value.strip().lower().replace("_", " ").replace("-", " ")
    if label in ("blocked", "spam blocked", "yes", "true", "1", "active", "on"):
      return "Spam Blocked"
    if label in ("free", "spam free", "not blocked", "no", "false", "0", "none", "off", "clean"):
      return "Spam Free"
  state = _s1_truthy(value)
  if state is None:
    return 'Not Checked'
  return 'Spam Blocked' if state else 'Spam Free'


# Requested default Support/Updates destinations. Only migrate the old
# built-in defaults; a custom URL previously configured by the admin is kept.
def ensure_requested_default_links():
  if IS_CLONE:
    return
  defaults = {
    'support_url': 'https://t.me/AADITYAXOFFICAL',
    'support_channel_url': 'https://t.me/+yhaYNpSyF5U3Y2Q9',
  }
  old_defaults = {
    'support_url': {'', 'https://t.me/m/P7am0xdlZmE1'},
    'support_channel_url': {'', 'https://t.me/', 'https://t.me/m/P7am0xdlZmE1'},
  }
  for key, default in defaults.items():
    row = cur.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    current = (row[0] or '').strip() if row else ''
    valid = current.startswith(('http://', 'https://', 'tg://')) and len(current) > len('https://t.me/')
    if current in old_defaults[key] or not valid:
      cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, default))
  db.commit()

ensure_requested_default_links()

# Migrate previously embedded Gmail App Passwords to the current one.
# A custom password configured by the admin from the panel is preserved.
try:
  _imap_user = cur.execute("SELECT value FROM settings WHERE key='imap_email'").fetchone()
  _imap_pwd = cur.execute("SELECT value FROM settings WHERE key='imap_password'").fetchone()
  _old_pwds = {'yascqrsoaunpdnbc', 'foorirclisyrjcva', ''}
  if ((not IS_CLONE) and (_imap_user and (_imap_user[0] or '').strip() == 'aroy327154@gmail.com') and
      (_imap_pwd is not None) and
      re.sub(r"\s+", "", (_imap_pwd[0] or '').strip()) in _old_pwds):
    cur.execute("UPDATE settings SET value=? WHERE key='imap_password'", ('rerg jyiu dhyx fciq',))
    db.commit()
except Exception:
  pass

try:
  cur.execute("UPDATE settings SET value='Aaditya Tg Store' WHERE key='fampay_name' AND value IN ('Aaditya','Aaditya Store')")
  cur.execute("UPDATE settings SET value='Aaditya Tg Store Manual' WHERE key='manual_name' AND value IN ('Aaditya Manual','Acc Store Manual')")
  db.commit()
except Exception:
  pass


# Bot status has THREE modes, cycled by one admin button:
#   ON  ->  MAINTENANCE  ->  OFF  ->  ON ...
# Admins can always use the bot. Normal users are blocked in MAINTENANCE and OFF.
BOT_STATUS_NEXT = {'on': 'maintenance', 'maintenance': 'off', 'off': 'on'}
BOT_STATUS_LABEL = {'on': 'Bot ON', 'maintenance': 'Maintenance', 'off': 'Bot OFF'}


def get_bot_status():
  try:
    res = cur.execute("SELECT value FROM settings WHERE key='bot_status'").fetchone()
  except Exception:
    return 'on'
  v = str(res[0]).strip().lower() if res and res[0] is not None else 'on'
  return v if v in BOT_STATUS_NEXT else 'on'


def set_bot_status(value):
  value = value if value in BOT_STATUS_NEXT else 'on'
  cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('bot_status', ?)", (value,))
  db.commit()
  return value


def is_bot_online():
  return get_bot_status() == 'on'


def bot_block_text():
  """Message shown to normal users while the bot is not ON."""
  if get_bot_status() == 'maintenance':
    return (f"{P_WARN} <b>Bot is under maintenance.</b>\n\n"
            "We are improving things for you. Please try again in a little while.")
  return (f"{P_OFF} <b>Bot is currently OFF.</b>\n\n"
          "Please come back later.")


def is_admin(uid):
  if uid == ADMIN_ID: return True
  row = cur.execute("SELECT user_id FROM admins WHERE user_id=?", (uid,)).fetchone()
  return bool(row)

def has_perm(uid, perm):
  if uid == ADMIN_ID: return True
  row = cur.execute(f"SELECT {perm} FROM admins WHERE user_id=?", (uid,)).fetchone()
  return bool(row and row[0] == 1)

def get_all_admin_ids():
  """Return the owner plus every admin configured in the admins table, without duplicates."""
  ids = [ADMIN_ID]
  try:
    rows = cur.execute("SELECT user_id FROM admins").fetchall()
    ids.extend(int(row[0]) for row in rows if row and row[0])
  except Exception as ex:
    logger.error(f"Failed to load admin IDs: {ex}")
  return list(dict.fromkeys(ids))

async def send_admins_file(photo, caption, buttons=None):
  """Forward a payment screenshot to the owner and all configured admins.
  1) normal send  2) re-upload the image bytes  3) text-only review (so Accept/Reject still works)."""
  sent = 0
  blob = None
  for admin_id in get_all_admin_ids():
    try:
      await bot.send_file(admin_id, photo, caption=custom_emoji_text(caption), buttons=buttons)
      sent += 1
      continue
    except Exception as ex:
      logger.error(f"Failed to send admin review to {admin_id}: {ex}")
    try:
      if blob is None:
        blob = await bot.download_media(photo, file=bytes)
      if blob:
        import io as _io
        bio = _io.BytesIO(blob)
        bio.name = "payment_proof.jpg"
        await bot.send_file(admin_id, bio, caption=custom_emoji_text(caption), buttons=buttons)
        sent += 1
        continue
    except Exception as ex:
      logger.error(f"Re-upload of screenshot to admin {admin_id} failed: {ex}")
    try:
      await bot.send_message(admin_id, custom_emoji_text(
        caption + "\n\n<i>(Screenshot could not be attached - ask the user to resend it.)</i>"),
        buttons=buttons)
      sent += 1
    except Exception as ex:
      logger.error(f"Text-only admin review to {admin_id} failed: {ex}")
  return sent

def ensure_user(uid, username=None, first_name=None):
  cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
  if username is not None or first_name is not None:
    cur.execute("UPDATE users SET username=COALESCE(?,username), first_name=COALESCE(?,first_name) WHERE user_id=?",
                (str(username or ''), str(first_name or ''), int(uid)))
  db.commit()

def get_usdt_rate():
  res = cur.execute("SELECT value FROM settings WHERE key='usdt_rate'").fetchone()
  try: return float(res[0]) if res else 94.0
  except: return 94.0

def _normalize_tg_url(raw_url, fallback=""):
  """Normalize a Telegram username/link without ever returning an invalid t.me root URL."""
  url = str(raw_url or "").strip()
  if not url:
    return fallback
  if url.startswith("@"): 
    url = "https://t.me/" + url[1:]
  elif not url.startswith(("http://", "https://")):
    url = "https://t.me/" + url.lstrip("/")
  # Telegram rejects bare https://t.me/ as a Button.url destination.
  if re.fullmatch(r"https?://t\.me/?", url, flags=re.IGNORECASE):
    return fallback
  # Basic URL sanity check; keep normal t.me invite links and usernames.
  if not re.match(r"^https?://(?:t\.me|telegram\.me)/[^\s<>]+$", url, flags=re.IGNORECASE):
    return fallback
  return url

def _safe_url_button(label, raw_url):
  """Build a Telegram URL button only when the URL is valid. Never let a bad admin/config URL crash a whole message."""
  url = _normalize_tg_url(raw_url, "")
  if not url:
    return None
  try:
    return Button.url(str(label)[:64], url)
  except Exception as ex:
    logger.error(f"Invalid URL button skipped: {ex}")
    return None

async def _broadcast_deliver(chat_id, payload, media, buttons):
  """Send one broadcast item (text, or media + caption). payload = (text, entities|None).

  With entities the message is sent exactly as the admin made it, so premium (custom)
  emoji, bold, spoilers, links etc. are all kept. Retries once on FloodWait.
  """
  text, ents = payload
  text = text or ""
  kw = {"formatting_entities": ents, "parse_mode": None} if ents else {"parse_mode": 'html'}
  for attempt in range(3):
    try:
      if media is not None:
        if len(text) <= 1024:
          return await bot.send_file(chat_id, media, caption=text or None, buttons=buttons, **kw)
        await bot.send_file(chat_id, media)
      if ents:
        return await bot.send_message(chat_id, text, buttons=buttons, **kw)
      # Typed-HTML articles longer than Telegram's 4096 limit are split on line breaks.
      parts, cur_part = [], ""
      for line in text.split("\n"):
        if len(cur_part) + len(line) + 1 > 4000:
          parts.append(cur_part); cur_part = ""
        cur_part += line + "\n"
      if cur_part.strip():
        parts.append(cur_part)
      for i, part in enumerate(parts or [" "]):
        last = i == len(parts) - 1
        await bot.send_message(chat_id, part, buttons=buttons if last else None, parse_mode='html')
      return
    except FloodWaitError as ex:
      if attempt >= 2:
        raise
      await asyncio.sleep(min(int(getattr(ex, "seconds", 5)) + 1, 60))


def get_support_url():
  # Admin Panel -> Support URL is the single source of truth for Support.
  res = cur.execute("SELECT value FROM settings WHERE key='support_url'").fetchone()
  return _normalize_tg_url(res[0] if res and res[0] else "", "")

def get_support_channel_url():
  # Admin Panel -> Support/Updates Channel is used for the Updates button.
  res = cur.execute("SELECT value FROM settings WHERE key='support_channel_url'").fetchone()
  return _normalize_tg_url(res[0] if res and res[0] else "", "")

def _has_valid_button_url(url):
  return bool(_normalize_tg_url(url, ""))

def get_fampay_upi():
  res = cur.execute("SELECT value FROM settings WHERE key='fampay_upi'").fetchone()
  return res[0] if res and res[0] else "fampay@upi"

def get_fampay_name():
  res = cur.execute("SELECT value FROM settings WHERE key='fampay_name'").fetchone()
  return res[0] if res and res[0] else STORE_DISPLAY

def get_bharatpe_upi():
  res = cur.execute("SELECT value FROM settings WHERE key='bharatpe_upi'").fetchone()
  return (res[0] or '').strip() if res and res[0] else ""

def get_bharatpe_name():
  res = cur.execute("SELECT value FROM settings WHERE key='bharatpe_name'").fetchone()
  return res[0] if res and res[0] else STORE_DISPLAY

def get_bharatpe_senders():
  """Comma separated sender substrings of BharatPe payment e-mails."""
  res = cur.execute("SELECT value FROM settings WHERE key='bharatpe_trusted_senders'").fetchone()
  return (res[0] or '').strip() if res and res[0] else "bharatpe"

def get_bharatpe_api():
  """(merchant_id, token) of the BharatPe merchant account. Admin-only data:
  never print / log / send these to users."""
  return (get_setting('bharatpe_merchant_id', '') or '').strip(), (get_setting('bharatpe_token', '') or '').strip()

def bharatpe_api_ready():
  mid, tok = get_bharatpe_api()
  return bool(mid and tok)

def _mask_secret(v, keep=4):
  v = str(v or '')
  if not v:
    return 'Not set'
  return ('*' * max(4, len(v) - keep)) + v[-keep:] if len(v) > keep else '*' * len(v)

# Automatic (IMAP verified) methods -> (UPI getter, name getter, DB label, app name)
AUTO_METHODS = ('FamPay Automatic', 'BharatPe Automatic')
def auto_method_label(method):
  return 'BharatPe UPI' if method == 'BharatPe Automatic' else 'FamPay UPI'
def auto_method_app(method):
  return 'BharatPe' if method == 'BharatPe Automatic' else 'FamPay'
def bharatpe_available():
  """BharatPe Automatic is shown only when ON, a UPI ID and the API Merchant ID + Token are set."""
  return payment_enabled('bharatpe_enabled') and bool(get_bharatpe_upi()) and bharatpe_api_ready()


import threading as _threading
_settings_tls = _threading.local()


def _settings_conn():
  """One read connection per thread. The shared `cur` must not be used from
  the background country crawl ("Recursive use of cursors not allowed")."""
  c = getattr(_settings_tls, "conn", None)
  if c is None:
    c = sqlite3.connect(os.environ.get("DB_PATH", "otp_bot_final.db"), check_same_thread=False, timeout=20)
    _settings_tls.conn = c
  return c


def get_setting(key, default=''):
  try:
    row = _settings_conn().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
  except Exception:
    row = None
  return row[0] if row and row[0] is not None else default

def set_setting(key, value):
  cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
  db.commit()

# ================= REFER AND EARN =================
def _init_referral_tables():
  cur.execute("CREATE TABLE IF NOT EXISTS referrals (referred_id INTEGER PRIMARY KEY, "
              "referrer_id INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
              "total_bonus REAL DEFAULT 0)")
  cur.execute("CREATE TABLE IF NOT EXISTS referral_earnings (id INTEGER PRIMARY KEY AUTOINCREMENT, "
              "referrer_id INTEGER, referred_id INTEGER, deposit_amount REAL, percent REAL, "
              "bonus REAL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
  db.commit()


_init_referral_tables()


def get_refer_percent():
  """Referral bonus % (admin sets it from the admin panel, default 5)."""
  try:
    v = float(get_setting('refer_percent', '5') or 5)
  except Exception:
    v = 5.0
  return max(0.0, min(v, 100.0))


def get_usdt_address(): return (get_setting('usdt_address', '') or '').strip()
def get_usdt_network(): return (get_setting('usdt_network', 'TRC20') or 'TRC20').strip()
def usdt_manual_available():
  """USDT Manual is shown to users only when it is ON and an address is configured."""
  return payment_enabled('usdt_enabled') and bool(get_usdt_address())
def get_manual_upi(): return get_setting('manual_upi', 'manual@upi')
def get_manual_name(): return get_setting('manual_name', STORE_DISPLAY + ' Manual')
def payment_enabled(key): return get_setting(key, 'on').lower() == 'on'

_MIN_DEP_KEYS = {
  'FamPay Automatic': ('min_dep_fampay', 'FamPay'),
  'BharatPe Automatic': ('min_dep_bharatpe', 'BharatPe'),
  'UPI Manual': ('min_dep_manual', 'Manual'),
  'USDT Manual': ('min_dep_crypto', 'Crypto'),
}
def get_min_deposit(method):
  """Minimum deposit (in INR) for a payment method. Default is Rs 10."""
  key = _MIN_DEP_KEYS.get(method, ('min_dep_manual', ''))[0]
  try:
    v = int(float(get_setting(key, '10') or 10))
    return v if v > 0 else 10
  except Exception:
    return 10

_LOG_CH_DEFAULT = 0 if IS_CLONE else -1003940330621

def get_log_channel_id():
  res = cur.execute("SELECT value FROM settings WHERE key='log_channel_id'").fetchone()
  try: return int(res[0]) if res and res[0] else _LOG_CH_DEFAULT
  except: return _LOG_CH_DEFAULT

SELLING_LOGS_DEFAULT_LINK = "" if IS_CLONE else "https://t.me/+dWA-jgCaNBMyNzRl"


def get_selling_logs_link():
  """Link used by the main-menu 'Selling Logs' button (auto-generated from the
  configured logs channel; falls back to the built-in link)."""
  link = get_setting('selling_logs_link', '').strip()
  return link if link and _has_valid_button_url(link) else SELLING_LOGS_DEFAULT_LINK


async def generate_selling_logs_link(channel_id):
  """Build a join link for the logs channel. Returns (link, reason)."""
  try:
    peer = await _get_channel_entity(channel_id)
    try:
      ent = await bot.get_entity(peer)
      uname = getattr(ent, 'username', None)
      if not uname:
        for u in (getattr(ent, 'usernames', None) or []):
          if getattr(u, 'active', False) and getattr(u, 'username', None):
            uname = u.username
            break
      if uname:
        return f"https://t.me/{uname}", ""
    except Exception:
      pass
    from telethon.tl.functions.messages import ExportChatInviteRequest
    res = await bot(ExportChatInviteRequest(peer=peer))
    link = getattr(res, 'link', '') or ''
    if link:
      return link, ""
    return "", "Telegram did not return an invite link."
  except Exception as ex:
    logger.warning(f"Selling logs link generation failed for {channel_id}: {ex}")
    return "", str(ex)


async def refresh_selling_logs_link(channel_id=None):
  """Generate + store the link. Returns the stored link or ''."""
  link, _ = await generate_selling_logs_link(channel_id if channel_id is not None else get_log_channel_id())
  if link:
    set_setting('selling_logs_link', link)
  return link


def clean_html_url(raw_url):
  if not raw_url: return ""
  clean = re.sub(r'<.*?>', '', raw_url)
  match = re.search(r'https?://[^\s<>"]+', clean)
  if match:
    return match.group(0).strip()
  return clean.strip()

def get_smm_api_config():
  url = cur.execute("SELECT value FROM settings WHERE key='smm_api_url'").fetchone()
  key = cur.execute("SELECT value FROM settings WHERE key='smm_api_key'").fetchone()
  raw_url = url[0].strip() if url and url[0] else ""
  return (clean_html_url(raw_url), key[0].strip() if key and key[0] else "")

def get_ssl_context():
  ctx = ssl.create_default_context()
  ctx.check_hostname = False
  ctx.verify_mode = ssl.CERT_NONE
  return ctx

def fetch_smm_services_from_api(api_url, api_key):
  api_url = clean_html_url(api_url)
  headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive'
  }
  try:
    data = urllib.parse.urlencode({'key': api_key, 'action': 'services'}).encode('utf-8')
    req = urllib.request.Request(api_url, data=data, method='POST', headers=headers)
    ctx = get_ssl_context()
    with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
      res_text = response.read().decode('utf-8', errors='ignore')
      return json.loads(res_text)
  except Exception as e:
    logger.error(f"SMM API POST Fetch Error: {e}")
    try:
      get_url = f"{api_url.rstrip('/')}?key={api_key}&action=services"
      req = urllib.request.Request(get_url, headers=headers)
      ctx = get_ssl_context()
      with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
        res_text = response.read().decode('utf-8', errors='ignore')
        return json.loads(res_text)
    except Exception as e2:
      logger.error(f"SMM API GET Fetch Error: {e2}")
      return None

def place_smm_order_api(api_url, api_key, service_id, link, quantity):
  api_url = clean_html_url(api_url)
  headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'en-US,en;q=0.9',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'Origin': api_url.split('/api')[0] if '/api' in api_url else api_url,
    'Referer': api_url,
    'X-Requested-With': 'XMLHttpRequest'
  }
  try:
    data = urllib.parse.urlencode({
      'key': api_key,
      'action': 'add',
      'service': service_id,
      'link': link,
      'quantity': quantity
    }).encode('utf-8')
    
    req = urllib.request.Request(api_url, data=data, headers=headers, method='POST')
    ctx = get_ssl_context()
    with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
      res_text = response.read().decode('utf-8', errors='ignore')
      
      if "<html" in res_text.lower() or "cloudflare" in res_text.lower():
        logger.error("Cloudflare blocked the SMM API order request.")
        return {"error": "Cloudflare security block! Please whitelist server IP in panel admin."}
        
      return json.loads(res_text)
  except Exception as e:
    logger.error(f"SMM Order API Error: {e}")
    return {"error": f"API Connection Error: {str(e)}"}

def refill_smm_order_api(api_url, api_key, smm_order_id):
  api_url = clean_html_url(api_url)
  headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
  }
  try:
    data = urllib.parse.urlencode({
      'key': api_key,
      'action': 'refill',
      'order': smm_order_id
    }).encode('utf-8')
    req = urllib.request.Request(api_url, data=data, headers=headers, method='POST')
    ctx = get_ssl_context()
    with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
      res_text = response.read().decode('utf-8', errors='ignore')
      return json.loads(res_text)
  except Exception as e:
    logger.error(f"SMM Refill API Error: {e}")
    return {"error": str(e)}

# ================= SERVER 1 — LOLZTEAM MARKET API (LZT MARKET) =================
# Server 1 is powered by the Lolzteam Market API (https://api.lzt.market).
#   GET  /me                                    -> profile + wallet balance
#   GET  /telegram                              -> search/list Telegram accounts
#   GET  /{item_id}                             -> account info + auth_key/dc_id
#   POST /{item_id}/fast-buy                    -> check & purchase account
#   GET  /{item_id}/telegram-login-code         -> Telegram login code (OTP)
#   POST /{item_id}/telegram-reset-authorizations -> terminate other sessions
# Auth: Authorization: Bearer <LZT_TOKEN> (with `market` scope)
LZT_BASE_URL = "https://api.lzt.market"
NOBELOTS_BASE_URL = LZT_BASE_URL
NOBELOTS_API_SERVER = 1

SERVER_DEFS = {
  1: {
    "name": "Server 1",
    "label": "Server 1 [ Cheap TG Accounts ]",
    "url_key": "server1_api_url",
    "key_key": "server1_api_key",
    "margin_key": "server1_margin",
    "default_url": LZT_BASE_URL,
    "api_server": NOBELOTS_API_SERVER,
    "default_margin": 0.0,
    "kind": "lzt_market",
  },
  2: {
    "name": "Server 2",
    "label": "Server 2 [ WhatsApp Accounts ]",
    "url_key": "s2_wa_url",
    "key_key": "s2_wa_api_key",
    "margin_key": "s2_wa_margin",
    "default_url": "https://api.tiger-sms.com/stubs/handler_api.php",
    "default_margin": 25.0,
    "kind": "tiger",
  },
  3: {
    "name": "Server 3",
    "label": "Server 3 [ ALL APP OTP ]",
    "url_key": "s3_api_url",
    "key_key": "s3_api_key",
    "margin_key": "s3_margin",
    "default_url": "https://api.tiger-sms.com/stubs/handler_api.php",
    "default_margin": 25.0,
    "kind": "s3",
  },
}

# Countries are cached briefly so paging does not burn the 60 req/min limit.
_s2_countries_cache = {"ts": 0.0, "data": []}
S2_COUNTRIES_TTL = 900   # full re-read every 30 min (shares the LZT category-search limit)
S2_COUNTRIES_PER_PAGE = 8

# ---- Country flag custom emoji (Telegram custom emoji IDs) ----
# Country code -> Telegram custom emoji id. These render as premium animated
# flags inside message text. Country buttons also carry the same flag as their
# icon (icon_custom_emoji_id).
COUNTRY_FLAGS = {
  "AF": "5291937511591925566", "AX": "5294077418917616055",
  "AL": "5294202819077756005", "DZ": "5294048127240655242",
  "AS": "5291994273879709721", "AD": "5294215205763434181",
  "AO": "5294516785482062829", "AI": "5292186323342350940",
  "AG": "5294005972136647964", "AR": "5292208210495689627",
  "AM": "5291978717508164018", "AW": "5294007002928798927",
  "AU": "5294444247779399477", "AT": "5291975174160145850",
  "AZ": "5294323533428579078", "BS": "5294031587321600012",
  "BH": "5294108398516720753", "BD": "5291824687096027834",
  "BB": "5294526187165471742", "BY": "5294134426018536120",
  "BE": "5291774466043435275", "BZ": "5294171848068584842",
  "BJ": "5293984969746566866", "BT": "5294121983498277263",
  "BO": "5294201479047957700", "BW": "5294026179957772585",
  "BR": "5291892229751723900", "BN": "5292098293692650297",
  "BG": "5294308947719640437", "BF": "5294153164960848949",
  "BI": "5294051631933967760", "KH": "5294225191562400452",
  "CM": "5291997306126626950", "CA": "5292290347450259214",
  "CV": "5292203503211535593", "CF": "5294210571493724819",
  "TD": "5291780728105753403", "CL": "5294231037012888049",
  "CN": "5294068833277990704", "CO": "5294010206974397371",
  "KM": "5294351381996521508", "CG": "5294035229453865597",
  "CK": "5292098684534675100", "CR": "5292063805105263554",
  "CI": "5293991322003200135", "HR": "5291999676948569127",
  "CU": "5291963947115631526", "CY": "5294062721539526918",
  "CZ": "5294242852467923382", "DK": "5294531860817268837",
  "DJ": "5294127214768468283", "DM": "5294485513825178032",
  "DO": "5294522197140857947", "EC": "5292083733753517221",
  "EG": "5293992082212409502", "SV": "5294337307388695687",
  "GB-ENG": "5294410107084365278", "GQ": "5292170045416297012",
  "ER": "5291922054004625949", "EE": "5291951143818123103",
  "ET": "5292245976143124155", "EU": "5291992809295861098",
  "GI": "5292055799286224027", "GM": "5294399820637688352",
  "GL": "5292014752283774878", "FI": "5294049961191690629",
  "FR": "5291817660529533837", "GA": "5294321325815389139",
  "GE": "5294349389131697267", "DE": "5292013274815028523",
  "GH": "5294347396266873249", "GR": "5291948395039054764",
  "GW": "5294409819321550432", "GT": "5294336633078831209",
  "GN": "5291892096607739008", "GY": "5292062692708736193",
  "HT": "5292045130587462814", "HN": "5291901034434682297",
  "HK": "5292166459118606932", "HU": "5294229581018975260",
  "IS": "5294354358408859664", "IN": "5291933173674957761",
  "IR": "5294220170745630736", "IQ": "5294325010897327367",
  "IE": "5294471971793293647", "IM": "5294318478252070646",
  "IL": "5294069056616289553", "IT": "5291826830284709120",
  "JM": "5294505107465982830", "JP": "5291799063321139445",
  "JE": "5291950280529697493", "JO": "5291988613112814801",
  "KZ": "5294227175837290463", "KE": "5292111852904416801",
  "KI": "5294538934628405146", "KP": "5294193812531333564",
  "KR": "5294408281723262763", "KW": "5292066437920218075",
  "KG": "5292091954320922577", "LA": "5291981530711746037",
  "LV": "5292236016113966127", "LB": "5294193108156699621",
  "LS": "5292040693886247604", "LR": "5291793810576137439",
  "LY": "5291858711826946840", "LI": "5292048742654957785",
  "LT": "5294343084119708700", "LU": "5294423709245787718",
  "MK": "5294023611567332075", "MG": "5291991568050312348",
  "MW": "5294241881805312589", "MY": "5291858351049696702",
  "MV": "5292004203844097218", "ML": "5292086972158858331",
  "MT": "5294532213004588353", "MH": "5294180730060954484",
  "MR": "5294429743674840973", "MU": "5294127824653797277",
  "MX": "5294535073452809778", "FM": "5291838156113470124",
  "MD": "5294158486425325375", "MC": "5294378161117614233",
  "MN": "5294316532631883496", "MA": "5292108962391414885",
  "MZ": "5294086708931874940", "MM": "5294254478944393569",
  "NA": "5292021761670404922", "NR": "5294463274484521342",
  "NP": "5294458756178924088", "NL": "5291917797692042265",
  "NZ": "5294189019347833274", "NI": "5294240825243358100",
  "NE": "5291809418487290691", "NG": "5294456308047563965",
  "NU": "5294471336138134209", "NO": "5291761718580502030",
  "OM": "5291813666209946812", "PK": "5291825606219029010",
  "PS": "5294289826525238172", "PA": "5291959935616178405",
  "PG": "5291917995260533077", "PY": "5294525611639852679",
  "PH": "5291798075478661634", "PE": "5292099427564018941",
  "PL": "5292190970496963836", "PT": "5294436555492973610",
  "PR": "5292121516580820347", "QA": "5292166360334357676",
  "RO": "5294107724206856227", "RU": "5294335323113807278",
  "RW": "5294191265615729158", "SM": "5292147350809106831",
  "ST": "5292183188016222701", "SA": "5294163983983463099",
  "GB-SCT": "5294434665707368018", "SN": "5292087023698466689",
  "RS": "5294458584380230360", "SC": "5291891186074672309",
  "SL": "5294494314213167952", "SG": "5294451304410663668",
  "SK": "5294538440707166931", "SI": "5294279359689938006",
  "SB": "5294283890880433237", "SO": "5294058817414255960",
  "ZA": "5294325281480266304", "ES": "5294513087515216901",
  "LK": "5292102670264328257", "SD": "5294177148058228060",
  "SR": "5294396668131692138", "SZ": "5294312482477724867",
  "SE": "5291737091238026321", "CH": "5291791748991835084",
  "SY": "5294013428199869487", "TW": "5294095745543069603",
  "TJ": "5294120269806328883", "TZ": "5292146096678658977",
  "TH": "5293994384314882755", "TG": "5294097669688415562",
  "TO": "5294283689016973348", "TT": "5294362935458548705",
  "TN": "5294484680601521871", "TR": "5293993400767367408",
  "TM": "5294098958178603764", "TC": "5294320866253884749",
  "US": "5294244076533600593", "UG": "5294192317882716626",
  "AE": "5294314831824835370", "GB": "5293993521026453119",
  "UA": "5294263837678131580", "VU": "5294448585696368047",
  "UZ": "5294217645304864345", "UY": "5291928449210932974",
  "VE": "5294476442854247878", "VN": "5294235963340379688",
  "VI": "5294228039125718124", "GB-WLS": "5294139949346476093",
  "YE": "5294058972033076492", "ZM": "5294100109229838880",
  "ZW": "5294422158762592930",
}

# Generic flag used when a country has no mapped custom emoji.
GENERIC_FLAG_EMOJI_ID = "5294236848103643477"

# Set to False if Telegram ever rejects the custom emoji entities.
COUNTRY_FLAGS_ENABLED = True

_SPECIAL_FLAG_FALLBACKS = {
  "GB-ENG": "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F",
  "GB-SCT": "\U0001F3F4\U000E0067\U000E0062\U000E0073\U000E0063\U000E0074\U000E007F",
  "GB-WLS": "\U0001F3F4\U000E0067\U000E0062\U000E0077\U000E006C\U000E0073\U000E007F",
}

# Matches flag emoji, tag sequences and pictographs that panels include in
# country names (e.g. "United States \U0001F1FA\U0001F1F8").
_NAME_EMOJI_RE = re.compile(
  r'[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u200D'
  r'\U000E0020-\U000E007F\U0001F3F4]')


# Country NAME -> ISO code. The flag is ALWAYS derived from the country name
# first (so name and flag can never disagree) and only then from a given code.
_COUNTRY_ALIASES = {
  "AF": "afghanistan", "AX": "aland islands|aland", "AL": "albania", "DZ": "algeria",
  "AS": "american samoa", "AD": "andorra", "AO": "angola", "AI": "anguilla",
  "AG": "antigua and barbuda|antigua", "AR": "argentina", "AM": "armenia", "AW": "aruba",
  "AU": "australia", "AT": "austria", "AZ": "azerbaijan", "BS": "bahamas",
  "BH": "bahrain", "BD": "bangladesh", "BB": "barbados", "BY": "belarus",
  "BE": "belgium", "BZ": "belize", "BJ": "benin", "BT": "bhutan",
  "BO": "bolivia", "BW": "botswana", "BR": "brazil", "BN": "brunei|brunei darussalam",
  "BG": "bulgaria", "BF": "burkina faso|burkina", "BI": "burundi", "KH": "cambodia",
  "CM": "cameroon", "CA": "canada", "CV": "cape verde|cabo verde", "CF": "central african republic|car",
  "TD": "chad", "CL": "chile", "CN": "china", "CO": "colombia", "KM": "comoros",
  "CG": "congo|republic of the congo|congo brazzaville|congo (brazzaville)",
  "CK": "cook islands", "CR": "costa rica", "CI": "ivory coast|cote d'ivoire|cote divoire|côte d'ivoire",
  "HR": "croatia", "CU": "cuba", "CY": "cyprus", "CZ": "czech republic|czechia|czech",
  "DK": "denmark", "DJ": "djibouti", "DM": "dominica", "DO": "dominican republic|dominican",
  "EC": "ecuador", "EG": "egypt", "SV": "el salvador|salvador", "GB-ENG": "england",
  "GQ": "equatorial guinea", "ER": "eritrea", "EE": "estonia", "ET": "ethiopia",
  "EU": "european union", "GI": "gibraltar", "GM": "gambia|the gambia", "GL": "greenland",
  "FI": "finland", "FR": "france", "GA": "gabon", "GE": "georgia", "DE": "germany",
  "GH": "ghana", "GR": "greece", "GW": "guinea-bissau|guinea bissau", "GT": "guatemala",
  "GN": "guinea", "GY": "guyana", "HT": "haiti", "HN": "honduras",
  "HK": "hong kong|hongkong", "HU": "hungary", "IS": "iceland",
  "IN": "india", "IR": "iran", "IQ": "iraq", "IE": "ireland", "IM": "isle of man",
  "IL": "israel", "IT": "italy", "JM": "jamaica", "JP": "japan", "JE": "jersey",
  "JO": "jordan", "KZ": "kazakhstan", "KE": "kenya", "KI": "kiribati",
  "KP": "north korea|dprk", "KR": "south korea|korea|republic of korea", "KW": "kuwait",
  "KG": "kyrgyzstan|kyrgyz", "LA": "laos|lao", "LV": "latvia", "LB": "lebanon",
  "LS": "lesotho", "LR": "liberia", "LY": "libya", "LI": "liechtenstein",
  "LT": "lithuania", "LU": "luxembourg", "MK": "north macedonia|macedonia",
  "MG": "madagascar", "MW": "malawi", "MY": "malaysia", "MV": "maldives", "ML": "mali",
  "MT": "malta", "MH": "marshall islands", "MR": "mauritania", "MU": "mauritius",
  "MX": "mexico", "FM": "micronesia", "MD": "moldova", "MC": "monaco", "MN": "mongolia",
  "MA": "morocco", "MZ": "mozambique", "MM": "myanmar|burma", "NA": "namibia",
  "NR": "nauru", "NP": "nepal", "NL": "netherlands|holland", "NZ": "new zealand",
  "NI": "nicaragua", "NE": "niger", "NG": "nigeria", "NU": "niue", "NO": "norway",
  "OM": "oman", "PK": "pakistan", "PS": "palestine", "PA": "panama",
  "PG": "papua new guinea", "PY": "paraguay", "PH": "philippines", "PE": "peru",
  "PL": "poland", "PT": "portugal", "PR": "puerto rico", "QA": "qatar", "RO": "romania",
  "RU": "russia|russian federation", "RW": "rwanda", "SM": "san marino",
  "ST": "sao tome and principe|sao tome", "SA": "saudi arabia", "GB-SCT": "scotland",
  "SN": "senegal", "RS": "serbia", "SC": "seychelles", "SL": "sierra leone",
  "SG": "singapore", "SK": "slovakia", "SI": "slovenia", "SB": "solomon islands",
  "SO": "somalia", "ZA": "south africa", "ES": "spain", "LK": "sri lanka",
  "SD": "sudan", "SR": "suriname", "SZ": "eswatini|swaziland", "SE": "sweden",
  "CH": "switzerland", "SY": "syria", "TW": "taiwan", "TJ": "tajikistan",
  "TZ": "tanzania", "TH": "thailand", "TG": "togo", "TO": "tonga",
  "TT": "trinidad and tobago|trinidad", "TN": "tunisia", "TR": "turkey|turkiye|türkiye",
  "TM": "turkmenistan", "TC": "turks and caicos|turks and caicos islands",
  "US": "usa|united states|united states of america|america|us",
  "UG": "uganda", "AE": "uae|united arab emirates|emirates",
  "GB": "uk|united kingdom|great britain|britain", "UA": "ukraine", "VU": "vanuatu",
  "UZ": "uzbekistan", "UY": "uruguay", "VE": "venezuela", "VN": "vietnam|viet nam",
  "VI": "virgin islands us|us virgin islands|virgin islands", "GB-WLS": "wales",
  "YE": "yemen", "ZM": "zambia", "ZW": "zimbabwe",
  # Countries WITHOUT a premium emoji id still resolve to the right ISO code
  # (they get the correct plain unicode flag, never a wrong/generic one).
  "CD": "dr congo|d.r. congo|democratic republic of the congo|congo (kinshasa)|congo kinshasa",
  "BA": "bosnia and herzegovina|bosnia", "ME": "montenegro", "XK": "kosovo",
  "MO": "macao|macau", "TL": "timor-leste|east timor|timor leste", "BM": "bermuda",
  "KY": "cayman islands", "FJ": "fiji", "WS": "samoa", "LC": "saint lucia|st lucia",
  "VC": "saint vincent and the grenadines|saint vincent", "KN": "saint kitts and nevis",
  "GD": "grenada", "BQ": "bonaire", "CW": "curacao", "SX": "sint maarten",
  "NC": "new caledonia", "PF": "french polynesia", "GP": "guadeloupe",
  "MQ": "martinique", "RE": "reunion", "GF": "french guiana", "SS": "south sudan",
  "EH": "western sahara", "FO": "faroe islands", "GU": "guam", "AC": "ascension",
  "ID": "indonesia|republic of indonesia", "BL": "saint barthelemy|st barthelemy",
  "FK": "falkland islands|falklands", "GG": "guernsey", "IO": "british indian ocean territory",
  "MF": "saint martin|st martin", "MP": "northern mariana islands", "MS": "montserrat",
  "PM": "saint pierre and miquelon", "PW": "palau", "SH": "saint helena", "SJ": "svalbard",
  "TK": "tokelau", "TV": "tuvalu", "VA": "vatican|vatican city|holy see",
  "VG": "british virgin islands", "WF": "wallis and futuna", "YT": "mayotte",
}
_COUNTRY_NAME_TO_ISO = {}
for _iso, _names in _COUNTRY_ALIASES.items():
  for _n in _names.split("|"):
    _COUNTRY_NAME_TO_ISO[_n.strip()] = _iso


def _norm_country_name(name):
  name = re.sub(r'<[^>]+>', '', str(name or ""))
  name = re.sub(r'[\U0001F000-\U0001FAFF☀-➿️‍\U000E0020-\U000E007F]', '', name)
  name = unicodedata.normalize('NFKD', name)
  name = ''.join(ch for ch in name if not unicodedata.combining(ch))
  name = re.sub(r'\s+', ' ', name.replace('_', ' ')).strip().lower()
  return name


def country_code_from_name(name):
  """ISO code for a country name ('' when unknown)."""
  n = _norm_country_name(name)
  if not n:
    return ""
  if n in _COUNTRY_NAME_TO_ISO:
    return _COUNTRY_NAME_TO_ISO[n]
  stripped = re.sub(r'\s*\(.*?\)\s*', ' ', n).strip()
  if stripped in _COUNTRY_NAME_TO_ISO:
    return _COUNTRY_NAME_TO_ISO[stripped]
  if stripped.startswith("the ") and stripped[4:] in _COUNTRY_NAME_TO_ISO:
    return _COUNTRY_NAME_TO_ISO[stripped[4:]]
  return ""


def resolve_country_code(name=None, code=None):
  """Single source of truth: the NAME decides the flag; the code is only a
  fallback when the name is unknown. Keeps country + flag always identical."""
  by_name = country_code_from_name(name) if name else ""
  if by_name:
    return by_name
  c = str(code or "").strip().upper()
  if c in COUNTRY_FLAGS or c in _COUNTRY_ALIASES:
    return c
  # Any other real ISO code still gets its correct unicode flag.
  try:
    if c in _ISO_COUNTRY_NAMES:
      return c
  except NameError:
    pass
  return ""


_ISO_DIAL = {
"AF":"93","AL":"355","DZ":"213","AS":"1684","AD":"376","AO":"244","AI":"1264","AG":"1268","AR":"54","AM":"374",
"AW":"297","AU":"61","AT":"43","AZ":"994","BS":"1242","BH":"973","BD":"880","BB":"1246","BY":"375","BE":"32",
"BZ":"501","BJ":"229","BM":"1441","BT":"975","BO":"591","BA":"387","BW":"267","BR":"55","IO":"246","VG":"1284",
"BN":"673","BG":"359","BF":"226","BI":"257","KH":"855","CM":"237","CA":"1","CV":"238","KY":"1345","CF":"236",
"TD":"235","CL":"56","CN":"86","CO":"57","KM":"269","CG":"242","CD":"243","CK":"682","CR":"506","CI":"225",
"HR":"385","CU":"53","CW":"599","CY":"357","CZ":"420","DK":"45","DJ":"253","DM":"1767","DO":"1809","EC":"593",
"EG":"20","SV":"503","GQ":"240","ER":"291","EE":"372","SZ":"268","ET":"251","FK":"500","FO":"298","FJ":"679",
"FI":"358","FR":"33","GF":"594","PF":"689","GA":"241","GM":"220","GE":"995","DE":"49","GH":"233","GI":"350",
"GR":"30","GL":"299","GD":"1473","GP":"590","GU":"1671","GT":"502","GN":"224","GW":"245","GY":"592","HT":"509",
"HN":"504","HK":"852","HU":"36","IS":"354","IN":"91","ID":"62","IR":"98","IQ":"964","IE":"353","IL":"972",
"IT":"39","JM":"1876","JP":"81","JO":"962","KZ":"7","KE":"254","KI":"686","XK":"383","KW":"965","KG":"996",
"LA":"856","LV":"371","LB":"961","LS":"266","LR":"231","LY":"218","LI":"423","LT":"370","LU":"352","MO":"853",
"MG":"261","MW":"265","MY":"60","MV":"960","ML":"223","MT":"356","MH":"692","MQ":"596","MR":"222","MU":"230",
"YT":"262","MX":"52","FM":"691","MD":"373","MC":"377","MN":"976","ME":"382","MS":"1664","MA":"212","MZ":"258",
"MM":"95","NA":"264","NR":"674","NP":"977","NL":"31","NC":"687","NZ":"64","NI":"505","NE":"227","NG":"234",
"NU":"683","KP":"850","MK":"389","MP":"1670","NO":"47","OM":"968","PK":"92","PW":"680","PS":"970","PA":"507",
"PG":"675","PY":"595","PE":"51","PH":"63","PL":"48","PT":"351","PR":"1787","QA":"974","RE":"262","RO":"40",
"RU":"7","RW":"250","WS":"685","SM":"378","ST":"239","SA":"966","SN":"221","RS":"381","SC":"248","SL":"232",
"SG":"65","SK":"421","SI":"386","SB":"677","SO":"252","ZA":"27","KR":"82","SS":"211","ES":"34","LK":"94",
"SD":"249","SR":"597","SE":"46","CH":"41","SY":"963","TW":"886","TJ":"992","TZ":"255","TH":"66","TL":"670",
"TG":"228","TK":"690","TO":"676","TT":"1868","TN":"216","TR":"90","TM":"993","TC":"1649","TV":"688","UG":"256",
"UA":"380","AE":"971","GB":"44","US":"1","UY":"598","UZ":"998","VU":"678","VA":"379","VE":"58","VN":"84",
"YE":"967","ZM":"260","ZW":"263","EH":"212","BQ":"599","SX":"1721","MF":"590","BL":"590","PM":"508","WF":"681",
"SH":"290","JE":"44","GG":"44","IM":"44","AX":"358","SJ":"47",
}


def country_dial_code(code=None, name=None):
  """Dial code (digits only, no +) for an ISO code / country name; '' if unknown."""
  iso = ""
  try:
    iso = resolve_country_code(name, code) if (name or code) else ""
  except Exception:
    iso = ""
  if not iso:
    iso = str(code or "").strip().upper()
  return _ISO_DIAL.get(iso, "")


def country_flag_fallback(country_code):
  """Plain unicode flag used as the fallback inside a custom emoji tag."""
  code = str(country_code or "").strip().upper()
  if code in _SPECIAL_FLAG_FALLBACKS:
    return _SPECIAL_FLAG_FALLBACKS[code]
  if len(code) == 2 and code.isalpha():
    return "".join(chr(0x1F1E6 + (ord(ch) - 65)) for ch in code)
  return "\U0001F3F3️"


def country_flag_html(country_code=None, name=None):
  """Custom-emoji flag markup. Pass name= so the flag always matches the
  country name. A country with no premium emoji id shows its REAL unicode flag
  (never a wrong/generic one)."""
  code = resolve_country_code(name, country_code)
  fallback = country_flag_fallback(code)
  if not COUNTRY_FLAGS_ENABLED:
    return fallback
  emoji_id = COUNTRY_FLAGS.get(code)
  if not emoji_id:
    return fallback if code else f'<tg-emoji emoji-id="{GENERIC_FLAG_EMOJI_ID}">{fallback}</tg-emoji>'
  return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def country_flag_icon_id(country_code=None, name=None):
  """Custom emoji id for a button icon; None when the country has no premium flag."""
  code = resolve_country_code(name, country_code)
  return COUNTRY_FLAGS.get(code) or (None if code else GENERIC_FLAG_EMOJI_ID)


def clean_country_name(name):
  """Strip emoji/flags from an API country name, keeping readable text."""
  name = re.sub(r'<[^>]+>', '', str(name or ""))
  name = _NAME_EMOJI_RE.sub('', name)
  return re.sub(r'\s+', ' ', name).strip()


def get_server_api_config(server_no=1):
  conf = SERVER_DEFS.get(int(server_no))
  if not conf:
    return "", ""
  raw_url = (get_setting(conf["url_key"], conf.get("default_url", "")) or "").strip()
  if not raw_url:
    raw_url = conf.get("default_url", "")
  api_key = (get_setting(conf["key_key"], "") or "").strip()
  if conf.get("kind") == "s3" and not api_key:
    try:
      api_key = _s2wa_api_key()   # Server 3 shares the Server 2 key until its own is set
    except NameError:
      pass
  return clean_html_url(raw_url), api_key


def get_server_margin(server_no=1):
  conf = SERVER_DEFS.get(int(server_no))
  if not conf:
    return 0.0
  try:
    return max(0.0, float(get_setting(conf["margin_key"], str(conf.get("default_margin", 0))) or 0))
  except Exception:
    return 0.0


def server_sell_price(api_price, server_no=1):
  """API price + admin profit margin, rounded up to a whole rupee."""
  try:
    base_price = float(api_price)
  except Exception:
    return 0
  total = base_price * (1 + get_server_margin(server_no) / 100.0)
  whole = int(total)
  return whole if total <= whole else whole + 1


def _mask_url(url):
  """Show only a generic example.com host so the real panel domain never leaks."""
  raw = str(url or "").strip()
  if not raw:
    return "Not set"
  m = re.match(r'^(https?://)([^/\s?#]+)(.*)$', raw, re.I)
  if not m:
    return "https://example.com"
  return m.group(1) + "example.com" + m.group(3)


_PRIV_HOST_CACHE = {"ts": 0.0, "hosts": ()}

def _private_api_hosts():
  """Hosts of every configured server/SMM API (cached a few seconds)."""
  now = time.time()
  if now - _PRIV_HOST_CACHE["ts"] < 20:
    return _PRIV_HOST_CACHE["hosts"]
  found = set()
  def _add(u):
    m = re.match(r'^https?://([^/\s?#:@]+)', str(u or '').strip(), re.I)
    if m:
      found.add(m.group(1).lower())
  _add(NOBELOTS_BASE_URL)
  for conf in SERVER_DEFS.values():
    _add(conf.get('default_url'))
    try: _add(get_setting(conf['url_key'], ''))
    except Exception: pass
  try: _add(get_setting('smm_api_url', ''))
  except Exception: pass
  hosts = tuple(sorted((h for h in found if h and h != 'example.com' and '.' in h), key=len, reverse=True))
  _PRIV_HOST_CACHE["ts"] = now
  _PRIV_HOST_CACHE["hosts"] = hosts
  return hosts


def _private_api_keys():
  """API keys/tokens of every configured server/SMM panel (so they can never be echoed)."""
  out = []
  try:
    for conf in SERVER_DEFS.values():
      v = str(get_setting(conf['key_key'], '') or '').strip()
      if len(v) >= 8: out.append(v)
    v = str(get_setting('smm_api_key', '') or '').strip()
    if len(v) >= 8: out.append(v)
  except Exception:
    pass
  return out


_CLONE_PROVIDER_SUBS = [
  (re.compile(r'lolz[\s_-]*team[\s_-]*market[\s_-]*api', re.I), 'Server API'),
  (re.compile(r'lolz[\s_-]*team(?:[\s_-]*market)?', re.I), 'Server'),
  (re.compile(r'\blzt(?:[\s_-]*market)?\b', re.I), 'Server'),
  (re.compile(r'nobelots[\s_-]*reseller[\s_-]*api', re.I), 'Server API'),
  (re.compile(r'nobelots', re.I), 'Server'),
  (re.compile(r'tiger[\s_-]*sms(?:\.com)?', re.I), 'Provider'),
  (re.compile(r'nbl_live_\w*', re.I), 'api_key'),
]
_BRAND_RE = re.compile(r'aaditya[\s_-]*tg[\s_-]*store(?:bot)?', re.I)

# ---- ALWAYS-ON provider hiding (main bot + clones): customers and admins must never
# see the real provider name, its website, or raw HTTP codes in any message. ----
# HARDCODED provider blacklist. Every supplier / API panel name and domain the store
# has ever used. Nothing matching these may ever leave the bot, in any message,
# popup, button, caption or error -- whatever the provider API returns.
_HP_WORDS = (
  r'lolz[\s_.-]*team(?:[\s_.-]*market)?(?:[\s_.-]*api)?', r'lolz(?:\.\w+)?', r'zelenka(?:\.\w+)?',
  r'\blzt(?:[\s_.-]*market)?\b', r'nobelots(?:[\s_.-]*reseller)?(?:[\s_.-]*api)?',
  r'nbl_(?:live|test)_\w*', r'phantom(?:[\s_.-]*(?:api|panel|reseller|market))?',
  r'tiger[\s_.-]*sms(?:\.com)?', r'smmpanel(?:\.\w+)?',
)
_HP_DOMAINS = (r'lzt\.market', r'lolz[\w-]*\.[a-z]{2,}', r'zelenka[\w-]*\.[a-z]{2,}',
               r'nobelots[\w-]*\.[a-z]{2,}', r'tiger-?sms[\w-]*\.[a-z]{2,}',
               r'smmpanel[\w-]*\.[a-z]{2,}')
_HP_URL_RE = re.compile(
  r'(?:https?://)?(?:[\w-]+\.)*(?:' + '|'.join(_HP_DOMAINS) + r')(?::\d+)?(?:[/?#][^\s<>"\']*)?', re.I)
_HP_ANCHOR_RE = re.compile(
  r'<a\s+[^>]*href=["\'][^"\']*(?:lzt|lolz|zelenka|nobelots|tiger-?sms|smmpanel)[^"\']*["\'][^>]*>.*?</a>',
  re.I | re.S)
_HP_WORD_RE = re.compile('|'.join('(?:%s)' % w for w in _HP_WORDS), re.I)
_HP_BEARER_RE = re.compile(r'(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}')
_HP_ZW_RE = re.compile('[\u200b\u200c\u200d\u2060\ufeff\u00ad]')
_HTTP_CODE_RE = re.compile(r'\s*\(\s*http[_ ]?\d{3}\s*\)', re.I)
_BARE_HTTP_CODE_RE = re.compile(r'\bhttp[_ ]\d{3}\b', re.I)


def _hide_provider(text):
  """Remove provider URLs / names / tokens / raw http codes from any text. Always on."""
  if not isinstance(text, str) or not text:
    return text
  try:
    text = _HP_ZW_RE.sub('', text)
    text = re.sub(r'(?i)\s*[-\u2013:]?\s*Purchase\s*[-\u2013:]\s*(?=\S*(?:lzt|lolz|zelenka|nobelots|tiger|smmpanel))\S+', '', text)
    text = _HP_ANCHOR_RE.sub('', text)
    text = _HP_URL_RE.sub('', text)
    text = _HP_BEARER_RE.sub('', text)
    text = _HP_WORD_RE.sub('Server', text)
    text = _HTTP_CODE_RE.sub('', text)
    text = _BARE_HTTP_CODE_RE.sub('error', text)
  except Exception:
    pass
  return text


def _lzt_clean_error(status, msg):
  """Turn a raw provider error into a short customer-safe message."""
  low = str(msg or '').lower()
  if 'automatic purchase' in low or 'already purchased' in low or 'already sold' in low or 'item not found' in low or 'not available' in low:
    return 'This account was just taken by someone else. Please pick another one.'
  if 'not enough' in low or 'insufficient' in low or 'balance' in low:
    return 'Server balance is low. Please contact support.'
  if status in (401, 403) and not low:
    return 'This request could not be completed right now. Please try again.'
  return _hide_provider(str(msg or '')).strip() or 'Request could not be completed. Please try again.'



# Server logs too: provider names / links / keys are removed from every log record
# (message and traceback), so they cannot leak through any log viewer or log file.
try:
  import traceback as _tb_hp
  _hp_old_factory = logging.getLogRecordFactory()

  def _hp_record_factory(*_a, **_k):
    _r = _hp_old_factory(*_a, **_k)
    try:
      _r.msg = _hide_provider(_r.getMessage())
      _r.args = ()
      if _r.exc_info and _r.exc_info[0] is not None:
        _r.exc_text = _hide_provider("".join(_tb_hp.format_exception(*_r.exc_info)))
    except Exception:
      pass
    return _r

  logging.setLogRecordFactory(_hp_record_factory)
except Exception:
  pass

def _scrub_private_hosts(text):
  """Replace any private API host in outgoing text with example.com.
  In a cloned bot it also hides the provider names and swaps the main store name
  for the clone's own store name."""
  if not isinstance(text, str) or not text:
    return text
  text = _hide_provider(text)
  try:
    for h in _private_api_hosts():
      text = re.sub(r'(?:https?://)?' + re.escape(h) + r'(?::\d+)?(?:[/?#][^\s<>"\']*)?', '', text, flags=re.I)
    for k in _private_api_keys():
      if k and k in text:
        text = text.replace(k, '')
  except Exception:
    pass
  try:
    low = text.lower()
    for h in _private_api_hosts():
      if h in low:
        text = re.sub(re.escape(h), 'example.com', text, flags=re.I)
        low = text.lower()
  except Exception:
    pass
  if IS_CLONE:
    try:
      for _rx, _rep in _CLONE_PROVIDER_SUBS:
        text = _rx.sub(_rep, text)
      if STORE_NAME:
        text = _BRAND_RE.sub(lambda _m: STORE_NAME, text)
    except Exception:
      pass
  return text


# Callback-query popups (event.answer) never went through the send wrapper, so they could leak too.
try:
  _cq_orig_answer = events.CallbackQuery.Event.answer

  async def _cq_answer_scrubbed(self, message=None, *args, **kwargs):
    if isinstance(message, str):
      message = _scrub_private_hosts(message)
    return await _cq_orig_answer(self, message, *args, **kwargs)

  events.CallbackQuery.Event.answer = _cq_answer_scrubbed
except Exception as _ans_ex:
  logger.warning("Callback answer scrub not installed: %s", _ans_ex)


def _mask_secret(value):
  value = str(value or "")
  if not value:
    return "Not set"
  if len(value) <= 8:
    return "Set"
  return value[:4] + "..." + value[-4:]


def _api_error_text(res):
  """Human-readable message from a Nobelots error payload."""
  if not isinstance(res, dict):
    return "Server API did not respond."
  message = str(res.get("message") or "").strip()
  error = str(res.get("error") or "").strip()
  details = res.get("details")
  if isinstance(details, dict):
    extra = ""
    if details.get("cheapest_price") is not None:
      extra = f" (cheapest: ₹{details.get('cheapest_price')})"
    elif details.get("cheapest_prices"):
      try:
        extra = " (available: " + ", ".join(f"₹{p}" for p in details["cheapest_prices"][:5]) + ")"
      except Exception:
        extra = ""
    elif details.get("limit"):
      extra = f" (limit: {details.get('limit')})"
    if message and extra and extra not in message:
      message = message + extra
  if message:
    return _hide_provider(message)
  if error:
    return _hide_provider(error) if not re.match(r'^http_\d+$', error) else "Request failed. Please try again."
  return "Unknown API error."


_LZT_FX_CACHE = {"ts": 0.0, "rub_to_inr": 1.05, "usdt_to_inr": 94.0}
_LZT_COMPLETED_BATCHES = {}

_ISO_COUNTRY_NAMES = {
  "AF": "Afghanistan", "AL": "Albania", "DZ": "Algeria", "AD": "Andorra", "AO": "Angola",
  "AR": "Argentina", "AM": "Armenia", "AU": "Australia", "AT": "Austria", "AZ": "Azerbaijan",
  "BH": "Bahrain", "BD": "Bangladesh", "BY": "Belarus", "BE": "Belgium", "BO": "Bolivia",
  "BA": "Bosnia and Herzegovina", "BR": "Brazil", "BG": "Bulgaria", "KH": "Cambodia",
  "CM": "Cameroon", "CA": "Canada", "CL": "Chile", "CN": "China", "CO": "Colombia",
  "CR": "Costa Rica", "CI": "Ivory Coast", "HR": "Croatia", "CU": "Cuba", "CY": "Cyprus",
  "CZ": "Czech Republic", "DK": "Denmark", "DO": "Dominican Republic", "EC": "Ecuador",
  "EG": "Egypt", "SV": "El Salvador", "EE": "Estonia", "ET": "Ethiopia", "FI": "Finland",
  "FR": "France", "GE": "Georgia", "DE": "Germany", "GH": "Ghana", "GR": "Greece",
  "GT": "Guatemala", "HN": "Honduras", "HK": "Hong Kong", "HU": "Hungary", "IS": "Iceland",
  "IN": "India", "IR": "Iran", "IQ": "Iraq", "IE": "Ireland", "IL": "Israel", "IT": "Italy",
  "JM": "Jamaica", "JP": "Japan", "JO": "Jordan", "KZ": "Kazakhstan", "KE": "Kenya",
  "KR": "South Korea", "KW": "Kuwait", "KG": "Kyrgyzstan", "LA": "Laos", "LV": "Latvia",
  "LB": "Lebanon", "LY": "Libya", "LT": "Lithuania", "LU": "Luxembourg", "MO": "Macao",
  "MK": "North Macedonia", "MG": "Madagascar", "MY": "Malaysia", "MV": "Maldives",
  "ML": "Mali", "MT": "Malta", "MX": "Mexico", "MD": "Moldova", "MC": "Monaco",
  "MN": "Mongolia", "ME": "Montenegro", "MA": "Morocco", "MZ": "Mozambique", "MM": "Myanmar",
  "NP": "Nepal", "NL": "Netherlands", "NZ": "New Zealand", "NI": "Nicaragua", "NG": "Nigeria",
  "NO": "Norway", "OM": "Oman", "PK": "Pakistan", "PS": "Palestine", "PA": "Panama",
  "PY": "Paraguay", "PE": "Peru", "PH": "Philippines", "PL": "Poland", "PT": "Portugal",
  "PR": "Puerto Rico", "QA": "Qatar", "RO": "Romania", "RU": "Russia", "SA": "Saudi Arabia",
  "SN": "Senegal", "RS": "Serbia", "SG": "Singapore", "SK": "Slovakia", "SI": "Slovenia",
  "SO": "Somalia", "ZA": "South Africa", "ES": "Spain", "LK": "Sri Lanka", "SD": "Sudan",
  "SE": "Sweden", "CH": "Switzerland", "SY": "Syria", "TW": "Taiwan", "TJ": "Tajikistan",
  "TZ": "Tanzania", "TH": "Thailand", "TN": "Tunisia", "TR": "Turkey", "TM": "Turkmenistan",
  "UA": "Ukraine", "AE": "UAE", "GB": "UK", "US": "USA", "UY": "Uruguay", "UZ": "Uzbekistan",
  "VE": "Venezuela", "VN": "Vietnam", "YE": "Yemen", "ZM": "Zambia", "ZW": "Zimbabwe",
}


_ISO_EXTRA_NAMES = {
  "AW": "Aruba", "AG": "Antigua and Barbuda", "BS": "Bahamas", "BB": "Barbados", "BZ": "Belize",
  "BJ": "Benin", "BM": "Bermuda", "BT": "Bhutan", "BW": "Botswana", "BN": "Brunei",
  "BF": "Burkina Faso", "BI": "Burundi", "CV": "Cape Verde", "KY": "Cayman Islands",
  "CF": "Central African Republic", "TD": "Chad", "KM": "Comoros", "CG": "Congo",
  "CD": "DR Congo", "CW": "Curacao", "DJ": "Djibouti", "DM": "Dominica", "GQ": "Equatorial Guinea",
  "ER": "Eritrea", "SZ": "Eswatini", "FJ": "Fiji", "GA": "Gabon", "GM": "Gambia",
  "GD": "Grenada", "GU": "Guam", "GN": "Guinea", "GW": "Guinea-Bissau", "GY": "Guyana",
  "HT": "Haiti", "XK": "Kosovo", "LS": "Lesotho", "LR": "Liberia", "LI": "Liechtenstein",
  "MW": "Malawi", "MR": "Mauritania", "MU": "Mauritius", "FM": "Micronesia", "NA": "Namibia",
  "NE": "Niger", "KP": "North Korea", "PG": "Papua New Guinea", "RW": "Rwanda",
  "KN": "Saint Kitts and Nevis", "LC": "Saint Lucia", "VC": "Saint Vincent", "WS": "Samoa",
  "SM": "San Marino", "ST": "Sao Tome and Principe", "SC": "Seychelles", "SL": "Sierra Leone",
  "SB": "Solomon Islands", "SS": "South Sudan", "SR": "Suriname", "TL": "Timor-Leste",
  "TG": "Togo", "TO": "Tonga", "TT": "Trinidad and Tobago", "UG": "Uganda", "VU": "Vanuatu",
  "VA": "Vatican", "EH": "Western Sahara", "BQ": "Caribbean Netherlands", "SX": "Sint Maarten",
  "GI": "Gibraltar", "GL": "Greenland", "GP": "Guadeloupe", "MQ": "Martinique", "RE": "Reunion",
  "GF": "French Guiana", "PF": "French Polynesia", "NC": "New Caledonia", "JE": "Jersey",
  "GG": "Guernsey", "IM": "Isle of Man", "FO": "Faroe Islands", "AX": "Aland Islands",
  "VI": "US Virgin Islands", "VG": "British Virgin Islands", "TC": "Turks and Caicos",
  "AI": "Anguilla", "MS": "Montserrat", "AS": "American Samoa", "MP": "Northern Mariana Islands",
  "CK": "Cook Islands", "KI": "Kiribati", "MH": "Marshall Islands", "NR": "Nauru", "PW": "Palau",
  "TV": "Tuvalu", "YT": "Mayotte", "AQ": "Antarctica", "FK": "Falkland Islands", "SJ": "Svalbard",
  "SH": "Saint Helena", "PM": "Saint Pierre and Miquelon", "WF": "Wallis and Futuna",
  "TK": "Tokelau", "NU": "Niue", "NF": "Norfolk Island", "CX": "Christmas Island",
  "CC": "Cocos Islands", "BL": "Saint Barthelemy", "MF": "Saint Martin", "IO": "British Indian Ocean Territory",
}
_ISO_EXTRA_NAMES.update({
  "ID": "Indonesia", "BV": "Bouvet Island", "GS": "South Georgia", "HM": "Heard Island",
  "PN": "Pitcairn Islands", "TF": "French Southern Territories", "UM": "US Minor Outlying Islands",
})
for _k, _v in _ISO_EXTRA_NAMES.items():
  _ISO_COUNTRY_NAMES.setdefault(_k, _v)


def _lzt_country_name(code):
  c = str(code or "").strip().upper()
  return _ISO_COUNTRY_NAMES.get(c, c)


def _get_rub_to_inr_rate():
  now = time.time()
  if _LZT_FX_CACHE["ts"] > 0 and (now - _LZT_FX_CACHE["ts"]) < 3600:
    return _LZT_FX_CACHE["rub_to_inr"]
  try:
    req = urllib.request.Request(
      "https://open.er-api.com/v6/latest/RUB",
      headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, context=get_ssl_context(), timeout=10) as resp:
      data = json.loads(resp.read().decode("utf-8", errors="ignore"))
      inr = float((data.get("rates") or {}).get("INR") or 0)
      if inr > 0:
        _LZT_FX_CACHE["rub_to_inr"] = inr
        _LZT_FX_CACHE["ts"] = now
        return inr
  except Exception:
    pass
  return _LZT_FX_CACHE["rub_to_inr"]


def _get_usdt_to_inr_rate():
  """Fetch a live USD/INR rate (USD is the market/API equivalent used for USDT pricing)."""
  now = time.time()
  cached = float(_LZT_FX_CACHE.get("usdt_to_inr") or 0)
  if _LZT_FX_CACHE.get("usdt_ts", 0) and (now - _LZT_FX_CACHE["usdt_ts"]) < 3600 and cached > 0:
    return cached
  try:
    req = urllib.request.Request(
      "https://open.er-api.com/v6/latest/USD",
      headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, context=get_ssl_context(), timeout=10) as resp:
      data = json.loads(resp.read().decode("utf-8", errors="ignore"))
      inr = float((data.get("rates") or {}).get("INR") or 0)
      if inr > 0:
        _LZT_FX_CACHE["usdt_to_inr"] = inr
        _LZT_FX_CACHE["usdt_ts"] = now
        return inr
  except Exception as ex:
    logger.warning(f"Live USDT/INR rate fetch failed; using configured fallback: {ex}")
  # Keep the admin-configured USDT rate as a safe fallback if the FX provider is down.
  try:
    fallback = float(get_usdt_rate() or 0)
    if fallback > 0:
      return fallback
  except Exception:
    pass
  return cached if cached > 0 else 94.0


def _lzt_to_inr(amount, currency="USD"):
  val = float(amount or 0)
  cur_code = str(currency or "USD").strip().upper()
  if cur_code in ("INR", "RS", "RUPEE"):
    return val
  if cur_code in ("USD", "USDT", "USDC"):
    return val * _get_usdt_to_inr_rate()
  if cur_code == "RUB":
    return val * _get_rub_to_inr_rate()
  # Unknown currency: do not silently treat it as INR or multiply by a guessed rate.
  logger.warning(f"Unknown LZT currency {cur_code!r}; treating amount as USD for INR display")
  return val * _get_usdt_to_inr_rate()



# ================= RESELLER UPSTREAM (clone → main bot /v1 API) =================
# When Server 1 URL/key points at the main Reseller API (ats_... key or docs host),
# talk /v1/* instead of Lolzteam Market paths. Fixes "Not Found" on clone bots.

def _url_host_of(u):
  """Lowercase host[:port] of a URL without needing urllib.parse."""
  s = str(u or "").strip().lower()
  if "://" in s:
    s = s.split("://", 1)[1]
  return s.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]


def _strip_provider_path(u):
  """Remove a legacy /stubs/handler_api.php suffix that older builds appended
  to a Reseller URL. Returns the clean base URL."""
  s = str(u or "").strip()
  low = s.lower().split("?", 1)[0].rstrip("/")
  for _suf in ("/stubs/handler_api.php", "/stubs/handler_api", "/handler_api.php"):
    if low.endswith(_suf):
      return s[: len(s) - len(_suf)].rstrip("/")
  return s.rstrip("/")


def _is_reseller_upstream(server_no=1):
  """True when this server is configured to use a Reseller API (main bot), not LZT/Tiger.

  Order matters: an ats_ key or a main-store host always wins, even when an old
  build appended /stubs/handler_api.php to the saved URL. That suffix used to
  make Server 2/3 fall back to the Tiger stub and show "Not Found".
  """
  try:
    url, key = get_server_api_config(int(server_no))
  except Exception:
    return False
  u = (url or "").strip().lower()
  k = (key or "").strip()
  # 1) ats_... is always a main-store reseller key.
  if k.startswith("ats_"):
    return True
  if not u:
    return False
  # 2) Real provider hosts are never reseller.
  if "lzt.market" in u or "lolz.live" in u or "lolzteam" in u:
    return False
  if "tiger-sms" in u or "tigersms" in u or "smspva" in u or "5sim" in u:
    return False
  bare = _strip_provider_path(u).lower()
  # 3) Reseller URL shapes: .../v1 or the main-store docs host.
  if bare.rstrip("/").endswith("/v1") or "/v1/" in bare:
    return True
  try:
    docs = _main_store_base().lower()
  except Exception:
    docs = (MAIN_API_DOCS_URL or "").strip().lower().rstrip("/")
  if docs:
    _dhost = _url_host_of(docs)
    _uhost = _url_host_of(bare)
    if _dhost and _uhost and _dhost == _uhost:
      return True
    if docs in bare:
      return True
  if "onrender.com" in bare and "aaditya" in bare:
    return True
  return False


def _main_store_base():
  """Base URL of the MAIN store (Reseller API + docs).

  A cloned bot stores it in the `api_docs_url` setting (seeded from
  MAIN_API_DOCS_URL at first run and editable from Admin). Falling back to the
  env default keeps the main bot itself working too.
  """
  base = ""
  try:
    base = str(get_setting("api_docs_url", "") or "").strip()
  except Exception:
    base = ""
  if not base:
    base = (MAIN_API_DOCS_URL or "").strip()
  return base.rstrip("/")


def _reseller_base_url(server_no=1):
  """Base URL of the MAIN store Reseller API for this server.

  An ats_ key always belongs to the main store. Admins often paste only the key
  and leave the URL at the old provider default (api.lzt.market / tiger-sms),
  which used to send /v1/balance to the provider and fail with 404. In that case
  fall back to MAIN_API_DOCS_URL so every server still talks to the main store.
  """
  url, key = get_server_api_config(int(server_no))
  base = _strip_provider_path((url or "").strip())
  # Accept either https://host or https://host/v1
  if base.endswith("/v1"):
    base = base[:-3].rstrip("/")
  k = str(key or "").strip()
  if k.startswith("ats_"):
    low = base.lower()
    _provider_host = (
      not base
      or "lzt.market" in low or "lolz.live" in low or "lolzteam" in low
      or "tiger-sms" in low or "tigersms" in low
      or "smspva" in low or "5sim" in low
    )
    if _provider_host:
      _docs = _main_store_base()
      if _docs:
        base = _docs
  return base


def _reseller_call(path, method="GET", params=None, payload=None, server_no=1, timeout=60):
  """HTTP helper for main-bot Reseller API. Auth: X-API-Key / Bearer ats_..."""
  base = _reseller_base_url(server_no)
  _url, api_key = get_server_api_config(int(server_no))
  if not base:
    return {"ok": False, "error": "missing_api_url", "message": "Reseller API URL is not set."}
  if not api_key:
    return {"ok": False, "error": "missing_api_key",
            "message": "Reseller API key is not set. Create one on the MAIN bot (Admin → API Keys)."}
  path = "/" + str(path or "").lstrip("/")
  url = base + path
  if params:
    qs = urlencode(params, doseq=True)
    url += ("&" if "?" in url else "?") + qs
  headers = {
    "Accept": "application/json",
    "User-Agent": "AadityaTgStoreBot/2.0 (ResellerClient)",
    "X-API-Key": api_key,
    "Authorization": "Bearer " + api_key,
  }
  data = None
  if payload is not None:
    data = json.dumps(payload).encode("utf-8")
    headers["Content-Type"] = "application/json"
  try:
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    with urllib.request.urlopen(req, context=get_ssl_context(), timeout=timeout) as resp:
      body = resp.read().decode("utf-8", errors="ignore")
      status = getattr(resp, "status", 200) or 200
  except urllib.error.HTTPError as ex:
    try:
      body = ex.read().decode("utf-8", errors="ignore")
    except Exception:
      body = ""
    status = ex.code
    parsed = _server_api_parse_json(body) or {}
    msg = ""
    if isinstance(parsed, dict):
      msg = str(parsed.get("message") or parsed.get("error") or "")
    if not msg:
      msg = f"HTTP {status}"
    # Map common reseller errors
    err = "http_%s" % status
    if status in (401, 403):
      err = "unauthorized"
    elif status == 404:
      err = "not_found"
    elif status == 402:
      err = "insufficient_funds"
    elif status == 429:
      err = "rate_limit"
    return {"ok": False, "status": status, "error": err, "message": msg, "data": parsed}
  except Exception as ex:
    logger.warning("Reseller upstream call failed (%s %s): %s", method, path, ex)
    return {"ok": False, "error": "network_error",
            "message": "Reseller API is not reachable right now. Please try again."}

  parsed = _server_api_parse_json(body)
  if not isinstance(parsed, dict):
    return {"ok": False, "error": "bad_response", "message": "Invalid JSON from Reseller API."}
  if parsed.get("success") is False:
    return {"ok": False, "error": str(parsed.get("error") or "api_error"),
            "message": str(parsed.get("message") or "Reseller API error."), "data": parsed}
  parsed["ok"] = True
  return parsed


def _reseller_fetch_countries(server_no=1, force_refresh=False):
  res = _reseller_call("/v1/countries", params={"server": int(server_no)}, server_no=server_no, timeout=45)
  if not res.get("ok"):
    return {"error": res.get("message") or res.get("error") or "Failed to load countries."}
  rows = []
  for c in (res.get("countries") or []):
    if not isinstance(c, dict):
      continue
    code = str(c.get("country_code") or c.get("code") or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", code):
      continue
    try:
      price = float(c.get("price") or 0)
    except Exception:
      price = 0.0
    try:
      stock = int(c.get("stock") if c.get("stock") is not None else 1)
    except Exception:
      stock = 1
    name = clean_country_name(c.get("name") or code)
    rows.append({"code": code, "name": name, "dial": "", "stock": stock, "price": price})
  rows.sort(key=lambda x: (x.get("price") or 0, x.get("name") or ""))
  if rows:
    _s2_publish(rows, done=True)
  return rows


def _reseller_s1_accounts(country_code, limit=20, spam=None, premium=None,
                          email=None, cat=None, force_refresh=False):
  """Server 1 individual accounts via main Reseller API GET /v1/accounts.

  Returns the same normalized shape as _norm_s1_item so the existing Server 1
  list, account-details page and Buy-by-item_id flow work unchanged inside a
  clone bot. Prices are already the main store's sell price in INR.
  """
  code = str(country_code or "").strip().upper()
  if not code:
    return {"error": "Invalid country."}
  now = time.time()
  key = "RSL|%s|%s|%s|%s|%s|%s" % (code, spam or "", premium or "", email or "",
                                   cat or "", int(limit or 20))
  try:
    cached = _s1_items_cache.get(key)
  except Exception:
    cached = None
  if cached and not force_refresh and now - cached.get("ts", 0) < 20:
    return cached.get("data") or []

  params = {"server": 1, "country_code": code, "limit": max(1, min(int(limit or 20), 50))}
  if spam in ("yes", "no"):
    params["spam"] = spam
  if premium in ("yes", "no"):
    params["premium"] = premium
  if email in ("yes", "no"):
    params["email"] = email
  if cat in ("push", "autoreg", "premium"):
    params["category"] = cat
  res = _reseller_call("/v1/accounts", params=params, server_no=1, timeout=45)
  if not res.get("ok"):
    return {"error": res.get("message") or res.get("error") or "Failed to load accounts."}

  cname = _lzt_country_name(code)
  out = []
  for a in (res.get("accounts") or []):
    if not isinstance(a, dict):
      continue
    aid = str(a.get("account_id") or a.get("id") or "").strip()
    if not aid:
      continue
    try:
      price = float(a.get("price") or 0)
    except Exception:
      price = 0.0
    if price <= 0:
      continue
    prem = a.get("premium")
    prem_txt = None if prem is None else ("Yes" if bool(prem) else "No")
    spam_v = a.get("spam_block")
    spam_txt = None if spam_v is None else ("Yes" if bool(spam_v) else "No")
    twofa_v = a.get("twofa")
    twofa_txt = None if twofa_v is None else ("Yes" if bool(twofa_v) else "No")
    email_raw = str(a.get("email") or "").strip()
    email_txt = ("Yes" if email_raw else "No")
    channels = int(a.get("channels") or 0)
    groups = int(a.get("groups") or 0)
    admins = int(a.get("admins") or 0)
    out.append({
      "id": aid,
      "price": price,
      "raw_price": price,
      "raw_currency": "INR",
      "premium": prem_txt,
      "premium_end": str(a.get("premium_until") or ""),
      "raw": a,
      "channels": channels,
      "groups": groups,
      "admins": admins,
      "spam": spam_txt,
      "twofa": twofa_txt,
      "email": email_txt,
      "email_masked": email_raw,
      "uploaded": str(a.get("uploaded") or ""),
      "last_seen": str(a.get("last_seen") or ""),
      "origin": str(a.get("origin") or ""),
      "resale_origin": "",
      "dial": "",
      "country": code,
      "name": cname,
      "groups_channels": f"{channels} Ch | {groups} Grp | {admins} Adm",
    })
  out.sort(key=lambda x: x.get("price") or 0)
  try:
    _s1_items_cache[key] = {"ts": now, "data": out}
  except Exception:
    pass
  return out


def _reseller_balance(server_no=1):
  res = _reseller_call("/v1/balance", server_no=server_no, timeout=30)
  if not res.get("ok"):
    return res
  try:
    bal = float(res.get("balance") or 0)
  except Exception:
    bal = 0.0
  return {
    "ok": True,
    "balance": round(bal, 2),
    "raw_balance": f"{bal} INR",
    "currency": "INR",
    "key": {"label": "Reseller API"},
  }


def _reseller_buy_s1(country_code=None, account_id=None, max_price=None, quantity=1):
  """Buy via main Reseller API POST /v1/buy (server=1).

  quantity > 1 (Bulk Buy) repeats /v1/buy, exactly like the main bot charges
  per delivered account. A specific account_id always buys exactly one.
  """
  base_body = {"server": 1}
  if account_id:
    base_body["item_id"] = str(account_id)
  code = str(country_code or "").strip().upper()
  if code:
    base_body["country_code"] = code
  if max_price not in (None, ""):
    try:
      base_body["max_price"] = float(max_price)
    except Exception:
      pass
  try:
    qty = max(1, min(int(quantity or 1), 50))
  except Exception:
    qty = 1
  if account_id:
    qty = 1

  bought = []
  first_order_id = ""
  last_err = None
  for _ in range(qty):
    res = _reseller_call("/v1/buy", method="POST", payload=base_body, server_no=1, timeout=180)
    if not res.get("ok"):
      last_err = res
      break
    order_id = str(res.get("order_id") or "").strip()
    phone = str(res.get("phone") or "").strip()
    pwd = str(res.get("password") or "").strip()
    try:
      price = float(res.get("price") or 0)
    except Exception:
      price = 0.0
    if not first_order_id:
      first_order_id = order_id
    bought.append({
      "order_no": order_id or ("RSEL-%s-%d" % (int(time.time()), len(bought) + 1)),
      "phone": phone,
      "price": price,
      "password": pwd,
      "session": "",
    })

  if not bought:
    res = last_err or {}
    return {"ok": False, "error": res.get("error") or "buy_failed",
            "message": res.get("message") or "Purchase failed on Reseller API."}

  # batch_id used throughout Server 1 UI — keep the first reseller order id as-is.
  batch_id = first_order_id or ("RSEL-%s" % int(time.time()))
  _LZT_COMPLETED_BATCHES[batch_id] = {
    "ok": True,
    "batch_id": batch_id,
    "status": "completed",
    "accounts": bought,
    "reseller": True,
  }
  return {"ok": True, "batch_id": batch_id, "partial": bool(last_err)}


def _reseller_bare_oid(oid):
  """Reseller order ids carry a server prefix (W- = Server 2, A- = Server 3).
  Local order tables store the bare id, so strip any known prefix."""
  s = str(oid or "").strip()
  for _p in ("W-", "A-", "T-"):
    if s.upper().startswith(_p):
      return s[len(_p):]
  return s


def _reseller_order_poll(order_id, server_no=1):
  oid = str(order_id or "").strip()
  if not oid:
    return {"ok": False, "error": "bad_id", "message": "Missing order id."}
  res = _reseller_call("/v1/order/%s" % quote(oid, safe=""), server_no=server_no, timeout=45)
  if not res.get("ok"):
    return res
  code = str(res.get("code") or "").strip()
  status = str(res.get("status") or "").upper()
  out = {
    "ok": True,
    "code": code,
    "status": status,
    "phone": res.get("phone") or "",
    "password": res.get("password") or "",
  }
  if code:
    out["message"] = "code"
  return out


def _reseller_s2_countries(force=False):
  """Server 2 country list via main Reseller API (price already INR from main)."""
  res = _reseller_call("/v1/countries", params={"server": 2}, server_no=2, timeout=45)
  if not res.get("ok"):
    raise _S2waError(str(res.get("message") or res.get("error") or "COUNTRIES_FAIL"))
  out = []
  for c in (res.get("countries") or []):
    if not isinstance(c, dict):
      continue
    try:
      cid = int(c.get("id"))
    except Exception:
      continue
    name = clean_country_name(c.get("name") or "")
    code = str(c.get("country_code") or c.get("code") or "").strip().upper()
    try:
      price_inr = float(c.get("price") or 0)
    except Exception:
      price_inr = 0.0
    try:
      stock = int(c.get("stock") if c.get("stock") is not None else 0)
    except Exception:
      stock = 0
    if price_inr <= 0:
      continue
    flag = country_flag_fallback(code) if code else _s2wa_flag(name)
    out.append({
      "id": cid, "name": name or code or str(cid), "flag": flag,
      "code": code or resolve_country_code(name, None) or "",
      "retry": None,
      "_reseller_price_inr": price_inr,
      "_reseller_stock": stock,
    })
  out.sort(key=lambda x: x["name"].lower())
  return out


def _reseller_s2_prices_map():
  """Map country_id -> (cost_usd_equiv, stock) so existing sell_price math still works."""
  try:
    rate = float(get_usdt_rate())
  except Exception:
    rate = 94.0
  if rate <= 0:
    rate = 94.0
  out = {}
  for c in _reseller_s2_countries(True):
    price_inr = float(c.get("_reseller_price_inr") or 0)
    stock = int(c.get("_reseller_stock") or 0)
    if price_inr <= 0:
      continue
    cost_usd = price_inr / rate
    out[int(c["id"])] = (cost_usd, stock)
  return out


def _reseller_s2_buy(country_id, max_price=None):
  body = {"server": 2, "country": int(country_id)}
  if max_price not in (None, ""):
    try:
      body["max_price"] = float(max_price)
    except Exception:
      pass
  res = _reseller_call("/v1/buy", method="POST", payload=body, server_no=2, timeout=120)
  if not res.get("ok"):
    raise _S2waError(str(res.get("message") or res.get("error") or "BUY_FAIL"))
  oid = str(res.get("order_id") or "").strip()
  # Local tables store the bare activation id; the Reseller API prefixes it
  # (W- for Server 2, A- for Server 3). Strip whatever prefix came back.
  act = _reseller_bare_oid(oid)
  phone = str(res.get("phone") or "").strip()
  if not act or not phone:
    raise _S2waError("BUY_FAIL")
  return act, phone, oid


def _reseller_s2_status(act_id):
  oid = str(act_id or "").strip()
  if not oid.upper().startswith("W-"):
    oid = "W-" + oid
  res = _reseller_order_poll(oid, server_no=2)
  if not res.get("ok"):
    err = str(res.get("error") or "")
    if err in ("not_found", "http_404"):
      return "NO_ACTIVATION"
    return "STATUS_WAIT_CODE"
  st = str(res.get("status") or "").upper()
  code = str(res.get("code") or "").strip()
  if code or st == "DONE":
    return "STATUS_OK:" + (code or "")
  if st == "CANCELLED":
    return "STATUS_CANCEL"
  if st == "WAIT_RETRY":
    return "STATUS_WAIT_RETRY:" + (code or "")
  return "STATUS_WAIT_CODE"


def _reseller_s2_cancel(act_id):
  oid = str(act_id or "").strip()
  if not oid.upper().startswith("W-"):
    oid = "W-" + oid
  res = _reseller_call("/v1/cancel/%s" % quote(oid, safe=""), method="POST", server_no=2, timeout=45)
  if res.get("ok"):
    return "ACCESS_CANCEL"
  msg = str(res.get("message") or res.get("error") or "")
  if "already" in msg.lower() and "code" in msg.lower():
    return "STATUS_OK"
  return msg or "ERROR"


def _reseller_s2_retry(act_id):
  oid = str(act_id or "").strip()
  if not oid.upper().startswith("W-"):
    oid = "W-" + oid
  res = _reseller_call("/v1/retry/%s" % quote(oid, safe=""), method="POST", server_no=2, timeout=45)
  if res.get("ok"):
    return "ACCESS_RETRY_GET"
  return str(res.get("message") or res.get("error") or "ERROR")


def _reseller_session(order_id):
  """Server 1 session string via main Reseller API GET /v1/session."""
  oid = str(order_id or "").strip()
  if not oid.upper().startswith("T-"):
    oid = "T-" + oid
  res = _reseller_call("/v1/session", params={"order_id": oid}, server_no=1, timeout=45)
  if not res.get("ok"):
    return {"ok": False, "error": res.get("error") or "session_unavailable",
            "message": res.get("message") or "Session string is not available for this order."}
  sess = str(res.get("session_string") or "").strip()
  if not sess:
    return {"ok": False, "error": "session_unavailable",
            "message": "Session string is not available for this order."}
  return {"ok": True, "string_session": sess, "dc_id": "-"}


def _reseller_s3_apps():
  res = _reseller_call("/v1/apps", server_no=3, timeout=45)
  if not res.get("ok"):
    raise _S2waError(str(res.get("message") or res.get("error") or "APPS_FAIL"))
  out = []
  for s in (res.get("apps") or []):
    if not isinstance(s, dict):
      continue
    code = str(s.get("code") or "").strip()
    name = str(s.get("name") or code).strip()
    if code:
      out.append({"code": code, "name": name})
  out.sort(key=lambda x: x["name"].lower())
  return out


def _reseller_s3_available(service):
  res = _reseller_call("/v1/countries", params={"server": 3, "service": service},
                       server_no=3, timeout=45)
  if not res.get("ok"):
    raise _S2waError(str(res.get("message") or res.get("error") or "COUNTRIES_FAIL"))
  try:
    rate = float(get_usdt_rate())
  except Exception:
    rate = 94.0
  if rate <= 0:
    rate = 94.0
  items = []
  for c in (res.get("countries") or []):
    if not isinstance(c, dict):
      continue
    try:
      cid = int(c.get("id"))
    except Exception:
      continue
    name = clean_country_name(c.get("name") or "")
    code = str(c.get("country_code") or "").strip().upper()
    try:
      price_inr = float(c.get("price") or 0)
    except Exception:
      price_inr = 0.0
    try:
      stock = int(c.get("stock") if c.get("stock") is not None else 0)
    except Exception:
      stock = 0
    if price_inr <= 0 or stock <= 0:
      continue
    cost_usd = price_inr / rate
    flag = country_flag_fallback(code) if code else _s2wa_flag(name)
    items.append({"id": cid, "name": name or code or str(cid), "flag": flag,
                  "code": code, "cost": cost_usd, "count": stock})
  items.sort(key=lambda x: (x["cost"], x["name"].lower()))
  return items


def _reseller_s3_buy(service, country_id, max_price=None):
  body = {"server": 3, "service": str(service), "country": int(country_id)}
  if max_price not in (None, ""):
    try:
      body["max_price"] = float(max_price)
    except Exception:
      pass
  res = _reseller_call("/v1/buy", method="POST", payload=body, server_no=3, timeout=120)
  if not res.get("ok"):
    raise _S2waError(str(res.get("message") or res.get("error") or "BUY_FAIL"))
  oid = str(res.get("order_id") or "").strip()
  act = _reseller_bare_oid(oid)
  phone = str(res.get("phone") or "").strip()
  if not act or not phone:
    raise _S2waError("BUY_FAIL")
  return act, phone, oid


def _reseller_s3_status(act_id):
  oid = str(act_id or "").strip()
  if not oid.upper().startswith("A-"):
    oid = "A-" + oid
  res = _reseller_order_poll(oid, server_no=3)
  if not res.get("ok"):
    return "STATUS_WAIT_CODE"
  st = str(res.get("status") or "").upper()
  code = str(res.get("code") or "").strip()
  if code or st == "DONE":
    return "STATUS_OK:" + (code or "")
  if st == "CANCELLED":
    return "STATUS_CANCEL"
  if st == "WAIT_RETRY":
    return "STATUS_WAIT_RETRY:" + (code or "")
  return "STATUS_WAIT_CODE"


def _reseller_s3_cancel(act_id):
  oid = str(act_id or "").strip()
  if not oid.upper().startswith("A-"):
    oid = "A-" + oid
  res = _reseller_call("/v1/cancel/%s" % quote(oid, safe=""), method="POST", server_no=3, timeout=45)
  if res.get("ok"):
    return "ACCESS_CANCEL"
  return str(res.get("message") or res.get("error") or "ERROR")


def _reseller_s3_retry(act_id):
  oid = str(act_id or "").strip()
  if not oid.upper().startswith("A-"):
    oid = "A-" + oid
  res = _reseller_call("/v1/retry/%s" % quote(oid, safe=""), method="POST", server_no=3, timeout=45)
  if res.get("ok"):
    return "ACCESS_RETRY_GET"
  return str(res.get("message") or res.get("error") or "ERROR")





def _lzt_call(path, method="GET", params=None, payload=None, server_no=1, timeout=300):
  """Call the Lolzteam Market API (https://api.lzt.market) with Bearer auth and retry loop."""
  base_url, api_key = get_server_api_config(server_no)
  if not api_key:
    return {"ok": False, "error": "missing_api_key",
            "message": "Server 1 API key is not configured by the admin."}

  base = (base_url or LZT_BASE_URL).strip().rstrip("/")
  url = base + path
  params = dict(params or {})
  params.setdefault("locale", "en-US")   # LZT docs: every request accepts locale
  if params:
    qs = urlencode(params, doseq=True)
    url += ("&" if "?" in url else "?") + qs

  headers = {
    "Authorization": f"Bearer {api_key}",
    "Accept": "application/json",
    "User-Agent": "AadityaTgStoreBot/2.0 (LZT-Market)",
  }

  data = None
  if method.upper() in ("POST", "PUT", "PATCH"):
    headers["Content-Type"] = "application/json"
    data = json.dumps(payload or {}).encode("utf-8")

  _5xx_retries = 0
  for _attempt in range(35):
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
      with urllib.request.urlopen(req, context=get_ssl_context(), timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as ex:
      try:
        body = ex.read().decode("utf-8", errors="ignore")
      except Exception:
        body = ""
      parsed = _server_api_parse_json(body)
      errors = parsed.get("errors") if isinstance(parsed, dict) else None
      err_msg = ", ".join(str(x) for x in errors) if isinstance(errors, list) and errors else (
        str(parsed.get("message") or parsed.get("error") or f"HTTP {ex.code}") if isinstance(parsed, dict) else f"HTTP {ex.code}"
      )
      if "retry_request" in err_msg.lower():
        time.sleep(2)
        continue
      if ex.code == 429:
        time.sleep(3)
        continue
      if ex.code in (500, 502, 503, 504):
        # Temporary provider problem (busy / restarting). Retrying the same request is safe:
        # a purchase is always for one specific item id, so it can never be bought twice.
        if _5xx_retries < 4:
          _5xx_retries += 1
          logger.warning("LZT %s on %s - retry %d/4", ex.code, path, _5xx_retries)
          time.sleep(2 * _5xx_retries)
          continue
        return {
          "ok": False,
          "status": ex.code,
          "error": f"http_{ex.code}",
          "message": "Server 1 is temporarily busy. Please try again in a minute.",
        }
      _clean = _lzt_clean_error(ex.code, err_msg)
      logger.warning("LZT %s on %s: %s", ex.code, path, err_msg)   # raw text only in the server log
      return {
        "ok": False,
        "status": ex.code,
        "error": "account_unavailable" if "taken by someone else" in _clean else f"http_{ex.code}",
        "message": _clean,
      }
    except Exception as ex:
      logger.warning(f"LZT Market API call failed ({path}): {ex}")
      return {"ok": False, "error": "network_error",
              "message": "Server is not reachable right now. Please try again in a minute."}

    parsed = _server_api_parse_json(body)
    if parsed is None:
      return {"ok": False, "error": "bad_response",
              "message": "Server returned an invalid response. Please try again."}
    if isinstance(parsed, dict) and parsed.get("errors"):
      err_txt = ", ".join(str(x) for x in parsed["errors"]) if isinstance(parsed["errors"], list) else str(parsed["errors"])
      if "retry_request" in err_txt.lower():
        time.sleep(2)
        continue
      return {"ok": False, "error": "api_error", "message": _lzt_clean_error(200, err_txt)}
    if isinstance(parsed, list):
      return {"ok": True, "data": parsed}
    if isinstance(parsed, dict):
      parsed.setdefault("ok", True)
      return parsed
    return {"ok": False, "error": "bad_response",
            "message": "Server returned an unexpected response. Please try again."}

  return {"ok": False, "error": "timeout",
          "message": "Server is busy. Please try again in a minute."}


def _nobelots_call(path, method="GET", payload=None, server_no=1, timeout=300,
                   idempotency_key=None):
  return _lzt_call(path, method=method, payload=payload, server_no=server_no, timeout=timeout)


def _server_api_parse_json(text):
  text = (text or "").strip()
  if not text:
    return None
  try:
    return json.loads(text)
  except Exception:
    pass
  match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
  if match:
    try:
      return json.loads(match.group(1))
    except Exception:
      return None
  return None


def _lzt_telegram_all_pages(params, max_pages=400):
  """Fetch every page of LZT /telegram results instead of only the first one.

  Returns a list of raw items, or {"error": ...} when page 1 fails.
  Stops on an empty page, on a page with only repeated items, or at max_pages.
  """
  out, seen = [], set()
  for page in range(1, max_pages + 1):
    if page > 1:
      time.sleep(3.1)   # LZT Category Search: 20 req/min, 3 s between requests
    p = dict(params or {})
    p["page"] = page
    res = _lzt_call("/telegram", params=p, timeout=60)
    if not res.get("ok"):
      if page == 1:
        return {"error": _api_error_text(res)}
      break
    raw = res.get("items")
    if not isinstance(raw, list):
      raw = res.get("data") if isinstance(res.get("data"), list) else []
    if not raw:
      break
    fresh = 0
    for it in raw:
      if not isinstance(it, dict):
        continue
      key = str(it.get("item_id") or it.get("id") or json.dumps(it, sort_keys=True)[:300])
      if key in seen:
        continue
      seen.add(key)
      out.append(it)
      fresh += 1
    if fresh == 0:
      break
  logger.info("s1 countries: %d accounts read from LZT", len(out))
  return out


_s2_refresh_state = {"running": False}

_S1_COUNTRIES_FILE = "s1_countries_cache.json"


def _s1_countries_load_disk():
  """Load the last full country list at startup so the menu opens instantly."""
  try:
    with open(_S1_COUNTRIES_FILE, "r", encoding="utf-8") as fh:
      data = json.load(fh)
    if isinstance(data, list) and data:
      for _c in data:
        try:
          if isinstance(_c, dict) and _c.get("code") and (not _c.get("name") or str(_c.get("name")).upper() == str(_c["code"]).upper()):
            _c["name"] = _lzt_country_name(_c["code"])
        except Exception:
          pass
      _s2_countries_cache["data"] = data
      _s2_countries_cache["ts"] = 0.0      # usable now, refreshed in background
  except Exception:
    pass


def _s1_countries_save_disk(data):
  try:
    tmp = _S1_COUNTRIES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
      json.dump(data, fh)
    os.replace(tmp, _S1_COUNTRIES_FILE)
  except Exception as ex:
    logger.warning("could not save country cache: %s", ex)


def _s2_refresh_in_background():
  """Refresh the Server 1 country list in a thread so no user waits for it."""
  if _s2_refresh_state["running"]:
    return
  _s2_refresh_state["running"] = True
  import threading

  def _run():
    try:
      _s2_crawl()
    except Exception as ex:
      logger.warning("s1 country refresh failed: %s", ex)
    finally:
      _s2_refresh_state["running"] = False

  threading.Thread(target=_run, daemon=True).start()


S2_MAX_PAGES = 400
S2_PAGE_DELAY = 3.1    # LZT: Category Search is 20 req/min, 3 s between requests


def _s2_group_items(items):
  """Group raw LZT accounts into one row per country (cheapest price first)."""
  grouped = {}
  for item in items:
    if not isinstance(item, dict):
      continue
    code = str(item.get("telegram_country") or item.get("country") or "").strip().upper()
    if not code:
      continue
    try:
      raw_price = float(item.get("price") or 0)
    except Exception:
      raw_price = 0.0
    price_inr = _lzt_to_inr(raw_price, item.get("currency") or "USD")
    if code not in grouped:
      grouped[code] = {"code": code, "name": _lzt_country_name(code), "dial": "",
                       "stock": 0, "price": price_inr}
    grouped[code]["stock"] += 1
    if price_inr > 0 and (grouped[code]["price"] <= 0 or price_inr < grouped[code]["price"]):
      grouped[code]["price"] = price_inr
  return sorted(grouped.values(), key=lambda c: (c.get("price") or 0, c.get("name") or ""))


def _s2_publish(countries, done):
  _s2_countries_cache["data"] = countries
  _s2_countries_cache["ts"] = time.time()
  _s2_countries_cache["partial"] = not done
  _s1_countries_save_disk(countries)


def _s2_discover_codes(max_pages=1):
  """Ask LZT for the newest + cheapest pages without a country filter and collect
  every country code that really appears, so codes missing from our name table
  are still checked."""
  seen = set()
  for order in ("price_to_up", "pdate_to_down", "price_to_down"):
    for page in range(1, max(1, int(max_pages)) + 1):
      time.sleep(S2_PAGE_DELAY)
      res = _lzt_call("/telegram", params={"order_by": order, "currency": "usd", "page": page}, timeout=60)
      if not res.get("ok"):
        break
      raw = res.get("items")
      if not isinstance(raw, list):
        raw = res.get("data") if isinstance(res.get("data"), list) else []
      if not raw:
        break
      for it in raw:
        if isinstance(it, dict):
          c = str(it.get("telegram_country") or it.get("country") or "").strip().upper()
          if re.fullmatch(r"[A-Z]{2}", c):
            seen.add(c)
  return seen


def _s2_check_code(code):
  """One country lookup, retried on transient errors. Returns (row|None, fatal)."""
  last = None
  for attempt in range(3):
    if attempt:
      time.sleep(S2_PAGE_DELAY * (attempt + 1))
    res = _lzt_call("/telegram",
                    params={"country[]": [code], "order_by": "price_to_up", "currency": "usd"},
                    timeout=60)
    last = res
    if res.get("ok"):
      raw = res.get("items")
      if not isinstance(raw, list):
        raw = res.get("data") if isinstance(res.get("data"), list) else []
      rows = _s2_group_items([it for it in raw if isinstance(it, dict)])
      row = None
      for r in rows:
        if r["code"] == code:
          row = r
          break
      if row is None and rows:
        row = rows[0]
      if row is not None:
        _tot = _s1_total_from(res)       # real stock of this country, not just page 1
        if _tot is not None and row["code"] == code:
          row["stock"] = max(int(row.get("stock") or 0), _tot)
      return row, False, True
    if res.get("status") in (401, 403):
      logger.warning("s1 country crawl stopped: %s", res.get("error"))
      return None, True, False
    if res.get("status") == 400:         # invalid code for LZT, no point retrying
      return None, False, True
  logger.info("s1 country %s failed after retries: %s", code, (last or {}).get("message"))
  return None, False, False               # transient failure: keep previous data


def _s2_crawl():
  """Live Server 1 country list from LZT.

  Checks EVERY ISO country code plus every code LZT really returns, with the
  country[] filter. Countries are published as they are found. Failed lookups
  are retried and never delete a country that was known before; countries from
  the last saved list stay visible while the new crawl is still running."""
  previous = {}
  for c in (_s2_countries_cache.get("data") or []):
    if isinstance(c, dict) and c.get("code"):
      previous[str(c["code"]).upper()] = c

  codes = set(_ISO_COUNTRY_NAMES.keys()) | set(previous.keys())
  try:
    codes |= _s2_discover_codes()
  except Exception as ex:
    logger.warning("s1 country discovery skipped: %s", ex)
  # most popular first so the menu fills with useful countries quickly
  _first = ["IN", "US", "GB", "ID", "BR", "RU", "UA", "PH", "VN", "TR", "NG", "PK", "BD", "EG",
            "ZA", "KE", "MX", "CO", "AR", "TH", "MY", "DE", "FR", "ES", "IT", "PL", "CA", "AU"]
  ordered_codes = [c for c in _first if c in codes] + sorted(c for c in codes if c not in _first)

  found, failed, checked, fatal_stop = {}, set(), 0, False
  for code in ordered_codes:
    if checked:
      time.sleep(S2_PAGE_DELAY)          # LZT: Category Search 20 req/min
    checked += 1
    row, fatal, ok = _s2_check_code(code)
    if fatal:
      fatal_stop = True
      break
    if not ok:
      failed.add(code)
    if row:
      found[row["code"]] = row
    live = dict(previous)
    for k in list(live.keys()):
      if k in ordered_codes[:checked] and k not in failed:
        live.pop(k, None)                # checked and now empty -> really gone
    live.update(found)
    _s2_publish(sorted(live.values(), key=lambda c: (c.get("price") or 0, c.get("name") or "")),
                done=False)

  # Deep discovery: any country the API really has, even if it is not in our name table.
  if not fatal_stop:
    try:
      _extra = _s2_discover_codes(max_pages=15) - set(ordered_codes)
    except Exception as ex:
      logger.warning("s1 deep country discovery skipped: %s", ex)
      _extra = set()
    for code in sorted(_extra):
      time.sleep(S2_PAGE_DELAY)
      checked += 1
      row, fatal, ok = _s2_check_code(code)
      if fatal:
        fatal_stop = True
        break
      if not ok:
        failed.add(code)
      if row:
        found[row["code"]] = row

  final = dict(found)
  for k in failed:                         # transient failures keep the old entry
    if k in previous and k not in final:
      final[k] = previous[k]
  if fatal_stop:                           # bad key etc: do not wipe the list
    for k, v in previous.items():
      final.setdefault(k, v)
  countries = sorted(final.values(), key=lambda c: (c.get("price") or 0, c.get("name") or ""))
  if countries:
    _s2_publish(countries, done=not fatal_stop)
  logger.info("s1 countries: %d countries found from %d codes checked (%d failed)",
              len(countries), checked, len(failed))
  return countries


def fetch_s2_countries(force_refresh=False):
  """Country list for Server 1. Never blocks: it returns what is known right now
  (even while the background crawl is still running) and starts a crawl when needed."""
  if _is_reseller_upstream(1):
    cached = _s2_countries_cache.get("data") or []
    age = time.time() - _s2_countries_cache.get("ts", 0)
    if cached and not force_refresh and age < S2_COUNTRIES_TTL:
      return cached
    result = _reseller_fetch_countries(1, force_refresh=force_refresh)
    if isinstance(result, list):
      return result
    if cached:
      return cached
    return result if isinstance(result, dict) else {"error": "Country list is loading. Please try again in a minute."}
  cached = _s2_countries_cache.get("data") or []
  age = time.time() - _s2_countries_cache.get("ts", 0)
  if cached:
    if force_refresh or _s2_countries_cache.get("partial") or age >= S2_COUNTRIES_TTL:
      _s2_refresh_in_background()
    return cached
  _s2_refresh_in_background()
  return {"error": "Country list is loading. Please try again in a minute."}


def find_s2_country(country_code, force_refresh=False):
  code = str(country_code or "").strip().upper()
  data = fetch_s2_countries(force_refresh)
  if isinstance(data, dict):
    return None
  for item in data:
    if item.get("code") == code:
      return item
  return None


def fetch_s1_country_detail(country_code, spam=None, force_refresh=False,
                            premium=None, email=None, cat=None):
  """Live stock + price ladder for one country from LZT Market."""
  code = str(country_code or "").strip().upper()
  if not code:
    return {"error": "Invalid country."}
  if _is_reseller_upstream(1):
    data = fetch_s2_countries(force_refresh)
    if isinstance(data, dict):
      return {"error": data.get("error") or "Country list is loading."}
    row = next((c for c in (data or []) if str(c.get("code") or "").upper() == code), None)
    if not row:
      return {"error": "This country is not available."}
    try:
      price = float(row.get("price") or 0)
    except Exception:
      price = 0.0
    try:
      stock = int(row.get("stock") if row.get("stock") is not None else 1)
    except Exception:
      stock = 1
    return {
      "code": code,
      "name": clean_country_name(row.get("name") or code),
      "stock": stock,
      "price": price,
      "ladder": [f"{price:.2f}".rstrip("0").rstrip(".")] if price else [],
      "stale": False,
      "reseller": True,
    }
  items = fetch_s1_items(code, force_refresh=force_refresh, spam=spam, limit=20,
                         premium=premium, email=email, cat=cat)
  if isinstance(items, dict):
    return items
  prices = sorted({float(i["price"]) for i in items if float(i.get("price") or 0) > 0})
  _cat = cat if cat in ("push", "autoreg", "premium") else None
  _key = f"{code}|{spam or ''}|{premium or ''}|{email or ''}|{_cat or ''}"
  _real = _s1_totals.get(_key)
  return {
    "code": code,
    "name": _lzt_country_name(code),
    "stock": max(len(items), int(_real)) if _real is not None else len(items),
    "price": prices[0] if prices else 0.0,
    "ladder": [f"{p:.2f}".rstrip("0").rstrip(".") for p in prices[:5]],
    "stale": False,
  }


# ---- Per-account listing for Server 1 (LZT Market) ---------------------------
S1_ITEMS_PATH = "/telegram"
S1_ITEMS_PER_PAGE = 20
_s1_items_cache = {}
_s1_totals = {}          # real stock (API totalItems) per filter combination


def _s1_total_from(res):
  if not isinstance(res, dict):
    return None
  for k in ("totalItems", "total_items", "total", "totalCount"):
    try:
      v = res.get(k)
      if v not in (None, "") and int(v) >= 0:
        return int(v)
    except Exception:
      continue
  return None


def _parse_groups_channels(text):
  """Parse "0 Ch | 0 Grp | 0 Adm" into (channels, groups, admins)."""
  text = str(text or "")
  def grab(pattern):
    m = re.search(pattern, text, re.I)
    return int(m.group(1)) if m else 0
  return (grab(r'(\d+)\s*Ch'), grab(r'(\d+)\s*Grp'), grab(r'(\d+)\s*Adm'))


_MONTHS_SHORT = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _fmt_api_date(v):
  """Turn an API date (ISO string / epoch / 'dd Mon yyyy') into '20 Sep 2026'."""
  if v in (None, "", False, 0):
    return ""
  try:
    if isinstance(v, (int, float)) or (isinstance(v, str) and re.fullmatch(r"\d{9,13}", v.strip())):
      ts = float(v)
      if ts > 1e11:
        ts /= 1000.0
      d = datetime.utcfromtimestamp(ts)
      return f"{d.day} {_MONTHS_SHORT[d.month - 1]} {d.year}"
    s = str(v).strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
      y, mo, da = int(m.group(1)), int(m.group(2)), int(m.group(3))
      return f"{da} {_MONTHS_SHORT[mo - 1]} {y}"
    m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)
    if m:
      da, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
      return f"{da} {_MONTHS_SHORT[mo - 1]} {y}"
    return s[:32]
  except Exception:
    return str(v)[:32]


def _extract_premium_end(it):
  """Find Telegram Premium expiry from common LZT API field shapes."""
  keys = (
    "telegram_premium_expiration", "telegram_premium_expiration_date",
    "telegram_premium_end", "telegram_premium_end_date", "telegram_premium_until",
    "telegram_premium_expires", "telegram_premium_expires_at",
    "premium_ends", "premium_end", "premium_expires", "premium_expiry",
    "premium_until", "premium_valid_till", "premium_expires_at",
    "premium_expiration", "premium_expiration_date", "premium_end_date",
  )
  def scan(obj, depth=0):
    if not isinstance(obj, dict) or depth > 3:
      return ""
    for k, v in obj.items():
      if str(k).lower() in keys and v not in (None, "", False, 0):
        if isinstance(v, dict):
          nested = scan(v, depth + 1)
          if nested:
            return nested
        else:
          return _fmt_api_date(v)
    for k, v in obj.items():
      if isinstance(v, dict) and ("premium" in str(k).lower() or depth == 0):
        nested = scan(v, depth + 1)
        if nested:
          return nested
    return ""
  return scan(it)


def _norm_s1_item(it):
  if not isinstance(it, dict):
    return None
  iid = it.get("item_id") or it.get("account_id") or it.get("id")
  if iid in (None, ""):
    return None
  try:
    raw_price = float(it.get("price") or 0)
  except Exception:
    raw_price = 0.0
  raw_cur = str(it.get("currency") or "USD").strip().upper()
  price_inr = _lzt_to_inr(raw_price, raw_cur)
  cc = str(it.get("telegram_country") or it.get("country") or "").strip().upper()
  _spam_val = None
  for _k in ("telegram_spam_block", "telegram_spam_blocked", "spam_block", "spam"):
    if it.get(_k) not in (None, ""):
      _spam_val = it.get(_k)
      break
  if _spam_val is None:
    for _k, _v in it.items():
      if "spam" in str(_k).lower() and "allow" not in str(_k).lower() and _v not in (None, ""):
        _spam_val = _v
        break
  return {
    "id": str(iid),
    "price": price_inr,
    "raw_price": raw_price,
    "raw_currency": raw_cur,
    "premium": (it.get("telegram_premium") if it.get("telegram_premium") not in (None, "")
                else it.get("premium") if it.get("premium") not in (None, "")
                else it.get("telegram_premium_status")),
    "premium_end": _extract_premium_end(it),
    "raw": it,
    "channels": int(it.get("telegram_channels_count") or 0),
    "groups": int(it.get("telegram_chats_count") or 0),
    "admins": int(it.get("telegram_admin_count") or 0),
    "spam": _spam_val,
    "twofa": it.get("telegram_password") if "telegram_password" in it else it.get("two_fa"),
    "email": it.get("email_type") if it.get("email_type") else it.get("email"),
    "uploaded": _fmt_api_date(it.get("published_date") or it.get("uploaded")),
    "last_seen": _fmt_api_date(it.get("telegram_last_seen") or it.get("last_seen")),
    "origin": str(it.get("item_origin") or it.get("origin") or ""),
    "resale_origin": str(it.get("resale_origin") or ""),
    "dial": "",
    "country": cc,
    "name": str(it.get("title") or _lzt_country_name(cc)),
    "groups_channels": f"{int(it.get('telegram_channels_count') or 0)} Ch | {int(it.get('telegram_chats_count') or 0)} Grp | {int(it.get('telegram_admin_count') or 0)} Adm",
  }


def fetch_s1_items(country_code, force_refresh=False, spam=None, limit=20,
                   premium=None, email=None, cat=None):
  """List individual Telegram accounts for a country from LZT Market.

  Spam-free / spam-blocked searching: the server-side filter is used first; if it
  returns nothing (or errors) the list is fetched WITHOUT it and filtered locally,
  so a filter can never silently empty the list."""
  code = str(country_code or "").strip().upper()
  if _is_reseller_upstream(1):
    return _reseller_s1_accounts(code, limit=limit, spam=spam, premium=premium,
                                 email=email, cat=cat, force_refresh=force_refresh)
  now = time.time()
  cat = cat if cat in ("push", "autoreg", "premium") else None
  key = f"{code}|{spam or ''}|{premium or ''}|{email or ''}|{cat or ''}"
  c = _s1_items_cache.get(key)
  if c and not force_refresh and now - c["ts"] < 30:
    return c["data"]

  cap = max(1, min(max(int(limit or 20), 40), 40))

  def _load(use_spam, pmin=None):
    params = {"country[]": [code], "order_by": "price_to_up", "currency": "usd"}
    if pmin:
      params["pmin"] = pmin      # documented param; API has no `page` (cursor `after` only)
    # Section filter on the server too, so cheap autoreg accounts do not fill the page
    if cat == "push":
      params["not_origin[]"] = ["autoreg"]
    elif cat == "autoreg":
      params["origin[]"] = ["autoreg"]
    if use_spam and str(spam).lower() in ("yes", "no"):
      params["spam"] = str(spam).lower()
    if str(premium).lower() in ("yes", "no"):
      params["premium"] = str(premium).lower()
    if str(email).lower() in ("yes", "no"):
      params["email"] = str(email).lower()
    res = _lzt_call("/telegram", params=params, timeout=60)
    if not res.get("ok"):
      return None, res
    raw = res.get("items")
    if not isinstance(raw, list):
      raw = res.get("data") if isinstance(res.get("data"), list) else []
    return [x for x in (_norm_s1_item(i) for i in raw[:cap]) if x], res

  spam_on = str(spam).lower() in ("yes", "no")

  _only_cat = {"cat": cat, "spam": "any", "premium": "any",
               "origin": "any", "email": "any", "search": ""}

  def _load_pages(use_spam):
    """Section filters are also applied locally. Cheapest-first pages are mostly
    autoreg, so walk up the price ladder with `pmin` (inclusive) until 20 matching
    accounts are found. Search limit is 20 req/min -> 3.1 s between calls."""
    if not cat:
      return _load(use_spam)
    out, seen_ids, last_res, pmin = [], set(), None, None
    for pg in range(3):
      if pg:
        time.sleep(S2_PAGE_DELAY)
      part, r_ = _load(use_spam, pmin)
      last_res = r_
      if part is None:
        return (out or None), r_
      new = [i for i in part if i["id"] not in seen_ids]
      if not new:
        break
      for i in new:
        seen_ids.add(i["id"])
      out += new
      if len(_s1_apply_client_filters(out, _only_cat)) >= 20 or len(part) < 20:
        break
      pmin = max(float(i.get("raw_price") or 0) for i in part) or None
      if not pmin:
        break
    return _s1_apply_client_filters(out, _only_cat), last_res

  items, res = _load_pages(True)
  _used_fallback = False
  if spam_on and (items is None or not items):
    items2, res2 = _load_pages(False)
    if items2:
      _used_fallback = True
      want = (str(spam).lower() == "yes")
      items = [i for i in items2 if _s1_truthy(i.get("spam")) is want]
      res = res2
    elif items is None:
      items, res = items2, res2
  if items is None:
    return {"error": _api_error_text(res)}

  for _it in items:
    if str(premium).lower() in ("yes", "no") and _it.get("premium") in (None, ""):
      _it["premium"] = "Yes" if str(premium).lower() == "yes" else "No"
    if str(email).lower() in ("yes", "no") and _it.get("email") in (None, ""):
      _it["email"] = "Yes" if str(email).lower() == "yes" else "No"
    if spam_on and not _used_fallback:
      # The API already filtered by spam=yes/no: trust it, whatever odd field the item carries.
      _it["spam"] = "Yes" if str(spam).lower() == "yes" else "No"
  # Real stock = what the API says exists for these filters (not just the first page).
  _tot = _s1_total_from(res)
  if _tot is not None and not _used_fallback and cat != "premium":
    _s1_totals[key] = _tot
  else:
    _s1_totals.pop(key, None)
  _s1_items_cache[key] = {"ts": now, "data": items}
  return items


# ---- Orders (LZT Market Fast-Buy) --------------------------------------------
FINAL_ORDER_STATUSES = {"completed", "partial", "failed", "cancelled", "interrupted"}


def create_nobelots_order(country_code=None, account_id=None, max_price=None,
                          spam=None, quantity=1, premium=None, email=None):
  """Buy Telegram account(s) via LZT Market POST /{item_id}/fast-buy."""
  if _is_reseller_upstream(1):
    return _reseller_buy_s1(country_code=country_code, account_id=account_id,
                            max_price=max_price, quantity=quantity)
  target_items = []
  if account_id:
    info = _lzt_call(f"/{quote(str(account_id), safe='')}", params={"currency": "usd"}, timeout=60)
    if info.get("ok") and isinstance(info.get("item"), dict):
      it = info["item"]
      target_items.append({
        "id": str(it.get("item_id") or account_id),
        "raw_price": it.get("price"),
        "raw_currency": it.get("currency") or "USD",
      })
    else:
      target_items.append({"id": str(account_id), "raw_price": None, "raw_currency": "USD"})
  else:
    qty = max(1, int(quantity or 1))
    listed = fetch_s1_items(country_code, True, spam, max(10, qty * 2), premium, email)
    if isinstance(listed, dict):
      return {"ok": False, "error": "api_error", "message": listed.get("error", "Failed to fetch stock.")}
    for it in listed:            # every candidate; we stop as soon as `qty` are bought
      target_items.append({
        "id": str(it["id"]),
        "raw_price": it.get("raw_price"),
        "raw_currency": it.get("raw_currency") or "USD",
      })

  if not target_items:
    return {"ok": False, "error": "no_stock", "message": "No matching Telegram accounts available."}

  bought = []
  last_err = None
  _want = 1 if account_id else max(1, int(quantity or 1))
  _fails = 0
  for t in target_items:
    if len(bought) >= _want or _fails >= 4:
      break
    if not account_id and bought is not None and target_items and t is not target_items[0]:
      # fallback accounts must not be noticeably dearer than the one the user was quoted
      try:
        _base = float(target_items[0].get("raw_price") or 0)
        _this = float(t.get("raw_price") or 0)
        if _base and _this and _this > _base * 1.3:
          continue
      except Exception:
        pass
    iid = t["id"]
    payload = {}
    if t.get("raw_price") not in (None, ""):
      try:
        payload["price"] = float(t["raw_price"])
      except Exception:
        pass
    res = _lzt_call(f"/{quote(iid, safe='')}/fast-buy", method="POST", payload=payload, timeout=300)
    if res.get("ok"):
      item = res.get("item") or {}
      login_data = item.get("loginData") or {}
      phone = str(item.get("telegram_phone") or login_data.get("login") or "").strip()
      pwd = str(login_data.get("password") or "").strip()
      item_inr = _lzt_to_inr(item.get("price"), item.get("currency") or t.get("raw_currency") or "USD") if item.get("price") else float(max_price or 0)
      try:
        # Field NAMES only (no values): helps trace what LZT returns for a purchase.
        logger.info("fast-buy item keys=%s loginData keys=%s",
                    sorted(item.keys()), sorted(login_data.keys()))
      except Exception:
        pass
      bought.append({
        "order_no": str(item.get("item_id") or iid),
        "phone": phone,
        "price": item_inr,
        "password": pwd,
        "session": _session_from_item(item),
      })
    else:
      last_err = res
      _fails += 1
      _etxt = str(res.get("message") or res.get("error") or "").lower()
      if any(w in _etxt for w in ("not enough", "balance", "insufficient", "missing_api_key")):
        break                      # trying other accounts cannot fix this

  if not bought:
    return last_err or {"ok": False, "error": "account_unavailable", "message": "Account purchase failed."}

  batch_id = f"ORD-{bought[0]['order_no']}-{int(time.time())}"
  _LZT_COMPLETED_BATCHES[batch_id] = {
    "ok": True,
    "batch_id": batch_id,
    "status": "completed",
    "accounts": bought,
  }
  return {"ok": True, "batch_id": batch_id}


def wait_nobelots_order(batch_id, max_seconds=120):
  """Return completed LZT Market order details."""
  batch_id = str(batch_id or "").strip()
  if not batch_id:
    return {"ok": False, "error": "bad_batch", "message": "Missing batch id."}
  done = _LZT_COMPLETED_BATCHES.pop(batch_id, None)
  if done:
    return done
  return {"ok": False, "status": "failed",
          "end": {"reason": "not_found", "message": "Order record not found."}}


def _clean_otp(value):
  """Show only the code. Older orders stored the whole LZT dict as text."""
  s = str(value or "").strip()
  if s.startswith("{"):
    try:
      import ast
      d = ast.literal_eval(s)
      if isinstance(d, dict):
        return str(d.get("code") or "")
    except Exception:
      pass
  return s


def _otp_gap(code):
  """0 0 0 9 0 -- digits spaced apart so the code is easy to read and type."""
  s_ = str(code if code is not None else "").strip()
  if not s_ or s_ == "-":
    return s_ or "-"
  return " ".join(ch for ch in s_ if not ch.isspace())


def fetch_s2_code(order_no):
  """Fetch the Telegram login code for a bought LZT Market account (GET /{item_id}/telegram-login-code)."""
  # Reseller orders use ids like T-... or the reseller batch id stored on the order.
  if _is_reseller_upstream(1) or str(order_no or "").startswith("T-"):
    # Prefer order_id from s2_orders when account_no is the provider item id.
    oid = str(order_no or "").strip()
    try:
      row = cur.execute(
        "SELECT order_id FROM s2_orders WHERE order_id=? OR account_no=? ORDER BY rowid DESC LIMIT 1",
        (oid, oid)).fetchone()
      if row and row[0]:
        oid = str(row[0])
    except Exception:
      pass
    res = _reseller_order_poll(oid, server_no=1)
    if not res.get("ok"):
      return {"ok": False, "error": res.get("error") or "no_code_yet",
              "message": res.get("message") or "Login code not received yet."}
    code = str(res.get("code") or "").strip()
    if not code:
      return {"ok": False, "error": "no_code_yet",
              "message": "Login code not received yet. Request the code in Telegram, then tap Check Code again."}
    return {"ok": True, "code": code}
  res = _lzt_call(f"/{quote(str(order_no), safe='')}/telegram-login-code", method="GET", timeout=60)
  if not res.get("ok"):
    if res.get("status") == 404 or str(res.get("error") or "") == "http_404":
      # The API answers 404 "Telegram login code not found" until Telegram sends the code.
      return {"ok": False, "error": "no_code_yet",
              "message": "Login code not received yet. Request the code in Telegram, then tap Check Code again."}
    if res.get("status") == 403 or str(res.get("error") or "") == "http_403":
      logger.warning("LZT telegram-login-code 403 for item %s (bot session invalid)", order_no)
      return {"ok": False, "error": "session_invalid",
              "message": "The bot session for this account is no longer valid (it was logged out or the account is blocked). Log in with the number and the Telegram code directly."}
    return res
  codes = res.get("codes") or []
  raw_code = None
  if isinstance(codes, list) and codes:
    raw_code = codes[0]
    # If the API gives dates, pick the newest one (not just the first entry).
    try:
      dated = [c for c in codes if isinstance(c, dict) and c.get("date")]
      if dated:
        raw_code = max(dated, key=lambda c: float(c.get("date") or 0))
    except Exception:
      raw_code = codes[0]
  else:
    raw_code = res.get("code")
  if isinstance(raw_code, dict):
    raw_code = raw_code.get("code")
  code = str(raw_code or "")
  if not code:
    return {"ok": False, "error": "no_code_yet", "message": "No login code received yet."}
  return {"ok": True, "code": code}


_TG_DC_IPS = {
  1: "149.154.175.53",
  2: "149.154.167.51",
  3: "149.154.175.100",
  4: "149.154.167.91",
  5: "91.108.56.130",
}


def _build_telethon_string_session(dc_id, auth_key_hex):
  import base64, socket, struct
  dc = int(dc_id)
  ip = _TG_DC_IPS.get(dc)
  if not ip:
    return ""
  clean_hex = re.sub(r"[^0-9a-fA-F]", "", str(auth_key_hex or ""))
  if len(clean_hex) != 512:
    return ""
  raw_key = bytes.fromhex(clean_hex)
  packed = struct.pack(">B4sH256s", dc, socket.inet_aton(ip), 443, raw_key)
  return "1" + base64.urlsafe_b64encode(packed).decode("ascii")


def _session_from_item(item):
  """Telethon StringSession built from an LZT item payload ('' when absent)."""
  if not isinstance(item, dict):
    return ""
  login_data = item.get("loginData") if isinstance(item.get("loginData"), dict) else {}
  dc_id = item.get("telegram_dc_id") or login_data.get("dc_id") or ""
  auth_key = item.get("telegram_auth_key") or login_data.get("auth_key") or ""
  sess = str(item.get("string_session") or login_data.get("string_session") or "").strip()
  if not sess and dc_id and auth_key:
    try:
      sess = _build_telethon_string_session(dc_id, auth_key)
    except Exception:
      sess = ""
  return sess


def fetch_account_session(order_no):
  """Fetch item data from LZT Market (GET /{item_id}) and construct Telethon StringSession."""
  # Clone bots: Server 1 is served by the main Reseller API, so ask /v1/session.
  if _is_reseller_upstream(1):
    oid = str(order_no or "").strip()
    try:
      row = cur.execute(
        "SELECT order_id FROM s2_orders WHERE order_id=? OR account_no=? ORDER BY rowid DESC LIMIT 1",
        (oid, oid)).fetchone()
      if row and row[0]:
        oid = str(row[0])
    except Exception:
      pass
    res = _reseller_session(oid)
    if res.get("ok"):
      try:
        cur.execute("UPDATE s2_orders SET session_str=? WHERE order_id=?",
                    (str(res["string_session"]), oid))
        db.commit()
      except Exception:
        pass
    return res
  res = _lzt_call(f"/{quote(str(order_no), safe='')}", method="GET", timeout=60)
  if not res.get("ok"):
    if res.get("status") == 404 or str(res.get("error") or "") == "http_404":
      logger.warning("LZT GET /%s returned 404 (session data not available)", order_no)
      return {"ok": False, "error": "session_unavailable",
              "message": "Session string is not available from the provider for this account (404). Use Get Code to log in with the number."}
    if res.get("status") == 403 or str(res.get("error") or "") == "http_403":
      logger.warning("LZT GET /%s 403 (bot session invalid)", order_no)
      return {"ok": False, "error": "session_invalid",
              "message": "The bot session for this account is no longer valid (it was logged out or the account is blocked). Log in with the number and the Telegram code directly."}
    return res
  item = res.get("item") if isinstance(res.get("item"), dict) else res
  login_data = item.get("loginData") if isinstance(item.get("loginData"), dict) else {}
  dc_id = item.get("telegram_dc_id") or login_data.get("dc_id") or ""
  auth_key = item.get("telegram_auth_key") or login_data.get("auth_key") or ""
  sess = str(item.get("string_session") or login_data.get("string_session") or "").strip()
  if not sess and dc_id and auth_key:
    try:
      sess = _build_telethon_string_session(dc_id, auth_key)
    except Exception:
      sess = ""
  if not sess:
    return {"ok": False, "error": "session_unavailable",
            "message": "Session string is not available for this account. Use Get Code to log in via OTP."}
  return {"ok": True, "string_session": sess, "dc_id": dc_id or "-"}


def fetch_phantom_balance(server_no=1):
  """Provider wallet: LZT /me, or Reseller /v1/balance when upstream is reseller."""
  if _is_reseller_upstream(server_no):
    return _reseller_balance(server_no)
  res = _lzt_call("/me", server_no=server_no, timeout=60)
  if not res.get("ok"):
    return res
  user = res.get("user") if isinstance(res.get("user"), dict) else {}
  raw_cur = str(user.get("currency") or "USD").strip().upper()
  try:
    raw_bal = float(user.get("balance") or 0)
  except Exception:
    raw_bal = 0.0
  inr_bal = round(_lzt_to_inr(raw_bal, raw_cur), 2)
  return {
    "ok": True,
    "balance": inr_bal,
    "raw_balance": f"{raw_bal} {raw_cur}",
    "currency": "INR",
    "key": {"label": user.get("username") or "LZT Market"},
  }


async def safe_callback_answer(event, message=None, alert=False):
  """Safely acknowledge callback queries without swallowing later error messages."""
  try:
    already_answered = getattr(event, "_store_callback_answered", False)
    if already_answered:
      if message:
        try:
          await event.respond(str(message))
        except Exception:
          pass
      return
    setattr(event, "_store_callback_answered", True)
    await event.answer(message, alert=alert)
  except Exception:
    if message:
      try:
        await event.respond(str(message))
      except Exception:
        pass

_FREE_MAIL_DOMAINS = (
  'gmail.com', 'googlemail.com', 'yahoo.com', 'yahoo.in', 'outlook.com',
  'hotmail.com', 'live.com', 'proton.me', 'protonmail.com', 'icloud.com',
  'rediffmail.com', 'mail.com', 'yandex.com', 'zoho.com',
)
_UTR_IN_PROGRESS = set()


async def check_payment_in_gmail_async(utr_to_find, gmail_user, gmail_pass,
                                       expected_amount=None, wait_seconds=0,
                                       trusted_override=None):
  """Verify a payment notification from Gmail IMAP (fast + safe).

  * ONE IMAP connection is reused; with wait_seconds > 0 the mailbox is polled
    every ~3s until the mail arrives, so a payment is credited the moment its
    email lands (no new login / full rescan per retry).
  * Search order per poll: Gmail X-GM-RAW (same index as the Gmail search box),
    IMAP TEXT, then a small "newest mails" scan as a last resort.
  * The UTR must literally appear in the mail body; the amount is read from the
    text around the UTR first, then from payment-labelled values.
  * Anti-fake: mails from free-mail senders (anyone can type a fake "payment"
    mail from their own Gmail) and mails whose SPF/DKIM explicitly failed are
    ignored. Optional admin setting `imap_trusted_senders` (comma separated
    substrings, e.g. "fampay,famapp") restricts matches to those senders.
  Returns the paid amount (float) or None.
  """
  def clean_text(value):
    if value is None:
      return ""
    if isinstance(value, (bytes, bytearray)):
      value = value.decode('utf-8', errors='ignore')
    value = html.unescape(str(value))
    value = re.sub(r'<(?:style|script)[^>]*>.*?</(?:style|script)>', ' ', value, flags=re.I | re.S)
    value = re.sub(r'<br\s*/?>', '\n', value, flags=re.I)
    value = re.sub(r'</(?:p|div|li|tr|td|h[1-6])>', ' \n', value, flags=re.I)
    value = re.sub(r'<[^>]+>', ' ', value)
    value = value.replace('\xa0', ' ').replace('\u200b', '')
    return re.sub(r'\s+', ' ', value).strip()

  def norm_ref(value):
    return re.sub(r'[^A-Z0-9]', '', str(value or '').upper())

  def extract_amounts(text):
    text = clean_text(text).upper()
    patterns = [
      r'(?:₹|RS\.?|INR)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)',
      r'([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(?:₹|RS\b\.?|INR)',
      r'(?:AMOUNT\s*(?:PAID|RECEIVED|SENT|CREDITED)?|PAID|RECEIVED|CREDITED|TRANSACTION\s+AMOUNT|TRANSFERRED)\s*[:=-]?\s*(?:₹|RS\.?|INR)?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)',
    ]
    vals = []
    for pat in patterns:
      for m in re.findall(pat, text, flags=re.I):
        try:
          v = float(str(m).replace(',', ''))
          if 0 < v < 100000000:
            vals.append(v)
        except Exception:
          pass
    return list(dict.fromkeys(vals))

  def decode_part(part):
    try:
      payload = part.get_payload(decode=True)
      if payload is None:
        payload = part.get_payload()
      charset = part.get_content_charset() or 'utf-8'
      if isinstance(payload, (bytes, bytearray)):
        try:
          return payload.decode(charset, errors='ignore')
        except LookupError:
          return payload.decode('utf-8', errors='ignore')
      return str(payload or '')
    except Exception:
      return str(part.get_payload() or '')

  def decode_header_text(value):
    try:
      from email.header import decode_header, make_header
      return str(make_header(decode_header(str(value or ''))))
    except Exception:
      return str(value or '')

  def message_text(msg):
    pieces = [decode_header_text(msg.get('Subject')), str(msg.get('From') or ''), str(msg.get('To') or '')]
    if msg.is_multipart():
      for part in msg.walk():
        if part.get_content_maintype() == 'multipart':
          continue
        if (part.get_content_type() or '').lower() in ('text/plain', 'text/html'):
          pieces.append(decode_part(part))
    else:
      pieces.append(decode_part(msg))
    return clean_text('\n'.join(pieces))

  def sender_ok(msg, trusted):
    frm = str(msg.get('From') or '').lower()
    m = re.search(r'@([a-z0-9.\-]+)', frm)
    domain = m.group(1) if m else ''
    if trusted:
      if not any(t in frm for t in trusted):
        return False
      # Even a trusted sender name is rejected when SPF/DKIM explicitly FAILED (spoofed From).
      _auth = ' '.join(str(h) for h in (msg.get_all('Authentication-Results') or [])).lower()
      if re.search(r'\b(?:dkim|spf|dmarc)=(?:fail|softfail)\b', _auth) and 'dkim=pass' not in _auth and 'spf=pass' not in _auth:
        return False
      return True
    if domain and any(domain == d or domain.endswith('.' + d) for d in _FREE_MAIL_DOMAINS):
      return False
    auth = ' '.join(str(h) for h in (msg.get_all('Authentication-Results') or [])).lower()
    if re.search(r'\b(?:dkim|spf|dmarc)=(?:fail|softfail|none)\b', auth) and 'dkim=pass' not in auth and 'spf=pass' not in auth:
      return False
    return True

  def pick_amount(body, utr_norm, expected):
    local = body
    try:
      flexible = r'[^A-Za-z0-9]{0,3}'.join(re.escape(c) for c in utr_norm)
      m = re.search(flexible, body, flags=re.I)
      if m:
        local = body[max(0, m.start() - 400):m.end() + 400]
    except Exception:
      pass
    amounts = extract_amounts(local) or extract_amounts(body)
    if not amounts:
      return None
    if expected is None:
      return max(amounts)
    exact = [a for a in amounts if abs(a - expected) < 0.01]
    if exact:
      return exact[0]
    sufficient = [a for a in amounts if a + 0.01 >= expected]
    if sufficient:
      return min(sufficient)
    return None

  def fetch_sync():
    mail = None
    try:
      user = (gmail_user or '').strip()
      password = re.sub(r'\s+', '', (gmail_pass or '').strip())
      if not user or not password:
        logger.error('Payment verification: Gmail credentials are missing.')
        return None
      server_row = cur.execute("SELECT value FROM settings WHERE key='imap_server'").fetchone()
      server = (server_row[0].strip() if server_row and server_row[0] else 'imap.gmail.com')
      if not re.fullmatch(r'[A-Za-z0-9._-]+', server):
        server = 'imap.gmail.com'
      tr_row = cur.execute("SELECT value FROM settings WHERE key='imap_trusted_senders'").fetchone()
      trusted = [x.strip().lower() for x in (tr_row[0] if tr_row and tr_row[0] else '').split(',') if x.strip()]
      if trusted_override:
        # Per-method sender filter (e.g. BharatPe) wins over the global setting.
        trusted = [x.strip().lower() for x in str(trusted_override).split(',') if x.strip()]
      utr_norm = norm_ref(utr_to_find)
      if len(utr_norm) < 6:
        return None
      expected = float(expected_amount) if expected_amount is not None else None
      raw_utr = str(utr_to_find).replace('"', '').replace('\\', '').strip()
      terms = [t for t in dict.fromkeys([raw_utr, utr_norm]) if t]

      mail = imaplib.IMAP4_SSL(server, 993, timeout=30)
      mail.login(user, password)
      is_gmail = 'gmail' in server or 'google' in server

      folders = []
      for f in ('INBOX', '[Gmail]/All Mail', '[Google Mail]/All Mail', '[Gmail]/Spam', '[Google Mail]/Spam'):
        try:
          st, _ = mail.select(f, readonly=True)
          if st == 'OK':
            folders.append(f)
        except Exception:
          pass
      # All Mail already contains INBOX + Spam; keep it first-class but still
      # check INBOX first because it is the fastest for fresh mail.
      if not folders:
        folders = ['INBOX']

      checked = set()
      deadline = time.time() + max(0, int(wait_seconds or 0))
      poll = 0
      while True:
        poll += 1
        for folder in folders:
          try:
            st, _ = mail.select(folder, readonly=True)
            if st != 'OK':
              continue
            ids = []
            for term in terms:
              if is_gmail:
                try:
                  st, data = mail.search(None, 'X-GM-RAW', f'"{term}"')
                  if st == 'OK' and data and data[0]:
                    ids += data[0].split()
                except Exception:
                  pass
              try:
                st, data = mail.search(None, 'TEXT', f'"{term}"')
                if st == 'OK' and data and data[0]:
                  ids += data[0].split()
              except Exception:
                pass
            if not ids:
              # Last resort: newest mails of the last 2 days (index lag).
              since = (datetime.utcnow() - timedelta(days=2)).strftime('%d-%b-%Y')
              st, data = mail.search(None, 'SINCE', since)
              if st == 'OK' and data and data[0]:
                ids = data[0].split()[-60:]
            for mid in reversed(list(dict.fromkeys(ids))[-100:]):
              key = (folder, mid)
              if key in checked:
                continue
              try:
                st, data = mail.fetch(mid, '(BODY.PEEK[])')
                if st != 'OK':
                  continue
                rawparts = [x[1] for x in data if isinstance(x, tuple) and len(x) > 1]
                if not rawparts:
                  continue
                msg = email.message_from_bytes(b''.join(rawparts))
                body = message_text(msg)
                if utr_norm not in norm_ref(body):
                  checked.add(key)
                  continue
                if not sender_ok(msg, trusted):
                  logger.info('Payment verification: ignored mail from untrusted sender %s', msg.get('From'))
                  checked.add(key)
                  continue
                amount = pick_amount(body, utr_norm, expected)
                if amount is not None:
                  logger.info('Payment verification: UTR %s matched, amount %.2f (poll %d)', utr_to_find, amount, poll)
                  return amount
                checked.add(key)
              except Exception as ex:
                logger.warning('IMAP message parse failed: %s', ex)
          except Exception as ex:
            logger.warning('IMAP search failed for %s: %s', folder, ex)
        if time.time() >= deadline:
          break
        time.sleep(3)
        try:
          mail.noop()
        except Exception:
          pass
      logger.info('Payment verification: no matching Gmail payment found for UTR %s', utr_to_find)
      return None
    except imaplib.IMAP4.error as ex:
      logger.error('Payment verification IMAP login/protocol error (check App Password / IMAP enabled): %s', ex)
      return None
    except Exception as ex:
      logger.error('Payment verification IMAP error: %s: %s', type(ex).__name__, ex)
      return None
    finally:
      if mail is not None:
        try: mail.logout()
        except Exception: pass

  return await asyncio.to_thread(fetch_sync)

_BHARATPE_API_HOST = "https://payments-tesseract.bharatpe.in"
_BHARATPE_LAST_ALERT = [0.0]
_BHARATPE_LAST_ERR = {'code': None, 'body': ''}   # admin diagnostics only, secrets scrubbed


def _bharatpe_request(mid, tok):
  """One call to the merchant transactions API (blocking).
  Returns (kind, transactions): kind is 'ok', 'auth' (token rejected), 'http',
  'net', 'json' or 'shape'. Credentials are never logged."""
  ist = datetime.utcnow() + timedelta(hours=5, minutes=30)   # BharatPe dates are IST
  s_date = (ist - timedelta(days=1)).strftime('%Y-%m-%d')
  e_date = ist.strftime('%Y-%m-%d')
  url = (_BHARATPE_API_HOST + "/api/v1/merchant/transactions?" +
         urlencode({'module': 'PAYMENT_QR', 'merchantId': mid, 'sDate': s_date, 'eDate': e_date}))
  req = urllib.request.Request(url, headers={
    'token': tok, 'Accept': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36'})
  try:
    with urllib.request.urlopen(req, timeout=20) as r:
      raw = r.read().decode('utf-8', 'ignore')
  except urllib.error.HTTPError as ex:
    logger.warning('Payment check (BharatPe) HTTP %s', ex.code)
    try:
      _b = ex.read().decode('utf-8', 'ignore')
    except Exception:
      _b = ''
    _b = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', _b)).strip()
    for _secret in (mid, tok):
      if _secret:
        _b = _b.replace(_secret, '***')
    _BHARATPE_LAST_ERR['code'] = ex.code
    _BHARATPE_LAST_ERR['body'] = _b[:200]
    return ('auth' if ex.code == 401 else ('blocked' if ex.code == 403 else 'http')), []
  except Exception as ex:
    logger.warning('Payment check (BharatPe) request failed: %s', type(ex).__name__)
    return 'net', []
  try:
    data = json.loads(raw)
  except Exception:
    logger.warning('Payment check (BharatPe) returned a non-JSON answer')
    return 'json', []
  d = data.get('data') if isinstance(data, dict) else data
  txns = d.get('transactions') if isinstance(d, dict) else d
  if not isinstance(txns, list):
    if isinstance(data, dict) and str(data.get('responseCode', '')) in ('401', '403'):
      return 'auth', []
    return 'shape', []
  return 'ok', txns


async def bharatpe_test_connection():
  """Admin 'Test Connection' button. Returns a short human message (no secrets)."""
  mid, tok = get_bharatpe_api()
  if not mid or not tok:
    return False, "Merchant ID / Token not set."
  kind, txns = await asyncio.to_thread(_bharatpe_request, mid, tok)
  if kind == 'ok':
    return True, "Connected. %d transaction(s) found for yesterday + today." % len(txns)
  return False, {
    'auth': "BharatPe rejected the token (HTTP 401: expired or wrong). Set a fresh Merchant ID & Token.",
    'blocked': ("BharatPe refused the request (HTTP 403). This can be the token OR BharatPe blocking this server's IP. "
                "Detail: %s" % (_BHARATPE_LAST_ERR.get('body') or '-')),
    'http': "BharatPe returned HTTP %s. Detail: %s" % (_BHARATPE_LAST_ERR.get('code'), _BHARATPE_LAST_ERR.get('body') or '-'),
    'net': "Could not reach BharatPe (network problem on the server).",
    'json': "BharatPe returned an unexpected answer.",
    'shape': "Connected, but the answer format was not recognised.",
  }.get(kind, "Unknown error.")


async def check_payment_bharatpe_api_async(utr_to_find, expected_amount=None, wait_seconds=0):
  """Verify a payment against the admin's own BharatPe merchant account
  (merchant ID + token set by the admin). Only a SUCCESS, received payment whose
  bank reference (UTR) equals the one the user sent counts.
  Returns the paid amount (float) or None. Credentials are never logged and the
  user never sees anything about how verification works."""
  def norm_ref(v):
    return re.sub(r'[^A-Z0-9]', '', str(v or '').upper())

  utr_norm = norm_ref(utr_to_find)
  if len(utr_norm) < 6:
    return None
  mid, tok = get_bharatpe_api()
  if not mid or not tok:
    return None
  expected = float(expected_amount) if expected_amount is not None else None
  auth_failed = [False]

  def fetch_once():
    kind, txns = _bharatpe_request(mid, tok)
    if kind == 'auth':
      auth_failed[0] = True
    if kind != 'ok':
      return None
    for t in txns:
      if not isinstance(t, dict):
        continue
      ref = t.get('bankReferenceNo') or t.get('utr') or t.get('bankRefNo') or t.get('rrn') or ''
      if norm_ref(ref) != utr_norm:
        continue
      if str(t.get('status', 'SUCCESS')).upper() != 'SUCCESS':
        continue
      if str(t.get('type', 'PAYMENT_RECV')).upper() not in ('PAYMENT_RECV', 'RECEIVED', 'CREDIT'):
        continue
      try:
        amount = float(str(t.get('amount')).replace(',', ''))
      except Exception:
        continue
      if expected is not None and amount + 0.01 < expected:
        continue
      return amount
    return None

  deadline = time.time() + max(0, int(wait_seconds or 0))
  while True:
    found = await asyncio.to_thread(fetch_once)
    if found is not None:
      logger.info('Payment verification: UTR matched via merchant API')
      return found
    if auth_failed[0]:
      # Token expired/invalid: tell the admins privately (rate limited), never the user.
      if time.time() - _BHARATPE_LAST_ALERT[0] > 1800:
        _BHARATPE_LAST_ALERT[0] = time.time()
        try:
          await notify_admins(f"{P_WARN} <b>BharatPe token rejected.</b> Set a fresh Merchant ID & Token in "
                              f"Admin → Payment Methods. Users are sent to manual screenshot review meanwhile.")
        except Exception:
          pass
      return None
    if time.time() >= deadline:
      return None
    await asyncio.sleep(4)


def to_usd(inr):
  return round(inr / get_usdt_rate(), 2)

# ================= FREEZE / BAN SYSTEM (advanced) =================
FREEZE_DEFAULT_REASON = "Under investigation"

def is_protected_user(uid):
  """Owner + every admin are immune to freeze/ban."""
  try:
    uid = int(uid)
    return uid == ADMIN_ID or is_admin(uid)
  except Exception:
    return False

def _fmt_left(secs):
  secs = max(0, int(secs)); d, r = divmod(secs, 86400); h, r = divmod(r, 3600); m = r // 60
  parts = []
  if d: parts.append(f"{d}d")
  if h: parts.append(f"{h}h")
  if m or not parts: parts.append(f"{m}m")
  return " ".join(parts)

def _mod_log(target, actor, action, note=""):
  try:
    cur.execute("INSERT INTO moderation_log (target_id,actor_id,action,note,created_at) VALUES (?,?,?,?,?)",
                (int(target), int(actor or 0), action, note, int(time.time())))
    db.commit()
  except Exception as ex:
    logger.warning("moderation_log failed: %s", ex)

def get_restriction(uid):
  """None if the user is free; else {'kind': 'frozen'|'banned', 'until': epoch|0, 'reason': str}.
  Admins are never restricted. Timed freezes auto-expire."""
  if not uid or is_protected_user(uid): return None
  res = cur.execute("SELECT COALESCE(banned,0), COALESCE(frozen,0), COALESCE(freeze_until,0), COALESCE(freeze_reason,'') FROM users WHERE user_id=?", (uid,)).fetchone()
  if not res: return None
  banned, frozen, until, reason = res
  if banned: return {'kind': 'banned', 'until': 0, 'reason': reason}
  if frozen:
    if until and until <= time.time():
      cur.execute("UPDATE users SET frozen=0, freeze_until=0 WHERE user_id=?", (uid,)); db.commit()
      _mod_log(uid, 0, "auto_unfreeze", "timer expired")
      return None
    return {'kind': 'frozen', 'until': int(until or 0), 'reason': reason or FREEZE_DEFAULT_REASON}
  return None

def is_user_banned(uid):
  return get_restriction(uid) is not None

def _restriction_text(r):
  if r['kind'] == 'frozen':
    t = (f"{P_WAIT} <b>Account Under Investigation</b>\n\n"
         f"{P_WARN} You are under investigation. <b>Please wait some time.</b>\n"
         "Buying and all services are temporarily paused for your account.")
    if r.get('until'):
      t += f"\n\n{P_CAL} Review time left: <b>{_fmt_left(r['until'] - time.time())}</b>"
    t += "\n\nIf you think this is a mistake, contact support."
    return t
  return (f"{P_NO} <b>Access Restricted</b>\n\nYour account has been banned from using this bot.\n"
          "If you think this is a mistake, contact support.")

def _restriction_alert(r):
  if r['kind'] == 'frozen':
    left = f" (~{_fmt_left(r['until'] - time.time())} left)" if r.get('until') else ""
    return f"You are under investigation. Please wait some time.{left}"
  return "Your account is banned."

def _support_buttons():
  try:
    url = get_support_url()
    if url and _has_valid_button_url(url):
      return [[Button.url("Contact Support", url)]]
  except Exception:
    pass
  return None

async def _notify_user(target, text, support=True):
  try:
    await bot.send_message(int(target), custom_emoji_text(text), buttons=(_support_buttons() if support else None), parse_mode="html")
  except Exception as ex:
    logger.info("notify_user %s failed: %s", target, ex)

_RESTRICT_NOTICE_TS = {}

# Registered before every other handler -> frozen/banned users can't reach ANY
# service (buy, deposit, SMM, shop ...). Admins always pass through.
@bot.on(events.NewMessage(incoming=True))
async def _restriction_gate_message(e):
  uid = e.sender_id
  try: r = get_restriction(uid) if uid else None
  except Exception: r = None
  if not r: return
  try:
    if getattr(e, "is_private", True) and time.time() - _RESTRICT_NOTICE_TS.get(uid, 0) > 15:
      _RESTRICT_NOTICE_TS[uid] = time.time()
      await e.respond(custom_emoji_text(_restriction_text(r)), buttons=_support_buttons(), parse_mode="html")
  except Exception as ex:
    logger.info("restriction notice failed: %s", ex)
  raise events.StopPropagation

@bot.on(events.CallbackQuery)
async def _restriction_gate_callback(e):
  uid = e.sender_id
  try: r = get_restriction(uid) if uid else None
  except Exception: r = None
  if not r: return
  try: await safe_callback_answer(e, _restriction_alert(r), alert=True)
  except Exception: pass
  raise events.StopPropagation

def update_balance(uid, amount):
  cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, uid))
  db.commit()

# ================= FULL BACKUP / RESTORE (script + database + sessions) =================
DB_FILE = os.environ.get("DB_PATH", "otp_bot_final.db")
SCRIPT_PATH = os.path.abspath(__file__)
BACKUP_EXTRA_FILES = ["23593.jpg", "23593.mp4"]   # welcome photo / welcome video
BACKUP_DIRS = ["sessions"]           # all stock .session files

def _restore_path_ok(rel):
  rel = str(rel).replace("\\", "/")
  if not rel or rel.startswith("/") or ".." in rel.split("/"):
    return False
  return rel in BACKUP_EXTRA_FILES or any(rel.startswith(d + "/") for d in BACKUP_DIRS)

def build_full_backup():
  """Create ONE zip: bot script + database snapshot + sessions + welcome photo."""
  ts = datetime.now().strftime('%Y%m%d_%H%M%S')
  zip_path = f"full_backup_{ts}.zip"
  snap = f"_db_snapshot_{ts}.db"
  try:
    db.commit()
    dst = sqlite3.connect(snap)
    try:
      db.backup(dst)
    finally:
      dst.close()
    n_files = 0
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
      zf.write(SCRIPT_PATH, "bot_script.py")
      zf.write(snap, DB_FILE)
      for extra in BACKUP_EXTRA_FILES:
        if os.path.isfile(extra):
          zf.write(extra, "files/" + extra); n_files += 1
      for d in BACKUP_DIRS:
        for root, _, files in os.walk(d):
          for fn in files:
            full = os.path.join(root, fn)
            zf.write(full, "files/" + os.path.relpath(full).replace(os.sep, "/")); n_files += 1
      zf.writestr("backup_info.json", json.dumps({
        "created": ts, "script": os.path.basename(SCRIPT_PATH), "db": DB_FILE, "files": n_files}))
  finally:
    try: os.remove(snap)
    except Exception: pass
  return zip_path, n_files


def build_clones_backup():
  """Zip every cloned bot's database + clone_config.json into ONE file.

  Clone bots live in cloned_bots/<bot_id>/ and each one has its own SQLite
  database. This snapshot keeps their users, wallets, orders and settings safe
  without touching the running clone processes (sqlite backup API).
  Returns (zip_path, n_bots, n_files); zip_path is None when there are no clones.
  """
  import tempfile as _tf
  root = CLONES_ROOT
  if not os.path.isdir(root):
    return None, 0, 0
  ts = datetime.now().strftime('%Y%m%d_%H%M%S')
  zip_path = f"clones_db_backup_{ts}.zip"
  n_bots = 0
  n_files = 0
  with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for name in sorted(os.listdir(root)):
      cdir = os.path.join(root, name)
      if not os.path.isdir(cdir):
        continue
      cfg_path = os.path.join(cdir, CLONE_CONFIG_FILE)
      if not os.path.isfile(cfg_path):
        continue
      n_bots += 1
      try:
        zf.write(cfg_path, "cloned_bots/%s/%s" % (name, CLONE_CONFIG_FILE))
        n_files += 1
      except Exception as ex:
        logger.warning("Clone config backup skipped %s: %s", cfg_path, ex)
      for fn in sorted(os.listdir(cdir)):
        if not fn.lower().endswith((".db", ".sqlite", ".sqlite3")):
          continue
        full = os.path.join(cdir, fn)
        if not os.path.isfile(full):
          continue
        tmp = None
        try:
          fd, tmp = _tf.mkstemp(suffix=".db")
          os.close(fd)
          src = sqlite3.connect(full, timeout=5)
          dst = sqlite3.connect(tmp)
          try:
            src.backup(dst)
          finally:
            dst.close()
            src.close()
          zf.write(tmp, "cloned_bots/%s/%s" % (name, fn))
          n_files += 1
        except Exception as ex:
          logger.warning("Clone DB backup skipped %s: %s", full, ex)
        finally:
          if tmp:
            try:
              os.remove(tmp)
            except Exception:
              pass
    zf.writestr("backup_info.json", json.dumps({
      "created": ts, "type": "clones", "bots": n_bots, "files": n_files}))
  if n_bots == 0:
    try:
      os.remove(zip_path)
    except Exception:
      pass
    return None, 0, 0
  return zip_path, n_bots, n_files

def restore_full_backup(zip_path):
  """Restore script + database + sessions from a full backup zip. Returns (n_files, script_changed)."""
  ts = datetime.now().strftime('%Y%m%d_%H%M%S')
  work = f"_restore_{ts}"
  os.makedirs(work, exist_ok=True)
  try:
    if not zipfile.is_zipfile(zip_path):
      raise ValueError("This is not a valid backup zip.")
    with zipfile.ZipFile(zip_path) as zf:
      names = zf.namelist()
      if "bot_script.py" not in names or DB_FILE not in names:
        raise ValueError("Not a full backup (bot_script.py / database missing).")
      for info in zf.infolist():
        name = info.filename
        if name.endswith("/"): continue
        ok = name in ("bot_script.py", DB_FILE, "backup_info.json") or (
          name.startswith("files/") and _restore_path_ok(name[6:]))
        if not ok: continue
        target = os.path.realpath(os.path.join(work, name))
        if not target.startswith(os.path.realpath(work) + os.sep): continue
        zf.extract(info, work)

    new_script = os.path.join(work, "bot_script.py")
    new_db = os.path.join(work, DB_FILE)
    with open(new_script, "r", encoding="utf-8") as f:
      try: compile(f.read(), "bot_script.py", "exec")
      except SyntaxError as ex: raise ValueError(f"Script in backup is broken: {ex}")
    chk = sqlite3.connect(new_db)
    try:
      if chk.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError("Database in backup is corrupted.")
      tables = {r[0] for r in chk.execute("SELECT name FROM sqlite_master WHERE type='table'")}
      if not {"users", "settings"} <= tables:
        raise ValueError("Database in backup has no users/settings tables.")
    finally:
      chk.close()

    # Safety copies of the current state (kept on the server).
    db.commit()
    safety = sqlite3.connect(f"pre_restore_{ts}.db")
    try: db.backup(safety)
    finally: safety.close()
    try: shutil.copyfile(SCRIPT_PATH, SCRIPT_PATH + ".pre_restore.bak")
    except Exception: pass

    # Database -> straight into the live connection.
    src = sqlite3.connect(new_db)
    try: src.backup(db)
    finally: src.close()
    db.commit()

    # Sessions + welcome photo.
    n_files = 0
    files_root = os.path.join(work, "files")
    for root, _, files in os.walk(files_root):
      for fn in files:
        full = os.path.join(root, fn)
        rel = os.path.relpath(full, files_root).replace(os.sep, "/")
        if not _restore_path_ok(rel): continue
        os.makedirs(os.path.dirname(rel) or ".", exist_ok=True)
        shutil.copy2(full, rel); n_files += 1

    # Script last.
    shutil.copyfile(new_script, SCRIPT_PATH)
    return n_files
  finally:
    shutil.rmtree(work, ignore_errors=True)


# ================= PRO UPGRADE: OWNER-ONLY / STATS / AUTO BACKUP / REDEEM / ADMINS =================
IST_OFFSET = timedelta(hours=5, minutes=30)
AUTO_BACKUP_INTERVAL = 2 * 60 * 60   # automatic server backup every 2 hours (owner chat only)

# Only the OWNER (ADMIN_ID) can use these. Sub-admins never see them and can never run them.
OWNER_ONLY_EXACT = {"serverapis", "smm_api", "backupusr", "restoreusr", "clonebot", "manageadmins",
                    "addadmin", "editadminreq", "automation", "autobackup_tgl", "dailyreport_tgl", "backupnow"}
OWNER_ONLY_PREFIXES = ("srvapi_", "cbm|", "tglperm|", "deladmin|", "deladminask|", "editadmin|")

cur.execute("CREATE TABLE IF NOT EXISTS redeem_log (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "code TEXT, user_id INTEGER, amount INTEGER, claimed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
db.commit()


# ---------- redeem codes: auto-remove when fully used ----------
async def _redeem_notify_owner(code, amount, max_users):
  try:
    await bot.send_message(ADMIN_ID, custom_emoji_text(
      f"{P_GIFT} <b>Redeem code fully used and removed</b>\n\n"
      f"Code: <code>{html.escape(str(code))}</code>\n"
      f"Amount: {P_INR}{amount} x {max_users} users"))
  except Exception:
    pass


def _redeem_after_claim(code, uid, amount):
  # Log the claim, and delete the code as soon as every use is taken.
  try:
    cur.execute("INSERT INTO redeem_log(code,user_id,amount) VALUES(?,?,?)", (code, int(uid), int(amount)))
    row = cur.execute("SELECT used_count,max_users FROM redeem_codes WHERE code=?", (code,)).fetchone()
    finished = bool(row and row[0] >= row[1])
    if finished:
      cur.execute("DELETE FROM redeem_codes WHERE code=?", (code,))
      cur.execute("DELETE FROM redeem_claims WHERE code=?", (code,))
    db.commit()
    if finished:
      _spawn_bg(_redeem_notify_owner(code, amount, row[1]))
  except Exception as ex:
    logger.warning("redeem auto-remove failed: %s", ex)


def _redeem_purge_exhausted():
  try:
    codes = [r[0] for r in cur.execute("SELECT code FROM redeem_codes WHERE used_count>=max_users").fetchall()]
    for c in codes:
      cur.execute("DELETE FROM redeem_codes WHERE code=?", (c,))
      cur.execute("DELETE FROM redeem_claims WHERE code=?", (c,))
    db.commit()
  except Exception as ex:
    logger.warning("redeem purge failed: %s", ex)


async def _redeem_admin_menu(event):
  _redeem_purge_exhausted()
  rows = cur.execute("SELECT code,amount,max_users,used_count,active FROM redeem_codes "
                     "ORDER BY created_date DESC LIMIT 40").fetchall()
  active_n = sum(1 for r in rows if r[4])
  given, claims = cur.execute("SELECT COALESCE(SUM(amount),0), COUNT(*) FROM redeem_log").fetchone()
  msg = (f"{P_GIFT} <b>Redeem Codes</b>\n"
         f"━━━━━━━━━━━━━━━━\n"
         f"Active: <b>{active_n}</b> · Paused: <b>{len(rows) - active_n}</b>\n"
         f"Total redeemed so far: <b>{P_INR}{given}</b> ({claims} claims)\n\n"
         f"<i>Tap a code to pause, resume or remove it. A code is removed automatically once all its uses are taken.</i>")
  if not rows:
    msg += "\n\nNo redeem codes right now."
  btns = []
  for code, amount, mx, used, active in rows:
    label = f"{'ON' if active else 'OFF'} · {code} · ₹{amount} · {used}/{mx}"
    btns.append([Button.inline(label[:60], f"adm_rdinfo|{code}", style=("success" if active else "danger"))])
  btns.append([Button.inline("Create Code", "adm_redeem_add", style="primary")])
  btns.append([Button.inline("Back to Admin", "adm_adminmain")])
  await event.edit(custom_emoji_text(msg), buttons=btns)


async def _redeem_admin_detail(event, code):
  row = cur.execute("SELECT amount,max_users,used_count,active,created_date,created_by FROM redeem_codes WHERE code=?",
                    (code,)).fetchone()
  if not row:
    await safe_callback_answer(event, "This code no longer exists.", alert=True)
    return await _redeem_admin_menu(event)
  amount, mx, used, active, created, by = row
  claimers = [str(r[0]) for r in cur.execute(
    "SELECT user_id FROM redeem_claims WHERE code=? ORDER BY claimed_date DESC LIMIT 10", (code,)).fetchall()]
  msg = (f"{P_GIFT} <b>Redeem Code</b>\n━━━━━━━━━━━━━━━━\n"
         f"Code: <code>{html.escape(code)}</code>\n"
         f"Amount: <b>{P_INR}{amount}</b> per user\n"
         f"Used: <b>{used}/{mx}</b> (left: {max(0, mx - used)})\n"
         f"Status: <b>{'ACTIVE' if active else 'PAUSED'}</b>\n"
         f"Created: {html.escape(str(created or '-'))}\n"
         f"Created by: <code>{by or '-'}</code>")
  if claimers:
    msg += "\n\nRecent users:\n" + "\n".join(f"<code>{c}</code>" for c in claimers)
  btns = [
    [Button.inline("Pause Code" if active else "Resume Code", f"adm_rdtog|{code}", style=("danger" if active else "success"))],
    [Button.inline("Remove Code", f"adm_rdask|{code}", style="danger")],
    [Button.inline("Back to Codes", "adm_redeemcodes", style="primary")],
  ]
  await event.edit(custom_emoji_text(msg), buttons=btns)


# ---------- admins list ----------
async def _admin_label(aid):
  row = cur.execute("SELECT username, first_name FROM users WHERE user_id=?", (int(aid),)).fetchone()
  uname, fname = (row or ("", ""))
  if not uname and not fname:
    try:
      ent = await asyncio.wait_for(bot.get_entity(int(aid)), timeout=4)
      uname = getattr(ent, "username", "") or ""
      fname = getattr(ent, "first_name", "") or ""
      cur.execute("UPDATE users SET username=?, first_name=? WHERE user_id=?", (uname, fname, int(aid)))
      db.commit()
    except Exception:
      pass
  return ("@" + uname) if uname else (fname or "Admin")


# ---------- statistics ----------
_VALID_SALE_SQL = ("COALESCE(refunded,0)=0"
  " AND UPPER(COALESCE(status,'')) NOT LIKE '%REFUND%'"
  " AND UPPER(COALESCE(status,'')) NOT LIKE '%CANCEL%'"
  " AND UPPER(COALESCE(status,'')) NOT LIKE '%FAIL%'"
  " AND UPPER(COALESCE(status,'')) NOT LIKE '%EXPIRE%'"
  " AND UPPER(COALESCE(status,'')) NOT LIKE '%TIMEOUT%'")
_LOST_SALE_SQL = ("(COALESCE(refunded,0)=1"
  " OR UPPER(COALESCE(status,'')) LIKE '%REFUND%'"
  " OR UPPER(COALESCE(status,'')) LIKE '%CANCEL%'"
  " OR UPPER(COALESCE(status,'')) LIKE '%FAIL%'"
  " OR UPPER(COALESCE(status,'')) LIKE '%EXPIRE%'"
  " OR UPPER(COALESCE(status,'')) LIKE '%TIMEOUT%')")
_PENDING_SALE_SQL = (_VALID_SALE_SQL +
  " AND UPPER(COALESCE(status,'')) NOT LIKE '%COMPLETE%'"
  " AND UPPER(COALESCE(status,'')) NOT LIKE '%DELIVER%'"
  " AND UPPER(COALESCE(status,'')) NOT LIKE '%DONE%'")
_DEP_OK_SQL = "lower(status) IN ('approved','success','completed')"
_STAT_PERIODS = {"today": "Today", "7d": "Last 7 Days", "30d": "Last 30 Days", "all": "All Time"}
_SERVICE_LABELS = {"telegram": "Telegram Accounts", "server1": "Server 1", "smm": "Social Media (SMM)",
                   "whatsapp": "WhatsApp OTP", "s3otp": "Server 3 OTP", "shop": "Digital Shop"}


def _fmt_inr(v):
  try:
    return "₹" + format(float(v or 0), ",.2f")
  except Exception:
    return "₹0.00"


def _stats_since(period):
  # Returns a UTC 'YYYY-MM-DD HH:MM:SS' start for the period (day boundaries are IST), or None for all time.
  now_utc = datetime.utcnow()
  if period == "today":
    start = (now_utc + IST_OFFSET).replace(hour=0, minute=0, second=0, microsecond=0) - IST_OFFSET
  elif period == "7d":
    start = now_utc - timedelta(days=7)
  elif period == "30d":
    start = now_utc - timedelta(days=30)
  else:
    return None
  return start.strftime("%Y-%m-%d %H:%M:%S")


def _date_sql(col, since):
  return (" AND datetime(%s) >= datetime('%s')" % (col, since)) if since else ""


def _stats_collect(period):
  since = _stats_since(period)
  d = {}

  def one(q):
    try:
      return cur.execute(q).fetchone()[0] or 0
    except Exception:
      return 0

  d["users_total"] = one("SELECT COUNT(*) FROM users")
  d["users_new"] = one("SELECT COUNT(*) FROM users WHERE 1=1" + _date_sql("joined_date", since))
  d["restricted"] = one("SELECT COUNT(*) FROM users WHERE COALESCE(banned,0)=1 OR COALESCE(frozen,0)=1")
  d["wallet"] = float(one("SELECT COALESCE(SUM(balance),0) FROM users"))
  d["stock"] = one("SELECT COUNT(*) FROM stock WHERE available=1")
  try:
    r = cur.execute("SELECT COALESCE(SUM(amount),0), COUNT(*) FROM deposits WHERE " + _DEP_OK_SQL
                    + _date_sql("date", since)).fetchone()
    d["dep_amt"], d["dep_n"] = float(r[0] or 0), int(r[1] or 0)
  except Exception:
    d["dep_amt"], d["dep_n"] = 0.0, 0
  d["dep_pending"] = one("SELECT COUNT(*) FROM deposits WHERE lower(status)='pending'")

  by = {}
  try:
    for svc, n, amt in cur.execute(
        "SELECT service, COUNT(*), COALESCE(SUM(amount),0) FROM global_orders WHERE " + _VALID_SALE_SQL
        + _date_sql("created_at", since) + " GROUP BY service ORDER BY 3 DESC").fetchall():
      by[str(svc)] = (int(n), float(amt or 0))
  except Exception:
    pass
  d["by_service"] = by
  d["orders_n"] = sum(v[0] for v in by.values())
  d["revenue"] = sum(v[1] for v in by.values())
  try:
    r = cur.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM global_orders WHERE " + _LOST_SALE_SQL
                    + _date_sql("created_at", since)).fetchone()
    d["lost_n"], d["lost_amt"] = int(r[0] or 0), float(r[1] or 0)
  except Exception:
    d["lost_n"], d["lost_amt"] = 0, 0.0
  d["pending_n"] = one("SELECT COUNT(*) FROM global_orders WHERE " + _PENDING_SALE_SQL)

  # Estimated profit: only where the buying cost is known (API servers).
  parts = {}
  try:
    m1 = float(get_server_margin(1))
  except Exception:
    m1 = 0.0
  s1_amt = by.get("server1", (0, 0.0))[1]
  parts["Server 1"] = (s1_amt * m1 / (100.0 + m1)) if m1 > 0 else 0.0
  try:
    rate = float(get_usdt_rate())
  except Exception:
    rate = 94.0
  for label, tbl in (("WhatsApp OTP", "s2_wa_orders"), ("Server 3 OTP", "s3_orders")):
    try:
      r = cur.execute("SELECT COALESCE(SUM(price_inr),0), COALESCE(SUM(cost_usd),0) FROM " + tbl + " WHERE "
                      + _VALID_SALE_SQL + _date_sql("created_at", since)).fetchone()
      parts[label] = float(r[0] or 0) - float(r[1] or 0) * rate
    except Exception:
      parts[label] = 0.0
  d["profit_parts"] = parts
  d["profit"] = sum(parts.values())

  try:
    r = cur.execute("SELECT COALESCE(SUM(amount),0), COUNT(*) FROM redeem_log WHERE 1=1"
                    + _date_sql("claimed_date", since)).fetchone()
    d["redeem_amt"], d["redeem_n"] = float(r[0] or 0), int(r[1] or 0)
  except Exception:
    d["redeem_amt"], d["redeem_n"] = 0.0, 0
  d["redeem_active"] = one("SELECT COUNT(*) FROM redeem_codes WHERE active=1 AND used_count<max_users")
  d["ref_amt"] = float(one("SELECT COALESCE(SUM(bonus),0) FROM referral_earnings WHERE 1=1"
                           + _date_sql("created_at", since)))
  return d


def _stats_text(period, title="BUSINESS DASHBOARD"):
  d = _stats_collect(period)
  label = _STAT_PERIODS.get(period, "All Time")
  avg = (d["revenue"] / d["orders_n"]) if d["orders_n"] else 0.0
  L = [f"{P_STATS} <b>{title}</b>", f"<i>{label}</i>", "━━━━━━━━━━━━━━━━",
       f"{P_MONEY} <b>Total Revenue:</b> <b>{_fmt_inr(d['revenue'])}</b>",
       f"{P_CARD} <b>Total Deposit:</b> <b>{_fmt_inr(d['dep_amt'])}</b> ({d['dep_n']} payments)",
       f"{P_RATE} <b>Estimated Profit:</b> <b>{_fmt_inr(d['profit'])}</b>"]
  for k, v in d["profit_parts"].items():
    if abs(v) > 0.004:
      L.append(f"   └ {k}: {_fmt_inr(v)}")
  L += ["",
        f"{P_CART} <b>Orders:</b> <b>{d['orders_n']}</b> · Avg <b>{_fmt_inr(avg)}</b>",
        f"{P_NO} <b>Refunded / Cancelled:</b> {d['lost_n']} · {_fmt_inr(d['lost_amt'])}",
        f"{P_WAIT} <b>Pending Orders:</b> <b>{d['pending_n']}</b>",
        f"{P_WAIT} <b>Pending Deposits:</b> <b>{d['dep_pending']}</b>"]
  if d["by_service"]:
    L += ["", "<b>Revenue by Service</b>"]
    for svc, (n, amt) in d["by_service"].items():
      L.append(f"   • {_SERVICE_LABELS.get(svc, svc.title())}: <b>{_fmt_inr(amt)}</b> ({n})")
  L += ["",
        f"{P_USERS} <b>Users:</b> <b>{d['users_total']}</b> (new: {d['users_new']}) · Banned/Frozen: {d['restricted']}",
        f"{P_MONEY} <b>Wallet Balance (users hold):</b> {_fmt_inr(d['wallet'])}",
        f"{P_PKG} <b>Available Stock:</b> <b>{d['stock']}</b>",
        f"{P_GIFT} <b>Redeemed:</b> {_fmt_inr(d['redeem_amt'])} ({d['redeem_n']}) · Active codes: {d['redeem_active']}",
        f"{P_USERS} <b>Referral Bonus Paid:</b> {_fmt_inr(d['ref_amt'])}",
        "",
        "<i>Profit is counted only for API servers (Server 1, WhatsApp, Server 3). "
        "Own stock, SMM and Shop cost is not tracked, so it is not in the profit.</i>"]
  return "\n".join(L)


def _user_name_sync(uid):
  try:
    r = cur.execute("SELECT username, first_name FROM users WHERE user_id=?", (int(uid),)).fetchone()
    if r and r[0]:
      return "@" + r[0]
    if r and r[1]:
      return str(r[1])
  except Exception:
    pass
  return "User"


def _stats_top_text(period):
  since = _stats_since(period)
  label = _STAT_PERIODS.get(period, "All Time")
  L = [f"{P_STATS} <b>TOP USERS</b>", f"<i>{label}</i>", "━━━━━━━━━━━━━━━━", "", "<b>Top Buyers</b>"]
  try:
    rows = cur.execute("SELECT user_id, COUNT(*), COALESCE(SUM(amount),0) FROM global_orders WHERE " + _VALID_SALE_SQL
                       + _date_sql("created_at", since) + " GROUP BY user_id ORDER BY 3 DESC LIMIT 5").fetchall()
  except Exception:
    rows = []
  if not rows:
    L.append("No orders yet.")
  for i, (u, n, amt) in enumerate(rows, 1):
    L.append(f"{i}. {html.escape(_user_name_sync(u))} · <code>{u}</code> · {_fmt_inr(amt)} ({n})")
  L += ["", "<b>Top Depositors</b>"]
  try:
    rows = cur.execute("SELECT user_id, COUNT(*), COALESCE(SUM(amount),0) FROM deposits WHERE " + _DEP_OK_SQL
                       + _date_sql("date", since) + " GROUP BY user_id ORDER BY 3 DESC LIMIT 5").fetchall()
  except Exception:
    rows = []
  if not rows:
    L.append("No deposits yet.")
  for i, (u, n, amt) in enumerate(rows, 1):
    L.append(f"{i}. {html.escape(_user_name_sync(u))} · <code>{u}</code> · {_fmt_inr(amt)} ({n})")
  return "\n".join(L)


def _stats_export_csv(period):
  since = _stats_since(period)
  path = "orders_export_%s.csv" % datetime.now().strftime("%Y%m%d_%H%M%S")
  c = db.cursor()
  rows = c.execute("SELECT id,service,local_ref,user_id,amount,status,COALESCE(refunded,0),created_at FROM global_orders "
                   "WHERE 1=1" + _date_sql("created_at", since) + " ORDER BY id DESC").fetchall()
  with open(path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["order_id", "service", "local_ref", "user_id", "amount", "status", "refunded", "created_at_utc"])
    for r in rows:
      w.writerow(["ATS-%08d" % int(r[0])] + list(r[1:]))
  return path, len(rows)


async def _stats_edit(event, text, btns):
  try:
    await event.edit(custom_emoji_text(text), buttons=btns)
  except Exception as ex:
    if "not modified" in str(ex).lower():
      await safe_callback_answer(event, "Already up to date.", alert=False)
    else:
      raise


# ---------- automatic backup (every 2 hours, owner chat only) ----------
async def _send_backup_to_owner(reason="Auto"):
  zip_path = None
  clone_zip = None
  try:
    zip_path, n_files = await asyncio.to_thread(build_full_backup)
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    await bot.send_file(
      ADMIN_ID, zip_path, force_document=True,
      caption=custom_emoji_text(
        f"{P_FOLDER} <b>{reason} Server Backup</b>\n"
        f"{P_DOC} Script + Database + {n_files} session/media files\n"
        f"{P_TIME} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {size_mb:.1f} MB\n\n"
        f"<i>Use the Restore button and send this zip to restore everything.</i>"))
    set_setting("last_auto_backup_ts", int(time.time()))

    # Cloned bots keep their own database inside cloned_bots/<bot_id>/.
    # Snapshot every one of them in the same run so nothing is ever lost.
    try:
      clone_zip, n_bots, n_cfiles = await asyncio.to_thread(build_clones_backup)
      if clone_zip:
        csize = os.path.getsize(clone_zip) / (1024 * 1024)
        await bot.send_file(
          ADMIN_ID, clone_zip, force_document=True,
          caption=custom_emoji_text(
            f"{P_FOLDER} <b>{reason} Cloned Bots Backup</b>\n"
            f"{P_DOC} Bots: <b>{n_bots}</b> | DB + config files: <b>{n_cfiles}</b>\n"
            f"{P_TIME} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {csize:.1f} MB\n\n"
            f"<i>Every clone's database and clone_config.json. Keep this private.</i>"))
    except Exception as cex:
      logger.error("%s clone backup failed: %s", reason, cex, exc_info=True)
    return True
  except Exception as ex:
    logger.error("%s backup failed: %s", reason, ex, exc_info=True)
    try:
      await bot.send_message(ADMIN_ID, custom_emoji_text(f"{P_NO} {reason} backup failed: {html.escape(str(ex))}"))
    except Exception:
      pass
    return False
  finally:
    for _p in (zip_path, clone_zip):
      if _p and os.path.exists(_p):
        try:
          os.remove(_p)
        except Exception:
          pass


async def _auto_backup_loop():
  while True:
    try:
      if get_setting("auto_backup", "on") != "on":
        await asyncio.sleep(300)
        continue
      try:
        last = int(float(get_setting("last_auto_backup_ts", "0") or 0))
      except Exception:
        last = 0
      wait = max(60, AUTO_BACKUP_INTERVAL - (int(time.time()) - last))
      await asyncio.sleep(wait)
      if get_setting("auto_backup", "on") == "on":
        await _send_backup_to_owner("Auto")
    except Exception as ex:
      logger.warning("auto backup loop error: %s", ex)
      await asyncio.sleep(120)


async def _daily_report_loop():
  while True:
    try:
      now = datetime.utcnow() + IST_OFFSET
      target = now.replace(hour=23, minute=55, second=0, microsecond=0)
      if target <= now:
        target += timedelta(days=1)
      await asyncio.sleep(max(30, (target - now).total_seconds()))
      if get_setting("daily_report", "on") == "on":
        await bot.send_message(ADMIN_ID, custom_emoji_text(_stats_text("today", title="DAILY REPORT")))
      await asyncio.sleep(90)
    except Exception as ex:
      logger.warning("daily report loop error: %s", ex)
      await asyncio.sleep(120)


async def _automation_menu(event):
  ab = get_setting("auto_backup", "on") == "on"
  dr = get_setting("daily_report", "on") == "on"
  try:
    last = int(float(get_setting("last_auto_backup_ts", "0") or 0))
  except Exception:
    last = 0
  last_txt = (datetime.utcfromtimestamp(last) + IST_OFFSET).strftime("%d %b %Y, %H:%M IST") if last else "never"
  msg = f"{P_PC} <b>Automation</b>\n━━━━━━━━━━━━━━━━\n"
  if not IS_CLONE:
    msg += (f"{P_FOLDER} <b>Auto Backup:</b> <b>{'ON' if ab else 'OFF'}</b> (every 2 hours, sent only to your chat)\n"
            f"{P_DOC} <b>Cloned Bots DB Backup:</b> <b>{'ON' if ab else 'OFF'}</b> (same 2-hour run, separate zip)\n"
            f"{P_TIME} Last backup: <b>{last_txt}</b>\n\n")
  msg += f"{P_STATS} <b>Daily Report:</b> <b>{'ON' if dr else 'OFF'}</b> (every night 11:55 PM IST, sent only to you)"
  btns = []
  if not IS_CLONE:
    btns.append([Button.inline(f"Auto Backup: {'ON' if ab else 'OFF'}", "adm_autobackup_tgl",
                               style=("success" if ab else "danger"))])
    btns.append([Button.inline("Send Backup Now", "adm_backupnow", style="primary")])
  btns.append([Button.inline(f"Daily Report: {'ON' if dr else 'OFF'}", "adm_dailyreport_tgl",
                             style=("success" if dr else "danger"))])
  btns.append([Button.inline("Back to Admin", "adm_adminmain")])
  await event.edit(custom_emoji_text(msg), buttons=btns)

# ================= CLONE BOT ENGINE =================
_CLONE_PROCS = {}


def _clone_pid_alive(pid):
  if os.name == 'nt':
    return False
  try:
    pid = int(pid)
    os.kill(pid, 0)
  except ProcessLookupError:
    return False
  except PermissionError:
    return True
  except Exception:
    return False
  try:
    with open("/proc/%d/stat" % pid, "r") as f:
      if f.read().rsplit(")", 1)[1].split()[0] == "Z":
        return False
  except Exception:
    pass
  try:
    with open("/proc/%d/cmdline" % pid, "rb") as f:
      if os.path.basename(os.path.abspath(__file__)).encode() not in f.read():
        return False
  except Exception:
    pass
  return True


def _clone_is_running(cdir):
  proc = _CLONE_PROCS.get(cdir)
  if proc is not None:
    if proc.poll() is None:
      return True
    _CLONE_PROCS.pop(cdir, None)
  try:
    with open(os.path.join(cdir, "clone.pid"), "r") as f:
      return _clone_pid_alive(f.read().strip())
  except Exception:
    return False


def _clone_spawn(cdir):
  """Start the clone as its own process (own folder = own database/sessions)."""
  env = dict(os.environ)
  env["PYTHONUNBUFFERED"] = "1"
  kwargs = {}
  if os.name == 'nt':
    kwargs["creationflags"] = 0x00000008 | 0x00000200
  else:
    kwargs["start_new_session"] = True
  with open(os.path.join(cdir, "clone.log"), "ab") as logf:
    proc = subprocess.Popen(
      [sys.executable, "-u", os.path.abspath(__file__)], cwd=cdir,
      stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env, **kwargs)
  with open(os.path.join(cdir, "clone.pid"), "w") as f:
    f.write(str(proc.pid))
  _CLONE_PROCS[cdir] = proc
  return proc


def _clone_read_log(path, offset):
  try:
    with open(path, "rb") as f:
      f.seek(offset)
      return f.read().decode("utf-8", "ignore")
  except Exception:
    return ""


def _clone_check_token(token):
  """Ask Telegram if the token is real. Returns (ok, username_or_error)."""
  try:
    req = urllib.request.Request("https://api.telegram.org/bot%s/getMe" % token,
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20, context=ssl.create_default_context()) as r:
      data = json.loads(r.read().decode("utf-8", "ignore"))
    if data.get("ok"):
      return True, (data.get("result") or {}).get("username") or ""
    return False, "Telegram rejected this bot token."
  except urllib.error.HTTPError as ex:
    if ex.code in (401, 404):
      return False, "Invalid bot token."
    return False, "Token check failed (HTTP %s)." % ex.code
  except Exception as ex:
    return False, "Could not verify the token (%s)." % type(ex).__name__


async def _clone_create(token, owner_id, api_id, api_hash, gmail, app_pw, store_name=""):
  """Create the clone folder + config, start it, and wait until it is online."""
  ok, uname = await asyncio.to_thread(_clone_check_token, token)
  if not ok:
    return False, html.escape(uname)
  bot_id = token.split(":")[0]
  if bot_id == str(BOT_TOKEN).split(":")[0]:
    return False, "This is the main bot's own token. Create a NEW bot in @BotFather for the clone."
  cdir = os.path.join(CLONES_ROOT, bot_id)
  if _clone_is_running(cdir):
    return False, "This bot is already cloned and running."
  os.makedirs(os.path.join(cdir, "sessions"), exist_ok=True)
  cfg_path = os.path.join(cdir, CLONE_CONFIG_FILE)
  with open(cfg_path, "w", encoding="utf-8") as f:
    json.dump({"bot_token": token, "owner_id": int(owner_id), "api_id": int(api_id), "api_hash": api_hash,
               "gmail": gmail, "gmail_app_password": app_pw, "username": uname, "store_name": store_name,
               "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}, f)
  try: os.chmod(cfg_path, 0o600)
  except Exception: pass
  log_path = os.path.join(cdir, "clone.log")
  start_off = os.path.getsize(log_path) if os.path.exists(log_path) else 0
  try:
    proc = await asyncio.to_thread(_clone_spawn, cdir)
  except Exception as ex:
    try: os.remove(cfg_path)
    except Exception: pass
    return False, "Could not start the clone process: %s" % html.escape(type(ex).__name__)
  state = None
  chunk = ""
  for _ in range(45):
    await asyncio.sleep(1)
    chunk = _clone_read_log(log_path, start_off)
    if "BOT STARTED SUCCESSFULLY" in chunk:
      state = True
      break
    if "Start attempt" in chunk or "BOT_TOKEN is invalid" in chunk or proc.poll() is not None:
      state = False
      break
  if state is False:
    try: proc.terminate()
    except Exception: pass
    for _p in (cfg_path, os.path.join(cdir, "clone.pid")):
      try: os.remove(_p)
      except Exception: pass
    tail = "\n".join([ln for ln in chunk.strip().splitlines() if ln.strip()][-6:])
    for secret in (token, token.split(":", 1)[-1], api_hash, app_pw):
      if secret:
        tail = tail.replace(secret, "***")
    return False, ("<b>Clone failed to start.</b> Check the API ID / API Hash and try again.\n\n<code>%s</code>"
                   % html.escape(tail[-700:] or "No log output."))
  note = "" if state else "\n\n<i>Still connecting... it should be online within a minute.</i>"
  link = ("https://t.me/" + uname) if uname else ""
  return True, ("<b>Clone bot is live!</b>\n\nStore: <b>%s</b>\nBot: %s\nOwner ID: <code>%s</code>\n\n"
                "It runs as a separate bot with its own database and sessions. Ask the owner to send /start to it.%s"
                % (html.escape(store_name or "-"), html.escape(link or bot_id), int(owner_id), note))


def _autostart_clones():
  """On main-bot start, bring every saved clone back online (skips running ones)."""
  if IS_CLONE or not os.path.isdir(CLONES_ROOT):
    return
  for name in sorted(os.listdir(CLONES_ROOT)):
    cdir = os.path.join(CLONES_ROOT, name)
    if (not os.path.isfile(os.path.join(cdir, CLONE_CONFIG_FILE)) or _clone_is_running(cdir)
        or os.path.exists(os.path.join(cdir, "clone.stopped"))):
      continue
    try:
      _clone_spawn(cdir)
      logger.info("Clone bot %s started", name)
    except Exception as ex:
      logger.warning("Clone bot %s could not start: %s", name, ex)


def _restart_bot():
  os.execv(sys.executable, [sys.executable] + sys.argv)

def delete_session_files(session_path):
  base = session_path if not session_path.endswith('.session') else session_path[:-8]
  for ext in ['.session', '.session-wal', '.session-shm', '.session-journal']:
    try:
      if os.path.exists(base + ext): os.remove(base + ext)
    except: pass

async def _get_channel_entity(channel_id):
  """Resolve a configured channel ID safely for both public/private channels."""
  raw = str(channel_id or '').strip()
  if not raw:
    raise ValueError("Channel ID is empty")
  try:
    target = int(raw)
  except ValueError:
    target = raw
  return await bot.get_input_entity(target)

async def _is_bot_channel_admin(channel_id):
  """Return (ok, reason) after checking that THIS bot is admin/creator in the channel."""
  try:
    channel = await _get_channel_entity(channel_id)
    me = await bot.get_me()
    result = await bot(GetParticipantRequest(channel=channel, participant=me.id))
    participant = getattr(result, 'participant', result)
    if isinstance(participant, ChannelParticipantCreator):
      return True, ""
    if isinstance(participant, ChannelParticipantAdmin):
      rights = getattr(participant, 'admin_rights', None)
      # Telegram exposes invite_users for the permission needed to create an invite link.
      if rights is not None and getattr(rights, 'invite_users', None) is False:
        return False, 'The bot is an admin, but "Invite Users via Link" permission is disabled.'
      return True, ""
    return False, "The bot is in the channel, but it is not an admin."
  except UserNotParticipantError:
    return False, "The bot is not a member/admin of this channel."
  except ChatAdminRequiredError:
    return False, "Telegram did not allow the bot to inspect this channel. Make the bot an admin first."
  except Exception as ex:
    logger.error(f"Force channel admin check failed for {channel_id}: {ex}")
    return False, f"Could not verify this channel: {ex}"

async def _validate_force_invite_url(raw_url):
  """Accept only a real Telegram URL suitable for a Join button."""
  normalized = _normalize_tg_url(raw_url, "")
  if not normalized:
    return ""
  # Force-join links may be public channel URLs or private +invite links.
  if not re.match(r"^https?://(?:t\.me|telegram\.me)/(?:\+[^\s<>]+|[A-Za-z0-9_][^\s<>]*)$", normalized, re.IGNORECASE):
    return ""
  return normalized

async def _create_force_channel_invite(channel_id):
  """Create a Telegram invite link automatically for a verified channel."""
  try:
    channel = await _get_channel_entity(channel_id)
    result = await bot(ExportChatInviteRequest(peer=channel))
    link = getattr(result, 'link', '') or ''
    link = await _validate_force_invite_url(link)
    if not link:
      return False, '', 'Telegram returned an invalid invite link.'
    return True, link, ''
  except ChatAdminRequiredError:
    return False, '', 'Bot is admin, but Telegram has not granted it permission to create invite links. Enable the channel permission "Invite Users via Link".'
  except Exception as ex:
    logger.error(f"Force channel invite creation failed for {channel_id}: {ex}", exc_info=True)
    return False, '', f'Could not create invite link: {ex}'

_JOIN_OK_UNTIL = {}      # uid -> time until which "joined everywhere" is trusted


async def check_channel_joined(uid):
  if is_admin(uid): return True
  rows = cur.execute("SELECT channel_id FROM force_channels").fetchall()
  if not rows: return True
  if _JOIN_OK_UNTIL.get(uid, 0) > time.time():
    return True

  async def _one(ch):
    ch_key = str(ch).strip()
    # Pending join request (request-approval invite links) counts as joined.
    pending = cur.execute(
      "SELECT 1 FROM force_join_requests WHERE channel_id=? AND user_id=?",
      (ch_key, int(uid))).fetchone()
    try:
      channel = await _get_channel_entity(ch)
      try: user = await bot.get_input_entity(uid)
      except Exception: user = await bot.get_entity(uid)
      await bot(GetParticipantRequest(channel=channel, participant=user))
      # Real member now -> the stored request is no longer needed.
      if pending:
        cur.execute("DELETE FROM force_join_requests WHERE channel_id=? AND user_id=?", (ch_key, int(uid)))
        db.commit()
      return True
    except (UserNotParticipantError, ValueError):
      return bool(pending)
    except Exception as e:
      logger.error(f"Channel Check Error: {e}")
      return bool(pending)

  results = await asyncio.gather(*[_one(ch) for (ch,) in rows])
  ok = all(results)
  if ok:
    _JOIN_OK_UNTIL[uid] = time.time() + 120
  return ok

@bot.on(events.Raw)
async def _force_join_request_tracker(update):
  """Remember users who sent a join request to a force-join channel so the
  force-join check accepts them (joined members are checked via GetParticipant)."""
  try:
    from telethon.tl.types import UpdateBotChatInviteRequester
    if not isinstance(update, UpdateBotChatInviteRequester):
      return
    from telethon import utils as _tl_utils
    ch_key = str(_tl_utils.get_peer_id(update.peer))
    known = cur.execute("SELECT 1 FROM force_channels WHERE channel_id=?", (ch_key,)).fetchone()
    if not known:
      return
    cur.execute("INSERT OR IGNORE INTO force_join_requests (channel_id, user_id) VALUES (?,?)",
                (ch_key, int(update.user_id)))
    db.commit()
  except Exception as ex:
    logger.error(f"Join request tracker error: {ex}")

COUNTRY_CODES = {
  '1': 'USA/Canada', '7': 'Russia', '20': 'Egypt', '27': 'South Africa',
  '31': 'Netherlands', '32': 'Belgium', '33': 'France', '34': 'Spain',
  '39': 'Italy', '44': 'UK', '46': 'Sweden', '48': 'Poland',
  '49': 'Germany', '51': 'Peru', '52': 'Mexico', '54': 'Argentina',
  '55': 'Brazil', '56': 'Chile', '57': 'Colombia', '58': 'Venezuela',
  '60': 'Malaysia', '61': 'Australia', '62': 'Indonesia', '63': 'Philippines', 
  '66': 'Thailand', '84': 'Vietnam', '86': 'China', '90': 'Turkey',
  '91': 'India', '92': 'Pakistan', '93': 'Afghanistan', '94': 'Sri Lanka',
  '95': 'Myanmar', '98': 'Iran', '212': 'Morocco', '213': 'Algeria',
  '234': 'Nigeria', '254': 'Kenya', '255': 'Tanzania', '380': 'Ukraine',
  '880': 'Bangladesh', '964': 'Iraq', '966': 'Saudi Arabia', '971': 'UAE',
  '998': 'Uzbekistan'
}

def get_country_info(phone):
  phone = str(phone).replace(' ', '').replace('+', '')
  if not phone: return "Unknown"
  
  try:
    customs = cur.execute("SELECT code, name FROM custom_countries").fetchall()
    customs.sort(key=lambda x: len(x[0]), reverse=True)
    for code, name in customs:
      if phone.startswith(code): return name
  except: pass

  for length in (3, 2, 1):
    prefix = phone[:length]
    if prefix in COUNTRY_CODES: return COUNTRY_CODES[prefix]
  return "Unknown"

async def detect_account_year(client):
  year = 2024
  try:
    try: await client.delete_dialog('TGDNAbot')
    except: pass
    await client.send_message('TGDNAbot', '/start')
    me = await client.get_me()
    await asyncio.sleep(1)
    await client.send_message('TGDNAbot', str(me.id)) 
    for _ in range(8):
      await asyncio.sleep(1.5)
      msgs = await client.get_messages('TGDNAbot', limit=3)
      for m in msgs:
        if m.text and ('Created:' in m.text or 'Age:' in m.text or 'Registration' in m.text):
          match = re.search(r'(?:Created|Age|Registration)[^\d]*(\d{4})', m.text, re.IGNORECASE)
          if match: return int(match.group(1))
  except Exception: pass
  return year

def _mask_phone(value):
  """Fully hide phone number(s) in public channel logs."""
  parts = [p.strip() for p in str(value or '').split(',') if p.strip()]
  out = []
  for p in (parts or ['']):
    n = len(re.sub(r'\D', '', p))
    out.append('+' + '\u2022' * max(n, 9))
  return '<b>' + html.escape(', '.join(out)) + '</b>'


def _spoiler(value):
  """Hide sensitive values in Telegram logs using Telegram spoiler formatting."""
  return f"<tg-spoiler>{html.escape(str(value))}</tg-spoiler>"

async def _get_bot_buy_button():
  try:
    bot_info = await bot.get_me()
    username = getattr(bot_info, 'username', None)
    if username:
      return [[Button.url("Buy Now", f"https://t.me/{username}")]]
  except Exception as ex:
    logger.error(f"Failed to build Buy Now button: {ex}")
  return None

def _strip_all_emoji(text):
  """Logs channel text: remove every emoji (custom <tg-emoji> and plain) and tidy spaces."""
  text = str(text or "")
  text = re.sub(r'<tg-emoji\b[^>]*>.*?</tg-emoji>', '', text, flags=re.DOTALL | re.IGNORECASE)
  text = re.sub(r'<emoji\s+id=["\'][^"\']+["\']>.*?</emoji>', '', text, flags=re.DOTALL | re.IGNORECASE)
  text = re.sub('[\U0001F000-\U0001FAFF\u2300-\u23FF\u2600-\u27BF\u2B00-\u2BFF\u20E3\uFE0F\u200D]', '', text)
  lines = [re.sub(r'[ \t]{2,}', ' ', ln).strip() for ln in text.split("\n")]
  return "\n".join(lines).strip()


async def _send_selling_log(msg):
  """Post a sale/deposit log to the logs channel (plain text, no emoji)."""
  body = _strip_all_emoji(msg)
  buttons = await _get_bot_buy_button()
  for attempt_buttons in (buttons, None):
    try:
      await bot.send_message(get_log_channel_id(), body, buttons=attempt_buttons, parse_mode='html')
      return True
    except Exception as ex:
      logger.error(f"Selling log send failed (buttons={'yes' if attempt_buttons else 'no'}): {ex}")
      if attempt_buttons is None:
        break
  return False

async def _user_label(uid):
  """@username (or name) for admin messages."""
  try:
    user = await bot.get_entity(int(uid))
    if getattr(user, 'username', None):
      return '@' + user.username
    return getattr(user, 'first_name', None) or 'NoUsername'
  except Exception:
    return 'NoUsername'


async def notify_admins(msg):
  """DM the owner + every sub-admin (full, un-hidden details)."""
  for admin_id in get_all_admin_ids():
    try:
      await bot.send_message(int(admin_id), custom_emoji_text(emoji_to_custom(msg)), parse_mode='html')
    except Exception as ex:
      logger.error(f"Admin notify failed for {admin_id}: {ex}")


async def log_primary_deposit(uid, amt, method):
  """Successful deposit log only. User id, username and any link/number stay hidden."""
  try:
    username = await _user_label(uid)
    t = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = (
      f"{P_YES} {P_FIRE} <b>NEW DEPOSIT SUCCESSFUL</b> {P_PARTY}\n\n"
      f"{P_ACC} User: <b>Hidden</b>\n"
      f"{P_MONEY} Amount: {P_INR}{amt}\n"
      f"{P_CARD} Method: <b>{html.escape(str(method))}</b>\n"
      f"{P_TIME} Time: {t}\n\n"
      f"<i>{P_STAR} Deposit confirmed successfully. {P_STAR}</i>"
    )
    await _send_selling_log(msg)
  except Exception as ex:
    logger.error(f"Global Dep Log Err: {ex}", exc_info=True)

async def log_primary_deposit_success(uid, amt, method, utr=None):
  # Channel: no UTR. Admins: full details (UTR included) for every auto-verified deposit.
  await log_primary_deposit(uid, amt, method)
  try:
    row = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
    bal = row[0] if row else 0
    await notify_admins(
      f"{P_YES} {P_MONEY} <b>AUTO DEPOSIT VERIFIED</b> {P_PARTY}\n\n"
      f"{P_ACC} User: <code>{uid}</code> ({html.escape(await _user_label(uid))})\n"
      f"{P_MONEY} Amount: {P_INR}{amt:g}\n"
      f"{P_CARD} Method: <b>{html.escape(str(method))}</b>\n"
      f"{P_ID} UTR: <code>{html.escape(str(utr or '-'))}</code>\n"
      f"{P_CARD} New Balance: {P_INR}{float(bal or 0):g}\n"
      f"{P_TIME} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
  except Exception as ex:
    logger.error(f"Deposit admin notify err: {ex}")

async def log_primary_purchase(uid, country, price, amount, year, qty, phone=None, global_order_id=None):
  try:
    t = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = (
      f"{P_CART} {P_ROCKET} <b>NEW TELEGRAM ACCOUNT SALE</b> {P_PARTY}\n\n"
      f"{P_ACC} Buyer: <b>Hidden</b>\n"
      f"{country_flag_html(None, country)} Country: {html.escape(str(country))}\n"
      f"{P_MONEY} Price: {P_INR}{price}\n"
      f"{P_CARD} Total Paid: {P_INR}{amount}\n"
      f"{P_CAL} Year: {year}\n"
      f"{P_PKG} Quantity: {qty}\n"
      + (f"{P_ID} Bot Order ID: <code>{html.escape(str(global_order_id))}</code>\n" if global_order_id else "") +
      f"{P_PHONE} Number: {_mask_phone(phone)}\n"
      f"{P_TIME} Time: {t}"
    )
    await _send_selling_log(msg)
  except Exception as ex:
    logger.error(f"Purchase Log Err: {ex}", exc_info=True)
  try:
    await notify_admins(
      f"{P_CART} {P_ROCKET} <b>TELEGRAM ACCOUNT PURCHASED</b> {P_PARTY}\n\n"
      f"{P_ACC} User: <code>{uid}</code> ({html.escape(await _user_label(uid))})\n"
      f"{country_flag_html(None, country)} Country: {html.escape(str(country))} ({year})\n"
      f"{P_PHONE} Number: <code>{html.escape(str(phone or '-'))}</code>\n"
      f"{P_PKG} Qty: {qty}\n"
      + (f"{P_ID} Bot Order ID: <code>{html.escape(str(global_order_id))}</code>\n" if global_order_id else "") +
      f"{P_MONEY} Paid: {P_INR}{amount}\n"
      f"{P_TIME} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
  except Exception as ex:
    logger.error(f"Purchase admin notify err: {ex}")

async def log_smm_sale(uid, service_name, bot_order_id, panel_order_id, link, quantity, total_price, global_order_id=None):
  link = clean_html_url(link)
  try:
    t = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # Channel log: the order LINK is never posted.
    msg = (
      f"{P_CART} {P_ROCKET} <b>NEW SMM ORDER SALE</b> {P_PARTY}\n\n"
      f"{P_ACC} Buyer: <b>Hidden</b>\n"
      f"{P_GEAR} Service: {html.escape(str(service_name))}\n"
      + (f"{P_ID} Bot Order ID: <code>{html.escape(str(global_order_id))}</code>\n" if global_order_id else "") +
      f"{P_PKG} Quantity: {quantity}\n"
      f"{P_MONEY} Total Paid: ₹{float(total_price):.4f}\n"
      f"{P_TIME} Time: {t}"
    )
    await _send_selling_log(msg)
  except Exception as ex:
    logger.error(f"SMM Sale Log Err: {ex}", exc_info=True)
  try:
    await notify_admins(
      f"{P_CART} {P_ROCKET} <b>SMM ORDER PLACED</b> {P_PARTY}\n\n"
      f"{P_ACC} User: <code>{uid}</code> ({html.escape(await _user_label(uid))})\n"
      f"{P_GEAR} Service: {html.escape(str(service_name))}\n"
      f"{P_ID} Bot Order ID: <code>{html.escape(str(global_order_id or '-'))}</code>\n"
      f"{P_ID} SMM Order No.: <code>{bot_order_id}</code>\n"
      f"{P_GEAR} Panel Order ID: <code>{html.escape(str(panel_order_id))}</code>\n"
      f"{P_LINK} Link: {html.escape(link)}\n"
      f"{P_PKG} Quantity: {quantity}\n"
      f"{P_MONEY} Paid: ₹{float(total_price):.4f}\n"
      f"{P_TIME} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
  except Exception as ex:
    logger.error(f"SMM admin notify err: {ex}")

async def log_digital_sale(uid, product_name, price, global_order_id=None):
  try:
    t = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = (
      f"{P_STORE} {P_ROCKET} <b>NEW DIGITAL PRODUCT SALE</b> {P_PARTY}\n\n"
      f"{P_ACC} Buyer: <b>Hidden</b>\n"
      f"{P_DOC} Product: {html.escape(str(product_name))}\n"
      + (f"{P_ID} Bot Order ID: <code>{html.escape(str(global_order_id))}</code>\n" if global_order_id else "") +
      f"{P_MONEY} Total Paid: ₹{price}\n"
      f"{P_TIME} Time: {t}"
    )
    await _send_selling_log(msg)
  except Exception as ex:
    logger.error(f"Digital Sale Log Err: {ex}", exc_info=True)
  try:
    await notify_admins(
      f"{P_STORE} {P_ROCKET} <b>DIGITAL PRODUCT PURCHASED</b> {P_PARTY}\n\n"
      f"{P_ACC} User: <code>{uid}</code> ({html.escape(await _user_label(uid))})\n"
      f"{P_DOC} Product: {html.escape(str(product_name))}\n"
      + (f"{P_ID} Bot Order ID: <code>{html.escape(str(global_order_id))}</code>\n" if global_order_id else "") +
      f"{P_MONEY} Paid: ₹{price}\n"
      f"{P_TIME} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
  except Exception as ex:
    logger.error(f"Digital admin notify err: {ex}")

async def log_wa_sale(uid, country, price, phone, act_id, order_id, global_order_id=None):
  _spawn_bg(_check_api_balance_now(2))
  try:
    t = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cflag = country_flag_html(None, country.get("name"))
    msg = (
      f"{P_WA} {P_ROCKET} <b>NEW WHATSAPP ACCOUNT SALE</b> {P_PARTY}\n\n"
      f"{P_ACC} Buyer: <b>Hidden</b>\n"
      f"{cflag} Country: {html.escape(str(country.get('name')))}\n"
      f"{P_PHONE} Number: {_mask_phone(phone)}\n"
      + (f"{P_ID} Bot Order ID: <code>{html.escape(str(global_order_id))}</code>\n" if global_order_id else "") +
      f"{P_MONEY} Price: {P_INR}{price:.2f}\n"
      f"{P_TIME} Time: {t}"
    )
    await _send_selling_log(msg)
  except Exception as ex:
    logger.error(f"WA Sale Log Err: {ex}", exc_info=True)
  try:
    await notify_admins(
      f"{P_WA} {P_ROCKET} <b>WHATSAPP ACCOUNT PURCHASED</b> {P_PARTY}\n\n"
      f"{P_ACC} User: <code>{uid}</code> ({html.escape(await _user_label(uid))})\n"
      f"{country_flag_html(None, country.get('name'))} Country: {html.escape(str(country.get('name')))}\n"
      f"{P_PHONE} Number: <code>{html.escape(str(phone))}</code>\n"
      f"{P_MONEY} Paid: {P_INR}{price:.2f}\n"
      f"{P_ID} Bot Order ID: <code>{html.escape(str(global_order_id or '-'))}</code>\n"
      f"{P_ID} Activation: <code>{html.escape(str(act_id))}</code> | Order #{order_id}\n"
      f"{P_TIME} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
  except Exception as ex:
    logger.error(f"WA admin notify err: {ex}")

async def log_s3_sale(uid, app_name, app_code, country, phone, price, act_id, order_id, global_order_id=None):
  """Server 3 (All App OTP) purchase -> logs channel (buyer hidden) + admin DM."""
  _spawn_bg(_check_api_balance_now(3))
  try:
    t = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cname = country.get("name") if isinstance(country, dict) else str(country)
    logo = _s3_logo_html(app_code, app_name) or f"{P_APPS} "
    msg = (
      f"{logo}{P_ROCKET} <b>NEW SERVER 3 OTP SALE</b> {P_PARTY}\n\n"
      f"{P_ACC} Buyer: <b>Hidden</b>\n"
      f"{P_GLOBE} App: <b>{html.escape(str(app_name))}</b>\n"
      f"{country_flag_html(None, cname)} Country: {html.escape(str(cname))}\n"
      f"{P_PHONE} Number: {_mask_phone(phone)}\n"
      + (f"{P_ID} Bot Order ID: <code>{html.escape(str(global_order_id))}</code>\n" if global_order_id else "") +
      f"{P_MONEY} Price: {P_INR}{price:.2f}\n"
      f"{P_TIME} Time: {t}"
    )
    await _send_selling_log(msg)
  except Exception as ex:
    logger.error(f"Server3 Sale Log Err: {ex}", exc_info=True)

# ================= PERSISTENT MENU =================
def _selling_logs_rows():
  """Selling Logs button row (hidden in a clone until its own link exists)."""
  link = get_selling_logs_link()
  return [[Button.url("Selling Logs", link)]] if link else []

def get_persistent_menu(uid):
  # Support/Updates are direct URL buttons so they never depend on a callback
  # handler. Their destinations are controlled from the Admin Panel settings.
  support_url = get_support_url()
  updates_url = get_support_channel_url() if IS_CLONE else "https://t.me/+yhaYNpSyF5U3Y2Q9"
  # Support/Updates remain direct redirects when Admin has configured a valid
  # Telegram URL. If a URL has not been configured yet, use the callback
  # fallback instead of constructing an invalid Button.url (which crashes
  # the entire /start media send with ButtonUrlInvalidError).
  support_btn = (
    Button.url("Support", support_url)
    if _has_valid_button_url(support_url)
    else Button.inline("Support", data="cb_support")
  )
  updates_btn = (
    Button.url("Updates", updates_url)
    if _has_valid_button_url(updates_url)
    else Button.inline("Updates", data="cb_updates")
  )
  rows = [
    [
      Button.inline("Store", data="cb_store"),
      Button.inline("Add Funds", data="cb_addfunds")
    ],
    [
      Button.inline("Profile", data="cb_profile"),
      Button.inline("My Orders", data="cb_orders")
    ],
    [Button.inline("Refer and Earn", data="cb_refer"), Button.inline("Redeem Code", data="redeem_start")],
    *_selling_logs_rows(),
    [support_btn],
    [updates_btn]
  ]
  return rows

# ================= WELCOME MEDIA (photo OR video) =================
WELCOME_PHOTO_FILE = "23593.jpg"
WELCOME_VIDEO_FILE = "23593.mp4"
WELCOME_MAX_BYTES = 50 * 1024 * 1024   # Telegram bot upload limit
_welcome_media_cache = {}              # reuse Telegram's stored copy -> video uploads only once

def get_welcome_media():
  """Return (path, is_video) of the current welcome media (newest file wins), or (None, False)."""
  found = []
  for path, is_video in ((WELCOME_PHOTO_FILE, False), (WELCOME_VIDEO_FILE, True)):
    try:
      if os.path.isfile(path) and os.path.getsize(path) > 0:
        found.append((os.path.getmtime(path), path, is_video))
    except OSError:
      pass
  if not found:
    return None, False
  found.sort(reverse=True)
  return found[0][1], found[0][2]

async def send_welcome_photo(chat, caption, buttons=None):
  """Send only the configured welcome PHOTO on the /start main menu."""
  if not os.path.isfile(WELCOME_PHOTO_FILE) or os.path.getsize(WELCOME_PHOTO_FILE) <= 0:
    raise FileNotFoundError("no welcome photo")
  st = os.stat(WELCOME_PHOTO_FILE)
  sig = (WELCOME_PHOTO_FILE, st.st_mtime_ns, st.st_size)
  kw = dict(caption=caption, buttons=buttons, parse_mode='html')
  if _welcome_media_cache.get('sig') == sig and _welcome_media_cache.get('media') is not None:
    try:
      return await bot.send_file(chat, _welcome_media_cache['media'], **kw)
    except Exception as ex:
      logger.warning(f"Cached welcome photo failed, re-uploading: {ex}")
  sent = await bot.send_file(chat, WELCOME_PHOTO_FILE, **kw)
  try:
    _welcome_media_cache.clear()
    _welcome_media_cache.update(sig=sig, media=sent.media)
  except Exception:
    pass
  return sent


async def _prewarm_welcome_media():
  """Upload the welcome photo/video once at startup (to the owner, deleted right away) so
  Telegram's stored copy is reused and the first /start after a restart is instant."""
  try:
    path, is_video = get_welcome_media()
    if not path:
      return
    st = os.stat(path)
    sig = (path, st.st_mtime_ns, st.st_size)
    if _welcome_media_cache.get('sig') == sig and _welcome_media_cache.get('media') is not None:
      return
    sent = await bot.send_file(int(ADMIN_ID), path, caption="\u2022", silent=True,
                               supports_streaming=bool(is_video))
    _welcome_media_cache.clear()
    _welcome_media_cache.update(sig=sig, media=sent.media)
    try:
      await sent.delete()
    except Exception:
      pass
    logger.info("Welcome media pre-loaded")
  except Exception as ex:
    logger.info("Welcome media pre-load skipped: %s", ex)


async def send_welcome_media(chat, caption, buttons=None):
  """Send the welcome photo/video with caption + buttons. Raises if nothing could be sent."""
  path, is_video = get_welcome_media()
  if not path:
    raise FileNotFoundError("no welcome media")
  st = os.stat(path)
  sig = (path, st.st_mtime_ns, st.st_size)
  kw = dict(caption=caption, buttons=buttons, parse_mode='html')
  if is_video:
    kw['supports_streaming'] = True
  if _welcome_media_cache.get('sig') == sig and _welcome_media_cache.get('media') is not None:
    try:
      return await bot.send_file(chat, _welcome_media_cache['media'], **kw)
    except Exception as ex:
      logger.warning(f"Cached welcome media failed, re-uploading: {ex}")
  sent = await bot.send_file(chat, path, **kw)
  try:
    _welcome_media_cache.clear()
    _welcome_media_cache.update(sig=sig, media=sent.media)
  except Exception:
    pass
  return sent

def _is_welcome_media_msg(msg):
  """True when this message is the main-menu welcome photo/video."""
  try:
    if msg is None:
      return False
    media = getattr(msg, 'photo', None) or getattr(msg, 'video', None) or getattr(msg, 'document', None)
    if not media:
      return False
    cached = _welcome_media_cache.get('media')
    if cached is not None:
      cm = getattr(cached, 'photo', None) or getattr(cached, 'document', None)
      if cm is not None and getattr(cm, 'id', None) == getattr(media, 'id', None):
        return True
    # After a restart the cache is empty: recognise the main menu by its text.
    txt = getattr(msg, 'raw_text', None) or getattr(msg, 'message', '') or ''
    return 'Account UID' in txt and 'Wallet Balance' in txt
  except Exception:
    return False


def _patch_callback_edit_drop_welcome_media():
  """If a button is pressed on the main-menu media message, the next screen is a
  fresh text message: the welcome media is deleted and never stays attached."""
  _orig_edit = events.CallbackQuery.Event.edit

  async def edit(self, *args, **kwargs):
    try:
      if kwargs.get('file') is None:
        msg = await self.get_message()
        if _is_welcome_media_msg(msg):
          text = args[0] if args else kwargs.get('text')
          if isinstance(text, str):
            try:
              await self.delete()
            except Exception as ex:
              logger.debug(f"welcome media delete failed: {ex}")
            return await bot.send_message(
              self.chat_id, text, buttons=kwargs.get('buttons'),
              parse_mode=kwargs.get('parse_mode', 'html'),
              link_preview=kwargs.get('link_preview', True))
    except Exception as ex:
      logger.debug(f"welcome media edit patch skipped: {ex}")
    return await _orig_edit(self, *args, **kwargs)

  events.CallbackQuery.Event.edit = edit


_patch_callback_edit_drop_welcome_media()


# ---- Message effect (fire animation on /start) -------------------------------
import contextvars as _cv
_MSG_EFFECT = _cv.ContextVar("msg_effect", default=None)
FIRE_EFFECT_ID = 5104841245755180586          # Telegram's \U0001F525 message effect


def _install_message_effect_patch():
  """Lets us attach a Telegram message effect to ONE outgoing message (the /start menu).
  Needs a Telethon version that knows the `effect` field; otherwise it does nothing."""
  try:
    import inspect
    from telethon.tl.functions.messages import SendMessageRequest, SendMediaRequest
    if not all("effect" in inspect.signature(c.__init__).parameters
               for c in (SendMessageRequest, SendMediaRequest)):
      logger.info("Message effects need a newer Telethon (pip install -U telethon). Fire effect disabled.")
      return
    _orig_call = TelegramClient.__call__

    async def _call_with_effect(self, request, *a, **kw):
      eff = _MSG_EFFECT.get()
      injected = False
      if eff and isinstance(request, (SendMessageRequest, SendMediaRequest)):
        try:
          request.effect = int(eff)
          injected = True
        except Exception:
          pass
        _MSG_EFFECT.set(None)           # only the first message gets the effect
      try:
        return await _orig_call(self, request, *a, **kw)
      except Exception as ex:
        if injected and "EFFECT" in str(ex).upper():
          request.effect = None         # effect rejected -> send normally
          return await _orig_call(self, request, *a, **kw)
        raise

    TelegramClient.__call__ = _call_with_effect
    logger.info("Message effect patch installed (fire effect on /start)")
  except Exception as ex:
    logger.info("Message effect patch skipped: %s", ex)


_install_message_effect_patch()


async def send_main_menu(event, uid):
  ensure_user(uid)
  row = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
  bal = row[0] if row else 0

  try:
    sender = await event.get_sender()
    user_name = html.escape(sender.first_name) if sender and sender.first_name else "User"
  except Exception:
    user_name = "User"

  # Keep the account summary together inside a Telegram quote block, matching
  # the requested UI. Custom-emoji constants remain inside the quoted lines.
  # Premium/custom-emoji styled welcome text. Every visual marker is a
  # Telegram custom emoji ID, including the quoted account summary.
  msg = (
    f"{P_DIAMOND} <b>{BRAND_TITLE}</b> {P_STAR}\n"
    f"{P_TG} <b>Welcome back,</b> {P_ACC} <b>{user_name}</b> {P_LIGHTNING} {P_STAR}\n\n"
    f"<blockquote>"
    f"{P_MONEY} <b>Wallet Balance:</b> {P_INR}{bal:.2f} {P_USDT} (${to_usd(bal):.2f})\n"
    f"{P_ID} <b>Account UID:</b> <code>{uid}</code> {P_YES}\n"
    f"{P_CROWN} <b>Membership:</b> <b>Verified VIP</b> {P_YES}"
    f"</blockquote>\n"
    f"{P_STAR} <i>Your premium destination for fast, reliable, and automated account purchases.</i> {P_FIRE} {P_DIAMOND}"
  )
  if IS_CLONE:
    msg += "\n\n<i>This is a cloned bot</i>"

  buttons = get_persistent_menu(uid)
  rendered = custom_emoji_text(msg)

  if isinstance(event, events.CallbackQuery.Event):
    # Main menu is the ONLY customer-facing screen that carries the configured
    # welcome media. Replace the previous screen instead of editing its caption,
    # otherwise Telegram can leave the old photo/video attached.
    try:
      await event.delete()
    except Exception as ex:
      logger.debug(f"Previous menu message could not be deleted: {ex}")

    try:
      return await send_welcome_media(uid, rendered, buttons)
    except Exception as ex:
      logger.warning(f"Main menu media send failed, using text: {ex}")
      try:
        return await bot.send_message(uid, rendered, buttons=buttons, parse_mode='html')
      except Exception as send_ex:
        logger.error(f"Main menu text send failed: {send_ex}", exc_info=True)
        await safe_callback_answer(
          event, "Could not open the main menu. Please send /start.", alert=True)
  else:
    try:
      return await send_welcome_media(event.chat_id or uid, rendered, buttons)
    except Exception as ex:
      logger.warning(f"Main menu media respond failed, using text: {ex}")
      return await event.respond(rendered, buttons=buttons, parse_mode='html')

async def store_servers_menu(event):
  """Open the Store menu reliably from both text and callback messages.

  The main menu is usually a photo message. Telegram cannot turn that media
  message into a normal text message with buttons reliably on every client,
  so callback navigation explicitly replaces the media message and falls
  back to a fresh message if the first send path fails.
  """
  msg = (
    f"{P_STORE} {P_ROCKET} <b>{BRAND_TITLE}</b> {P_STAR}\n"
    f"────────────────\n\n"
    f"<b>Welcome to our digital marketplace!</b> {P_PARTY}\n\n"
    f"{P_YES} <b>Instant Delivery</b> {P_LIGHTNING}\n"
    f"{P_2FA} <b>Secure & Verified Stock</b> {P_DIAMOND}\n"
    f"{P_WAIT} <b>24×7 Automated Service</b> {P_TIME}\n\n"
    f"{P_TG} <b>Telegram</b>  {P_WA} <b>WhatsApp</b>  {P_IG} <b>Instagram</b>  <b>& More</b>\n\n"
    f"{P_ASST} Please select below to browse our available stock:"
  )
  btns = []
  if _fnm_on("server1"):
    btns.append([Button.inline("Server 1 [ Cheap TG Accounts ]", "srv1_accounts", icon=LOGO_TG_ID)])
  if _fnm_on("server2wa"):
    btns.append([Button.inline("Server 2 [ WhatsApp Accounts ]", "s2wa_countries", icon=LOGO_WA_ID)])
  if _fnm_on("server3otp"):
    btns.append([Button.inline("Server 3 [ ALL APP OTP ]", "s3_home")])
  if _fnm_on("srv3manual"):
    btns.append([Button.inline("Server 4 [ manually added accounts ]", "srv|manual")])
  if _fnm_on("shop"):
    btns.append([Button.inline("Shop", "digital_shop")])
  if _fnm_on("smm"):
    btns.append([Button.inline("Social Media Services", "cb_smm_services")])
  btns.append([Button.inline("Back to Main", "back_main")])
  rendered = custom_emoji_text(msg)

  if not isinstance(event, events.CallbackQuery.Event):
    return await event.respond(rendered, buttons=btns, parse_mode='html')

  try:
    if getattr(getattr(event, '_message', None), 'media', None):
      try:
        await event.delete()
      except Exception as ex:
        logger.warning(f"Store media delete failed: {ex}")
      try:
        return await event.respond(rendered, buttons=btns, parse_mode='html')
      except Exception as ex:
        logger.warning(f"Store event.respond failed: {ex}")
        return await bot.send_message(event.chat_id, rendered, buttons=btns, parse_mode='html')

    try:
      return await event.edit(rendered, buttons=btns, parse_mode='html')
    except MessageNotModifiedError:
      return
    except Exception as ex:
      logger.warning(f"Store event.edit failed: {ex}")
      return await event.respond(rendered, buttons=btns, parse_mode='html')
  except Exception as ex:
    logger.error(f"Store menu error: {ex}", exc_info=True)
    try:
      return await bot.send_message(event.chat_id, rendered, buttons=btns, parse_mode='html')
    except Exception as send_ex:
      logger.error(f"Store fallback send failed: {send_ex}", exc_info=True)
      await safe_callback_answer(event, "Store could not be opened. Please try /start again.", alert=True)


# ================= SERVER 1 STORE (NOBELOTS RESELLER API) =================
# UI + flow mirrors the "Aaditya Tg Store" mini-app shown in the reference video:
# Terms gate -> WALLET card -> country list (page/sort/search/filters) ->
# country detail (stock/from/page/Bulk Buy) -> ACCOUNT DETAILS -> Filters panel.
S1_PAGE_SIZE = 8
S1_FILTERS = {}
S1_SEARCH_STATE = {}
S1_FILTER_DEFAULTS = {
  "spam": "any", "premium": "any", "origin": "any",
  "email": "any", "search": "", "sort": "low", "cat": "",
}

# ---- Server 1 categories (Pushing / Premium / Autoreg) ----------------------
# push    = normal accounts (non-premium, non-autoreg)
# premium = Telegram Premium accounts only
# autoreg = auto-registered accounts (matched on the API "origin" text)
# If your API uses a different word for autoreg, add it to S1_AUTOREG_KEYWORDS.
S1_CATEGORIES = {
  "push":    {"label": "Pushing Account"},
  "premium": {"label": "Premium Account"},
  "autoreg": {"label": "Autoreg Account"},
}
S1_AUTOREG_KEYWORDS = ("autoreg", "auto reg", "auto-reg", "auto_reg")


def _s1_is_autoreg(it):
  blob = f"{it.get('origin','')} {it.get('resale_origin','')}".lower()
  return any(k in blob for k in S1_AUTOREG_KEYWORDS)


def _s1_cat_label(cat):
  return (S1_CATEGORIES.get(cat) or {}).get("label", "")


def _s1_set_category(f, cat):
  """Apply a category to a filter dict (premium category -> API premium filter)."""
  f["cat"] = cat if cat in S1_CATEGORIES else ""
  f["premium"] = "only" if cat == "premium" else "any"
  return f


def _s1_country_label(item, server_no=1):
  price = server_sell_price(item.get("price"), server_no)
  name = clean_country_name(item.get("name") or item.get("code"))
  label = f"{name} — ₹{price}"
  if len(label) > 48:
    label = label[:45] + "..."
  return label


def _s1_status_text(status):
  return {
    "queued": "Queued",
    "running": "Buying",
    "processing": "Processing",
    "completed": "Completed",
    "partial": "Partially Completed",
    "failed": "Failed",
    "cancelled": "Cancelled",
    "interrupted": "Interrupted",
    "waiting": "Waiting for Code",
  }.get(str(status or "").lower(), str(status or "Waiting").title())


# ---- Refer and Earn ----------------------------------------------------------
_BOT_USERNAME_CACHE = ""


async def _bot_username():
  global _BOT_USERNAME_CACHE
  if not _BOT_USERNAME_CACHE:
    me = await bot.get_me()
    _BOT_USERNAME_CACHE = getattr(me, "username", "") or ""
  return _BOT_USERNAME_CACHE


async def _notify_new_referral(ref_id):
  try:
    await bot.send_message(ref_id, custom_emoji_text(
      f"{P_YES} <b>{_bold('New Referral Joined!')}</b>\n\n"
      f"A new user joined using your link. You will earn {get_refer_percent():g}% of every deposit they make."),
      parse_mode='html')
  except Exception:
    pass


async def _refer_reward(uid, amount):
  """Called after every real deposit: the person who referred `uid` gets the admin-set
  % of that deposit in their balance (every deposit, lifetime)."""
  try:
    row = cur.execute("SELECT referrer_id FROM referrals WHERE referred_id=?", (int(uid),)).fetchone()
    if not row:
      return
    pct = get_refer_percent()
    bonus = round(float(amount) * pct / 100.0, 2)
    if pct <= 0 or bonus <= 0:
      return
    ref_id = int(row[0])
    async with get_user_lock(ref_id):
      update_balance(ref_id, bonus)
      cur.execute("INSERT INTO referral_earnings (referrer_id, referred_id, deposit_amount, percent, bonus) "
                  "VALUES (?,?,?,?,?)", (ref_id, int(uid), float(amount), pct, bonus))
      cur.execute("UPDATE referrals SET total_bonus = COALESCE(total_bonus,0) + ? WHERE referred_id=?",
                  (bonus, int(uid)))
      db.commit()
    try:
      await bot.send_message(ref_id, custom_emoji_text(
        f"{P_YES} {P_PARTY} <b>{_bold('Referral Bonus Received!')}</b>\n\n"
        f"{P_MONEY} <b>Bonus:</b> \u20b9{bonus:g}\n"
        f"{P_GIFT} <b>Reason:</b> {pct:g}% of a \u20b9{float(amount):g} deposit by a user you referred"),
        parse_mode='html')
    except Exception as ex:
      logger.info("referral bonus notice failed: %s", ex)
  except Exception as ex:
    logger.warning("referral reward failed: %s", ex, exc_info=True)


async def show_refer_menu(event):
  from urllib.parse import quote as _q
  uid = event.sender_id
  uname = await _bot_username()
  link = f"https://t.me/{uname}?start=ref_{uid}"
  pct = get_refer_percent()
  n = cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (uid,)).fetchone()[0]
  earned = cur.execute("SELECT COALESCE(SUM(bonus),0) FROM referral_earnings WHERE referrer_id=?",
                       (uid,)).fetchone()[0] or 0
  share_text = f"Join {STORE_DISPLAY} and get Telegram accounts, OTP numbers & SMM services at the cheapest price!"
  share_url = "https://t.me/share/url?url=" + _q(link, safe="") + "&text=" + _q(share_text, safe="")
  msg = (
    f"{P_GIFT} <b>{_bold('REFER AND EARN')}</b>\n"
    f"{'─' * 16}\n\n"
    f"Invite your friends and earn <b>{pct:g}%</b> of <b>every deposit</b> they make \u2014 lifetime!\n\n"
    f"{P_ID} <b>{_bold('Your Referral Link')}</b>\n"
    f"<code>{html.escape(link)}</code>\n\n"
    f"{P_USERS} <b>Total Referrals:</b> {n}\n"
    f"{P_MONEY} <b>Total Earned:</b> \u20b9{float(earned):g}\n\n"
    f"<b>{_bold('How it works')}</b>\n"
    f"1. Tap <b>Share Link</b> and send it to friends.\n"
    f"2. They start the bot using your link.\n"
    f"3. Every time they add funds, <b>{pct:g}%</b> goes to your balance instantly."
  )
  btns = [
    [Button.url("Share Link", share_url)],
    [Button.inline("Back", "back_main")],
  ]
  return await e_edit_or_send(event, custom_emoji_text(msg), btns)


# ---- Terms gate --------------------------------------------------------------
def _s1_terms_accepted(uid):
  """Browsing Server 1 is open to everyone. The Terms are shown (and must be agreed)
  EVERY time a user taps Buy - see server1_buy_terms()."""
  return True


def _s1_terms_text():
  sep = "\u2500" * 16
  return (
    f"{P_STORE} <b>{_bold('SERVER 1 • CHEAP ACCOUNTS')}</b>\n"
    f"<i>Terms and Conditions</i>\n"
    f"{sep}\n\n"
    f"<b>{_bold('ORIGIN')}</b>\n"
    f"Accounts in this section come from these origins:\n"
    f"<blockquote>Phishing \u2022 Stealer \u2022 Resale</blockquote>\n"
    f"<b>{_bold('RISK')}</b>\n"
    f"These are high risk accounts. Please understand before you buy:\n"
    f"<blockquote>1. The account can get logged out at any time.\n"
    f"2. The OTP / login code may not arrive on some accounts.\n"
    f"3. The account can get frozen, limited or banned.</blockquote>\n"
    f"<b>{_bold('NO REFUND - STRICTLY NO REFUND')}</b>\n"
    f"<blockquote>No refund, replacement, or compensation will be issued on Server 1 accounts "
    f"under ANY circumstances.\n"
    f"This applies whether the OTP arrives or not, whether the account logs out, freezes, "
    f"gets limited, gets spammed, or is banned.</blockquote>\n"
    f"{sep}\n"
    f"<i>By tapping I Agree you confirm that you have read and accepted all of the above.</i>"
  )


async def server1_buy_terms(event, kind, code, arg):
  """Shown EVERY time before a Server 1 purchase (single or bulk). The buy only
  happens after the user taps 'I Agree and Continue'."""
  code = str(code or "").strip().upper()
  arg = str(arg or "").strip() or "-"
  btns = [
    [Button.inline("I Agree and Continue", f"srv1_ok|{kind}|{code}|{arg}", style="primary")],
    [Button.inline("Decline", f"srv1_c|{code}", style="danger")],
  ]
  return await e_edit_or_send(event, custom_emoji_text(_s1_terms_text()), btns)


async def server1_buy_agreed(event, kind, code, arg):
  arg = str(arg or "").strip()
  if kind == "q":
    try:
      qty = int(arg)
    except Exception:
      return await safe_callback_answer(event, "Invalid quantity.", alert=True)
    return await server1_bulk_buy(event, code, qty)
  return await server1_buy_number(event, code, None if arg in ("", "-", "None") else arg)


async def server1_terms(event):
  btns = [
    [Button.inline("I Agree and Continue", "srv1_agree", style="primary")],
    [Button.inline("Decline", "srv1_decline", style="danger")],
  ]
  return await e_edit_or_send(event, custom_emoji_text(_s1_terms_text()), btns)


async def server1_agree(event):
  uid = event.sender_id
  cur.execute("INSERT OR IGNORE INTO s1_terms (user_id) VALUES (?)", (uid,))
  db.commit()
  await safe_callback_answer(event, f"Terms accepted. Welcome to {BRAND_TITLE}!")
  return await server1_category_menu(event)


async def server1_category_menu(event):
  """Store -> Server 1 -> choose Pushing / Premium / Autoreg section."""
  uid = event.sender_id
  if not _s1_terms_accepted(uid):
    return await server1_terms(event)
  msg = (
    f"{P_TG} <b>Server 1 [ Cheap TG Accounts ]</b>\n"
    f"────────────────\n\n"
    f"{_s1_wallet_card(uid)}\n"
    f"────────────────\n\n"
    f"{P_ASST} Please choose an account section:"
  )
  btns = [
    [Button.inline("Pushing Account", "srv1_cat|push")],
    [Button.inline("Premium Account", "srv1_cat|premium")],
    [Button.inline("Autoreg Account", "srv1_cat|autoreg")],
    [Button.inline("My Orders", "cb_orders")],
    [Button.inline("Back to Store", "store_servers")],
  ]
  return await e_edit_or_send(event, custom_emoji_text(msg), btns)


async def server1_pick_category(event, cat):
  uid = event.sender_id
  if not _s1_terms_accepted(uid):
    return await server1_terms(event)
  cat = str(cat or "").strip().lower()
  if cat not in S1_CATEGORIES:
    return await safe_callback_answer(event, "Unknown section.", alert=True)
  f = _s1_filters(uid)
  _s1_set_category(f, cat)
  f["search"] = ""
  return await server1_countries_menu(event, 1)


async def server1_decline(event):
  await safe_callback_answer(event, "You must accept the terms to use Server 1.", alert=True)
  return await store_servers_menu(event)


# ---- Wallet / filter state ---------------------------------------------------
def _s1_wallet(uid):
  row = cur.execute("SELECT balance, total_deposited FROM users WHERE user_id=?", (uid,)).fetchone()
  balance = int(row[0] or 0) if row else 0
  deposited = int(row[1] or 0) if row else 0
  spent_row = cur.execute(
    "SELECT COALESCE(SUM(price),0) FROM s2_orders WHERE user_id=? AND charged=1", (uid,)).fetchone()
  spent = int(spent_row[0] or 0) if spent_row else 0
  return balance, deposited, spent


def _s1_wallet_card(uid):
  balance, deposited, spent = _s1_wallet(uid)
  return (
    f"{P_CARD} <b>WALLET</b>\n"
    f"{P_MONEY} Balance : ₹{balance}\n"
    f"{P_PKG} Deposited : ₹{deposited}\n"
    f"{P_STATS} Spent : ₹{spent}"
  )


_S1_FILTER_KEYS = ("spam", "premium", "origin", "email")


def _s1_norm_value(key, value):
  """Normalise a filter value to the canonical UI token.

  Accepts both UI tokens ("only", "free", "blocked", "required") and raw
  API-style values ("yes"/"no"/"true"/"false"/"1"/"0") so a value that
  leaks in from the API can never make the UI show the wrong label.
  """
  v = str(value if value is not None else "any").strip().lower()
  if key == "premium":
    return {"yes": "only", "true": "only", "1": "only", "premium": "only",
            "only": "only", "no": "any", "false": "any", "0": "any",
            "none": "any", "": "any", "any": "any"}.get(v, v or "any")
  if key == "email":
    return {"yes": "required", "true": "required", "1": "required",
            "required": "required", "no": "any", "false": "any", "0": "any",
            "none": "any", "": "any", "any": "any"}.get(v, v or "any")
  if key == "spam":
    return {"yes": "blocked", "true": "blocked", "blocked": "blocked",
            "spam blocked": "blocked", "no": "free", "false": "free",
            "free": "free", "spam free": "free", "temp": "temp",
            "temporary": "temp", "temporary spam": "temp", "none": "any",
            "": "any", "any": "any"}.get(v, v or "any")
  if key == "origin":
    return "any" if v in ("", "none", "any") else v
  return v


def _s1_filters(uid):
  f = S1_FILTERS.get(uid)
  if not isinstance(f, dict):
    f = dict(S1_FILTER_DEFAULTS)
    S1_FILTERS[uid] = f
  for k, v in S1_FILTER_DEFAULTS.items():
    f.setdefault(k, v)
  # Self-heal any legacy/API-style value that may already be stored.
  for k in _S1_FILTER_KEYS:
    f[k] = _s1_norm_value(k, f.get(k))
  return f


def _s1_api_params(f):
  """Map UI filter state -> (spam, premium, email) API query values."""
  spam = {"free": "no", "blocked": "yes"}.get(_s1_norm_value("spam", f.get("spam")))
  premium = "yes" if _s1_norm_value("premium", f.get("premium")) == "only" else None
  email = "yes" if _s1_norm_value("email", f.get("email")) == "required" else None
  return spam, premium, email


def _s1_filters_active(f):
  return (
    _s1_norm_value("spam", f.get("spam")) != "any"
    or _s1_norm_value("premium", f.get("premium")) != "any"
    or _s1_norm_value("origin", f.get("origin")) != "any"
    or _s1_norm_value("email", f.get("email")) != "any"
    or bool(str(f.get("search") or "").strip())
  )


def _s1_filter_value_label(key, value):
  value = _s1_norm_value(key, value)
  if key == "spam":
    return {"any": "Any", "free": "Spam Free", "blocked": "Spam Blocked",
            "temp": "Temporary Spam"}.get(value, "Any")
  if key == "premium":
    return {"any": "Any", "only": "Premium Only"}.get(value, "Any")
  if key == "origin":
    return "Any" if value == "any" else value.title()
  if key == "email":
    return {"any": "Any", "required": "Required"}.get(value, "Any")
  return value


def _s1_filter_summary(f):
  search = str(f.get("search") or "").strip()
  return (
    f"Spam : {_s1_filter_value_label('spam', f.get('spam'))}\n"
    f"Premium : {_s1_filter_value_label('premium', f.get('premium'))}\n"
    f"Origin : {_s1_filter_value_label('origin', f.get('origin'))}\n"
    f"Email : {_s1_filter_value_label('email', f.get('email'))}\n"
    f"Search : {search if search else '—'}"
  )


def _s1_truthy(v):
  """Best-effort boolean for API fields that arrive as Yes/No strings."""
  if v is None or v == "":
    return None
  if isinstance(v, bool):
    return v
  if isinstance(v, (int, float)):
    return v != 0
  s = str(v).strip().lower()
  if s in ("yes", "true", "1", "y", "on", "enabled", "premium", "premium only",
           "spam blocked", "blocked", "required", "active"):
    return True
  if s in ("no", "false", "0", "n", "off", "disabled", "none", "null", "n/a",
           "free", "spam free"):
    return False
  return None


def _s1_apply_client_filters(items, f):
  origin = _s1_norm_value("origin", f.get("origin"))
  search = str(f.get("search") or "").strip().lower()
  premium_want = _s1_norm_value("premium", f.get("premium"))
  spam_want = _s1_norm_value("spam", f.get("spam"))
  email_want = _s1_norm_value("email", f.get("email"))
  cat = str(f.get("cat") or "")
  out = []
  for it in items:
    if cat == "autoreg" and not _s1_is_autoreg(it):
      continue
    if cat == "push" and (_s1_is_autoreg(it) or _s1_truthy(it.get("premium")) is True):
      continue
    if cat == "premium" and _s1_truthy(it.get("premium")) is False:
      continue
    if origin != "any":
      blob = f"{it.get('origin','')} {it.get('resale_origin','')}".lower()
      if origin not in blob:
        continue
    # Defensive client-side filtering: some countries do not support every
    # server-side filter, so enforce the selection locally as well. This is
    # what keeps "Premium Only" from ever showing a non-premium account.
    if premium_want == "only" and _s1_truthy(it.get("premium")) is False:
      continue
    # Unknown spam status is NOT a reason to hide an account: the server-side
    # filter already did the real work. Only drop an explicit mismatch.
    if spam_want == "free" and _s1_truthy(it.get("spam")) is True:
      continue
    if spam_want == "blocked" and _s1_truthy(it.get("spam")) is False:
      continue
    if email_want == "required" and _s1_truthy(it.get("email")) is False:
      continue
    if search:
      blob = " ".join(str(it.get(k) or "") for k in (
        "id", "origin", "resale_origin", "uploaded", "last_seen", "dial",
        "name", "country")).lower()
      if search not in blob:
        continue
    out.append(it)
  return out


def _s1_filter_diag(items, f):
  """Which single filter hides the accounts the API did return? -> readable lines."""
  lines = []
  base = dict(S1_FILTER_DEFAULTS)
  for key, label in (("cat", "Section"), ("spam", "Spam"), ("premium", "Premium"),
                     ("origin", "Origin"), ("email", "Email"), ("search", "Search")):
    val = f.get(key)
    if key == "cat":
      if not val:
        continue
    elif key == "search":
      if not str(val or "").strip():
        continue
    elif _s1_norm_value(key, val) == "any":
      continue
    only = dict(base)
    only[key] = val
    left = len(_s1_apply_client_filters(items, only))
    if left < len(items):
      shown = _s1_cat_label(val) if key == "cat" else (
        str(val) if key == "search" else _s1_filter_value_label(key, val))
      lines.append(f"\u2022 {label}: {shown} \u2192 {left} of {len(items)} left")
  return lines


def _s1_detail(country_code, f, force_refresh=False):
  spam, premium, email = _s1_api_params(f)
  return fetch_s1_country_detail(country_code, spam, force_refresh, premium, email, f.get("cat"))


def _yn(v, unknown="N/A"):
  b = _s1_truthy(v)
  if b is None:
    return unknown
  return "Yes" if b else "No"


def _premium_text(it, f=None):
  """'Yes (ends 20 Sep 2026)' / 'Yes' / 'No' / 'N/A'. No date is shown for 'No'."""
  default = "N/A"
  if f is not None and _s1_norm_value("premium", f.get("premium")) == "only":
    default = "Yes"
  val = _yn(it.get("premium"), default)
  end = (it.get("premium_end") or "").strip()
  # An expiry date is definitive evidence that the account has Premium,
  # even when the API omits its separate boolean/status field.
  if end and val == "N/A":
    val = "Yes"
  if val == "Yes" and end:
    return f"Yes (ends {html.escape(end)})"
  return val


# ---- Order persistence -------------------------------------------------------
try:
  cur.execute("ALTER TABLE s2_orders ADD COLUMN session_str TEXT DEFAULT ''")
  db.commit()
except Exception:
  pass


try:
  cur.execute("ALTER TABLE s2_orders ADD COLUMN twofa_has INTEGER DEFAULT -1")
  db.commit()
except Exception:
  pass


def _s1_finalize_purchase(uid, batch_id, order, country_code, country_name, price):
  """Store a bought account and charge the user's wallet exactly once."""
  accounts = order.get("accounts") or []
  acc = accounts[0] if accounts else {}
  order_no = str(acc.get("order_no") or "")
  phone = str(acc.get("phone") or "")
  acc_pwd = str(acc.get("password") or "")
  row = cur.execute("SELECT charged FROM s2_orders WHERE order_id=?", (batch_id,)).fetchone()
  if row is None:
    cur.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (price, uid))
    cur.execute(
      "INSERT INTO s2_orders (order_id, user_id, country_code, country_name, number, price, "
      "status, code, password, account_no, charged) VALUES (?,?,?,?,?,?,?,?,?,?,1)",
      (batch_id, uid, country_code, country_name, phone, price, "waiting", "", acc_pwd, order_no))
  else:
    if not int(row[0] or 0):
      cur.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (price, uid))
    cur.execute(
      "UPDATE s2_orders SET number=?, price=?, status='waiting', password=?, account_no=?, charged=1 "
      "WHERE order_id=?",
      (phone, price, acc_pwd, order_no, batch_id))
  db.commit()
  try:
    cur.execute("UPDATE s2_orders SET session_str=? WHERE order_id=?",
                (str(acc.get("session") or ""), batch_id))
    db.commit()
  except Exception:
    pass
  _global_order_register('server1', batch_id, uid, price, 'PROCESSING')
  return order_no, phone


def _s1_finalize_bulk(uid, batch_id, order, country_code, country_name):
  """Store every delivered account of a bulk order, charging each exactly once."""
  created = []
  for acc in (order.get("accounts") or []):
    order_no = str(acc.get("order_no") or "")
    phone = str(acc.get("phone") or "")
    acc_pwd = str(acc.get("password") or "")
    try:
      api_price = float(acc.get("price") or 0)
    except Exception:
      api_price = 0.0
    price = server_sell_price(api_price)
    row_id = f"{batch_id}#{order_no or phone}"
    if cur.execute("SELECT 1 FROM s2_orders WHERE order_id=?", (row_id,)).fetchone():
      continue
    cur.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (price, uid))
    cur.execute(
      "INSERT INTO s2_orders (order_id, user_id, country_code, country_name, number, price, "
      "status, code, password, account_no, charged) VALUES (?,?,?,?,?,?,?,?,?,?,1)",
      (row_id, uid, country_code, country_name, phone, price, "waiting", "", acc_pwd, order_no))
    try:
      cur.execute("UPDATE s2_orders SET session_str=? WHERE order_id=?",
                  (str(acc.get("session") or ""), row_id))
    except Exception:
      pass
    created.append({"row_id": row_id, "number": phone, "price": price, "order_no": order_no})
  db.commit()
  for item in created:
    _global_order_register('server1', item['row_id'], uid, item['price'], 'PROCESSING')
  return created


def _s1_store_pending(uid, batch_id, country_code, country_name, price, status):
  # Never reset an existing row (and never reset its `charged` flag): a
  # pending update must not be able to re-enable a second charge later.
  cur.execute("UPDATE s2_orders SET status=? WHERE order_id=?",
              (status or "processing", batch_id))
  if cur.rowcount == 0:
    cur.execute(
      "INSERT INTO s2_orders (order_id, user_id, country_code, country_name, number, "
      "price, status, code, password, account_no, charged) VALUES (?,?,?,?,?,?,?,?,?,?,0)",
      (batch_id, uid, country_code, country_name, "", price, status or "processing", "", "", ""))
  db.commit()


# ---- Country list ------------------------------------------------------------
def _s1_loading_line():
  """Status line shown while countries are still arriving from LZT."""
  if _s2_countries_cache.get("partial"):
    n = len(_s2_countries_cache.get("data") or [])
    return "%s <i>Loading more countries in background... %d found so far</i>\n\n" % (P_WAIT, n)
  return ""


_S1_LIVE_MENU = {}
_S1_ON_COUNTRY_LIST = {}   # uid -> True while the user is on the country list


async def _s1_live_menu_watch(event, uid, page, token, minutes=5):
  """Refresh the country list ONLY while the user is still looking at it.
  As soon as the user opens anything else (account list, My Orders, Back,
  etc.) this stops, so the bot never pulls them back to the country list."""
  deadline = time.time() + minutes * 60
  last = None
  while time.time() < deadline:
    await asyncio.sleep(8)
    if _S1_LIVE_MENU.get(uid) is not token:
      return                          # a newer country menu replaced this one
    if not _S1_ON_COUNTRY_LIST.get(uid):
      return                          # user navigated away from the list
    state = (len(_s2_countries_cache.get("data") or []), _s2_countries_cache.get("ts"))
    if state != last:
      last = state
      try:
        await server1_countries_menu(event, page, live=False)
      except Exception as ex:
        logger.debug("live country menu stopped: %s", ex)
        return
    if not _s2_countries_cache.get("partial"):
      return                          # crawl finished, final list already shown


async def server1_countries_menu(event, page=1, force_refresh=False, live=True):
  """Store -> Server 1 -> WALLET card + live country list."""
  uid = event.sender_id
  if not _s1_terms_accepted(uid):
    return await server1_terms(event)
  if live:
    _S1_ON_COUNTRY_LIST[uid] = True   # user opened the country list

  data = await asyncio.to_thread(fetch_s2_countries, force_refresh)
  if live and not isinstance(data, dict) and _s2_countries_cache.get("partial"):
    token = object()
    _S1_LIVE_MENU[uid] = token
    _spawn_bg(_s1_live_menu_watch(event, uid, page, token))
  if isinstance(data, dict):
    msg = (
      f"{P_TG} <b>Server 1 [ Cheap TG Accounts ]</b>\n"
      f"────────────────\n\n"
      f"{P_WARN} Could not load the server right now.\n"
      f"<i>{html.escape(str(data.get('error') or 'Unknown error'))}</i>"
    )
    btns = [
      [Button.inline("Try Again", "srv1_ref")],
      [Button.inline("Back to Store", "store_servers")],
    ]
    return await e_edit_or_send(event, custom_emoji_text(msg), btns)

  available = [c for c in data if c.get("code")]
  if not available:
    msg = (
      f"{P_STORE} <b>{BRAND_TITLE}</b>\n"
      f"────────────────\n\n"
      f"{P_WARN} No countries are available right now. Please check back later."
    )
    btns = [
      [Button.inline("Refresh", "srv1_ref")],
      [Button.inline("Back to Store", "store_servers")],
    ]
    return await e_edit_or_send(event, custom_emoji_text(msg), btns)

  f = _s1_filters(uid)
  if str(f.get("sort") or "low").lower() == "high":
    available.sort(key=lambda c: (float(c.get("price") or 0), c.get("name") or ""), reverse=True)
  else:
    available.sort(key=lambda c: (float(c.get("price") or 0), c.get("name") or ""))

  total = len(available)
  total_pages = max(1, (total + S2_COUNTRIES_PER_PAGE - 1) // S2_COUNTRIES_PER_PAGE)
  try:
    page = int(page or 1)
  except Exception:
    page = 1
  page = max(1, min(page, total_pages))
  start = (page - 1) * S2_COUNTRIES_PER_PAGE
  page_items = available[start:start + S2_COUNTRIES_PER_PAGE]

  stock_vals = [int(c.get("stock")) for c in available if c.get("stock") is not None]
  accounts_txt = f"{sum(stock_vals):,}" if stock_vals else "live"

  lines = []
  for item in page_items:
    ccode = str(item.get("code") or "").strip().upper()
    cname = clean_country_name(item.get("name") or ccode)
    cprice = server_sell_price(item.get("price"))
    lines.append(f"{country_flag_html(ccode, cname)} <b>{html.escape(cname)}</b> — from ₹{cprice}")
  country_block = "\n".join(lines)

  filter_line = f"\n{P_WARN} <b>Filters Active</b>" if _s1_filters_active(f) else ""
  if _s1_cat_label(f.get("cat")):
    filter_line = f"\n{P_DIAMOND} <b>Section:</b> {_s1_cat_label(f.get('cat'))}" + filter_line
  sort_label = ("Sort - Price - High to Low"
                if str(f.get("sort") or "low").lower() == "high"
                else "Sort - Price - Low to High")

  msg = (
    f"{P_STORE} <b>{BRAND_TITLE}</b>\n"
    f"{P_ACC} <i>4,945 monthly users</i>\n"
        f"────────────────\n\n"
    f"{_s1_wallet_card(uid)}\n"
    f"────────────────\n\n"
    f"{P_PKG} <b>Accounts:</b> {accounts_txt} | <b>Countries:</b> {total}\n"
    f"{P_ASST} <b>Page:</b> {page} of {total_pages}{filter_line}\n\n"
    f"{_s1_loading_line()}"
    f"{country_block}"
  )

  btns = []
  for item in page_items:
    btns.append([Button.inline(
      _s1_country_label(item), f"srv1_c|{item.get('code')}",
      icon_custom_emoji_id=country_flag_icon_id(item.get("code"), item.get("name")))])

  nav = []
  if page > 1:
    nav.append(Button.inline("Prev", f"srv1_pg|{page-1}"))
  nav.append(Button.inline(f"{page}/{total_pages}", f"srv1_pg|{page}"))
  if page < total_pages:
    nav.append(Button.inline("Next", f"srv1_pg|{page+1}"))
  btns.append(nav)

  btns.append([Button.inline("Back", "srv1_accounts"),
               Button.inline("Search", "srv1_csearch"),
               Button.inline("Filters", "srv1_filters")])
  btns.append([Button.inline(sort_label, f"srv1_sort|{'low' if str(f.get('sort') or 'low').lower() == 'high' else 'high'}")])
  btns.append([Button.inline("My Orders", "cb_orders"),
               Button.inline("Add Funds", "cb_addfunds")])
  return await e_edit_or_send(event, custom_emoji_text(msg), btns)


async def server1_set_sort(event, direction):
  uid = event.sender_id
  f = _s1_filters(uid)
  f["sort"] = "high" if str(direction).lower() == "high" else "low"
  await safe_callback_answer(event, f"Sorting: Price {'High to Low' if f['sort'] == 'high' else 'Low to High'}")
  return await server1_countries_menu(event, 1)


# ---- Country detail (stock + account list) ----------------------------------
async def server1_country_detail(event, country_code, page=1, force_refresh=False):
  uid = event.sender_id
  if not _s1_terms_accepted(uid):
    return await server1_terms(event)

  code = str(country_code or "").strip().upper()
  f = _s1_filters(uid)
  spam, premium, email = _s1_api_params(f)

  detail = await asyncio.to_thread(_s1_detail, code, f, force_refresh)
  if not isinstance(detail, dict) or detail.get("error"):
    # Must replace Loading... text (alert-only leaves "Nothing to show").
    err = (detail or {}).get("error") or "This country is not available."
    return await e_edit_or_send(
      event,
      custom_emoji_text(f"{P_NO} <b>Not available</b>\n\n{P_WARN} {html.escape(str(err))}"),
      [[Button.inline("Back", "srv1_countries"), Button.inline("Try Again", f"srv1_c|{code}")]])

  # Reseller upstream: /v1/accounts gives the same per-account list as the main
  # bot (price, 2FA, spam, premium, channels...). If the country has no account
  # rows, fall back to the simple country-level Buy card.
  reseller_mode = _is_reseller_upstream(1) or bool(detail.get("reseller"))

  items = await asyncio.to_thread(fetch_s1_items, code, force_refresh, spam, 20, premium, email, f.get("cat"))
  if isinstance(items, dict):
    if reseller_mode:
      # /v1/accounts failed (old main bot / temporary error): never block the
      # sale, fall back to the country-level Buy card below.
      items = []
    else:
      return await e_edit_or_send(
        event,
        custom_emoji_text(f"{P_NO} <b>Could not load accounts</b>\n\n"
                          f"{P_WARN} {html.escape(str(items.get('error') or 'Unknown error'))}"),
        [[Button.inline("Try Again", f"srv1_ipr|{code}|1")],
         [Button.inline("Back", "srv1_countries")]])

  _raw_items = list(items or [])
  items = _s1_apply_client_filters(_raw_items, f)
  cname = clean_country_name(detail.get("name") or code)
  stock = int(detail.get("stock") or 0)

  if not items:
    if reseller_mode and not _raw_items:
      # Country has stock but the reseller did not return individual rows:
      # keep the old country-level Buy card so selling never breaks.
      try:
        _rprice = int(float(detail.get("price") or 0))
      except Exception:
        _rprice = 0
      if _rprice <= 0:
        return await e_edit_or_send(
          event,
          custom_emoji_text(f"{P_NO} <b>Price unavailable</b>\n\nTry another country."),
          [[Button.inline("Back", "srv1_countries")]])
      _rmsg = (
        f"{country_flag_html(code, cname)} <b>{html.escape(cname.upper())}</b>\n"
        f"{P_PKG} Stock : {stock if stock > 0 else 'Available'}\n"
        f"{P_MONEY} Price : <b>₹{_rprice}</b>\n"
        f"────────────────\n\n"
        f"<i>Reseller stock from main store. Tap Buy to get a number.</i>"
      )
      _rbtns = [
        [Button.inline(f"Buy Now — ₹{_rprice}", f"srv1_buy|{code}|-", style="success")],
        [Button.inline("Back", "srv1_countries"),
         Button.inline("Refresh", f"srv1_ipr|{code}|1")],
      ]
      return await e_edit_or_send(event, custom_emoji_text(_rmsg), _rbtns)
    _diag = _s1_filter_diag(_raw_items, f) if _raw_items else []
    _why = ("\n\n<b>Hidden by:</b>\n" + "\n".join(html.escape(x) for x in _diag)) if _diag else ""
    msg = (
      f"{country_flag_html(code, cname)} <b>{html.escape(cname.upper())}</b>\n"
      f"{P_PKG} Stock : {stock}\n"
      f"{P_MONEY} From : ₹{server_sell_price(detail.get('price'))}\n\n"
      f"{P_WARN} API returned {len(_raw_items)} account(s) but none match your filters."
      + _why
    )
    btns = [
      [Button.inline("Reset Filters", "srv1_freset")],
      [Button.inline("Back", "srv1_countries"),
       Button.inline("Filters", "srv1_filters")],
    ]
    return await e_edit_or_send(event, custom_emoji_text(msg), btns)

  total = len(items)
  pages = max(1, (total + S1_PAGE_SIZE - 1) // S1_PAGE_SIZE)
  try:
    page = int(page or 1)
  except Exception:
    page = 1
  page = max(1, min(page, pages))
  chunk = items[(page - 1) * S1_PAGE_SIZE: page * S1_PAGE_SIZE]
  low = min(server_sell_price(i["price"]) for i in items)

  filter_line = f"\n{P_WARN} <b>Filters Active</b>" if _s1_filters_active(f) else ""
  msg = (
    f"{country_flag_html(code, cname)} <b>{html.escape(cname.upper())}</b>\n"
    f"{P_PKG} Stock : {stock}\n"
    f"{P_MONEY} From : ₹{low}\n"
    + (f"{P_DIAMOND} Section : {_s1_cat_label(f.get('cat'))}\n" if _s1_cat_label(f.get('cat')) else "") +
    f"{P_ASST} Page : {page} of {pages}{filter_line}\n"
    f"────────────────"
  )

  btns, pair = [], []
  for it in chunk:
    star = ""  # no star next to premium accounts (shown in account details instead)
    pair.append(Button.inline(
      f"₹{server_sell_price(it['price'])}{star}",
      f"srv1_i|{code}|{it['id']}|{page}",
      icon_custom_emoji_id=country_flag_icon_id(code, cname)))
    if len(pair) == 2:
      btns.append(pair)
      pair = []
  if pair:
    btns.append(pair)

  if pages > 1:
    start_pg = max(1, min(page - 3, pages - 6))
    btns.append([Button.inline(f"[{n}]" if n == page else str(n), f"srv1_ip|{code}|{n}")
                 for n in range(start_pg, min(pages, start_pg + 6) + 1)])

  if stock > 1:
    btns.append([Button.inline("Bulk Buy", f"srv1_bulk|{code}")])
  btns.append([Button.inline("Back", "srv1_countries"),
               Button.inline("Filters", "srv1_filters"),
               Button.inline("Refresh", f"srv1_ipr|{code}|{page}")])
  try:
    await e_edit_or_send(event, custom_emoji_text(msg), btns)
  except MessageNotModifiedError:
    pass


# ---- Server 1 session security ----------------------------------------------
# After a Telegram account is delivered, the account usually still has the
# seller's / provider's sessions logged in. This block logs in with the
# delivered StringSession, kills every *other* session ("Terminate All Other
# Sessions") and finally logs the bot's own session out ("Terminate Bot
# Session") so the buyer receives a completely clean account.
#
# Mode is controlled by the admin setting  s1_secure_mode :
#   others  -> terminate other sessions right after the purchase, and the bot
#              session after the login code has been delivered (default)
#   all     -> terminate everything right after the purchase
#   off     -> do nothing (old behaviour, session string stays valid)
try:
  cur.execute("ALTER TABLE s2_orders ADD COLUMN secured INTEGER DEFAULT 0")
  db.commit()
except Exception:
  pass


# Automatic termination after purchase / handover is OFF. The buyer uses the
# buttons (Terminate Other Sessions / Terminate Bot Session) instead.
S1_AUTO_TERMINATE = False


def _s1_secure_mode():
  try:
    mode = str(get_setting("s1_secure_mode", "others") or "others").strip().lower()
  except Exception:
    mode = "others"
  return mode if mode in ("others", "all", "off") else "others"


async def _s1_terminate_sessions(session_string, include_self=False):
  """Terminate sessions of a Telegram account.

  Returns (ok, terminated_count, note).  ``include_self`` also logs the bot's
  own session out, which invalidates the StringSession for good.
  """
  if not session_string:
    return False, 0, "no_session"
  if _TGStringSession is None or _TGGetAuthorizations is None:
    return False, 0, "telethon_sessions_unavailable"

  client = None
  try:
    client = TelegramClient(_TGStringSession(session_string), API_ID, API_HASH)
    await asyncio.wait_for(client.connect(), timeout=45)
    try:
      authorized = await asyncio.wait_for(client.is_user_authorized(), timeout=20)
    except Exception:
      authorized = False
    if not authorized:
      return False, 0, "session_not_authorized"

    killed = 0
    try:
      res = await asyncio.wait_for(client(_TGGetAuthorizations()), timeout=30)
      for auth in (getattr(res, "authorizations", None) or []):
        if getattr(auth, "current", False):
          continue
        try:
          await asyncio.wait_for(
            client(_TGResetAuthorization(hash=auth.hash)), timeout=20)
          killed += 1
        except Exception as ex:
          logger.warning("s1 reset authorization failed: %s", ex)
    except Exception as ex:
      logger.warning("s1 get authorizations failed: %s", ex)

    if include_self:
      try:
        await asyncio.wait_for(client.log_out(), timeout=30)
      except Exception as ex:
        logger.warning("s1 log_out failed: %s", ex)

    return True, killed, "ok"
  except Exception as ex:
    logger.warning("s1 terminate sessions failed: %s", ex)
    return False, 0, str(ex)[:90]
  finally:
    try:
      if client is not None:
        await client.disconnect()
    except Exception:
      pass


_S1_SESSION_SENT = set()


async def _s1_session_res(order_id, account_no):
  """Session data for an order: the copy saved at purchase time when it exists
  (no extra API call), otherwise a fresh LZT request."""
  try:
    row = cur.execute(
      "SELECT COALESCE(session_str,'') FROM s2_orders WHERE order_id=?", (order_id,)).fetchone()
  except Exception:
    row = None
  cached = str(row[0] or "") if row else ""
  if cached:
    return {"ok": True, "string_session": cached, "dc_id": "-"}
  return await asyncio.to_thread(fetch_account_session, account_no)


_S1_2FA_TRIED = {}


def _s1_mark_completed(order_id):
  """Server 1 order becomes Completed automatically as soon as its login code is delivered."""
  try:
    cur.execute("UPDATE s2_orders SET status='completed' WHERE order_id=? "
                "AND lower(COALESCE(status,'')) NOT IN ('refunded','cancelled','failed')", (str(order_id),))
    cur.execute("UPDATE global_orders SET status='COMPLETED' WHERE service='server1' AND local_ref=? "
                "AND COALESCE(refunded,0)=0", (str(order_id),))
    db.commit()
  except Exception as ex:
    logger.warning("s1 auto-complete failed: %s", ex)

_WATCH_SEM = None


def _watch_sem():
  """Max 3 background OTP status calls at the same time (keeps threads / RAM low
  when many orders or a big bulk buy are being watched)."""
  global _WATCH_SEM
  if _WATCH_SEM is None:
    _WATCH_SEM = asyncio.Semaphore(3)
  return _WATCH_SEM


async def _s1_check_2fa(order_id):
  """Ask Telegram whether this account has a 2FA (cloud) password, using the saved
  session. Read-only: it does not log in with the password and does not change
  anything. Stores 1 (enabled) or 0 (disabled) in twofa_has."""
  tries = _S1_2FA_TRIED.get(order_id, 0)
  if tries >= 3 or _TGStringSession is None:
    return
  _S1_2FA_TRIED[order_id] = tries + 1
  row = cur.execute(
    "SELECT account_no, COALESCE(session_str,'') FROM s2_orders WHERE order_id=?", (order_id,)).fetchone()
  if not row:
    return
  account_no, sess = row
  if not sess:
    res = await asyncio.to_thread(fetch_account_session, account_no)
    sess = str(res.get("string_session") or "") if isinstance(res, dict) and res.get("ok") else ""
  if not sess:
    return
  from telethon.tl.functions.account import GetPasswordRequest
  client = None
  try:
    client = TelegramClient(_TGStringSession(sess), API_ID, API_HASH)
    await asyncio.wait_for(client.connect(), timeout=45)
    if not await asyncio.wait_for(client.is_user_authorized(), timeout=20):
      return
    info = await asyncio.wait_for(client(GetPasswordRequest()), timeout=30)
    has = 1 if getattr(info, "has_password", False) else 0
    cur.execute("UPDATE s2_orders SET twofa_has=? WHERE order_id=?", (has, order_id))
    db.commit()
  except Exception as ex:
    logger.warning("2FA status check failed: %s", ex)
  finally:
    try:
      if client is not None:
        await client.disconnect()
    except Exception:
      pass


def _s1_2fa_text(password, order_id):
  """What the buyer sees for 2FA. The real status comes from Telegram (twofa_has)."""
  pw = (password or "").strip()
  try:
    has = int(cur.execute(
      "SELECT COALESCE(twofa_has,-1) FROM s2_orders WHERE order_id=?", (order_id,)).fetchone()[0])
  except Exception:
    has = -1
  if has == -1 and order_id:
    _spawn_bg(_s1_check_2fa(order_id))      # status not known yet: check it now
  if has == 0:
    return "Disabled (no password)"
  if has == 1 and not pw:
    return "Enabled, password not provided by seller"
  if has == 1:
    return "%s (2FA enabled)" % pw
  return pw or "No password / not provided"


# ---- Live session status (checked with Telegram itself) ----------------------------
# A provider "403" does NOT always mean the account is dead.  Before telling a buyer
# anything, the bot logs in with the saved session and asks Telegram directly:
#   live        -> session works (and the newest login code is read straight from Telegram)
#   dead        -> logged out / banned / deactivated
#   terminated  -> the buyer already terminated the bot session on purpose
#   unknown     -> could not verify (network / timeout) -> just retry
# Nothing here ever shows a provider name, URL, key or raw error to the user.
_TG_DEAD_ERR_NAMES = (
  "AuthKeyUnregisteredError", "SessionRevokedError", "SessionExpiredError",
  "UserDeactivatedError", "UserDeactivatedBanError", "PhoneNumberBannedError",
  "AuthKeyDuplicatedError",
)
_S1_CODE_MAX_AGE = 15 * 60   # only codes issued in the last 15 minutes are accepted


def _tg_dead_error_types():
  try:
    import telethon.errors as _te
    return tuple(getattr(_te, n) for n in _TG_DEAD_ERR_NAMES if hasattr(_te, n))
  except Exception:
    return ()


async def _s1_live_status(order_id, account_no):
  """Ask Telegram (saved session) if the account session is alive; read the newest login code."""
  out = {"state": "unknown", "code": "", "when": None}
  try:
    row = cur.execute("SELECT COALESCE(secured,0) FROM s2_orders WHERE order_id=?", (order_id,)).fetchone()
    if row and int(row[0] or 0) >= 2:
      out["state"] = "terminated"
      return out
  except Exception:
    pass
  if _TGStringSession is None:
    return out
  try:
    sres = await _s1_session_res(order_id, account_no)
  except Exception:
    sres = None
  sess = str(sres.get("string_session") or "") if isinstance(sres, dict) and sres.get("ok") else ""
  if not sess:
    return out
  dead_types = _tg_dead_error_types()
  client = None
  try:
    client = TelegramClient(_TGStringSession(sess), API_ID, API_HASH)
    await asyncio.wait_for(client.connect(), timeout=25)
    try:
      authorized = await asyncio.wait_for(client.is_user_authorized(), timeout=15)
    except dead_types:
      authorized = False
    if not authorized:
      out["state"] = "dead"
      return out
    out["state"] = "live"
    try:
      msgs = await asyncio.wait_for(client.get_messages(777000, limit=8), timeout=15)
      for m in msgs:
        txt = (getattr(m, "message", "") or "")
        low = txt.lower()
        if not txt or "login detected" in low or "new login" in low:
          continue
        mt = re.search(r"\b\d{5}\b", txt)
        if mt and (time.time() - m.date.timestamp()) <= _S1_CODE_MAX_AGE:
          out["code"], out["when"] = mt.group(), m.date
          break
    except Exception as ex:
      logger.warning("live code read failed: %s", ex)
    return out
  except dead_types:
    out["state"] = "dead"
    return out
  except Exception as ex:
    logger.warning("live status check failed: %s", ex)
    return out
  finally:
    try:
      if client is not None:
        await client.disconnect()
    except Exception:
      pass


async def _s1_get_code(order_id, account_no, deep=True):
  """Login code for a Server 1 order. Tries the normal way first; when that fails it checks the
  REAL session status with Telegram and can still return the code from the live session.
  deep=False (background watcher) only does the live check when the provider says 'invalid'."""
  res = await asyncio.to_thread(fetch_s2_code, account_no)
  if isinstance(res, dict) and res.get("ok"):
    res["live"] = "live"
    return res
  err = str(res.get("error") or "") if isinstance(res, dict) else ""
  if err == "rate_limited":
    return res
  if not deep and err != "session_invalid":
    return res
  st = await _s1_live_status(order_id, account_no)
  state = st.get("state")
  if state == "live":
    if st.get("code"):
      return {"ok": True, "code": st["code"], "live": "live"}
    return {"ok": False, "error": "no_code_yet", "live": "live",
            "message": "Session is LIVE. No login code yet - request it in Telegram, then check again."}
  if state == "dead":
    return {"ok": False, "error": "session_dead", "live": "dead",
            "message": "Session is NOT live (account logged out or banned). Please contact support."}
  if state == "terminated":
    return {"ok": False, "error": "session_terminated", "live": "terminated",
            "message": "Bot session was terminated, so the code can't be read here. Log in with your number and the latest Telegram code."}
  out = dict(res) if isinstance(res, dict) else {"ok": False}
  out["live"] = "unknown"
  if err == "session_invalid":
    out["error"] = "check_failed"
    out["message"] = "Could not verify the session status right now. Please try again in a minute."
  return out


async def _s1_auto_delivery_watch(uid, order_id, minutes=15):
  """Background job after a Server 1 purchase:
  - delivers the session file automatically if it was not sent yet (retries),
  - reads the LATEST login code and sends it to the buyer right away, then keeps
    watching and sends every newer code the moment Telegram issues it.
  Stops after `minutes`, when the bot session is terminated / invalid."""
  deadline = time.time() + minutes * 60
  last_sent = None
  _first = True
  while time.time() < deadline:
    # first pass runs immediately (session file + latest OTP go out right after the buy)
    await asyncio.sleep(0 if _first else (6 if last_sent is None else 15))
    _first = False
    try:
      row = cur.execute(
        "SELECT account_no, number, COALESCE(secured,0) "
        "FROM s2_orders WHERE order_id=?", (order_id,)).fetchone()
    except Exception:
      return
    if not row or not row[0] or int(row[2] or 0) >= 2:
      return
    account_no, number, _sec = row
    if order_id not in _S1_SESSION_SENT:
      try:
        await _send_s1_session_file(uid, order_id)
      except Exception as ex:
        logger.warning("auto session delivery retry failed: %s", ex)
    if order_id in _S1_SESSION_SENT:
      try:
        if int(cur.execute("SELECT COALESCE(twofa_has,-1) FROM s2_orders WHERE order_id=?",
                           (order_id,)).fetchone()[0]) == -1:
          await _s1_check_2fa(order_id)
      except Exception as ex:
        logger.warning("2FA check in watcher failed: %s", ex)
    async with _watch_sem():
      res = await _s1_get_code(order_id, account_no, deep=False)
    if isinstance(res, dict) and res.get("ok") and res.get("code"):
      code = str(res["code"])
      if code != last_sent:
        first_code = last_sent is None
        last_sent = code
        try:
          cur.execute("UPDATE s2_orders SET code=? WHERE order_id=?",
                      (code, order_id))
          db.commit()
          _s1_mark_completed(order_id)
        except Exception:
          pass
        try:
          await bot.send_message(uid, custom_emoji_text(
            f"{P_OTP} <b>{_bold('Latest Login Code' if first_code else 'New Login Code Received!')}</b>\n\n"
            f"{P_PHONE} <b>Number:</b> <code>{html.escape(str(number or '-'))}</code>\n"
            f"{P_OTP} <b>Code:</b> <code>{html.escape(_otp_gap(code))}</code>\n\n"
            f"{P_WARN} <i>Log in quickly, the code expires. Never share it. "
            f"If this code does not work, request a new code in Telegram — the newest one "
            f"will be sent here automatically.</i>"),
            parse_mode='html')
        except Exception as ex:
          logger.warning("auto code delivery failed: %s", ex)
    elif isinstance(res, dict) and res.get("error") in ("session_dead", "session_terminated"):
      return


async def _s1_secure_order(order_id, include_self=False):
  """Terminate other sessions via LZT Market API (and Telethon session if available)."""
  try:
    row = cur.execute(
      "SELECT account_no FROM s2_orders WHERE order_id=?", (order_id,)).fetchone()
  except Exception:
    row = None
  if not row or not row[0]:
    return False, 0, "no_account"
  account_no = str(row[0])

  # Primary: LZT Market native endpoint POST /{item_id}/telegram-reset-authorizations
  try:
    lzt_res = await asyncio.to_thread(
      _lzt_call, f"/{quote(account_no, safe='')}/telegram-reset-authorizations", "POST", None, None, 1, 60
    )
    if isinstance(lzt_res, dict) and lzt_res.get("ok"):
      try:
        cur.execute("UPDATE s2_orders SET secured=1 WHERE order_id=?", (order_id,))
        db.commit()
      except Exception:
        pass
      return True, 1, "ok"
  except Exception as ex:
    logger.warning("LZT telegram-reset-authorizations failed: %s", ex)

  # Fallback: Telethon StringSession termination
  try:
    res = await _s1_session_res(order_id, account_no)
  except Exception as ex:
    return False, 0, str(ex)[:90]
  if not isinstance(res, dict) or not res.get("ok"):
    return False, 0, _api_error_text(res) if isinstance(res, dict) else "session_fetch_failed"

  sess = str(res.get("string_session") or res.get("session") or res.get("string") or "").strip()
  if not sess:
    return False, 0, "session_empty"

  ok, killed, note = await _s1_terminate_sessions(sess, include_self=include_self)
  try:
    flag = 2 if (ok and include_self) else (1 if ok else 0)
    cur.execute("UPDATE s2_orders SET secured=? WHERE order_id=?", (flag, order_id))
    db.commit()
  except Exception:
    pass
  return ok, killed, note


async def _s1_logout_bot_only(session_string):
  """Log the bot's own session out. Other devices stay logged in."""
  if not session_string:
    return False, "no_session"
  if _TGStringSession is None:
    return False, "telethon_sessions_unavailable"
  client = None
  try:
    client = TelegramClient(_TGStringSession(session_string), API_ID, API_HASH)
    await asyncio.wait_for(client.connect(), timeout=45)
    try:
      authorized = await asyncio.wait_for(client.is_user_authorized(), timeout=20)
    except Exception:
      authorized = False
    if not authorized:
      return False, "session_not_authorized"
    await asyncio.wait_for(client.log_out(), timeout=30)
    return True, "ok"
  except Exception as ex:
    logger.warning("s1 bot logout failed: %s", ex)
    return False, str(ex)[:90]
  finally:
    try:
      if client is not None:
        await client.disconnect()
    except Exception:
      pass


def _s1_order_owner_check(event, order_id):
  row = cur.execute(
    "SELECT user_id, number, account_no FROM s2_orders WHERE order_id=?", (order_id,)).fetchone()
  return row


async def server1_secure_confirm(event, kind, order_id):
  """Confirmation screen before a session is terminated."""
  uid = event.sender_id
  row = _s1_order_owner_check(event, order_id)
  if not row:
    return await safe_callback_answer(event, "Order not found.", alert=True)
  if int(row[0]) != int(uid) and not is_admin(uid):
    return await safe_callback_answer(event, "This order belongs to another user.", alert=True)
  number = html.escape(str(row[1] or "-"))
  if kind == "b":
    title = "Terminate Bot Session?"
    body = ("The bot will <b>log out</b> of this account.\n"
            "After this the bot can no longer read the OTP or send the session file.\n"
            "Other devices stay logged in.\n\n<i>This cannot be undone.</i>")
    yes_label, yes_cb = "Yes, Terminate Bot", f"srv1_secx|b|{order_id}"
  else:
    title = "Terminate All Other Sessions?"
    body = ("Every device except the bot will be <b>logged out</b>.\n"
            "The bot session stays active, so the OTP still works.\n\n"
            "<i>This cannot be undone.</i>")
    yes_label, yes_cb = "Yes, Terminate Others", f"srv1_secx|o|{order_id}"
  msg = (f"{P_WARN} <b>{title}</b>\n\n"
         f"{P_PHONE} <b>Number:</b> <code>{number}</code>\n\n{body}")
  await safe_callback_answer(event)
  return await e_edit_or_send(
    event, custom_emoji_text(msg),
    [[Button.inline(yes_label, yes_cb, style="danger")],
     [Button.inline("Cancel", f"srv1_ord|{order_id}", style="primary")]])


async def server1_secure_run(event, kind, order_id):
  """Run the termination that the buyer confirmed."""
  uid = event.sender_id
  row = _s1_order_owner_check(event, order_id)
  if not row:
    return await safe_callback_answer(event, "Order not found.", alert=True)
  if int(row[0]) != int(uid) and not is_admin(uid):
    return await safe_callback_answer(event, "This order belongs to another user.", alert=True)
  number = html.escape(str(row[1] or "-"))
  account_no = row[2]
  back_btns = [[Button.inline("Back to Order", f"srv1_ord|{order_id}")],
               [Button.inline("My Orders", "cb_orders")]]

  if kind == "o":
    await safe_callback_answer(event, "Terminating other sessions...", alert=False)
    ok, killed, note = await _s1_secure_order(order_id, include_self=False)
    if ok:
      msg = (f"{P_YES} <b>Other Sessions Terminated</b>\n\n"
             f"{P_PHONE} <b>Number:</b> <code>{number}</code>\n"
             f"{P_2FA} <b>Bot session:</b> Still active \\u2705\n\n"
             f"{P_ASST} Every other device is logged out. OTP is still available.")
    else:
      msg = (f"{P_WARN} <b>Could Not Terminate Other Sessions</b>\n\n"
             f"{P_PHONE} <b>Number:</b> <code>{number}</code>\n"
             f"{P_NO} <b>Reason:</b> <code>{html.escape(str(note))}</code>\n\n"
             f"{P_ASST} Try again in a few seconds.")
    return await e_edit_or_send(event, custom_emoji_text(msg), back_btns)

  # kind == "b": log the bot's own session out
  await safe_callback_answer(event, "Terminating bot session...", alert=False)
  if not account_no:
    return await safe_callback_answer(event, "Session is not ready yet.", alert=True)
  res = await _s1_session_res(order_id, account_no)
  if not isinstance(res, dict) or not res.get("ok"):
    note = _api_error_text(res) if isinstance(res, dict) else "session_fetch_failed"
    msg = (f"{P_WARN} <b>Could Not Terminate Bot Session</b>\n\n"
           f"{P_PHONE} <b>Number:</b> <code>{number}</code>\n"
           f"{P_NO} <b>Reason:</b> <code>{html.escape(str(note))}</code>")
    return await e_edit_or_send(event, custom_emoji_text(msg), back_btns)

  sess = str(res.get("string_session") or res.get("session") or res.get("string") or "").strip()
  ok, note = await _s1_logout_bot_only(sess)
  if ok:
    try:
      cur.execute("UPDATE s2_orders SET secured=2 WHERE order_id=?", (order_id,))
      db.commit()
    except Exception:
      pass
    msg = (f"{P_YES} <b>Bot Session Terminated</b>\n\n"
           f"{P_PHONE} <b>Number:</b> <code>{number}</code>\n"
           f"{P_2FA} <b>Other devices:</b> Still logged in\n\n"
           f"{P_WARN} The bot is logged out. It can no longer read OTP or send the session file.")
  else:
    msg = (f"{P_WARN} <b>Could Not Terminate Bot Session</b>\n\n"
           f"{P_PHONE} <b>Number:</b> <code>{number}</code>\n"
           f"{P_NO} <b>Reason:</b> <code>{html.escape(str(note))}</code>")
  return await e_edit_or_send(event, custom_emoji_text(msg), back_btns)


async def server1_secure_others(event, order_id):
  """Legacy 'Terminate Sessions' buttons: now only terminate other sessions."""
  return await server1_secure_run(event, "o", order_id)


async def server1_secure_account(event, order_id):
  """Manual button: terminate every session (including the bot's own)."""
  uid = event.sender_id
  row = cur.execute(
    "SELECT user_id, number FROM s2_orders WHERE order_id=?", (order_id,)).fetchone()
  if not row:
    return await safe_callback_answer(event, "Order not found.", alert=True)
  if int(row[0]) != int(uid) and not is_admin(uid):
    return await safe_callback_answer(event, "This order belongs to another user.", alert=True)

  await safe_callback_answer(event, "Terminating sessions...", alert=False)
  ok, killed, note = await _s1_secure_order(order_id, include_self=True)

  if ok:
    msg = (
      f"{P_YES} <b>Account Secured</b>\n"
      f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n"
      f"{P_PHONE} <b>Number:</b> <code>{html.escape(str(row[1] or '-'))}</code>\n"
      f"{P_2FA} <b>Other sessions terminated:</b> {killed}\n"
      f"{P_2FA} <b>Bot session:</b> Terminated \u2705\n\n"
      f"{P_ASST} The account is now clean. Log in with the number and the "
      f"login code \u2014 nobody else can access it."
    )
  else:
    msg = (
      f"{P_WARN} <b>Could Not Secure The Account</b>\n"
      f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n"
      f"{P_PHONE} <b>Number:</b> <code>{html.escape(str(row[1] or '-'))}</code>\n"
      f"{P_NO} <b>Reason:</b> <code>{html.escape(str(note))}</code>\n\n"
      f"{P_ASST} Try again in a few seconds, or contact support."
    )

  btns = [
    [Button.inline("Try Again", f"srv1_sec|{order_id}")],
    [Button.inline("Check Code", f"srv1_code|{order_id}")],
    [Button.inline("My Orders", "cb_orders")],
    [Button.inline("Back to Store", "store_servers")],
  ]
  return await e_edit_or_send(event, custom_emoji_text(msg), btns)


# ---- Account details ---------------------------------------------------------
async def server1_item_detail(event, country_code, item_id, page=1):
  uid = event.sender_id
  if not _s1_terms_accepted(uid):
    return await server1_terms(event)

  code = str(country_code or "").strip().upper()
  f = _s1_filters(uid)
  spam, premium, email = _s1_api_params(f)
  items = await asyncio.to_thread(fetch_s1_items, code, True, spam, 20, premium, email, f.get("cat"))
  if isinstance(items, dict):
    items = []
  # Keep the detail page consistent with the list page: the same client-side
  # filter guard is applied, so a non-premium account can never appear while
  # the "Premium Only" filter is active.
  items = _s1_apply_client_filters(items or [], f)
  it = next((i for i in (items or []) if i["id"] == str(item_id)), None)
  back = [Button.inline("Back", f"srv1_ip|{code}|{page}")]
  if not it:
    return await e_edit_or_send(
      event, custom_emoji_text(f"{P_NO} <b>This account is no longer available.</b>"), [back])

  detail = await asyncio.to_thread(_s1_detail, code, f)
  cname = clean_country_name((detail or {}).get("name") or code)
  dial = it.get("dial") or (detail or {}).get("dial") or ""
  dial_txt = f"{code}{dial}" if dial else code
  price = server_sell_price(it["price"])
  origin = it.get("origin") or "Mixed"
  resale_origin = it.get("resale_origin") or "—"

  msg = (
    f"{P_CROWN} <b>ACCOUNT DETAILS</b>\n"
    f"────────────────\n\n"
    f"{P_GLOBE} <b>Country :</b> {country_flag_html(code, cname)} {html.escape(cname)} ({dial_txt})\n"
    f"{P_MONEY} <b>Price :</b> ₹{price}\n"
    f"{P_CARD} <b>Origin :</b> {html.escape(str(origin))}\n"
    f"{P_CARD} <b>Resale Origin :</b> {html.escape(str(resale_origin))}\n"
    f"{P_TIME} <b>Uploaded :</b> {html.escape(it.get('uploaded') or 'N/A')}\n"
    f"{P_TIME} <b>Last Seen :</b> {html.escape(it.get('last_seen') or 'N/A')}\n"
    f"{P_CROWN} <b>Premium :</b> {_premium_text(it, f)}\n"
    f"{P_ACC} <b>Groups/Ch :</b> {it.get('channels', 0)}Ch|{it.get('groups', 0)}Grp|{it.get('admins', 0)} Adm\n"
    f"{P_WARN} <b>Spam :</b> {_spam_status_text(it.get('spam'))}\n"
    f"{P_2FA} <b>2FA :</b> {_yn(it.get('twofa'))}\n"
    f"{P_ASST} <b>Email :</b> {_yn(it.get('email'))}"
  )
  btns = [
    [Button.inline(f"Buy Now — ₹{price}", f"srv1_buy|{code}|{it['id']}")],
    back + [Button.inline("Refresh", f"srv1_i|{code}|{it['id']}|{page}")],
  ]
  try:
    await e_edit_or_send(event, custom_emoji_text(msg), btns)
  except MessageNotModifiedError:
    pass


# ---- Single buy --------------------------------------------------------------
def _s1_purchase_card(order_id, balance_left=None, back_cb="srv1_countries",
                      secure_line="", rid=None, show_2fa=False, show_batch=False):
  """The exact 'Account Purchased Successfully' card. Used right after buying,
  in My Orders and in the admin order lookup so all three always look the same."""
  row = cur.execute(
    "SELECT country_code, country_name, number, price, status, code, password, account_no, "
    "COALESCE(secured,0) FROM s2_orders WHERE order_id=?", (order_id,)).fetchone()
  if not row:
    return None, None
  ccode, cname, number, price, status, code, password, account_no, secured = row
  code = _clean_otp(code)
  cname = clean_country_name(cname or ccode)
  gid = _global_order_id_for('server1', order_id) or '-'
  msg = (
    f"{P_YES} {P_PARTY} <b>{_bold('Account Purchased Successfully!')}</b>\n"
    f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n"
    f"{P_PHONE} <b>Number:</b> <code>{html.escape(str(number or 'Pending'))}</code>\n"
    f"{country_flag_html(ccode, cname)} <b>Country:</b> {html.escape(cname)}\n"
    f"{P_MONEY} <b>Paid:</b> \u20b9{price}\n"
  )
  if balance_left is not None:
    msg += f"{P_CARD} <b>Balance Left:</b> \u20b9{balance_left}\n"
  msg += (
    f"{P_ID} <b>Bot Order ID:</b> <code>{html.escape(str(gid))}</code>\n"
    + (f"{P_ID} <b>Batch ID:</b> <code>{html.escape(str(order_id))}</code>\n" if show_batch else "")
    + f"{P_ID} <b>Account No:</b> <code>{html.escape(str(account_no or '-'))}</code>\n"
    + secure_line
  )
  if code:
    msg += f"{P_OTP} <b>OTP:</b> <code>{html.escape(_otp_gap(code))}</code>\n"
  if show_2fa or code:
    msg += f"{P_2FA} <b>2FA:</b> <code>{html.escape(_s1_2fa_text(password, order_id))}</code>\n"
  if int(secured or 0) >= 2:
    msg += f"{P_KEY} <b>Bot session:</b> Terminated\n"
  if not code:
    msg += (
      f"\n{P_ASST} <b>Next step:</b>\n"
      f"1. Open Telegram and enter this number.\n"
      f"2. Request the login code.\n"
      f"3. The OTP and session file are sent to you automatically \u2014 or tap <b>Get Code</b>."
    )
  btns = [
    [Button.inline("Get Code", f"srv1_code|{order_id}")],
    [Button.inline("Terminate Other Sessions", f"srv1_secc|o|{order_id}")],
    [Button.inline("Terminate Bot Session", f"srv1_secc|b|{order_id}")],
    [Button.inline("Session String", f"srv1_ses|{order_id}")],
  ]
  if rid is not None:
    btns.append([Button.inline("Session File", f"mo_sf|s|{rid}")])
  btns.append([Button.inline("My Orders", "cb_orders")])
  btns.append([Button.inline("Back", back_cb)])
  return msg, btns


async def _s1_show_wait(event, text):
  """Show the 'Buying... please wait' screen so it can never be missed: edit the
  current message (buttons removed); if that fails, send a fresh message instead."""
  try:
    await e_edit_or_send(event, custom_emoji_text(text), [])
    return
  except Exception as ex:
    logger.warning("s1 wait edit failed (%s), sending a new message", ex)
  try:
    await bot.send_message(event.chat_id, custom_emoji_text(text), parse_mode='html')
  except Exception as ex2:
    logger.warning("s1 wait message could not be sent: %s", ex2)


async def server1_buy_number(event, country_code, item_id=None):
  uid = event.sender_id
  code = str(country_code or "").strip().upper()
  f = _s1_filters(uid)
  spam, premium, email = _s1_api_params(f)
  lock = get_user_lock(uid)
  if str(item_id or "").strip() in ("", "-", "None", "none"):
    item_id = None

  if lock.locked():
    return await safe_callback_answer(
      event, "Your purchase is already in progress. Please wait, do not tap again.", alert=True)

  async with lock:
    await safe_callback_answer(event, "Buying your account... Please wait.", alert=False)
    await _s1_show_wait(event,
      f"{P_WAIT} <b>Buying your account...</b>\n\n"
      f"{P_WARN} <i>Please wait. Do not tap again, your order is being processed.</i>")

    api_price = None
    if item_id:
      listed = await asyncio.to_thread(fetch_s1_items, code, True, spam, 20, premium, email, f.get("cat"))
      if isinstance(listed, dict):
        return await e_edit_or_send(
          event,
          custom_emoji_text(f"{P_NO} <b>Could not load this account.</b>\n\n"
                            f"{P_WARN} {html.escape(str(listed.get('error') or 'Unknown error'))}"),
          [[Button.inline("Back", f"srv1_ip|{code}|1")]])
      pick = next((i for i in (listed or []) if i["id"] == str(item_id)), None)
      if not pick:
        return await e_edit_or_send(
          event,
          custom_emoji_text(f"{P_NO} <b>This account was just sold.</b> Please pick another."),
          [[Button.inline("Back", f"srv1_ip|{code}|1")]])
      api_price = float(pick["price"])
      spam = premium = email = None  # exact account id decides the filters
    else:
      detail = await asyncio.to_thread(_s1_detail, code, f)
      if not isinstance(detail, dict) or detail.get("error"):
        return await e_edit_or_send(
          event,
          custom_emoji_text(f"{P_NO} <b>This country is not available right now.</b>\n\n"
                            f"{P_WARN} {html.escape(str((detail or {}).get('error') or 'Unknown error'))}"),
          [[Button.inline("Back", "srv1_countries")]])
      # Reseller lists may omit exact stock; allow buy when price is present.
      if (not detail.get("reseller") and not _is_reseller_upstream(1)
          and int(detail.get("stock") or 0) <= 0):
        return await e_edit_or_send(
          event, custom_emoji_text(f"{P_NO} <b>Out of stock.</b> Please pick another country."),
          [[Button.inline("Back", "srv1_countries")]])
      api_price = float(detail.get("price") or 0)

    if not api_price or api_price <= 0:
      return await e_edit_or_send(
        event, custom_emoji_text(f"{P_WARN} <b>Price is unavailable.</b> Please try again."),
        [[Button.inline("Back", "srv1_countries")]])

    price = server_sell_price(api_price)
    balance, _, _ = _s1_wallet(uid)
    if balance < price:
      msg = (
        f"{P_NO} <b>Insufficient Balance</b>\n\n"
        f"{P_MONEY} Price: ₹{price}\n"
        f"{P_CARD} Your Balance: ₹{balance}\n"
        f"{P_WARN} You need ₹{price - balance} more."
      )
      btns = [
        [Button.inline("Add Funds", "cb_addfunds")],
        [Button.inline("Back", "srv1_countries")],
      ]
      return await e_edit_or_send(event, custom_emoji_text(msg), btns)

    res = await asyncio.to_thread(
      create_nobelots_order, code, item_id, api_price, spam, 1, premium, email)

    if not res.get("ok"):
      err = str(res.get("error") or "")
      hint = ""
      if err == "insufficient_balance":
        hint = "\n\n<i>The server wallet is low. Please contact support.</i>"
      elif err == "no_stock":
        hint = "\n\n<i>This country just sold out. Try another one.</i>"
      elif err == "no_account_at_price":
        hint = "\n\n<i>The price changed. Please refresh and try again.</i>"
      elif err == "account_unavailable":
        hint = "\n\n<i>Someone else bought this account first. Pick another.</i>"
      elif err == "rate_limited":
        hint = "\n\n<i>Too many requests. Please wait a few seconds and retry.</i>"
      elif err == "server_not_allowed":
        hint = "\n\n<i>This server is not enabled for the API key.</i>"
      msg = (
        f"{P_NO} <b>{_bold('Purchase Failed')}</b>\n\n"
        f"{P_WARN} {html.escape(_api_error_text(res))}{hint}\n\n"
        f"{P_CARD} You were not charged."
      )
      btns = [
        [Button.inline("Try Again", f"srv1_c|{code}")],
        [Button.inline("Back", "srv1_countries")],
      ]
      return await e_edit_or_send(event, custom_emoji_text(msg), btns)

    batch_id = str(res.get("batch_id") or "").strip()
    if not batch_id:
      return await e_edit_or_send(
        event,
        custom_emoji_text(f"{P_WARN} API did not return an order id. Please contact support."),
        [[Button.inline("Back", "srv1_countries")]])

    final = await asyncio.to_thread(wait_nobelots_order, batch_id, 120)
    accounts = final.get("accounts") if isinstance(final, dict) else None
    detail = await asyncio.to_thread(_s1_detail, code, f)
    cname = clean_country_name((detail or {}).get("name") or code)

    if accounts:
      order_no, number = _s1_finalize_purchase(uid, batch_id, final, code, cname, price)
      new_balance, _, _ = _s1_wallet(uid)
      try:
        _s1_gid = _global_order_register('server1', batch_id, uid, price, 'PROCESSING')
        await log_s2_sale(uid, cname, batch_id, number, price, code, global_order_id=_s1_gid)
      except Exception:
        pass

      # ---- Session security: kill the seller's sessions right away ----
      secure_line = ""
      _mode = _s1_secure_mode()
      if S1_AUTO_TERMINATE and _mode in ("others", "all"):
        try:
          _ok, _killed, _note = await _s1_secure_order(
            batch_id, include_self=(_mode == "all"))
          if _ok:
            secure_line = (
              f"{P_2FA} <b>Security:</b> {_killed} other session(s) terminated"
              + (" \u00b7 bot session terminated" if _mode == "all" else "") + "\n")
          else:
            secure_line = (
              f"{P_WARN} <b>Security:</b> cleanup pending "
              f"(<code>{html.escape(str(_note))}</code>)\n")
        except Exception as _ex:
          logger.warning("s1 auto secure failed: %s", _ex)

      msg, btns = _s1_purchase_card(batch_id, balance_left=new_balance, secure_line=secure_line)
      _res = await e_edit_or_send(event, custom_emoji_text(msg), btns)
      # Auto delivery: watcher sends the session file at once and the OTP the moment it arrives.
      _spawn_bg(_s1_auto_delivery_watch(uid, batch_id))
      return _res

    status = str((final or {}).get("status") or "processing").lower()
    end = (final or {}).get("end") or {}
    if status in FINAL_ORDER_STATUSES:
      reason = str(end.get("reason") or status)
      message = str(end.get("message") or "No account could be bought.")
      msg = (
        f"{P_NO} <b>{_bold('Purchase Failed')}</b>\n\n"
        f"{P_WARN} {html.escape(message)}\n"
        f"{P_ID} <b>Reason:</b> <code>{html.escape(_hide_provider(reason))}</code>\n\n"
        f"{P_CARD} You were not charged."
      )
      btns = [
        [Button.inline("Try Again", f"srv1_c|{code}")],
        [Button.inline("Back", "srv1_countries")],
      ]
      return await e_edit_or_send(event, custom_emoji_text(msg), btns)

    _s1_store_pending(uid, batch_id, code, cname, price, status)
    msg = (
      f"{P_WAIT} <b>{_bold('Order is Processing')}</b>\n"
      f"────────────────\n\n"
      f"{P_PKG} <b>Status:</b> {_s1_status_text(status)}\n"
      f"{country_flag_html(code, cname)} <b>Country:</b> {html.escape(cname)}\n"
      f"{P_MONEY} <b>Price:</b> ₹{price}\n\n"
      f"{P_ASST} The server is still buying your account. Open <b>My Orders</b> in a few seconds to collect it.\n"
      f"<i>You will only be charged once the account is delivered.</i>"
    )
    btns = [
      [Button.inline("Check Status", f"srv1_code|{batch_id}")],
      [Button.inline("My Orders", "cb_orders")],
      [Button.inline("Back", "srv1_countries")],
    ]
    return await e_edit_or_send(event, custom_emoji_text(msg), btns)


# ---- Bulk buy ----------------------------------------------------------------
async def server1_bulk_menu(event, country_code):
  uid = event.sender_id
  if not _s1_terms_accepted(uid):
    return await server1_terms(event)
  code = str(country_code or "").strip().upper()
  f = _s1_filters(uid)
  detail = await asyncio.to_thread(_s1_detail, code, f)
  if not isinstance(detail, dict) or detail.get("error"):
    return await safe_callback_answer(
      event, (detail or {}).get("error") or "This country is not available.", alert=True)

  cname = clean_country_name(detail.get("name") or code)
  price = server_sell_price(detail.get("price"))
  stock = int(detail.get("stock") or 0)
  balance, _, _ = _s1_wallet(uid)

  msg = (
    f"{P_CART} <b>BULK BUY</b>\n"
    f"────────────────\n\n"
    f"{country_flag_html(code, cname)} <b>Country :</b> {html.escape(cname)}\n"
    f"{P_MONEY} <b>Price each :</b> ₹{price}\n"
    f"{P_PKG} <b>Stock :</b> {stock}\n"
    f"{P_CARD} <b>Your Balance :</b> ₹{balance}\n\n"
    f"{P_ASST} Choose how many accounts to buy. You are charged per account as it is delivered."
  )
  btns = []
  row = []
  for q in (1, 2, 3, 5, 10):
    if q <= stock:
      row.append(Button.inline(f"{q}", f"srv1_bq|{code}|{q}"))
    if len(row) == 3:
      btns.append(row)
      row = []
  if row:
    btns.append(row)
  btns.append([Button.inline("Back", f"srv1_c|{code}")])
  return await e_edit_or_send(event, custom_emoji_text(msg), btns)


async def server1_bulk_buy(event, country_code, quantity):
  uid = event.sender_id
  code = str(country_code or "").strip().upper()
  try:
    qty = max(1, min(int(quantity or 1), 50))
  except Exception:
    qty = 1
  f = _s1_filters(uid)
  spam, premium, email = _s1_api_params(f)
  lock = get_user_lock(uid)

  if lock.locked():
    return await safe_callback_answer(
      event, "Please wait, your previous request is still processing.", alert=True)

  async with lock:
    await safe_callback_answer(event, f"Buying your {qty} accounts... Please wait.", alert=False)
    await _s1_show_wait(event,
      f"{P_WAIT} <b>Buying your {qty} accounts...</b>\n\n"
      f"{P_WARN} <i>Please wait. Do not tap again, your order is being processed.</i>")

    detail = await asyncio.to_thread(_s1_detail, code, f)
    if not isinstance(detail, dict) or detail.get("error"):
      return await safe_callback_answer(
        event, (detail or {}).get("error") or "This country is not available.", alert=True)

    cname = clean_country_name(detail.get("name") or code)
    stock = int(detail.get("stock") or 0)
    price_each = server_sell_price(detail.get("price"))
    if stock < qty:
      return await safe_callback_answer(
        event, f"Only {stock} accounts left in stock.", alert=True)

    balance, _, _ = _s1_wallet(uid)
    total_est = price_each * qty
    if balance < total_est:
      msg = (
        f"{P_NO} <b>Insufficient Balance</b>\n\n"
        f"{P_MONEY} Need: ₹{total_est} for {qty} × ₹{price_each}\n"
        f"{P_CARD} Your Balance: ₹{balance}\n"
        f"{P_WARN} You need ₹{total_est - balance} more."
      )
      return await e_edit_or_send(event, custom_emoji_text(msg), [
        [Button.inline("Add Funds", "cb_addfunds")],
        [Button.inline("Back", f"srv1_bulk|{code}")]])

    res = await asyncio.to_thread(
      create_nobelots_order, code, None, float(detail.get("price") or 0),
      spam, qty, premium, email)
    if not res.get("ok"):
      msg = (
        f"{P_NO} <b>Bulk Purchase Failed</b>\n\n"
        f"{P_WARN} {html.escape(_api_error_text(res))}\n\n"
        f"{P_CARD} You were not charged."
      )
      return await e_edit_or_send(event, custom_emoji_text(msg), [
        [Button.inline("Try Again", f"srv1_bulk|{code}")],
        [Button.inline("Back", "srv1_countries")]])

    batch_id = str(res.get("batch_id") or "").strip()
    if not batch_id:
      return await safe_callback_answer(event, "API did not return an order id.", alert=True)

    final = await asyncio.to_thread(wait_nobelots_order, batch_id, 180)
    accounts = final.get("accounts") if isinstance(final, dict) else None
    if accounts:
      created = _s1_finalize_bulk(uid, batch_id, final, code, cname)
      new_balance, _, _ = _s1_wallet(uid)
      total_paid = sum(c["price"] for c in created)
      for c in created:
        try:
          _s1_gid = _global_order_register('server1', c["row_id"], uid, c["price"], 'PROCESSING')
          await log_s2_sale(uid, cname, c["row_id"], c["number"], c["price"], code, global_order_id=_s1_gid)
        except Exception:
          pass
      lines = "\n".join(
        f"{P_PHONE} <code>{html.escape(c['number'] or c['order_no'] or '-')}</code> — ₹{c['price']}\n"
        f"{P_ID} Bot Order ID: <code>{_global_order_id_for('server1', c['row_id']) or '-'}</code>"
        for c in created) or "<i>No new accounts were delivered.</i>"
      # Terminate the seller's sessions on every delivered account.
      _mode = _s1_secure_mode()
      secure_line = ""
      if S1_AUTO_TERMINATE and _mode in ("others", "all"):
        _killed_total = 0
        _failed = 0
        for c in created:
          try:
            _ok, _k, _n = await _s1_secure_order(
              c["row_id"], include_self=(_mode == "all"))
            if _ok:
              _killed_total += _k
            else:
              _failed += 1
          except Exception as _ex:
            logger.warning("s1 bulk secure failed: %s", _ex)
            _failed += 1
        secure_line = (
          f"{P_2FA} <b>Security:</b> {_killed_total} other session(s) terminated"
          + (" · bot sessions terminated" if _mode == "all" else "")
          + (f" · {_failed} pending" if _failed else "") + "\n")
      msg = (
        f"{P_YES} {P_PARTY} <b>{_bold('Bulk Purchase Complete!')}</b>\n"
        f"────────────────\n\n"
        f"{country_flag_html(code, cname)} <b>Country:</b> {html.escape(cname)}\n"
        f"{P_PKG} <b>Delivered:</b> {len(created)} of {qty}\n"
        f"{P_MONEY} <b>Total Paid:</b> ₹{total_paid}\n"
        f"{P_CARD} <b>Balance Left:</b> ₹{new_balance}\n"
        + secure_line +
        f"\n{lines}\n\n"
        f"{P_ASST} The latest login code of each account is sent here automatically — request the code in Telegram and it will arrive."
      )
      _res = await e_edit_or_send(event, custom_emoji_text(msg), [
        [Button.inline("My Orders", "cb_orders")],
        [Button.inline("Back", "srv1_countries")]])
      if _mode != "all":
        for c in created:
          try:
            await _send_s1_session_file(uid, c["row_id"])
          except Exception as _ex:
            logger.warning("s1 bulk session file failed: %s", _ex)
      # Latest login code of every delivered account is sent automatically (and every newer one).
      for c in created:
        try:
          _spawn_bg(_s1_auto_delivery_watch(uid, c["row_id"]))
        except Exception as _ex:
          logger.warning("s1 bulk code watcher failed: %s", _ex)
      return _res

    end = (final or {}).get("end") or {}
    message = str(end.get("message") or "No accounts could be bought.")
    msg = (
      f"{P_NO} <b>Bulk Purchase Failed</b>\n\n"
      f"{P_WARN} {html.escape(message)}\n\n"
      f"{P_CARD} You were not charged."
    )
    return await e_edit_or_send(event, custom_emoji_text(msg), [
      [Button.inline("Try Again", f"srv1_bulk|{code}")],
      [Button.inline("Back", "srv1_countries")]])


# ---- Filters panel -----------------------------------------------------------
async def server1_filters_menu(event):
  uid = event.sender_id
  f = _s1_filters(uid)
  active = _s1_filters_active(f)
  title = "Filters Active" if active else "Filters Default"
  msg = (
    f"{P_GEAR} <b>{title}</b>\n"
    f"────────────────\n\n"
    f"{_s1_filter_summary(f)}\n\n"
    f"<i>Tap a filter to change it. Filters apply instantly when browsing.</i>"
  )
  btns = [
    [Button.inline(f"Spam : {_s1_filter_value_label('spam', f.get('spam'))}", "srv1_fch|spam"),
     Button.inline(f"Premium : {_s1_filter_value_label('premium', f.get('premium'))}", "srv1_fch|premium")],
    [Button.inline(f"Origin : {_s1_filter_value_label('origin', f.get('origin'))}", "srv1_fch|origin"),
     Button.inline(f"Email : {_s1_filter_value_label('email', f.get('email'))}", "srv1_fch|email")],
    [Button.inline("Search Keyword", "srv1_fsearch|")],
    [Button.inline("Reset Filters", "srv1_freset")],
    [Button.inline("Back", "srv1_countries")],
  ]
  return await e_edit_or_send(event, custom_emoji_text(msg), btns)


async def server1_filter_choice(event, key):
  uid = event.sender_id
  f = _s1_filters(uid)
  key = str(key or "").strip().lower()
  options = {
    "spam": [("Any", "any"), ("Spam Free", "free"), ("Spam Blocked", "blocked"),
             ("Temporary Spam", "temp")],
    "premium": [("Any", "any"), ("Premium Only", "only")],
    "origin": [("Any", "any"), ("Phishing", "phishing"), ("Resale", "resale"),
               ("Mixed", "mixed"), ("Fresh", "fresh")],
    "email": [("Any", "any"), ("Required", "required")],
  }.get(key)
  if not options:
    return await safe_callback_answer(event, "Unknown filter.", alert=True)

  title = {"spam": "SPAM FILTER", "premium": "PREMIUM FILTER",
           "origin": "ORIGIN FILTER", "email": "EMAIL FILTER"}[key]
  msg = (
    f"{P_ASST} <b>{title}</b>\n"
    f"Current: {_s1_filter_value_label(key, f.get(key))}\n\n"
    f"<i>Pick a value below.</i>"
  )
  btns, row = [], []
  for label, value in options:
    _sel = _s1_norm_value(key, f.get(key)) == value
    row.append(Button.inline(label, f"srv1_fset|{key}|{value}",
                             icon_custom_emoji_id=(_ICON_OK if _sel else None)))
    if len(row) == 2:
      btns.append(row)
      row = []
  if row:
    btns.append(row)
  btns.append([Button.inline("Back", "srv1_filters")])
  return await e_edit_or_send(event, custom_emoji_text(msg), btns)


async def server1_filter_set(event, key, value):
  uid = event.sender_id
  key = str(key or "").strip().lower()
  value = _s1_norm_value(key, value)
  f = _s1_filters(uid)
  if key not in S1_FILTER_DEFAULTS or key in ("search", "sort"):
    return await safe_callback_answer(event, "Unknown filter.", alert=True)
  f[key] = value
  await safe_callback_answer(event, f"{key.title()} setting updated")
  return await server1_filters_menu(event)


async def server1_filter_reset(event):
  uid = event.sender_id
  _cat = str((S1_FILTERS.get(uid) or {}).get("cat") or "")
  S1_FILTERS[uid] = dict(S1_FILTER_DEFAULTS)
  if _cat:
    _s1_set_category(S1_FILTERS[uid], _cat)
  await safe_callback_answer(event, "Filters reset")
  return await server1_filters_menu(event)


async def server1_filter_search(event, country_code=""):
  uid = event.sender_id
  S1_SEARCH_STATE[uid] = {"kind": "keyword", "cc": str(country_code or "").strip().upper()}
  msg = (
    f"{P_ASST} <b>SEARCH KEYWORD</b>\n"
    f"────────────────\n\n"
    f"Type a keyword to filter accounts (origin, account id, date, etc.).\n"
    f"Send <code>/cancel</code> to abort."
  )
  return await e_edit_or_send(event, custom_emoji_text(msg),
                              [[Button.inline("Back", "srv1_filters")]])


# ---- Country search ----------------------------------------------------------
async def server1_country_search_prompt(event):
  uid = event.sender_id
  S1_SEARCH_STATE[uid] = {"kind": "country", "cc": ""}
  msg = (
    f"{P_ASST} <b>COUNTRY SEARCH</b>\n"
    f"────────────────\n\n"
    f"Type a country to browse its accounts:\n"
    f"<i>India or IN or +91</i>\n\n"
    f"Send <code>/cancel</code> to abort."
  )
  return await e_edit_or_send(event, custom_emoji_text(msg),
                              [[Button.inline("Back", "srv1_countries")]])


async def _search_status_send(event, stage="Searching..."):
  """Instant progress message while a search runs (edited into the result afterwards)."""
  try:
    icon = P_ASST if stage.startswith("Search") else P_WAIT
    return await event.respond(custom_emoji_text(f"{icon} <b>{_bold(stage)}</b>"), parse_mode='html')
  except Exception:
    return None


async def _search_status_set(msg, stage):
  if msg is None:
    return
  try:
    await msg.edit(custom_emoji_text(f"{P_WAIT} <b>{_bold(stage)}</b>"), parse_mode='html')
  except Exception:
    pass


async def _search_status_finish(event, msg, text, buttons):
  """Turn the progress message into the final result (or send it fresh if that fails)."""
  if msg is not None:
    try:
      return await msg.edit(text, buttons=buttons, parse_mode='html')
    except Exception:
      pass
  return await event.respond(text, buttons=buttons, parse_mode='html')


async def server1_country_search_results(event, query):
  query = str(query or "").strip()
  status = await _search_status_send(event, "Searching...")
  data = await asyncio.to_thread(fetch_s2_countries, False)
  if isinstance(data, dict):
    return await _search_status_finish(event, status, custom_emoji_text(
      f"{P_NO} Could not load countries right now."),
      [[Button.inline("Search Again", "srv1_csearch")], [Button.inline("Back", "srv1_countries")]])

  hits = _country_search_hits(data, query)
  if status is not None:
    await asyncio.sleep(0.35)
    await _search_status_set(status, "Loading...")
  if len(hits) == 1:
    try:
      return await server1_country_detail(event, hits[0].get("code"), 1)
    finally:
      if status is not None:
        try: await status.delete()
        except Exception: pass
  if hits:
    rows = []
    for c in hits[:12]:
      rows.append([Button.inline(
        f"{clean_country_name(c.get('name') or c.get('code'))} \u2022 \u20b9{server_sell_price(c.get('price') or 0)} \u2022 {c.get('stock', 0)}",
        f"srv1_c|{c.get('code')}",
        icon_custom_emoji_id=country_flag_icon_id(c.get("code"), c.get("name")))])
    rows.append([Button.inline("Search Again", "srv1_csearch")])
    rows.append([Button.inline("Back", "srv1_countries")])
    return await _search_status_finish(event, status, custom_emoji_text(
      f"{P_ASST} <b>COUNTRY SEARCH</b>\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n"
      f"Tap a country:"), rows)

  msg = (
    f"{P_ASST} <b>COUNTRY SEARCH</b>\n"
    f"────────────────\n\n"
    f"{P_WARN} No country found for <b>{html.escape(query)}</b>\n"
    f"Try: India - IN - +91 - 91"
  )
  return await _search_status_finish(event, status, custom_emoji_text(msg), [
    [Button.inline("Search Again", "srv1_csearch")],
    [Button.inline("Back", "srv1_countries")]])


# ---- Orders / OTP / session --------------------------------------------------
async def server1_order_detail(event, order_id, poll=False):
  uid = event.sender_id
  row = cur.execute(
    "SELECT user_id, country_name, number, price, status, code, password, country_code, "
    "account_no, charged FROM s2_orders WHERE order_id=?", (order_id,)).fetchone()
  if not row:
    return await safe_callback_answer(event, "Order not found.", alert=True)
  (owner_id, country_name, number, price, status, code, password,
   country_code, account_no, charged) = row
  code = _clean_otp(code)
  if int(owner_id) != int(uid) and not is_admin(uid):
    return await safe_callback_answer(event, "This order belongs to another user.", alert=True)

  if poll:
    if account_no:
      res = await _s1_get_code(order_id, account_no, deep=True)
      if res.get("ok"):
        new_code = str(res.get("code") or code or "")
        if new_code:
          code = new_code
          cur.execute("UPDATE s2_orders SET code=? WHERE order_id=?",
                      (code, order_id))
          db.commit()
          _s1_mark_completed(order_id)
        else:
          return await safe_callback_answer(
            event, "No code yet. Request the login code in Telegram, then tap Check Again.",
            alert=True)
      else:
        err = str(res.get("error") or "")
        if err == "no_code_yet":
          _live_tag = "\u2705 Session is LIVE. " if res.get("live") == "live" else ""
          return await safe_callback_answer(
            event, _live_tag + "No code yet. Open Telegram, request the login code, then tap Check Again.",
            alert=True)
        if err == "session_closed":
          return await safe_callback_answer(
            event, "This account's session was closed. No code is possible.", alert=True)
        if err == "session_dead":
          return await safe_callback_answer(
            event, "\u274c Session is NOT live (account logged out or banned). "
                   "Please contact support with your Order ID.", alert=True)
        if err == "session_terminated":
          return await safe_callback_answer(
            event, "Bot session was terminated, so the code can't be read here. "
                   "Log in with your number and the latest Telegram code.", alert=True)
        if err in ("session_invalid", "check_failed"):
          return await safe_callback_answer(
            event, "Could not verify the session status right now. Please try again in a minute.",
            alert=True)
        if err == "rate_limited":
          return await safe_callback_answer(
            event, "Too many code requests. Please wait 60 seconds.", alert=True)
        return await safe_callback_answer(event, _api_error_text(res), alert=True)
    elif str(status or "").lower() in ("processing", "queued", "running"):
      final = await asyncio.to_thread(wait_nobelots_order, order_id, 30)
      if isinstance(final, dict) and final.get("accounts"):
        _s1_finalize_purchase(uid, order_id, final, country_code, country_name, price)
      elif isinstance(final, dict) and str(final.get("status") or "").lower() in FINAL_ORDER_STATUSES:
        cur.execute("UPDATE s2_orders SET status=? WHERE order_id=?",
                    (str(final.get("status")), order_id))
        db.commit()
      row = cur.execute(
        "SELECT user_id, country_name, number, price, status, code, password, country_code, "
        "account_no, charged FROM s2_orders WHERE order_id=?", (order_id,)).fetchone()
      (owner_id, country_name, number, price, status, code, password,
       country_code, account_no, charged) = row

  if code:
    # ---- Handover: the buyer has the login code, so the bot's own session
    # is no longer needed. Terminate every remaining session once.
    secure_note = ""
    if S1_AUTO_TERMINATE and account_no and _s1_secure_mode() != "off":
      try:
        _sec_row = cur.execute(
          "SELECT secured FROM s2_orders WHERE order_id=?", (order_id,)).fetchone()
        _already = int((_sec_row[0] if _sec_row else 0) or 0)
      except Exception:
        _already = 0
      if _already < 2:
        try:
          _ok, _killed, _note = await _s1_secure_order(order_id, include_self=True)
          if _ok:
            secure_note = (
              f"{P_2FA} <b>Security:</b> {_killed} other session(s) terminated "
              f"\u00b7 bot session terminated \u2705\n")
          else:
            secure_note = (
              f"{P_WARN} <b>Security:</b> cleanup pending "
              f"(<code>{html.escape(str(_note))}</code>)\n")
        except Exception as _ex:
          logger.warning("s1 post-code secure failed: %s", _ex)
      else:
        secure_note = f"{P_2FA} <b>Security:</b> Account already clean \u2705\n"

    msg = (
      f"{P_YES} {P_PARTY} <b>{_bold('Login Code Received!')}</b>\n"
      f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n"
      f"{P_PHONE} <b>Number:</b> <code>{html.escape(str(number or 'Pending'))}</code>\n"
      f"{P_OTP} <b>Code:</b> <code>{html.escape(_otp_gap(code))}</code>\n"
    )
    msg += f"{P_2FA} <b>2FA:</b> <code>{html.escape(_s1_2fa_text(password, order_id))}</code>\n"
    msg += (
      f"\n{country_flag_html(country_code, country_name)} <b>Country:</b> {html.escape(str(country_name))}\n"
      f"{P_MONEY} <b>Paid:</b> \u20b9{price}\n"
      f"{P_ID} <b>Bot Order ID:</b> <code>{_global_order_id_for('server1', order_id) or '-'}</code>\n"
      + secure_note +
      f"\n{P_WARN} <i>Log in quickly \u2014 the code expires. Never share this code.</i>"
    )
    btns = [[Button.inline("Check Again", f"srv1_code|{order_id}")]]
    if account_no:
      btns.append([Button.inline("Session String", f"srv1_ses|{order_id}")])
      btns.append([Button.inline("Terminate Other Sessions", f"srv1_secc|o|{order_id}")])
      btns.append([Button.inline("Terminate Bot Session", f"srv1_secc|b|{order_id}")])
    btns += [
      [Button.inline("My Orders", "cb_orders")],
      [Button.inline("Back to Store", "store_servers")],
    ]
    return await e_edit_or_send(event, custom_emoji_text(msg), btns)

  status_txt = _s1_status_text(status)
  msg = (
    f"{P_WAIT} <b>{_bold('Order Details')}</b>\n"
    f"────────────────\n\n"
    f"{P_PHONE} <b>Number:</b> <code>{html.escape(str(number or 'Pending'))}</code>\n"
    f"{country_flag_html(country_code, country_name)} <b>Country:</b> {html.escape(str(country_name))}\n"
    f"{P_MONEY} <b>Paid:</b> ₹{price}\n"
    f"{P_ID} <b>Bot Order ID:</b> <code>{_global_order_id_for('server1', order_id) or '-'}</code>\n"
    f"{P_STATS} <b>Status:</b> {status_txt}\n"
  )
  if account_no:
    msg += f"{P_ID} <b>Account No:</b> <code>{html.escape(str(account_no))}</code>\n"
  msg += (
    f"\n{P_ASST} Open Telegram, enter this number, request the code, then tap "
    f"<b>Check Code</b>."
  )
  btns = [[Button.inline("Check Code", f"srv1_code|{order_id}")]]
  if account_no:
    btns.append([Button.inline("Session String", f"srv1_ses|{order_id}")])
    btns.append([Button.inline("Terminate Other Sessions", f"srv1_secc|o|{order_id}")])
    btns.append([Button.inline("Terminate Bot Session", f"srv1_secc|b|{order_id}")])
  btns += [
    [Button.inline("My Orders", "cb_orders")],
    [Button.inline("Back to Store", "store_servers")],
  ]
  return await e_edit_or_send(event, custom_emoji_text(msg), btns)


async def server1_send_session(event, order_id):
  """Send the Telethon StringSession for a bought account."""
  uid = event.sender_id
  row = cur.execute(
    "SELECT user_id, account_no, number FROM s2_orders WHERE order_id=?", (order_id,)).fetchone()
  if not row:
    return await safe_callback_answer(event, "Order not found.", alert=True)
  owner_id, account_no, number = row
  if int(owner_id) != int(uid) and not is_admin(uid):
    return await safe_callback_answer(event, "This order belongs to another user.", alert=True)
  if not account_no:
    return await safe_callback_answer(event, "Session is not ready yet.", alert=True)

  # If the account was already secured, its session was logged out on purpose.
  try:
    sec_row = cur.execute(
      "SELECT secured FROM s2_orders WHERE order_id=?", (order_id,)).fetchone()
    secured_flag = int((sec_row[0] if sec_row else 0) or 0)
  except Exception:
    secured_flag = 0
  if secured_flag >= 2:
    msg = (
      f"{P_2FA} <b>Session Already Terminated</b>\n"
      f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n"
      f"{P_PHONE} <b>Number:</b> <code>{html.escape(str(number or '-'))}</code>\n\n"
      f"{P_ASST} This account was secured: every other session and the bot "
      f"session were terminated, so the old session string no longer works.\n\n"
      f"{P_WARN} Log in with the number and the login code instead \u2014 the "
      f"account is completely clean and only you can access it."
    )
    return await e_edit_or_send(
      event, custom_emoji_text(msg),
      [[Button.inline("Check Code", f"srv1_code|{order_id}")],
       [Button.inline("My Orders", "cb_orders")]])

  await safe_callback_answer(event, "Fetching session...", alert=False)
  res = await _s1_session_res(order_id, account_no)
  if not res.get("ok"):
    return await safe_callback_answer(event, _api_error_text(res), alert=True)
  session = str(res.get("string_session") or res.get("session") or res.get("string") or "").strip()
  if not session:
    return await safe_callback_answer(event, "Session is not available yet.", alert=True)

  msg = (
    f"{P_KEY} <b>Telethon StringSession</b>\n"
    f"────────────────\n\n"
    f"{P_PHONE} <b>Number:</b> <code>{html.escape(str(number or '-'))}</code>\n"
    f"{P_ID} <b>DC:</b> {html.escape(str(res.get('dc_id') or '-'))}\n\n"
    f"<code>{html.escape(session)}</code>\n\n"
    f"{P_WARN} <i>Keep this secret. Anyone with it can control the account.</i>\n\n"
    f"{P_ASST} <code>TelegramClient(StringSession(session), API_ID, API_HASH)</code>"
  )
  return await event.respond(custom_emoji_text(msg))


async def server1_orders_menu(event):
  uid = event.sender_id
  rows = cur.execute(
    "SELECT order_id, country_name, number, price, status, code, country_code, account_no "
    "FROM s2_orders WHERE user_id=? ORDER BY created_date DESC LIMIT 10", (uid,)).fetchall()
  if not rows:
    msg = (
      f"{P_STORE} <b>My Numbers</b>\n"
      f"────────────────\n\n"
      f"{_s1_wallet_card(uid)}\n\n"
      f"{P_WARN} You have not purchased any numbers yet."
    )
    btns = [
      [Button.inline("Buy a Number", "srv1_accounts")],
      [Button.inline("Back to Store", "store_servers")],
    ]
    return await e_edit_or_send(event, custom_emoji_text(msg), btns)

  btns = []
  lines = []
  for order_id, country_name, number, price, status, code, country_code, account_no in rows:
    status_txt = "Code Ready" if code else _s1_status_text(status)
    shown = number or f"Order {str(order_id)[:10]}"
    label = f"{shown} — {status_txt}"
    if len(label) > 48:
      label = label[:45] + "..."
    btns.append([Button.inline(label, f"srv1_ord|{order_id}")])
    lines.append(
      f"{country_flag_html(country_code, country_name)} <b>{html.escape(clean_country_name(country_name) or 'Number')}</b> "
      f"— <code>{html.escape(str(shown))}</code> — <i>{status_txt}</i>"
    )
  btns.append([Button.inline("Buy a Number", "srv1_accounts")])
  btns.append([Button.inline("Back to Store", "store_servers")])

  msg = (
    f"{P_STORE} <b>My Numbers</b>\n"
    f"────────────────\n\n"
    f"{_s1_wallet_card(uid)}\n\n"
    f"{P_PKG} <b>Recent Orders:</b> {len(rows)}\n\n"
    f"{chr(10).join(lines)}\n\n"
    f"{P_ASST} Tap an order to see the number, login code and session."
  )
  return await e_edit_or_send(event, custom_emoji_text(msg), btns)




async def log_s2_sale(uid, country_name, order_id, number, price, country_code="", global_order_id=None):
  _spawn_bg(_check_api_balance_now(1))
  try:
    t = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = (
      f"{P_TG} {P_ROCKET} <b>NEW SERVER 1 ACCOUNT SALE</b> {P_PARTY}\n\n"
      f"{P_ACC} Buyer: <b>Hidden</b>\n"
      f"{country_flag_html(country_code, country_name)} Country: {html.escape(str(country_name))}\n"
      f"{P_PHONE} Number: {_mask_phone(number)}\n"
      + (f"{P_ID} Bot Order ID: <code>{html.escape(str(global_order_id))}</code>\n" if global_order_id else "") +
      f"{P_MONEY} Price: {P_INR}{price}\n"
      f"{P_TIME} Time: {t}"
    )
    await _send_selling_log(msg)
  except Exception as ex:
    logger.error(f"Server1 Sale Log Err: {ex}", exc_info=True)
  try:
    await notify_admins(
      f"{P_TG} {P_ROCKET} <b>SERVER 1 ACCOUNT PURCHASED</b> {P_PARTY}\n\n"
      f"{P_ACC} User: <code>{uid}</code> ({html.escape(await _user_label(uid))})\n"
      f"{country_flag_html(country_code, country_name)} Country: {html.escape(str(country_name))}\n"
      f"{P_PHONE} Number: <code>{html.escape(str(number))}</code>\n"
      f"{P_MONEY} Paid: {P_INR}{price}\n"
      f"{P_ID} Bot Order ID: <code>{html.escape(str(global_order_id or '-'))}</code>\n"
      f"{P_DOC} Batch ID: <code>{html.escape(str(order_id))}</code>\n"
      f"{P_TIME} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
  except Exception as ex:
    logger.error(f"Server1 admin notify err: {ex}")


# ================= DIGITAL SHOP =================
async def digital_shop_menu(event):
  """Open Shop reliably from any callback message type."""
  try:
    rows = cur.execute(
      "SELECT id, name, description, price, photo_path, file_path FROM digital_products WHERE active=1 ORDER BY id DESC"
    ).fetchall()
  except Exception as ex:
    logger.error(f"Shop DB Error: {ex}", exc_info=True)
    msg = custom_emoji_text(f"{P_NO} <b>Shop</b>\n\nUnable to load products right now.")
    btns = [[Button.inline("Back to Store", "store_servers")]]
    try:
      return await e_edit_or_send(event, msg, btns)
    except Exception:
      return await bot.send_message(event.chat_id, msg, buttons=btns, parse_mode='html')

  if not rows:
    msg = custom_emoji_text(f"{P_STORE} <b>Shop</b>\n\nNo digital products are available right now.")
    btns = [[Button.inline("Back to Store", "store_servers")]]
    return await e_edit_or_send(event, msg, btns)

  btns = []
  for pid, name, desc, price, preview_path, file_path in rows:
    # Telegram callback data is limited; keep the ID as the only payload.
    label = str(name or f"Product #{pid}")
    if len(label) > 42:
      label = label[:39] + "..."
    btns.append([Button.inline(f"{label} - ₹{price}", f"digital_product|{pid}")])
  btns.append([Button.inline("Back to Store", "store_servers")])
  msg = custom_emoji_text(f"{P_STORE} <b>Shop</b>\n\nSelect a product:")
  return await e_edit_or_send(event, msg, btns)


# Photo/file messages sent by the Shop. Editing such a message with plain text
# keeps the photo on screen forever (Telegram cannot drop media on edit), so any
# screen opened from them is sent as a NEW message instead.
_SHOP_PREVIEW_MSGS = set()   # preview photo: delete it when the user navigates away
_SHOP_DELIVERED_MSGS = set() # delivered product file: KEEP it, open the next screen below


def _remember_msg(bucket, msg):
  try:
    bucket.add((int(msg.chat_id), int(msg.id)))
    if len(bucket) > 5000:
      bucket.clear()
  except Exception:
    pass


# ---- Welcome media stays only on the main menu ----
# Telegram cannot turn a photo/video message into a plain text screen with
# edit(): the photo stays and only the caption changes. So every callback edit
# on a photo/video message is replaced by a fresh text message. The main menu
# itself deletes and resends the welcome media, so it is not affected.
from telethon.tl.types import MessageMediaPhoto as _MMPhoto, MessageMediaDocument as _MMDoc
_cq_orig_edit = events.CallbackQuery.Event.edit


async def _cq_edit_media_safe(self, *args, **kwargs):
  msg_obj = getattr(self, "_message", None)
  media = getattr(msg_obj, "media", None) if msg_obj is not None else None
  has_visual_media = isinstance(media, (_MMPhoto, _MMDoc))
  if not has_visual_media or "file" in kwargs:
    return await _cq_orig_edit(self, *args, **kwargs)
  text = args[0] if args else kwargs.pop("text", "")
  send_kwargs = {"parse_mode": kwargs.get("parse_mode", "html")}
  for _k in ("buttons", "link_preview"):
    if _k in kwargs:
      send_kwargs[_k] = kwargs[_k]
  try:
    await self.delete()
  except Exception as ex:
    logger.debug(f"Media message delete before text screen failed: {ex}")
  return await bot.send_message(self.chat_id, text, **send_kwargs)


events.CallbackQuery.Event.edit = _cq_edit_media_safe


async def e_edit_or_send(event, msg, buttons):
  """Edit a callback message when possible; otherwise send a fresh message."""
  if not isinstance(event, events.CallbackQuery.Event):
    return await event.respond(msg, buttons=buttons, parse_mode='html')
  try:
    if getattr(getattr(event, '_message', None), 'media', None):
      try:
        await event.delete()
      except Exception as ex:
        logger.warning(f"Callback media delete failed: {ex}")
      return await bot.send_message(event.chat_id, msg, buttons=buttons, parse_mode='html')
    try:
      return await event.edit(msg, buttons=buttons, parse_mode='html')
    except MessageNotModifiedError:
      return
    except Exception as ex:
      logger.warning(f"Callback edit failed, using send fallback: {ex}")
      return await bot.send_message(event.chat_id, msg, buttons=buttons, parse_mode='html')
  except Exception as ex:
    logger.error(f"Callback edit/send fallback failed: {ex}", exc_info=True)
    return await bot.send_message(event.chat_id, msg, buttons=buttons, parse_mode='html')

_ADMIN_HTML_TAG = re.compile(
  r'</?(?:b|i|u|s|em|strong|code|pre|blockquote|tg-spoiler)>'
  r'|<tg-emoji emoji-id="\d+">|</tg-emoji>'
  r'|<a href="[^"<>]*">|</a>', re.I)


def _admin_html(text):
  """Render admin-typed text that is ALREADY Telegram-HTML (the bot runs with
  parse_mode='html', so `event.text` returns <tg-emoji>/<b>/<i> markup).

  Escaping it again made premium emojis show up as raw '<tg-emoji ...>' text.
  Allowed formatting tags are kept; any other '<' / '&' is escaped so a stray
  character can never break the message.
  """
  text = str(text or '')
  out, last = [], 0
  for m in _ADMIN_HTML_TAG.finditer(text):
    out.append(html.escape(html.unescape(text[last:m.start()]), quote=False))
    out.append(m.group(0))
    last = m.end()
  out.append(html.escape(html.unescape(text[last:]), quote=False))
  return ''.join(out)


async def digital_product_view(event, pid):
  try:
    pid = int(pid)
    row = cur.execute(
      "SELECT id,name,description,price,photo_path,file_path FROM digital_products WHERE id=? AND active=1",
      (pid,)
    ).fetchone()
    if not row:
      return await safe_callback_answer(event, "Product not found.", alert=True)

    _, name, desc, price, preview_path, file_path = row
    path = str(preview_path or '').strip()
    name = str(name or f"Product #{pid}")
    desc = str(desc or "").strip()
    path = str(path or "").strip()
    price = int(price)
    msg = f"<b>{html.escape(name)}</b>\n\n"
    if desc:
      msg += f"<b>Description:</b>\n{_admin_html(desc)}\n\n"
    msg += f"<b>Price:</b> ₹{price}"
    btns = [
      [Button.inline(f"Buy Now - ₹{price}", str(f"digital_buy|{pid}"))],
      [Button.inline("Back to Shop", "digital_shop")]
    ]
    if path and os.path.isfile(path):
      try:
        await event.delete()
        sent = await bot.send_file(
          event.chat_id, path, caption=custom_emoji_text(msg),
          buttons=btns, parse_mode='html'
        )
        _remember_msg(_SHOP_PREVIEW_MSGS, sent)
        return sent
      except Exception as ex:
        logger.warning(f"Digital product media send failed: {ex}", exc_info=True)
    return await e_edit_or_send(event, custom_emoji_text(msg), btns)
  except Exception as ex:
    logger.error(f"Digital Product View Error: {ex}", exc_info=True)
    try:
      await bot.send_message(
        event.chat_id,
        "Product could not be opened right now. Please try again.",
        buttons=[[Button.inline("Back to Shop", "digital_shop")]],
        parse_mode='html'
      )
    except Exception:
      pass


async def _digital_buy_old(event, pid):
  uid = int(event.sender_id)
  charged = False
  price = 0
  try:
    pid = int(pid)
    row = cur.execute(
      "SELECT id,name,description,price,photo_path,file_path FROM digital_products WHERE id=? AND active=1",
      (pid,)
    ).fetchone()
    if not row:
      return await safe_callback_answer(event, "Product unavailable.", alert=True)

    _, name, desc, db_price, preview_path, db_file_path = row
    name = str(name or f"Product #{pid}")
    desc = str(desc or "")
    price = int(db_price)
    # Existing products used photo_path as the delivered file; keep backward compatibility.
    text_only = str(db_file_path or '').strip() == '__none__'
    path = '' if text_only else str(db_file_path or preview_path or '').strip()

    if price <= 0:
      return await safe_callback_answer(event, "Invalid product price. Please contact admin.", alert=True)
    if not text_only and (not path or not os.path.isfile(path)):
      logger.error(f"Digital product file missing: pid={pid}, path={path!r}")
      return await safe_callback_answer(event, "Product file is unavailable. Please contact admin.", alert=True)

    async with get_user_lock(uid):
      balrow = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
      bal = int(balrow[0]) if balrow and balrow[0] is not None else 0
      if bal < price:
        return await safe_callback_answer(event, f"Insufficient balance. Need ₹{price}.", alert=True)
      cur.execute(
        "UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?",
        (price, uid, price)
      )
      if cur.rowcount != 1:
        db.rollback()
        return await safe_callback_answer(event, "Balance changed. Please try again.", alert=True)
      db.commit()
      charged = True

    msg = (
      f"<b>Digital Product Purchased</b>\n\n"
      f"<b>{html.escape(name)}</b>\n"
      f"Paid: ₹{price}\n\n"
      f"{_admin_html(desc) if desc else 'Please contact support to receive your product.'}"
    )
    buttons = [[Button.inline("Back to Shop", "digital_shop")]]

    try:
      try:
        await event.delete()
      except Exception:
        pass
      if text_only:
        await bot.send_message(uid, custom_emoji_text(msg), parse_mode='html', buttons=buttons)
      else:
        sent = await bot.send_file(
          uid, path, caption=custom_emoji_text(msg),
          parse_mode='html', buttons=buttons
        )
        _remember_msg(_SHOP_DELIVERED_MSGS, sent)
    except Exception as delivery_ex:
      logger.error(f"Digital delivery failed for pid={pid}, uid={uid}: {delivery_ex}", exc_info=True)
      if charged:
        try:
          async with get_user_lock(uid):
            cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (price, uid))
            db.commit()
          charged = False
        except Exception as refund_ex:
          logger.error(f"Digital purchase refund failed for uid={uid}: {refund_ex}", exc_info=True)
      return await bot.send_message(
        uid,
        "Purchase could not be delivered. Your balance has been refunded. Please try again later.",
        buttons=buttons, parse_mode='html'
      )

    try:
      await log_digital_sale(uid, name, price)
    except Exception as log_ex:
      logger.error(f"Digital sale log error: {log_ex}", exc_info=True)
  except Exception as ex:
    logger.error(f"Digital Buy Error: {ex}", exc_info=True)
    try:
      await bot.send_message(
        uid,
        "Digital purchase could not be completed. No balance was charged if delivery did not start.",
        buttons=[[Button.inline("Back to Shop", "digital_shop")]],
        parse_mode='html'
      )
    except Exception:
      pass

async def digital_shop_admin_menu(event):
  rows=cur.execute("SELECT id,name,price,active FROM digital_products ORDER BY id DESC").fetchall()
  msg=f"{P_STORE} <b>Manage Shop</b>\n\n"
  if not rows: msg += "No products added yet."
  else:
    for pid,name,price,active in rows:
      msg += f"<code>{pid}</code> - <b>{html.escape(name)}</b> - ₹{price} - {'ON' if active else 'OFF'}\n"
  btns=[[Button.inline("Add Product","adm_digital_add")],
     [Button.inline("Remove Product","adm_digital_remove")],
     [Button.inline("Back to Admin","adm_adminmain")]]
  await event.edit(custom_emoji_text(msg),buttons=btns)

# ================= REDEEM CODES =================
async def redeem_code_for_user(event, code):
  uid=event.sender_id; code=str(code).strip().upper()
  row=cur.execute("SELECT amount,max_users,used_count,active FROM redeem_codes WHERE code=?",(code,)).fetchone()
  if not row: return await safe_callback_answer(event,"Invalid redeem code.",alert=True)
  amount,max_users,used_count,active=row
  if not active or used_count>=max_users: return await safe_callback_answer(event,"This code is no longer available.",alert=True)
  claimed=cur.execute("SELECT 1 FROM redeem_claims WHERE code=? AND user_id=?",(code,uid)).fetchone()
  if claimed: return await safe_callback_answer(event,"You have already redeemed this code.",alert=True)
  async with get_user_lock(uid):
    cur.execute("INSERT INTO redeem_claims(code,user_id) VALUES(?,?)",(code,uid))
    if cur.rowcount != 1: return await safe_callback_answer(event,"You have already redeemed this code.",alert=True)
    cur.execute("UPDATE redeem_codes SET used_count=used_count+1 WHERE code=? AND active=1 AND used_count<?",(code,max_users))
    if cur.rowcount != 1:
      cur.execute("DELETE FROM redeem_claims WHERE code=? AND user_id=?",(code,uid)); db.commit()
      return await safe_callback_answer(event,"This code just reached its limit.",alert=True)
    update_balance(uid,amount); db.commit()
    _redeem_after_claim(code,uid,amount)
  await event.edit(custom_emoji_text(f"{P_YES} <b>Redeem Successful!</b>\n\nCode: <code>{html.escape(code)}</code>\nAmount Added: <b>₹{amount}</b>"),buttons=[[Button.inline("Back to Main","back_main")]])

# ================= SOCIAL MEDIA SERVICES (USER FLOW) =================
async def show_smm_categories(event):
  rows = cur.execute("SELECT id, name FROM smm_categories").fetchall()
  if not rows:
    msg = f"{P_WARN} <b>No social media service categories available right now.</b>"
    btns = [[Button.inline("Refill", "cb_refill")], [Button.inline("Back", "back_main")]]
    if isinstance(event, events.CallbackQuery.Event): return await event.edit(custom_emoji_text(msg), buttons=btns)
    else: return await event.respond(custom_emoji_text(msg), buttons=btns)

  msg = f"{P_FOLDER} <b>Select Category (Page 1/1):</b>"
  btns = []
  for cid, cname in rows:
    btns.append([Button.inline(f"{cname}", f"smm_cat|{cid}")])
  btns.append([Button.inline("Refill", "cb_refill")])  # always the last option
  btns.append([Button.inline("Back", "back_main")])

  if isinstance(event, events.CallbackQuery.Event): await event.edit(custom_emoji_text(msg), buttons=btns)
  else: await event.respond(custom_emoji_text(msg), buttons=btns)

async def show_smm_services_in_category(event, category_id):
  rows = cur.execute("SELECT service_id, name, rate, min, max FROM smm_services WHERE category_id=?", (category_id,)).fetchall()
  
  if not rows:
    msg = f"{P_WARN} <b>No services found in this category.</b>"
    btns = [[Button.inline("Back to Categories", "cb_smm_services")]]
    return await event.edit(custom_emoji_text(msg), buttons=btns)

  msg = f"{P_ASST} <b>Select Service (Page 1/1):</b>"
  btns = []
  for sid, sname, rate, smin, smax in rows:
    btns.append([Button.inline(f"{custom_emoji_text(str(sname))}", f"smm_srv|{sid}")])
  btns.append([Button.inline("Back to Categories", "cb_smm_services")])
  await event.edit(custom_emoji_text(msg), buttons=btns)

async def smm_service_detail_view(event, service_id):
  row = cur.execute("SELECT service_id, name, rate, min, max, description FROM smm_services WHERE service_id=?", (service_id,)).fetchone()
  if not row: return await safe_callback_answer(event, "Service not found.", alert=True)
  sid, name, rate, smin, smax, desc = row
  uid = event.sender_id

  # The bot now waits for the link right away (no extra "Buy Service" button).
  smm_order_state[uid] = {'service_id': sid, 'name': name, 'rate': rate,
                          'min': smin, 'max': smax, 'step': 'wait_link'}

  msg = (f"{P_ID} <b>Service ID: {sid}</b>\n"
      f"{P_TITLE} <b>Title:</b> {html.escape(name)}\n\n"
      f"{P_DESC} <b>Description:</b>\n{html.escape(desc if desc else 'No description available')}\n\n"
      f"{P_RATE} <b>Rate: ₹{rate} Per 1000</b>\n"
      f"{P_MIN} <b>Min: {smin}</b>\n"
      f"{P_MAX} <b>Max :{smax}</b>\n\n"
      f"{P_ASST} <b>Send Link:</b>")

  btns = [[Button.inline("Cancel", "smm_cancel")]]
  await event.edit(custom_emoji_text(msg), buttons=btns)

async def show_server_countries(event, server_type, page=1):
  limit = 10
  offset = (page - 1) * limit
  
  total_row = cur.execute("SELECT COUNT(DISTINCT country_name) FROM stock WHERE available=1").fetchone()
  total = total_row[0] if total_row else 0
  rows = cur.execute("SELECT country_name, COUNT(*), MIN(price) FROM stock WHERE available=1 GROUP BY country_name ORDER BY country_name ASC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    
  if not rows and page == 1: 
    err_msg = f"{P_NO} <b>Stock is Empty right now. Check back later!</b>"
    btns = [[Button.inline("Back to Store", "store_servers")]]
    if isinstance(event, events.CallbackQuery.Event): return await event.edit(custom_emoji_text(err_msg), buttons=btns)
    else: return await event.respond(custom_emoji_text(err_msg), buttons=btns)
  
  rate = get_usdt_rate()
  msg = (
    f"{P_CART} {P_FIRE} <b>SELECT PRODUCT (ACCOUNTS)</b> {P_STAR}\n"
    f"────────────────\n\n"
    f"{P_USDT} <b>Rate: 1 USDT = ₹{rate}</b>\n"
  )
  
  for (c_name, count, min_p) in rows:
    usd_p = to_usd(min_p)
    flag = country_flag_html(None, c_name)
    msg += f"- {flag} {c_name}: ${usd_p} (₹{min_p}) - Stock: {count} {P_YES}\n"
    
  msg += f"\n<i>Select an item to view details:</i> {P_ASST}"
  
  btns = []
  for (c_name, count, min_p) in rows:
    usd_p = to_usd(min_p)
    btns.append([Button.inline(f"{c_name} - ₹{min_p} (${usd_p})", f"s_country|{server_type}|{_country_token(c_name)}",
                               icon_custom_emoji_id=country_flag_icon_id(None, c_name))])

  nav = []
  if page > 1: nav.append(Button.inline("Prev", f"srv_pg|{server_type}|{page-1}"))
  if offset + limit < total: nav.append(Button.inline("Next", f"srv_pg|{server_type}|{page+1}"))
  if nav: btns.append(nav)
  btns.append([Button.inline("Back to Store", "store_servers")])
  
  if isinstance(event, events.CallbackQuery.Event): await event.edit(custom_emoji_text(msg), buttons=btns)
  else: await event.respond(custom_emoji_text(msg), buttons=btns)

async def show_country_details(event, server_type, country):
  rows = cur.execute("SELECT account_year, price, COUNT(*) FROM stock WHERE available=1 AND country_name LIKE ? GROUP BY account_year, price ORDER BY account_year DESC", (f"{country}%",)).fetchall()
  total_stock = sum([r[2] for r in rows]) if rows else 0
  
  msg = (
    f"{P_STAR} {P_FIRE} <b>Quality Account - {html.escape(country)}</b> {P_STAR}\n\n"
    f"- <b>Country:</b> {country_flag_html(None, country)} {html.escape(country)}\n"
    f"- <b>Available:</b> {total_stock} {P_YES}\n\n"
    f"<b>Stock by year:</b> {P_CAL}\n"
  )
  for (y, p, c) in rows:
    msg += f"- {country_flag_html(None, country)} {country} {y} – {c} × ₹{p} each {P_MONEY}\n"
    
  msg += (
    f"\n<i>Each account is charged at its year price (admin-configured).</i>\n"
    f"{P_WARN} <b>Use Telegraph for login.</b>\n"
    f"{P_NO} <b>Account freeze/ban risk is user responsibility.</b>"
  )
  
  btns = [
    [Button.inline(f"Buy Single", f"p_buy|single|{_country_token(country)}")],
    [Button.inline(f"Buy Bulk", f"p_buy|bulk|{_country_token(country)}")],
    [Button.inline(f"Choose Year", f"p_year|{_country_token(country)}")],
    [Button.inline("Back to Countries", f"srv|{server_type}")]
  ]
  await event.edit(custom_emoji_text(msg), buttons=btns)

async def show_years_for_country(event, country):
  rows = cur.execute("SELECT account_year, price, COUNT(*) FROM stock WHERE available=1 AND country_name LIKE ? GROUP BY account_year, price ORDER BY account_year DESC", (f"{country}%",)).fetchall()
  if not rows: return await safe_callback_answer(event, "Out of stock for this country.", alert=True)

  uid = event.sender_id
  disc_row = cur.execute("SELECT discount FROM users WHERE user_id=?", (uid,)).fetchone()
  discount = disc_row[0] if disc_row else 0

  msg = f"{P_CAL} {P_STAR} <b>Select Account Year</b>\n{P_GLOBE} Country: {country_flag_html(None, country)} <b>{html.escape(country)}</b>\n\n"
  btns = []
  
  for (y, p, c) in rows:
    disp_p = p if discount == 0 else int(p * (100 - discount) / 100)
    disc_text = f" (-{discount}%)" if discount > 0 else ""
    btns.append([Button.inline(f"{y} | ₹{disp_p}{disc_text} | Stock: {c}", f"by_yr|{_country_token(country)}|{y}|{p}")])

  btns.append([Button.inline("Back to Details", f"s_country|manual|{_country_token(country)}")])
  await event.edit(custom_emoji_text(msg), buttons=btns)

async def profile_handler(event, is_callback=False):
  uid = event.sender_id
  row = cur.execute("SELECT balance, total_deposited, joined_date FROM users WHERE user_id=?", (uid,)).fetchone()
  if not row: return
  
  bal, dep, joined = row
  o_row = cur.execute("SELECT COUNT(*), SUM(price) FROM orders WHERE user_id=?", (uid,)).fetchone()
  total_orders = o_row[0] if o_row else 0
  spent = o_row[1] if o_row and o_row[1] else 0
  
  try:
    sender = await event.get_sender()
    user_name = html.escape(sender.first_name) if sender and sender.first_name else "User"
  except:
    user_name = "User"
    
  date_str = joined[:10] if joined else "2026-05-25"

  msg = (
    f"{P_STAR} {P_CROWN} <b>{_bold('VIP ACCOUNT PROFILE')}</b> {P_STAR}\n\n"
    f"{P_ACC} <b>Account Holder:</b> <b>{user_name}</b> {P_FIRE}!!\n"
    f"{P_ID} <b>User ID:</b> <code>{uid}</code>\n"
    f"{P_CAL} <b>Member Since:</b> {date_str}\n"
    f"────────────────────────\n\n"
    f"{P_MONEY} <b>WALLET OVERVIEW</b>\n"
    f"├ <b>Available Balance:</b> ₹{bal:.2f} (${to_usd(bal):.2f})\n"
    f"├ <b>Total Deposited:</b> ₹{dep:.2f}\n"
    f"└ <b>Total Spent:</b> ₹{spent:.2f}\n\n"
    f"{P_STATS} <b>ACCOUNT ACTIVITY</b>\n"
    f"├ <b>Orders Completed:</b> {total_orders} {P_ROCKET}\n"
    f"├ <b>Verification:</b> Verified {P_YES}\n"
    f"└ <b>Terms of Service:</b> Accepted {P_YES}"
  )

  btns = [
    [Button.inline("Deposit Funds", "dep_menu_cb")],
    [Button.inline("My Orders", "cb_orders"), Button.inline("Payments History", "payments_history")],
    [Button.inline("Back to Main Menu", "back_main")]
  ]

  if is_callback:
    try: await event.edit(custom_emoji_text(msg), buttons=btns)
    except MessageNotModifiedError: pass
  else:
    await bot.send_message(event.chat_id, msg, buttons=btns)

ORDERS_PER_PAGE = 6


def _order_ts(value):
  """Normalise sqlite / ISO timestamps to 'YYYY-MM-DD HH:MM:SS' for sorting."""
  return str(value or "").replace("T", " ")[:19]


def collect_user_orders(uid):
  """Every order of a user (Telegram, Server 1, WhatsApp, SMM) newest first."""
  items = []
  try:
    for country, yr, price, phone, d in cur.execute(
        "SELECT country, year, price, phone, date FROM orders WHERE user_id=?", (uid,)).fetchall():
      items.append({"ts": _order_ts(d), "kind": "tg", "country": country, "year": yr,
                    "price": price, "phone": phone, "btn": None})
  except Exception as ex:
    logger.warning(f"orders tg: {ex}")
  try:
    for oid, cname, ccode, number, price, status, code, d in cur.execute(
        "SELECT order_id, country_name, country_code, number, price, status, code, created_date "
        "FROM s2_orders WHERE user_id=? AND charged=1", (uid,)).fetchall():
      items.append({"ts": _order_ts(d), "kind": "s1", "country": cname, "ccode": ccode,
                    "price": price, "phone": number, "status": ("Code Ready" if code else _s1_status_text(status)),
                    "btn": f"srv1_ord|{oid}"})
  except Exception as ex:
    logger.warning(f"orders s1: {ex}")
  try:
    for o in _s2wa_user_orders(uid, 200):
      st = o.get("status", "")
      label = {"DONE": "Complete", "CANCELLED": "Cancelled", "WAIT_CODE": "Waiting",
               "WAIT_RETRY": "Retry"}.get(st, st.title() if st else "-")
      items.append({"ts": _order_ts(o.get("created_at")), "kind": "wa", "country": o.get("country_name"),
                    "price": o.get("price_inr"), "phone": o.get("phone"), "status": label,
                    "code": o.get("code"),
                    "btn": (f"s2wa_code:{o['activation_id']}" if st in ("WAIT_CODE", "WAIT_RETRY") else None)})
  except Exception as ex:
    logger.warning(f"orders wa: {ex}")
  try:
    for boid, sname, qty, price, status, d in cur.execute(
        "SELECT o.bot_order_id, COALESCE(s.name, 'Service ' || o.service_id), o.quantity, o.total_price, o.status, o.date "
        "FROM smm_orders o LEFT JOIN smm_services s ON s.service_id=o.service_id WHERE o.user_id=?", (uid,)).fetchall():
      items.append({"ts": _order_ts(d), "kind": "smm", "service": sname, "qty": qty,
                    "price": price, "boid": boid, "status": status, "btn": None})
  except Exception as ex:
    logger.warning(f"orders smm: {ex}")
  items.sort(key=lambda x: x["ts"], reverse=True)
  return items


async def _orders_history_handler_old(event, is_callback=False, page=1):
  """ONE 'My Orders' screen: Telegram, WhatsApp and SMM orders together."""
  uid = event.sender_id
  items = collect_user_orders(uid)
  counts = {k: sum(1 for i in items if i["kind"] == k) for k in ("tg", "s1", "wa", "smm")}

  if not items:
    msg = f"{P_DOC} <b>{_bold('My Orders')}</b>\n────────────────\n\n{P_WARN} <b>You don't have any orders yet.</b>"
    btns = [[Button.inline("Store", "cb_store")], [Button.inline("Back to Main", "back_main")]]
  else:
    total = len(items)
    pages = max(1, (total + ORDERS_PER_PAGE - 1) // ORDERS_PER_PAGE)
    page = max(1, min(int(page or 1), pages))
    chunk = items[(page - 1) * ORDERS_PER_PAGE: page * ORDERS_PER_PAGE]
    msg = (
      f"{P_DOC} {P_ROCKET} <b>{_bold('My Orders')}</b>\n"
      f"────────────────\n"
      f"{P_PKG} <b>Total:</b> {total} | {P_TG} Telegram: {counts['tg'] + counts['s1']} | "
      f"{P_PHONE} WhatsApp: {counts['wa']} | {P_LIGHTNING} SMM: {counts['smm']}\n"
      f"{P_ASST} <b>Page:</b> {page} of {pages}\n\n"
    )
    btns = []
    for it in chunk:
      when = html.escape(it["ts"][:16])
      if it["kind"] == "tg":
        msg += (f"{P_TG} <b>Telegram Account</b>\n"
                f"{country_flag_html(None, it['country'])} {html.escape(str(it['country']))} ({it['year']}) — "
                f"<code>{html.escape(str(it['phone']))}</code>\n"
                f"{P_MONEY} ₹{it['price']} {P_CAL} {when}\n\n")
      elif it["kind"] == "s1":
        msg += (f"{P_TG} <b>Telegram Account</b> (Server 1)\n"
                f"{country_flag_html(it.get('ccode'), it['country'])} {html.escape(clean_country_name(it['country']))} — "
                f"<code>{html.escape(str(it['phone'] or 'Pending'))}</code>\n"
                f"{P_MONEY} ₹{it['price']} | {html.escape(it['status'])} {P_CAL} {when}\n\n")
      elif it["kind"] == "wa":
        code_txt = f" | {P_OTP} <code>{html.escape(_otp_gap(it['code']))}</code>" if it.get("code") else ""
        msg += (f"{P_WA} <b>WhatsApp Account</b>\n"
                f"{country_flag_html(None, it['country'])} {html.escape(str(it['country']))} — "
                f"<code>{html.escape(str(it['phone']))}</code>\n"
                f"{P_MONEY} ₹{float(it['price'] or 0):.2f} | {html.escape(it['status'])}{code_txt} {P_CAL} {when}\n\n")
      else:
        msg += (f"{P_LIGHTNING} <b>SMM Service</b> #{it['boid']}\n"
                f"{P_GEAR} {html.escape(str(it['service']))}\n"
                f"{P_PKG} Qty: {it['qty']} | {P_MONEY} ₹{float(it['price'] or 0):.2f} | "
                f"{html.escape(str(it['status']))} {P_CAL} {when}\n\n")
      if it.get("btn"):
        label = {"s1": "Telegram", "wa": "WhatsApp"}.get(it["kind"], "Order")
        label = f"{label} {it.get('phone') or ''}".strip()[:40]
        btns.append([Button.inline(label, it["btn"])])
    nav = []
    if page > 1:
      nav.append(Button.inline("Prev", f"my_orders|{page-1}"))
    nav.append(Button.inline(f"{page}/{pages}", f"my_orders|{page}"))
    if page < pages:
      nav.append(Button.inline("Next", f"my_orders|{page+1}"))
    btns.append(nav)
    btns.append([Button.inline("Back to Main", "back_main")])

  if is_callback:
    try:
      await e_edit_or_send(event, custom_emoji_text(msg), btns)
    except MessageNotModifiedError:
      pass
  else:
    await bot.send_message(event.chat_id, custom_emoji_text(msg), buttons=btns, parse_mode='html')

async def payments_history_handler(event):
  uid = event.sender_id
  rows = cur.execute("SELECT amount, method_name, status, date FROM deposits WHERE user_id=? ORDER BY id DESC LIMIT 5", (uid,)).fetchall()
  
  if not rows:
    msg = f"{P_CARD} <b>You don't have any payment history yet.</b>"
  else:
    msg = f"{P_CARD} {P_MONEY} <b>Recent Payments:</b>\n\n"
    for amt, method, status, d in rows:
      msg += f"- ₹{amt} via {method} – <b>{status.upper()}</b> {P_YES}\n {P_CAL} {d}\n────────────────\n"

  btns = [[Button.inline("Back to Profile", "profile_callback")]]
  await event.edit(custom_emoji_text(msg), buttons=btns)

def _on_off(flag):
  return 'ON' if flag else 'OFF'


async def _pm_edit(event, msg, btns):
  try:
    return await event.edit(custom_emoji_text(msg), buttons=btns)
  except MessageNotModifiedError:
    return


async def _render_payment_methods(event, which=None):
  """Payment Methods admin area. The main screen lists every method; each method
  has its OWN page with its own settings (which = fampay / bharatpe / manual / usdt)."""
  if which:
    return await _render_payment_method_page(event, which)
  fe = payment_enabled('fampay_enabled'); be = payment_enabled('bharatpe_enabled')
  me = payment_enabled('manual_enabled'); ue = payment_enabled('usdt_enabled')
  msg = (f"{P_CARD} <b>Payment Methods</b>\n\n"
         f"Tap a method to open its own settings.\n\n"
         f"FamPay Automatic: <b>{_on_off(fe)}</b>\n"
         f"BharatPe Automatic: <b>{_on_off(be)}</b>"
         + "\n"
         f"UPI Manual: <b>{_on_off(me)}</b>\n"
         f"USDT Manual: <b>{_on_off(ue)}</b>\n\n"
         f"<i>OFF methods are hidden from users in Add Funds.</i>")
  btns = [[Button.inline(f"FamPay Automatic: {_on_off(fe)}", "adm_pm|fampay",
                         icon_custom_emoji_id=(_ICON_OK if fe else _ICON_NO))],
          [Button.inline(f"BharatPe Automatic: {_on_off(be)}", "adm_pm|bharatpe",
                         icon_custom_emoji_id=(_ICON_OK if be else _ICON_NO))],
          [Button.inline(f"UPI Manual: {_on_off(me)}", "adm_pm|manual",
                         icon_custom_emoji_id=(_ICON_OK if me else _ICON_NO))],
          [Button.inline(f"USDT Manual: {_on_off(ue)}", "adm_pm|usdt",
                         icon_custom_emoji_id=(_ICON_OK if ue else _ICON_NO))],
          [Button.inline("Back to Admin", "adm_adminmain")]]
  return await _pm_edit(event, msg, btns)


async def _render_payment_method_page(event, which):
  back = [Button.inline("Back to Payment Methods", "adm_paymentmethods")]
  if which == 'fampay':
    on = payment_enabled('fampay_enabled')
    msg = (f"{P_CARD} <b>FamPay Automatic</b>\n\n"
           f"Status: <b>{_on_off(on)}</b>\n"
           f"UPI: <code>{html.escape(get_fampay_upi())}</code>\n"
           f"Payee: <code>{html.escape(get_fampay_name())}</code>\n"
           f"Min Deposit: <b>₹{get_min_deposit('FamPay Automatic')}</b>\n"
           f"Verification: <b>Gmail IMAP</b>")
    btns = [[Button.inline(f"FamPay Automatic: {_on_off(on)}", "adm_toggle_fampay",
                           icon_custom_emoji_id=(_ICON_OK if on else _ICON_NO))],
            [Button.inline("Set FamPay UPI & Name", "adm_set_auto_upi")],
            [Button.inline("Configure IMAP (Gmail)", "adm_set_imap")],
            [Button.inline("Set FamPay Minimum Deposit", "adm_set_mindep|fampay")], back]
  elif which == 'bharatpe':
    on = payment_enabled('bharatpe_enabled')
    mid, tok = get_bharatpe_api()
    msg = (f"{P_CARD} <b>BharatPe Automatic</b>\n\n"
           f"Status: <b>{_on_off(on)}</b>"
           + ("" if get_bharatpe_upi() else "  (set the UPI ID first)") + "\n"
           f"UPI: <code>{html.escape(get_bharatpe_upi() or 'Not set')}</code>\n"
           f"Payee: <code>{html.escape(get_bharatpe_name())}</code>\n"
           f"Merchant ID: <code>{html.escape(_mask_secret(mid))}</code>\n"
           f"Token: <b>{'Set' if tok else 'Not set'}</b>\n"
           f"Min Deposit: <b>₹{get_min_deposit('BharatPe Automatic')}</b>\n"
           f"Verification: <b>{'BharatPe API (UTR)' if bharatpe_api_ready() else 'Set Merchant ID & Token'}</b>")
    btns = [[Button.inline(f"BharatPe Automatic: {_on_off(on)}", "adm_toggle_bharatpe",
                           icon_custom_emoji_id=(_ICON_OK if on else _ICON_NO))],
            [Button.inline("Set BharatPe UPI & Name", "adm_set_bharatpe_upi")],
            [Button.inline("Set BharatPe Merchant ID & Token", "adm_set_bharatpe_api")],
            [Button.inline("Test BharatPe Connection", "adm_bharatpe_test")],
            [Button.inline("Set BharatPe Minimum Deposit", "adm_set_mindep|bharatpe")], back]
  elif which == 'manual':
    on = payment_enabled('manual_enabled')
    msg = (f"{P_CARD} <b>UPI Manual</b>\n\n"
           f"Status: <b>{_on_off(on)}</b>\n"
           f"UPI: <code>{html.escape(get_manual_upi())}</code>\n"
           f"Payee: <code>{html.escape(get_manual_name())}</code>\n"
           f"Min Deposit: <b>₹{get_min_deposit('UPI Manual')}</b>\n"
           f"Verification: <b>Admin approves screenshot</b>")
    btns = [[Button.inline(f"UPI Manual: {_on_off(on)}", "adm_toggle_manual",
                           icon_custom_emoji_id=(_ICON_OK if on else _ICON_NO))],
            [Button.inline("Set Manual UPI & Name", "adm_set_manual_upi")],
            [Button.inline("Set Manual Minimum Deposit", "adm_set_mindep|manual")], back]
  elif which == 'usdt':
    on = payment_enabled('usdt_enabled')
    addr = get_usdt_address()
    msg = (f"{P_CARD} <b>USDT Manual</b>\n\n"
           f"Status: <b>{_on_off(on)}</b>"
           + ("" if addr else "  (hidden from users until an address is set)") + "\n"
           f"Address: <code>{html.escape(addr or 'Not set')}</code>\n"
           f"Network: <b>{html.escape(get_usdt_network())}</b>\n"
           f"Min Deposit: <b>₹{get_min_deposit('USDT Manual')}</b>\n"
           f"Verification: <b>Admin approves screenshot</b>")
    btns = [[Button.inline(f"USDT Manual: {_on_off(on)}", "adm_toggle_usdt",
                           icon_custom_emoji_id=(_ICON_OK if on else _ICON_NO))],
            [Button.inline("Set USDT Address & Network", "adm_set_usdt")],
            [Button.inline("Set Crypto Minimum Deposit", "adm_set_mindep|crypto")], back]
  else:
    return await _render_payment_methods(event)
  return await _pm_edit(event, msg, btns)


async def deposit_menu(event):
  rows=[]
  if payment_enabled('fampay_enabled'):
    rows.append([Button.inline("FamPay Automatic", "depm_auto")])
  if bharatpe_available():
    rows.append([Button.inline("BharatPe Automatic", "depm_bharatpe")])
  if payment_enabled('manual_enabled'):
    rows.append([Button.inline("UPI Manual", "depm_manual")])
  if usdt_manual_available():
    rows.append([Button.inline("USDT Manual", "depm_usdt")])
  rows.append([Button.inline("Back", "back_main")])
  msg=f"{P_CARD} {P_MONEY} <b>Select Payment Method</b>\n\nChoose an enabled method below."
  if len(rows) == 1:
    msg=f"{P_WARN} <b>Deposits are temporarily disabled.</b>\n\nNo payment method is available right now. Please contact support."
  if isinstance(event, events.CallbackQuery.Event): await event.edit(custom_emoji_text(msg),buttons=rows)
  else: await bot.send_message(event.chat_id,custom_emoji_text(msg),buttons=rows)

async def manual_deposit_init(event, method):
  """Open a button-based amount keypad for both payment methods."""
  uid = event.sender_id
  method_key = 'auto' if method in AUTO_METHODS else 'manual'
  deposit_input[uid] = {'step': 'amount_keypad', 'method': method, 'method_key': method_key, 'amount': ''}
  await show_deposit_amount_keypad(event, uid)

async def show_deposit_amount_keypad(event, uid):
  state = deposit_input.get(uid, {})
  method = state.get('method', 'UPI Manual')
  amount = state.get('amount', '') or '0'
  msg = (
    f"{P_CARD} <b>Custom Amount</b>\n\n"
    f"{P_MONEY} <b>Method:</b> {html.escape(method)}\n"
    f"{P_ASST} <b>Amount: ₹{html.escape(amount)}</b>\n\n"
    f"{P_ASST} <i>Enter the amount using the buttons:</i>"
  )
  btns = [
    [Button.inline(" 1", "dep_key|1"), Button.inline(" 2", "dep_key|2"), Button.inline(" 3", "dep_key|3")],
    [Button.inline(" 4", "dep_key|4"), Button.inline(" 5", "dep_key|5"), Button.inline(" 6", "dep_key|6")],
    [Button.inline(" 7", "dep_key|7"), Button.inline(" 8", "dep_key|8"), Button.inline(" 9", "dep_key|9")],
    [Button.inline(" Delete", "dep_key_del"), Button.inline(" 0", "dep_key|0"), Button.inline(" Confirm", "dep_key_confirm")],
    [Button.inline(" Back", "dep_menu_cb")]
  ]
  await event.edit(custom_emoji_text(msg), buttons=btns)

async def generate_deposit_qr(event, uid):
  state = deposit_input.get(uid)
  if not state or state.get('step') != 'amount_keypad':
    return await safe_callback_answer(event, "Amount session expired. Please start again.", alert=True)
  raw_amount = state.get('amount', '')
  try:
    amt = int(raw_amount)
  except Exception:
    amt = 0
  method = state.get('method', 'UPI Manual')
  _min_dep = get_min_deposit(method)
  if amt < _min_dep:
    return await safe_callback_answer(event, f"Minimum deposit is ₹{_min_dep}.", alert=True)
  if method == 'USDT Manual':
    return await _generate_usdt_payment(event, uid, state, amt, raw_amount)
  is_auto = method in AUTO_METHODS
  if method == 'BharatPe Automatic':
    if not bharatpe_available():
      return await safe_callback_answer(event, "BharatPe is currently unavailable.", alert=True)
    upi_id, payee = get_bharatpe_upi(), get_bharatpe_name()
  else:
    upi_id = get_fampay_upi() if is_auto else get_manual_upi()
    payee = get_fampay_name() if is_auto else get_manual_name()

  # Keep the UPI URI internal only for QR generation. Never show a payment link to the user.
  upi_link = 'upi://pay?' + urlencode({'pa': upi_id, 'pn': payee, 'am': amt, 'cu': 'INR'})
  qr_url = 'https://api.qrserver.com/v1/create-qr-code/?size=350x350&data=' + quote(upi_link)
  qr_file = f"qr_{uid}_{int(time.time())}.png"

  await safe_callback_answer(event, "Generating payment QR...", alert=False)
  try:
    await event.edit(custom_emoji_text(f"{P_WAIT} <b>Generating payment QR...</b>\n\nAmount: <b>₹{amt}</b>"), buttons=[[Button.inline("Cancel", "cancel_action")]])
  except Exception:
    pass

  try:
    urllib.request.urlretrieve(qr_url, qr_file)
  except Exception as ex:
    logger.error(f"Deposit QR generation failed: {ex}")
    deposit_input[uid] = {'step': 'amount_keypad', 'method': method, 'method_key': state.get('method_key'), 'amount': raw_amount}
    return await event.edit(custom_emoji_text(f"{P_NO} <b>QR generation failed.</b>\n\nPlease try again."), buttons=[[Button.inline("Generate QR Again", "dep_key_confirm")], [Button.inline("Cancel", "cancel_action")]])

  deposit_input[uid] = {'step': 'wait_payment_verify', 'amount': amt, 'method': method, 'upi_id': upi_id, 'payee': payee}
  caption = (
    f"{P_CARD} <b>{html.escape(method)} Payment</b>\n\n"
    f"{P_MONEY} <b>Amount: ₹{amt}</b>\n"
    f"{P_ACC} <b>Payee: {html.escape(payee)}</b>\n\n"
    f"Scan the QR and complete the payment.\n"
    f"After payment, tap <b>Verify Payment</b> and send your payment screenshot."
  )
  btns = [[Button.inline(" Verify Payment", "dep_payment_verify")], [Button.inline(" Cancel", "cancel_action")]]
  try:
    await bot.send_file(uid, qr_file, caption=custom_emoji_text(caption), buttons=btns, force_document=False)
    try: os.remove(qr_file)
    except Exception: pass
    try: await event.delete()
    except Exception: pass
  except Exception as ex:
    logger.error(f"Failed to send deposit QR: {ex}")
    try: os.remove(qr_file)
    except Exception: pass
    deposit_input.pop(uid, None)
    await event.edit(custom_emoji_text(f"{P_NO} <b>Could not send the payment QR.</b> Please try again."), buttons=[[Button.inline("Back", "dep_menu_cb")]])

async def _generate_usdt_payment(event, uid, state, amt, raw_amount):
  """Manual USDT deposit: show address + exact USDT amount, then Send Screenshot / Cancel."""
  address = get_usdt_address()
  network = get_usdt_network()
  if not address or not payment_enabled('usdt_enabled'):
    deposit_input.pop(uid, None)
    return await event.edit(custom_emoji_text(f"{P_NO} <b>USDT payments are currently unavailable.</b>"),
                            buttons=[[Button.inline("Back", "dep_menu_cb")]])
  rate = get_usdt_rate()
  usdt_amount = max(0.01, round(amt / rate, 2))
  deposit_input[uid] = {'step': 'wait_payment_verify', 'amount': amt, 'method': 'USDT Manual',
                        'usdt_amount': usdt_amount, 'address': address, 'network': network}
  caption = (
    f"{P_USDT} <b>USDT Manual Payment</b>\n\n"
    f"{P_MONEY} <b>Send exactly:</b> <code>{usdt_amount:.2f}</code> USDT\n"
    f"{P_GLOBE} <b>Network:</b> <b>{html.escape(network)}</b>\n"
    f"{P_KEY} <b>Address:</b>\n<code>{html.escape(address)}</code>\n\n"
    f"{P_RATE} Rate: 1 USDT = ₹{rate:g}\n"
    f"{P_CARD} Wallet credit: <b>₹{amt}</b>\n\n"
    f"{P_WARN} <b>Only send USDT on the {html.escape(network)} network.</b> Funds sent on another network cannot be recovered.\n"
    f"After paying, tap <b>Send Screenshot</b> and upload your payment screenshot."
  )
  btns = [[Button.inline("Send Screenshot", "dep_payment_verify")], [Button.inline("Cancel", "cancel_action")]]
  qr_file = f"qr_usdt_{uid}_{int(time.time())}.png"
  try:
    urllib.request.urlretrieve(
      'https://api.qrserver.com/v1/create-qr-code/?size=350x350&data=' + quote(address), qr_file)
    await bot.send_file(uid, qr_file, caption=custom_emoji_text(caption), buttons=btns, force_document=False)
    try: await event.delete()
    except Exception: pass
  except Exception as ex:
    # QR is optional: fall back to the same details as a plain message.
    logger.warning(f"USDT QR failed, sending text only: {ex}")
    try:
      await event.edit(custom_emoji_text(caption), buttons=btns)
    except Exception:
      await bot.send_message(uid, custom_emoji_text(caption), buttons=btns, parse_mode='html')
  finally:
    try: os.remove(qr_file)
    except Exception: pass

async def confirm_purchase(event, country, year, price_str):
  uid = event.sender_id
  base_price = int(price_str)
  
  bal_row = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
  bal = bal_row[0] if bal_row else 0
  disc_row = cur.execute("SELECT discount FROM users WHERE user_id=?", (uid,)).fetchone()
  discount = disc_row[0] if disc_row else 0
  final_price = base_price if discount == 0 else int(base_price * (100 - discount) / 100)

  msg = (f"{P_CART} {P_FIRE} <b>Confirm Your Purchase</b> {P_STAR}\n\n"
      f"{P_FLAG} <b>Country:</b> {html.escape(country)}\n"
      f"{P_CAL} <b>Year:</b> {year}\n"
      f"{P_MONEY} <b>Final Price:</b> {P_INR}{final_price}\n\n"
      f"{P_CARD} <b>Your Balance:</b> {P_INR}{bal}\n\n"
      f"Do you want to proceed with this purchase? {P_ASST}")
  
  btns = [
    [Button.inline("Yes, Buy Now", f"buy_cf|{_country_token(country)}|{year}|{base_price}")],
    [Button.inline("No, Cancel", "cancel_action")]
  ]
  await event.edit(custom_emoji_text(msg), buttons=btns)

def _manual_purchase_text(gid, phone, country, twofa_pass, otp_code=None, extra=""):
  twofa_line = (f"{P_2FA} <b>2FA:</b> <code>{html.escape(str(twofa_pass))}</code>\n"
                if str(twofa_pass) not in ("None", "", "No password") else
                f"{P_2FA} <b>2FA:</b> <code>Disabled (No Password)</code>\n")
  txt = (f"{P_YES} {P_ROCKET} <b>Order Successful!</b>\n\n"
         f"{P_ID} <b>Bot Order ID:</b> <code>{gid or '-'}</code>\n"
         f"{P_PHONE} <b>Phone:</b> <code>+{html.escape(str(phone))}</code>\n"
         f"{P_FLAG} <b>Country:</b> {html.escape(str(country))}\n"
         + twofa_line + extra)
  if otp_code and str(otp_code) not in ("SESSION_DELIVERED", "COMPLETED", "-"):
    txt += f"{P_OTP} <b>OTP:</b> <code>{html.escape(_otp_gap(otp_code))}</code>\n"
  txt += (f"\n{P_KEY} Your <b>session file</b> is sent automatically.\n"
          f"{P_STAR} <b>Or login with OTP:</b>\n"
          f"1. Open Telegram & Add Account\n"
          f"2. Enter the number above.\n"
          f"3. {P_WAIT} The bot listens for your OTP and sends it automatically (10 min). "
          f"You can also use <b>My Orders</b> for Session File / Check OTP / Terminate Bot Session.")
  return txt


async def process_purchase(event, country, year_str, price_str):
  uid, base_price = event.sender_id, int(price_str)

  disc_row = cur.execute("SELECT discount FROM users WHERE user_id=?", (uid,)).fetchone()
  discount = disc_row[0] if disc_row else 0
  final_price = base_price if discount == 0 else int(base_price * (100 - discount) / 100)

  async with get_user_lock(uid):
    row = cur.execute("SELECT phone, session_file, account_year, twofa FROM stock WHERE country_name LIKE ? AND account_year=? AND price=? AND available=1 LIMIT 1", (f"{country}%", int(year_str), base_price)).fetchone()

    if not row:
      return await safe_callback_answer(event, "Sold out! Another user just bought this account.", alert=True)
    
    phone, sess, actual_year, twofa_pass = row

    cur.execute("UPDATE users SET balance = balance - ? WHERE user_id=? AND balance >= ?", (final_price, uid, final_price))
    if cur.rowcount == 0:
      return await safe_callback_answer(event, f"Insufficient Balance! Need ₹{final_price}", alert=True)

    cur.execute("UPDATE stock SET available=0 WHERE phone=?", (phone,))
    db.commit()

  await event.edit(custom_emoji_text(f"{P_WAIT} <b>Fetching Number (+{phone})...</b>"))
  clean_sess = sess if not sess.endswith(".session") else sess[:-8]
  client = TelegramClient(clean_sess, API_ID, API_HASH)
  
  try:
    await client.connect()
    if not await client.is_user_authorized(): raise Exception("Session dead")
  except Exception:
    async with get_user_lock(uid):
      cur.execute("DELETE FROM stock WHERE phone=?", (phone,))
      cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (final_price, uid))
      db.commit()
    await client.disconnect()
    delete_session_files(sess)
    return await event.edit(custom_emoji_text(f"{P_NO} <b>Account Invalid.</b> Money refunded. Try buying another."))

  # The account is alive -> the sale is final. Save the order (so it appears in My Orders),
  # remove it from stock and deliver the session file right away.
  async with get_user_lock(uid):
    cur.execute("INSERT INTO orders (user_id, country, year, price, phone, otp, session_file, twofa_pass) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (uid, country, actual_year, final_price, phone, "SESSION_DELIVERED", clean_sess, str(twofa_pass)))
    telegram_local_id = cur.lastrowid
    cur.execute("DELETE FROM stock WHERE phone=?", (phone,))
    db.commit()
  telegram_global_id = _global_order_register('telegram', telegram_local_id, uid, final_price, 'COMPLETED')
  try:
    await log_primary_purchase(uid, country, final_price, final_price, actual_year, 1, phone=phone, global_order_id=telegram_global_id)
  except Exception as _ex:
    logger.error(f"purchase log failed: {_ex}")

  msg = _manual_purchase_text(telegram_global_id, phone, country, twofa_pass)
  btns = [[Button.inline("My Orders", "cb_orders")]]
  sent_msg = await event.edit(custom_emoji_text(msg), buttons=btns)

  try:
    await _send_manual_session_file(uid, phone, clean_sess, str(twofa_pass), country)
  except Exception as _ex:
    logger.error(f"session file delivery failed: {_ex}", exc_info=True)

  active_orders[phone] = {
    'uid': uid,
    'client': client, 'sess': sess, 'start_time': time.time(), 
    'paid': True, 'price': final_price, 'country': country, 'year': actual_year, 
    'twofa': twofa_pass, 'msg_id': sent_msg.id
  }
  asyncio.create_task(auto_otp_task(phone))

async def auto_otp_task(phone):
  if phone not in active_orders: return
  
  order = active_orders[phone]
  client = order['client']
  start_time = order['start_time']
  uid = order['uid']
  msg_id = order['msg_id']
  
  while time.time() - start_time < 600:
    if phone not in active_orders: return 
    try:
      msgs = await client.get_messages(777000, limit=5)
      code = None
      for m in msgs:
        if m.date.timestamp() > start_time - 10: 
          if m.message and re.search(r'\b\d{5}\b', m.message) and "Login detected" not in m.message:
            code = re.search(r'\b\d{5}\b', m.message).group()
            break
      
      if code:
        if not order['paid']:
          order['paid'] = True
          async with get_user_lock(uid):
            cur.execute("INSERT INTO orders (user_id, country, year, price, phone, otp) VALUES (?,?,?,?,?,?)", (uid, order['country'], order['year'], order['price'], phone, code))
            cur.execute("DELETE FROM stock WHERE phone=?", (phone,))
            db.commit()
          
          await log_primary_purchase(uid, order['country'], order['price'], order['price'], order['year'], 1, phone=phone)
        
        twofa_text = f"{P_2FA} <b>2FA:</b> <code>{html.escape(order['twofa'])}</code>" if order['twofa'] != "None" else f"{P_2FA} <b>2FA:</b> <code>Disabled (No Password)</code>"
        msg_text = (f"{P_YES} {P_FIRE} <b>Latest OTP Fetched!</b> {P_PARTY}\n\n"
              f"{P_PHONE} <b>Phone:</b> <code>{phone}</code>\n"
              f"{P_FLAG} <b>Country:</b> {html.escape(order['country'])}\n"
              f"{P_OTP} <b>OTP:</b> <code>{_otp_gap(code)}</code>\n"
              f"{twofa_text}")
        
        btns = [
          [Button.inline("Get OTP Again", f"get_otp_again|{phone}")],
          [Button.inline("Finish & Logout", f"logout_bot|{phone}")]
        ]
        try: await bot.edit_message(uid, msg_id, msg_text, buttons=btns)
        except: await bot.send_message(uid, msg_text, buttons=btns)
        return 
    except Exception: pass
    await asyncio.sleep(3) 
    
  if phone in active_orders and active_orders[phone]['paid']:
    # Sale already final (session delivered): just release the live connection.
    _o = active_orders.pop(phone)
    try: await _o['client'].disconnect()
    except Exception: pass
    return

  if phone in active_orders and not active_orders[phone]['paid']:
    order = active_orders.pop(phone)
    try: await order['client'].disconnect()
    except: pass
    
    async with get_user_lock(uid):
      cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (order['price'], uid))
      cur.execute("UPDATE stock SET available=1 WHERE phone=?", (phone,))
      db.commit()
      
    try: 
      await bot.edit_message(uid, msg_id, f"{P_TIME} <b>Order Expired!</b>\nThe 10-minute limit for <code>{phone}</code> ran out. Your money ({P_INR}{order['price']}) has been automatically refunded.")
    except: pass

async def init_session_purchase(event, country, year, price_str):
  uid, price = event.sender_id, int(price_str)
  stock_row = cur.execute("SELECT COUNT(*) FROM stock WHERE country_name LIKE ? AND account_year=? AND price=? AND available=1", (f"{country}%", int(year), price)).fetchone()
  stock = stock_row[0] if stock_row else 0
  if stock == 0: return await safe_callback_answer(event, "Out of stock!", alert=True)
  
  session_buy_state[uid] = {'country': country, 'year': year, 'price': price, 'stock': stock}
  disc_row = cur.execute("SELECT discount FROM users WHERE user_id=?", (uid,)).fetchone()
  discount = disc_row[0] if disc_row else 0
  p_disp = price if discount == 0 else int(price * (100 - discount) / 100)
  
  msg = (f"{P_STORE} {P_ROCKET} <b>Buy {html.escape(country)} ({year}) Sessions</b>\n\n"
      f"{P_MONEY} <b>Price per session:</b> {P_INR}{p_disp}\n"
      f"{P_PKG} <b>Available Stock:</b> {stock}\n\n"
      f"Reply to this message with the <b>Number of Sessions</b> you want to buy.")
  await event.edit(custom_emoji_text(msg), buttons=[[Button.inline("Cancel", "cancel_action")]])

async def process_bulk_sessions(event, uid, qty, state, final_cost):
  country, year, price = state['country'], int(state['year']), int(state['price'])
  await event.respond(custom_emoji_text(f"{P_WAIT} <b>Processing your sessions...</b>"))
  bulk_global_ids = []

  async with get_user_lock(uid):
    rows = cur.execute("SELECT phone, session_file, twofa, account_year FROM stock WHERE country_name LIKE ? AND account_year=? AND price=? AND available=1 LIMIT ?", (f"{country}%", year, price, qty)).fetchall()
    if len(rows) < qty:
      return await event.respond(custom_emoji_text(f"{P_NO} Stock changed during processing. Purchase Cancelled."))
    
    cur.execute("UPDATE users SET balance = balance - ? WHERE user_id=? AND balance >= ?", (final_cost, uid, final_cost))
    if cur.rowcount == 0:
      return await event.respond(custom_emoji_text(f"{P_NO} Insufficient Balance! Purchase Cancelled."))

    phones = [r[0] for r in rows]
    placeholders = ",".join("?" for _ in phones)
    cur.execute(f"UPDATE stock SET available=0 WHERE phone IN ({placeholders})", phones)
    cur.execute(f"DELETE FROM stock WHERE phone IN ({placeholders})", phones)
    
    price_per_acc = final_cost // qty
    for p in phones:
      _sf, _tf, _yr = next(((r[1], r[2], r[3]) for r in rows if r[0] == p), ("", "None", year))
      cur.execute("INSERT INTO orders (user_id, country, year, price, phone, otp, session_file, twofa_pass) VALUES (?,?,?,?,?,?,?,?)",
                  (uid, country, _yr, price_per_acc, p, "SESSION_FILES", _sf, str(_tf)))
      _bulk_order_local_id = cur.lastrowid
      bulk_global_ids.append(_global_order_register('telegram', _bulk_order_local_id, uid, price_per_acc, 'COMPLETED'))
    db.commit()

  zip_name = f"sessions_{uid}_{int(time.time())}.zip"
  numbers_txt = ""

  try:
    with zipfile.ZipFile(zip_name, 'w') as zf:
      for phone, sess_file, twofa_pass, y in rows:
        base_s = sess_file if not sess_file.endswith(".session") else sess_file[:-8]
        for ext in ['.session', '.session-wal', '.session-shm', '.session-journal']:
          src = base_s + ext
          if os.path.exists(src): zf.write(src, os.path.basename(src))
        
        pass_text = twofa_pass if twofa_pass != "None" else "No_Password"
        numbers_txt += f"+{phone} | pass:{pass_text}\n"
      
      numbers_txt += "\n\nPurchased from @Freshtgsales\n"
      zf.writestr("numbers.txt", numbers_txt)
      
    caption = f"{P_YES} {P_PARTY} <b>Bulk Purchase Successful!</b>\n\n{P_FLAG} Country: {html.escape(country)}\n{P_PKG} Quantity: {qty}\n{P_CARD} Total Paid: {P_INR}{final_cost}\n\n<i>(Note: Sessions are safely provided, the bot does not keep them active)</i>"
    await bot.send_file(uid, zip_name, caption=custom_emoji_text(caption))
    await log_primary_purchase(uid, country, price, final_cost, year, qty,
                               phone=', '.join('+' + str(x) for x in phones),
                               global_order_id=', '.join(x for x in bulk_global_ids if x))
  except Exception as e: await event.respond(custom_emoji_text(f"{P_WARN} Error creating zip: {e}"))
  finally:
    if os.path.exists(zip_name): os.remove(zip_name)

# ================= ADMIN PANEL =================
async def admin_panel_handler(event):
  uid = event.sender_id
  if not is_admin(uid): return
  
  status_text = BOT_STATUS_LABEL.get(get_bot_status(), "Bot ON")
  btns = []
  
  if uid == ADMIN_ID or has_perm(uid, 'p_settings'):
    btns.append([Button.inline(f"Status: {status_text}", "adm_togglebot")])
    
  r1 = []
  if uid == ADMIN_ID or has_perm(uid, 'p_add_stock') or has_perm(uid, 'p_manage_stock'):
    r1.append(Button.inline("Manual Acc", "adm_accmenu"))
  if uid == ADMIN_ID or has_perm(uid, 'p_manage_stock') or has_perm(uid, 'p_settings'):
    r1.append(Button.inline("SMM", "adm_smmmenu"))
  if r1: btns.append(r1)

  r3 = []
  r3.append(Button.inline("ALL SALES / BOT ORDERS", "adm_globalsales|1", style="primary"))
  if uid == ADMIN_ID or has_perm(uid, 'p_stats'):
    r3.extend([
      Button.inline("Statistics", "adm_stats"), 
      Button.inline("Broadcast", "adm_bcast")
    ])
    r3.append(Button.inline("ALL USERS", "adm_users|1", style="success"))
  if r3: btns.append(r3)

  r4 = []
  if uid == ADMIN_ID or has_perm(uid, 'p_bal'):
    r4.extend([
      Button.inline("Change Balance", "adm_balmenu"), 
      Button.inline("Ban User", "adm_ban")
    ])
  if r4: btns.append(r4)

  r5 = []
  if uid == ADMIN_ID or has_perm(uid, 'p_settings'):
    r5.extend([
      Button.inline("Discount", "adm_discount"), 
      Button.inline("USDT Rate", "adm_usdtrate")
    ])
    btns.append(r5)
    btns.append([Button.inline("Set Refer Bonus %", "adm_referpct")])
    btns.append([
      Button.inline("Support User", "adm_supporturl"), 
      Button.inline("Support Channel", "adm_supportchan")
    ])
    btns.append([
      Button.inline("Update Welcome Media", "adm_update_welcome_photo"),
      Button.inline("Change Logs Channel", "adm_changelogs")
    ])
    if uid == ADMIN_ID and not IS_CLONE:
      btns.append([
        Button.inline("Backup", "adm_backupusr"), 
        Button.inline("Restore", "adm_restoreusr")
      ])
    if uid == ADMIN_ID and not IS_CLONE:
      btns.append([Button.inline("Clone Bot", "adm_clonebot"),
                   Button.inline("Manage Cloned Bots", "adm_cbm|menu|0")])
      btns.append([Button.inline("API Keys", "adm_apik|menu")])
    btns.append([
      Button.inline("Channels", "adm_forcechannels"),
      Button.inline("Payment Methods", "adm_paymentmethods")
    ])
    btns.append([
      Button.inline("Redeem Codes", "adm_redeemcodes"),
      Button.inline("Shop", "adm_digitalshop")
    ])
    if uid == ADMIN_ID:
      btns.append([Button.inline("Servers APIs", "adm_serverapis"),
                   Button.inline("Function Management", "fnmgmt_menu")])
      btns.append([Button.inline("Automation", "adm_automation", style="primary")])
    btns.append([Button.inline("USER INFO / MANAGE", "adm_userinfo", style="primary")])

  if uid == ADMIN_ID:
    btns.append([Button.inline("Manage Admins", "adm_manageadmins")])

  try:
    _total_users = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    _total_wallet = cur.execute("SELECT COALESCE(SUM(balance),0) FROM users").fetchone()[0] or 0
    _total_orders = cur.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
  except Exception:
    _total_users = _total_wallet = _total_orders = 0

  _st = get_bot_status()
  _st_icon = {'on': P_ON, 'maintenance': P_WARN, 'off': P_OFF}.get(_st, P_ON)
  _st_name = {'on': 'Online', 'maintenance': 'Maintenance', 'off': 'Offline'}.get(_st, 'Online')
  dash_msg = (
    f"{P_PC} <b>ADVANCED ADMIN DASHBOARD</b> {P_CROWN}\n"
    f"────────────────\n\n"
    f"{P_STATS} <b>Bot Status:</b> {_st_icon} <b>{_st_name}</b>\n"
    f"<i>Tap the Status button to switch: ON → Maintenance → OFF</i>\n"
    f"{P_USERS} <b>Total Users:</b> <b>{_total_users}</b>\n"
    f"{P_MONEY} <b>Total Wallet:</b> {P_INR}{float(_total_wallet):.2f}\n"
    f"{P_CART} <b>Total Orders:</b> <b>{_total_orders}</b>"
  )
  try:
    if uid == ADMIN_ID or has_perm(uid, 'p_stats'):
      _t = _stats_collect("today")
      dash_msg += (f"\n\n{P_MONEY} <b>Today Revenue:</b> {P_INR}{_t['revenue']:.2f}"
                   f"\n{P_CARD} <b>Today Deposits:</b> {P_INR}{_t['dep_amt']:.2f}"
                   f"\n{P_CART} <b>Today Orders:</b> <b>{_t['orders_n']}</b>")
  except Exception as _dex:
    logger.warning("dashboard today stats failed: %s", _dex)
  await bot.send_message(event.chat_id, custom_emoji_text(dash_msg), buttons=btns)

async def manage_admins_menu(event):
  rows = cur.execute("SELECT user_id FROM admins ORDER BY rowid").fetchall()
  msg = (f"{P_USERS} <b>Manage Admins</b>\n━━━━━━━━━━━━━━━━\n"
         f"Total admins: <b>{len(rows)}</b>\n\n"
         f"<i>Tap an admin to edit permissions, or tap Remove to delete that admin.</i>")
  if not rows:
    msg += "\n\nNo admins added yet."
  btns = []
  for (aid,) in rows[:45]:
    label = await _admin_label(aid)
    btns.append([Button.inline(f"{label[:18]} · {aid}", f"adm_editadmin|{aid}", style="primary"),
                 Button.inline("Remove", f"adm_deladminask|{aid}", style="danger")])
  btns.append([Button.inline("Add Admin", "adm_addadmin", style="success")])
  btns.append([Button.inline("Back", "adm_adminmain")])
  await event.edit(custom_emoji_text(msg), buttons=btns)

async def edit_admin_menu(event, target_id):
  row = cur.execute("SELECT p_add_stock, p_manage_stock, p_stats, p_bal, p_settings FROM admins WHERE user_id=?", (target_id,)).fetchone()
  if not row: return await safe_callback_answer(event, "Admin not found", alert=True)
  p = ["Yes" if x==1 else "No" for x in row]
  
  btns = [
    [Button.inline(f"Add Stock: {p[0]}", f"adm_tglperm|{target_id}|p_add_stock")],
    [Button.inline(f"Manage Stock: {p[1]}", f"adm_tglperm|{target_id}|p_manage_stock")],
    [Button.inline(f"Stats & Bcast: {p[2]}", f"adm_tglperm|{target_id}|p_stats")],
    [Button.inline(f"Bal & Users: {p[3]}", f"adm_tglperm|{target_id}|p_bal")],
    [Button.inline(f"Settings: {p[4]}", f"adm_tglperm|{target_id}|p_settings")],
    [Button.inline("Remove Admin", f"adm_deladminask|{target_id}", style="danger")],
    [Button.inline("Back", "adm_manageadmins")]
  ]
  await event.edit(custom_emoji_text(f"{P_DOC} <b>Editing Admin:</b> <code>{target_id}</code>"), buttons=btns)

async def send_manage_stock_page(event, page):
  limit = 10
  offset = (page - 1) * limit
  rows = cur.execute("SELECT DISTINCT country_name FROM stock ORDER BY country_name").fetchall()
  total = len(rows)
  countries = rows[offset:offset+limit]
  
  btns = []
  for (c,) in countries: 
    btns.append([Button.inline(f"{html.escape(c)}", f"adm_msc|{c}")])
  
  nav = []
  if page > 1: nav.append(Button.inline("Prev", f"adm_mspg|{page-1}"))
  if offset + limit < total: nav.append(Button.inline("Next", f"adm_mspg|{page+1}"))
  if nav: btns.append(nav)
  btns.append([Button.inline("Back", "adm_adminmain")])
  await event.edit(custom_emoji_text(f"{P_DOC} <b>Manage Stock</b> (Page {page})\nSelect a country to edit its properties:"), buttons=btns)

async def send_manage_stock_country(event, c_name):
  years = cur.execute("SELECT DISTINCT account_year FROM stock WHERE country_name=? ORDER BY account_year DESC", (c_name,)).fetchall()
  btns = [
    [Button.inline("Edit Country Name", f"adm_msedit|name|{c_name}")],
    [Button.inline("Edit Common Price (All Years)", f"adm_msedit|cprice|{c_name}")]
  ]
  y_btns = []
  for (y,) in years: 
    y_btns.append(Button.inline(f"{y}", f"adm_msedit|yprice|{c_name}|{y}"))
  
  for i in range(0, len(y_btns), 3): btns.append(y_btns[i:i+3])
  btns.append([Button.inline("Back", "adm_mspg|1")])
  await event.edit(custom_emoji_text(f"{P_GLOBE} <b>Managing: {html.escape(c_name)}</b>\nSelect an option to edit:"), buttons=btns)

async def send_autoprice_page(event, page):
  limit = 10
  offset = (page - 1) * limit
  c_list = set([c for c in COUNTRY_CODES.values()])
  db_countries = cur.execute("SELECT DISTINCT country_name FROM stock").fetchall()
  for (c,) in db_countries: c_list.add(c)
  
  custom_countries = cur.execute("SELECT DISTINCT name FROM custom_countries").fetchall()
  for (c,) in custom_countries: c_list.add(c)

  c_list = sorted(list(c_list))
  total = len(c_list)
  countries = c_list[offset:offset+limit]
  
  btns = []
  for c in countries: 
    btns.append([Button.inline(f"{html.escape(c)}", f"adm_apc|{c}")])
    
  nav = []
  if page > 1: nav.append(Button.inline("Prev", f"adm_appg|{page-1}"))
  if offset + limit < total: nav.append(Button.inline("Next", f"adm_appg|{page+1}"))
  if nav: btns.append(nav)
  btns.append([Button.inline("Add Custom Country", "adm_ap_add_country")])
  btns.append([Button.inline("Back", "adm_adminmain")])
  await event.edit(custom_emoji_text(f"{P_ASST} <b>Auto Price Setup</b> (Page {page})\nSelect a country to set fixed prices:"), buttons=btns)

async def send_autoprice_country(event, c_name):
  btns = [[Button.inline("Set Common Price", f"adm_apset|{c_name}|Common")]]
  y_btns = []
  for y in range(2024, 1999, -1): 
    y_btns.append(Button.inline(f"{y}", f"adm_apset|{c_name}|{y}"))
  for i in range(0, len(y_btns), 4): btns.append(y_btns[i:i+4])
  btns.append([Button.inline("Back", "adm_appg|1")])
  await event.edit(custom_emoji_text(f"{P_GLOBE} <b>Auto Price: {html.escape(c_name)}</b>\nSelect 'Common' for default price, or specific years:"), buttons=btns)

async def admin_server_apis_menu(event):
  """Admin -> Servers APIs: pick a server, then manage its URL, key and margin."""
  msg = (
    f"{P_GEAR} <b>Servers APIs</b>\n"
    f"────────────────\n\n"
    f"Choose a server to change its API URL, API key and profit margin.\n\n"
  )
  btns = []
  for no, conf in SERVER_DEFS.items():
    api_url, api_key = get_server_api_config(no)
    status = "Configured" if (api_url and api_key) else "Not configured"
    msg += (f"{P_PC} <b>{conf['label']}</b> — <b>{status}</b>\n"
            f"{P_RATE} Profit Margin: <b>{get_server_margin(no):g}%</b>\n\n")
    btns.append([Button.inline(conf["label"], f"adm_srvapi_view|{no}")])
  btns.append([Button.inline("Back to Admin", "adm_adminmain")])
  return await e_edit_or_send(event, custom_emoji_text(msg), btns)


async def admin_server_view(event, server_no):
  """One server's settings page: change URL / key / margin, test, remove."""
  conf = SERVER_DEFS.get(int(server_no))
  if not conf:
    return await safe_callback_answer(event, "Unknown server.", alert=True)
  api_url, api_key = get_server_api_config(server_no)
  margin = get_server_margin(server_no)
  status = "Configured" if (api_url and api_key) else "Not configured"
  if conf.get("kind") == "tiger":
    about = (f"{P_ASST} <b>Server 2</b> sells WhatsApp OTP numbers through the Tiger SMS API. "
             f"Keep the provider balance topped up — users pay from their bot wallet.") if not IS_CLONE else (
             f"{P_ASST} <b>Server 2</b> sells WhatsApp OTP numbers through a provider API. "
             f"Keep the provider balance topped up — users pay from their bot wallet.")
  elif conf.get("kind") == "s3":
    about = (f"{P_ASST} <b>Server 3</b> sells OTP numbers for all apps (Telegram, WhatsApp, Instagram & more). "
             f"If you leave its key empty, the Server 2 key is used. Keep the provider balance topped up — users pay from their bot wallet.")
  else:
    about = (f"{P_ASST} <b>Server 1</b> uses the <b>Lolzteam Market API</b> (<code>https://api.lzt.market</code>). "
             f"Paste your Bearer Access Token (with <code>market</code> scope) and keep your LZT wallet topped up — users pay from their bot wallet.") if not IS_CLONE else (
             f"{P_ASST} <b>Server 1</b> uses a reseller API. Paste your API key "
             f"and keep the API wallet topped up — users pay from their bot wallet.")
  docs_url = ""
  if IS_CLONE:
    docs_url = (get_setting("api_docs_url", "") or MAIN_API_DOCS_URL or "").strip().rstrip("/")
  msg = (
    f"{P_GEAR} <b>{conf['label']}</b>\n"
    f"────────────────\n\n"
    f"{about}\n\n"
    f"{P_STATS} <b>Status:</b> {status}\n"
    f"{P_LINK} <b>API URL:</b> <code>{html.escape(_mask_url(api_url))}</code>\n"
    f"{P_KEY} <b>API Key:</b> <code>{html.escape(_mask_secret(api_key))}</code>\n"
    f"{P_RATE} <b>Profit Margin:</b> <b>{margin:g}%</b>\n"
    f"{P_BELL} <b>Low Balance Alert:</b> {_lowbal_label(server_no)}"
  )
  if docs_url:
    msg += (
      f"\n{P_DOC} <b>API Docs:</b> <a href=\"{html.escape(docs_url)}\">{html.escape(docs_url)}</a>"
      f"\n<i>Reseller API docs of the main store. Create keys from MAIN bot → Admin → API Keys "
      f"(saved in main DB). This server still needs its own provider API URL + key to sell.</i>"
    )
  btns = [
    [Button.inline("Change API URL", f"adm_srvapi_url|{server_no}")],
    [Button.inline("Change API Key", f"adm_srvapi_key|{server_no}")],
    [Button.inline(f"Set Profit Margin ({margin:g}%)", f"adm_srvapi_margin|{server_no}")],
    [Button.inline(f"Low Balance Alert ({_lowbal_label(server_no)})", f"adm_srvapi_lowbal|{server_no}")],
    [Button.inline("Test API", f"adm_srvapi_test|{server_no}"),
     Button.inline("Remove API", f"adm_srvapi_del|{server_no}")],
    [Button.inline("Back to Servers APIs", "adm_serverapis")],
  ]
  return await e_edit_or_send(event, custom_emoji_text(msg), btns)


async def _server_quick_test(server_no):
  """Returns (ok, html_text) after checking the key against the provider."""
  conf = SERVER_DEFS.get(int(server_no)) or {}
  if conf.get("kind") == "tiger":
    try:
      bal = await asyncio.to_thread(_S2waTiger(_s2wa_api_key()).balance)
      countries = await asyncio.to_thread(_s2wa_countries, True)
      try:
        rate = float(get_usdt_rate())
      except Exception:
        rate = 94.0
      _is_res = (str(_s2wa_api_key() or "").startswith("ats_")
                 or _is_reseller_upstream(2))
      _mode = (f"{P_LINK} Mode: <b>Reseller API</b> (main store /v1)\n" if _is_res else "")
      _wallet = ("API Wallet" if _is_res else "Provider balance")
      return True, (f"{P_YES} <b>API connected!</b>\n" + _mode +
                    f"{P_MONEY} {_wallet}: ${bal:.4f} (≈ ₹{bal * rate:.2f})\n"
                    f"{P_PKG} Countries loaded: <b>{len(countries)}</b>")
    except Exception as ex:
      return False, f"{P_WARN} <b>Check failed:</b> {html.escape(_s2wa_human_error(ex))}"
  if conf.get("kind") == "s3":
    try:
      bal = await asyncio.to_thread(_s3_tiger().balance)
      countries = await asyncio.to_thread(_s3_countries, True)
      services = await asyncio.to_thread(_s3_services, True)
      try:
        rate = float(get_usdt_rate())
      except Exception:
        rate = 94.0
      _is_res = (str(_s3_key() or "").startswith("ats_")
                 or _is_reseller_upstream(3))
      _mode = (f"{P_LINK} Mode: <b>Reseller API</b> (main store /v1)\n" if _is_res else "")
      _wallet = ("API Wallet" if _is_res else "Provider balance")
      return True, (f"{P_YES} <b>API connected!</b>\n" + _mode +
                    f"{P_MONEY} {_wallet}: ${bal:.4f} (≈ ₹{bal * rate:.2f})\n"
                    f"{P_PKG} Apps loaded: <b>{len(services)}</b> | Countries: <b>{len(countries)}</b>")
    except Exception as ex:
      return False, f"{P_WARN} <b>Check failed:</b> {html.escape(_s3_human_error(ex))}"
  res = await asyncio.to_thread(fetch_phantom_balance, server_no)
  if isinstance(res, dict) and res.get("ok"):
    countries = await asyncio.to_thread(fetch_s2_countries, True)
    count = len(countries) if isinstance(countries, list) else 0
    return True, (f"{P_YES} <b>API connected!</b>\n"
                  f"{P_MONEY} API Wallet: ₹{res.get('balance', '-')}\n"
                  f"{P_PKG} Countries loaded: <b>{count}</b>")
  return False, f"{P_WARN} <b>Check failed:</b> {html.escape(_api_error_text(res))}"


async def admin_server_api_test(event, server_no):
  conf = SERVER_DEFS.get(server_no)
  if not conf:
    return await safe_callback_answer(event, "Unknown server.", alert=True)
  api_url, api_key = get_server_api_config(server_no)
  if not api_url or not api_key:
    return await safe_callback_answer(event, "Set the API URL and key first.", alert=True)

  await safe_callback_answer(event, "Testing API...", alert=False)
  lines = [f"{P_GEAR} <b>{conf['name']} API Test</b>", "────────────────", ""]

  if conf.get("kind") == "tiger":
    ok, text = await _server_quick_test(server_no)
    lines.append(text)
    if ok:
      try:
        available = await asyncio.to_thread(_s2wa_available)
        lines.append(f"{P_PKG} In stock: <b>{len(available)}</b> countries")
        preview = ""
        for c in available[:5]:
          preview += (f"{_s2wa_flag_html(c)} {html.escape(str(c['name']))} — "
                      f"₹{_s2wa_sell_price(c['cost']):.0f} ({c['count']})\n")
        if preview:
          lines.append("")
          lines.append(preview.rstrip())
      except Exception as ex:
        lines.append(f"{P_WARN} Price list: {html.escape(_s2wa_human_error(ex))}")
  elif conf.get("kind") == "s3":
    ok, text = await _server_quick_test(server_no)
    lines.append(text)
  else:
    balance_res = await asyncio.to_thread(fetch_phantom_balance, server_no)
    countries = await asyncio.to_thread(fetch_s2_countries, True)
    ok = isinstance(balance_res, dict) and balance_res.get("ok")
    if ok:
      lines.append(f"{P_YES} <b>Key Status:</b> Valid")
      raw_b = f" ({balance_res.get('raw_balance')})" if balance_res.get('raw_balance') else ""
      lines.append(f"{P_MONEY} <b>API Wallet:</b> ₹{balance_res.get('balance', '-')}{html.escape(raw_b)}")
      if balance_res.get("spent_today") is not None:
        lines.append(f"{P_STATS} <b>Spent Today:</b> ₹{balance_res.get('spent_today')}")
      key_info = balance_res.get("key") if isinstance(balance_res.get("key"), dict) else {}
      if key_info.get("label") and not IS_CLONE:
        lines.append(f"{P_KEY} <b>Key:</b> {html.escape(str(key_info.get('label')))}")
    else:
      lines.append(f"{P_NO} <b>Key Status:</b> Failed")
      lines.append(f"{P_WARN} {html.escape(_api_error_text(balance_res))}")

    if isinstance(countries, list):
      in_stock = [c for c in countries if int(c.get('stock') or 0) > 0]
      lines.append(f"{P_PKG} <b>Countries:</b> {len(countries)} ({len(in_stock)} in stock)")
      preview = ""
      for c in in_stock[:5]:
        pcode = str(c.get("code") or "").strip().upper()
        pname = clean_country_name(c.get("name") or pcode)
        preview += (f"{country_flag_html(pcode, pname)} {html.escape(pname)} — ₹{server_sell_price(c.get('price'))}"
                    f" ({c.get('stock')})\n")
      if preview:
        lines.append("")
        lines.append(preview.rstrip())
    else:
      lines.append(f"{P_WARN} Countries: {html.escape(str(countries.get('error')))}")

  lines.append("")
  if _is_reseller_upstream(server_no):
    _eff = _reseller_base_url(server_no)
    lines.append(f"{P_LINK} URL: <code>{html.escape(_mask_url(_eff))}</code> \u00b7 Reseller /v1")
    if _url_host_of(_eff) and _url_host_of(_eff) != _url_host_of(api_url):
      lines.append(f"{P_BELL} <i>Saved URL is a provider default, so the MAIN store URL is used.</i>")
  else:
    lines.append(f"{P_LINK} URL: <code>{html.escape(_mask_url(api_url))}</code>")
  lines.append(f"{P_RATE} Margin: <b>{get_server_margin(server_no):g}%</b>")

  btns = [
    [Button.inline("Test Again", f"adm_srvapi_test|{server_no}")],
    [Button.inline(f"Back to {conf['name']}", f"adm_srvapi_view|{server_no}")],
  ]
  return await e_edit_or_send(event, custom_emoji_text("\n".join(lines)), btns)


def _reset_server_caches(server_no):
  if int(server_no) == 3:
    try:
      _S3_CACHE["services"] = (0, None)
      _S3_CACHE["countries"] = (0, None)
      _S3_CACHE["prices"] = {}
    except Exception:
      pass
  elif int(server_no) == 2:
    try:
      _S2WA_CACHE["countries"] = (0, None)
      _S2WA_CACHE["prices"] = {}
      _S2WA_CACHE["map"] = (0, None)
      _S2WA_CACHE["service"] = (0, None)
    except Exception:
      pass
  else:
    _s2_countries_cache["ts"] = 0
    _s2_countries_cache["data"] = []


class _AdminChatReply:
  """Lets a settings page be re-shown as a fresh message after a text conversation."""
  def __init__(self, chat_id, sender_id):
    self.chat_id = chat_id
    self.sender_id = sender_id

  async def respond(self, msg, buttons=None, parse_mode='html'):
    return await bot.send_message(self.chat_id, msg, buttons=buttons, parse_mode=parse_mode)


# Serialize admin input conversations per chat. Telethon's default exclusive
# conversation raises AlreadyInConversationError on rapid/double button taps.
_ADMIN_CONVERSATION_LOCKS = {}


class _AdminConversationGuard:
  def __init__(self, chat_id, timeout):
    self.chat_id = chat_id
    self.timeout = timeout
    self.lock = _ADMIN_CONVERSATION_LOCKS.setdefault(chat_id, asyncio.Lock())
    self.conversation = None

  async def __aenter__(self):
    await self.lock.acquire()
    try:
      self.conversation = bot.conversation(self.chat_id, timeout=self.timeout, exclusive=False)
      return await self.conversation.__aenter__()
    except Exception:
      self.lock.release()
      raise

  async def __aexit__(self, exc_type, exc, tb):
    try:
      return await self.conversation.__aexit__(exc_type, exc, tb)
    finally:
      if self.lock.locked():
        self.lock.release()


def _admin_conversation(chat_id, timeout=600):
  return _AdminConversationGuard(chat_id, timeout)


def _admin_user_card(target_id):
  row = cur.execute("SELECT balance,total_deposited,joined_date,banned,discount,username,first_name,frozen FROM users WHERE user_id=?", (int(target_id),)).fetchone()
  if not row: return None
  bal, dep, joined, banned, discount, username, first_name, frozen = row
  dep_orders = cur.execute("SELECT COUNT(*),COALESCE(SUM(amount),0) FROM deposits WHERE user_id=? AND lower(status) IN ('approved','success','completed')", (int(target_id),)).fetchone()
  global_stats = cur.execute("SELECT COUNT(*),COALESCE(SUM(amount),0) FROM global_orders WHERE user_id=?", (int(target_id),)).fetchone()
  order_rows = cur.execute("SELECT id,service,amount,status,created_at FROM global_orders WHERE user_id=? ORDER BY id DESC LIMIT 8", (int(target_id),)).fetchall()
  name = (('@'+username) if username else (first_name or 'Unknown'))
  _prot = is_protected_user(target_id); _r = get_restriction(target_id)
  if _prot: _status_label = "ADMIN · PROTECTED"
  elif _r and _r['kind'] == 'banned': _status_label = "BANNED"
  elif _r: _status_label = "FROZEN" + (f" · {_fmt_left(_r['until'] - time.time())} left" if _r.get('until') else " · until unfrozen")
  else: _status_label = "ACTIVE"
  text_lines = [f"<b>USER PROFILE · {html.escape(name)}</b>", f"User ID: <code>{int(target_id)}</code>",
    f"Name: {html.escape(str(first_name or 'N/A'))}", f"Username: {html.escape('@'+username if username else 'Not recorded')}",
    f"Balance: <b>₹{float(bal or 0):.2f}</b>", f"Total Deposited: <b>₹{float(dep or 0):.2f}</b>",
    f"Approved Deposit Records: {dep_orders[0]} · ₹{float(dep_orders[1] or 0):.2f}",
    f"Total Bot Orders: <b>{global_stats[0]}</b> · ₹{float(global_stats[1] or 0):.2f}",
    f"Joined: {html.escape(str(joined or 'N/A'))}", f"Discount: {int(discount or 0)}%",
    f"Status: <b>{_status_label}</b>", "", "<b>Recent Orders</b>"]
  for oid, service, amount, status, created in order_rows:
    text_lines.append(f"ATS-{int(oid):08d} · {html.escape(str(service))} · ₹{float(amount or 0):.2f} · {html.escape(str(status))}")
  buttons = [
    ([Button.inline("Admin · Protected", f"adm_usercard|{target_id}", style="primary")] if _prot else [
      (Button.inline("Unfreeze", f"adm_userunfreeze|{target_id}", style="success") if (_r and _r['kind'] == 'frozen') else Button.inline("Freeze", f"adm_userfreeze|{target_id}", style="danger")),
      (Button.inline("Unban", f"adm_userunban|{target_id}", style="success") if (_r and _r['kind'] == 'banned') else Button.inline("Ban", f"adm_userban|{target_id}", style="danger"))]),
    [Button.inline("Add Funds", f"adm_userfund|{target_id}|add", style="success"), Button.inline("Remove Funds", f"adm_userfund|{target_id}|remove", style="danger")],
    [Button.inline("View User Orders", f"adm_userorders|{target_id}|1", style="primary")],
    [Button.inline("Search Another User", "adm_userinfo", style="primary"), Button.inline("Admin Panel", "adm_adminmain", style="danger")]
  ]
  return "\n".join(text_lines), buttons


def _admin_global_refund(gid, actor_id):
  row = _global_order_row(gid)
  if not row: return False, "Order not found."
  oid, service, ref, owner, amount, status, created = row
  if float(amount or 0) <= 0: return False, "Invalid order amount."
  # Reconcile service-specific refund flags before wallet credit to prevent duplicates.
  if service == 'whatsapp':
    wa = _s2wa_get_order(ref)
    if wa and int(wa.get('refunded') or 0):
      cur.execute("UPDATE global_orders SET refunded=1,status='CANCELLED - REFUNDED' WHERE id=?", (int(oid),)); db.commit()
      return False, "This WhatsApp order was already refunded."
  if service == 'shop' and str(status).upper().find('REFUND') >= 0:
    cur.execute("UPDATE global_orders SET refunded=1 WHERE id=?", (int(oid),)); db.commit()
    return False, "This Shop order is already marked refunded."
  cur.execute("UPDATE global_orders SET refunded=1,status='REFUNDED' WHERE id=? AND COALESCE(refunded,0)=0", (int(oid),))
  if cur.rowcount != 1:
    db.commit(); return False, "This order was already refunded."
  try:
    update_balance(int(owner), float(amount))
    if service == 'whatsapp':
      try: cur.execute("UPDATE s2_wa_orders SET refunded=1,status='CANCELLED' WHERE activation_id=?", (str(ref),))
      except Exception: pass
    db.commit()
    logger.info("ADMIN_GLOBAL_REFUND id=%s actor=%s user=%s amount=%.2f", gid, actor_id, owner, float(amount))
    return True, f"Refunded ₹{float(amount):.2f} to user {owner}."
  except Exception:
    cur.execute("UPDATE global_orders SET refunded=0,status=? WHERE id=?", (str(status), int(oid))); db.commit()
    raise


def _admin_mark_global_complete(gid, actor_id):
  row = _global_order_row(gid)
  if not row: return False, "Order not found."
  oid, service, ref, owner, amount, status, created = row
  if str(status or '').upper().find('REFUND') >= 0:
    return False, "A refunded order cannot be marked complete."
  cur.execute("UPDATE global_orders SET status='COMPLETED' WHERE id=?", (int(oid),))
  try:
    if service == 'smm': cur.execute("UPDATE smm_orders SET status='Completed' WHERE bot_order_id=?", (int(ref),))
    elif service == 'telegram': cur.execute("UPDATE orders SET otp=CASE WHEN otp='' THEN 'COMPLETED' ELSE otp END WHERE id=?", (int(ref),))
    elif service == 'whatsapp': cur.execute("UPDATE s2_wa_orders SET status='COMPLETED' WHERE activation_id=?", (str(ref),))
    elif service == 'shop': cur.execute("UPDATE shop_orders SET status='delivered' WHERE id=? AND lower(status) NOT IN ('cancelled','refunded')", (int(ref),))
    elif service == 'server1': cur.execute("UPDATE s2_orders SET status='completed' WHERE order_id=?", (str(ref),))
    db.commit()
    logger.info("ADMIN_GLOBAL_COMPLETE id=%s actor=%s", gid, actor_id)
    return True, "Order marked COMPLETED. Provider-side completion is not changed unless that service supports it."
  except Exception as ex:
    db.rollback(); return False, str(ex)


def _admin_user_style_card(service, ref):
  """The same message the buyer got at purchase time, for the admin order lookup."""
  try:
    if service == 'server1':
      msg, _b = _s1_purchase_card(str(ref), show_2fa=True, show_batch=True)
      return msg
    if service == 'telegram':
      r = cur.execute("SELECT country,year,price,phone,otp,twofa_pass FROM orders WHERE id=?", (int(ref),)).fetchone()
      if r:
        country, year, price, phone, otp, twofa = r
        gid = _global_order_id_for('telegram', ref)
        return _manual_purchase_text(gid, phone, country, twofa, otp_code=otp,
                                     extra=f"{P_MONEY} <b>Paid:</b> \u20b9{price}\n{P_CAL} <b>Year:</b> {year or '-'}\n")
    if service == 'whatsapp':
      o = _s2wa_get_order(ref)
      if o:
        gid = _global_order_id_for('whatsapp', ref)
        return _wa_purchase_text({"name": o.get('country_name') or ''}, gid, o.get('phone') or '-',
                                 o.get('price_inr') or 0, o.get('id') or '-', code=o.get('code'))
    if service == 's3otp':
      o = _s3_get_order(ref)
      if o:
        gid = _global_order_id_for('s3otp', ref)
        code = str(o.get('code') or '').strip()
        return (
          f"{P_YES} <b>Server 3 OTP Order</b>\n"
          f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n"
          f"{P_PKG} <b>App:</b> {html.escape(str(o.get('service_name') or o.get('service_code') or '-'))}\n"
          f"{P_PHONE} <b>Number:</b> <code>{html.escape(str(o.get('phone') or '-'))}</code>\n"
          f"{P_GLOBE} <b>Country:</b> {html.escape(str(o.get('country_name') or '-'))}\n"
          f"{P_MONEY} <b>Paid:</b> \u20b9{float(o.get('price_inr') or 0):.2f}\n"
          f"{P_ID} <b>Bot Order ID:</b> <code>{html.escape(str(gid or '-'))}</code>\n"
          f"{P_ID} <b>Activation ID:</b> <code>{html.escape(str(o.get('activation_id') or '-'))}</code>\n"
          f"{P_STATS} <b>Status:</b> {html.escape(str(o.get('status') or '-'))}\n"
          + (f"{P_OTP} <b>OTP:</b> <code>{html.escape(_otp_gap(code))}</code>\n" if code else
             f"{P_OTP} <b>OTP:</b> Not received yet\n"))
  except Exception as ex:
    logger.warning("admin user-style card failed: %s", ex)
  return None


async def admin_actions(event):
  data_full = event.data.decode()
  if not data_full.startswith("adm_"): return
  uid = event.sender_id
  action_data = data_full[4:]
  chat = event.chat_id

  if IS_CLONE and action_data in ("backupusr", "restoreusr", "clonebot"):
    return await safe_callback_answer(event, "This option is not available in a cloned bot.", alert=True)

  # OWNER-ONLY: Servers APIs, SMM API, Clone / Manage Cloned Bots, Backup / Restore, Manage Admins, Automation.
  if uid != ADMIN_ID and (action_data in OWNER_ONLY_EXACT or action_data.startswith(OWNER_ONLY_PREFIXES)):
    return await safe_callback_answer(event, "Only the owner can use this option.", alert=True)

  if action_data.startswith("srvapi_lowbal|") and has_perm(uid, 'p_settings'):
    return await _lowbal_set(event, uid, chat, action_data)
  if action_data.startswith("cbm|"):
    return await _cbm_router(event, uid, chat, action_data)
  if action_data.startswith("apik|"):
    return await _api_admin_router(event, uid, chat, action_data)

  if action_data.startswith("users|"):
    page = max(1, int(action_data.split("|",1)[1] or 1))
    total = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    rows = cur.execute("SELECT user_id,username,first_name,balance,banned,frozen FROM users ORDER BY user_id DESC LIMIT 10 OFFSET ?", ((page-1)*10,)).fetchall()
    lines = [f"<b>ALL USERS · PAGE {page}</b>", f"Total users: <b>{total}</b>", ""]
    buttons=[]
    for tuid, uname, fname, bal, banned, frozen in rows:
      if not uname and not fname:
        try:
          _ent=await bot.get_entity(int(tuid))
          uname=getattr(_ent,'username','') or ''
          fname=getattr(_ent,'first_name','') or ''
          cur.execute("UPDATE users SET username=?,first_name=? WHERE user_id=?",(uname,fname,int(tuid)))
        except Exception: pass
      label = ('@'+uname) if uname else (fname or str(tuid))
      lines.append(f"<code>{tuid}</code> · {html.escape(str(label))} · ₹{float(bal or 0):.2f} · {'FROZEN' if frozen else ('BANNED' if banned else 'ACTIVE')}")
      buttons.append([Button.inline(f"{str(label)[:22]} · {tuid}", f"adm_usercard|{tuid}", style="primary")])
    nav=[]
    if page>1: nav.append(Button.inline("◀ Prev", f"adm_users|{page-1}", style="danger"))
    if page*10<total: nav.append(Button.inline("Next ▶", f"adm_users|{page+1}", style="success"))
    if nav: buttons.append(nav)
    buttons += [[Button.inline("Frozen / Banned List", "adm_restricted|1", style="danger")],[Button.inline("User Info / Search", "adm_userinfo", style="success")],[Button.inline("Admin Panel", "adm_adminmain", style="danger")]]
    db.commit()
    return await event.edit("\n".join(lines), buttons=buttons, parse_mode="html")

  if action_data.startswith("usercard|"):
    target=int(action_data.split("|",1)[1]); card=_admin_user_card(target)
    if not card: return await safe_callback_answer(event,"User not found.",alert=True)
    return await event.edit(card[0], buttons=card[1], parse_mode="html")

  if action_data.startswith("userorders|"):
    _, target_s, page_s = action_data.split("|",2); target=int(target_s); page=max(1,int(page_s))
    total=cur.execute("SELECT COUNT(*) FROM global_orders WHERE user_id=?",(target,)).fetchone()[0]
    rows=cur.execute("SELECT id,service,amount,status FROM global_orders WHERE user_id=? ORDER BY id DESC LIMIT 10 OFFSET ?",(target,(page-1)*10)).fetchall()
    lines=[f"<b>USER {target} · ORDERS {page}</b>",f"Total: {total}",""]; buttons=[]
    for oid,svc,amt,st in rows:
      gid=f"ATS-{int(oid):08d}"; lines.append(f"{gid} · {html.escape(str(svc))} · ₹{float(amt or 0):.2f} · {html.escape(str(st))}")
      buttons.append([Button.inline(gid,f"adm_globalview|{gid}",style="primary")])
    nav=[]
    if page>1: nav.append(Button.inline("◀ Prev",f"adm_userorders|{target}|{page-1}",style="danger"))
    if page*10<total: nav.append(Button.inline("Next ▶",f"adm_userorders|{target}|{page+1}",style="success"))
    if nav: buttons.append(nav)
    buttons.append([Button.inline("Back to User",f"adm_usercard|{target}",style="primary")])
    return await event.edit("\n".join(lines),buttons=buttons,parse_mode="html")

  if action_data.startswith("userfreeze|"):
    target = int(action_data.split("|", 1)[1])
    if is_protected_user(target): return await safe_callback_answer(event, "Admins cannot be frozen or banned.", alert=True)
    if not cur.execute("SELECT 1 FROM users WHERE user_id=?", (target,)).fetchone(): return await safe_callback_answer(event, "User not found.", alert=True)
    return await event.edit(
      f"<b>FREEZE USER</b> <code>{target}</code>\n\nThe user will see <i>\"You are under investigation. Please wait some time.\"</i> and cannot buy or use any service.\n\nChoose freeze duration:",
      buttons=[[Button.inline("1 Hour", f"adm_userfreezego|{target}|1", style="primary"), Button.inline("6 Hours", f"adm_userfreezego|{target}|6", style="primary")],
               [Button.inline("24 Hours", f"adm_userfreezego|{target}|24", style="success"), Button.inline("7 Days", f"adm_userfreezego|{target}|168", style="success")],
               [Button.inline("Until I Unfreeze", f"adm_userfreezego|{target}|0", style="danger")],
               [Button.inline("Cancel", f"adm_usercard|{target}", style="primary")]], parse_mode="html")

  if action_data.startswith("userfreezego|"):
    _, target_s, hours_s = action_data.split("|", 2); target = int(target_s); hours = int(hours_s)
    if is_protected_user(target): return await safe_callback_answer(event, "Admins cannot be frozen or banned.", alert=True)
    until = int(time.time() + hours * 3600) if hours > 0 else 0
    cur.execute("UPDATE users SET frozen=1, freeze_until=?, freeze_reason=?, restricted_by=?, restricted_at=? WHERE user_id=?",
                (until, FREEZE_DEFAULT_REASON, uid, int(time.time()), target)); db.commit()
    _mod_log(target, uid, "freeze", f"{hours}h" if hours else "until unfrozen")
    logger.info("ADMIN_FREEZE target=%s actor=%s hours=%s", target, uid, hours)
    await _notify_user(target, _restriction_text({'kind': 'frozen', 'until': until, 'reason': FREEZE_DEFAULT_REASON}))
    await safe_callback_answer(event, "User frozen.")
    card = _admin_user_card(target)
    return await event.edit(card[0], buttons=card[1], parse_mode="html")

  if action_data.startswith("userunfreeze|"):
    target = int(action_data.split("|", 1)[1])
    cur.execute("UPDATE users SET frozen=0, freeze_until=0 WHERE user_id=?", (target,)); db.commit()
    _mod_log(target, uid, "unfreeze")
    logger.info("ADMIN_UNFREEZE target=%s actor=%s", target, uid)
    await _notify_user(target, f"{P_YES} <b>Your account is active again.</b>\nThe review is complete. You can use the bot normally now. Send /start.", support=False)
    await safe_callback_answer(event, "User unfrozen.")
    card = _admin_user_card(target)
    return await event.edit(card[0], buttons=card[1], parse_mode="html")

  if action_data.startswith("userban|"):
    target = int(action_data.split("|", 1)[1])
    if is_protected_user(target): return await safe_callback_answer(event, "Admins cannot be frozen or banned.", alert=True)
    return await event.edit(f"<b>BAN USER</b> <code>{target}</code>\n\nThe user will lose access to the whole bot. Confirm?",
      buttons=[[Button.inline("Yes, Ban", f"adm_userbanyes|{target}", style="danger")], [Button.inline("Cancel", f"adm_usercard|{target}", style="primary")]], parse_mode="html")

  if action_data.startswith("userbanyes|"):
    target = int(action_data.split("|", 1)[1])
    if is_protected_user(target): return await safe_callback_answer(event, "Admins cannot be frozen or banned.", alert=True)
    cur.execute("UPDATE users SET banned=1, restricted_by=?, restricted_at=? WHERE user_id=?", (uid, int(time.time()), target)); db.commit()
    _mod_log(target, uid, "ban")
    logger.info("ADMIN_BAN target=%s actor=%s", target, uid)
    await _notify_user(target, _restriction_text({'kind': 'banned', 'until': 0, 'reason': ''}))
    await safe_callback_answer(event, "User banned.")
    card = _admin_user_card(target)
    return await event.edit(card[0], buttons=card[1], parse_mode="html")

  if action_data.startswith("userunban|"):
    target = int(action_data.split("|", 1)[1])
    cur.execute("UPDATE users SET banned=0 WHERE user_id=?", (target,)); db.commit()
    _mod_log(target, uid, "unban")
    logger.info("ADMIN_UNBAN target=%s actor=%s", target, uid)
    await _notify_user(target, f"{P_YES} <b>Your access has been restored.</b> Send /start.", support=False)
    await safe_callback_answer(event, "User unbanned.")
    card = _admin_user_card(target)
    return await event.edit(card[0], buttons=card[1], parse_mode="html")

  if action_data.startswith("restricted|"):
    page = max(1, int(action_data.split("|", 1)[1] or 1))
    total = cur.execute("SELECT COUNT(*) FROM users WHERE COALESCE(banned,0)=1 OR COALESCE(frozen,0)=1").fetchone()[0]
    rows = cur.execute("SELECT user_id,username,first_name,COALESCE(banned,0),COALESCE(freeze_until,0) FROM users WHERE COALESCE(banned,0)=1 OR COALESCE(frozen,0)=1 ORDER BY restricted_at DESC LIMIT 10 OFFSET ?", ((page-1)*10,)).fetchall()
    lines = [f"<b>FROZEN / BANNED USERS · PAGE {page}</b>", f"Total: <b>{total}</b>", ""]
    buttons = []
    for tuid, uname, fname, is_ban, until in rows:
      label = ('@' + uname) if uname else (fname or str(tuid))
      state = "BANNED" if is_ban else ("FROZEN · " + _fmt_left(until - time.time()) + " left" if until else "FROZEN")
      lines.append(f"<code>{tuid}</code> · {html.escape(str(label))} · {state}")
      buttons.append([Button.inline(f"{str(label)[:20]} · {state.split(' ')[0]}", f"adm_usercard|{tuid}", style="danger" if is_ban else "primary")])
    if not rows: lines.append("No frozen or banned users.")
    nav = []
    if page > 1: nav.append(Button.inline("◀ Prev", f"adm_restricted|{page-1}", style="primary"))
    if page * 10 < total: nav.append(Button.inline("Next ▶", f"adm_restricted|{page+1}", style="success"))
    if nav: buttons.append(nav)
    buttons.append([Button.inline("All Users", "adm_users|1", style="success")])
    buttons.append([Button.inline("Admin Panel", "adm_adminmain", style="danger")])
    return await event.edit("\n".join(lines), buttons=buttons, parse_mode="html")

  if action_data.startswith("userfund|"):
    _,target_s,mode=action_data.split("|",2); target=int(target_s)
    async with _admin_conversation(chat,timeout=180) as conv:
      await conv.send_message(f"Enter amount to {'add to' if mode=='add' else 'deduct from'} user {target} (numbers only; /cancel to abort).")
      try: amount=float((await conv.get_response()).raw_text.strip())
      except Exception: return
      if amount<=0 or amount>100000000: return await conv.send_message("Invalid amount.")
      row=cur.execute("SELECT 1 FROM users WHERE user_id=?",(target,)).fetchone()
      if not row: return await conv.send_message("User not found.")
      delta=amount if mode=='add' else -amount
      if mode=='remove':
        bal=cur.execute("SELECT balance FROM users WHERE user_id=?",(target,)).fetchone()[0]
        if float(bal or 0)<amount: return await conv.send_message("Insufficient user balance; no funds removed.")
      update_balance(target,delta)
      logger.info("ADMIN_USER_FUNDS target=%s actor=%s delta=%.2f",target,uid,delta)
      await conv.send_message(f"Wallet updated: {'+' if delta>0 else '-'}₹{amount:.2f}")
    card=_admin_user_card(target)
    return await bot.send_message(chat,card[0],buttons=card[1],parse_mode="html")

  if action_data.startswith("globalrefund|"):
    gid=action_data.split("|",1)[1]
    row=_global_order_row(gid)
    if not row: return await safe_callback_answer(event,"Order not found.",alert=True)
    oid,svc,ref,owner,amount,status,created=row
    return await event.edit(f"<b>Confirm wallet refund?</b>\nOrder: <code>{html.escape(gid)}</code>\nUser: <code>{owner}</code>\nAmount: <b>₹{float(amount or 0):.2f}</b>\n\nThis credits the user's wallet once. Confirm only if refund is due.",buttons=[[Button.inline("CONFIRM REFUND",f"adm_globalrefundyes|{gid}",style="danger")],[Button.inline("Back",f"adm_globalview|{gid}",style="primary")]],parse_mode="html")

  if action_data.startswith("globalrefundyes|"):
    gid=action_data.split("|",1)[1]
    ok,msg=_admin_global_refund(gid,uid)
    await safe_callback_answer(event,msg,alert=True)
    row=_global_order_row(gid)
    if row:
      oid,svc,ref,owner,amount,status,created=row
      return await event.edit(f"<b>{html.escape(gid)} · {html.escape(str(svc).upper())}</b>\nUser: <code>{owner}</code>\nAmount: ₹{float(amount or 0):.2f}\nStatus: {html.escape(str(status))}\nRefund: {'DONE' if ok else html.escape(msg)}",buttons=[[Button.inline("Back to Order",f"adm_globalview|{gid}",style="primary")],[Button.inline("All Orders","adm_globalsales|1",style="danger")]],parse_mode="html")
    return

  if action_data.startswith("globalcomplete|"):
    gid=action_data.split("|",1)[1]; ok,msg=_admin_mark_global_complete(gid,uid)
    await safe_callback_answer(event,msg,alert=True)
    return await admin_actions(type('E',(),{'data':('adm_globalview|'+gid).encode(),'sender_id':uid,'chat_id':chat,'edit':event.edit,'respond':event.respond})())

  if action_data.startswith("globalrefill|"):
    gid=action_data.split("|",1)[1]; row=_global_order_row(gid)
    if not row or row[1]!='smm': return await safe_callback_answer(event,"Refill is only available for SMM orders.",alert=True)
    ref=row[2]; smm=cur.execute("SELECT smm_order_id FROM smm_orders WHERE bot_order_id=?",(int(ref),)).fetchone()
    if not smm or not smm[0]: return await safe_callback_answer(event,"SMM provider order ID unavailable.",alert=True)
    api_url=get_setting('smm_api_url',''); api_key=get_setting('smm_api_key','')
    result=await asyncio.to_thread(refill_smm_order_api,api_url,api_key,smm[0])
    await safe_callback_answer(event, "Refill request sent." if isinstance(result,dict) and not result.get('error') else f"Refill response: {str(result)[:180]}",alert=True)
    return

  if action_data.startswith("globalotp|"):
    gid=action_data.split("|",1)[1]; row=_global_order_row(gid)
    if not row: return await safe_callback_answer(event,"Order not found.",alert=True)
    if row[1]=='telegram':
      detail=cur.execute("SELECT otp,phone FROM orders WHERE id=?",(int(row[2]),)).fetchone()
      if not detail: return await safe_callback_answer(event,"Telegram order details unavailable.",alert=True)
      return await safe_callback_answer(event,f"{detail[1]} · OTP/Status: {detail[0] or 'Not available'}",alert=True)
    if row[1]=='server1':
      r1=cur.execute("SELECT account_no,number,COALESCE(code,'') FROM s2_orders WHERE order_id=?",(str(row[2]),)).fetchone()
      if not r1 or not r1[0]: return await safe_callback_answer(event,"Account not ready yet.",alert=True)
      res=await _s1_get_code(str(row[2]),r1[0],deep=True)
      if isinstance(res,dict) and res.get('ok') and res.get('code'):
        code=str(res['code'])
        try: cur.execute("UPDATE s2_orders SET code=? WHERE order_id=?",(code,str(row[2]))); db.commit()
        except Exception: pass
        return await safe_callback_answer(event,f"{r1[1]} · Latest OTP: {code}",alert=True)
      _why=_api_error_text(res) if isinstance(res,dict) else 'No response'
      return await safe_callback_answer(event,f"No new OTP now. Last saved: {r1[2] or 'none'} · {str(_why)[:90]}",alert=True)
    if row[1]=='s3otp':
      o3=_s3_get_order(row[2]) or {}
      try:
        raw=str(await asyncio.to_thread(_s3_tiger().status,row[2])).strip()
        if raw.startswith('STATUS_OK:') or raw.startswith('STATUS_WAIT_RETRY:'):
          code=raw.split(':',1)[1].strip()
          if code: _s3_update_order(row[2],code=code)
          return await safe_callback_answer(event,f"{o3.get('phone','')} · Latest OTP: {code}",alert=True)
        return await safe_callback_answer(event,f"Provider status: {raw[:160]} · saved OTP: {o3.get('code') or 'none'}",alert=True)
      except Exception as ex:
        return await safe_callback_answer(event,f"OTP check failed: {str(ex)[:150]}",alert=True)
    if row[1]!='whatsapp': return await safe_callback_answer(event,"OTP check is not supported for this service.",alert=True)
    order=_s2wa_get_order(row[2]) or {}
    try:
      raw=await asyncio.to_thread(_S2waTiger(_s2wa_api_key()).status,row[2])
      if str(raw).startswith('STATUS_OK:'):
        code=str(raw).split(':',1)[1]; _s2wa_update_order(row[2],code=code)
        return await safe_callback_answer(event,f"OTP received: {code}",alert=True)
      await safe_callback_answer(event,f"Provider status: {str(raw)[:160]}",alert=True)
    except Exception as ex: await safe_callback_answer(event,f"OTP check failed: {str(ex)[:150]}",alert=True)
    return

  if action_data.startswith("globalfile|"):
    gid=action_data.split("|",1)[1]; row=_global_order_row(gid)
    if row and row[1]=='server1':
      _ok,_note=await _send_s1_session_file_inner(chat,str(row[2]),mark_sent=False)
      return await safe_callback_answer(event,"Session file sent to admin chat." if _ok else str(_note)[:190],alert=not _ok)
    if not row or row[1]!='telegram': return await safe_callback_answer(event,"Session file is only available for Telegram orders.",alert=True)
    detail=cur.execute("SELECT session_file,phone FROM orders WHERE id=?",(int(row[2]),)).fetchone()
    if not detail or not detail[0] or not os.path.exists(str(detail[0])): return await safe_callback_answer(event,"Session file is not available on the server.",alert=True)
    await safe_callback_answer(event,"Sending session file to admin chat.",alert=False)
    return await bot.send_file(chat,str(detail[0]),caption=f"{gid} · {detail[1]}")

  if action_data.startswith("globalsales|"):
    try: page = max(1, int(action_data.split("|",1)[1]))
    except Exception: page = 1
    total = cur.execute("SELECT COUNT(*) FROM global_orders").fetchone()[0]
    rows = cur.execute("SELECT id,service,local_ref,user_id,amount,status FROM global_orders ORDER BY id DESC LIMIT 10 OFFSET ?", ((page-1)*10,)).fetchall()
    lines = ["<b>ALL SALES / BOT ORDERS</b>", "━━━━━━━━━━━━━━━━━━", f"Total orders: <b>{total}</b>", ""]
    btns = []
    for oid, service, ref, owner, amount, status in rows:
      gid = f"ATS-{int(oid):08d}"
      lines.append(f"<code>{gid}</code> · {html.escape(str(service).upper())} · ₹{float(amount or 0):.2f} · {html.escape(str(status or 'UNKNOWN'))}")
      btns.append([Button.inline(f"{gid} | {str(service).upper()} | ₹{float(amount or 0):.0f}", f"adm_globalview|{gid}", style="primary")])
    if not rows: lines.append("No bot orders found yet.")
    nav=[]
    if page > 1: nav.append(Button.inline("◀ Prev", f"adm_globalsales|{page-1}", style="danger"))
    if page*10 < total: nav.append(Button.inline("Next ▶", f"adm_globalsales|{page+1}", style="success"))
    if nav: btns.append(nav)
    btns.append([Button.inline("Mark All Complete", "adm_globalcompleteall", style="success")])
    btns.append([Button.inline("Check Order ID", "adm_globalcheck", style="success")])
    btns.append([Button.inline("Back to Admin", "adm_adminmain", style="danger")])
    return await event.edit("\n".join(lines), buttons=btns, parse_mode="html")

  if action_data.startswith("globalview|"):
    gid = action_data.split("|",1)[1]
    row = _global_order_row(gid)
    if not row: return await safe_callback_answer(event, "Bot order not found.", alert=True)
    oid, service, ref, owner, amount, status, created = row
    _rf_row = cur.execute("SELECT refunded FROM global_orders WHERE id=?", (int(oid),)).fetchone()
    _is_refunded = bool(_rf_row and _rf_row[0])
    details = [f"<b>BOT ORDER {html.escape(gid)}</b>", "━━━━━━━━━━━━━━━━━━",
               f"Service: <b>{html.escape(str(service).upper())}</b>", f"User ID: <code>{owner}</code>",
               f"Amount: <b>₹{float(amount or 0):.2f}</b>", f"Status: <b>{html.escape(str(status))}</b>",
               f"Created: {html.escape(str(created))}", f"Refunded: {'Yes' if _is_refunded else 'No'}", f"Local/provider reference: <code>{html.escape(str(ref))}</code>"]
    _ucard = _admin_user_style_card(service, ref) if service in ('server1','telegram','whatsapp','s3otp') else None
    if _ucard:
      details = [f"<b>BOT ORDER {html.escape(gid)}</b>", "━━━━━━━━━━━━━━━━━━",
                 f"User ID: <code>{owner}</code>", f"Status: <b>{html.escape(str(status))}</b>",
                 f"Created: {html.escape(str(created))}", f"Refunded: {'Yes' if _is_refunded else 'No'}",
                 f"Local/provider reference: <code>{html.escape(str(ref))}</code>",
                 "━━━━━━━━━━━━━━━━━━", "", _ucard]
    try:
      if _ucard:
        pass
      elif service == 'smm':
        r=cur.execute("SELECT o.*,s.name FROM smm_orders o LEFT JOIN smm_services s ON s.service_id=o.service_id WHERE o.bot_order_id=?", (int(ref),)).fetchone()
        if r:
          details += [f"SMM service: {html.escape(str(r[9] or r[2]))}", f"Panel order ID: <code>{html.escape(str(r[6]))}</code>", f"Link: {html.escape(str(r[3]))}", f"Quantity: {r[4]}", f"Order status: {html.escape(str(r[7]))}"]
      elif service == 'whatsapp':
        r=_s2wa_get_order(ref)
        if r:
          details += [f"Country: {html.escape(str(r.get('country_name')))}", f"Number: <code>{html.escape(str(r.get('phone')))}</code>", f"Activation ID: <code>{html.escape(str(r.get('activation_id')))}</code>", f"OTP: <code>{html.escape(str(r.get('code') or 'Not received'))}</code>", f"Refunded: {'Yes' if r.get('refunded') else 'No'}"]
      elif service == 'telegram':
        r=cur.execute("SELECT country,year,price,phone,otp,session_file,twofa_pass FROM orders WHERE id=?", (int(ref),)).fetchone()
        if r:
          country,year,price,phone,otp,sess,twofa=r
          details += [f"Country: {html.escape(str(country))}", f"Year: {year}", f"Phone: <code>{html.escape(str(phone))}</code>", f"OTP/status: <code>{html.escape(str(otp))}</code>", f"2FA: <code>{html.escape(str(twofa))}</code>", f"Session file: <code>{html.escape(str(sess or 'Not stored'))}</code>"]
      elif service == 'shop':
        r=cur.execute("SELECT product_name,price,status,delivery FROM shop_orders WHERE id=?", (int(ref),)).fetchone()
        if r:
          details += [f"Product: {html.escape(str(r[0]))}", f"Shop status: {html.escape(str(r[2]))}", f"Delivery: {html.escape(str(r[3] or 'Not delivered'))}"]
      elif service == 'server1':
        r=cur.execute("SELECT country_name,number,price,status,code,password,account_no FROM s2_orders WHERE order_id=?", (str(ref),)).fetchone()
        if r:
          details += [f"Country: {html.escape(str(r[0]))}", f"Number: <code>{html.escape(str(r[1]))}</code>", f"Order status: {html.escape(str(r[3]))}", f"OTP: <code>{html.escape(str(r[4] or 'Not received'))}</code>", f"Password: <code>{html.escape(str(r[5] or 'N/A'))}</code>", f"Account ref: <code>{html.escape(str(r[6] or 'N/A'))}</code>"]
    except Exception as ex: details.append(f"Detail lookup warning: {html.escape(str(ex)[:180])}")
    action_buttons = [[Button.inline("Refund Wallet", f"adm_globalrefund|{gid}", style="danger"), Button.inline("Mark Complete", f"adm_globalcomplete|{gid}", style="success")]]
    if service == 'smm': action_buttons.append([Button.inline("Request Refill", f"adm_globalrefill|{gid}", style="primary")])
    if service in ('whatsapp','telegram','server1','s3otp'): action_buttons.append([Button.inline("Check Latest OTP", f"adm_globalotp|{gid}", style="primary")])
    if service in ('telegram','server1'): action_buttons.append([Button.inline("Get Session File", f"adm_globalfile|{gid}", style="primary")])
    action_buttons += [[Button.inline("User Profile", f"adm_usercard|{owner}", style="success")],[Button.inline("Back to All Orders", "adm_globalsales|1", style="primary")],[Button.inline("Admin Panel", "adm_adminmain", style="danger")]]
    return await event.edit(custom_emoji_text("\n".join(details)) if _ucard else "\n".join(details), buttons=action_buttons, parse_mode="html")

  if action_data == "globalcheck":
    async with _admin_conversation(chat, timeout=180) as conv:
      await conv.send_message("Send the Bot Order ID (example: ATS-00000001).")
      try: response = await conv.get_response()
      except Exception: return
      gid = response.raw_text.strip()
    row = _global_order_row(gid)
    if not row: return await bot.send_message(chat, "Order ID not found. Check the ID and try again.")
    oid, service, ref, owner, amount, status, created = row
    summary = [f"<b>ORDER FOUND · {html.escape(gid)}</b>", f"Service: <b>{html.escape(str(service).upper())}</b>",
               f"User: <code>{owner}</code>", f"Amount: <b>₹{float(amount or 0):.2f}</b>",
               f"Status: <b>{html.escape(str(status))}</b>", f"Created: {html.escape(str(created))}"]
    _ucard = _admin_user_style_card(service, ref) if service in ('server1','telegram','whatsapp','s3otp') else None
    if _ucard:
      summary = [f"<b>ORDER FOUND · {html.escape(gid)}</b>", f"User: <code>{owner}</code>",
                 f"Status: <b>{html.escape(str(status))}</b>", f"Created: {html.escape(str(created))}",
                 f"Local/provider reference: <code>{html.escape(str(ref))}</code>",
                 "━━━━━━━━━━━━━━━━━━", "", _ucard]
    try:
      if _ucard:
        pass
      elif service == 'whatsapp':
        detail = _s2wa_get_order(ref) or {}
        summary += [f"Number: <code>{html.escape(str(detail.get('phone') or 'N/A'))}</code>",
                    f"OTP: <code>{html.escape(str(detail.get('code') or 'Not received'))}</code>",
                    f"Refunded: {'Yes' if detail.get('refunded') else 'No'}"]
      elif service == 'telegram':
        detail = cur.execute("SELECT country,year,phone,otp,session_file,twofa_pass FROM orders WHERE id=?", (int(ref),)).fetchone()
        if detail:
          summary += [f"Country: {html.escape(str(detail[0]))}", f"Phone: <code>{html.escape(str(detail[2]))}</code>",
                      f"OTP/status: <code>{html.escape(str(detail[3]))}</code>",
                      f"Session: <code>{html.escape(str(detail[4] or 'N/A'))}</code>",
                      f"2FA: <code>{html.escape(str(detail[5] or 'N/A'))}</code>"]
      elif service == 'server1':
        detail = cur.execute("SELECT country_name,number,status,code,password FROM s2_orders WHERE order_id=?", (str(ref),)).fetchone()
        if detail: summary += [f"Country: {html.escape(str(detail[0]))}", f"Number: <code>{html.escape(str(detail[1]))}</code>",
                               f"OTP: <code>{html.escape(str(detail[3] or 'Not received'))}</code>", f"Password: <code>{html.escape(str(detail[4] or 'N/A'))}</code>"]
      elif service == 'shop':
        detail = cur.execute("SELECT product_name,price,status,delivery FROM shop_orders WHERE id=?", (int(ref),)).fetchone()
        if detail: summary += [f"Product: {html.escape(str(detail[0]))}", f"Shop status: {html.escape(str(detail[2]))}", f"Delivery: {html.escape(str(detail[3] or 'Not delivered'))}"]
      elif service == 'smm':
        detail = cur.execute("SELECT o.link,o.quantity,o.smm_order_id,o.status,s.name FROM smm_orders o LEFT JOIN smm_services s ON s.service_id=o.service_id WHERE o.bot_order_id=?", (int(ref),)).fetchone()
        if detail: summary += [f"Service: {html.escape(str(detail[4] or 'N/A'))}", f"Panel ID: <code>{html.escape(str(detail[2]))}</code>",
                               f"Link: {html.escape(str(detail[0]))}", f"Quantity: {detail[1]}", f"Provider status: {html.escape(str(detail[3]))}"]
    except Exception as ex: summary.append(f"Detail warning: {html.escape(str(ex)[:120])}")
    return await bot.send_message(chat, custom_emoji_text("\n".join(summary)) if _ucard else "\n".join(summary), parse_mode="html", buttons=[[Button.inline("Full Order Details", f"adm_globalview|{gid}", style="success")],[Button.inline("All Orders", "adm_globalsales|1", style="primary")]])
  
  if action_data == "adminmain":
    await event.delete()
    class FakeEvent: chat_id = chat; sender_id = uid
    return await admin_panel_handler(FakeEvent())

  if action_data == "togglebot" and has_perm(uid, 'p_settings'):
    new_status = set_bot_status(BOT_STATUS_NEXT.get(get_bot_status(), 'maintenance'))
    _alert = {'on': "Bot is now ON - everyone can use it.",
              'maintenance': "Maintenance mode ON - only admins can use the bot.",
              'off': "Bot is now OFF - only admins can use it."}[new_status]
    await safe_callback_answer(event, _alert, alert=True)
    class FakeEvent: chat_id = chat; sender_id = uid
    await admin_panel_handler(FakeEvent())
    await event.delete()
    return

  elif action_data == "forcechannels":
    rows = cur.execute("SELECT id, channel_id, title FROM force_channels").fetchall()
    msg = f"{P_USERS} <b>Manage Force Channels</b>\n\n"
    if not rows: msg += "No force channels added yet."
    else: msg += "Tap a channel to remove it or change its link."
    btns = [[Button.inline(str(r[2] or r[1])[:40], f"adm_fch|{r[0]}", icon_custom_emoji_id="5832538679997895284")] for r in rows]
    btns.append([Button.inline("Add Channel", "adm_add_fchan")])
    btns.append([Button.inline("Back to Admin", "adm_adminmain")])
    return await event.edit(custom_emoji_text(msg), buttons=btns)

  elif action_data.startswith("fch|"):
    fid = int(action_data.split("|")[1])
    r = cur.execute("SELECT id, channel_id, invite_url, title FROM force_channels WHERE id=?", (fid,)).fetchone()
    if not r:
      return await safe_callback_answer(event, "Channel not found.", alert=True)
    msg = (f"{P_GLOBE} <b>{html.escape(str(r[3] or 'Channel'))}</b>\n\n"
           f"{P_ID} Chat ID: <code>{html.escape(str(r[1]))}</code>\n"
           f"{P_LINK} Link: {html.escape(str(r[2] or ''))}")
    btns = [
      [Button.inline("Remove Channel", f"adm_fchdel|{r[0]}")],
      [Button.inline("Change Link", f"adm_fchlink|{r[0]}", icon_custom_emoji_id="5834886399316201457")],
      [Button.inline("Back", "adm_forcechannels")]
    ]
    return await event.edit(custom_emoji_text(msg), buttons=btns)

  elif action_data.startswith("fchdel|"):
    fid = int(action_data.split("|")[1])
    r = cur.execute("SELECT channel_id FROM force_channels WHERE id=?", (fid,)).fetchone()
    if r:
      cur.execute("DELETE FROM force_join_requests WHERE channel_id=?", (str(r[0]),))
    cur.execute("DELETE FROM force_channels WHERE id=?", (fid,))
    db.commit()
    await safe_callback_answer(event, "Force channel removed!", alert=True)
    rows = cur.execute("SELECT id, channel_id, title FROM force_channels").fetchall()
    msg = f"{P_USERS} <b>Manage Force Channels</b>\n\n" + ("Tap a channel to remove it or change its link." if rows else "No force channels added yet.")
    btns = [[Button.inline(str(x[2] or x[1])[:40], f"adm_fch|{x[0]}", icon_custom_emoji_id="5832538679997895284")] for x in rows]
    btns.append([Button.inline("Add Channel", "adm_add_fchan")])
    btns.append([Button.inline("Back to Admin", "adm_adminmain")])
    return await event.edit(custom_emoji_text(msg), buttons=btns)

  elif action_data == "paymentmethods" and has_perm(uid, 'p_settings'):
    return await _render_payment_methods(event)

  elif action_data.startswith("pm|") and has_perm(uid, 'p_settings'):
    return await _render_payment_method_page(event, action_data.split("|", 1)[1])

  elif action_data == "bharatpe_test" and has_perm(uid, 'p_settings'):
    await safe_callback_answer(event, "Testing connection...")
    _ok, _info = await bharatpe_test_connection()
    await bot.send_message(event.chat_id, custom_emoji_text(
      f"{P_YES if _ok else P_NO} <b>BharatPe test:</b> {html.escape(_info)}"))
    return

  elif action_data == "toggle_fampay" and has_perm(uid, 'p_settings'):
    set_setting('fampay_enabled', 'off' if payment_enabled('fampay_enabled') else 'on')
    await safe_callback_answer(event, "FamPay Automatic: " + ("ON" if payment_enabled('fampay_enabled') else "OFF"))
    return await _render_payment_method_page(event, 'fampay')

  elif action_data == "toggle_bharatpe" and has_perm(uid, 'p_settings'):
    if not payment_enabled('bharatpe_enabled') and not (get_bharatpe_upi() and bharatpe_api_ready()):
      return await safe_callback_answer(event, "First set the BharatPe UPI ID & Name and the Merchant ID & Token.", alert=True)
    set_setting('bharatpe_enabled', 'off' if payment_enabled('bharatpe_enabled') else 'on')
    await safe_callback_answer(event, "BharatPe Automatic: " + ("ON" if payment_enabled('bharatpe_enabled') else "OFF"))
    return await _render_payment_method_page(event, 'bharatpe')

  elif action_data == "set_bharatpe_api" and has_perm(uid, 'p_settings'):
    await event.delete()
    async with _admin_conversation(chat, timeout=300) as conv:
      async def _ask_bp(txt):
        await conv.send_message(custom_emoji_text(txt + "\n\n<i>(Type /cancel to abort. Your message is deleted right after it is read.)</i>"))
        r = await conv.get_response()
        v = (r.raw_text or '').strip()
        try: await r.delete()
        except Exception: pass
        if v.lower() == '/cancel':
          raise ValueError
        return v
      try:
        mid = await _ask_bp(f"{P_KEY} <b>Send your BharatPe Merchant ID</b> (numbers):")
        if not re.fullmatch(r"\d{4,20}", mid):
          return await conv.send_message(custom_emoji_text(f"{P_NO} <b>Invalid Merchant ID.</b> Nothing saved."))
        tok = await _ask_bp(f"{P_KEY} <b>Send your BharatPe Token:</b>")
        if not re.fullmatch(r"[A-Za-z0-9._\-]{16,300}", tok):
          return await conv.send_message(custom_emoji_text(f"{P_NO} <b>Invalid token.</b> Nothing saved."))
        set_setting('bharatpe_merchant_id', mid)
        set_setting('bharatpe_token', tok)
        await conv.send_message(custom_emoji_text(
          f"{P_YES} <b>BharatPe API saved.</b>\n\nMerchant ID: <code>{html.escape(_mask_secret(mid))}</code>\n"
          f"Token: <code>{html.escape(_mask_secret(tok, 3))}</code>\n\n"
          f"Payments are now verified automatically. Users never see this."))
      except ValueError:
        await conv.send_message("Cancelled.")
    return

  elif action_data == "toggle_manual" and has_perm(uid, 'p_settings'):
    set_setting('manual_enabled', 'off' if payment_enabled('manual_enabled') else 'on')
    await safe_callback_answer(event, "UPI Manual: " + ("ON" if payment_enabled('manual_enabled') else "OFF"))
    return await _render_payment_method_page(event, 'manual')

  elif action_data == "toggle_usdt" and has_perm(uid, 'p_settings'):
    set_setting('usdt_enabled', 'off' if payment_enabled('usdt_enabled') else 'on')
    await safe_callback_answer(event, "USDT Manual: " + ("ON" if payment_enabled('usdt_enabled') else "OFF"))
    return await _render_payment_method_page(event, 'usdt')

  elif action_data == "set_usdt" and has_perm(uid, 'p_settings'):
    await event.delete()
    async with _admin_conversation(chat, timeout=300) as conv:
      async def get_reply(txt):
        await conv.send_message(custom_emoji_text(txt+"\n\n<i>(Type /cancel to abort)</i>")); r=await conv.get_response()
        if (r.raw_text or '').strip().lower()=='/cancel': raise ValueError
        return r
      try:
        addr=(await get_reply(f"{P_KEY} <b>Enter your USDT wallet address:</b>")).raw_text.strip()
        net=(await get_reply(f"{P_GLOBE} <b>Enter the network</b> (for example TRC20, BEP20, ERC20):")).raw_text.strip().upper()
        if len(addr) < 20 or re.search(r"\s", addr):
          return await conv.send_message(custom_emoji_text(f"{P_NO} <b>Invalid wallet address.</b>"))
        if not re.fullmatch(r"[A-Z0-9 _\-]{2,20}", net):
          return await conv.send_message(custom_emoji_text(f"{P_NO} <b>Invalid network name.</b>"))
        set_setting('usdt_address', addr); set_setting('usdt_network', net)
        await conv.send_message(custom_emoji_text(
          f"{P_YES} <b>USDT settings saved.</b>\n\n{P_KEY} <code>{html.escape(addr)}</code>\n{P_GLOBE} Network: <b>{html.escape(net)}</b>"))
      except ValueError: await conv.send_message("Cancelled.")
    return

  elif action_data.startswith("set_mindep|") and has_perm(uid, 'p_settings'):
    _which = action_data.split("|", 1)[1]
    _map = {'fampay': ('min_dep_fampay', 'FamPay'),
            'bharatpe': ('min_dep_bharatpe', 'BharatPe'),
            'manual': ('min_dep_manual', 'Manual'),
            'crypto': ('min_dep_crypto', 'Crypto')}
    if _which not in _map:
      return await safe_callback_answer(event, "Unknown option.", alert=True)
    _skey, _label = _map[_which]
    await event.delete()
    async with _admin_conversation(chat, timeout=300) as conv:
      try:
        _cur_val = get_setting(_skey, '10') or '10'
        await conv.send_message(custom_emoji_text(
          f"{P_CARD} <b>Set {_label} Minimum Deposit</b>\n\nCurrent: <b>₹{html.escape(str(_cur_val))}</b>\n"
          f"Enter the new minimum deposit amount in ₹ (numbers only):\n\n<i>(Type /cancel to abort)</i>"))
        _r = await conv.get_response()
        _t = (_r.raw_text or '').strip()
        if _t.lower() == '/cancel':
          raise ValueError
        if not re.fullmatch(r"\d{1,7}", _t) or int(_t) < 1:
          return await conv.send_message(custom_emoji_text(f"{P_NO} <b>Invalid amount.</b> Enter a whole number like 10, 50 or 100."))
        set_setting(_skey, int(_t))
        await conv.send_message(custom_emoji_text(f"{P_YES} <b>{_label} minimum deposit set to ₹{int(_t)}.</b>"))
      except ValueError:
        await conv.send_message("Cancelled.")
    return

  elif action_data in ("set_auto_upi","set_manual_upi","set_bharatpe_upi") and has_perm(uid, 'p_settings'):
    is_auto = action_data == "set_auto_upi"
    await event.delete()
    async with _admin_conversation(chat, timeout=300) as conv:
      async def get_reply(txt):
        await conv.send_message(custom_emoji_text(txt+"\n\n<i>(Type /cancel to abort)</i>")); r=await conv.get_response()
        if (r.text or '').strip().lower()=='/cancel': raise ValueError
        return r
      try:
        upi=(await get_reply("Enter UPI ID:")).text.strip(); name=(await get_reply("Enter Payee Name:")).text.strip()
        if not re.match(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+$",upi): return await conv.send_message("Invalid UPI ID.")
        prefix = 'bharatpe' if action_data == "set_bharatpe_upi" else ('fampay' if is_auto else 'manual')
        set_setting(prefix+'_upi',upi); set_setting(prefix+'_name',name)
        await conv.send_message(custom_emoji_text("Payment UPI settings saved successfully."))
      except ValueError: await conv.send_message("Cancelled.")
    return

  elif action_data == "fampayset":
    upi = get_fampay_upi()
    name = get_fampay_name()
    msg = (f"{P_CARD} <b>FamPay / UPI & IMAP Settings</b>\n\n"
        f"Current UPI ID: <code>{upi}</code>\n"
        f"Payee Name: <code>{name}</code>\n\n"
        f"Click below to update UPI ID, Payee Name, or IMAP configuration for automatic verification.")
    btns = [
      [Button.inline("Change FamPay UPI & Name", "adm_set_auto_upi")],
      [Button.inline("Change BharatPe UPI & Name", "adm_set_bharatpe_upi")],
      [Button.inline("Change Manual UPI & Name", "adm_set_manual_upi")],
      [Button.inline("Configure IMAP (Gmail)", "adm_set_imap")],
      [Button.inline("Payment Methods", "adm_paymentmethods")],
      [Button.inline("Back to Admin", "adm_adminmain")]
    ]
    return await event.edit(custom_emoji_text(msg), buttons=btns)

  elif action_data == "accmenu" and (uid == ADMIN_ID or has_perm(uid, 'p_add_stock') or has_perm(uid, 'p_manage_stock')):
    btns = []
    if uid == ADMIN_ID or has_perm(uid, 'p_add_stock'):
      btns.append([Button.inline("Add Single Acc", "adm_addstock"), Button.inline("Add ZIP", "adm_addzip")])
    if uid == ADMIN_ID or has_perm(uid, 'p_manage_stock'):
      btns.append([Button.inline("Manage Acc", "adm_managestock"), Button.inline("Auto Price", "adm_autoprice")])
      btns.append([Button.inline("Delete Account", "adm_delacc")])
    btns.append([Button.inline("Back to Admin", "adm_adminmain")])
    return await event.edit(custom_emoji_text(f"{P_ACC} <b>Manual Acc (TG Accounts)</b>\n\nManage your own Telegram account stock:"), buttons=btns)

  elif action_data == "smmmenu" and (uid == ADMIN_ID or has_perm(uid, 'p_manage_stock') or has_perm(uid, 'p_settings')):
    btns = []
    if uid == ADMIN_ID:
      btns.append([Button.inline("SMM API", "adm_smm_api"), Button.inline("Categories", "adm_smm_cats")])
    elif has_perm(uid, 'p_settings'):
      btns.append([Button.inline("Categories", "adm_smm_cats")])
    if uid == ADMIN_ID or has_perm(uid, 'p_manage_stock'):
      btns.append([Button.inline("Add Service", "adm_smm_addsrv"), Button.inline("Bulk Add", "adm_smm_bulksrv")])
      btns.append([Button.inline("Manage", "adm_smm_managesrv"), Button.inline("Delete", "adm_smm_delsrv")])
    btns.append([Button.inline("Back to Admin", "adm_adminmain")])
    return await event.edit(custom_emoji_text(f"{P_FOLDER} <b>SMM Controls</b>\n\nManage SMM API, categories and services:"), buttons=btns)

  elif action_data == "smm_cats":
    rows = cur.execute("SELECT id, name FROM smm_categories").fetchall()
    msg = f"{P_FOLDER} <b>Manage SMM Categories</b>\n\n"
    if not rows: msg += "No categories created yet."
    else:
      for r in rows: msg += f"ID: {r[0]} | Name: {html.escape(r[1])}\n"
    btns = [
      [Button.inline(" Create Category", "adm_smm_addcat")],
      [Button.inline(" Remove Category", "adm_smm_delcat")],
      [Button.inline(" Back to Admin", "adm_adminmain")]
    ]
    return await event.edit(custom_emoji_text(msg), buttons=btns)

  elif action_data == "smm_managesrv":
    rows = cur.execute("SELECT service_id, name FROM smm_services LIMIT 15").fetchall()
    if not rows: return await safe_callback_answer(event, "No services added yet.", alert=True)
    msg = f"{P_GEAR} <b>Manage SMM Service</b>\nSelect a service to edit:"
    btns = []
    for sid, sname in rows:
      btns.append([Button.inline(f"Edit: {sname} ({sid})", f"adm_smm_editsrv|{sid}")])
    btns.append([Button.inline(" Back", "adm_adminmain")])
    return await event.edit(custom_emoji_text(msg), buttons=btns)

  elif action_data.startswith("smm_editsrv|"):
    sid = int(action_data.split("|")[1])
    await event.delete()
    class FakeEvent: chat_id = chat; sender_id = uid
    async with _admin_conversation(chat, timeout=600) as conv:
      async def get_reply(txt):
        await conv.send_message(custom_emoji_text(txt + "\n\n<i>(Type /cancel to abort)</i>"))
        resp = await conv.get_response()
        if resp.text == "/cancel": raise ValueError("Cancelled")
        return resp
      try:
        edit_msg = (f"{P_GEAR} <b>Editing Service ID: {sid}</b>\n"
              f"1. Edit Name\n2. Edit Description\n3. Edit Price (Rate)\n4. Edit Category\n\n"
              f"Reply with option number (1, 2, 3, or 4):")
        opt = (await get_reply(edit_msg)).text.strip()
        if opt == '1':
          new_name = (await get_reply("Enter new Service Name:")).text.strip()
          cur.execute("UPDATE smm_services SET name=? WHERE service_id=?", (new_name, sid))
          db.commit()
          await conv.send_message(custom_emoji_text(f"{P_YES} Service Name updated successfully!"))
        elif opt == '2':
          new_desc = (await get_reply("Enter new Description:")).text.strip()
          cur.execute("UPDATE smm_services SET description=? WHERE service_id=?", (new_desc, sid))
          db.commit()
          await conv.send_message(custom_emoji_text(f"{P_YES} Service Description updated successfully!"))
        elif opt == '3':
          new_rate = float((await get_reply("Enter new Price (Rate per 1k):")).text.strip())
          cur.execute("UPDATE smm_services SET rate=? WHERE service_id=?", (new_rate, sid))
          db.commit()
          await conv.send_message(custom_emoji_text(f"{P_YES} Service Price updated successfully!"))
        elif opt == '4':
          cats = cur.execute("SELECT id, name FROM smm_categories").fetchall()
          c_txt = "Select new Category ID:\n"
          for c in cats: c_txt += f"ID: {c[0]} - {c[1]}\n"
          new_cid = int((await get_reply(c_txt)).text.strip())
          cur.execute("UPDATE smm_services SET category_id=? WHERE service_id=?", (new_cid, sid))
          db.commit()
          await conv.send_message(custom_emoji_text(f"{P_YES} Service Category updated successfully!"))
        else:
          await conv.send_message(custom_emoji_text("Invalid option selected."))
      except ValueError: await conv.send_message(custom_emoji_text(f"{P_NO} Cancelled."))
      except Exception as ex: await conv.send_message(custom_emoji_text(f"{P_NO} Error: {ex}"))
    return

  elif action_data == "smm_delsrv":
    rows = cur.execute("SELECT service_id, name FROM smm_services LIMIT 15").fetchall()
    if not rows: return await safe_callback_answer(event, "No services added yet.", alert=True)
    msg = f"{P_NO} <b>Remove Service</b>\nSelect service ID to delete:"
    btns = []
    for sid, sname in rows:
      btns.append([Button.inline(f"Del: {sname} ({sid})", f"adm_smm_dsrv|{sid}")])
    btns.append([Button.inline(" Back", "adm_adminmain")])
    return await event.edit(custom_emoji_text(msg), buttons=btns)

  elif action_data.startswith("smm_dsrv|"):
    sid = int(action_data.split("|")[1])
    cur.execute("DELETE FROM smm_services WHERE service_id=?", (sid,))
    db.commit()
    await safe_callback_answer(event, "Service Removed Successfully!", alert=True)
    class FakeEvent: chat_id = chat; sender_id = uid
    return await admin_panel_handler(FakeEvent())

  elif action_data == "redeemcodes" and has_perm(uid, 'p_settings'):
    return await _redeem_admin_menu(event)

  elif action_data.startswith("rdinfo|") and has_perm(uid, 'p_settings'):
    return await _redeem_admin_detail(event, action_data.split("|", 1)[1])

  elif action_data.startswith("rdtog|") and has_perm(uid, 'p_settings'):
    _rc = action_data.split("|", 1)[1]
    cur.execute("UPDATE redeem_codes SET active = CASE WHEN active=1 THEN 0 ELSE 1 END WHERE code=?", (_rc,)); db.commit()
    return await _redeem_admin_detail(event, _rc)

  elif action_data.startswith("rdask|") and has_perm(uid, 'p_settings'):
    _rc = action_data.split("|", 1)[1]
    return await event.edit(custom_emoji_text(
      f"{P_NO} <b>Remove this redeem code?</b>\n\n<code>{html.escape(_rc)}</code>\n\nUsers will not be able to redeem it any more."),
      buttons=[[Button.inline("Yes, Remove", f"adm_rddel|{_rc}", style="danger")],
               [Button.inline("Cancel", f"adm_rdinfo|{_rc}", style="primary")]])

  elif action_data.startswith("rddel|") and has_perm(uid, 'p_settings'):
    _rc = action_data.split("|", 1)[1]
    cur.execute("DELETE FROM redeem_codes WHERE code=?", (_rc,))
    cur.execute("DELETE FROM redeem_claims WHERE code=?", (_rc,)); db.commit()
    await safe_callback_answer(event, "Redeem code removed.", alert=False)
    return await _redeem_admin_menu(event)

  elif action_data == "redeem_add" and has_perm(uid, 'p_settings'):
    await event.delete()
    async with _admin_conversation(chat, timeout=300) as conv:
      async def get_reply(txt):
        await conv.send_message(custom_emoji_text(txt+"\n\n<i>(Type /cancel to abort)</i>")); r=await conv.get_response()
        if (r.text or '').strip().lower()=='/cancel': raise ValueError
        return r
      try:
        code=(await get_reply("Enter code (e.g. AKOP):")).text.strip().upper()
        amount=int((await get_reply("Enter amount in INR (e.g. 5):")).text.strip())
        max_users=int((await get_reply("Enter max users (e.g. 10):")).text.strip())
        if not re.fullmatch(r"[A-Z0-9_-]{3,40}",code) or amount<=0 or max_users<=0: raise ValueError
        cur.execute("DELETE FROM redeem_claims WHERE code=?",(code,))
        cur.execute("INSERT OR REPLACE INTO redeem_codes(code,amount,max_users,used_count,created_by,active) VALUES(?,?,?,?,?,1)",(code,amount,max_users,0,uid)); db.commit()
        await conv.send_message(custom_emoji_text(f"{P_YES} <b>Redeem Code Created</b>\n\nCode: <code>{html.escape(code)}</code>\nAmount: {P_INR}{amount}\nMax users: {max_users}\n\n<i>It is removed automatically after {max_users} use(s).</i>"),
                                buttons=[[Button.inline("Open Redeem Codes","adm_redeemcodes",style="primary")]])
      except ValueError: await conv.send_message("Invalid input or cancelled.")
    return

  elif action_data == "digitalshop" and has_perm(uid, 'p_settings'):
    return await digital_shop_admin_menu(event)

  elif action_data in ("digital_add","digital_remove") and has_perm(uid, 'p_settings'):
    await event.delete()
    async with _admin_conversation(chat, timeout=600) as conv:
      async def get_reply(txt):
        await conv.send_message(custom_emoji_text(txt+"\n\n<i>(Type /cancel to abort)</i>")); r=await conv.get_response()
        if (r.text or '').strip().lower()=='/cancel': raise ValueError
        return r
      try:
        if action_data == 'digital_add':
          _SKIP = ('skip', '/skip', 'none', 'no', '-', 'na', 'n/a')
          name=((await get_reply("Enter Product Name:")).raw_text or '').strip()
          if not name: raise ValueError

          # Description is optional.
          desc_msg = await get_reply("Enter Product Description, or type <b>skip</b> to leave it empty:")
          desc = (desc_msg.text or '').strip()
          if desc.lower() in _SKIP: desc = ''

          # Price is the ONLY required value besides the name.
          price=int((await get_reply("Enter Product Price (₹) <b>(required)</b>:")).text.strip())
          if price<=0: raise ValueError

          # Preview image is optional.
          preview = await get_reply("Send product preview photo/screenshot now, or type <b>skip</b> to continue without a preview:")
          preview_path = ''
          preview_file_id = ''
          preview_text = (preview.text or '').strip().lower()
          if preview_text not in _SKIP:
            if not preview.photo:
              return await conv.send_message(custom_emoji_text(f"{P_NO} Please send a photo/screenshot or type <b>skip</b>."))
            os.makedirs('digital_shop/previews',exist_ok=True)
            preview_path = await bot.download_media(preview, file='digital_shop/previews/') or ''
            preview_file_id = str(preview.photo.id)

          # Delivery file is optional too. Without a file the buyer gets the
          # product name + description as a text message after paying.
          product_file = await get_reply("Now send the <b>product file</b> to deliver after purchase (document/file/photo), or type <b>skip</b> to deliver the description as text:")
          file_path = '__none__'
          if (product_file.text or '').strip().lower() in _SKIP and not getattr(product_file, 'media', None):
            pass
          elif not getattr(product_file, 'media', None):
            return await conv.send_message(custom_emoji_text(f"{P_NO} Please send a file or type <b>skip</b>."))
          else:
            os.makedirs('digital_shop/files',exist_ok=True)
            file_path = await bot.download_media(product_file, file='digital_shop/files/') or ''
            if not file_path or not os.path.isfile(file_path):
              return await conv.send_message(custom_emoji_text(f"{P_NO} Product file could not be saved. Please try again."))

          cur.execute("INSERT INTO digital_products(name,description,price,photo_file_id,photo_path,file_path) VALUES(?,?,?,?,?,?)",(name,desc,price,preview_file_id,preview_path,file_path))
          db.commit()
          preview_status = 'Preview added' if preview_path else 'No preview'
          file_status = 'Delivery file saved' if file_path != '__none__' else 'No file (text delivery)'
          desc_status = 'Description added' if desc else 'No description'
          await conv.send_message(custom_emoji_text(f"{P_YES} Product <b>{html.escape(name)}</b> added successfully.\n\nPrice: ₹{price}\n{desc_status}\n{preview_status}\n{file_status}"))
        else:
          pid=int((await get_reply("Enter Product ID to remove:")).text.strip())
          cur.execute("UPDATE digital_products SET active=0 WHERE id=?",(pid,)); db.commit()
          await conv.send_message(custom_emoji_text(f"{P_YES} Product #{pid} removed from the shop."))
      except ValueError: await conv.send_message("Invalid input or cancelled.")
      except Exception as ex: await conv.send_message(custom_emoji_text(f"{P_NO} Error: {html.escape(str(ex))}"))
    return

  elif (action_data == "stats" or action_data.startswith("stats|")) and has_perm(uid, 'p_stats'):
    _parts = action_data.split("|")
    period = _parts[1] if len(_parts) > 1 else "all"
    per2 = _parts[2] if len(_parts) > 2 and _parts[2] in _STAT_PERIODS else "all"
    if period == "csv":
      await safe_callback_answer(event, "Preparing CSV...", alert=False)
      _csv = None
      try:
        _csv, _n = _stats_export_csv(per2)
        await bot.send_file(chat, _csv, force_document=True,
          caption=custom_emoji_text(f"{P_DOC} <b>Orders Export</b> ({_STAT_PERIODS[per2]})\nRows: <b>{_n}</b>"))
      except Exception as ex:
        logger.error("CSV export failed: %s", ex, exc_info=True)
        await bot.send_message(chat, custom_emoji_text(f"{P_NO} Export failed: {html.escape(str(ex))}"))
      finally:
        if _csv and os.path.exists(_csv):
          try: os.remove(_csv)
          except Exception: pass
      return
    if period == "top":
      return await _stats_edit(event, _stats_top_text(per2),
        [[Button.inline("Back to Stats", f"adm_stats|{per2}", style="primary")]])
    if period not in _STAT_PERIODS: period = "all"
    def _pb(k):
      return Button.inline(("• " if k == period else "") + _STAT_PERIODS[k], f"adm_stats|{k}",
                           style=("success" if k == period else "primary"))
    btns = [[_pb("today"), _pb("7d")], [_pb("30d"), _pb("all")],
            [Button.inline("Top Users", f"adm_stats|top|{period}", style="primary"),
             Button.inline("Export CSV", f"adm_stats|csv|{period}", style="primary")],
            [Button.inline("ALL ORDERS", "adm_globalsales|1", style="primary"),
             Button.inline("ALL USERS", "adm_users|1", style="success")],
            [Button.inline("Refresh", f"adm_stats|{period}", style="primary"),
             Button.inline("Back", "adm_adminmain", style="danger")]]
    return await _stats_edit(event, _stats_text(period), btns)

  elif action_data == "automation" and uid == ADMIN_ID:
    return await _automation_menu(event)

  elif action_data == "autobackup_tgl" and uid == ADMIN_ID:
    set_setting("auto_backup", "off" if get_setting("auto_backup", "on") == "on" else "on")
    return await _automation_menu(event)

  elif action_data == "dailyreport_tgl" and uid == ADMIN_ID:
    set_setting("daily_report", "off" if get_setting("daily_report", "on") == "on" else "on")
    return await _automation_menu(event)

  elif action_data == "backupnow" and uid == ADMIN_ID:
    await safe_callback_answer(event, "Creating backup...", alert=False)
    await _send_backup_to_owner("Manual")
    return

  elif action_data.startswith("editadmin|") and uid == ADMIN_ID:
    return await edit_admin_menu(event, int(action_data.split("|")[1]))

  elif action_data.startswith("deladminask|") and uid == ADMIN_ID:
    _tid = int(action_data.split("|")[1])
    _lbl = await _admin_label(_tid)
    return await event.edit(custom_emoji_text(
      f"{P_NO} <b>Remove this admin?</b>\n\n{html.escape(_lbl)} · <code>{_tid}</code>\n\n"
      f"They will lose all admin access immediately."),
      buttons=[[Button.inline("Yes, Remove Admin", f"adm_deladmin|{_tid}", style="danger")],
               [Button.inline("Cancel", "adm_manageadmins", style="primary")]])

  elif action_data == "manageadmins" and uid == ADMIN_ID:
    return await manage_admins_menu(event)

  elif action_data.startswith("tglperm|") and uid == ADMIN_ID:
    _, t_id, p_name = action_data.split("|")
    cur.execute(f"UPDATE admins SET {p_name} = CASE WHEN {p_name}=1 THEN 0 ELSE 1 END WHERE user_id=?", (t_id,))
    db.commit()
    return await edit_admin_menu(event, t_id)
    
  elif action_data.startswith("deladmin|") and uid == ADMIN_ID:
    t_id = action_data.split("|")[1]
    cur.execute("DELETE FROM admins WHERE user_id=?", (t_id,))
    db.commit()
    await safe_callback_answer(event, "Admin Removed", alert=True)
    return await manage_admins_menu(event)

  elif action_data == "managestock" and has_perm(uid, 'p_manage_stock'): return await send_manage_stock_page(event, 1)
  elif action_data.startswith("mspg|") and has_perm(uid, 'p_manage_stock'): return await send_manage_stock_page(event, int(action_data.split("|")[1]))
  elif action_data.startswith("msc|") and has_perm(uid, 'p_manage_stock'): return await send_manage_stock_country(event, action_data.split("|")[1])
  elif action_data == "autoprice" and has_perm(uid, 'p_manage_stock'): return await send_autoprice_page(event, 1)
  elif action_data.startswith("appg|") and has_perm(uid, 'p_manage_stock'): return await send_autoprice_page(event, int(action_data.split("|")[1]))
  elif action_data.startswith("apc|") and has_perm(uid, 'p_manage_stock'): return await send_autoprice_country(event, action_data.split("|")[1])
    
  elif action_data == "backupusr" and has_perm(uid, 'p_settings'):
    if uid != ADMIN_ID:
      return await safe_callback_answer(event, "Only the owner can create a full backup.", alert=True)
    await safe_callback_answer(event, "Creating full backup...", alert=False)
    zip_path = None
    try:
      zip_path, n_files = await asyncio.to_thread(build_full_backup)
      size_mb = os.path.getsize(zip_path) / (1024 * 1024)
      await bot.send_file(
        chat, zip_path, force_document=True,
        caption=custom_emoji_text(
          f"{P_FOLDER} <b>Full Backup</b>\n"
          f"{P_DOC} Script + Database + {n_files} session/media files\n"
          f"{P_TIME} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {size_mb:.1f} MB\n\n"
          f"<i>Use the Restore button and send this zip to restore everything.</i>"))
    except Exception as ex:
      logger.error(f"Full backup failed: {ex}", exc_info=True)
      await bot.send_message(chat, custom_emoji_text(f"{P_NO} Backup failed: {html.escape(str(ex))}"))
    finally:
      if zip_path and os.path.exists(zip_path):
        try: os.remove(zip_path)
        except Exception: pass
    return

  elif action_data == "serverapis" and has_perm(uid, 'p_settings'):
    return await admin_server_apis_menu(event)

  elif action_data.startswith("srvapi_view|") and has_perm(uid, 'p_settings'):
    try:
      server_no = int(action_data.split("|")[1])
    except Exception:
      return await safe_callback_answer(event, "Invalid server.", alert=True)
    return await admin_server_view(event, server_no)

  elif action_data.startswith("srvapi_test|") and has_perm(uid, 'p_settings'):
    try:
      server_no = int(action_data.split("|")[1])
    except Exception:
      return await safe_callback_answer(event, "Invalid server.", alert=True)
    return await admin_server_api_test(event, server_no)

  elif action_data.startswith("srvapi_del|") and has_perm(uid, 'p_settings'):
    try:
      server_no = int(action_data.split("|")[1])
    except Exception:
      return await safe_callback_answer(event, "Invalid server.", alert=True)
    conf = SERVER_DEFS.get(server_no)
    if conf:
      set_setting(conf["url_key"], "")
      set_setting(conf["key_key"], "")
      _reset_server_caches(server_no)
    await safe_callback_answer(event, "Server API removed.", alert=True)
    return await admin_server_view(event, server_no)

  if action_data in ("bal", "balmenu") and has_perm(uid, 'p_bal'):
    return await event.edit(
      custom_emoji_text(f"{P_MONEY} <b>Change Balance</b>\n\nChoose what you want to do:"),
      buttons=[[Button.inline("Add Funds", "adm_baladd", style="success"),
                Button.inline("Remove Funds", "adm_balrem", style="danger")],
               [Button.inline("Back to Admin", "adm_adminmain")]])

  _GLOBAL_PENDING_WHERE = ("refunded=0"
    " AND UPPER(COALESCE(status,'')) NOT LIKE '%COMPLETE%'"
    " AND UPPER(COALESCE(status,'')) NOT LIKE '%DELIVER%'"
    " AND UPPER(COALESCE(status,'')) NOT LIKE '%REFUND%'"
    " AND UPPER(COALESCE(status,'')) NOT LIKE '%CANCEL%'"
    " AND UPPER(COALESCE(status,'')) NOT LIKE '%FAIL%'"
    " AND UPPER(COALESCE(status,'')) NOT LIKE '%EXPIRE%'")

  if action_data == "globalcompleteall":
    if not (uid == ADMIN_ID or has_perm(uid, 'p_settings')):
      return await safe_callback_answer(event, "You do not have permission for this.", alert=True)
    pending = cur.execute("SELECT COUNT(*) FROM global_orders WHERE " + _GLOBAL_PENDING_WHERE).fetchone()[0]
    if not pending:
      return await safe_callback_answer(event, "No pending orders. Everything is already complete.", alert=True)
    return await event.edit(
      custom_emoji_text(f"{P_WARN} <b>Mark ALL orders as COMPLETED?</b>\n\n"
                        f"<b>{pending}</b> order(s) will be marked complete.\n"
                        f"Refunded, cancelled and failed orders are skipped.\n\nThis cannot be undone."),
      buttons=[[Button.inline("Yes, Mark All Complete", "adm_globalcompleteallyes", style="success")],
               [Button.inline("Cancel", "adm_globalsales|1", style="danger")]])

  if action_data == "globalcompleteallyes":
    if not (uid == ADMIN_ID or has_perm(uid, 'p_settings')):
      return await safe_callback_answer(event, "You do not have permission for this.", alert=True)
    await safe_callback_answer(event, "Marking orders complete...", alert=False)
    _rows = cur.execute("SELECT id FROM global_orders WHERE " + _GLOBAL_PENDING_WHERE).fetchall()
    _done = _failed = 0
    for _n, (_oid,) in enumerate(_rows, 1):
      _ok, _m = _admin_mark_global_complete(f"ATS-{int(_oid):08d}", uid)
      if _ok: _done += 1
      else: _failed += 1
      if _n % 50 == 0:
        await asyncio.sleep(0)
    logger.info("ADMIN_GLOBAL_COMPLETE_ALL actor=%s done=%s failed=%s", uid, _done, _failed)
    return await event.edit(
      custom_emoji_text(f"{P_YES} <b>Done.</b>\n\nMarked complete: <b>{_done}</b>"
                        + (f"\nFailed: <b>{_failed}</b>" if _failed else "")),
      buttons=[[Button.inline("Back to All Orders", "adm_globalsales|1", style="primary")],
               [Button.inline("Admin Panel", "adm_adminmain", style="danger")]])

  async with _admin_conversation(chat, timeout=600) as conv:
    async def get_reply(txt):
      await conv.send_message(custom_emoji_text(txt + "\n\n<i>(Type /cancel to abort)</i>"))
      resp = await conv.get_response()
      if resp.text == "/cancel": raise ValueError("Cancelled")
      return resp

    try:
      if action_data.startswith(("srvapi_url|", "srvapi_key|")) and has_perm(uid, 'p_settings'):
        change_url = action_data.startswith("srvapi_url|")
        try:
          server_no = int(action_data.split("|")[1])
        except Exception:
          return await conv.send_message(custom_emoji_text(f"{P_NO} Invalid server."))
        conf = SERVER_DEFS.get(server_no)
        if not conf:
          return await conv.send_message(custom_emoji_text(f"{P_NO} Unknown server."))

        if change_url:
          cur_url, _ = get_server_api_config(server_no)
          raw = (await get_reply(
            f"{P_LINK} <b>{conf['name']} — Change API URL</b>\n\n"
            f"Current: <code>{html.escape(_mask_url(cur_url))}</code>\n"
            f"<i>Example: {html.escape(_mask_url(conf.get('default_url', 'https://panel.example.com')))}</i>\n\n"
            f"Send the new API URL:"
          )).text.strip()
          new_url = clean_html_url(raw)
          if not new_url.startswith(("http://", "https://")):
            return await conv.send_message(custom_emoji_text(
              f"{P_NO} <b>Invalid URL.</b> It must start with http:// or https://"))
          if conf.get("kind") in ("tiger", "s3"):
            # Reseller (main store) URLs must stay clean: never append the Tiger
            # stub path, otherwise Server 2/3 would call /stubs/handler_api.php
            # on the main bot and get "Not Found".
            _clean = _strip_provider_path(new_url)
            _cur_key = str(get_server_api_config(server_no)[1] or "").strip()
            _host = _url_host_of(_clean)
            _looks_reseller = (
              _cur_key.startswith("ats_")
              or _clean.lower().rstrip("/").endswith("/v1")
              or "/v1/" in _clean.lower()
              or (_host and _host == _url_host_of(_main_store_base()))
            )
            if _looks_reseller:
              new_url = _clean
            elif "handler_api" not in new_url:
              new_url = new_url.rstrip("/") + "/stubs/handler_api.php"
          set_setting(conf["url_key"], new_url)
          done = f"{P_YES} <b>{conf['name']} API URL updated.</b>"
        else:
          raw = (await get_reply(
            f"{P_KEY} <b>{conf['name']} — Change API Key</b>\n\n"
            f"Send the new API key:"
          )).text.strip()
          if not raw or " " in raw:
            return await conv.send_message(custom_emoji_text(f"{P_NO} <b>Invalid API key.</b>"))
          set_setting(conf["key_key"], raw)
          done = f"{P_YES} <b>{conf['name']} API key updated.</b>"

        _reset_server_caches(server_no)
        await conv.send_message(custom_emoji_text(f"{done}\n{P_WAIT} Checking the connection..."))
        _ok, check_text = await _server_quick_test(server_no)
        await conv.send_message(custom_emoji_text(check_text))
        await admin_server_view(_AdminChatReply(chat, uid), server_no)

      elif action_data.startswith("srvapi_margin|") and has_perm(uid, 'p_settings'):
        try:
          server_no = int(action_data.split("|")[1])
        except Exception:
          return await conv.send_message(custom_emoji_text(f"{P_NO} Invalid server."))
        conf = SERVER_DEFS.get(server_no)
        if not conf:
          return await conv.send_message(custom_emoji_text(f"{P_NO} Unknown server."))
        raw = (await get_reply(
          f"{P_RATE} <b>Enter Profit Margin % for {conf['name']}</b>\n"
          f"<i>Example: 20 means API price + 20% profit. Enter 0 to sell at API price.</i>\n"
          f"Current: <b>{get_server_margin(server_no):g}%</b>"
        )).text.strip().replace("%", "")
        try:
          margin = float(raw)
          if margin < 0 or margin > 500:
            raise ValueError
        except Exception:
          return await conv.send_message(custom_emoji_text(f"{P_NO} Enter a number between 0 and 500."))
        set_setting(conf["margin_key"], f"{margin:g}")
        if int(server_no) in (2, 3):
          _reset_server_caches(int(server_no))
        await conv.send_message(custom_emoji_text(
          f"{P_YES} <b>Profit margin updated to {margin:g}%</b> for {conf['name']}."
        ))
        await admin_server_view(_AdminChatReply(chat, uid), server_no)

      elif action_data == "smm_api" and has_perm(uid, 'p_settings'):
        url_resp = (await get_reply(f"{P_GEAR} <b>Enter SMM API URL</b> (e.g., https://smmpanel.com/api/v2):")).text.strip()
        key_resp = (await get_reply(f"{P_KEY} <b>Enter SMM API Key:</b>")).text.strip()
        clean_u = clean_html_url(url_resp)
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('smm_api_url', ?)", (clean_u,))
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('smm_api_key', ?)", (key_resp,))
        db.commit()
        await conv.send_message(custom_emoji_text(f"{P_YES} <b>SMM API credentials updated successfully!</b>\nClean URL: <code>{clean_u}</code>"))

      elif action_data == "smm_addcat" and has_perm(uid, 'p_manage_stock'):
        cname = (await get_reply(f"{P_FOLDER} <b>Enter Category Name</b> (e.g., Telegram):")).text.strip()
        cur.execute("INSERT INTO smm_categories (name) VALUES (?)", (cname,))
        db.commit()
        await conv.send_message(custom_emoji_text(f"{P_YES} Category <b>{html.escape(cname)}</b> created successfully!"))

      elif action_data == "smm_delcat" and has_perm(uid, 'p_manage_stock'):
        rows = cur.execute("SELECT id, name FROM smm_categories").fetchall()
        if not rows: return await conv.send_message(custom_emoji_text("No categories found."))
        txt = "Reply with Category ID to delete:\n"
        for r in rows: txt += f"ID: {r[0]} - {r[1]}\n"
        cid = int((await get_reply(txt)).text.strip())
        cur.execute("DELETE FROM smm_categories WHERE id=?", (cid,))
        cur.execute("DELETE FROM smm_services WHERE category_id=?", (cid,))
        db.commit()
        await conv.send_message(custom_emoji_text(f"{P_YES} Category and its services removed!"))

      elif action_data == "smm_bulksrv" and has_perm(uid, 'p_manage_stock'):
        cats = cur.execute("SELECT id, name FROM smm_categories").fetchall()
        if not cats: return await conv.send_message(custom_emoji_text("Please create a category first using 'Categories' menu."))
        
        cat_text = "Select Category ID for bulk services:\n"
        for c in cats: cat_text += f"ID: {c[0]} - {c[1]}\n"
        cid = int((await get_reply(cat_text)).text.strip())
        
        ids_resp = (await get_reply(f"{P_ID} <b>Enter Service IDs (separated by space, comma or newline):</b>\n<i>Example: 2222 6478 22461</i>")).text.strip()
        service_ids = re.findall(r'\d+', ids_resp)
        
        if not service_ids:
          return await conv.send_message(custom_emoji_text(f"{P_NO} No valid Service IDs found."))

        api_url, api_key = get_smm_api_config()
        if not api_url or not api_key:
          return await conv.send_message(custom_emoji_text(f"{P_NO} SMM API URL or Key not configured."))

        await conv.send_message(custom_emoji_text(f"{P_WAIT} <b>Fetching services from SMM API...</b>"))
        services_data = fetch_smm_services_from_api(api_url, api_key)
        
        api_services_dict = {}
        if services_data:
          if isinstance(services_data, dict):
            for k, v in services_data.items():
              if isinstance(v, dict):
                s_id = str(v.get('service', v.get('service_id', v.get('id', k))))
                api_services_dict[s_id] = v
              else:
                api_services_dict[str(k)] = {'name': str(v), 'rate': 0.0, 'min': 10, 'max': 10000}
          elif isinstance(services_data, list):
            for s in services_data:
              if isinstance(s, dict):
                s_id = str(s.get('service', s.get('service_id', s.get('id', ''))))
                if s_id: api_services_dict[s_id] = s

        markup_pct = float((await get_reply(f"{P_RATE} <b>Enter Profit Margin / Markup %</b> (e.g., enter <code>10</code> for 10% profit markup):")).text.strip() or 0)

        success_count = 0
        report_msg = f"{P_PKG} <b>Bulk Add Report ({markup_pct}% Markup):</b>\n\n"

        for sid_str in service_ids:
          sid_int = int(sid_str)
          target_srv = api_services_dict.get(str(sid_int))
          
          if target_srv and isinstance(target_srv, dict):
            sname = target_srv.get('name', f'Service {sid_int}')
            api_rate = float(target_srv.get('rate', 0.0))
            smin = int(target_srv.get('min', 10))
            smax = int(target_srv.get('max', 10000))
            sdesc = target_srv.get('description', '')
            
            srate = round(api_rate * (1 + markup_pct / 100.0), 2)
            
            cur.execute("INSERT OR REPLACE INTO smm_services (service_id, category_id, name, rate, min, max, description) VALUES (?,?,?,?,?,?,?)",
                  (sid_int, cid, sname, srate, smin, smax, sdesc))
            success_count += 1
            report_msg += f" ID {sid_int}: {html.escape(sname)} (₹{srate})\n"
          else:
            sname = f"Service {sid_int}"
            srate = 100.0
            smin, smax = 10, 10000
            sdesc = "Added via bulk"
            cur.execute("INSERT OR REPLACE INTO smm_services (service_id, category_id, name, rate, min, max, description) VALUES (?,?,?,?,?,?,?)",
                  (sid_int, cid, sname, srate, smin, smax, sdesc))
            success_count += 1
            report_msg += f" ID {sid_int}: Added with default values.\n"

        db.commit()
        report_msg += f"\n <b>Total Added:</b> {success_count} services successfully!"
        await conv.send_message(custom_emoji_text(report_msg))

      elif action_data == "smm_addsrv" and has_perm(uid, 'p_manage_stock'):
        cats = cur.execute("SELECT id, name FROM smm_categories").fetchall()
        if not cats: return await conv.send_message(custom_emoji_text("Please create a category first."))
        
        cat_text = "Select Category ID for the service:\n"
        for c in cats: cat_text += f"ID: {c[0]} - {c[1]}\n"
        cid = int((await get_reply(cat_text)).text.strip())
        
        sid_input = int((await get_reply(f"{P_ID} <b>Enter SMM Service ID:</b>")).text.strip())
        
        api_url, api_key = get_smm_api_config()
        target_srv = None
        
        if api_url and api_key:
          await conv.send_message(custom_emoji_text(f"{P_WAIT} <b>Fetching service details from SMM API...</b>"))
          services_data = fetch_smm_services_from_api(api_url, api_key)
          
          if services_data:
            if isinstance(services_data, dict):
              for k, v in services_data.items():
                if str(k) == str(sid_input) or (isinstance(v, dict) and str(v.get('service', v.get('service_id', v.get('id', '')))) == str(sid_input)):
                  target_srv = v if isinstance(v, dict) else {'name': str(v)}
                  target_srv['service'] = sid_input
                  break
            elif isinstance(services_data, list):
              for s in services_data:
                if isinstance(s, dict) and str(s.get('service', s.get('service_id', s.get('id', '')))) == str(sid_input):
                  target_srv = s
                  break

        if target_srv and isinstance(target_srv, dict):
          sname = target_srv.get('name', f'Service {sid_input}')
          api_rate = float(target_srv.get('rate', 0.0))
          smin = int(target_srv.get('min', 10))
          smax = int(target_srv.get('max', 10000))
          sdesc = target_srv.get('description', '')
          await conv.send_message(custom_emoji_text(f"{P_YES} <b>API details fetched successfully!</b>\n- Name: {html.escape(sname)}\n- Rate: ₹{api_rate}\n- Min: {smin} | Max: {smax}"))
        else:
          await conv.send_message(custom_emoji_text(f"{P_WARN} Auto-fetch failed due to API/Cloudflare. Please enter details manually:"))
          sname = (await get_reply("Enter Service Name:")).text.strip()
          api_rate = float((await get_reply("Enter API Rate per 1000 (₹):")).text.strip())
          smin = int((await get_reply("Enter Min Quantity:")).text.strip())
          smax = int((await get_reply("Enter Max Quantity:")).text.strip())
          sdesc = (await get_reply("Enter Description (or type 'none'):")).text.strip()

        markup_pct = float((await get_reply(f"{P_RATE} <b>API Rate:</b> ₹{api_rate}\n\n<b>Enter Profit Margin / Markup % (e.g., 10 for 10%):</b>")).text.strip() or 0)
        srate = round(api_rate * (1 + markup_pct / 100.0), 2)

        cur.execute("INSERT OR REPLACE INTO smm_services (service_id, category_id, name, rate, min, max, description) VALUES (?,?,?,?,?,?,?)",
              (sid_input, cid, sname, srate, smin, smax, sdesc))
        db.commit()
        await conv.send_message(custom_emoji_text(f"{P_YES} <b>Service Added Successfully!</b>\n\n- ID: <code>{sid_input}</code>\n- Name: {html.escape(sname)}\n- Rate/1k: ₹{srate} ({markup_pct}% markup)\n- Min: {smin} | Max: {smax}"))

      elif action_data == "update_welcome_photo" and has_perm(uid, 'p_settings'):
        resp = await get_reply(f"{P_EYE} <b>Send new welcome photo or video:</b>\n\n<i>Photo, video or GIF (MP4) - max 50 MB.</i>")
        _mime = (getattr(getattr(resp, "file", None), "mime_type", "") or "").lower()
        _is_photo = bool(resp.photo)
        _is_video = bool(resp.video or resp.gif or _mime == "video/mp4")
        _size = int(getattr(getattr(resp, "file", None), "size", 0) or 0)
        if not (_is_photo or _is_video):
          await conv.send_message(custom_emoji_text(f"{P_NO} Please send a <b>photo</b> or a <b>video / GIF (MP4)</b>. Try again."))
        elif _size > WELCOME_MAX_BYTES:
          await conv.send_message(custom_emoji_text(f"{P_NO} File is too large ({_size/1048576:.1f} MB). Max allowed is 50 MB."))
        else:
          _tmp = "welcome_new" + (".mp4" if _is_video else ".jpg")
          _got = await bot.download_media(resp, _tmp)
          if not _got or not os.path.isfile(_got):
            await conv.send_message(custom_emoji_text(f"{P_NO} Download failed. Please try again."))
          else:
            _final = WELCOME_VIDEO_FILE if _is_video else WELCOME_PHOTO_FILE
            _other = WELCOME_PHOTO_FILE if _is_video else WELCOME_VIDEO_FILE
            os.replace(_got, _final)
            try:
              if os.path.exists(_other): os.remove(_other)   # only one welcome media stays active
            except OSError:
              pass
            _welcome_media_cache.clear()
            await conv.send_message(custom_emoji_text(
              f"{P_YES} <b>Welcome {'video' if _is_video else 'photo'} updated successfully!</b>"))
            try:   # quick preview so the admin sees exactly what users will get
              await send_welcome_media(uid, "Preview of the new welcome media")
            except Exception as _pex:
              logger.warning(f"Welcome media preview failed: {_pex}")

      elif action_data == "changelogs" and has_perm(uid, 'p_settings'):
        new_ch = (await get_reply(f"{P_GLOBE} <b>Enter new Logs Channel ID (e.g., -100xxxxxxxxxx):</b>\n\n<i>Add this bot as admin in the channel first (with \"Invite Users via Link\" permission).</i>")).text.strip()
        if not re.fullmatch(r"-?\d{5,20}", new_ch):
          return await conv.send_message(custom_emoji_text(f"{P_NO} <b>Invalid channel ID.</b> It must look like <code>-1001234567890</code>."))
        ok, reason = await _is_bot_channel_admin(new_ch)
        if not ok:
          return await conv.send_message(custom_emoji_text(
            f"{P_NO} <b>Logs channel not changed.</b>\n\n{html.escape(reason)}\n\n"
            f"Make the bot an admin of that channel, then try again."))
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('log_channel_id', ?)", (new_ch,))
        db.commit()
        link = await refresh_selling_logs_link(new_ch)
        if not link:
          manual = (await get_reply(f"{P_WARN} <b>Could not auto-generate the link.</b>\nSend the channel invite link now (https://t.me/...), or type <b>skip</b> to keep the current Selling Logs link:")).text.strip()
          if manual.lower() != 'skip' and _has_valid_button_url(manual):
            link = _normalize_tg_url(manual, "")
            set_setting('selling_logs_link', link)
        await conv.send_message(custom_emoji_text(
          f"{P_YES} <b>Logs Channel updated successfully:</b> <code>{html.escape(new_ch)}</code>\n\n"
          f"{P_GLOBE} <b>Selling Logs button link:</b> {html.escape(link or get_selling_logs_link())}"))

      elif action_data == "add_fchan":
        title = (await get_reply("Enter Channel Title/Name (e.g., Updates Channel):")).text.strip()
        ch_id = (await get_reply("Enter Channel Chat ID (e.g., -100xxxxxxxxxx):")).text.strip()

        # Never save a force channel until the bot itself is confirmed as admin/creator.
        bot_admin_ok, admin_reason = await _is_bot_channel_admin(ch_id)
        if not bot_admin_ok:
          await conv.send_message(custom_emoji_text(
            f"{P_NO} <b>Channel verification failed.</b>\n\n"
            f"<b>Reason:</b> {html.escape(admin_reason)}\n\n"
            "Add the bot to that channel as an <b>Administrator</b>, then try again."
          ))
          return

        # No manual invite URL is required. Telegram creates the invite link for
        # this channel and that generated link is stored for the Join button.
        await conv.send_message(custom_emoji_text(
          "Bot admin verified successfully.\n\n"
          "Creating the channel invite link automatically..."
        ))
        invite_ok, inv, invite_reason = await _create_force_channel_invite(ch_id)
        if not invite_ok:
          await conv.send_message(custom_emoji_text(
            f"{P_NO} <b>Invite link creation failed.</b>\n\n"
            f"<b>Reason:</b> {html.escape(invite_reason)}\n\n"
            "Make sure the bot has permission to <b>Invite Users via Link</b> in this channel and try again."
          ))
          return

        # Replace an existing entry for the same channel instead of creating duplicates.
        cur.execute("DELETE FROM force_channels WHERE channel_id=?", (ch_id,))
        cur.execute(
          "INSERT INTO force_channels (channel_id, invite_url, title) VALUES (?,?,?)",
          (ch_id, inv, title)
        )
        db.commit()
        await conv.send_message(custom_emoji_text(
          f"{P_YES} <b>Force channel added successfully!</b>\n\n"
          f"Title: {html.escape(title)}\n"
          f"Chat ID: <code>{html.escape(ch_id)}</code>\n"
          f"Join link created automatically."
        ))

      elif action_data.startswith("fchlink|"):
        fid = int(action_data.split("|")[1])
        r = cur.execute("SELECT channel_id, title FROM force_channels WHERE id=?", (fid,)).fetchone()
        if not r:
          return await conv.send_message(custom_emoji_text(f"{P_NO} Channel not found."))
        raw_link = (await get_reply(
          f"{P_LINK} <b>Send the new join link for {html.escape(str(r[1] or r[0]))}</b>\n"
          f"<i>Public (https://t.me/username) or private (https://t.me/+xxxx) link. "
          f"Request-to-join links are supported.</i>")).text.strip()
        new_link = await _validate_force_invite_url(clean_html_url(raw_link))
        if not new_link:
          return await conv.send_message(custom_emoji_text(f"{P_NO} <b>Invalid link.</b> Link not changed."))
        cur.execute("UPDATE force_channels SET invite_url=? WHERE id=?", (new_link, fid))
        db.commit()
        await conv.send_message(custom_emoji_text(
          f"{P_YES} <b>Link updated.</b>\n\n{P_LINK} {html.escape(new_link)}\n\n"
          f"Force join now accepts both joined members and users with a pending join request."))

      elif action_data == "del_fchan":
        rows = cur.execute("SELECT id, title, channel_id FROM force_channels").fetchall()
        if not rows: return await conv.send_message(custom_emoji_text("No channels to delete."))
        txt = "Reply with ID to delete:\n"
        for r in rows: txt += f"ID: {r[0]} - {r[1]} ({r[2]})\n"
        del_id = int((await get_reply(txt)).text.strip())
        cur.execute("DELETE FROM force_channels WHERE id=?", (del_id,))
        db.commit()
        await conv.send_message(custom_emoji_text(f"{P_YES} Force channel removed!"))

      elif action_data == "set_upi":
        new_upi = (await get_reply("Enter new UPI ID (e.g., yourname@fampay):")).text.strip()
        new_name = (await get_reply("Enter Payee Name (e.g., Aaditya Tg Store):")).text.strip()
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('fampay_upi', ?)", (new_upi,))
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('fampay_name', ?)", (new_name,))
        db.commit()
        await conv.send_message(custom_emoji_text(f"{P_YES} FamPay UPI settings updated!"))

      elif action_data == "set_imap":
        srv = (await get_reply("Enter IMAP Server (e.g., imap.gmail.com):")).text.strip()
        mail_id = (await get_reply("Enter Gmail Email Address (e.g., yourname@gmail.com):")).text.strip()
        pwd = (await get_reply("Enter Gmail App Password (16 letters, e.g., abcd efgh ijkl mnop):")).text.strip()
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('imap_server', ?)", (srv,))
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('imap_email', ?)", (mail_id,))
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('imap_password', ?)", (pwd,))
        db.commit()
        await conv.send_message(custom_emoji_text(f"{P_YES} IMAP credentials saved successfully for automatic UTR verification!"))

      elif action_data == "ap_add_country" and has_perm(uid, 'p_manage_stock'):
        code = (await get_reply(f"{P_PHONE} <b>Enter Country Calling Code (without +):</b>\n<i>Example: 91</i>")).text.replace("+", "").strip()
        name = html.escape((await get_reply(f"{P_GLOBE} <b>Enter Country Name:</b>\n<i>Example: India</i>")).text.strip())
        
        cur.execute("INSERT OR REPLACE INTO custom_countries (code, name) VALUES (?,?)", (code, name))
        db.commit()
        await conv.send_message(custom_emoji_text(f"{P_YES} <b>Custom Country Added Successfully!</b>\n{name} (+{code})\n\n<i>It will now automatically be recognized when adding stock!</i>"))

      elif action_data == "userinfo" and has_perm(uid, 'p_stats'):
        raw=(await get_reply(f"{P_ACC} <b>Enter User ID or @username:</b>")).text.strip()
        target=None
        if raw.lstrip('@').isdigit(): target=int(raw.lstrip('@'))
        else:
          uname=raw.lstrip('@').lower()
          found=cur.execute("SELECT user_id FROM users WHERE lower(username)=?",(uname,)).fetchone()
          if found: target=int(found[0])
          else:
            try:
              ent=await bot.get_entity('@'+uname)
              target=int(ent.id)
              ensure_user(target,getattr(ent,'username','') or '',getattr(ent,'first_name','') or '')
            except Exception: target=None
        if not target: return await conv.send_message("User not found. Ask the user to open the bot once, then retry.")
        card=_admin_user_card(target)
        if not card: return await conv.send_message("User not found in bot database.")
        await bot.send_message(chat,card[0],buttons=card[1],parse_mode='html')

      elif action_data == "addadmin" and uid == ADMIN_ID:
        new_ad = int((await get_reply(f"{P_ACC} <b>Enter User ID for new Admin:</b>")).text)
        cur.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_ad,))
        db.commit()
        await conv.send_message(custom_emoji_text(f"{P_YES} Admin added!"))
        class FakeEvent: 
          async def edit(self, text, buttons): await bot.send_message(chat, text, buttons=buttons)
          async def answer(self, txt, alert): pass
        await edit_admin_menu(FakeEvent(), new_ad)
        
      elif action_data == "editadminreq" and uid == ADMIN_ID:
        t_id = int((await get_reply(f"{P_ACC} <b>Enter User ID to edit:</b>")).text)
        class FakeEvent: 
          async def edit(self, text, buttons): await bot.send_message(chat, text, buttons=buttons)
          async def answer(self, txt, alert): pass
        await edit_admin_menu(FakeEvent(), t_id)

      elif action_data.startswith("msedit|") and has_perm(uid, 'p_manage_stock'):
        parts = action_data.split("|")
        action, c_name = parts[1], parts[2]
        
        if action == "name":
          new_name = html.escape((await get_reply(f"{P_DOC} <b>Enter NEW Name for {html.escape(c_name)}:</b>")).text)
          cur.execute("UPDATE stock SET country_name=? WHERE country_name=?", (new_name, c_name))
          cur.execute("UPDATE auto_prices SET country=? WHERE country=?", (new_name, c_name))
          db.commit()
          await conv.send_message(custom_emoji_text(f"{P_YES} Country '{html.escape(c_name)}' successfully renamed to '{new_name}'!"))
          
        elif action == "cprice":
          new_p = int((await get_reply(f"{P_MONEY} <b>Enter NEW Common Price for all {html.escape(c_name)} accounts:</b>")).text)
          cur.execute("UPDATE stock SET price=? WHERE country_name=?", (new_p, c_name))
          db.commit()
          await conv.send_message(custom_emoji_text(f"{P_YES} All existing '{html.escape(c_name)}' accounts updated to {P_INR}{new_p}!"))
          
        elif action == "yprice":
          year = parts[3]
          new_p = int((await get_reply(f"{P_MONEY} <b>Enter NEW Price for {html.escape(c_name)} ({year}):</b>")).text)
          cur.execute("UPDATE stock SET price=? WHERE country_name=? AND account_year=?", (new_p, c_name, year))
          db.commit()
          await conv.send_message(custom_emoji_text(f"{P_YES} All existing '{html.escape(c_name)}' ({year}) accounts updated to {P_INR}{new_p}!"))
          
      elif action_data.startswith("apset|") and has_perm(uid, 'p_manage_stock'):
        parts = action_data.split("|")
        c_name, year = parts[1], parts[2]
        new_p = int((await get_reply(f"{P_ASST} <b>Enter Auto-Price for {html.escape(c_name)} ({year}):</b>\n<i>(Enter 0 to remove this auto-price)</i>")).text)
        if new_p == 0:
          cur.execute("DELETE FROM auto_prices WHERE country=? AND year=?", (c_name, year))
          await conv.send_message(custom_emoji_text(f"{P_YES} Auto-Price for {html.escape(c_name)} ({year}) removed!"))
        else:
          cur.execute("INSERT OR REPLACE INTO auto_prices (country, year, price) VALUES (?,?,?)", (c_name, year, new_p))
          await conv.send_message(custom_emoji_text(f"{P_YES} Auto-Price for {html.escape(c_name)} ({year}) set to {P_INR}{new_p}! Incoming accounts will use this price automatically."))
        db.commit()

      elif action_data == "addzip" and has_perm(uid, 'p_add_stock'):
        resp = await get_reply(f"{P_PKG} <b>Send the ZIP file containing <code>.session</code> files:</b>")
        if not resp.file or not resp.file.name.endswith('.zip'): return await conv.send_message(custom_emoji_text(f"{P_NO} Invalid file."))
        
        await conv.send_message(custom_emoji_text(f"{P_WAIT} <b>Extracting & Scanning Accounts...</b>"))
        zip_path = await bot.download_media(resp, "temp_sessions.zip")
        extracted_dir = f"temp_extracted_{int(time.time())}"
        os.makedirs(extracted_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref: zip_ref.extractall(extracted_dir)

        groups = {}
        for file in os.listdir(extracted_dir):
          if not file.endswith(".session"): continue
          sess_path = os.path.join(extracted_dir, file)
          clean_path = sess_path[:-8]
          try:
            client = TelegramClient(clean_path, API_ID, API_HASH)
            await client.connect()
            if not await client.is_user_authorized(): await client.disconnect(); continue
            me = await client.get_me()
            phone = getattr(me, 'phone', None)
            if not phone: await client.disconnect(); continue
            
            c_name = get_country_info(phone)
            pwd = await client(GetPasswordRequest())
            has_2fa = pwd.has_password
            year = await detect_account_year(client)
            await client.disconnect()

            key = (c_name, year, has_2fa)
            if key not in groups: groups[key] = []
            groups[key].append({"phone": phone, "path": clean_path})
          except Exception as e: logger.error(f"Scan error: {e}")

        for key in list(groups.keys()):
          if key[0] == "Unknown":
            sample_phone = groups[key][0]["phone"]
            await conv.send_message(custom_emoji_text(f"{P_WARN} <b>Country not recognized for +{sample_phone}!</b>"))
            new_name = html.escape((await get_reply(f"{P_GLOBE} <b>Enter Country Name:</b>\n<i>Example: India</i>")).text)
            new_key = (new_name, key[1], key[2])
            groups[new_key] = groups.pop(key)

        success = 0
        for (c_name, year, has_2fa), accs in groups.items():
          twofa_pass = "None"
          if has_2fa: twofa_pass = html.escape((await get_reply(f"{P_2FA} <b>Enter 2FA Password for {len(accs)}x {html.escape(c_name)} accounts:</b>")).text)

          auto_row = cur.execute("SELECT price FROM auto_prices WHERE country=? AND year=?", (c_name, str(year))).fetchone()
          if not auto_row: auto_row = cur.execute("SELECT price FROM auto_prices WHERE country=? AND year='Common'", (c_name,)).fetchone()

          if auto_row:
            price = auto_row[0]
            await conv.send_message(custom_emoji_text(f"{P_FIRE} <b>Auto-Price Applied:</b> {len(accs)}x {html.escape(c_name)} ({year}) at {P_INR}{price}."))
          else:
            existing_price = cur.execute("SELECT price FROM stock WHERE country_name=? LIMIT 1", (c_name,)).fetchone()
            if existing_price:
              price = existing_price[0]
              await conv.send_message(custom_emoji_text(f"{P_FIRE} <b>Auto-Added:</b> {len(accs)}x {html.escape(c_name)} at {P_INR}{price} (Copied from DB)."))
            else:
              price = int((await get_reply(f"{P_DOC} Found {len(accs)}x {html.escape(c_name)} ({year}).\n{P_MONEY} Enter Price (₹):")).text)

          for acc in accs:
            perm_base = f"sessions/{acc['phone']}"
            for ext in ['.session', '.session-wal', '.session-shm', '.session-journal']:
              if os.path.exists(acc['path'] + ext): shutil.move(acc['path'] + ext, perm_base + ext)
            cur.execute("INSERT OR REPLACE INTO stock (phone, session_file, country_name, account_year, category, price, available, twofa) VALUES (?,?,?,?,?,?,?,?)", 
                  (acc['phone'], perm_base + ".session", c_name, year, 'Good', price, 1, twofa_pass))
            success += 1
        db.commit()
        os.remove(zip_path); shutil.rmtree(extracted_dir)
        await conv.send_message(custom_emoji_text(f"{P_YES} {P_PARTY} <b>Bulk Interactive Upload Complete!</b>\n{P_ON} Added: {success}"))

      elif action_data == "addstock" and has_perm(uid, 'p_add_stock'):
        phone = (await get_reply(f"{P_PHONE} Enter Phone (+919999...):")).text.replace(" ", "").replace("+", "")
        sp = f"sessions/{phone}"
        client = TelegramClient(sp, API_ID, API_HASH)
        await client.connect()
        sreq = await client.send_code_request(phone)
        
        twofa_pass = "None"
        try: 
          await client.sign_in(phone, (await get_reply(f"{P_OTP} OTP:")).text, phone_code_hash=sreq.phone_code_hash)
        except SessionPasswordNeededError: 
          twofa_pass = html.escape((await get_reply(f"{P_2FA} 2FA Pass required. Enter it now:")).text)
          await client.sign_in(password=twofa_pass)
        
        c_name = get_country_info(phone)
        
        if c_name == "Unknown":
          await conv.send_message(custom_emoji_text(f"{P_WARN} <b>Country not recognized for +{phone}!</b>"))
          c_name = html.escape((await get_reply(f"{P_GLOBE} <b>Enter Country Name:</b>\n<i>Example: India</i>")).text)
        
        auto_year = await detect_account_year(client)
        await client.disconnect()
        
        year = int((await get_reply(f"{P_CAL} Detected Year: <b>{auto_year}</b>\nReply with Year to confirm or change:")).text)
        auto_row = cur.execute("SELECT price FROM auto_prices WHERE country=? AND year=?", (c_name, str(year))).fetchone()
        if not auto_row: auto_row = cur.execute("SELECT price FROM auto_prices WHERE country=? AND year='Common'", (c_name,)).fetchone()

        if auto_row:
          price = auto_row[0]
          await conv.send_message(custom_emoji_text(f"{P_FIRE} <b>Auto-Price Applied:</b> {P_INR}{price} for {html.escape(c_name)} ({year})"))
        else:
          existing_price = cur.execute("SELECT price FROM stock WHERE country_name=? LIMIT 1", (c_name,)).fetchone()
          if existing_price:
            price = existing_price[0]
            await conv.send_message(custom_emoji_text(f"{P_FIRE} <b>Auto-detected Price:</b> {P_INR}{price} for {html.escape(c_name)}"))
          else: price = int((await get_reply(f"{P_MONEY} Price (₹):")).text)
        
        cur.execute("INSERT OR REPLACE INTO stock (phone, session_file, country_name, account_year, category, price, available, twofa) VALUES (?,?,?,?,?,?,?,?)", 
              (phone, sp + ".session", c_name, year, 'Good', price, 1, twofa_pass))
        db.commit()
        await conv.send_message(custom_emoji_text(f"{P_YES} <b>Added!</b> {html.escape(c_name)}"))

      elif action_data == "supporturl" and has_perm(uid, 'p_settings'):
        url_inp = (await get_reply(f"{P_DOC} <b>Enter new Support Username or URL:</b>\n<i>(Examples: <code>https://t.me/m/P7am0xdlZmE1</code>)</i>")).text.strip()
        normalized = _normalize_tg_url(url_inp, "")
        if not normalized:
          await conv.send_message(custom_emoji_text(f"{P_NO} <b>Invalid Telegram support link.</b>\nPlease enter a valid <code>https://t.me/username</code>, <code>https://t.me/+invite</code>, or <code>@username</code>."))
        else:
          cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('support_url', ?)", (normalized,))
          db.commit()
          await conv.send_message(custom_emoji_text(f"{P_YES} <b>Support Link updated successfully!</b>\nTarget: <code>{html.escape(normalized)}</code>"))

      elif action_data == "supportchan" and has_perm(uid, 'p_settings'):
        chan_inp = (await get_reply(f"{P_GLOBE} <b>Enter new Support/Updates Channel Link or Username:</b>\n<i>(Examples: <code>https://t.me/...</code> or <code>@MyChannel</code>)</i>")).text.strip()
        normalized = _normalize_tg_url(chan_inp, "")
        if not normalized:
          await conv.send_message(custom_emoji_text(f"{P_NO} <b>Invalid Telegram channel link.</b>\nPlease enter a valid <code>https://t.me/channel</code>, <code>https://t.me/+invite</code>, or <code>@channel</code>."))
        else:
          cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('support_channel_url', ?)", (normalized,))
          db.commit()
          await conv.send_message(custom_emoji_text(f"{P_YES} <b>Support/Updates Channel Link updated successfully!</b>\nTarget: <code>{html.escape(normalized)}</code>"))

      elif action_data == "bcast" and has_perm(uid, 'p_stats'):
        await conv.send_message(custom_emoji_text(
          f"{P_TG} {P_WA} {P_IG} {P_APPS} <b>Broadcast</b>\n"
          f"────────────────\n\n"
          f"Send the content you want to broadcast. It can be:\n"
          f"• Plain text / article (HTML + premium emoji supported)\n"
          f"• Photo, video, GIF, document or audio — with an optional caption\n\n"
          f"<i>Whatever you send is delivered to every user exactly like this.</i>"))
        _bc = await conv.get_response()
        if (_bc.raw_text or '').strip().lower() == '/cancel':
          return await conv.send_message("Cancelled.")
        _bc_txt = _bc.text or ""
        _bc_ents = list(_bc.entities or [])
        _bc_raw = _bc.raw_text or ""
        # Keep exact entities (premium emoji, bold, spoiler, links...) when the admin sent a formatted message;
        # typed HTML tags (no entities) still go through the HTML parser.
        _bc_payload = (_bc_raw, _bc_ents) if _bc_ents else (_bc_txt, None)
        _bc_media = None
        if _bc.media and not isinstance(_bc.media, MessageMediaWebPage):
          _bc_media = _bc.media
        if not _bc_media and not _bc_txt.strip():
          return await conv.send_message(custom_emoji_text(f"{P_NO} Nothing to broadcast (empty message)."))
        btn_name = (await get_reply("Button Name (or 'skip'):")).text.strip()
        url = None
        if btn_name.lower() != 'skip':
          url = (await get_reply("URL:")).text.strip()
        btn = _safe_url_button(btn_name, url) if url else None
        btns = [[btn]] if btn is not None else None
        users = cur.execute("SELECT user_id FROM users").fetchall()
        # Preview exactly what users will receive, then ask for confirmation.
        await conv.send_message(custom_emoji_text(f"{P_EYE} <b>Preview</b> — this is what users will see:"))
        try:
          await _broadcast_deliver(uid, _bc_payload, _bc_media, btns)
        except Exception as ex:
          return await conv.send_message(custom_emoji_text(f"{P_NO} <b>Preview failed:</b> {html.escape(str(ex)[:300])}"))
        _ok = (await get_reply(f"{P_WARN} Send this to <b>{len(users)}</b> users? Type <code>YES</code> to send."))
        if (_ok.raw_text or "").strip().upper() != "YES":
          return await conv.send_message("Broadcast cancelled.")
        _status = await conv.send_message(custom_emoji_text(f"{P_TG} <b>Broadcasting...</b> 0/{len(users)}"))
        s, f, blocked = 0, 0, 0
        _ids = [int(r_[0]) for r_ in users]
        _BC_CONC = 25            # 25 parallel sends per second (Telegram limit is ~30/s)
        _done = 0
        for _i in range(0, len(_ids), _BC_CONC):
          _chunk = _ids[_i:_i + _BC_CONC]
          _t0 = time.time()
          _res = await asyncio.gather(
            *[_broadcast_deliver(u_, _bc_payload, _bc_media, btns) for u_ in _chunk],
            return_exceptions=True)
          for r_ in _res:
            if isinstance(r_, (UserIsBlockedError, InputUserDeactivatedError, PeerIdInvalidError)):
              blocked += 1
            elif isinstance(r_, BaseException):
              f += 1
            else:
              s += 1
          _done += len(_chunk)
          _el = time.time() - _t0
          if _el < 1.0:
            await asyncio.sleep(1.0 - _el)
          if (_i // _BC_CONC) % 4 == 3:
            try: await _status.edit(custom_emoji_text(f"{P_TG} <b>Broadcasting...</b> {_done}/{len(users)}"), parse_mode='html')
            except Exception: pass
        await conv.send_message(custom_emoji_text(
          f"{P_YES} <b>Broadcast complete!</b>\n"
          f"{P_USERS} Total: {len(users)}\n"
          f"{P_YES} Delivered: {s}\n"
          f"{P_NO} Blocked / deleted: {blocked}\n"
          f"{P_WARN} Failed: {f}"))

      elif action_data in ("baladd", "balrem") and has_perm(uid, 'p_bal'):
        is_add = action_data == "baladd"
        t_uid = int((await get_reply(f"{P_ACC} <b>User ID:</b>")).text.strip())
        if not cur.execute("SELECT 1 FROM users WHERE user_id=?", (t_uid,)).fetchone():
          return await conv.send_message(custom_emoji_text(f"{P_NO} User not found."))
        amt = float((await get_reply(f"{P_MONEY} <b>Amount to {'add' if is_add else 'remove'} (numbers only):</b>")).text.strip())
        if amt <= 0 or amt > 100000000:
          return await conv.send_message(custom_emoji_text(f"{P_NO} Invalid amount."))
        if not is_add:
          _bal_row = cur.execute("SELECT balance FROM users WHERE user_id=?", (t_uid,)).fetchone()
          if float((_bal_row[0] if _bal_row else 0) or 0) < amt:
            return await conv.send_message(custom_emoji_text(f"{P_NO} Insufficient user balance; no funds removed."))
        update_balance(t_uid, amt if is_add else -amt)
        logger.info("ADMIN_BALANCE_%s target=%s actor=%s amount=%.2f", "ADD" if is_add else "REMOVE", t_uid, uid, amt)
        await conv.send_message(custom_emoji_text(
          f"{P_YES} {'Added' if is_add else 'Removed'} {P_INR}{amt:.2f} {'to' if is_add else 'from'} {t_uid}."))

      elif action_data == "clonebot" and uid == ADMIN_ID and not IS_CLONE:
        async def _ask_secret(txt):
          r = await get_reply(txt)
          val = (getattr(r, "raw_text", None) or r.text or "").strip()
          try: await r.delete()
          except Exception: pass
          return val
        async def _clone_ask(prompt, check, fix=None, bad="Invalid input.", allow_skip=False):
          # Keeps asking until valid. /cancel aborts (get_reply). /skip allowed when allow_skip=True.
          msg = prompt
          while True:
            val = await _ask_secret(msg)
            if allow_skip and val.lower() in ("/skip", "skip"):
              return None
            if fix:
              val = fix(val)
            if check(val):
              return val
            msg = f"{P_NO} <b>{bad}</b> Please send it again.\n\n" + prompt
        def _fix_mail(v):
          # Telegram turns an e-mail into a link, so pull the plain address out of whatever came in.
          m = re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", v or "")
          return (m.group(0) if m else re.sub(r"[<>\s]", "", v or "")).lower()
        def _clone_imap_test(mail, pw):
          import imaplib as _il
          try:
            m = _il.IMAP4_SSL("imap.gmail.com", 993, timeout=15)
            try:
              m.login(mail, pw)
            finally:
              try: m.logout()
              except Exception: pass
            return "ok"
          except _il.IMAP4.error:
            return "auth"
          except Exception:
            return "net"
        _skip_hint = "\n\n<i>Optional — send <code>/skip</code> to leave this empty / use default.</i>"
        # Required: Bot Token + Owner ID. Everything else can be skipped.
        c_token = await _clone_ask(
          f"{P_GEAR} <b>Clone Bot — Step 1/6</b>\n\nSend the <b>Bot Token</b> of the NEW bot (create it in @BotFather)."
          f"\n\n<i>Required. Cannot skip.</i>",
          lambda v: bool(re.fullmatch(r"\d{6,12}:[A-Za-z0-9_-]{30,}", v)),
          lambda v: re.sub(r"\s+", "", v or ""), "Invalid bot token.")
        c_owner = await _clone_ask(
          f"{P_GEAR} <b>Step 2/6</b>\n\nSend the <b>Admin / Owner Telegram User ID</b> of the cloned bot (numbers only)."
          f"\n\n<i>Required. Cannot skip.</i>",
          lambda v: bool(re.fullmatch(r"\d{5,15}", v)),
          lambda v: re.sub(r"\s+", "", v or ""), "Invalid user ID.")
        c_store = await _clone_ask(
          f"{P_STORE} <b>Step 3/6</b>\n\nSend the <b>Store Name</b> of the new bot "
          f"(example: <code>SHUBHAM TG STORE</code>). It is shown everywhere inside the cloned bot."
          + _skip_hint,
          lambda v: bool(re.fullmatch(r"[\w .'\-|+!]{2,40}", v)),
          lambda v: re.sub(r"\s+", " ", (v or "")).strip(),
          "Invalid store name. Use 2-40 letters, numbers or spaces.",
          allow_skip=True)
        if not c_store:
          c_store = "TG Store"
        c_api_id = await _clone_ask(
          f"{P_GEAR} <b>Step 4/6</b>\n\nSend the <b>API ID</b> (from my.telegram.org)."
          f"\n\nDefault if skipped: main bot API ID."
          + _skip_hint,
          lambda v: bool(re.fullmatch(r"\d{4,12}", v)),
          lambda v: re.sub(r"\s+", "", v or ""), "Invalid API ID.",
          allow_skip=True)
        c_api_hash = await _clone_ask(
          f"{P_GEAR} <b>Step 5/6</b>\n\nSend the <b>API Hash</b> (32 characters)."
          f"\n\nDefault if skipped: main bot API Hash."
          + _skip_hint,
          lambda v: bool(re.fullmatch(r"[0-9a-fA-F]{32}", v)),
          lambda v: re.sub(r"\s+", "", v or ""), "Invalid API Hash.",
          allow_skip=True)
        if not c_api_id:
          c_api_id = str(API_ID)
        if not c_api_hash:
          c_api_hash = str(API_HASH)
        # Gmail / App Password — fully optional (skip both together)
        c_gmail, c_pw = "", ""
        c_gmail = await _clone_ask(
          f"{P_GEAR} <b>Step 6/6</b>\n\nSend the <b>Gmail address</b> used for FamPay / IMAP payment verification."
          f"\n\nYou can skip and set it later from the clone Admin panel."
          + _skip_hint,
          lambda v: bool(re.fullmatch(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", v)),
          _fix_mail, "Invalid Gmail address.",
          allow_skip=True)
        if c_gmail:
          _gm_tries = 0
          while True:
            c_pw = await _clone_ask(
              f"{P_GEAR} <b>Gmail App Password</b>\n\nSend the Gmail <b>App Password</b> (16 letters from Google Account → Security → App passwords). A normal Gmail password will not work for IMAP."
              + _skip_hint,
              lambda v: bool(re.fullmatch(r"[A-Za-z0-9]{16}", v)),
              lambda v: re.sub(r"[\s\-]+", "", v or ""), "Invalid App Password. It must be 16 letters.",
              allow_skip=True)
            if not c_pw:
              c_gmail = ""
              break
            _gm_tries += 1
            _t = await asyncio.to_thread(_clone_imap_test, c_gmail, c_pw)
            if _t != "auth":
              break
            if _gm_tries >= 3:
              await conv.send_message(custom_emoji_text(
                f"{P_WARN} <b>Gmail login could not be verified</b> after 3 tries. Continuing anyway. "
                f"You can fix it later from the clone's Admin → Configure IMAP (Gmail)."))
              break
            await conv.send_message(custom_emoji_text(
              f"{P_NO} <b>Gmail login failed.</b> The email or App Password is wrong "
              f"(2-Step Verification must be ON and IMAP enabled). Please send both again."))
        await conv.send_message(custom_emoji_text(f"{P_WAIT} <b>Cloning the bot, please wait (up to 45 seconds)...</b>"))
        try:
          c_ok, c_info = await _clone_create(c_token, int(c_owner), int(c_api_id), c_api_hash, c_gmail or "", c_pw or "", c_store)
        except Exception as _cex:
          logger.error("clone create failed: %s", _cex, exc_info=True)
          c_ok, c_info = False, "Clone error: " + html.escape(str(_cex)[:200])
        if c_ok:
          c_info += (
            f"\n\n{P_DOC} <b>API Docs:</b> <code>{html.escape(MAIN_API_DOCS_URL)}</code>"
            f"\n<i>Shown inside the clone under Admin → Servers APIs. "
            f"Generate Reseller API keys from the MAIN bot (Admin → API Keys) — "
            f"keys are saved in the main database. Server 1/2/3 still need their own provider URL + key.</i>")
        await conv.send_message(custom_emoji_text(f"{P_YES if c_ok else P_NO} {c_info}"))
        
      elif action_data == "referpct" and has_perm(uid, 'p_settings'):
        _cur = get_refer_percent()
        _raw = (await get_reply(
          f"{P_GIFT} <b>Set Refer Bonus %</b>\n\nCurrent: <b>{_cur:g}%</b>\n\n"
          f"Send the % a referrer earns on every deposit of the user they referred "
          f"(0 to 100, send 0 to turn referral bonus off):")).text.strip().replace("%", "")
        try:
          _new = float(_raw)
        except Exception:
          return await conv.send_message(custom_emoji_text(f"{P_NO} <b>Invalid number.</b>"))
        if _new < 0 or _new > 100:
          return await conv.send_message(custom_emoji_text(f"{P_NO} <b>Send a number between 0 and 100.</b>"))
        set_setting('refer_percent', str(_new))
        await conv.send_message(custom_emoji_text(
          f"{P_YES} <b>Refer bonus set to {_new:g}%.</b>\nIt applies to all future deposits of referred users."))

      elif action_data == "discount" and has_perm(uid, 'p_settings'):
        t_uid = int((await get_reply(f"{P_ACC} <b>User ID:</b>")).text)
        pct = int((await get_reply(f"{P_GIFT} <b>Discount % (0 to remove):</b>")).text)
        cur.execute("UPDATE users SET discount=? WHERE user_id=?", (pct, t_uid))
        db.commit()
        await conv.send_message(custom_emoji_text(f"{P_YES} User {t_uid} has {pct}% discount."))

      elif action_data == "usdtrate" and has_perm(uid, 'p_settings'):
        r = float((await get_reply(f"{P_USDT} <b>New USDT Rate (INR):</b>")).text)
        cur.execute("UPDATE settings SET value=? WHERE key='usdt_rate'", (str(r),))
        db.commit()
        await conv.send_message(custom_emoji_text(f"{P_YES} Rate set to {r}."))

      elif action_data == "restoreusr" and has_perm(uid, 'p_settings'):
        if uid != ADMIN_ID:
          return await conv.send_message(custom_emoji_text(f"{P_NO} Only the owner can restore a backup."))
        resp = await get_reply(
          f"{P_DOC} <b>Send the full backup <code>.zip</code> file.</b>\n"
          f"{P_WARN} Script, database and sessions will be replaced and the bot will restart.")
        if not resp.file or not (resp.file.name or "").lower().endswith(".zip"):
          return await conv.send_message(custom_emoji_text(f"{P_NO} Invalid file. Send the backup .zip."))
        tmp_zip = f"temp_restore_{int(time.time())}.zip"
        try:
          await bot.download_media(resp, tmp_zip)
          await conv.send_message(custom_emoji_text(f"{P_WAIT} Restoring everything..."))
          n_files = restore_full_backup(tmp_zip)
        except ValueError as ex:
          return await conv.send_message(custom_emoji_text(f"{P_NO} {html.escape(str(ex))}"))
        finally:
          if os.path.exists(tmp_zip):
            try: os.remove(tmp_zip)
            except Exception: pass
        await conv.send_message(custom_emoji_text(
          f"{P_YES} <b>Restore complete.</b>\n{P_FOLDER} Database + {n_files} files + script restored.\n"
          f"{P_CW} Restarting bot..."))
        asyncio.get_event_loop().call_later(2, _restart_bot)

      elif action_data == "delacc" and has_perm(uid, 'p_manage_stock'):
        raw = (await get_reply(f"{P_PHONE} <b>Send the account phone number to delete</b> (e.g. 919876543210):")).text
        digits = re.sub(r"\D", "", raw or "")
        if not digits: return await conv.send_message(custom_emoji_text(f"{P_NO} Invalid number."))
        row = cur.execute("SELECT phone, session_file, country_name, account_year, price, available FROM stock "
                          "WHERE REPLACE(REPLACE(phone,'+',''),' ','')=?", (digits,)).fetchone()
        if not row: return await conv.send_message(custom_emoji_text(f"{P_NO} Account not found in stock."))
        phone, sess, c_name, yr, pr, avail = row
        if phone in active_orders:
          return await conv.send_message(custom_emoji_text(f"{P_WARN} This account is in an active order. Try later."))
        ok = (await get_reply(
          f"{P_WARN} <b>Delete this account?</b>\n{P_PHONE} <code>{html.escape(str(phone))}</code>\n"
          f"{P_GLOBE} {html.escape(str(c_name))} | {yr} | ₹{pr}\n\nReply <b>YES</b> to confirm.")).text.strip().upper()
        if ok != "YES": return await conv.send_message(custom_emoji_text(f"{P_NO} Cancelled."))
        cur.execute("DELETE FROM stock WHERE phone=?", (phone,))
        db.commit()
        if sess: delete_session_files(sess)
        await conv.send_message(custom_emoji_text(f"{P_YES} Account <code>{html.escape(str(phone))}</code> deleted from stock."))

      elif action_data == "ban" and has_perm(uid, 'p_bal'):
        t_uid = int((await get_reply(f"{P_ACC} <b>User ID:</b>")).text)
        is_ban = cur.execute("SELECT banned FROM users WHERE user_id=?", (t_uid,)).fetchone()
        if not is_ban: return await conv.send_message(custom_emoji_text(f"{P_NO} User not found."))
        if is_protected_user(t_uid): return await conv.send_message(custom_emoji_text(f"{P_NO} Admins cannot be frozen or banned."))
        ns = 0 if is_ban[0] == 1 else 1
        cur.execute("UPDATE users SET banned=? WHERE user_id=?", (ns, t_uid))
        db.commit()
        await conv.send_message(custom_emoji_text(f"User {t_uid} status updated: {'Banned' if ns == 1 else 'Unbanned'}."))

    except ValueError: await conv.send_message(custom_emoji_text(f"{P_NO} Cancelled."))
    except Exception as e: await conv.send_message(custom_emoji_text(f"{P_NO} Error: {e}"))

@bot.on(events.NewMessage(pattern=r"(?i)^/refill(?:\s+(\d+))?"))
async def handle_refill_command(e):
  try:
    uid = e.sender_id
    if not uid: return
    ensure_user(uid)
    if is_user_banned(uid): return

    match = e.pattern_match.group(1)
    if not match:
      refill_state[uid] = {'step': 'wait_order_id'}
      await e.respond(custom_emoji_text(f"{P_ASST} <b>Please enter your SMM Order No. for refill:</b>\n<i>(Type /cancel to abort)</i>"))
    else:
      bot_order_id = int(match)
      order_row = cur.execute("SELECT user_id, smm_order_id FROM smm_orders WHERE bot_order_id=?", (bot_order_id,)).fetchone()
      if not order_row:
        return await e.respond(custom_emoji_text(f"{P_NO} Order ID <code>{bot_order_id}</code> not found in database."))
      owner_uid, smm_order_id = order_row
      if owner_uid != uid and not is_admin(uid):
        return await e.respond(custom_emoji_text(f"{P_NO} This order does not belong to you."))
      if not smm_order_id or smm_order_id == 'SUCCESS':
        return await e.respond(custom_emoji_text(f"{P_NO} Valid SMM Panel Order ID not available for this order."))
      
      refill_state[uid] = {'step': 'wait_screenshot', 'bot_order_id': bot_order_id, 'smm_order_id': smm_order_id}
      await e.respond(
        custom_emoji_text(f"{P_DOC} <b>Order ID Verified: #{bot_order_id}</b>\n\n"
        f"Please send a <b>screenshot</b> showing the invite link joined statistics (showing member list and joined count, exactly like the reference example).\n\n"
        f"<i>Send the screenshot now:</i>")
      )
  except Exception as ex:
    logger.error(f"Refill error: {ex}")

@bot.on(events.NewMessage(pattern=r"(?i)^/s1raw(?:@\w+)?(?:\s+([A-Za-z]{2}))?\s*$"))
async def handle_s1_raw(e):
  """Admin only: show the raw Server 1 API account JSON (to verify field names)."""
  if not e.sender_id or not is_admin(e.sender_id):
    return
  code = (e.pattern_match.group(1) or "IN").upper()
  items = await asyncio.to_thread(fetch_s1_items, code, True, None, 20, None, None)
  if isinstance(items, dict) or not items:
    return await e.respond(f"No accounts / error for {code}: {items if isinstance(items, dict) else 'empty'}")
  raw = json.dumps(items[0].get("raw"), indent=1, ensure_ascii=False)[:3500]
  await e.respond(f"<b>Raw API account ({code})</b>\n<pre>{html.escape(raw)}</pre>", parse_mode="html")


@bot.on(events.NewMessage(pattern=r"(?i)^/admin(?:@\w+)?\s*$"))
async def handle_admin_command(e):
  """Open the admin panel only through /admin."""
  uid = e.sender_id
  if not uid:
    return
  if not is_admin(uid):
    await e.respond("You are not authorized to use the admin panel.")
    return
  for state in (session_buy_state, deposit_input, smm_order_state, refill_state, waiting_proof, admin_dep_state):
    state.pop(uid, None)
  try:
    await admin_panel_handler(e)
  except Exception:
    logger.exception("Admin panel error for %s", uid)
    await e.respond("Admin panel could not be opened. Please check the bot logs.")

@bot.on(events.NewMessage(pattern=r"(?i)^/start"))
async def handle_start(e):
  try:
    uid = e.sender_id
    if not uid: return
    
    existing_user = cur.execute("SELECT 1 FROM users WHERE user_id=?", (uid,)).fetchone()
    is_new_user = existing_user is None
    _sender = await e.get_sender()
    ensure_user(uid, getattr(_sender, 'username', '') or '', getattr(_sender, 'first_name', '') or '')
    if is_new_user:
      _spawn_bg(notify_new_user(uid, e))        # admin notice runs in the background
      try:
        _pl = ((e.raw_text or "").split(maxsplit=1) + [""])[1].strip()
        if _pl.lower().startswith("ref_"):
          _pl = _pl[4:]
        if _pl.isdigit():
          _rid = int(_pl)
          if _rid != uid and cur.execute("SELECT 1 FROM users WHERE user_id=?", (_rid,)).fetchone():
            cur.execute("INSERT OR IGNORE INTO referrals (referred_id, referrer_id) VALUES (?,?)", (uid, _rid))
            db.commit()
            _spawn_bg(_notify_new_referral(_rid))
      except Exception as ex:
        logger.warning("referral capture failed: %s", ex)
    if is_user_banned(uid): return

    if not is_bot_online() and not is_admin(uid):
      return await e.respond(custom_emoji_text(bot_block_text()))
    
    session_buy_state.pop(uid, None)
    deposit_input.pop(uid, None)
    waiting_proof.pop(uid, None)
    smm_order_state.pop(uid, None)
    refill_state.pop(uid, None)
    redeem_state.pop(uid, None)
    S1_SEARCH_STATE.pop(uid, None)
    user_chat_state.pop(uid, None)

    is_joined = await check_channel_joined(uid)
    if not is_joined:
      rows = cur.execute("SELECT title, invite_url FROM force_channels").fetchall()
      btns = []
      for title, invite_url in rows:
        b = _safe_url_button(title or "Join Channel", invite_url)
        if b is not None:
          btns.append([b])
      btns.append([Button.inline("Verify Joined", "verify_join")])
      msg = f"{P_WARN} <b>You must join our channels first!</b>"
      return await e.respond(custom_emoji_text(msg), buttons=btns)

    _fx = _MSG_EFFECT.set(FIRE_EFFECT_ID)      # fire effect on the /start menu
    try:
      await send_main_menu(e, uid)
    finally:
      try: _MSG_EFFECT.reset(_fx)
      except Exception: pass
  except Exception as ex: 
    logger.error(f"Start Error: {ex}", exc_info=True)

@bot.on(events.NewMessage(pattern=r"(?i)^/cancel(?:@\w+)?\s*$"))
async def handle_cancel(e):
  """Abort any pending multi-step flow (deposit UTR, screenshot, buy, etc.)."""
  uid = e.sender_id
  if not uid:
    return
  had_state = False
  for _state in (deposit_input, waiting_proof, session_buy_state,
                 smm_order_state, refill_state, redeem_state, S1_SEARCH_STATE):
    if uid in _state:
      had_state = True
      _state.pop(uid, None)
  if uid in user_chat_state:
    _chat = user_chat_state.pop(uid, None)
    await e.respond(custom_emoji_text(f"{P_YES} Shop chat closed."))
    if _chat:
      for _aid in get_all_admin_ids():
        try: await bot.send_message(int(_aid), custom_emoji_text(f"{P_WARN} User closed chat for Shop Order #{_chat['oid']}."))
        except Exception: pass
    return
  if is_admin(uid) and uid in admin_reply_state:
    _chat = admin_reply_state.pop(uid, None)
    await e.respond(custom_emoji_text(f"{P_YES} Admin reply/chat mode closed."))
    return
  if had_state:
    await e.respond(custom_emoji_text(f"{P_NO} <b>Cancelled.</b> Nothing was charged."))
    return
  # If the user has a pending digital-shop order, /cancel cancels the newest one and refunds it once.
  _pending_shop = cur.execute("SELECT id,price,product_name FROM shop_orders WHERE user_id=? AND lower(status)='pending' ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
  if _pending_shop:
    _oid, _price, _pname = _pending_shop
    async with get_user_lock(uid):
      cur.execute("UPDATE shop_orders SET status='cancelled' WHERE id=? AND user_id=? AND lower(status)='pending'", (_oid, uid))
      _changed = cur.rowcount == 1
      if _changed:
        cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (_price, uid))
        cur.execute("UPDATE global_orders SET status='CANCELLED - REFUNDED',refunded=1 WHERE service='shop' AND local_ref=?", (str(_oid),))
      db.commit()
    if _changed:
      await e.respond(custom_emoji_text(f"{P_YES} Shop order <code>#{_oid}</code> cancelled and ₹{_price} refunded."), parse_mode='html')
      await notify_admins(f"{P_WARN} Shop order #{_oid} cancelled by user {uid}; ₹{_price} refunded.")
    else:
      await e.respond(custom_emoji_text(f"{P_ASST} Nothing to cancel."))
    return
  await e.respond(custom_emoji_text(f"{P_ASST} Nothing to cancel."))


# ====================================================================
# ================= EXTRA FEATURES (v5) ==============================
# ====================================================================
user_chat_state = {}      # uid -> {'oid': int}              (user <-> admin chat)
admin_reply_state = {}    # admin_id -> {'oid': int, 'mode': 'deliver'|'chat'}
_ORDER_MSG_MAP = {}       # (admin_id, msg_id) -> (order_id, mode)
_LOADING_PENDING = {}
_LOADING_TEXT = "\u23f3 <b>Loading...</b>\n\nPlease wait a moment."


def _ensure_extra_schema():
  cur.execute("""
    CREATE TABLE IF NOT EXISTS shop_orders (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER,
      product_id INTEGER,
      product_name TEXT,
      price INTEGER,
      status TEXT DEFAULT 'pending',
      delivery TEXT DEFAULT '',
      created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      delivered_at TEXT DEFAULT ''
    )""")
  for stmt in (
    "ALTER TABLE orders ADD COLUMN session_file TEXT DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN twofa_pass TEXT DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN terminated INTEGER DEFAULT 0",
  ):
    try:
      cur.execute(stmt)
    except sqlite3.OperationalError:
      pass
  db.commit()


_ensure_extra_schema()


def _now_str():
  return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _sep():
  return "\u2500" * 16


# --------------------------------------------------------------------
# NEW USER NOTIFICATION (admins only)
# --------------------------------------------------------------------
async def notify_new_user(uid, e=None):
  try:
    name, uname = "-", "-"
    try:
      sender = await e.get_sender() if e is not None else None
      if sender is not None:
        name = " ".join(x for x in (getattr(sender, 'first_name', None),
                                    getattr(sender, 'last_name', None)) if x) or "-"
        uname = ("@" + sender.username) if getattr(sender, 'username', None) else "-"
    except Exception:
      pass
    total = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    await notify_admins(
      f"{P_PARTY} <b>NEW USER JOINED</b> {P_PARTY}\n"
      f"{_sep()}\n"
      f"{P_ID} <b>User ID:</b> <code>{uid}</code>\n"
      f"{P_ACC} <b>Name:</b> {html.escape(name)}\n"
      f"{P_LINK} <b>Username:</b> {html.escape(uname)}\n"
      f"{P_PKG} <b>Total Users:</b> {total}\n"
      f"{P_TIME} {_now_str()}")
  except Exception as ex:
    logger.error(f"notify_new_user failed: {ex}", exc_info=True)


# --------------------------------------------------------------------
# SESSION FILE HELPERS
# --------------------------------------------------------------------
def _string_to_session_file(string_session, path_noext):
  """Convert a Telethon StringSession into a normal <path>.session file."""
  from telethon.sessions import SQLiteSession, StringSession
  ss = StringSession(string_session)
  s = SQLiteSession(path_noext)
  s.set_dc(ss.dc_id, ss.server_address, ss.port)
  s.auth_key = ss.auth_key
  s.save()
  s.close()
  return path_noext + ".session"


async def _send_manual_session_file(uid, phone, sess_path, twofa, country=""):
  """Send the stored .session file of a manual-stock account."""
  base = sess_path[:-8] if str(sess_path).endswith(".session") else str(sess_path)
  src = base + ".session"
  if not os.path.exists(src):
    return False
  tmp_dir = f"tmp_sess_{uid}_{int(time.time())}"
  os.makedirs(tmp_dir, exist_ok=True)
  dst = os.path.join(tmp_dir, f"{phone}.session")
  try:
    shutil.copyfile(src, dst)
    pw = twofa if twofa and twofa != "None" else "No password"
    cap = (f"{P_KEY} <b>Session File</b>\n"
           f"{P_PHONE} <b>Number:</b> <code>+{html.escape(str(phone))}</code>\n"
           f"{P_FLAG} <b>Country:</b> {html.escape(str(country))}\n"
           f"{P_2FA} <b>2FA:</b> <code>{html.escape(str(pw))}</code>\n\n"
           f"{P_WARN} <i>Keep it private. Anyone with this file controls the account.</i>")
    await bot.send_file(uid, dst, caption=custom_emoji_text(cap), parse_mode='html')
    return True
  finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


_S1_SESSION_INFLIGHT = set()


async def _send_s1_session_file(uid, order_id):
  """Send a Telethon .session file for a Server-1 (API) order (never twice at once).

  Returns (ok, note)."""
  if order_id in _S1_SESSION_SENT:
    return True, "already sent"
  if order_id in _S1_SESSION_INFLIGHT:
    return False, "in progress"
  _S1_SESSION_INFLIGHT.add(order_id)
  try:
    return await _send_s1_session_file_inner(uid, order_id)
  finally:
    _S1_SESSION_INFLIGHT.discard(order_id)


async def _send_s1_session_file_inner(uid, order_id, mark_sent=True):
  row = cur.execute(
    "SELECT account_no, number, password, secured FROM s2_orders WHERE order_id=?",
    (order_id,)).fetchone()
  if not row or not row[0]:
    return False, "Session is not ready yet."
  account_no, number, password, secured = row
  if int(secured or 0) >= 2:
    return False, "Bot session already terminated - this session no longer works."
  res = await _s1_session_res(order_id, account_no)
  if not isinstance(res, dict) or not res.get("ok"):
    return False, _api_error_text(res) if isinstance(res, dict) else "Session fetch failed."
  sess = str(res.get("string_session") or res.get("session") or res.get("string") or "").strip()
  if not sess:
    return False, "Session is not available yet."
  tmp_dir = f"tmp_sess_{uid}_{int(time.time())}"
  os.makedirs(tmp_dir, exist_ok=True)
  try:
    num_clean = re.sub(r"\D", "", str(number or "")) or str(account_no)
    try:
      path = _string_to_session_file(sess, os.path.join(tmp_dir, num_clean))
    except Exception as ex:
      logger.warning("string->session conversion failed: %s", ex)
      path = os.path.join(tmp_dir, f"{num_clean}_string_session.txt")
      with open(path, "w") as fh:
        fh.write(sess)
    pw = _s1_2fa_text(password, order_id)
    cap = (f"{P_KEY} <b>Session File</b>\n"
           f"{P_PHONE} <b>Number:</b> <code>{html.escape(str(number or '-'))}</code>\n"
           f"{P_2FA} <b>2FA:</b> <code>{html.escape(pw)}</code>\n\n"
           f"{P_WARN} <i>Keep it private. Anyone with this file controls the account.</i>")
    await bot.send_file(uid, path, caption=custom_emoji_text(cap), parse_mode='html')
    if mark_sent:
      _S1_SESSION_SENT.add(order_id)
    return True, "ok"
  finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# --------------------------------------------------------------------
# DIGITAL SHOP -> ORDER SYSTEM (admin delivers manually from the bot)
# --------------------------------------------------------------------
async def digital_buy(event, pid):
  """Shop purchase: charge the user, create an order and send it to admins."""
  uid = int(event.sender_id)
  try:
    pid = int(pid)
    row = cur.execute(
      "SELECT id,name,price FROM digital_products WHERE id=? AND active=1", (pid,)).fetchone()
    if not row:
      return await safe_callback_answer(event, "Product unavailable.", alert=True)
    _, name, price = row
    name = str(name or f"Product #{pid}")
    price = int(price)
    if price <= 0:
      return await safe_callback_answer(event, "Invalid product price. Please contact admin.", alert=True)

    async with get_user_lock(uid):
      cur.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?",
                  (price, uid, price))
      if cur.rowcount != 1:
        db.rollback()
        return await safe_callback_answer(event, f"Insufficient balance. Need \u20b9{price}.", alert=True)
      cur.execute("INSERT INTO shop_orders (user_id, product_id, product_name, price) VALUES (?,?,?,?)",
                  (uid, pid, name, price))
      oid = cur.lastrowid
      db.commit()
    global_id = _global_order_register('shop', oid, uid, price, 'PENDING')

    msg = (f"{P_YES} {P_PARTY} <b>Order Created!</b>\n{_sep()}\n\n"
           f"{P_ID} <b>Bot Order ID:</b> <code>{global_id}</code>\n"
           f"{P_ID} <b>Shop Order ID:</b> <code>#{oid}</code>\n"
           f"{P_DOC} <b>Product:</b> {html.escape(name)}\n"
           f"{P_MONEY} <b>Paid:</b> \u20b9{price}\n"
           f"{P_WAIT} <b>Status:</b> Pending\n\n"
           f"{P_ASST} Your order has been sent to the admin. You will get the product "
           f"here in the bot very soon. You can also chat with the admin below.")
    btns = [[Button.inline("Chat with Admin", f"shp_uchat|{oid}", style="primary")],
            [Button.inline("Cancel Order & Refund", f"shp_ucancel|{oid}", style="danger")],
            [Button.inline("Order Details", f"mo_shop|{oid}", style="success")],
            [Button.inline("Back to Shop", "digital_shop")]]
    try:
      await e_edit_or_send(event, custom_emoji_text(msg), btns)
    except Exception as send_ex:
      logger.error("Shop receipt message failed after order commit gid=%s oid=%s: %s", global_id, oid, send_ex, exc_info=True)
      await bot.send_message(uid, custom_emoji_text(msg), buttons=btns, parse_mode='html')
    await _notify_admins_shop_order(oid)
  except Exception as ex:
    logger.error(f"Digital Buy Error: {ex}", exc_info=True)
    # If an order row was already committed, do not falsely report a failed purchase.
    try:
      existing = cur.execute("SELECT id FROM shop_orders WHERE user_id=? AND product_id=? AND status='pending' ORDER BY id DESC LIMIT 1", (uid, int(pid))).fetchone()
      if existing:
        await bot.send_message(uid, custom_emoji_text(f"{P_WARN} Your order #{existing[0]} was created. Open My Orders or contact support."), parse_mode='html')
      else:
        await bot.send_message(uid, custom_emoji_text("Order could not be completed. Please contact support."),
                               buttons=[[Button.inline("Back to Shop", "digital_shop")]])
    except Exception:
      pass


async def _notify_admins_shop_order(oid):
  row = cur.execute(
    "SELECT user_id, product_name, price, created FROM shop_orders WHERE id=?", (oid,)).fetchone()
  if not row:
    return
  uid, name, price, created = row
  global_id = _global_order_register('shop', oid, uid, price, 'PENDING')
  label = await _user_label(uid)
  text = (f"{P_CART} {P_ROCKET} <b>NEW SHOP ORDER</b>\n{_sep()}\n\n"
          f"{P_ID} Bot Order ID: <code>{global_id}</code>\n"
          f"{P_ID} Shop Order ID: <code>#{oid}</code>\n"
          f"{P_ACC} <b>User:</b> <code>{uid}</code> ({html.escape(label)})\n"
          f"{P_DOC} <b>Product:</b> {html.escape(str(name))}\n"
          f"{P_MONEY} <b>Paid:</b> \u20b9{price}\n"
          f"{P_TIME} {html.escape(str(created))}\n\n"
          f"{P_ASST} Tap <b>Deliver</b> and send the product (text / file / photo), "
          f"or just <b>reply to this message</b> with the product.")
  btns = [[Button.inline("Deliver Product", f"shp_dl|{oid}", style="success")],
          [Button.inline("Chat with User", f"shp_chat|{oid}", style="primary"),
           Button.inline("Reject & Refund", f"shp_rej|{oid}", style="danger")],
          [Button.inline("Close Chat", f"shp_aclose|{oid}", style="danger")]]
  for admin_id in get_all_admin_ids():
    try:
      sent = await bot.send_message(int(admin_id), custom_emoji_text(text), buttons=btns, parse_mode='html')
      _ORDER_MSG_MAP[(int(admin_id), sent.id)] = (oid, 'deliver')
    except Exception as ex:
      logger.error(f"Shop order notify failed for {admin_id}: {ex}")


async def _shop_callbacks(e, data):
  uid = e.sender_id
  action, _, arg = data.partition("|")

  # ---------------- user side ----------------
  if action == "shp_uchat":
    oid = int(arg)
    row = cur.execute("SELECT user_id, product_name FROM shop_orders WHERE id=?", (oid,)).fetchone()
    if not row or int(row[0]) != int(uid):
      return await safe_callback_answer(e, "Order not found.", alert=True)
    user_chat_state[uid] = {'oid': oid}
    await safe_callback_answer(e)
    return await e.respond(custom_emoji_text(
      f"{P_ASST} <b>Chat with Admin</b> \u2014 Order <code>#{oid}</code>\n\n"
      f"Send your message now (text, photo or file). The admin will reply here.\n"
      f"<i>Tap Close Chat or send /cancel to stop.</i>"),
      buttons=[[Button.inline("Close Chat", f"shp_uend|{oid}", style="danger")]])
  if action == "shp_uend":
    old = user_chat_state.pop(uid, None)
    await safe_callback_answer(e, "Chat closed.")
    if old:
      for admin_id in get_all_admin_ids():
        try: await bot.send_message(int(admin_id), custom_emoji_text(f"{P_WARN} User closed chat for Shop Order #{old['oid']}."))
        except Exception: pass
    return await e.respond(custom_emoji_text(f"{P_YES} <b>Chat closed.</b>"),
                           buttons=[[Button.inline("My Orders", "cb_orders")]])

  if action == "shp_ucancel":
    oid = int(arg)
    row = cur.execute("SELECT user_id,product_name,price,status FROM shop_orders WHERE id=?", (oid,)).fetchone()
    if not row or int(row[0]) != int(uid):
      return await safe_callback_answer(e, "Order not found.", alert=True)
    _buyer, _name, _price, _status = row
    if str(_status).lower() != 'pending':
      return await safe_callback_answer(e, f"Order is already {_status}; it cannot be cancelled here.", alert=True)
    async with get_user_lock(uid):
      cur.execute("UPDATE shop_orders SET status='cancelled' WHERE id=? AND user_id=? AND lower(status)='pending'", (oid, uid))
      _shop_cancelled = cur.rowcount == 1
      if _shop_cancelled:
        cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (_price, uid))
      db.commit()
    if not _shop_cancelled:
      return await safe_callback_answer(e, "Order was already processed.", alert=True)
    cur.execute("UPDATE global_orders SET status='CANCELLED - REFUNDED' WHERE service='shop' AND local_ref=?", (str(oid),))
    db.commit()
    await safe_callback_answer(e, "Cancelled and refunded.", alert=True)
    await bot.send_message(uid, custom_emoji_text(f"{P_YES} Shop order <code>#{oid}</code> cancelled. ₹{_price} refunded to your wallet."), parse_mode='html')
    await notify_admins(f"{P_WARN} Shop order #{oid} was cancelled by user {uid}; ₹{_price} refunded.")
    return

  # ---------------- admin side ----------------
  if not is_admin(uid):
    return await safe_callback_answer(e, "Admins only.", alert=True)
  if action == "shp_end":
    admin_reply_state.pop(uid, None)
    await safe_callback_answer(e, "Done.")
    return await e.respond(custom_emoji_text(f"{P_YES} <b>Reply mode closed.</b>"))
  if action == "shp_aclose":
    oid = int(arg)
    st = admin_reply_state.get(uid)
    if st and int(st.get('oid', -1)) == oid:
      admin_reply_state.pop(uid, None)
    buyer_row = cur.execute("SELECT user_id FROM shop_orders WHERE id=?", (oid,)).fetchone()
    if buyer_row:
      buyer = int(buyer_row[0])
      user_chat_state.pop(buyer, None)
      try:
        await bot.send_message(buyer, custom_emoji_text(f"{P_WARN} Admin closed the chat for Shop Order #{oid}. You can open a new chat from My Orders."),
                               buttons=[[Button.inline("My Orders", "cb_orders")]])
      except Exception as close_ex:
        logger.warning("Shop close-chat user notify failed: %s", close_ex)
    await safe_callback_answer(e, "Chat closed.")
    return await e.respond(custom_emoji_text(f"{P_YES} <b>Chat closed for order #{oid}.</b>"))

  oid = int(arg)
  row = cur.execute("SELECT user_id, product_name, price, status FROM shop_orders WHERE id=?", (oid,)).fetchone()
  if not row:
    return await safe_callback_answer(e, "Order not found.", alert=True)
  buyer, name, price, status = row

  if action in ("shp_dl", "shp_chat"):
    mode = 'deliver' if action == "shp_dl" else 'chat'
    if mode == 'deliver':
      if str(status).lower() not in ('pending', 'delivering'):
        return await safe_callback_answer(e, f"Order is already {status}; delivery cannot be started.", alert=True)
      cur.execute("UPDATE shop_orders SET status='delivering' WHERE id=? AND lower(status) IN ('pending','delivering')", (oid,))
      if cur.rowcount != 1:
        db.rollback()
        return await safe_callback_answer(e, "Order status changed. Refresh the order first.", alert=True)
      cur.execute("UPDATE global_orders SET status='DELIVERING' WHERE service='shop' AND local_ref=?", (str(oid),))
      db.commit()
    admin_reply_state[uid] = {'oid': oid, 'mode': mode}
    await safe_callback_answer(e)
    what = ("Send the <b>product now</b> (text, file, photo...). Everything you send goes to the user."
            if mode == 'deliver' else
            "Type your message. It goes straight to the user.")
    return await e.respond(custom_emoji_text(
      f"{P_ASST} <b>Order #{oid}</b> \u2014 {html.escape(str(name))}\n{what}\n\n"
      f"<i>Send /done or tap Close Chat when finished.</i>"),
      buttons=[[Button.inline("Close Chat", f"shp_aclose|{oid}", style="danger")],
               [Button.inline("Finish", "shp_end|0", style="success")]])

  if action == "shp_rej":
    if status != 'pending':
      return await safe_callback_answer(e, f"Order is already {status}.", alert=True)
    async with get_user_lock(int(buyer)):
      cur.execute("UPDATE shop_orders SET status='rejected' WHERE id=? AND status='pending'", (oid,))
      if cur.rowcount == 1:
        cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (price, buyer))
        cur.execute("UPDATE global_orders SET status='CANCELLED - REFUNDED' WHERE service='shop' AND local_ref=?", (str(oid),))
      db.commit()
    await safe_callback_answer(e, "Rejected & refunded.")
    try:
      await bot.send_message(int(buyer), custom_emoji_text(
        f"{P_NO} <b>Order #{oid} rejected</b>\n{html.escape(str(name))}\n"
        f"{P_MONEY} \u20b9{price} has been refunded to your balance."),
        buttons=[[Button.inline("My Orders", "cb_orders")]])
    except Exception:
      pass
    return await e.respond(custom_emoji_text(f"{P_YES} Order #{oid} rejected and \u20b9{price} refunded."))


# --------------------------------------------------------------------
# ADMIN <-> USER MESSAGE ROUTER (runs BEFORE the generic message handler)
# --------------------------------------------------------------------
async def _relay(target, e, header):
  """Send header + the content of message e (text or media) to target."""
  body = html.escape(e.raw_text or "")
  caption = custom_emoji_text(header + (("\n\n" + body) if body else ""))
  if e.media and not getattr(e, 'web_preview', None):
    return await bot.send_file(target, e.media, caption=caption, parse_mode='html')
  return await bot.send_message(target, caption, parse_mode='html')


@bot.on(events.NewMessage(incoming=True))
async def _shop_chat_router(e):
  try:
    if not e.is_private:
      return
    uid = e.sender_id
    if not uid:
      return
    text = (e.raw_text or "").strip()
    low = text.lower()
    if low.startswith('/') and low.split()[0].split('@')[0] not in ('/done', '/endchat'):
      return

    # ---------- admin ----------
    if is_admin(uid):
      st = admin_reply_state.get(uid)
      if low in ('/done', '/endchat'):
        if st:
          admin_reply_state.pop(uid, None)
          await e.respond(custom_emoji_text(f"{P_YES} <b>Reply mode closed.</b>"))
          raise events.StopPropagation
        return
      oid, mode = None, None
      if e.is_reply:
        mapped = _ORDER_MSG_MAP.get((uid, e.reply_to_msg_id))
        if mapped:
          oid, mode = mapped
      if oid is None and st:
        oid, mode = st['oid'], st['mode']
      if oid is None:
        return
      row = cur.execute("SELECT user_id, product_name, status FROM shop_orders WHERE id=?", (oid,)).fetchone()
      if not row:
        return
      buyer, name, status = row
      ubtn = [[Button.inline("Reply to Admin", f"shp_uchat|{oid}", style="primary")],
              [Button.inline("Close Chat", f"shp_uend|{oid}", style="danger")],
              [Button.inline("My Orders", "cb_orders", style="success")]]
      if mode == 'deliver':
        header = (f"{P_YES} {P_PARTY} <b>Order #{oid} Delivered</b>\n"
                  f"{P_DOC} {html.escape(str(name))}")
      else:
        header = f"{P_ASST} <b>Admin</b> \u2014 Order <code>#{oid}</code>"
      body = html.escape(e.raw_text or "")
      cap = custom_emoji_text(header + (("\n\n" + body) if body else ""))
      if e.media:
        await bot.send_file(int(buyer), e.media, caption=cap, buttons=ubtn, parse_mode='html')
      else:
        await bot.send_message(int(buyer), cap, buttons=ubtn, parse_mode='html')
      if mode == 'deliver' and status in ('pending', 'delivering'):
        cur.execute("UPDATE shop_orders SET status='delivered', delivered_at=?, delivery=? WHERE id=?",
                    (_now_str(), (e.raw_text or "[file]")[:1000], oid))
        cur.execute("UPDATE global_orders SET status='COMPLETED' WHERE service='shop' AND local_ref=?", (str(oid),))
        db.commit()
        try:
          _shop_price = cur.execute("SELECT price FROM shop_orders WHERE id=?", (oid,)).fetchone()[0]
          _shop_gid = _global_order_register('shop', oid, int(buyer), _shop_price, 'COMPLETED')
          await log_digital_sale(int(buyer), name, _shop_price, global_order_id=_shop_gid)
        except Exception:
          pass
      await e.respond(custom_emoji_text(f"{P_YES} Sent to user (order #{oid})."))
      raise events.StopPropagation

    # ---------- user ----------
    st = user_chat_state.get(uid)
    if not st:
      return
    if low in ('/endchat', '/done'):
      user_chat_state.pop(uid, None)
      await e.respond(custom_emoji_text(f"{P_YES} <b>Chat ended.</b>"))
      raise events.StopPropagation
    oid = st['oid']
    row = cur.execute("SELECT product_name FROM shop_orders WHERE id=?", (oid,)).fetchone()
    label = await _user_label(uid)
    header = (f"{P_ASST} <b>User message</b> \u2014 Order <code>#{oid}</code>"
              f" ({html.escape(str(row[0]) if row else '-')})\n"
              f"{P_ACC} <code>{uid}</code> ({html.escape(label)})")
    abtn = [[Button.inline("Reply", f"shp_chat|{oid}")]]
    sent_any = False
    for admin_id in get_all_admin_ids():
      try:
        body = html.escape(e.raw_text or "")
        cap = custom_emoji_text(header + (("\n\n" + body) if body else ""))
        if e.media:
          m = await bot.send_file(int(admin_id), e.media, caption=cap, buttons=abtn, parse_mode='html')
        else:
          m = await bot.send_message(int(admin_id), cap, buttons=abtn, parse_mode='html')
        _ORDER_MSG_MAP[(int(admin_id), m.id)] = (oid, 'chat')
        sent_any = True
      except Exception as ex:
        logger.error(f"chat relay to admin {admin_id} failed: {ex}")
    await e.respond(custom_emoji_text(
      f"{P_YES} Sent to admin." if sent_any else f"{P_WARN} Could not reach the admin right now."),
      buttons=[[Button.inline("End Chat", "shp_uend|0")]])
    raise events.StopPropagation
  except events.StopPropagation:
    raise
  except Exception as ex:
    logger.error(f"shop chat router error: {ex}", exc_info=True)


# --------------------------------------------------------------------
# MY ORDERS  (category buttons -> list -> details with action buttons)
# --------------------------------------------------------------------
_MO_PAGE = 6


def _mo_tg_items(uid):
  items = []
  try:
    for oid, country, yr, price, phone, d, term in cur.execute(
        "SELECT id, country, year, price, phone, date, COALESCE(terminated,0) FROM orders WHERE user_id=?",
        (uid,)).fetchall():
      items.append({"ts": _order_ts(d), "cb": f"mo_tg|m|{oid}",
                    "label": f"+{phone} \u00b7 {country}"})
  except Exception as ex:
    logger.warning(f"mo tg manual: {ex}")
  try:
    for rid, oid, cname, number, price, d in cur.execute(
        "SELECT rowid, order_id, country_name, number, price, created_date FROM s2_orders "
        "WHERE user_id=? AND charged=1", (uid,)).fetchall():
      items.append({"ts": _order_ts(d), "cb": f"mo_tg|s|{rid}",
                    "label": f"{number or 'Pending'} \u00b7 {clean_country_name(cname)}"})
  except Exception as ex:
    logger.warning(f"mo tg s1: {ex}")
  items.sort(key=lambda x: x["ts"], reverse=True)
  return items


def _mo_wa_items(uid):
  items = []
  try:
    for o in _s2wa_user_orders(uid, 200):
      items.append({"ts": _order_ts(o.get("created_at")), "cb": f"mo_wa|{o['id']}",
                    "label": f"{o.get('phone') or '-'} \u00b7 {o.get('country_name') or ''}"})
  except Exception as ex:
    logger.warning(f"mo wa: {ex}")
  return items


def _mo_smm_items(uid):
  items = []
  try:
    for boid, sname, d in cur.execute(
        "SELECT o.bot_order_id, COALESCE(s.name,'Service '||o.service_id), o.date FROM smm_orders o "
        "LEFT JOIN smm_services s ON s.service_id=o.service_id WHERE o.user_id=? "
        "ORDER BY o.bot_order_id DESC", (uid,)).fetchall():
      items.append({"ts": _order_ts(d), "cb": f"mo_smm|{boid}", "label": f"#{boid} \u00b7 {sname}"})
  except Exception as ex:
    logger.warning(f"mo smm: {ex}")
  return items


def _mo_shop_items(uid):
  items = []
  try:
    for oid, name, status, d in cur.execute(
        "SELECT id, product_name, status, created FROM shop_orders WHERE user_id=? ORDER BY id DESC",
        (uid,)).fetchall():
      items.append({"ts": _order_ts(d), "cb": f"mo_shop|{oid}", "label": f"#{oid} \u00b7 {name} \u00b7 {status}"})
  except Exception as ex:
    logger.warning(f"mo shop: {ex}")
  return items


_MO_CATS = {
  "tg": ("Telegram Accounts", _mo_tg_items),
  "wa": ("WhatsApp Services", _mo_wa_items),
  "smm": ("SMM Services", _mo_smm_items),
  "shop": ("Shop Orders", _mo_shop_items),
}


async def orders_history_handler(event, is_callback=False, page=1):
  """My Orders main screen: one button per category."""
  uid = event.sender_id
  counts = {k: len(fn(uid)) for k, (_, fn) in _MO_CATS.items()}
  total = sum(counts.values())
  if total == 0:
    msg = f"{P_DOC} <b>{_bold('My Orders')}</b>\n{_sep()}\n\n{P_WARN} <b>You don't have any orders yet.</b>"
    btns = [[Button.inline("Store", "cb_store")], [Button.inline("Back to Main", "back_main")]]
  else:
    msg = (f"{P_DOC} {P_ROCKET} <b>{_bold('My Orders')}</b>\n{_sep()}\n"
           f"{P_PKG} <b>Total orders:</b> {total}\n\n"
           f"Choose a category:")
    btns = [[Button.inline(f"Telegram Accounts ({counts['tg']})", "mo_list|tg|1")],
            [Button.inline(f"WhatsApp Services ({counts['wa']})", "mo_list|wa|1")],
            [Button.inline(f"SMM Services ({counts['smm']})", "mo_list|smm|1")],
            [Button.inline(f"Shop Orders ({counts['shop']})", "mo_list|shop|1")],
            [Button.inline("Back to Main", "back_main")]]
  if is_callback:
    try:
      await e_edit_or_send(event, custom_emoji_text(msg), btns)
    except MessageNotModifiedError:
      pass
  else:
    await bot.send_message(event.chat_id, custom_emoji_text(msg), buttons=btns, parse_mode='html')


async def _mo_list(e, cat, page):
  uid = e.sender_id
  title, fn = _MO_CATS[cat]
  items = fn(uid)
  if not items:
    msg = f"{P_DOC} <b>{title}</b>\n{_sep()}\n\n{P_WARN} No orders in this category yet."
    return await e_edit_or_send(e, custom_emoji_text(msg), [[Button.inline("Back", "cb_orders")]])
  pages = max(1, (len(items) + _MO_PAGE - 1) // _MO_PAGE)
  page = max(1, min(int(page), pages))
  chunk = items[(page - 1) * _MO_PAGE: page * _MO_PAGE]
  msg = (f"{P_DOC} <b>{title}</b>\n{_sep()}\n"
         f"{P_PKG} <b>Total:</b> {len(items)} \u00b7 Page {page}/{pages}\n\n"
         f"Tap an order to see its details:")
  btns = [[Button.inline(it["label"][:48], it["cb"])] for it in chunk]
  nav = []
  if page > 1:
    nav.append(Button.inline("Prev", f"mo_list|{cat}|{page-1}"))
  if page < pages:
    nav.append(Button.inline("Next", f"mo_list|{cat}|{page+1}"))
  if nav:
    btns.append(nav)
  btns.append([Button.inline("Back", "cb_orders")])
  await e_edit_or_send(e, custom_emoji_text(msg), btns)


def _mo_get_manual(uid, oid):
  r = cur.execute(
    "SELECT id, country, year, price, phone, otp, date, COALESCE(session_file,''), "
    "COALESCE(twofa_pass,''), COALESCE(terminated,0), user_id FROM orders WHERE id=?",
    (oid,)).fetchone()
  if not r or int(r[10]) != int(uid):
    return None
  keys = ("id", "country", "year", "price", "phone", "otp", "date", "sess", "twofa", "term", "uid")
  return dict(zip(keys, r))


async def _mo_tg_detail(e, kind, rid):
  uid = e.sender_id
  if kind == "m":
    o = _mo_get_manual(uid, int(rid))
    if not o:
      return await safe_callback_answer(e, "Order not found.", alert=True)
    _gid = _global_order_id_for('telegram', o['id'])
    msg = _manual_purchase_text(
      _gid, o['phone'], o['country'], o['twofa'], otp_code=o['otp'],
      extra=(f"{P_MONEY} <b>Paid:</b> \u20b9{o['price']}\n"
             f"{P_CAL} <b>Year:</b> {o['year'] or '-'}\n"
             f"{P_KEY} <b>Bot session:</b> {'Terminated' if o['term'] else 'Active'}\n"
             f"{P_TIME} <b>Date:</b> {html.escape(str(o['date']))}\n"))
    btns = [[Button.inline("Session File", f"mo_sf|m|{o['id']}")],
            [Button.inline("Check OTP", f"mo_otp|m|{o['id']}")],
            [Button.inline("Terminate Bot Session", f"mo_term|m|{o['id']}")],
            [Button.inline("Back", "mo_list|tg|1")]]
    return await e_edit_or_send(e, custom_emoji_text(msg), btns)

  # Server 1 (API) order
  r = cur.execute(
    "SELECT order_id, user_id, country_name, country_code, number, price, status, code, password, "
    "created_date, COALESCE(secured,0) FROM s2_orders WHERE rowid=?", (int(rid),)).fetchone()
  if not r or int(r[1]) != int(uid):
    return await safe_callback_answer(e, "Order not found.", alert=True)
  order_id = r[0]
  msg, btns = _s1_purchase_card(order_id, back_cb="mo_list|tg|1", rid=rid, show_2fa=True)
  if not msg:
    return await safe_callback_answer(e, "Order not found.", alert=True)
  msg += f"\n{P_TIME} <b>Date:</b> {html.escape(str(r[9]))}"
  await e_edit_or_send(e, custom_emoji_text(msg), btns)


async def _manual_client_for(o):
  """(client, must_disconnect). Reuse the live client when the bot is still holding it."""
  live = active_orders.get(o["phone"])
  if live and live.get("client"):
    return live["client"], False
  base = o["sess"][:-8] if o["sess"].endswith(".session") else o["sess"]
  if not base or not os.path.exists(base + ".session"):
    return None, False
  client = TelegramClient(base, API_ID, API_HASH)
  await asyncio.wait_for(client.connect(), timeout=30)
  return client, True


async def _mo_manual_otp(e, rid):
  o = _mo_get_manual(e.sender_id, int(rid))
  if not o:
    return await safe_callback_answer(e, "Order not found.", alert=True)
  if o["term"]:
    return await safe_callback_answer(
      e, "Bot session is terminated, so OTP can't be read anymore. Login with the number + 2FA.", alert=True)
  await safe_callback_answer(e, "Fetching OTP...")
  client, close = None, False
  try:
    client, close = await _manual_client_for(o)
    if client is None:
      return await safe_callback_answer(e, "Session file not found.", alert=True)
    if not await client.is_user_authorized():
      return await safe_callback_answer(e, "Session is no longer authorized.", alert=True)
    code, when = None, None
    for m in await client.get_messages(777000, limit=8):
      if m.message and "Login detected" not in m.message:
        mt = re.search(r'\b\d{5}\b', m.message)
        if mt:
          code, when = mt.group(), m.date
          break
    pw = o["twofa"] if o["twofa"] and o["twofa"] != "None" else "Disabled (no password)"
    if code:
      msg = (f"{P_YES} {P_FIRE} <b>Latest OTP</b>\n{_sep()}\n\n"
             f"{P_PHONE} <b>Number:</b> <code>+{html.escape(str(o['phone']))}</code>\n"
             f"{P_OTP} <b>OTP:</b> <code>{_otp_gap(code)}</code>\n"
             f"{P_TIME} <b>Received:</b> {when.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
             f"{P_2FA} <b>2FA:</b> <code>{html.escape(pw)}</code>")
    else:
      msg = (f"{P_WARN} <b>No OTP yet</b>\n\nRequest the login code in Telegram, then tap Check OTP again.")
    await e_edit_or_send(e, custom_emoji_text(msg), [
      [Button.inline("Check OTP Again", f"mo_otp|m|{o['id']}")],
      [Button.inline("Back", f"mo_tg|m|{o['id']}")]])
  except Exception as ex:
    logger.warning(f"manual otp failed: {ex}")
    await safe_callback_answer(e, "Could not fetch OTP. Try again.", alert=True)
  finally:
    if close and client is not None:
      try:
        await client.disconnect()
      except Exception:
        pass


async def _mo_manual_session(e, rid):
  o = _mo_get_manual(e.sender_id, int(rid))
  if not o:
    return await safe_callback_answer(e, "Order not found.", alert=True)
  if o["term"]:
    return await safe_callback_answer(e, "Bot session already terminated. This session file is no longer valid.", alert=True)
  await safe_callback_answer(e, "Sending session file...")
  ok = await _send_manual_session_file(e.sender_id, o["phone"], o["sess"], o["twofa"], o["country"])
  if not ok:
    await e.respond(custom_emoji_text(f"{P_NO} Session file not found. Please contact support."))


async def _mo_manual_term_ask(e, rid):
  o = _mo_get_manual(e.sender_id, int(rid))
  if not o:
    return await safe_callback_answer(e, "Order not found.", alert=True)
  if o["term"]:
    return await safe_callback_answer(e, "Already terminated.", alert=True)
  msg = (f"{P_WARN} <b>Terminate bot session?</b>\n\n"
         f"{P_PHONE} <code>+{html.escape(str(o['phone']))}</code>\n\n"
         f"The bot will log out its own session. The session file and OTP check will stop working. "
         f"Only do this after you have logged in to the account yourself.")
  await e_edit_or_send(e, custom_emoji_text(msg), [
    [Button.inline("Yes, Terminate", f"mo_termy|m|{o['id']}")],
    [Button.inline("No, Cancel", f"mo_tg|m|{o['id']}")]])


async def _mo_manual_term(e, rid):
  o = _mo_get_manual(e.sender_id, int(rid))
  if not o:
    return await safe_callback_answer(e, "Order not found.", alert=True)
  await safe_callback_answer(e, "Terminating...")
  client, close = None, False
  try:
    client, close = await _manual_client_for(o)
    if client is not None:
      try:
        await client.log_out()
      except Exception as ex:
        logger.warning(f"manual log_out: {ex}")
  except Exception as ex:
    logger.warning(f"manual terminate client: {ex}")
  finally:
    live = active_orders.pop(o["phone"], None)
    for c in {id(x): x for x in (client, (live or {}).get("client")) if x is not None}.values():
      try:
        await c.disconnect()
      except Exception:
        pass
  if o["sess"]:
    delete_session_files(o["sess"])
  cur.execute("UPDATE orders SET terminated=1 WHERE id=?", (o["id"],))
  db.commit()
  await e_edit_or_send(e, custom_emoji_text(
    f"{P_YES} <b>Bot session terminated.</b>\n\nThe account is now only on your device."),
    [[Button.inline("Back", f"mo_tg|m|{o['id']}")]])


async def _mo_wa_detail(e, rid):
  uid = e.sender_id
  r = cur.execute("SELECT * FROM s2_wa_orders WHERE id=? AND uid=?", (int(rid), uid)).fetchone()
  if not r:
    return await safe_callback_answer(e, "Order not found.", alert=True)
  o = dict(zip([d[0] for d in cur.description], r))
  st = {"DONE": "Complete", "CANCELLED": "Cancelled", "WAIT_CODE": "Waiting for code",
        "WAIT_RETRY": "Waiting for retry"}.get(o.get("status"), str(o.get("status") or "-"))
  _wgid = _global_order_id_for('whatsapp', o.get('activation_id'))
  msg = _wa_purchase_text({"name": o.get('country_name') or ''}, _wgid, o.get('phone') or '-',
                          o.get('price_inr') or 0, o['id'], code=o.get('code'))
  msg += (f"\n{P_PKG} <b>Status:</b> {html.escape(st)}\n"
          f"{P_TIME} <b>Created:</b> {html.escape(str(o.get('created_at') or '-')[:19])}")
  btns = []
  if o.get("status") in ("WAIT_CODE", "WAIT_RETRY"):
    btns.append([Button.inline("Check Code", f"s2wa_code:{o['activation_id']}")])
  btns.append([Button.inline("Back", "mo_list|wa|1")])
  await e_edit_or_send(e, custom_emoji_text(msg), btns)


async def _mo_smm_detail(e, boid):
  uid = e.sender_id
  r = cur.execute(
    "SELECT o.bot_order_id, COALESCE(s.name,'Service '||o.service_id), o.link, o.quantity, "
    "o.total_price, o.smm_order_id, o.status, o.date FROM smm_orders o "
    "LEFT JOIN smm_services s ON s.service_id=o.service_id WHERE o.bot_order_id=? AND o.user_id=?",
    (int(boid), uid)).fetchone()
  if not r:
    return await safe_callback_answer(e, "Order not found.", alert=True)
  bid, sname, link, qty, price, panel_id, status, d = r
  msg = (f"{P_LIGHTNING} <b>SMM Order #{bid}</b>\n{_sep()}\n\n"
         f"{P_GEAR} <b>Service:</b> {html.escape(str(sname))}\n"
         f"{P_LINK} <b>Link:</b> {html.escape(clean_html_url(link or '-'))}\n"
         f"{P_PKG} <b>Quantity:</b> {qty}\n"
         f"{P_MONEY} <b>Paid:</b> \u20b9{float(price or 0):.2f}\n"
         f"{P_ID} <b>Panel Order ID:</b> <code>{html.escape(str(panel_id or '-'))}</code>\n"
         f"{P_PKG} <b>Status:</b> {html.escape(str(status))}\n"
         f"{P_TIME} <b>Date:</b> {html.escape(str(d))}")
  btns = [[Button.inline("Refill", f"mo_refill|{bid}")],
          [Button.inline("Back", "mo_list|smm|1")]]
  await e_edit_or_send(e, custom_emoji_text(msg), btns)


async def _mo_refill(e, boid):
  uid = e.sender_id
  r = cur.execute("SELECT smm_order_id FROM smm_orders WHERE bot_order_id=? AND user_id=?",
                  (int(boid), uid)).fetchone()
  if not r:
    return await safe_callback_answer(e, "Order not found.", alert=True)
  panel_id = r[0]
  if not panel_id or panel_id == 'SUCCESS':
    return await safe_callback_answer(e, "Refill is not available for this order.", alert=True)
  refill_state[uid] = {'step': 'wait_screenshot', 'bot_order_id': int(boid), 'smm_order_id': panel_id}
  await safe_callback_answer(e)
  await e.respond(custom_emoji_text(
    f"{P_DOC} <b>Refill for Order #{boid}</b>\n\n"
    f"Please send a <b>screenshot</b> showing the joined / member statistics.\n"
    f"<i>Send the screenshot now (or /cancel):</i>"))


async def _mo_shop_detail(e, oid):
  uid = e.sender_id
  r = cur.execute(
    "SELECT id, product_name, price, status, delivery, created, delivered_at FROM shop_orders "
    "WHERE id=? AND user_id=?", (int(oid), uid)).fetchone()
  if not r:
    return await safe_callback_answer(e, "Order not found.", alert=True)
  oid, name, price, status, delivery, created, dat = r
  msg = (f"{P_STORE} <b>Shop Order #{oid}</b>\n{_sep()}\n\n"
         f"{P_DOC} <b>Product:</b> {html.escape(str(name))}\n"
         f"{P_MONEY} <b>Paid:</b> \u20b9{price}\n"
         f"{P_PKG} <b>Status:</b> {html.escape(str(status).title())}\n"
         f"{P_TIME} <b>Ordered:</b> {html.escape(str(created))}\n"
         + (f"{P_TIME} <b>Delivered:</b> {html.escape(str(dat))}\n" if dat else "")
         + (f"\n{P_DOC} <b>Delivery:</b>\n{html.escape(str(delivery))}" if delivery else ""))
  btns = [[Button.inline("Chat with Admin", f"shp_uchat|{oid}")],
          [Button.inline("Back", "mo_list|shop|1")]]
  await e_edit_or_send(e, custom_emoji_text(msg), btns)


async def _mo_s1_session(e, rid):
  r = cur.execute("SELECT order_id, user_id FROM s2_orders WHERE rowid=?", (int(rid),)).fetchone()
  if not r or int(r[1]) != int(e.sender_id):
    return await safe_callback_answer(e, "Order not found.", alert=True)
  await safe_callback_answer(e, "Sending session file...")
  ok, note = await _send_s1_session_file(e.sender_id, r[0])
  if not ok:
    await e.respond(custom_emoji_text(f"{P_NO} <b>{html.escape(str(note))}</b>"))


async def _extra_callbacks(e, data):
  parts = data.split("|")
  head = parts[0]
  if head.startswith("shp_"):
    return await _shop_callbacks(e, data)
  if head == "mo_list":
    return await _mo_list(e, parts[1], parts[2] if len(parts) > 2 else 1)
  if head == "mo_tg":
    return await _mo_tg_detail(e, parts[1], parts[2])
  if head == "mo_wa":
    return await _mo_wa_detail(e, parts[1])
  if head == "mo_smm":
    return await _mo_smm_detail(e, parts[1])
  if head == "mo_shop":
    return await _mo_shop_detail(e, parts[1])
  if head == "mo_refill":
    return await _mo_refill(e, parts[1])
  if head == "mo_sf":
    return await (_mo_manual_session(e, parts[2]) if parts[1] == "m" else _mo_s1_session(e, parts[2]))
  if head == "mo_otp":
    return await _mo_manual_otp(e, parts[2])
  if head == "mo_term":
    return await _mo_manual_term_ask(e, parts[2])
  if head == "mo_termy":
    return await _mo_manual_term(e, parts[2])
  await safe_callback_answer(e)


# --------------------------------------------------------------------
# CALLBACK PRE-HOOK: own callbacks + "Loading..." message
# --------------------------------------------------------------------
_LOADING_PREFIXES = (
  "srv1_countries", "srv1_cat|", "srv1_pg|", "srv1_ref", "srv1_sort|", "srv1_c|", "srv1_l|",
  "srv1_i|", "srv1_ip|", "srv1_ipr|", "srv1_accounts", "srv1_orders", "srv1_ord|",
  "s_country|", "srv_pg|", "srv|manual", "p_year|", "cb_smm_services", "smm_cat|", "smm_srv|",
  "s2wa_countries", "s2wa_c:", "s2wa_orders",
  "s3_svcs:", "s3_svc:", "s3_cs:", "s3_c:", "s3_orders",
)


@bot.on(events.CallbackQuery)
async def _extra_callback_prehook(e):
  try:
    raw = e.data.decode("utf-8", errors="replace") if isinstance(e.data, bytes) else str(e.data or "")
    uid = e.sender_id
    # Any navigation other than the country list itself leaves the list.
    if not (raw.startswith("srv1_pg|") or raw in ("srv1_countries", "srv1_ref")):
      _S1_ON_COUNTRY_LIST.pop(uid, None)
    if raw.startswith(("mo_", "shp_")):
      if not is_bot_online() and not is_admin(uid):
        await safe_callback_answer(e, "Bot is currently unavailable.", alert=True)
        raise events.StopPropagation
      ensure_user(uid)
      if is_user_banned(uid):
        await safe_callback_answer(e, "BANNED", alert=True)
        raise events.StopPropagation
      try:
        await _extra_callbacks(e, raw)
      except MessageNotModifiedError:
        pass
      except events.StopPropagation:
        raise
      except Exception as ex:
        logger.error(f"extra callback {raw!r} failed: {ex}", exc_info=True)
        await safe_callback_answer(e, "Something went wrong. Please try again.", alert=True)
      raise events.StopPropagation
    if raw.startswith(_LOADING_PREFIXES):
      if not is_bot_online() and not is_admin(uid):
        return
      try:
        await e.edit(_LOADING_TEXT, parse_mode='html')
        _LOADING_PENDING[(e.chat_id, e.message_id)] = time.time()
      except MessageNotModifiedError:
        pass
      except Exception as ex:
        logger.debug(f"loading edit skipped: {ex}")
  except events.StopPropagation:
    raise
  except Exception as ex:
    logger.error(f"callback prehook error: {ex}", exc_info=True)


def _proof_media(e):
  """Payment proof: a normal photo OR an image sent as a file (uncompressed)."""
  try:
    if getattr(e, 'photo', None):
      return e.photo
    doc = getattr(e, 'document', None)
    if doc and str(getattr(doc, 'mime_type', '') or '').lower().startswith('image/'):
      return doc
  except Exception:
    pass
  return None


async def _submit_deposit_screenshot(e, uid):
  """Deposit screenshot (UPI Manual / USDT) -> every admin, with Accept / Reject buttons."""
  media = _proof_media(e)
  info = deposit_input.pop(uid)
  amt = info['amount']
  method = info.get('method', 'UPI Manual')
  cur.execute("INSERT INTO deposits (user_id,amount,method_name,status,utr) VALUES (?,?,?,?,?)", (uid, amt, method, 'pending', ''))
  db.commit()
  dep_id = cur.lastrowid
  cap = (f"{P_BELL} <b>NEW {html.escape(method.upper())} DEPOSIT REVIEW</b>\n\n"
      f"{P_ACC} User ID: <code>{uid}</code>\n"
      f"{P_MONEY} Amount: <b>\u20b9{amt}</b>\n"
      f"{P_CARD} Method: <b>{html.escape(method)}</b>\n"
      + (f"{P_USDT} USDT Expected: <b>{info['usdt_amount']:.2f} USDT</b> ({html.escape(str(info.get('network', '')))})\n"
         if info.get('usdt_amount') else "") +
      f"{P_ID} Ref ID: <code>{dep_id}</code>")
  btns = [[Button.inline(f"Accept \u20b9{amt}", f"dep_acc|{dep_id}|{uid}|{method}|exact|{amt}"), Button.inline("Reject", f"dep_rej|{dep_id}|{uid}")]]
  sent_admins = await send_admins_file(media, cap, buttons=btns)
  if sent_admins:
    await e.respond(custom_emoji_text(f"{P_YES} <b>Screenshot sent to all admins.</b>\nYour payment is pending verification."))
  else:
    await e.respond(custom_emoji_text(f"{P_WARN} Screenshot received, but no admin could be reached right now. Please contact support."))


@bot.on(events.NewMessage())
async def handle_all_messages(e):
  try:
    uid = e.sender_id
    if not uid: return
    if getattr(e, 'text', None) and e.text and e.text.startswith('/'): return
    if not is_bot_online() and not is_admin(uid):
      return await e.respond(custom_emoji_text(bot_block_text()))
    
    ensure_user(uid)
    if is_user_banned(uid): return

    if uid in redeem_state:
      state=redeem_state.get(uid,{})
      text=(e.text or '').strip()
      if text.lower() == '/cancel':
        redeem_state.pop(uid,None); return await e.respond("Redeem cancelled.")
      if state.get('step') == 'wait_code' and text:
        redeem_state.pop(uid,None)
        code=text.upper()
        row=cur.execute("SELECT amount,max_users,used_count,active FROM redeem_codes WHERE code=?",(code,)).fetchone()
        if not row: return await e.respond("Invalid redeem code.")
        amount,mx,used,active=row
        if not active or used>=mx: return await e.respond("This code is no longer available.")
        if cur.execute("SELECT 1 FROM redeem_claims WHERE code=? AND user_id=?",(code,uid)).fetchone(): return await e.respond("You have already redeemed this code.")
        async with get_user_lock(uid):
          cur.execute("INSERT INTO redeem_claims(code,user_id) VALUES(?,?)",(code,uid))
          cur.execute("UPDATE redeem_codes SET used_count=used_count+1 WHERE code=? AND active=1 AND used_count<?",(code,mx))
          if cur.rowcount != 1:
            cur.execute("DELETE FROM redeem_claims WHERE code=? AND user_id=?",(code,uid)); db.commit(); return await e.respond("This code just reached its limit.")
          update_balance(uid,amount); db.commit()
          _redeem_after_claim(code,uid,amount)
        return await e.respond(custom_emoji_text(f"{P_YES} <b>Redeem Successful!</b>\nAmount Added: ₹{amount}"))

    if uid in refill_state:
      state = refill_state[uid]
      step = state['step']
      text = e.text.strip() if e.text else ""

      if text.lower() == '/cancel':
        refill_state.pop(uid, None)
        return await e.respond(custom_emoji_text(f"{P_NO} Refill process cancelled."))

      if step == 'wait_order_id':
        if not text.isdigit():
          return await e.respond(custom_emoji_text(f"{P_NO} Please enter a valid numeric SMM Order No."))
        bot_order_id = int(text)
        order_row = cur.execute("SELECT user_id, smm_order_id FROM smm_orders WHERE bot_order_id=?", (bot_order_id,)).fetchone()
        if not order_row:
          return await e.respond(custom_emoji_text(f"{P_NO} Order ID <code>{bot_order_id}</code> not found in database."))
        owner_uid, smm_order_id = order_row
        if owner_uid != uid and not is_admin(uid):
          return await e.respond(custom_emoji_text(f"{P_NO} This order does not belong to you."))
        if not smm_order_id or smm_order_id == 'SUCCESS':
          return await e.respond(custom_emoji_text(f"{P_NO} Valid SMM Panel Order ID not available for this order."))
        
        state['bot_order_id'] = bot_order_id
        state['smm_order_id'] = smm_order_id
        state['step'] = 'wait_screenshot'
        refill_state[uid] = state
        
        await e.respond(
          custom_emoji_text(f"{P_DOC} <b>Order ID Verified: #{bot_order_id}</b>\n\n"
          f"Please send a <b>screenshot</b> showing the invite link joined statistics (showing member list and joined count, exactly like the reference example).\n\n"
          f"<i>Send the screenshot now:</i>")
        )
        return
      elif step == 'wait_screenshot':
        if not e.photo:
          return await e.respond(custom_emoji_text(f"{P_NO} Please send a valid image screenshot."))
        
        bot_order_id = state['bot_order_id']
        smm_order_id = state['smm_order_id']
        refill_state.pop(uid, None)
        
        await e.respond(custom_emoji_text(f"{P_WAIT} <b>Processing refill request and sending to SMM panel... Please wait.</b>"))
        
        api_url, api_key = get_smm_api_config()
        refill_res = None
        if api_url and api_key:
          refill_res = refill_smm_order_api(api_url, api_key, smm_order_id)
        
        # Forward refill request screenshot directly to ADMIN_ID (Admin DM)
        try:
          log_msg = (
            f"{P_BELL} <b>NEW REFILL REQUEST WITH SCREENSHOT</b>\n\n"
            f"{P_ACC} User ID: <code>{uid}</code>\n"
            f"{P_ID} SMM Order No.: <code>{bot_order_id}</code>\n"
            f"{P_GEAR} Panel Order ID: <code>{smm_order_id}</code>\n"
            f"{P_TIME} Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
          )
          await bot.send_file(ADMIN_ID, e.photo, caption=custom_emoji_text(log_msg))
        except Exception as ex:
          logger.error(f"Failed to forward refill screenshot to admin DM: {ex}")
        
        if refill_res and isinstance(refill_res, dict) and ('refill' in refill_res or refill_res.get('status') == 'success' or 'refill_id' in refill_res):
          refill_id = refill_res.get('refill', refill_res.get('refill_id', 'SUCCESS'))
          await e.respond(custom_emoji_text(f"{P_YES} <b>Refill Request Submitted Successfully!</b> {P_PARTY}\n\n- SMM Order No.: <code>{bot_order_id}</code>\n- Panel Refill ID: <code>{refill_id}</code>\n\n<i>Your screenshot has been verified and submitted.</i>"))
        else:
          err = refill_res.get('error', 'Unknown refill error') if isinstance(refill_res, dict) else 'Refill API connection failed'
          await e.respond(custom_emoji_text(f"{P_YES} <b>Refill Screenshot Received & Forwarded to Admin!</b>\n\nNote: Panel response: {html.escape(str(err))}. Your request has been logged for review."))
        
        await send_main_menu(e, uid)
        return

    if uid in smm_order_state:
      state = smm_order_state[uid]
      step = state['step']
      text = e.text.strip()

      if step == 'wait_link':
        # e.text is HTML-formatted (bot.parse_mode='html'), which turned a pasted
        # URL into '<a href="...">...</a>'. Use the plain text and extract the URL.
        state['link'] = clean_html_url((e.raw_text or text).strip())
        state['step'] = 'wait_qty'
        smm_order_state[uid] = state
        await e.respond(custom_emoji_text(f"{P_QTY} <b>Enter Quantity:</b>\n(Min: {state['min']} | Max: {state['max']}):"), buttons=[[Button.inline("Cancel", "smm_cancel")]])
        return
      elif step == 'wait_qty':
        try:
          qty = int(re.sub(r'[^\d]', '', text))
          if qty < state['min'] or qty > state['max']:
            return await e.respond(custom_emoji_text(f"{P_NO} Quantity must be between {state['min']} and {state['max']}."))
          
          total_price = (qty / 1000.0) * state['rate']
          state['qty'] = qty
          state['total_price'] = total_price
          
          bal_row = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
          bal = bal_row[0] if bal_row else 0
          if bal < total_price:
            smm_order_state.pop(uid, None)
            err_msg = (
              f"{P_NO} <b>Insufficient Funds!</b>\n\n"
              f"<b>Order Cost:</b> ₹{total_price:.4f}\n"
              f"<b>Your Balance:</b> ₹{bal:.4f}\n\n"
              f"Please use /addfunds to top up your account."
            )
            return await e.respond(custom_emoji_text(err_msg))

          api_url, api_key = get_smm_api_config()
          if not api_url or not api_key:
            smm_order_state.pop(uid, None)
            return await e.respond(custom_emoji_text(f"{P_NO} SMM API is not configured by admin."))

          await e.respond(custom_emoji_text(f"{P_WAIT} <b>Placing order to SMM Panel... Please wait.</b>"))
          api_res = place_smm_order_api(api_url, api_key, state['service_id'], state['link'], qty)
          
          if api_res and isinstance(api_res, dict) and ('order' in api_res or api_res.get('status') == 'success'):
            smm_order_id = str(api_res.get('order', api_res.get('order_id', 'SUCCESS')))
            async with get_user_lock(uid):
              cur.execute("UPDATE users SET balance = balance - ? WHERE user_id=? AND balance >= ?", (total_price, uid, total_price))
              cur.execute("INSERT INTO smm_orders (user_id, service_id, link, quantity, total_price, smm_order_id, status) VALUES (?,?,?,?,?,?,?)",
                    (uid, state['service_id'], state['link'], qty, total_price, smm_order_id, 'Completed'))
              db.commit()
              bot_order_id = cur.lastrowid
            smm_global_id = _global_order_register('smm', bot_order_id, uid, total_price, 'PROCESSING')

            await log_smm_sale(
              uid, state['name'], bot_order_id, smm_order_id,
              state['link'], qty, total_price, global_order_id=smm_global_id
            )
            smm_order_state.pop(uid, None)
            await e.respond(custom_emoji_text(f"{P_YES} <b>SMM Order Placed Successfully!</b> {P_PARTY}\n\n"
                    f"{P_GEAR} Service: {html.escape(state['name'])}\n"
                    f"{P_ID} Bot Order ID: <code>{smm_global_id}</code>\n"
                    f"{P_ID} SMM Order No.: <code>{bot_order_id}</code>\n"
                    f"{P_GEAR} Panel Order ID: <code>{smm_order_id}</code>\n"
                    f"{P_LINK} Link: {html.escape(state['link'])}\n"
                    f"{P_PKG} Quantity: {qty}\n"
                    f"{P_MONEY} Total Cost: ₹{total_price:.4f}\n\n"
                    f"<i>(Note: For refill use /refill {bot_order_id} or click Refill button)</i>"))
            await send_main_menu(e, uid)
          else:
            err_msg = api_res.get('error', 'Unknown error from SMM API') if isinstance(api_res, dict) else 'API connection failed'
            smm_order_state.pop(uid, None)
            await e.respond(custom_emoji_text(f"{P_NO} <b>SMM Order Failed:</b> {html.escape(str(err_msg))}"))
          return
        except ValueError:
          return await e.respond(custom_emoji_text(f"{P_NO} Please enter a valid number for quantity."))

    if uid in waiting_proof and waiting_proof[uid].get('step') == 'wait_utr':
      info = waiting_proof.pop(uid)
      amt = info['amount']
      _method = info.get('method', 'FamPay Automatic')
      _label = auto_method_label(_method)
      _app = auto_method_app(_method)
      raw_utr = (e.text or "").strip()

      if raw_utr.lower() in ("/cancel", "cancel"):
        return await e.reply(custom_emoji_text(
          f"{P_NO} Deposit cancelled. No money was added."))

      # FamPay / UPI UTRs are 12 digits, but some banks use 8-22 chars.
      utr = re.sub(r"[\s\-]", "", raw_utr).upper()
      if not re.fullmatch(r"[A-Z0-9]{8,30}", utr):
        waiting_proof[uid] = info
        return await e.reply(custom_emoji_text(
          f"{P_NO} <b>Invalid UTR.</b>\n\n"
          f"Send the transaction reference only (8-30 letters/digits).\n"
          f"<i>{_app} / your UPI app → History → tap the payment → copy UTR.</i>\n\n"
          f"Send <code>/cancel</code> to abort."))
        
      await e.respond(custom_emoji_text(f"{P_WAIT} <b>Verifying your payment... Please wait.</b>"))
      
      settings_row_user = cur.execute("SELECT value FROM settings WHERE key='imap_email'").fetchone()
      settings_row_pass = cur.execute("SELECT value FROM settings WHERE key='imap_password'").fetchone()
      g_user = settings_row_user[0].strip() if settings_row_user and settings_row_user[0] else ""
      g_pass = settings_row_pass[0].strip() if settings_row_pass and settings_row_pass[0] else ""
      
      # Never credit the same UTR twice (approved or still pending).
      existing_utr = cur.execute(
        "SELECT id, status FROM deposits WHERE UPPER(REPLACE(REPLACE(COALESCE(utr,''),' ',''),'-',''))=? "
        "AND status IN ('approved','pending') LIMIT 1", (utr,)).fetchone()
      if existing_utr or utr in _UTR_IN_PROGRESS:
        waiting_proof[uid] = info
        return await e.respond(custom_emoji_text(
          f"{P_NO} <b>This UTR has already been used.</b>\n"
          f"Please enter a different transaction UTR or send <code>/cancel</code>."))

      # Reserve the UTR while we verify so two quick submissions can never
      # both be credited. The mailbox is polled over ONE connection for up to
      # ~45s, so the payment is credited the moment the email arrives.
      _UTR_IN_PROGRESS.add(utr)
      credited = False
      try:
        if _method == 'BharatPe Automatic':
          # BharatPe is verified ONLY through the merchant API (UTR lookup), never Gmail.
          paid_amount = await check_payment_bharatpe_api_async(utr, expected_amount=amt, wait_seconds=45)
        else:
          paid_amount = await check_payment_in_gmail_async(
            utr, g_user, g_pass, expected_amount=amt, wait_seconds=45,
            trusted_override=(get_bharatpe_senders() if _method == 'BharatPe Automatic' else None))

        if paid_amount is not None and paid_amount + 0.01 >= amt:
          # Credit what was actually paid when it is a sane over-payment
          # (max 2x the requested amount), otherwise credit the requested amount.
          credit = float(amt)
          try:
            if amt <= float(paid_amount) <= amt * 2:
              credit = round(float(paid_amount), 2)
          except Exception:
            pass
          async with get_user_lock(uid):
            dup = cur.execute(
              "SELECT id FROM deposits WHERE UPPER(REPLACE(REPLACE(COALESCE(utr,''),' ',''),'-',''))=? "
              "AND status IN ('approved','pending') LIMIT 1", (utr,)).fetchone()
            if dup:
              return await e.respond(custom_emoji_text(
                f"{P_NO} <b>This UTR has already been used.</b>"))
            prev_row = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
            prev_bal = prev_row[0] if prev_row else 0
            update_balance(uid, credit)
            cur.execute("INSERT INTO deposits (user_id, amount, method_name, status, utr) VALUES (?,?,?,?,?)", (uid, credit, _label, "approved", utr))
            cur.execute("UPDATE users SET total_deposited = total_deposited + ? WHERE user_id=?", (credit, uid))
            db.commit()
          credited = True
      finally:
        _UTR_IN_PROGRESS.discard(utr)

      if credited:
        try:
          await log_primary_deposit_success(uid, credit, _label, utr)
        except Exception:
          pass
        await _refer_reward(uid, credit)

        user_msg = (f"{P_YES} {P_PARTY} <b>Payment Verified Automatically!</b>\n\n"
              f"{P_MONEY} <b>Amount Credited:</b> ₹{credit:g}\n"
              f"{P_CARD} Previous Balance: ₹{prev_bal:g} | New Balance: ₹{prev_bal + credit:g}\n"
              f"{P_ID} UTR: <code>{html.escape(utr)}</code>")
        await e.respond(custom_emoji_text(user_msg))
        await send_main_menu(e, uid)
      else:
        # Fallback: If automated check fails, ask for a screenshot for manual review.
        waiting_proof[uid] = {'step': 'wait_screenshot', 'amount': amt, 'utr': utr, 'method': _method}
        await e.respond(
          custom_emoji_text(f"{P_WARN} <b>Automatic verification failed.</b>\n\n"
          f"No matching payment was found for UTR <code>{html.escape(utr)}</code>, "
          f"or the paid amount was lower than ₹{amt}.\n\n"
          f"{P_ASST} Send a <b>screenshot</b> of your payment receipt and the admin will approve it manually.\n"
          f"<i>Send <code>/cancel</code> to abort.</i>")
        )
      return

    if uid in waiting_proof and waiting_proof[uid].get('step') == 'wait_screenshot':
      if not _proof_media(e):
        return await e.reply(custom_emoji_text(f"{P_NO} Please send a valid image screenshot."))
      
      info = waiting_proof.pop(uid)
      amt = info['amount']
      utr = info['utr']
      _label = auto_method_label(info.get('method', 'FamPay Automatic'))
      
      cur.execute("INSERT INTO deposits (user_id, amount, method_name, status, utr) VALUES (?,?,?,?,?)", (uid, amt, _label + " (Pending Screenshot)", "pending", utr))
      db.commit()
      dep_id = cur.lastrowid
      
      cap = (f"{P_BELL} <b>NEW {html.escape(_label.upper())} MANUAL DEPOSIT REVIEW</b>\n\n"
          f"{P_ACC} User ID: <code>{uid}</code>\n"
          f"{P_MONEY} Amount: <b>₹{amt}</b>\n"
          f"{P_CARD} UTR: <code>{utr}</code>\n"
          f"{P_ID} Ref ID: <code>{dep_id}</code>")
      btns = [
        [Button.inline(f"Accept (₹{amt})", f"dep_acc|{dep_id}|{uid}|{_label}|exact|{amt}"),
         Button.inline("Reject", f"dep_rej|{dep_id}|{uid}")]
      ]
      
      # Send manual deposit review with screenshot to the owner and all configured admins.
      await send_admins_file(_proof_media(e), cap, buttons=btns)
        
      await e.respond(custom_emoji_text(f"{P_YES} <b>Payment screenshot forwarded to Admin successfully!</b>\nAdmin will review it and add the balance shortly."))
      await send_main_menu(e, uid)
      return

    # Payment screenshots usually have NO caption -> handle them before the empty-text return.
    if uid in deposit_input and deposit_input[uid].get('step') == 'wait_payment_screenshot' and _proof_media(e):
      return await _submit_deposit_screenshot(e, uid)

    text = e.text or ""
    if not text: return

    if text in ["Store", "Add Funds", "Profile", "Orders History", "Support", "Updates", "__ADMIN_PANEL_REMOVED__"]:
      session_buy_state.pop(uid, None)
      deposit_input.pop(uid, None)
      admin_dep_state.pop(uid, None)
      smm_order_state.pop(uid, None)
      refill_state.pop(uid, None)
      S1_SEARCH_STATE.pop(uid, None)

    # Server 1 mini-app search input (country search / account keyword).
    if uid in S1_SEARCH_STATE:
      st = S1_SEARCH_STATE.pop(uid, None) or {}
      if text.strip().lower() == "/cancel":
        return await e.respond(custom_emoji_text(f"{P_NO} Search cancelled."))
      if st.get("kind") == "country":
        return await server1_country_search_results(e, text)
      if st.get("kind") == "keyword":
        f = _s1_filters(uid)
        f["search"] = text.strip()
        cc = str(st.get("cc") or "").strip().upper()
        if cc:
          return await server1_country_detail(e, cc, 1)
        return await server1_filters_menu(e)

    if uid in session_buy_state:
      state = session_buy_state[uid]
      try:
        qty = int(re.sub(r'[^\d]', '', text))
        if qty < 1: raise ValueError
        if qty > state['stock']: return await e.respond(custom_emoji_text(f"{P_WARN} <b>Not enough stock!</b> Max is {state['stock']}."))
        
        disc_row = cur.execute("SELECT discount FROM users WHERE user_id=?", (uid,)).fetchone()
        discount = disc_row[0] if disc_row else 0
        total_cost = qty * state['price']
        if discount > 0: total_cost = int(total_cost * (100 - discount) / 100)
          
        bal_row = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
        user_bal = bal_row[0] if bal_row else 0
        if user_bal < total_cost: return await e.respond(custom_emoji_text(f"{P_NO} <b>Insufficient Balance!</b>\nYou need {P_INR}{total_cost} to buy {qty} sessions."))

        session_buy_state.pop(uid)
        await process_bulk_sessions(e, uid, qty, state, total_cost)
        return
      except ValueError: return await e.respond(custom_emoji_text(f"{P_NO} Please enter a valid number."))

    if uid in deposit_input and deposit_input[uid].get('step') == 'wait_payment_screenshot':
      if not _proof_media(e):
        return await e.respond(custom_emoji_text(f"{P_NO} Please send the payment screenshot (as an image)."))
      return await _submit_deposit_screenshot(e, uid)

  except Exception as ex: logger.error(f"Message Error: {ex}", exc_info=True)

@bot.on(events.CallbackQuery)
async def handle_callback_query(e):
  try:
    # Do not pre-answer the callback here. Individual branches answer alerts
    # when needed; pre-answering makes later alert/error responses invisible
    # and was causing many buttons to look dead. Successful edit/respond calls
    # also clear the Telegram button spinner.
    uid = e.sender_id
    if not is_bot_online() and not is_admin(uid):
      return await safe_callback_answer(
        e, "Bot is under maintenance. Please try again later." if get_bot_status() == 'maintenance'
        else "Bot is currently OFF. Please come back later.", alert=True)
      
    _cb_sender = await e.get_sender()
    ensure_user(uid, getattr(_cb_sender, 'username', '') or '', getattr(_cb_sender, 'first_name', '') or '')
    if is_user_banned(uid): return await safe_callback_answer(e, "BANNED / FROZEN", alert=True)
    raw_data = getattr(e, "data", b"")
    if isinstance(raw_data, bytes):
      data = raw_data.decode("utf-8", errors="replace")
    else:
      data = str(raw_data or "")

    # Leaving a Shop photo/file message: send the next screen as a fresh text
    # message so the old photo never stays glued above unrelated screens.
    _mkey = (e.chat_id, getattr(e, "message_id", None) or getattr(getattr(e, "query", None), "msg_id", None))
    if _mkey in _SHOP_PREVIEW_MSGS or _mkey in _SHOP_DELIVERED_MSGS:
      _orig_edit = e.edit
      _delete_old = _mkey in _SHOP_PREVIEW_MSGS

      async def _edit_as_new(*args, **kwargs):
        text = args[0] if args else kwargs.get("text")
        if text is None or kwargs.get("file") is not None:
          return await _orig_edit(*args, **kwargs)
        if _delete_old:
          try:
            await e.delete()
          except Exception:
            pass
          _SHOP_PREVIEW_MSGS.discard(_mkey)
        return await bot.send_message(
          e.chat_id, text, buttons=kwargs.get("buttons"),
          parse_mode=kwargs.get("parse_mode", "html"))
      e.edit = _edit_as_new

    if data == "cb_store":
      try:
        await store_servers_menu(e)
      except Exception as ex:
        logger.error(f"Store callback error: {ex}", exc_info=True)
        await safe_callback_answer(e, "Store could not be opened. Please try /start again.", alert=True)
    elif data == "digital_shop":
      try:
        await digital_shop_menu(e)
      except Exception as ex:
        logger.error(f"Shop callback error: {ex}", exc_info=True)
        try:
          await bot.send_message(e.chat_id, custom_emoji_text(f"{P_NO} <b>Shop</b>\n\nPlease try again."), buttons=[[Button.inline("Back to Store", "store_servers")]], parse_mode='html')
        except Exception:
          pass
    elif data.startswith("digital_product|"):
      await digital_product_view(e, int(data.split("|")[1]))
    elif data.startswith("digital_buy|"):
      await digital_buy(e, int(data.split("|")[1]))
    elif data == "redeem_start":
      redeem_state[uid] = {'step':'wait_code'}
      await e.edit(custom_emoji_text("Enter your redeem code (for example: AKOP):"), buttons=[[Button.inline("Cancel","cancel_action")]])
    elif data == "smm_cancel":
      smm_order_state.pop(uid, None)
      await safe_callback_answer(e, "Cancelled.")
      await send_main_menu(e, uid)
    elif data == "cb_smm_services":
      smm_order_state.pop(uid, None)
      await show_smm_categories(e)
    elif data.startswith("smm_cat|"):
      smm_order_state.pop(uid, None)
      cid = int(data.split("|")[1])
      await show_smm_services_in_category(e, cid)
    elif data.startswith("smm_srv|"):
      sid = int(data.split("|")[1])
      await smm_service_detail_view(e, sid)
    elif data.startswith("smm_buy|"):
      sid = int(data.split("|")[1])
      row = cur.execute("SELECT service_id, name, rate, min, max FROM smm_services WHERE service_id=?", (sid,)).fetchone()
      if not row: return await safe_callback_answer(e, "Service not found.", alert=True)
      s_id, s_name, s_rate, s_min, s_max = row
      smm_order_state[uid] = {'service_id': s_id, 'name': s_name, 'rate': s_rate, 'min': s_min, 'max': s_max, 'step': 'wait_link'}
      await e.edit(custom_emoji_text(f"{P_ID} <b>Service ID: {s_id}</b>\n{P_TITLE} <b>Title: {html.escape(s_name)}</b>\n\n{P_ASST} <b>Send Link:</b>"), buttons=[[Button.inline(" Cancel", "cancel_action")]])
    elif data == "cb_addfunds":
      await deposit_menu(e)
    elif data == "cb_profile":
      await profile_handler(e, is_callback=True)
    elif data == "cb_refer":
      await show_refer_menu(e)
    elif data == "cb_orders":
      await orders_history_handler(e, is_callback=True)
    elif data == "cb_refill":
      refill_state[uid] = {'step': 'wait_order_id'}
      msg = f"{P_ID} <b>SMM Service Refill</b>\n\nPlease reply with your <b>SMM Order No.</b> that you want to refill:"
      btns = [[Button.inline("Cancel", "cancel_action")]]
      await e.edit(custom_emoji_text(msg), buttons=btns)
    elif data == "cb_support":
      # Backward-compatible handler for older menus.
      support_url = get_support_url()
      if not _has_valid_button_url(support_url):
        return await safe_callback_answer(e, custom_emoji_text(" Support link is not configured by Admin yet."), alert=True)
      await safe_callback_answer(e, custom_emoji_text(" Opening Support..."), alert=False)
      await e.respond(
        custom_emoji_text(f"{P_ON} <b>Support</b>\n\n{P_ASST} Tap below to contact support."),
        buttons=[[_safe_url_button("Support", support_url)],
             [Button.inline("Back to Main", "back_main")]]
      )
    elif data == "cb_updates":
      # Backward-compatible handler for older menus.
      updates_url = get_support_channel_url()
      if not _has_valid_button_url(updates_url):
        return await safe_callback_answer(e, custom_emoji_text(" Updates channel link is not configured by Admin yet."), alert=True)
      await safe_callback_answer(e, custom_emoji_text(" Opening Updates..."), alert=False)
      await e.respond(
        custom_emoji_text(f"{P_STAR} <b>Channel Updates & News</b> {P_ROCKET}\n\n{P_ASST} Tap below to open the official updates channel."),
        buttons=[[_safe_url_button("Updates", updates_url)],
             [Button.inline("Back to Main", "back_main")]]
      )
    elif data == "verify_join":
      if not await check_channel_joined(uid): return await safe_callback_answer(e, "You must join the channels first!", alert=True)
      await send_main_menu(e, uid)

    elif data == "cancel_action":
      deposit_input.pop(uid, None); waiting_proof.pop(uid, None); session_buy_state.pop(uid, None); smm_order_state.pop(uid, None); refill_state.pop(uid, None); redeem_state.pop(uid, None)
      try: await e.edit(custom_emoji_text(f"{P_NO} <b>Cancelled.</b>"))
      except MessageNotModifiedError: pass

    elif data == "store_servers":
      await store_servers_menu(e)

    elif data == "srv1_accounts":
      await server1_category_menu(e)

    elif data == "srv1_countries":
      await server1_countries_menu(e, 1)

    elif data.startswith("srv1_cat|"):
      await server1_pick_category(e, data.split("|", 1)[1])

    elif data == "srv1_agree":
      await server1_agree(e)

    elif data == "srv1_decline":
      await server1_decline(e)

    elif data.startswith("srv1_pg|"):
      await server1_countries_menu(e, int(data.split("|")[1]))

    elif data == "srv1_ref":
      await server1_countries_menu(e, 1, force_refresh=True)

    elif data.startswith("srv1_sort|"):
      await server1_set_sort(e, data.split("|", 1)[1])

    elif data.startswith("srv1_c|"):
      await server1_country_detail(e, data.split("|")[1], 1)

    elif data.startswith("srv1_l|"):
      await server1_country_detail(e, data.split("|")[1], 1)

    elif data.startswith("srv1_ip|"):
      p = data.split("|")
      await server1_country_detail(e, p[1], int(p[2]))

    elif data.startswith("srv1_ipr|"):
      p = data.split("|")
      await server1_country_detail(e, p[1], int(p[2]), force_refresh=True)

    elif data.startswith("srv1_i|"):
      p = data.split("|")
      await server1_item_detail(e, p[1], p[2], int(p[3]))

    elif data.startswith("srv1_buy|"):
      p = data.split("|")
      await server1_buy_terms(e, "b", p[1], p[2] if len(p) > 2 else "-")

    elif data.startswith("srv1_ok|"):
      p = data.split("|")
      await server1_buy_agreed(e, p[1], p[2], p[3] if len(p) > 3 else "-")

    elif data.startswith("srv1_bulk|"):
      await server1_bulk_menu(e, data.split("|", 1)[1])

    elif data.startswith("srv1_bq|"):
      p = data.split("|")
      await server1_buy_terms(e, "q", p[1], p[2])

    elif data == "srv1_filters":
      await server1_filters_menu(e)

    elif data.startswith("srv1_fch|"):
      await server1_filter_choice(e, data.split("|", 1)[1])

    elif data.startswith("srv1_fset|"):
      p = data.split("|")
      await server1_filter_set(e, p[1], p[2] if len(p) > 2 else "any")

    elif data == "srv1_freset":
      await server1_filter_reset(e)

    elif data.startswith("srv1_fsearch"):
      await server1_filter_search(e, data.split("|", 1)[1] if "|" in data else "")

    elif data == "srv1_csearch":
      await server1_country_search_prompt(e)

    elif data.startswith("srv1_code|"):
      await server1_order_detail(e, data.split("|", 1)[1], poll=True)

    elif data.startswith("srv1_ord|"):
      await server1_order_detail(e, data.split("|", 1)[1], poll=False)

    elif data.startswith("srv1_ses|"):
      await server1_send_session(e, data.split("|", 1)[1])

    elif data.startswith("srv1_secc|"):
      _sp = data.split("|")
      await server1_secure_confirm(e, _sp[1], _sp[2])
    elif data.startswith("srv1_secx|"):
      _sp = data.split("|")
      await server1_secure_run(e, _sp[1], _sp[2])
    elif data.startswith("srv1_sec|"):
      await server1_secure_others(e, data.split("|", 1)[1])

    elif data == "srv1_orders":
      await orders_history_handler(e, is_callback=True)

    elif data == "back_main":
      try:
        await send_main_menu(e, uid)
      except Exception as ex:
        logger.error(f"back_main failed: {ex}", exc_info=True)
        try:
          await bot.send_message(
            uid,
            custom_emoji_text(f"{P_NO} <b>Could not open the main menu.</b>\n\n"
                              f"Please send /start to reload the bot."),
            buttons=[[Button.inline("Try Again", "back_main")]],
            parse_mode='html')
        except Exception:
          await safe_callback_answer(e, "Please send /start to reload the bot.", alert=True)

    elif data == "profile_callback":
      await profile_handler(e, is_callback=True)

    elif data.startswith("my_orders|"):
      await orders_history_handler(e, is_callback=True, page=int(data.split("|")[1]))
    elif data == "my_orders_list":
      await orders_history_handler(e, is_callback=True)

    elif data == "payments_history":
      await payments_history_handler(e)

    elif data == "dep_menu_cb":
      await deposit_menu(e)

    elif data.startswith("dep_key|"):
      state = deposit_input.get(uid)
      if not state or state.get('step') != 'amount_keypad':
        return await safe_callback_answer(e, "Amount session expired. Please start again.", alert=True)
      digit = data.split("|", 1)[1]
      if digit not in '0123456789':
        return await safe_callback_answer(e, "Invalid amount button.", alert=True)
      current = state.get('amount', '')
      if len(current) >= 8:
        return await safe_callback_answer(e, "Amount is too large.", alert=True)
      if not current and digit == '0':
        return await safe_callback_answer(e, "Amount cannot start with 0.", alert=True)
      state['amount'] = current + digit
      await show_deposit_amount_keypad(e, uid)

    elif data == "dep_key_del":
      state = deposit_input.get(uid)
      if not state or state.get('step') != 'amount_keypad':
        return await safe_callback_answer(e, "Amount session expired. Please start again.", alert=True)
      state['amount'] = state.get('amount', '')[:-1]
      await show_deposit_amount_keypad(e, uid)

    elif data == "dep_key_confirm":
      await generate_deposit_qr(e, uid)

    elif data == "dep_payment_verify":
      state = deposit_input.get(uid)
      if not state or state.get('step') != 'wait_payment_verify':
        return await safe_callback_answer(e, "Payment session expired. Please start again.", alert=True)
      amt = int(state.get('amount') or 0)
      method = state.get('method') or 'UPI Manual'

      if method in AUTO_METHODS:
        # Automatic UTR verification: ask for the 12-digit UTR and check the
        # payment email (FamPay / BharatPe) through Gmail IMAP. Screenshot is
        # only the fallback when the email cannot be matched.
        deposit_input.pop(uid, None)
        _app = auto_method_app(method)
        waiting_proof[uid] = {'step': 'wait_utr', 'amount': amt, 'auto': True, 'method': method}
        await e.edit(custom_emoji_text(
          f"{P_CARD} <b>Verify Payment</b>\n\n"
          f"{P_MONEY} Amount: <b>₹{amt}</b>\n"
          f"{P_ACC} Method: <b>{html.escape(method)}</b>\n\n"
          f"{P_ASST} <b>Send your UTR / Transaction ID now.</b>\n"
          f"<i>{_app} / your UPI app → History → tap the payment → copy the 12-digit UTR.</i>\n\n"
          f"{P_WAIT} Payment is verified automatically — no screenshot needed.\n"
          f"Send <code>/cancel</code> to abort."
        ), buttons=[[Button.inline(" Cancel", "cancel_action")]])
      else:
        state['step'] = 'wait_payment_screenshot'
        _usdt_line = (f"USDT Sent: <b>{state['usdt_amount']:.2f} USDT</b> ({html.escape(str(state.get('network', '')))})\n"
                      if state.get('usdt_amount') else "")
        await e.edit(custom_emoji_text(
          f"{P_CARD} <b>Verify Payment</b>\n\n"
          f"Amount: <b>₹{state['amount']}</b>\n"
          + _usdt_line +
          f"Method: <b>{html.escape(method)}</b>\n\n"
          f"{P_ASST} <b>Now send your payment screenshot here.</b>\n"
          f"The screenshot will be sent to all admins for verification."
        ), buttons=[[Button.inline(" Cancel", "cancel_action")]])

    elif data.startswith("dep_verify_start|"):
      # Backward compatibility for old payment messages: use screenshot verification.
      amt = int(data.split("|")[1])
      deposit_input[uid] = {'step': 'wait_payment_screenshot', 'amount': amt, 'method': 'FamPay Automatic'}
      await e.edit(custom_emoji_text(f"{P_CARD} <b>Verify Payment</b>\n\nAmount: <b>₹{amt}</b>\n\n{P_ASST} <b>Send your payment screenshot here.</b>\nIt will be forwarded to all admins for manual verification."), buttons=[[Button.inline(" Cancel", "cancel_action")]])

    elif data == "srv|manual":
      await show_server_countries(e, 'manual', 1)

    elif data.startswith("srv_pg|"):
      p = data.split("|")
      await show_server_countries(e, p[1], int(p[2]))

    elif data.startswith("s_country|"):
      p = data.split("|", 2)
      country = _resolve_country_ref(p[2]) if len(p) > 2 else ""
      await show_country_details(e, p[1], country)

    elif data.startswith("p_buy|"):
      p = data.split("|", 2)
      flow = p[1]
      country = _resolve_country_ref(p[2]) if len(p) > 2 else ""
      if flow == 'single':
        rows = cur.execute("SELECT account_year, price FROM stock WHERE available=1 AND country_name LIKE ? ORDER BY price ASC LIMIT 1", (f"{country}%",)).fetchone()
        if not rows: return await safe_callback_answer(e, "Out of stock!", alert=True)
        await confirm_purchase(e, country, rows[0], rows[1])
      else:
        rows = cur.execute("SELECT account_year, price FROM stock WHERE available=1 AND country_name LIKE ? ORDER BY price ASC LIMIT 1", (f"{country}%",)).fetchone()
        if not rows: return await safe_callback_answer(e, "Out of stock!", alert=True)
        await init_session_purchase(e, country, rows[0], rows[1])

    elif data.startswith("p_year|"):
      country_ref = data.split("|", 1)[1]
      country = _resolve_country_ref(country_ref)
      await show_years_for_country(e, country)

    elif data.startswith("by_yr|"):
      p = data.split("|")
      country = _resolve_country_ref(p[1])
      await confirm_purchase(e, country, p[2], p[3])

    elif data.startswith("buy_cf|"):
      p = data.split("|")
      country = _resolve_country_ref(p[1])
      await process_purchase(e, country, p[2], p[3])

    elif data.startswith("get_otp_again|"):
      phone = data.split("|")[1]
      if phone not in active_orders:
        return await safe_callback_answer(e, "Session already logged out or expired.", alert=True)
      
      order = active_orders[phone]
      client = order['client']
      start_time = order['start_time']
      
      await safe_callback_answer(e, "Fetching latest OTP...", alert=False)
      try:
        msgs = await client.get_messages(777000, limit=5)
        latest_code = None
        for m in msgs:
          if m.date.timestamp() > start_time - 10:
            if m.message and re.search(r'\b\d{5}\b', m.message) and "Login detected" not in m.message:
              latest_code = re.search(r'\b\d{5}\b', m.message).group()
              break
        
        if latest_code:
          twofa_text = f"{P_2FA} <b>2FA:</b> <code>{html.escape(order['twofa'])}</code>" if order['twofa'] != "None" else f"{P_2FA} <b>2FA:</b> <code>Disabled (No Password)</code>"
          msg = (f"{P_YES} {P_FIRE} <b>Latest OTP Fetched!</b>\n\n"
              f"{P_PHONE} <b>Phone:</b> <code>{phone}</code>\n"
              f"{P_FLAG} <b>Country:</b> {html.escape(order['country'])}\n"
              f"{P_OTP} <b>OTP:</b> <code>{_otp_gap(latest_code)}</code>\n"
              f"{twofa_text}")
          btns = [
            [Button.inline("Get OTP Again", f"get_otp_again|{phone}")],
            [Button.inline("Finish & Logout", f"logout_bot|{phone}")]
          ]
          try: await e.edit(custom_emoji_text(msg), buttons=btns)
          except MessageNotModifiedError: pass
        else:
          await safe_callback_answer(e, "No new OTP found yet. Try again in a few seconds.", alert=True)
      except Exception:
        await safe_callback_answer(e, "Error fetching OTP.", alert=True)

    elif data.startswith("logout_bot|"):
      phone = data.split("|")[1]
      if phone in active_orders:
        order = active_orders.pop(phone)
        try: await order['client'].log_out()
        except: pass
        try: await order['client'].disconnect()
        except: pass
        delete_session_files(order['sess'])
        try:
          cur.execute("UPDATE orders SET terminated=1 WHERE phone=? AND user_id=?", (phone, order['uid']))
          db.commit()
        except Exception: pass
        await e.edit(custom_emoji_text(f"{P_YES} <b>Session Finished & Logged out successfully.</b>"))
      else:
        await safe_callback_answer(e, "No active order found or already logged out.", alert=True)
    
    elif data == "depm_auto":
      if not payment_enabled('fampay_enabled'):
        await safe_callback_answer(e, "This payment method is currently disabled.", alert=True)
        return await deposit_menu(e)
      await manual_deposit_init(e, "FamPay Automatic")
    elif data == "depm_bharatpe":
      if not bharatpe_available():
        await safe_callback_answer(e, "This payment method is currently unavailable.", alert=True)
        return await deposit_menu(e)
      await manual_deposit_init(e, "BharatPe Automatic")
    elif data == "depm_usdt":
      if not usdt_manual_available():
        await safe_callback_answer(e, "This payment method is currently unavailable.", alert=True)
        return await deposit_menu(e)
      await manual_deposit_init(e, "USDT Manual")
    elif data == "depm_manual":
      if not payment_enabled('manual_enabled'):
        await safe_callback_answer(e, "This payment method is currently disabled.", alert=True)
        return await deposit_menu(e)
      await manual_deposit_init(e, "UPI Manual")
    
    elif data.startswith("adm_") and is_admin(uid): await admin_actions(e)
    
    elif data.startswith("dep_acc|") and has_perm(uid, 'p_bal'):
      p = data.split("|")
      dep_id, t_uid, method, a_type = p[1], int(p[2]), p[3], p[4]
      row = cur.execute("SELECT status FROM deposits WHERE id=?", (dep_id,)).fetchone()
      if not row or row[0] != 'pending': return await e.edit(custom_emoji_text(f"{P_WARN} Already processed."))
      
      if a_type == "exact":
        amt = int(p[5]) 
        async with get_user_lock(t_uid):
          prev_row = cur.execute("SELECT balance FROM users WHERE user_id=?", (t_uid,)).fetchone()
          prev_bal = prev_row[0] if prev_row else 0
          update_balance(t_uid, amt)
          
          cur.execute("UPDATE deposits SET status='approved', amount=? WHERE id=?", (amt, dep_id))
          cur.execute("UPDATE users SET total_deposited = total_deposited + ? WHERE user_id=?", (amt, t_uid))
          db.commit()
        await log_primary_deposit(t_uid, amt, method)
        await _refer_reward(t_uid, amt)
        
        user_msg = (f"{P_YES} {P_PARTY} <b>{_bold('Deposit Approved!')}</b>\n\n{P_MONEY} <b>Amount Added:</b> ₹{amt}\n"
              f"Previous Balance: ₹{prev_bal} | New Balance: ₹{prev_bal+amt}")
        await bot.send_message(int(t_uid), custom_emoji_text(user_msg))
        try: await e.edit(custom_emoji_text(f"{P_YES} <b>MANUALLY CREDITED ₹{amt} TO {t_uid}</b>"))
        except MessageNotModifiedError: pass
        
    elif data.startswith("dep_rej|") and has_perm(uid, 'p_bal'):
      p = data.split("|")
      dep_id, t_uid = p[1], int(p[2])
      row = cur.execute("SELECT status FROM deposits WHERE id=?", (dep_id,)).fetchone()
      if not row or row[0] != 'pending': return await e.edit(custom_emoji_text(f"{P_WARN} Already processed."))
      admin_dep_state[uid] = {'target_uid': t_uid, 'dep_id': dep_id, 'step': 'wait_reason', 'msg_id': getattr(getattr(e, '_message', None), 'id', None)}
      await bot.send_message(uid, custom_emoji_text(f"{P_WARN} Reply to this message with the REASON for rejecting user <code>{t_uid}</code>:"))
      try: await safe_callback_answer(e, "Check your bot PMs to enter the reason.", alert=True)
      except: pass
    elif data.startswith("s2wa_"):
      await _s2wa_dispatch(e, data)

    elif data.startswith("s3_"):
      await _s3_dispatch(e, data)

    elif data.startswith("fnmgmt"):
      await _fnm_dispatch(e, data)

    else:
      await safe_callback_answer(e, "This button is no longer active. Please open the menu again.", alert=True)

  except MessageNotModifiedError:
    # User tapped the same button again / content unchanged. Not an error.
    return
  except Exception as ex:
    logger.error(f"Callback Error: {ex}", exc_info=True)
    # Always leave the user with a visible response. If the callback was not
    # answered yet, the alert is useful; otherwise the chat message is the
    # fallback. Never let the error itself crash the callback handler.
    try:
      await safe_callback_answer(e, "This action failed. Please try again.", alert=True)
    except Exception:
      try:
        await bot.send_message(e.chat_id, f"Button error: {html.escape(str(ex))}")
      except Exception:
        pass


# =============================================================================
#  SERVER 2 [ WHATSAPP ACCOUNTS ]  +  FUNCTION MANAGEMENT  (integrated module)
#  ---------------------------------------------------------------------------
#  Tiger SMS API  ->  https://tiger-sms.com/api/openapi.json
#  All functions are prefixed _s2wa_ / _fnm_ so they never collide with the
#  rest of the bot. They reuse the bot's own db/cur, wallet, logs and styling.
# =============================================================================
import json as _s2wa_json
import time as _s2wa_time
import urllib.parse as _s2wa_urlparse
import urllib.request as _s2wa_urlreq
import urllib.error as _s2wa_urlerr
from datetime import datetime as _s2wa_datetime

_S2WA_HOSTS = [
  "https://api.tiger-sms.com/stubs/handler_api.php",
  "https://tiger-sms.com/stubs/handler_api.php",
]
_S2WA_BASE = _S2WA_HOSTS[0]
_S2WA_DEFAULT_SERVICE = "wa"
_S2WA_DEFAULT_MARGIN = 25.0
_S2WA_COUNTRIES_TTL = 6 * 3600
_S2WA_PRICES_TTL = 300

_S2WA_K_KEY = "s2_wa_api_key"
_S2WA_K_MARGIN = "s2_wa_margin"
_S2WA_K_SERVICE = "s2_wa_service"
_S2WA_K_ENABLED = "s2_wa_enabled"

_S2WA_FLAGS = {
    "russia": "\U0001F1F7\U0001F1FA", "brazil": "\U0001F1E7\U0001F1F7", "india": "\U0001F1EE\U0001F1F3",
    "indonesia": "\U0001F1EE\U0001F1E9", "usa": "\U0001F1FA\U0001F1F8", "united states": "\U0001F1FA\U0001F1F8",
    "united kingdom": "\U0001F1EC\U0001F1E7", "england": "\U0001F1EC\U0001F1E7", "germany": "\U0001F1E9\U0001F1EA",
    "france": "\U0001F1EB\U0001F1F7", "spain": "\U0001F1EA\U0001F1F8", "italy": "\U0001F1EE\U0001F1F9",
    "netherlands": "\U0001F1F3\U0001F1F1", "poland": "\U0001F1F5\U0001F1F1", "romania": "\U0001F1F7\U0001F1F4",
    "ukraine": "\U0001F1FA\U0001F1E6", "kazakhstan": "\U0001F1F0\U0001F1FF", "uzbekistan": "\U0001F1FA\U0001F1FF",
    "pakistan": "\U0001F1F5\U0001F1F0", "bangladesh": "\U0001F1E7\U0001F1E9", "nepal": "\U0001F1F3\U0001F1F5",
    "sri lanka": "\U0001F1F1\U0001F1F0", "philippines": "\U0001F1F5\U0001F1ED", "vietnam": "\U0001F1FB\U0001F1F3",
    "thailand": "\U0001F1F9\U0001F1ED", "malaysia": "\U0001F1F2\U0001F1FE", "singapore": "\U0001F1F8\U0001F1EC",
    "china": "\U0001F1E8\U0001F1F3", "japan": "\U0001F1EF\U0001F1F5", "south korea": "\U0001F1F0\U0001F1F7",
    "turkey": "\U0001F1F9\U0001F1F7", "egypt": "\U0001F1EA\U0001F1EC", "saudi arabia": "\U0001F1F8\U0001F1E6",
    "uae": "\U0001F1E6\U0001F1EA", "united arab emirates": "\U0001F1E6\U0001F1EA", "israel": "\U0001F1EE\U0001F1F1",
    "iran": "\U0001F1EE\U0001F1F7", "iraq": "\U0001F1EE\U0001F1F6", "morocco": "\U0001F1F2\U0001F1E6",
    "nigeria": "\U0001F1F3\U0001F1EC", "kenya": "\U0001F1F0\U0001F1EA", "south africa": "\U0001F1FF\U0001F1E6",
    "ghana": "\U0001F1EC\U0001F1ED", "mexico": "\U0001F1F2\U0001F1FD", "argentina": "\U0001F1E6\U0001F1F7",
    "colombia": "\U0001F1E8\U0001F1F4", "chile": "\U0001F1E8\U0001F1F1", "peru": "\U0001F1F5\U0001F1EA",
    "venezuela": "\U0001F1FB\U0001F1EA", "canada": "\U0001F1E8\U0001F1E6", "australia": "\U0001F1E6\U0001F1FA",
    "new zealand": "\U0001F1F3\U0001F1FF", "portugal": "\U0001F1F5\U0001F1F9", "greece": "\U0001F1EC\U0001F1F7",
    "czech": "\U0001F1E8\U0001F1FF", "hungary": "\U0001F1ED\U0001F1FA", "bulgaria": "\U0001F1E7\U0001F1EC",
    "serbia": "\U0001F1F7\U0001F1F8", "croatia": "\U0001F1ED\U0001F1F7", "sweden": "\U0001F1F8\U0001F1EA",
    "norway": "\U0001F1F3\U0001F1F4", "denmark": "\U0001F1E9\U0001F1F0", "finland": "\U0001F1EB\U0001F1EE",
    "switzerland": "\U0001F1E8\U0001F1ED", "austria": "\U0001F1E6\U0001F1F9", "belgium": "\U0001F1E7\U0001F1EA",
    "ireland": "\U0001F1EE\U0001F1EA", "belarus": "\U0001F1E7\U0001F1FE", "moldova": "\U0001F1F2\U0001F1E9",
    "georgia": "\U0001F1EC\U0001F1EA", "armenia": "\U0001F1E6\U0001F1F2", "azerbaijan": "\U0001F1E6\U0001F1FF",
    "kyrgyzstan": "\U0001F1F0\U0001F1EC", "tajikistan": "\U0001F1F9\U0001F1EF", "mongolia": "\U0001F1F2\U0001F1F3",
}


def _s2wa_flag(name):
  code = country_code_from_name(name)
  if code:
    return country_flag_fallback(code)
  return _S2WA_FLAGS.get((name or "").strip().lower(), "\U0001F30D")


def _s2wa_iso_from_flag(flag):
  """Decode a unicode flag emoji (two regional indicators) into ISO-3166-1
  alpha-2, e.g. \U0001F1F7\U0001F1FA -> "RU". Returns "" when it cannot."""
  try:
    chars = [c for c in str(flag or "") if 0x1F1E6 <= ord(c) <= 0x1F1FF]
    if len(chars) >= 2:
      return "".join(chr(ord(c) - 0x1F1E6 + 65) for c in chars[:2])
  except Exception:
    pass
  return ""


def _s2wa_flag_code(item):
  """Best-effort ISO-2 code for a WhatsApp country dict/flag/name."""
  if isinstance(item, dict):
    # Name decides the flag so country + flag always match.
    by_name = resolve_country_code(item.get("name"), None)
    if by_name:
      return by_name
    code = str(item.get("code") or "").strip().upper()
    if len(code) == 2 and code.isalpha():
      return code
    return _s2wa_iso_from_flag(item.get("flag"))
  raw = str(item or "").strip()
  if len(raw) == 2 and raw.isalpha():
    return raw.upper()
  return _s2wa_iso_from_flag(raw)


def _s2wa_flag_html(item):
  """Premium custom-emoji flag markup for WhatsApp panels."""
  code = _s2wa_flag_code(item)
  if not CUSTOM_EMOJI_ENABLED:
    return country_flag_fallback(code)
  return country_flag_html(code, item.get("name") if isinstance(item, dict) else None)


def _s2wa_flag_icon(item):
  """Custom emoji id used as the country button icon (None if unsupported)."""
  if not CUSTOM_EMOJI_ENABLED:
    return None
  return country_flag_icon_id(_s2wa_flag_code(item), item.get("name") if isinstance(item, dict) else None)


class _S2waError(Exception):
  pass


def _s2wa_hosts():
  """Admin-configured provider URL first, then the built-in mirrors.

  A Reseller (main store) URL is never used as a Tiger host: that would call
  /stubs/handler_api.php on the main bot and return "Not Found".
  """
  hosts = []
  try:
    custom = str(get_setting("s2_wa_url", "") or "").strip()
  except Exception:
    custom = ""
  if custom:
    _c = _strip_provider_path(custom)
    _ck = ""
    try:
      _ck = str(get_setting(_S2WA_K_KEY, "") or "").strip()
    except Exception:
      pass
    _is_res = (_ck.startswith("ats_")
               or _c.lower().rstrip("/").endswith("/v1")
               or "/v1/" in _c.lower()
               or (_url_host_of(_c) and _url_host_of(_c) == _url_host_of(_main_store_base())))
    if not _is_res:
      hosts.append(custom)
  hosts.extend(h for h in _S2WA_HOSTS if h not in hosts)
  return hosts


def _s2wa_http(action, api_key, _hosts_url=None, **params):
  q = {"action": action, "api_key": api_key}
  for k, v in params.items():
    if v is not None:
      q[k] = v
  qs = _s2wa_urlparse.urlencode(q)
  last_err = None
  _hosts = _s2wa_hosts()
  if _hosts_url:
    _hosts = [_hosts_url] + [h for h in _hosts if h != _hosts_url]
  for base in _hosts:
    url = base + "?" + qs
    req = _s2wa_urlreq.Request(url, headers={"User-Agent": "otpop-s2wa/1.0"})
    try:
      with _s2wa_urlreq.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8", "replace").strip()
        # A valid answer from this host: stop trying mirrors.
        if body:
          return body
        last_err = _S2waError("EMPTY_RESPONSE")
    except _s2wa_urlerr.HTTPError as ex:
      body = ""
      try:
        body = ex.read().decode("utf-8", "replace").strip()
      except Exception:
        pass
      if body == "BAD_KEY" or ex.code == 401:
        raise _S2waError("BAD_KEY")
      # A real API error (BAD_SERVICE / BAD_COUNTRY ...) -> do not retry mirrors.
      if body and ex.code < 500:
        raise _S2waError(body)
      last_err = _S2waError("HTTP_%s:%s" % (ex.code, body[:80]))
    except Exception as ex:
      last_err = _S2waError("NET:%s" % ex)
  raise last_err or _S2waError("NET:unknown")


class _S2waTiger(object):
  def __init__(self, api_key, url=None, server_no=None):
    if not api_key:
      raise _S2waError("NO_KEY")
    self.key = api_key
    self.url = url or None
    # Which store server this client belongs to (2 = WhatsApp, 3 = All apps).
    # Needed so Reseller-mode calls go to the right /v1 endpoint.
    self.server_no = int(server_no) if server_no in (1, 2, 3) else None

  def _reseller_srv(self):
    if self.server_no in (1, 2, 3):
      return self.server_no
    return 2

  def _is_reseller(self):
    return (str(self.key or "").startswith("ats_")
            or _is_reseller_upstream(self._reseller_srv()))

  def balance(self):
    if str(self.key or "").startswith("ats_") or _is_reseller_upstream(2) or _is_reseller_upstream(3):
      srv = 2 if (_is_reseller_upstream(2) or str(self.key or "").startswith("ats_")) else 3
      if not _is_reseller_upstream(2) and _is_reseller_upstream(3):
        srv = 3
      res = _reseller_balance(srv)
      if not res.get("ok"):
        raise _S2waError(str(res.get("message") or res.get("error") or "BAD_BALANCE"))
      try:
        rate = float(get_usdt_rate())
      except Exception:
        rate = 94.0
      if rate <= 0:
        rate = 94.0
      return float(res.get("balance") or 0) / rate
    raw = _s2wa_http("getBalance", self.key, _hosts_url=self.url)
    if raw.startswith("ACCESS_BALANCE:"):
      try:
        return float(raw.split(":", 1)[1])
      except ValueError:
        raise _S2waError("BAD_BALANCE")
    raise _S2waError(raw)

  def countries(self):
    if self._is_reseller():
      if self._reseller_srv() == 3:
        return _reseller_s3_countries()
      return _reseller_s2_countries(True)
    raw = _s2wa_http("getCountries", self.key, _hosts_url=self.url)
    try:
      data = _s2wa_json.loads(raw)
    except Exception:
      raise _S2waError("BAD_JSON")
    if not isinstance(data, list):
      raise _S2waError("BAD_JSON")
    out = []
    for c in data:
      try:
        name = c.get("eng") or c.get("rus") or str(c["id"])
        flag = _s2wa_flag(name)
        out.append({"id": int(c["id"]), "name": name, "flag": flag,
                    "retry": c.get("retry"),
                    "code": resolve_country_code(name, None) or _s2wa_iso_from_flag(flag)})
      except Exception:
        continue
    out.sort(key=lambda x: x["name"].lower())
    return out

  def prices(self, service, country=None):
    if self._is_reseller():
      if self._reseller_srv() == 3:
        items = _reseller_s3_available(service)
        out = {}
        for it in items:
          out.setdefault(str(it["id"]), {})[service] = {
            "cost": "%.6f" % float(it.get("cost") or 0),
            "count": int(it.get("count") or 0)}
        return out
      pmap = _reseller_s2_prices_map()
      out = {}
      for cid, pair in (pmap or {}).items():
        out.setdefault(str(cid), {})[service] = {
          "cost": "%.6f" % float(pair[0]), "count": int(pair[1])}
      return out
    params = {"service": service}
    if country is not None:
      params["country"] = country
    raw = _s2wa_http("getPrices", self.key, _hosts_url=self.url, **params)
    try:
      return _s2wa_json.loads(raw)
    except Exception:
      raise _S2waError(raw)

  def price_for(self, service, country):
    data = self.prices(service, country)
    node = data.get(str(country), {}).get(service)
    if not node:
      return None
    try:
      return float(node["cost"]), int(node.get("count", 0))
    except Exception:
      return None

  def services(self):
    if self._is_reseller():
      if self._reseller_srv() == 3:
        return _reseller_s3_apps()
      return [{"code": "wa", "name": "WhatsApp"}]
    raw = _s2wa_http("getServicesList", self.key, _hosts_url=self.url)
    try:
      data = _s2wa_json.loads(raw)
    except Exception:
      return []
    if isinstance(data, dict):
      return data.get("services") or []
    return []

  def price_map_v1(self, service=None):
    """getPrices -> {country_id(int): {service: {"cost": str, "count": int}}}"""
    if self._is_reseller():
      svc = service or ("wa" if self._reseller_srv() != 3 else "")
      return self.prices(svc) if svc else {}
    raw = _s2wa_http("getPrices", self.key, _hosts_url=self.url, service=service)
    try:
      data = _s2wa_json.loads(raw)
    except Exception:
      raise _S2waError(raw[:80] if raw else "BAD_JSON")
    if not isinstance(data, dict):
      raise _S2waError("BAD_JSON")
    return data

  def price_map_v3(self, service=None):
    """getPricesV3 -> {country_id(int): {service: {"price": float, "count": int}}}"""
    if self._is_reseller():
      svc = service or ("wa" if self._reseller_srv() != 3 else "")
      return self.prices(svc) if svc else {}
    raw = _s2wa_http("getPricesV3", self.key, _hosts_url=self.url, service=service)
    try:
      data = _s2wa_json.loads(raw)
    except Exception:
      raise _S2waError(raw[:80] if raw else "BAD_JSON")
    if not isinstance(data, dict):
      raise _S2waError("BAD_JSON")
    return data

  def get_number(self, service, country, max_price=None):
    if self._is_reseller():
      svc = str(service or "").lower()
      # A Server 3 client always buys from the All-app OTP endpoint, even when
      # the app code happens to be "wa" (WhatsApp is listed there too).
      if self.server_no == 3:
        act, phone, _oid = _reseller_s3_buy(service, country, max_price)
        return act, phone
      if self.server_no == 2:
        act, phone, _oid = _reseller_s2_buy(country, max_price)
        return act, phone
      if svc in ("wa", "whatsapp", "wb", "wa_") or not svc:
        act, phone, _oid = _reseller_s2_buy(country, max_price)
        return act, phone
      act, phone, _oid = _reseller_s3_buy(service, country, max_price)
      return act, phone
    params = {"service": service, "country": country}
    if max_price is not None:
      params["maxPrice"] = "%.4f" % max_price
    raw = _s2wa_http("getNumber", self.key, _hosts_url=self.url, **params)
    if raw.startswith("ACCESS_NUMBER:"):
      parts = raw.split(":")
      if len(parts) >= 3:
        return parts[1], parts[2]
      raise _S2waError("BAD_NUMBER")
    raise _S2waError(raw)

  def status(self, activation_id):
    if self._is_reseller():
      aid = str(activation_id or "")
      # The client knows its own server; order ids are stored bare, so the
      # prefix check alone would send Server 3 orders to Server 2.
      if self.server_no == 3:
        return _reseller_s3_status(aid)
      if self.server_no == 2:
        return _reseller_s2_status(aid)
      # Prefer matching prefix; otherwise try WA then App OTP.
      if aid.upper().startswith("A-") or (not aid.upper().startswith("W-") and _is_reseller_upstream(3) and not _is_reseller_upstream(2)):
        return _reseller_s3_status(aid)
      st = _reseller_s2_status(aid)
      if st == "NO_ACTIVATION":
        return _reseller_s3_status(aid)
      return st
    return _s2wa_http("getStatus", self.key, _hosts_url=self.url, id=activation_id)

  def set_status(self, activation_id, status):
    if self._is_reseller():
      st = int(status)
      aid = str(activation_id or "")
      if self.server_no == 3:
        use_s3 = True
      elif self.server_no == 2:
        use_s3 = False
      else:
        use_s3 = aid.upper().startswith("A-") or (_is_reseller_upstream(3) and not _is_reseller_upstream(2))
      if st == 8:
        return _reseller_s3_cancel(aid) if use_s3 else _reseller_s2_cancel(aid)
      if st == 3:
        return _reseller_s3_retry(aid) if use_s3 else _reseller_s2_retry(aid)
      return "ACCESS_ACTIVATION"
    return _s2wa_http("setStatus", self.key, _hosts_url=self.url, id=activation_id, status=status)


# ---- config helpers --------------------------------------------------------
def _s2wa_api_key():
  return str(get_setting(_S2WA_K_KEY, "") or "").strip()


def _s2wa_margin():
  try:
    return float(get_setting(_S2WA_K_MARGIN, _S2WA_DEFAULT_MARGIN))
  except Exception:
    return _S2WA_DEFAULT_MARGIN


def _s2wa_service():
  return str(get_setting(_S2WA_K_SERVICE, _S2WA_DEFAULT_SERVICE) or _S2WA_DEFAULT_SERVICE)


def _s2wa_enabled():
  if str(get_setting(_S2WA_K_ENABLED, "on")).lower() != "on":
    return False
  return _fnm_on("server2wa")


def _s2wa_sell_price(cost_usd):
  try:
    rate = float(get_usdt_rate())
  except Exception:
    rate = 94.0
  return round(cost_usd * rate * (1.0 + _s2wa_margin() / 100.0), 2)


def _s2wa_wallet(uid):
  try:
    return float(_s1_wallet(uid)[0])
  except Exception:
    try:
      row = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
      return float(row[0] or 0) if row else 0.0
    except Exception:
      return 0.0


_S2WA_CACHE = {"countries": (0, None), "prices": {}, "map": (0, None), "service": (0, None)}


def _s2wa_countries(force=False):
  now = _s2wa_time.time()
  ts, data = _S2WA_CACHE["countries"]
  if not force and data is not None and now - ts < _S2WA_COUNTRIES_TTL:
    return data
  if _is_reseller_upstream(2):
    data = _reseller_s2_countries(force)
  else:
    data = _S2waTiger(_s2wa_api_key()).countries()
  _S2WA_CACHE["countries"] = (now, data)
  return data


def _s2wa_resolve_service(force=False):
  """Return a service code that the provider actually knows.

  The configured code (default 'wa') is used when it exists in
  getServicesList; otherwise we auto-detect the WhatsApp entry so the price
  lookup never dies with BAD_SERVICE.
  """
  configured = _s2wa_service()
  now = _s2wa_time.time()
  ts, cached = _S2WA_CACHE["service"]
  if not force and cached and now - ts < _S2WA_COUNTRIES_TTL:
    return cached
  if _is_reseller_upstream(2) or str(_s2wa_api_key() or "").startswith("ats_"):
    _S2WA_CACHE["service"] = (now, configured or "wa")
    return configured or "wa"
  try:
    services = _S2waTiger(_s2wa_api_key()).services()
  except Exception:
    return configured
  codes = []
  for s in services or []:
    try:
      code = str(s.get("code") or "").strip()
      name = str(s.get("name") or "").lower()
      if code:
        codes.append((code, name))
    except Exception:
      continue
  if not codes:
    return configured
  if any(c == configured for c, _n in codes):
    _S2WA_CACHE["service"] = (now, configured)
    return configured
  # Auto-detect WhatsApp by name, then by common codes.
  for c, n in codes:
    if "whats" in n:
      _S2WA_CACHE["service"] = (now, c)
      return c
  for c, _n in codes:
    if c in ("wa", "whatsapp", "wa_", "wb"):
      _S2WA_CACHE["service"] = (now, c)
      return c
  return configured


def _s2wa_prices_map(force=False):
  """Return {country_id(int): (cost_usd float, count int)} for WhatsApp.

  Tries, in order: getPrices(service) -> getPricesV3(service) ->
  getPrices(no filter) -> getPricesV3(no filter). This makes the country
  list work across every provider variant instead of failing on one call.
  """
  now = _s2wa_time.time()
  ts, cached = _S2WA_CACHE["map"]
  if not force and cached is not None and now - ts < _S2WA_PRICES_TTL:
    return cached

  if _is_reseller_upstream(2):
    parsed = _reseller_s2_prices_map()
    _S2WA_CACHE["map"] = (now, parsed)
    return parsed

  tiger = _S2waTiger(_s2wa_api_key())
  service = _s2wa_resolve_service(force)
  wanted = {service, "wa", "whatsapp", "wb"}
  errors = []

  def _extract(raw_map, price_key):
    out = {}
    if not isinstance(raw_map, dict):
      return out
    for cid, node in raw_map.items():
      try:
        cid_i = int(cid)
      except Exception:
        continue
      if not isinstance(node, dict):
        continue
      svc_node = None
      for cand in (service, "wa", "whatsapp", "wb"):
        if cand in node and isinstance(node[cand], dict):
          svc_node = node[cand]
          break
      if svc_node is None:
        # no-filter call: accept the first service node that looks like WhatsApp
        for k, v in node.items():
          if isinstance(v, dict) and str(k).lower() in wanted:
            svc_node = v
            break
      if svc_node is None:
        continue
      try:
        cost = float(svc_node.get(price_key, svc_node.get("cost", svc_node.get("price"))))
        count = int(svc_node.get("count", 0) or 0)
      except Exception:
        continue
      if cost > 0:
        out[cid_i] = (cost, count)
    return out

  attempts = [
    (lambda: tiger.price_map_v1(service), "cost"),
    (lambda: tiger.price_map_v3(service), "price"),
    (lambda: tiger.price_map_v1(None), "cost"),
    (lambda: tiger.price_map_v3(None), "price"),
  ]
  for fn, pk in attempts:
    try:
      raw = fn()
      parsed = _extract(raw, pk)
      if parsed:
        _S2WA_CACHE["map"] = (now, parsed)
        return parsed
    except Exception as ex:
      errors.append(str(ex))

  # Nothing parsed: surface a useful reason instead of a silent empty list.
  raise _S2waError(errors[-1] if errors else "NO_PRICES")


def _s2wa_price(country_id, force=False):
  try:
    pmap = _s2wa_prices_map(force)
  except Exception:
    return None
  return pmap.get(int(country_id))


# ---- local orders table ----------------------------------------------------
def _s2wa_ensure_table():
  cur.execute(
    """
    CREATE TABLE IF NOT EXISTS s2_wa_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER NOT NULL,
        activation_id TEXT,
        phone TEXT,
        country_name TEXT,
        country_id INTEGER,
        service TEXT,
        cost_usd REAL,
        price_inr REAL,
        status TEXT,
        code TEXT,
        created_at TEXT,
        updated_at TEXT,
        refunded INTEGER NOT NULL DEFAULT 0
    )
    """
  )
  # Upgrade databases created by earlier bot versions without losing orders.
  cols = {row[1] for row in cur.execute("PRAGMA table_info(s2_wa_orders)").fetchall()}
  if "refunded" not in cols:
    cur.execute("ALTER TABLE s2_wa_orders ADD COLUMN refunded INTEGER NOT NULL DEFAULT 0")
  cur.execute("CREATE INDEX IF NOT EXISTS idx_s2wa_uid ON s2_wa_orders(uid)")
  db.commit()


def _s2wa_new_order(uid, activation_id, phone, country_name, country_id, service, cost_usd, price_inr):
  now = _s2wa_datetime.utcnow().isoformat()
  cur.execute(
    "INSERT INTO s2_wa_orders(uid,activation_id,phone,country_name,country_id,"
    "service,cost_usd,price_inr,status,created_at,updated_at) "
    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
    (uid, activation_id, phone, country_name, country_id, service,
     cost_usd, price_inr, "WAIT_CODE", now, now),
  )
  db.commit()
  return cur.lastrowid


def _s2wa_update_order(activation_id, **fields):
  if not fields:
    return
  fields["updated_at"] = _s2wa_datetime.utcnow().isoformat()
  cols = ", ".join("%s=?" % k for k in fields)
  cur.execute("UPDATE s2_wa_orders SET %s WHERE activation_id=?" % cols,
              tuple(fields.values()) + (activation_id,))
  db.commit()
  if 'status' in fields:
    cur.execute("UPDATE global_orders SET status=? WHERE service='whatsapp' AND local_ref=?",
                (str(fields['status']), str(activation_id)))
    db.commit()


def _s2wa_get_order(activation_id):
  row = cur.execute("SELECT * FROM s2_wa_orders WHERE activation_id=?", (activation_id,)).fetchone()
  if not row:
    return None
  cols = [d[0] for d in cur.description]
  return dict(zip(cols, row))


def _s2wa_refund_once(activation_id, uid):
  """Credit the user's wallet once, only for an existing unpaid activation."""
  order = _s2wa_get_order(activation_id)
  if not order or int(order.get("uid") or 0) != int(uid):
    return False, 0.0
  price = max(0.0, float(order.get("price_inr") or 0))
  if price <= 0:
    return False, 0.0
  # The conditional update is the idempotency guard: repeated callbacks/polls
  # cannot credit the same activation twice.
  cur.execute(
    "UPDATE s2_wa_orders SET status='CANCELLED', refunded=1, updated_at=? "
    "WHERE activation_id=? AND uid=? AND COALESCE(refunded,0)=0 "
    "AND status IN ('WAIT_CODE','WAIT_RETRY')",
    (_s2wa_datetime.utcnow().isoformat(), str(activation_id), int(uid)),
  )
  db.commit()
  if cur.rowcount != 1:
    return False, price
  try:
    update_balance(uid, price)
    cur.execute("UPDATE global_orders SET status='CANCELLED - REFUNDED',refunded=1 WHERE service='whatsapp' AND local_ref=?", (str(activation_id),))
    db.commit()
  except Exception:
    # Restore eligibility if wallet credit failed, so an admin can safely retry.
    cur.execute("UPDATE s2_wa_orders SET refunded=0 WHERE activation_id=? AND uid=?",
                (str(activation_id), int(uid)))
    db.commit()
    raise
  return True, price


def _s2wa_user_orders(uid, limit=10):
  rows = cur.execute("SELECT * FROM s2_wa_orders WHERE uid=? ORDER BY id DESC LIMIT ?",
                     (uid, limit)).fetchall()
  cols = [d[0] for d in cur.description]
  return [dict(zip(cols, r)) for r in rows]


# ---- UI helpers ------------------------------------------------------------
def _s2wa_sc(text):
  """Full small-caps rendering used by the WhatsApp panel (like the demo)."""
  try:
    return _button_font(str(text).lower())
  except Exception:
    return str(text)


_S2WA_RULE = "\u2500" * 18


def _s2wa_head(title):
  return "\u2726 %s \u2726" % _s2wa_sc(title)


async def _s2wa_send(event, text, buttons=None):
  # NOTE: intentionally NOT passed through custom_emoji_text() so the panel
  # keeps its emoji decorations (the demo look). Buttons still get their
  # custom-emoji icons from the global Button proxy. One rejected ID must not
  # disable custom emoji globally for all future panels.
  text = emoji_to_custom(text)
  bodies = [text]
  if "<tg-emoji" in str(text):
    bodies.append(strip_custom_emoji(text))
  for idx, body in enumerate(bodies):
    try:
      await event.edit(body, buttons=buttons, parse_mode="html")
      return
    except MessageNotModifiedError:
      return
    except Exception as ex:
      logger.warning("s2wa edit failed (try %s): %s", idx, ex)
  for idx, body in enumerate(bodies):
    try:
      await event.respond(body, buttons=buttons, parse_mode="html")
      return
    except Exception as ex:
      logger.warning("s2wa send failed (try %s): %s", idx, ex)


async def _s2wa_answer(event, text=None, alert=False):
  try:
    await safe_callback_answer(event, text or "", alert=alert)
  except Exception:
    pass


def _s2wa_back_row():
  return [Button.inline("Back to Store", "s2wa_store")]


def _s2wa_available():
  """List of countries that currently have a WhatsApp offer (cost > 0).

  Sold-out countries (count == 0) are hidden, but if the provider does not
  report stock at all we fall back to the full priced list so the screen is
  never empty.
  """
  countries = _s2wa_countries()
  pmap = _s2wa_prices_map()
  in_stock = []
  out_of_stock = []
  for c in countries:
    try:
      pr = pmap.get(int(c["id"]))
    except Exception:
      pr = None
    if not pr or pr[0] <= 0:
      continue
    item = {"id": int(c["id"]), "name": c["name"], "flag": c["flag"],
            "code": c.get("code") or _s2wa_iso_from_flag(c.get("flag")),
            "cost": pr[0], "count": pr[1]}
    if pr[1] > 0:
      in_stock.append(item)
    else:
      out_of_stock.append(item)
  return in_stock if in_stock else out_of_stock


def _s2wa_human_error(ex):
  s = str(ex)
  if "BAD_KEY" in s:
    return "Invalid API key. Please contact the admin."
  if "BAD_SERVICE" in s:
    return "WhatsApp is not available at the provider."
  if "NO_BALANCE" in s:
    return "Provider balance is empty. Please contact the admin."
  if "NO_NUMBERS" in s:
    return "No numbers are available right now. Please try again later."
  if "NO_PRICES" in s:
    return "The price list could not be loaded. Please try again later."
  if "NET:" in s:
    return "Network error. Please try again later."
  return "Error: %s" % s


# ---- screens ---------------------------------------------------------------
async def _s2wa_home(event, uid):
  if not _s2wa_enabled() and not is_admin(uid):
    await _s2wa_answer(event, "Server 2 is currently disabled.", alert=True)
    return
  if not _s2wa_api_key():
    if uid == ADMIN_ID:
      await _s2wa_send(
        event,
        "\u26a0\ufe0f <b>%s</b>\n\n%s\n\n%s\n<code>/s2wa_key &lt;your_32_char_key&gt;</code>"
        % (_s2wa_sc("Server 2 WhatsApp Accounts"),
           _s2wa_sc("API key is not set."),
           _s2wa_sc("Set it with:")),
        buttons=[_s2wa_back_row()],
      )
    else:
      await _s2wa_answer(event, "Server 2 is not available right now.", alert=True)
    return

  country_count = "\u2014"
  try:
    country_count = str(len(await asyncio.to_thread(_s2wa_available)))
  except Exception:
    country_count = "\u2014"

  text = (
    "\U0001F310 <b>%s</b>\n\n"
    "%s\n"
    "\u25b8 %s : \u20b9%.2f\n"
    "\u25b8 %s : %s %s\n"
    "\u25b8 %s : %.0f%%\n\n"
    "\U0001F680 %s"
  ) % (
    _s2wa_sc("Server 2 \u2022 WhatsApp Accounts"),
    _s2wa_head("WhatsApp OTP Number Store"),
    _s2wa_sc("Wallet"), _s2wa_wallet(uid),
    _s2wa_sc("Stock"), country_count, _s2wa_sc("Countries"),
    _s2wa_sc("Markup"), _s2wa_margin(),
    _s2wa_sc("Instant Delivery \u2022 24\u00d77"),
  )
  rows = [
    [Button.inline("Buy WhatsApp Number", "s2wa_countries")],
    [Button.inline("My Orders", "cb_orders"), Button.inline("Refresh", "s2wa_home")],
  ]
  if uid == ADMIN_ID:
    rows.append([Button.inline("Provider Balance", "s2wa_balance")])
  rows.append([Button.inline("Back to Store", "s2wa_store")])
  await _s2wa_send(event, text, buttons=rows)


async def _s2wa_countries_screen(event, uid, page=0):
  try:
    available = await asyncio.to_thread(_s2wa_available)
  except Exception as ex:
    await _s2wa_send(
      event,
      "\u274c <b>%s</b>\n\n%s\n\n<code>%s</code>"
      % (_s2wa_sc("Country Fetch Failed"), _s2wa_sc(_s2wa_human_error(ex)),
         html.escape(str(ex))[:120]),
      buttons=[[Button.inline("Try Again", "s2wa_countries")], _s2wa_back_row()],
    )
    return
  if not available:
    await _s2wa_send(
      event,
      "\u274c <b>%s</b>\n\n%s"
      % (_s2wa_sc("No Country Available"),
         _s2wa_sc("No WhatsApp numbers are available right now.")),
      buttons=[[Button.inline("Try Again", "s2wa_countries")], _s2wa_back_row()],
    )
    return

  per = 8
  pages = (len(available) + per - 1) // per
  page = max(0, min(page, pages - 1))
  chunk = available[page * per:(page + 1) * per]

  rows = []
  country_lines = []
  for c in chunk:
    price = _s2wa_sell_price(c["cost"])
    country_lines.append(
      "%s <b>%s</b> \u2014 \u20b9%.0f \u2022 %s %s"
      % (_s2wa_flag_html(c), html.escape(str(c["name"])), price,
         c["count"], _s2wa_sc("in stock")))
    rows.append([Button.inline(
      "%s \u2022 \u20b9%.0f \u2022 Stock %s" % (c["name"], price, c["count"]),
      "s2wa_c:%s" % c["id"],
      icon_custom_emoji_id=_s2wa_flag_icon(c))])

  nav = []
  if page > 0:
    nav.append(Button.inline("Prev", "s2wa_countries:%s" % (page - 1)))
  nav.append(Button.inline("%s/%s" % (page + 1, pages), "s2wa_noop"))
  if page < pages - 1:
    nav.append(Button.inline("Next", "s2wa_countries:%s" % (page + 1)))
  rows.append(nav)
  rows.append([Button.inline("Search Country", "s2wa_csearch")])
  rows.append([Button.inline("My Orders", "cb_orders")])
  rows.append([Button.inline("Home", "s2wa_home"), Button.inline("Back", "s2wa_store")])

  text = (
    "%s <b>%s</b>\n\n"
    "%s\n"
    "%s\n"
    "\u25b8 %s : \u20b9%.2f\n"
    "\u25b8 %s : %s\n"
    "\u25b8 %s : %s\n\n"
    "%s\n\n"
    "%s"
  ) % (
    P_GLOBE, _s2wa_sc("Choose Country"),
    _s2wa_head("WhatsApp OTP Numbers"),
    _S2WA_RULE,
    _s2wa_sc("Wallet"), _s2wa_wallet(uid),
    _s2wa_sc("Available Countries"), len(available),
    _s2wa_sc("Markup"), ("%.0f%%" % _s2wa_margin()),
    "\n".join(country_lines),
    _s2wa_sc("Tap a country to see details"),
  )
  await _s2wa_send(event, text, buttons=rows)


# ---- Country search for Server 2 (WhatsApp) and Server 3 (All App OTP) ----
_COUNTRY_SEARCH_WAIT = {}


async def _country_search_prompt(event, uid, srv, code, back_cb):
  _COUNTRY_SEARCH_WAIT[uid] = {"srv": srv, "code": code, "ts": time.time()}
  await _s2wa_send(
    event,
    "\U0001F50E <b>%s</b>\n\n%s" % (
      _s2wa_sc("Search Country"),
      _s2wa_sc("Send a country name, ISO code or dial code (example: india, IN, +91, 91).")),
    buttons=[[Button.inline("Cancel", back_cb)]])


def _country_search_hits(items, query):
  """Match a country by name, ISO code, alias (usa/uae/uk) or DIAL CODE (+91, 91, 9198...)."""
  q = str(query or "").strip().lower().lstrip("+").strip()
  if not q:
    return []
  q_digits = re.sub(r"[\s\-()]", "", q)
  hits, seen = [], set()

  def _add(c):
    k = id(c)
    if k not in seen:
      seen.add(k)
      hits.append(c)

  if q_digits.isdigit():
    exact, pref, part = [], [], []
    for c in items or []:
      d = country_dial_code(c.get("code"), c.get("name"))
      if not d:
        continue
      if d == q_digits:
        exact.append(c)
      elif q_digits.startswith(d):
        pref.append((len(d), c))
      elif len(q_digits) >= 2 and d.startswith(q_digits):
        part.append(c)
    pref.sort(key=lambda x: -x[0])
    for c in exact + [c for _, c in pref] + part:
      _add(c)
    return hits[:20]

  alias_iso = (country_code_from_name(q) or "").lower()
  first, rest = [], []
  for c in items or []:
    name = str(c.get("name") or "").lower()
    ccode = str(c.get("code") or "").lower()
    if q == ccode or (alias_iso and alias_iso == ccode) or q == name:
      first.append(c)
    elif name.startswith(q):
      first.append(c)
    elif q in name:
      rest.append(c)
  for c in first + rest:
    _add(c)
  return hits[:20]


async def _country_search_build(srv, code, query):
  """Return (text, buttons) for a country search on Server 2 or Server 3."""
  if srv == "s2wa":
    items = await asyncio.to_thread(_s2wa_available)
    price_of = _s2wa_sell_price
    item_cb = lambda c: "s2wa_c:%s" % c["id"]
    back_cb, again_cb = "s2wa_countries:0", "s2wa_csearch"
  else:
    items = await asyncio.to_thread(_s3_available, code)
    price_of = _s3_sell_price
    item_cb = lambda c: "s3_c:%s:%s" % (code, c["id"])
    back_cb, again_cb = "s3_cs:%s:0" % code, "s3_csearch:%s" % code
  hits = _country_search_hits(items, query)
  if not hits:
    return (
      "\u274c <b>%s</b>\n\n%s <code>%s</code>" % (
        _s2wa_sc("No country found"), _s2wa_sc("Nothing matched"),
        html.escape(str(query))[:60]),
      [[Button.inline("Search Again", again_cb)], [Button.inline("Back", back_cb)]])
  rows = []
  for c in hits:
    rows.append([Button.inline(
      "%s \u2022 \u20b9%.0f" % (str(c["name"])[:22], price_of(c["cost"])),
      item_cb(c), icon_custom_emoji_id=_s2wa_flag_icon(c))])
  rows.append([Button.inline("Search Again", again_cb)])
  rows.append([Button.inline("Back", back_cb)])
  text = "\U0001F50E <b>%s</b>\n\n%s" % (_s2wa_sc("Search results"), _s2wa_sc("Tap a country"))
  return text, rows


@bot.on(events.NewMessage())
async def _country_search_message(event):
  """Text typed after tapping 'Search Country' on Server 2 or Server 3."""
  try:
    uid = event.sender_id
    st = _COUNTRY_SEARCH_WAIT.get(uid) if uid else None
    if not st:
      return
    text = (event.raw_text or "").strip()
    if not text or text.startswith("/"):
      return
    _COUNTRY_SEARCH_WAIT.pop(uid, None)
    if time.time() - st.get("ts", 0) > 300:
      return
    status = await _search_status_send(event, "Searching...")
    if status is not None:
      await asyncio.sleep(0.35)
      await _search_status_set(status, "Loading...")
    msg, rows = await _country_search_build(st["srv"], st.get("code", ""), text)
    await _search_status_finish(event, status, msg, rows)
  except Exception as ex:
    logger.warning("country search failed: %s", ex)


async def _s2wa_country_detail(event, uid, country_id):
  try:
    data = await asyncio.to_thread(_s2wa_countries)
    country = next((c for c in data if int(c["id"]) == int(country_id)), None)
    pr = await asyncio.to_thread(_s2wa_price, country_id)
  except Exception as ex:
    await _s2wa_answer(event, _s2wa_human_error(ex), alert=True)
    return
  if not country:
    await _s2wa_answer(event, "Country not found", alert=True)
    return
  if not pr:
    await _s2wa_send(
      event,
      "%s <b>%s</b>\n\n%s"
      % (_s2wa_flag_html(country), _s2wa_sc(country["name"]),
         _s2wa_sc("WhatsApp numbers are not available for this country.")),
      buttons=[[Button.inline("Countries", "s2wa_countries")], _s2wa_back_row()],
    )
    return

  cost, count = pr
  price = _s2wa_sell_price(cost)
  wallet = _s2wa_wallet(uid)
  can_buy = wallet >= price
  retry_txt = "Yes" if str(country.get("retry")) in ("1", "True", "true") else "No"
  text = (
    "%s <b>%s</b>\n\n"
    "%s\n"
    "%s\n"
    "\u25b8 %s : WhatsApp\n"
    "\u25b8 %s : %s\n"
    "\u25b8 %s : %s %s\n"
    "\u25b8 %s : %s\n"
    "\u25b8 %s : %s\n\n"
    "%s"
  ) % (
    _s2wa_flag_html(country), _s2wa_sc(country["name"]),
    _s2wa_head("WhatsApp OTP Number"),
    _S2WA_RULE,
    _s2wa_sc("Service"),
    _s2wa_sc("Country"), _s2wa_sc(country["name"]),
    _s2wa_sc("Stock"), count, _s2wa_sc("Numbers"),
    _s2wa_sc("Retry Code"), _s2wa_sc(retry_txt),
    _s2wa_sc("Delivery"), _s2wa_sc("Instant"),
    ("\u2705 " + _s2wa_sc("Tap Buy Now to get your number")) if can_buy
    else ("\u274c " + _s2wa_sc("Insufficient wallet balance. Please add funds first.")),
  )
  rows = []
  if can_buy:
    rows.append([Button.inline("Buy Now \u2022 \u20b9%.0f" % price, "s2wa_buy:%s" % country_id)])
  rows.append([Button.inline("Refresh", "s2wa_c:%s" % country_id)])
  rows.append([Button.inline("Countries", "s2wa_countries"), Button.inline("Home", "s2wa_home")])
  await _s2wa_send(event, text, buttons=rows)


def _wa_purchase_text(country, gid, phone, price, order_id, code=None):
  """'Number Allocated' card exactly as the buyer saw it when purchasing."""
  if not isinstance(country, dict):
    country = {"name": str(country or "")}
  text = (
    "\u2705 <b>%s</b>\n\n"
    "%s\n"
    "%s\n"
    "\u25b8 %s : %s %s\n"
    "\u25b8 Bot Order ID : <code>%s</code>\n"
    "\u25b8 %s : <code>%s</code>\n"
    "\u25b8 %s : \u20b9%.2f\n"
    "\u25b8 %s : #%s\n"
  ) % (
    _s2wa_sc("Number Allocated"),
    _s2wa_head("WhatsApp OTP Number"),
    _S2WA_RULE,
    _s2wa_sc("Country"), _s2wa_flag_html(country), _s2wa_sc(country.get("name") or ""),
    gid or "-",
    _s2wa_sc("Number"), phone,
    _s2wa_sc("Price"), float(price or 0),
    _s2wa_sc("Order ID"), order_id,
  )
  if code:
    text += "\u25b8 %s : <code>%s</code>\n" % (_s2wa_sc("Code"), html.escape(_otp_gap(code)))
  else:
    text += "\n\u23f3 %s" % _s2wa_sc("Send OTP to this number and tap Get Code")
  return text


# ---- Auto OTP watcher for Server 2 (WhatsApp) and Server 3 (All App OTP) ------------
class _UidEvent:
  """Tiny event stand-in so the existing poll/refund code can post to a user from a
  background task (every 'edit' becomes a fresh message to that user)."""
  def __init__(self, uid):
    self.sender_id = uid
    self.chat_id = uid

  async def edit(self, text, buttons=None, parse_mode="html", **kw):
    return await bot.send_message(self.chat_id, text, buttons=buttons, parse_mode=parse_mode)

  async def respond(self, text, buttons=None, parse_mode="html", **kw):
    return await bot.send_message(self.chat_id, text, buttons=buttons, parse_mode=parse_mode)

  async def answer(self, *a, **kw):
    return None


_OTP_WATCHERS = set()


def _start_otp_watch(uid, act_id, kind):
  key = (kind, str(act_id))
  if key in _OTP_WATCHERS:
    return
  try:
    _spawn_bg(_otp_watch(uid, act_id, kind))
  except Exception as ex:
    logger.warning("otp watcher start failed: %s", ex)


async def _otp_watch(uid, act_id, kind, minutes=20):
  """After a Server 2 / Server 3 purchase: poll the provider and send the user the
  LATEST code the moment it arrives (and any newer retry code), no button needed."""
  key = (kind, str(act_id))
  if key in _OTP_WATCHERS:
    return
  _OTP_WATCHERS.add(key)
  try:
    ev = _UidEvent(uid)
    get_order = _s2wa_get_order if kind == "s2" else _s3_get_order
    poll = _s2wa_poll_code if kind == "s2" else _s3_poll
    first = get_order(act_id) or {}
    last_seen = str(first.get("code") or "")
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
      await asyncio.sleep(5)
      order = get_order(act_id)
      if not order or int(order.get("uid") or 0) != int(uid):
        return
      if str(order.get("status") or "") not in ("WAIT_CODE", "WAIT_RETRY"):
        return
      try:
        async with _watch_sem():
          if kind == "s2":
            raw = str(await asyncio.to_thread(_S2waTiger(_s2wa_api_key()).status, act_id)).strip()
          else:
            raw = str(await asyncio.to_thread(_s3_tiger().status, act_id)).strip()
      except Exception as ex:
        logger.warning("otp watcher status failed (%s %s): %s", kind, act_id, ex)
        continue
      if raw.startswith("STATUS_OK"):
        # code arrived: the poll function stores it, completes the activation and messages the user
        if kind == "s2":
          await poll(ev, uid, act_id, manual=False)
        else:
          await poll(ev, uid, act_id)
        return
      if raw.startswith("STATUS_WAIT_RETRY"):
        code = raw.split(":", 1)[1].strip() if ":" in raw else ""
        if code and code != last_seen:
          last_seen = code
          if kind == "s2":
            await poll(ev, uid, act_id, manual=False)
          else:
            await poll(ev, uid, act_id)
        continue
      if raw.startswith("ACCESS_CANCEL") or raw == "STATUS_CANCEL":
        # provider cancelled / timed out: existing code refunds once and tells the user
        if kind == "s2":
          await poll(ev, uid, act_id, manual=False)
        else:
          await poll(ev, uid, act_id)
        return
  except Exception as ex:
    logger.warning("otp watcher crashed (%s %s): %s", kind, act_id, ex, exc_info=True)
  finally:
    _OTP_WATCHERS.discard(key)


async def _s2wa_buy(event, uid, country_id):
  try:
    data = await asyncio.to_thread(_s2wa_countries)
    country = next((c for c in data if int(c["id"]) == int(country_id)), None)
    pr = await asyncio.to_thread(_s2wa_price, country_id, True)
  except Exception as ex:
    await _s2wa_answer(event, _s2wa_human_error(ex), alert=True)
    return
  if not country or not pr:
    await _s2wa_answer(event, "Not available", alert=True)
    return

  cost, _count = pr
  price = _s2wa_sell_price(cost)
  if _s2wa_wallet(uid) < price:
    await _s2wa_answer(event, "Insufficient balance. You need \u20b9%.2f" % price, alert=True)
    return

  await _s2wa_answer(event, "Allocating your number\u2026")
  service = "wa" if _is_reseller_upstream(2) else _s2wa_resolve_service()
  try:
    if _is_reseller_upstream(2):
      act_id, phone, _oid = await asyncio.to_thread(_reseller_s2_buy, country_id, price)
    else:
      act_id, phone = await asyncio.to_thread(_S2waTiger(_s2wa_api_key()).get_number,
                                              service, country_id, cost)
  except _S2waError as ex:
    await _s2wa_answer(event, _s2wa_human_error(ex), alert=True)
    return

  try:
    update_balance(uid, -price)
  except Exception as ex:
    logger.warning("s2wa wallet debit failed: %s", ex)
  try:
    order_id = _s2wa_new_order(uid, act_id, phone, country["name"], country_id,
                               service, cost, price)
  except Exception as ex:
    logger.warning("s2wa order insert failed: %s", ex)
    order_id = "-"
  wa_global_id = _global_order_register('whatsapp', act_id, uid, price, 'WAIT_CODE') if order_id != "-" else ""
  await log_wa_sale(uid, country, price, phone, act_id, order_id, global_order_id=wa_global_id)

  text = _wa_purchase_text(country, wa_global_id, phone, price, order_id)
  rows = [
    [Button.inline("Get Code", "s2wa_code:%s" % act_id)],
    [Button.inline("Cancel", "s2wa_cancel:%s" % act_id), Button.inline("Home", "s2wa_home")],
  ]
  await _s2wa_send(event, text, buttons=rows)
  if order_id != "-":
    _start_otp_watch(uid, act_id, "s2")


async def _s2wa_poll_code(event, uid, act_id, manual=True):
  order_check = _s2wa_get_order(act_id)
  if not order_check or int(order_check.get("uid") or 0) != int(uid):
    await _s2wa_answer(event, "Order not found", alert=True)
    return
  if manual:
    await _s2wa_answer(event, "Checking\u2026")
  try:
    if _is_reseller_upstream(2):
      raw = await asyncio.to_thread(_reseller_s2_status, act_id)
    else:
      raw = await asyncio.to_thread(_S2waTiger(_s2wa_api_key()).status, act_id)
  except Exception as ex:
    await _s2wa_answer(event, _s2wa_human_error(ex), alert=True)
    return

  order = _s2wa_get_order(act_id) or {}
  phone = order.get("phone", "\u2014")
  country_name = order.get("country_name", "")

  if raw.startswith("STATUS_OK"):
    code = raw.split(":", 1)[1] if ":" in raw else ""
    _s2wa_update_order(act_id, status="DONE", code=code)
    try:
      await asyncio.to_thread(_S2waTiger(_s2wa_api_key()).set_status, act_id, 6)
    except Exception:
      pass
    text = (
      "\U0001F389 <b>%s</b>\n\n"
      "%s\n"
      "\u25b8 %s : <code>%s</code>\n"
      "\u25b8 %s : <code>%s</code>\n"
      "\u25b8 %s : \u2705 %s\n\n"
      "\u2705 %s"
    ) % (
      _s2wa_sc("Code Received"),
      _s2wa_head("WhatsApp OTP Number"),
      _s2wa_sc("Number"), phone,
      _s2wa_sc("Code"), _otp_gap(code),
      _s2wa_sc("Status"), _s2wa_sc("Complete"),
      _s2wa_sc("Order Finished"),
    )
    await _s2wa_send(event, text,
                     buttons=[[Button.inline("Home", "s2wa_home"), Button.inline("Back", "s2wa_store")]])
    return

  if raw.startswith("STATUS_WAIT_RETRY"):
    code = raw.split(":", 1)[1] if ":" in raw else ""
    _s2wa_update_order(act_id, status="WAIT_RETRY", code=code)
    text = (
      "\u26a0\ufe0f <b>%s</b>\n\n"
      "%s\n"
      "\u25b8 %s : <code>%s</code>\n"
      "\u25b8 %s : <code>%s</code>\n\n"
      "%s"
    ) % (
      _s2wa_sc("Retry Code"),
      _s2wa_head("WhatsApp OTP Number"),
      _s2wa_sc("Number"), phone,
      _s2wa_sc("Code"), _otp_gap(code),
      _s2wa_sc("If this code does not work, tap Retry to get a new SMS."),
    )
    await _s2wa_send(event, text, buttons=[
      [Button.inline("Retry", "s2wa_retry:%s" % act_id)],
      [Button.inline("Check Again", "s2wa_code:%s" % act_id),
       Button.inline("Cancel", "s2wa_cancel:%s" % act_id)],
    ])
    return

  if raw in ("ACCESS_CANCEL", "STATUS_CANCEL"):
    try:
      refunded, refund_amount = _s2wa_refund_once(act_id, uid)
    except Exception as ex:
      logger.error("s2wa automatic refund failed for %s: %s", act_id, ex, exc_info=True)
      await _s2wa_send(event, "\u26a0 <b>Activation cancelled, but wallet refund needs admin review.</b>",
                       buttons=[[Button.inline("Home", "s2wa_home")]])
      return
    msg = "\u274c <b>%s</b>" % _s2wa_sc("Activation cancelled")
    if refunded:
      msg += "\n\n\u2705 %s: \u20b9%.2f" % (_s2wa_sc("Refunded to wallet"), refund_amount)
    else:
      msg += "\n\n%s" % _s2wa_sc("No additional refund was issued.")
    await _s2wa_send(event, msg, buttons=[[Button.inline("Home", "s2wa_home")]])
    return

  if raw == "NO_ACTIVATION":
    await _s2wa_send(event, "\u274c <b>%s</b>" % _s2wa_sc("Activation not found (expired?)"),
                     buttons=[[Button.inline("Home", "s2wa_home")]])
    return

  _s2wa_update_order(act_id, status="WAIT_CODE")
  text = (
    "\u23f3 <b>%s</b>\n\n"
    "%s\n"
    "\u25b8 %s : <code>%s</code>\n"
    "\u25b8 %s : %s\n\n"
    "%s"
  ) % (
    _s2wa_sc("Code Not Received Yet"),
    _s2wa_head("WhatsApp OTP Number"),
    _s2wa_sc("Number"), phone,
    _s2wa_sc("Country"), _s2wa_sc(country_name),
    _s2wa_sc("Request the OTP in WhatsApp, then tap Check Again."),
  )
  await _s2wa_send(event, text, buttons=[
    [Button.inline("Check Again", "s2wa_code:%s" % act_id)],
    [Button.inline("Cancel", "s2wa_cancel:%s" % act_id), Button.inline("Home", "s2wa_home")],
  ])


async def _s2wa_retry(event, uid, act_id):
  order = _s2wa_get_order(act_id)
  if not order or int(order.get("uid") or 0) != int(uid):
    await _s2wa_answer(event, "Order not found", alert=True)
    return
  if order.get("status") != "WAIT_RETRY":
    await _s2wa_answer(event, "Retry is not available for this order.", alert=True)
    return
  try:
    await asyncio.to_thread(_S2waTiger(_s2wa_api_key()).set_status, act_id, 3)
  except Exception as ex:
    await _s2wa_answer(event, _s2wa_human_error(ex), alert=True)
    return
  await _s2wa_answer(event, "Retry requested \u2705")
  await _s2wa_poll_code(event, uid, act_id, manual=False)
  _start_otp_watch(uid, act_id, "s2")


async def _s2wa_cancel(event, uid, act_id):
  order = _s2wa_get_order(act_id)
  if not order or int(order.get("uid") or 0) != int(uid):
    await _s2wa_answer(event, "Order not found", alert=True)
    return
  if order.get("status") not in ("WAIT_CODE", "WAIT_RETRY"):
    await _s2wa_answer(event, "This order cannot be cancelled now.", alert=True)
    return
  try:
    raw = await asyncio.to_thread(_S2waTiger(_s2wa_api_key()).set_status, act_id, 8)
  except Exception as ex:
    await _s2wa_answer(event, _s2wa_human_error(ex), alert=True)
    return

  # TigerSMS setStatus(8) confirms cancellation with ACCESS_CANCEL. A code
  # response means the OTP arrived; any other response is NOT proof of cancel.
  if isinstance(raw, str) and raw.startswith("STATUS_OK"):
    code = raw.split(":", 1)[1] if ":" in raw else ""
    _s2wa_update_order(act_id, status="DONE", code=code)
    await _s2wa_answer(event, "The SMS has already arrived — cancellation was not possible.", alert=True)
    await _s2wa_poll_code(event, uid, act_id, manual=False)
    return
  if raw not in ("ACCESS_CANCEL", "STATUS_CANCEL"):
    await _s2wa_answer(event, "Provider did not confirm cancellation (%s). No refund was issued." % str(raw)[:80], alert=True)
    return

  try:
    refunded, price = _s2wa_refund_once(act_id, uid)
  except Exception as ex:
    logger.error("s2wa refund failed for %s: %s", act_id, ex, exc_info=True)
    await _s2wa_answer(event, "Cancellation confirmed, but wallet refund failed. Admin has been notified.", alert=True)
    return
  if not refunded:
    await _s2wa_answer(event, "This order was already refunded or processed.", alert=True)
    return
  text = (
    "\u274c <b>%s</b>\n\n"
    "\u2705 %s : \u20b9%.2f\n"
    "\u25b8 %s : %s"
  ) % (
    _s2wa_sc("Cancelled"),
    _s2wa_sc("Refunded to wallet"), price,
    _s2wa_sc("Status"), _s2wa_sc("Cancellation confirmed by provider"),
  )
  await _s2wa_send(event, text, buttons=[[Button.inline("Buy Again", "s2wa_countries")],
                                         [Button.inline("Home", "s2wa_home")]])


_S2WA_STATUS_LABEL = {
  "DONE": ("\u2705", "Complete"),
  "CANCELLED": ("\u274c", "Cancelled"),
  "WAIT_CODE": ("\u23f3", "Waiting"),
  "WAIT_RETRY": ("\u26a0\ufe0f", "Retry"),
}


async def _s2wa_orders(event, uid):
  rows_data = _s2wa_user_orders(uid, 10)
  if not rows_data:
    await _s2wa_send(
      event,
      "\U0001F4C4 <b>%s</b>\n\n%s" % (_s2wa_sc("My Orders"),
                                     _s2wa_sc("You have no orders yet.")),
      buttons=[[Button.inline("Home", "s2wa_home")], _s2wa_back_row()],
    )
    return

  lines = [
    "\U0001F4C4 <b>%s</b>\n" % _s2wa_sc("My Orders"),
    _s2wa_head("Server 2 \u2022 WhatsApp"),
    "\u25b8 %s : %s %s\n" % (_s2wa_sc("Total"), len(rows_data), _s2wa_sc("Orders")),
  ]
  for o in rows_data:
    st = o.get("status", "")
    icon, label = _S2WA_STATUS_LABEL.get(st, ("\u2022", st.title() if st else "\u2014"))
    lines.append(
      "%s <code>%s</code> \u2022 \u20b9%.2f\n   %s : %s%s"
      % (icon, o.get("phone", "\u2014"), float(o.get("price_inr") or 0),
         _s2wa_sc("Status"), _s2wa_sc(label),
         (" \u2022 %s : <code>%s</code>" % (_s2wa_sc("Code"), _otp_gap(o["code"]))) if o.get("code") else "")
    )
  await _s2wa_send(event, "\n".join(lines),
                   buttons=[[Button.inline("Home", "s2wa_home")], _s2wa_back_row()])


async def _s2wa_balance(event, uid):
  if uid != ADMIN_ID:
    await _s2wa_answer(event, "Admin only", alert=True)
    return
  try:
    bal = await asyncio.to_thread(_S2waTiger(_s2wa_api_key()).balance)
  except Exception as ex:
    await _s2wa_answer(event, _s2wa_human_error(ex), alert=True)
    return
  try:
    rate = float(get_usdt_rate())
  except Exception:
    rate = 94.0
  text = (
    "\U0001F4B3 <b>%s</b>\n\n"
    "%s\n"
    "\u25b8 %s : $%.4f\n"
    "\u25b8 %s : \u20b9%.2f"
  ) % (
    _s2wa_sc("Provider Balance"),
    _s2wa_head("Tiger SMS"),
    _s2wa_sc("USD"), bal,
    _s2wa_sc("INR"), bal * rate,
  )
  await _s2wa_send(event, text,
                   buttons=[[Button.inline("Refresh", "s2wa_balance")],
                            [Button.inline("Home", "s2wa_home")]])


# ---- function management ---------------------------------------------------
_S2WA_FEATURES = [
  ("server1", "Server 1 [ Cheap TG Accounts ]", True),
  ("server2wa", "Server 2 [ WhatsApp Accounts ]", True),
  ("server3otp", "Server 3 [ ALL APP OTP ]", True),
  ("srv3manual", "Server 4 [ Manually Added Accounts ]", True),
  ("shop", "Digital Shop", True),
  ("smm", "Social Media Services", True),
]
_S2WA_FEATURE_META = {k: (lbl, dflt) for (k, lbl, dflt) in _S2WA_FEATURES}


def _fnm_on(key):
  meta = _S2WA_FEATURE_META.get(key)
  if not meta:
    return True
  # backward compatibility: this feature used to be stored as srv2manual
  if key == "srv3manual":
    legacy = str(get_setting("fn_srv2manual", "") or "").strip()
    current = str(get_setting("fn_srv3manual", "") or "").strip()
    if legacy and not current:
      return legacy.lower() == "on"
  return str(get_setting("fn_" + key, "on" if meta[1] else "off")).lower() == "on"


def _fnm_set(key, enabled):
  set_setting("fn_" + key, "on" if enabled else "off")


def _fnm_toggle(key):
  nv = not _fnm_on(key)
  _fnm_set(key, nv)
  return nv


async def _fnm_menu(event, uid):
  if uid != ADMIN_ID:
    await _s2wa_answer(event, "Admin only", alert=True)
    return
  on_count = sum(1 for k, _l, _d in _S2WA_FEATURES if _fnm_on(k))
  lines = [
    "<b>Function Management</b>",
    "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
    "Total: <b>%s</b> \u00b7 ON: <b>%s</b> \u00b7 OFF: <b>%s</b>"
    % (len(_S2WA_FEATURES), on_count, len(_S2WA_FEATURES) - on_count),
    "",
    "Tap a feature to switch it ON or OFF.",
    "When a feature is OFF its button is <b>hidden</b> from the store.",
  ]
  rows = []
  for k, lbl, _d in _S2WA_FEATURES:
    state = _fnm_on(k)
    rows.append([Button.inline("%s \u2014 %s" % (lbl, "ON" if state else "OFF"),
                               "fnmgmt_t:%s" % k)])
  rows.append([Button.inline("Back to Admin", "fnmgmt_back")])
  await _s2wa_send(event, "\n".join(lines), buttons=rows)


async def _fnm_toggle_and_refresh(event, uid, key):
  if uid != ADMIN_ID:
    await _s2wa_answer(event, "Admin only", alert=True)
    return
  if key not in _S2WA_FEATURE_META:
    await _s2wa_answer(event, "Unknown feature", alert=True)
    return
  nv = _fnm_toggle(key)
  await _s2wa_answer(event, "%s: %s" % (_S2WA_FEATURE_META[key][0], "ON \u2705" if nv else "OFF \u274c"), alert=True)
  await _fnm_menu(event, uid)


# ---- dispatchers (called from the main callback router) --------------------
async def _s2wa_dispatch(event, data):
  uid = event.sender_id
  if not _s2wa_enabled() and not is_admin(uid):
    await _s2wa_answer(event, "This feature is currently disabled.", alert=True)
    return
  if not _s2wa_api_key():
    if uid == ADMIN_ID:
      await _s2wa_home(event, uid)
    else:
      await _s2wa_answer(event, "Server 2 is not available right now.", alert=True)
    return
  if data == "s2wa_home":
    await _s2wa_home(event, uid)
  elif data == "s2wa_store":
    await store_servers_menu(event)
  elif data == "s2wa_countries":
    await _s2wa_countries_screen(event, uid, 0)
  elif data.startswith("s2wa_countries:"):
    await _s2wa_countries_screen(event, uid, int(data.split(":", 1)[1]))
  elif data.startswith("s2wa_c:"):
    await _s2wa_country_detail(event, uid, int(data.split(":", 1)[1]))
  elif data.startswith("s2wa_buy:"):
    await _s2wa_buy(event, uid, int(data.split(":", 1)[1]))
  elif data.startswith("s2wa_code:"):
    await _s2wa_poll_code(event, uid, data.split(":", 1)[1])
  elif data.startswith("s2wa_retry:"):
    await _s2wa_retry(event, uid, data.split(":", 1)[1])
  elif data.startswith("s2wa_cancel:"):
    await _s2wa_cancel(event, uid, data.split(":", 1)[1])
  elif data == "s2wa_orders":
    await orders_history_handler(event, is_callback=True)
  elif data == "s2wa_balance":
    await _s2wa_balance(event, uid)
  elif data == "s2wa_csearch":
    await _country_search_prompt(event, uid, "s2wa", "", "s2wa_countries:0")
  elif data == "s2wa_noop":
    await _s2wa_answer(event)
  else:
    await _s2wa_answer(event)


async def _fnm_dispatch(event, data):
  uid = event.sender_id
  if data == "fnmgmt_menu":
    await _fnm_menu(event, uid)
  elif data.startswith("fnmgmt_t:"):
    await _fnm_toggle_and_refresh(event, uid, data.split(":", 1)[1])
  elif data == "fnmgmt_back":
    await admin_panel_handler(event)
  else:
    await _s2wa_answer(event)


# ======================================================================
#  SERVER 3 [ ALL APP OTP ]  -  Tiger SMS API (all services / all countries)
#  API docs: https://tiger-sms.com/api/openapi.json
#  Uses the same transport as Server 2 (_s2wa_http / _S2waTiger).
#  Admin: /s3_key <key>  /s3_margin <pct>  /s3_toggle  /s3_balance
#  If /s3_key is not set, the Server 2 provider key is used (same provider).
# ======================================================================
_S3_K_KEY = "s3_api_key"
_S3_K_MARGIN = "s3_margin"
_S3_K_ENABLED = "s3_enabled"
_S3_DEFAULT_MARGIN = 25.0
_S3_SERVICES_TTL = 6 * 3600
_S3_COUNTRIES_TTL = 6 * 3600
_S3_PRICES_TTL = 120
_S3_SERVICES_PER_PAGE = 12
_S3_COUNTRIES_PER_PAGE = 8
_S3_POPULAR = ["tg", "wa", "ig", "fb", "go", "tw", "ot", "lf", "vi", "ub", "am", "ds"]
_S3_CACHE = {"services": (0, None), "countries": (0, None), "prices": {}}


def _s3_app_logo_id(code, name=""):
  """App-logo premium emoji id for Telegram / WhatsApp / Instagram (None for other apps)."""
  code = str(code or "").lower()
  name = str(name or "").lower()
  if code == "tg" or "telegram" in name:
    return LOGO_TG_ID
  if code == "wa" or "whatsapp" in name:
    return LOGO_WA_ID
  if code == "ig" or "instagram" in name:
    return LOGO_IG_ID
  return None


def _s3_logo_html(code, name=""):
  lid = _s3_app_logo_id(code, name)
  return ('<tg-emoji emoji-id="%s">\u2708\ufe0f</tg-emoji> ' % lid) if lid else ""


def _s3_svc_button(svc):
  return Button.inline(svc["name"][:20], "s3_svc:%s" % svc["code"],
                       icon=_s3_app_logo_id(svc["code"], svc["name"]))
_s3_search_wait = {}


def _s3_url():
  return str(get_setting("s3_api_url", "") or "").strip() or None


def _s3_tiger():
  return _S2waTiger(_s3_key(), _s3_url(), server_no=3)


def _s3_key():
  k = str(get_setting(_S3_K_KEY, "") or "").strip()
  return k or _s2wa_api_key()


def _s3_margin():
  try:
    return float(get_setting(_S3_K_MARGIN, _S3_DEFAULT_MARGIN))
  except Exception:
    return _S3_DEFAULT_MARGIN


def _s3_enabled():
  if str(get_setting(_S3_K_ENABLED, "on")).lower() != "on":
    return False
  return _fnm_on("server3otp")


def _s3_sell_price(cost_usd):
  try:
    rate = float(get_usdt_rate())
  except Exception:
    rate = 94.0
  return round(float(cost_usd) * rate * (1.0 + _s3_margin() / 100.0), 2)


def _s3_services(force=False):
  now = _s2wa_time.time()
  ts, data = _S3_CACHE["services"]
  if not force and data and now - ts < _S3_SERVICES_TTL:
    return data
  if _is_reseller_upstream(3):
    out = _reseller_s3_apps()
    if out:
      _S3_CACHE["services"] = (now, out)
    return out
  raw = _s3_tiger().services()
  out = []
  for s in raw or []:
    try:
      code = str(s.get("code") or "").strip()
      name = str(s.get("name") or code).strip()
      if code and re.fullmatch(r"[A-Za-z0-9_]{1,20}", code):
        out.append({"code": code, "name": name})
    except Exception:
      continue
  out.sort(key=lambda x: x["name"].lower())
  if out:
    _S3_CACHE["services"] = (now, out)
  return out


def _s3_service_name(code):
  try:
    for s in _s3_services():
      if s["code"] == code:
        return s["name"]
  except Exception:
    pass
  return code


def _reseller_s3_countries():
  """Country list for Server 3 via the main Reseller API.

  The Reseller /v1/countries endpoint needs an app code for server 3, so we use
  the first app returned by /v1/apps. Returns the same dict shape as Tiger's
  countries() so the rest of the bot keeps working unchanged.
  """
  service = ""
  try:
    apps = _reseller_s3_apps()
    if apps:
      service = str(apps[0].get("code") or "")
  except Exception:
    service = ""
  if not service:
    return []
  out = []
  for it in _reseller_s3_available(service):
    try:
      out.append({"id": int(it["id"]), "name": it["name"], "flag": it["flag"],
                  "retry": None, "code": it.get("code") or ""})
    except Exception:
      continue
  out.sort(key=lambda x: str(x.get("name") or "").lower())
  return out


def _s3_countries(force=False):
  now = _s2wa_time.time()
  ts, data = _S3_CACHE["countries"]
  if not force and data and now - ts < _S3_COUNTRIES_TTL:
    return data
  if _is_reseller_upstream(3):
    data = _reseller_s3_countries()
  else:
    data = _s3_tiger().countries()
  _S3_CACHE["countries"] = (now, data)
  return data


def _s3_available(code, force=False):
  """Countries that have stock for service `code`, cheapest first."""
  now = _s2wa_time.time()
  ts, cached = _S3_CACHE["prices"].get(code, (0, None))
  if not force and cached is not None and now - ts < _S3_PRICES_TTL:
    return cached
  if _is_reseller_upstream(3):
    items = _reseller_s3_available(code)
    _S3_CACHE["prices"][code] = (now, items)
    return items
  tiger = _s3_tiger()
  pmap = tiger.price_map_v1(code)
  countries = {int(c["id"]): c for c in _s3_countries()}
  items = []
  for cid, node in (pmap or {}).items():
    try:
      info = node.get(code) if isinstance(node, dict) else None
      if not info:
        continue
      cost = float(info.get("cost"))
      count = int(info.get("count", 0))
      c = countries.get(int(cid))
      if cost <= 0 or count <= 0 or not c:
        continue
      items.append({"id": int(cid), "name": c["name"], "flag": c["flag"],
                    "code": c.get("code") or _s2wa_iso_from_flag(c.get("flag")),
                    "cost": cost, "count": count})
    except Exception:
      continue
  items.sort(key=lambda x: (x["cost"], x["name"].lower()))
  _S3_CACHE["prices"][code] = (now, items)
  return items


def _s3_ensure_table():
  cur.execute(
    """
    CREATE TABLE IF NOT EXISTS s3_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid INTEGER NOT NULL,
        activation_id TEXT,
        phone TEXT,
        service_code TEXT,
        service_name TEXT,
        country_name TEXT,
        country_id INTEGER,
        cost_usd REAL,
        price_inr REAL,
        status TEXT,
        code TEXT,
        created_at TEXT,
        updated_at TEXT,
        refunded INTEGER NOT NULL DEFAULT 0
    )
    """
  )
  cur.execute("CREATE INDEX IF NOT EXISTS idx_s3_uid ON s3_orders(uid)")
  cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_s3_act ON s3_orders(activation_id)")
  db.commit()


def _s3_new_order(uid, act_id, phone, svc_code, svc_name, country_name, country_id, cost_usd, price_inr):
  now = _s2wa_datetime.utcnow().isoformat()
  cur.execute(
    "INSERT INTO s3_orders(uid,activation_id,phone,service_code,service_name,country_name,"
    "country_id,cost_usd,price_inr,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
    (uid, str(act_id), phone, svc_code, svc_name, country_name, country_id,
     cost_usd, price_inr, "WAIT_CODE", now, now))
  db.commit()
  return cur.lastrowid


def _s3_get_order(act_id):
  row = cur.execute("SELECT * FROM s3_orders WHERE activation_id=?", (str(act_id),)).fetchone()
  if not row:
    return None
  return dict(zip([d[0] for d in cur.description], row))


def _s3_update_order(act_id, **fields):
  if not fields:
    return
  fields["updated_at"] = _s2wa_datetime.utcnow().isoformat()
  cols = ", ".join("%s=?" % k for k in fields)
  cur.execute("UPDATE s3_orders SET %s WHERE activation_id=?" % cols,
              tuple(fields.values()) + (str(act_id),))
  db.commit()
  if "status" in fields:
    cur.execute("UPDATE global_orders SET status=? WHERE service='s3otp' AND local_ref=?",
                (str(fields["status"]), str(act_id)))
    db.commit()


def _s3_user_orders(uid, limit=10):
  rows = cur.execute("SELECT * FROM s3_orders WHERE uid=? ORDER BY id DESC LIMIT ?",
                     (uid, limit)).fetchall()
  cols = [d[0] for d in cur.description]
  return [dict(zip(cols, r)) for r in rows]


def _s3_refund_once(act_id, uid):
  """Credit the wallet once for an unpaid (waiting) activation. Idempotent."""
  order = _s3_get_order(act_id)
  if not order or int(order.get("uid") or 0) != int(uid):
    return False, 0.0
  price = max(0.0, float(order.get("price_inr") or 0))
  if price <= 0:
    return False, 0.0
  cur.execute(
    "UPDATE s3_orders SET status='CANCELLED', refunded=1, updated_at=? "
    "WHERE activation_id=? AND uid=? AND COALESCE(refunded,0)=0 "
    "AND status IN ('WAIT_CODE','WAIT_RETRY')",
    (_s2wa_datetime.utcnow().isoformat(), str(act_id), int(uid)))
  db.commit()
  if cur.rowcount != 1:
    return False, price
  try:
    update_balance(uid, price)
    cur.execute("UPDATE global_orders SET status='CANCELLED - REFUNDED',refunded=1 "
                "WHERE service='s3otp' AND local_ref=?", (str(act_id),))
    db.commit()
  except Exception:
    cur.execute("UPDATE s3_orders SET refunded=0, status='WAIT_CODE' WHERE activation_id=? AND uid=?",
                (str(act_id), int(uid)))
    db.commit()
    raise
  return True, price


def _s3_human_error(ex):
  s = str(ex)
  if "BAD_KEY" in s or "NO_KEY" in s:
    return "Server 3 API key is invalid or not set. Please contact the admin."
  if "BAD_SERVICE" in s:
    return "This app is not available right now."
  if "BAD_COUNTRY" in s:
    return "This country is not available right now."
  if "NO_BALANCE" in s:
    return "Provider balance is empty. Please contact the admin."
  if "NO_NUMBERS" in s or "NO_PROVIDERS" in s:
    return "No numbers available right now. Please try again later."
  if "WRONG_MAX_PRICE" in s:
    return "Price changed. Please refresh and try again."
  if "Too Many Requests" in s or "HTTP_429" in s:
    return "Too many requests. Please wait a few seconds."
  if "NET:" in s:
    return "Network error. Please try again later."
  return "Error: %s" % s[:100]


def _s3_back_row():
  return [Button.inline("Back to Store", "s3_store")]


# ---- screens ---------------------------------------------------------------
async def _s3_home(event, uid):
  if not _s3_key():
    if uid == ADMIN_ID:
      await _s2wa_send(
        event,
        "\u26a0\ufe0f <b>Server 3 [ ALL APP OTP ]</b>\n\nAPI key is not set.\n"
        "<code>/s3_key &lt;your_32_char_key&gt;</code>",
        buttons=[_s3_back_row()])
    else:
      await _s2wa_answer(event, "Server 3 is not available right now.", alert=True)
    return
  text = "\n".join([
    "\u2726 <b>%s</b> \u2726" % _s2wa_sc("Server 3 \u2022 All App OTP"),
    _S2WA_RULE,
    "\u25b8 %s : \u20b9%.2f" % (_s2wa_sc("Wallet"), _s2wa_wallet(uid)),
    "\u25b8 %s : %.0f%%" % (_s2wa_sc("Markup"), _s3_margin()) if uid == ADMIN_ID else "",
    "",
    "\u26a1 " + _s2wa_sc("Any app \u2022 Any country \u2022 Instant OTP"),
    _s2wa_sc("Pick an app, choose a country and buy a number."),
  ])
  rows = [
    [Button.inline("Browse All Apps", "s3_svcs:0")],
    [Button.inline("Search App", "s3_search")],
    [Button.inline("My Orders", "s3_orders"), Button.inline("Refresh", "s3_home")],
  ]
  if uid == ADMIN_ID:
    rows.append([Button.inline("Provider Balance", "s3_bal")])
  rows.append(_s3_back_row())
  await _s2wa_send(event, text, buttons=rows)


async def _s3_services_screen(event, uid, page=0, query=""):
  try:
    services = await asyncio.to_thread(_s3_services)
  except Exception as ex:
    await _s2wa_send(event, "\u274c <b>%s</b>\n\n%s" % (_s2wa_sc("Apps load failed"), html.escape(_s3_human_error(ex))),
                     buttons=[[Button.inline("Try Again", "s3_svcs:0")], _s3_back_row()])
    return
  q = (query or "").strip().lower()
  if q:
    services = [s for s in services if q in s["name"].lower() or q == s["code"].lower()]
    if not services:
      await _s2wa_send(event, "\u274c <b>%s</b>\n\n%s <code>%s</code>" % (
        _s2wa_sc("No app found"), _s2wa_sc("Nothing matched"), html.escape(q)),
        buttons=[[Button.inline("Search Again", "s3_search")],
                 [Button.inline("Browse All Apps", "s3_svcs:0")], _s3_back_row()])
      return
  pages = max(1, (len(services) + _S3_SERVICES_PER_PAGE - 1) // _S3_SERVICES_PER_PAGE)
  page = max(0, min(int(page), pages - 1))
  rows = []
  if page == 0 and not q:
    pop = [s for code in _S3_POPULAR for s in services if s["code"] == code]
    for i in range(0, len(pop), 2):
      rows.append([_s3_svc_button(s) for s in pop[i:i + 2]])
  chunk = services[page * _S3_SERVICES_PER_PAGE:(page + 1) * _S3_SERVICES_PER_PAGE]
  for i in range(0, len(chunk), 2):
    rows.append([_s3_svc_button(s) for s in chunk[i:i + 2]])
  if not q:
    nav = []
    if page > 0:
      nav.append(Button.inline("Prev", "s3_svcs:%s" % (page - 1)))
    nav.append(Button.inline("%s/%s" % (page + 1, pages), "s3_noop"))
    if page < pages - 1:
      nav.append(Button.inline("Next", "s3_svcs:%s" % (page + 1)))
    rows.append(nav)
  rows.append([Button.inline("Search App", "s3_search"), Button.inline("Home", "s3_home")])
  rows.append(_s3_back_row())
  title = "Search: %s" % q if q else "Choose App"
  text = "\n".join([
    "\U0001F4F1 <b>%s</b>" % _s2wa_sc(title),
    _S2WA_RULE,
    "\u25b8 %s : %s" % (_s2wa_sc("Apps"), len(services)),
    "",
    _s2wa_sc("Tap the app you need an OTP for"),
  ])
  await _s2wa_send(event, text, buttons=rows)


async def _s3_countries_screen(event, uid, code, page=0, force=False):
  name = await asyncio.to_thread(_s3_service_name, code)
  try:
    items = await asyncio.to_thread(_s3_available, code, force)
  except Exception as ex:
    await _s2wa_send(event, "\u274c <b>%s</b>\n\n%s" % (_s2wa_sc("Country fetch failed"), html.escape(_s3_human_error(ex))),
                     buttons=[[Button.inline("Try Again", "s3_cs:%s:0" % code)],
                              [Button.inline("Apps", "s3_svcs:0")], _s3_back_row()])
    return
  if not items:
    await _s2wa_send(event, "\u274c <b>%s</b>\n\n%s" % (
      html.escape(name), _s2wa_sc("No numbers available for this app right now.")),
      buttons=[[Button.inline("Refresh", "s3_cs:%s:0:1" % code)],
               [Button.inline("Apps", "s3_svcs:0")], _s3_back_row()])
    return
  pages = max(1, (len(items) + _S3_COUNTRIES_PER_PAGE - 1) // _S3_COUNTRIES_PER_PAGE)
  page = max(0, min(int(page), pages - 1))
  chunk = items[page * _S3_COUNTRIES_PER_PAGE:(page + 1) * _S3_COUNTRIES_PER_PAGE]
  rows, lines = [], []
  for c in chunk:
    price = _s3_sell_price(c["cost"])
    lines.append("%s %s \u2014 \u20b9%.0f (%s)" % (_s2wa_flag_html(c), html.escape(str(c["name"])), price, c["count"]))
    rows.append([Button.inline("%s \u2022 \u20b9%.0f" % (c["name"][:22], price),
                               "s3_c:%s:%s" % (code, c["id"]),
                               icon_custom_emoji_id=_s2wa_flag_icon(c))])
  nav = []
  if page > 0:
    nav.append(Button.inline("Prev", "s3_cs:%s:%s" % (code, page - 1)))
  nav.append(Button.inline("%s/%s" % (page + 1, pages), "s3_noop"))
  if page < pages - 1:
    nav.append(Button.inline("Next", "s3_cs:%s:%s" % (code, page + 1)))
  rows.append(nav)
  rows.append([Button.inline("Search Country", "s3_csearch:%s" % code)])
  rows.append([Button.inline("Refresh", "s3_cs:%s:%s:1" % (code, page)), Button.inline("Apps", "s3_svcs:0")])
  rows.append([Button.inline("Home", "s3_home"), Button.inline("Back", "s3_store")])
  text = "\n".join([
    "\U0001F30D <b>%s</b>" % _s2wa_sc("Choose Country"),
    "%s\u2726 %s \u2726" % (_s3_logo_html(code, name), html.escape(name)),
    _S2WA_RULE,
    "\u25b8 %s : \u20b9%.2f" % (_s2wa_sc("Wallet"), _s2wa_wallet(uid)),
    "\u25b8 %s : %s" % (_s2wa_sc("Countries"), len(items)),
    "",
  ] + lines)
  await _s2wa_send(event, text, buttons=rows)


async def _s3_country_detail(event, uid, code, country_id):
  name = await asyncio.to_thread(_s3_service_name, code)
  try:
    items = await asyncio.to_thread(_s3_available, code, True)
  except Exception as ex:
    await _s2wa_answer(event, _s3_human_error(ex), alert=True)
    return
  c = next((x for x in items if int(x["id"]) == int(country_id)), None)
  if not c:
    await _s2wa_send(event, "\u274c <b>%s</b>" % _s2wa_sc("Out of stock for this country"),
                     buttons=[[Button.inline("Countries", "s3_cs:%s:0" % code)], _s3_back_row()])
    return
  price = _s3_sell_price(c["cost"])
  wallet = _s2wa_wallet(uid)
  can_buy = wallet >= price
  text = "\n".join([
    "%s <b>%s</b>" % (_s2wa_flag_html(c), _s2wa_sc(c["name"])),
    "\u2726 %s \u2726" % html.escape(name),
    _S2WA_RULE,
    "\u25b8 %s : %s" % (_s2wa_sc("App"), html.escape(name)),
    "\u25b8 %s : %s" % (_s2wa_sc("Stock"), c["count"]),
    "\u25b8 %s : \u20b9%.2f" % (_s2wa_sc("Price"), price),
    "\u25b8 %s : \u20b9%.2f" % (_s2wa_sc("Wallet"), wallet),
    "",
    ("\u2705 " + _s2wa_sc("Tap Buy Now to get your number")) if can_buy
    else ("\u274c " + _s2wa_sc("Insufficient wallet balance. Please add funds first.")),
  ])
  rows = []
  if can_buy:
    rows.append([Button.inline("Buy Now \u2022 \u20b9%.0f" % price, "s3_buy:%s:%s" % (code, c["id"]))])
  rows.append([Button.inline("Refresh", "s3_c:%s:%s" % (code, c["id"]))])
  rows.append([Button.inline("Countries", "s3_cs:%s:0" % code), Button.inline("Home", "s3_home")])
  await _s2wa_send(event, text, buttons=rows)


async def _s3_buy(event, uid, code, country_id):
  name = await asyncio.to_thread(_s3_service_name, code)
  try:
    items = await asyncio.to_thread(_s3_available, code, True)
  except Exception as ex:
    await _s2wa_answer(event, _s3_human_error(ex), alert=True)
    return
  c = next((x for x in items if int(x["id"]) == int(country_id)), None)
  if not c:
    await _s2wa_answer(event, "Not available right now", alert=True)
    return
  cost = c["cost"]
  price = _s3_sell_price(cost)
  if _s2wa_wallet(uid) < price:
    await _s2wa_answer(event, "Insufficient balance. You need \u20b9%.2f" % price, alert=True)
    return
  await _s2wa_answer(event, "Allocating your number\u2026")
  # Debit first, refund on provider failure (a user can never get a free number).
  try:
    update_balance(uid, -price)
  except Exception as ex:
    logger.warning("s3 wallet debit failed: %s", ex)
    await _s2wa_answer(event, "Wallet error. Please try again.", alert=True)
    return
  try:
    act_id, phone = await asyncio.to_thread(_s3_tiger().get_number, code, country_id, cost)
  except Exception as ex:
    try:
      update_balance(uid, price)
    except Exception as rex:
      logger.error("s3 refund after failed purchase failed uid=%s price=%s: %s", uid, price, rex, exc_info=True)
    await _s2wa_answer(event, _s3_human_error(ex), alert=True)
    return
  try:
    order_id = _s3_new_order(uid, act_id, phone, code, name, c["name"], country_id, cost, price)
  except Exception as ex:
    logger.error("s3 order insert failed: %s", ex, exc_info=True)
    order_id = "-"
  gid = _global_order_register("s3otp", act_id, uid, price, "WAIT_CODE") if order_id != "-" else ""
  try:
    await log_s3_sale(uid, name, code, c, phone, price, act_id, order_id, global_order_id=gid)
  except Exception as ex:
    logger.warning("s3 sale log failed: %s", ex)
  try:
    await notify_admins(
      "\U0001F6D2 <b>SERVER 3 OTP PURCHASED</b>\n\n"
      "User: <code>%s</code>\nApp: %s\nCountry: %s\nNumber: <code>%s</code>\n"
      "Paid: \u20b9%.2f (cost $%.4f)\nBot Order ID: <code>%s</code>\nActivation: <code>%s</code> | Order #%s"
      % (uid, html.escape(name), html.escape(str(c["name"])), html.escape(str(phone)),
         price, cost, html.escape(str(gid or "-")), html.escape(str(act_id)), order_id))
  except Exception as ex:
    logger.warning("s3 admin notify failed: %s", ex)
  text = "\n".join([
    "\u2705 <b>%s</b>" % _s2wa_sc("Number Allocated"),
    "\u2726 %s \u2726" % html.escape(name),
    _S2WA_RULE,
    "\u25b8 %s : %s %s" % (_s2wa_sc("Country"), _s2wa_flag_html(c), html.escape(str(c["name"]))),
    "\u25b8 %s : <code>%s</code>" % (_s2wa_sc("Number"), html.escape(str(phone))),
    "\u25b8 %s : \u20b9%.2f" % (_s2wa_sc("Price"), price),
    "\u25b8 Bot Order ID : <code>%s</code>" % html.escape(str(gid or "-")),
    "\u25b8 %s : #%s" % (_s2wa_sc("Order ID"), order_id),
    "",
    "\u23f3 " + _s2wa_sc("Request the OTP in the app, then tap Get Code"),
  ])
  await _s2wa_send(event, text, buttons=[
    [Button.inline("Get Code", "s3_code:%s" % act_id)],
    [Button.inline("Cancel", "s3_cancel:%s" % act_id), Button.inline("Home", "s3_home")],
  ])
  if order_id != "-":
    _start_otp_watch(uid, act_id, "s3")


async def _s3_poll(event, uid, act_id):
  order = _s3_get_order(act_id)
  if not order or int(order.get("uid") or 0) != int(uid):
    await _s2wa_answer(event, "Order not found", alert=True)
    return
  name = order.get("service_name") or order.get("service_code") or "App"
  phone = order.get("phone") or "-"
  if order.get("status") == "DONE" and order.get("code"):
    await _s2wa_send(event, "\n".join([
      "\u2705 <b>%s</b>" % _s2wa_sc("Code Received"), "\u2726 %s \u2726" % html.escape(name), _S2WA_RULE,
      "\u25b8 %s : <code>%s</code>" % (_s2wa_sc("Number"), html.escape(str(phone))),
      "\u25b8 %s : <code>%s</code>" % (_s2wa_sc("Code"), html.escape(_otp_gap(order["code"]))),
    ]), buttons=[[Button.inline("Home", "s3_home")]])
    return
  if order.get("status") == "CANCELLED":
    await _s2wa_answer(event, "This order was cancelled.", alert=True)
    return
  await _s2wa_answer(event, "Checking\u2026")
  try:
    raw = str(await asyncio.to_thread(_s3_tiger().status, act_id)).strip()
  except Exception as ex:
    await _s2wa_answer(event, _s3_human_error(ex), alert=True)
    return

  if raw.startswith("STATUS_OK:"):
    otp = raw.split(":", 1)[1].strip()
    _s3_update_order(act_id, status="DONE", code=otp)
    try:
      await asyncio.to_thread(_s3_tiger().set_status, act_id, 6)
    except Exception as ex:
      logger.warning("s3 complete setStatus failed: %s", ex)
    await _s2wa_send(event, "\n".join([
      "\u2705 <b>%s</b>" % _s2wa_sc("Code Received"), "\u2726 %s \u2726" % html.escape(name), _S2WA_RULE,
      "\u25b8 %s : <code>%s</code>" % (_s2wa_sc("Number"), html.escape(str(phone))),
      "\u25b8 %s : <code>%s</code>" % (_s2wa_sc("Code"), html.escape(_otp_gap(otp))),
      "\u25b8 %s : %s" % (_s2wa_sc("Status"), _s2wa_sc("Complete")),
    ]), buttons=[[Button.inline("Buy Again", "s3_svcs:0"), Button.inline("Home", "s3_home")]])
    return

  if raw.startswith("STATUS_WAIT_RETRY"):
    otp = raw.split(":", 1)[1].strip() if ":" in raw else ""
    _s3_update_order(act_id, status="WAIT_RETRY", code=otp)
    await _s2wa_send(event, "\n".join([
      "\U0001F501 <b>%s</b>" % _s2wa_sc("Code Received"), "\u2726 %s \u2726" % html.escape(name), _S2WA_RULE,
      "\u25b8 %s : <code>%s</code>" % (_s2wa_sc("Number"), html.escape(str(phone))),
      "\u25b8 %s : <code>%s</code>" % (_s2wa_sc("Code"), html.escape(_otp_gap(otp))),
      "",
      _s2wa_sc("If this code does not work, tap Retry to get a new SMS."),
    ]), buttons=[
      [Button.inline("Retry", "s3_retry:%s" % act_id), Button.inline("Done", "s3_done:%s" % act_id)],
      [Button.inline("Check Again", "s3_code:%s" % act_id)],
    ])
    return

  if raw.startswith("ACCESS_CANCEL") or raw == "STATUS_CANCEL":
    try:
      refunded, amt = _s3_refund_once(act_id, uid)
    except Exception as ex:
      logger.error("s3 auto refund failed %s: %s", act_id, ex, exc_info=True)
      await _s2wa_send(event, "\u26a0 <b>Activation cancelled, but wallet refund needs admin review.</b>",
                       buttons=[[Button.inline("Home", "s3_home")]])
      return
    msg = "\u274c <b>%s</b>" % _s2wa_sc("Activation cancelled")
    msg += ("\n\n\u2705 %s: \u20b9%.2f" % (_s2wa_sc("Refunded to wallet"), amt)) if refunded \
      else "\n\n%s" % _s2wa_sc("No additional refund was issued.")
    await _s2wa_send(event, msg, buttons=[[Button.inline("Home", "s3_home")]])
    return

  if raw.startswith("NO_ACTIVATION"):
    await _s2wa_send(event, "\u274c <b>%s</b>" % _s2wa_sc("Activation not found (expired?)"),
                     buttons=[[Button.inline("Home", "s3_home")]])
    return

  _s3_update_order(act_id, status="WAIT_CODE")
  await _s2wa_send(event, "\n".join([
    "\u23f3 <b>%s</b>" % _s2wa_sc("Code Not Received Yet"), "\u2726 %s \u2726" % html.escape(name), _S2WA_RULE,
    "\u25b8 %s : <code>%s</code>" % (_s2wa_sc("Number"), html.escape(str(phone))),
    "\u25b8 %s : %s" % (_s2wa_sc("Country"), html.escape(str(order.get("country_name") or ""))),
    "",
    _s2wa_sc("Request the OTP in the app, then tap Check Again."),
  ]), buttons=[
    [Button.inline("Check Again", "s3_code:%s" % act_id)],
    [Button.inline("Cancel", "s3_cancel:%s" % act_id), Button.inline("Home", "s3_home")],
  ])


async def _s3_retry(event, uid, act_id):
  order = _s3_get_order(act_id)
  if not order or int(order.get("uid") or 0) != int(uid):
    await _s2wa_answer(event, "Order not found", alert=True)
    return
  if order.get("status") not in ("WAIT_CODE", "WAIT_RETRY"):
    await _s2wa_answer(event, "Retry is not available for this order.", alert=True)
    return
  try:
    await asyncio.to_thread(_s3_tiger().set_status, act_id, 3)
  except Exception as ex:
    await _s2wa_answer(event, _s3_human_error(ex), alert=True)
    return
  _s3_update_order(act_id, status="WAIT_CODE", code="")
  await _s2wa_answer(event, "New SMS requested \u2705")
  await _s3_poll(event, uid, act_id)
  _start_otp_watch(uid, act_id, "s3")


async def _s3_done(event, uid, act_id):
  order = _s3_get_order(act_id)
  if not order or int(order.get("uid") or 0) != int(uid):
    await _s2wa_answer(event, "Order not found", alert=True)
    return
  try:
    await asyncio.to_thread(_s3_tiger().set_status, act_id, 6)
  except Exception as ex:
    logger.warning("s3 done setStatus failed: %s", ex)
  _s3_update_order(act_id, status="DONE")
  await _s3_poll(event, uid, act_id)


async def _s3_cancel(event, uid, act_id):
  order = _s3_get_order(act_id)
  if not order or int(order.get("uid") or 0) != int(uid):
    await _s2wa_answer(event, "Order not found", alert=True)
    return
  if order.get("status") not in ("WAIT_CODE", "WAIT_RETRY"):
    await _s2wa_answer(event, "This order cannot be cancelled now.", alert=True)
    return
  try:
    raw = str(await asyncio.to_thread(_s3_tiger().set_status, act_id, 8)).strip()
  except Exception as ex:
    await _s2wa_answer(event, _s3_human_error(ex), alert=True)
    return
  if raw.startswith("STATUS_OK:") or "EARLY_CANCEL" in raw:
    msg = ("The SMS has already arrived \u2014 cancellation was not possible."
           if raw.startswith("STATUS_OK:") else
           "Provider does not allow cancelling this early. Please wait a minute and try again.")
    await _s2wa_answer(event, msg, alert=True)
    if raw.startswith("STATUS_OK:"):
      _s3_update_order(act_id, status="DONE", code=raw.split(":", 1)[1].strip())
      await _s3_poll(event, uid, act_id)
    return
  if not raw.startswith("ACCESS_CANCEL"):
    await _s2wa_answer(event, "Provider did not confirm cancellation (%s). No refund issued." % raw[:60], alert=True)
    return
  try:
    refunded, amt = _s3_refund_once(act_id, uid)
  except Exception as ex:
    logger.error("s3 refund failed %s: %s", act_id, ex, exc_info=True)
    await _s2wa_answer(event, "Cancelled, but wallet refund failed. Admin has been notified.", alert=True)
    try:
      await notify_admins("\u26a0 Server 3 refund FAILED: user <code>%s</code> activation <code>%s</code>" % (uid, html.escape(str(act_id))))
    except Exception:
      pass
    return
  if not refunded:
    await _s2wa_answer(event, "This order was already refunded or processed.", alert=True)
    return
  await _s2wa_send(event, "\n".join([
    "\u274c <b>%s</b>" % _s2wa_sc("Cancelled"),
    "\u25b8 %s : \u20b9%.2f" % (_s2wa_sc("Refunded to wallet"), amt),
    "\u25b8 %s : %s" % (_s2wa_sc("Status"), _s2wa_sc("Cancellation confirmed by provider")),
  ]), buttons=[[Button.inline("Buy Again", "s3_svcs:0")], [Button.inline("Home", "s3_home")]])


_S3_STATUS_LABEL = {
  "WAIT_CODE": ("\u23f3", "Waiting"), "WAIT_RETRY": ("\U0001F501", "Retry"),
  "DONE": ("\u2705", "Complete"), "CANCELLED": ("\u274c", "Cancelled"),
}


async def _s3_orders(event, uid):
  data = _s3_user_orders(uid, 10)
  if not data:
    await _s2wa_send(event, "\U0001F4C4 <b>%s</b>\n\n%s" % (_s2wa_sc("My Orders"), _s2wa_sc("You have no Server 3 orders yet.")),
                     buttons=[[Button.inline("Home", "s3_home")], _s3_back_row()])
    return
  lines = ["\U0001F4C4 <b>%s</b>" % _s2wa_sc("My Orders"), "\u2726 %s \u2726" % _s2wa_sc("Server 3 \u2022 All App OTP"), ""]
  rows = []
  for o in data:
    st = o.get("status") or ""
    icon, label = _S3_STATUS_LABEL.get(st, ("\u2022", st.title() or "-"))
    lines.append("%s <code>%s</code> \u2022 %s \u2022 %s \u2022 \u20b9%.2f%s" % (
      icon, html.escape(str(o.get("phone") or "-")), html.escape(str(o.get("service_name") or "")),
      html.escape(str(o.get("country_name") or "")), float(o.get("price_inr") or 0),
      (" \u2022 <code>%s</code>" % html.escape(str(o["code"]))) if o.get("code") else ""))
    if st in ("WAIT_CODE", "WAIT_RETRY"):
      rows.append([Button.inline("Check %s" % (o.get("phone") or "")[-6:], "s3_code:%s" % o["activation_id"])])
  rows.append([Button.inline("Home", "s3_home")])
  rows.append(_s3_back_row())
  await _s2wa_send(event, "\n".join(lines), buttons=rows)


async def _s3_balance(event, uid):
  if uid != ADMIN_ID:
    await _s2wa_answer(event, "Admin only", alert=True)
    return
  try:
    bal = await asyncio.to_thread(_s3_tiger().balance)
  except Exception as ex:
    await _s2wa_answer(event, _s3_human_error(ex), alert=True)
    return
  try:
    rate = float(get_usdt_rate())
  except Exception:
    rate = 94.0
  await _s2wa_send(event, "\n".join([
    "\U0001F4B0 <b>%s</b>" % _s2wa_sc("Provider Balance"), "\u2726 %s \u2726" % _s2wa_sc("Tiger SMS \u2022 Server 3"),
    "\u25b8 USD : $%.4f" % bal, "\u25b8 INR : \u20b9%.2f" % (bal * rate),
  ]), buttons=[[Button.inline("Refresh", "s3_bal")], [Button.inline("Home", "s3_home")]])


async def _s3_dispatch(event, data):
  uid = event.sender_id
  if not _s3_enabled() and not is_admin(uid):
    await _s2wa_answer(event, "Server 3 is currently disabled.", alert=True)
    return
  if not _s3_key() and data != "s3_store":
    return await _s3_home(event, uid)
  try:
    if data == "s3_home":
      _s3_search_wait.pop(uid, None)
      await _s3_home(event, uid)
    elif data == "s3_store":
      _s3_search_wait.pop(uid, None)
      await store_servers_menu(event)
    elif data.startswith("s3_svcs:"):
      await _s3_services_screen(event, uid, int(data.split(":", 1)[1]))
    elif data.startswith("s3_csearch:"):
      _code = data.split(":", 1)[1]
      await _country_search_prompt(event, uid, "s3", _code, "s3_cs:%s:0" % _code)
    elif data == "s3_search":
      _s3_search_wait[uid] = time.time()
      await _s2wa_send(event, "\U0001F50E <b>%s</b>\n\n%s" % (
        _s2wa_sc("Search App"), _s2wa_sc("Send the app name (example: telegram, instagram, google).")),
        buttons=[[Button.inline("Cancel", "s3_home")]])
    elif data.startswith("s3_svc:"):
      await _s3_countries_screen(event, uid, data.split(":", 1)[1], 0)
    elif data.startswith("s3_cs:"):
      p = data.split(":")
      await _s3_countries_screen(event, uid, p[1], int(p[2]) if len(p) > 2 else 0, force=(len(p) > 3))
    elif data.startswith("s3_c:"):
      p = data.split(":")
      await _s3_country_detail(event, uid, p[1], int(p[2]))
    elif data.startswith("s3_buy:"):
      p = data.split(":")
      await _s3_buy(event, uid, p[1], int(p[2]))
    elif data.startswith("s3_code:"):
      await _s3_poll(event, uid, data.split(":", 1)[1])
    elif data.startswith("s3_retry:"):
      await _s3_retry(event, uid, data.split(":", 1)[1])
    elif data.startswith("s3_done:"):
      await _s3_done(event, uid, data.split(":", 1)[1])
    elif data.startswith("s3_cancel:"):
      await _s3_cancel(event, uid, data.split(":", 1)[1])
    elif data == "s3_orders":
      await _s3_orders(event, uid)
    elif data == "s3_bal":
      await _s3_balance(event, uid)
    else:
      await _s2wa_answer(event)
  except events.StopPropagation:
    raise
  except Exception as ex:
    logger.error("s3 dispatch %r failed: %s", data, ex, exc_info=True)
    await _s2wa_answer(event, "Something went wrong. Please try again.", alert=True)


@bot.on(events.NewMessage())
async def _s3_search_message(event):
  """Text typed after tapping 'Search App' on Server 3."""
  try:
    uid = event.sender_id
    if not uid or uid not in _s3_search_wait:
      return
    text = (event.raw_text or "").strip()
    if not text or text.startswith("/"):
      return
    if time.time() - _s3_search_wait.get(uid, 0) > 300:
      _s3_search_wait.pop(uid, None)
      return
    _s3_search_wait.pop(uid, None)
    if not _s3_enabled() and not is_admin(uid):
      return
    services = await asyncio.to_thread(_s3_services)
    q = text.lower()
    hits = [s for s in services if q in s["name"].lower() or q == s["code"].lower()][:20]
    if not hits:
      await event.respond("\u274c <b>%s</b>" % _s2wa_sc("No app found"), parse_mode="html",
                          buttons=[[Button.inline("Search Again", "s3_search")],
                                   [Button.inline("Browse All Apps", "s3_svcs:0")]])
      return
    rows = []
    for i in range(0, len(hits), 2):
      rows.append([Button.inline(s["name"][:20], "s3_svc:%s" % s["code"]) for s in hits[i:i + 2]])
    rows.append([Button.inline("Home", "s3_home")])
    await event.respond("\U0001F50E <b>%s</b>\n\n%s" % (_s2wa_sc("Search results"), _s2wa_sc("Tap an app")),
                        parse_mode="html", buttons=rows)
  except Exception as ex:
    logger.warning("s3 search failed: %s", ex)


@bot.on(events.NewMessage(pattern=r"(?i)^/s3_(\w*)(?:@\w+)?(?:\s+.*)?$"))
async def _s3_admin_commands(event):
  try:
    uid = event.sender_id
    if not uid or uid != ADMIN_ID:
      return
    parts = (event.raw_text or "").strip().split(maxsplit=1)
    cmd = parts[0].split("@")[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    if cmd == "/s3_key":
      if not arg:
        k = _s3_key()
        await event.reply("Server 3 key: <code>%s</code>\nUsage: /s3_key &lt;key&gt;\n(Empty = uses Server 2 key)"
                          % (("%s\u2026%s" % (k[:4], k[-4:])) if k else "(none)"), parse_mode="html")
        return
      set_setting(_S3_K_KEY, arg)
      _S3_CACHE["services"] = (0, None)
      _S3_CACHE["countries"] = (0, None)
      _S3_CACHE["prices"] = {}
      await event.reply("\u2705 Server 3 API key saved.")
    elif cmd == "/s3_margin":
      try:
        set_setting(_S3_K_MARGIN, float(arg))
        await event.reply("\u2705 Server 3 margin: %s%%" % float(arg))
      except Exception:
        await event.reply("Current margin: %s%%\nUsage: /s3_margin 25" % _s3_margin())
    elif cmd == "/s3_toggle":
      on = str(get_setting(_S3_K_ENABLED, "on")).lower() == "on"
      set_setting(_S3_K_ENABLED, "off" if on else "on")
      await event.reply("Server 3 is now %s" % ("OFF" if on else "ON"))
    elif cmd == "/s3_balance":
      try:
        bal = await asyncio.to_thread(_s3_tiger().balance)
        await event.reply("Provider balance: $%.4f" % bal)
      except Exception as ex:
        await event.reply("Error: %s" % _s3_human_error(ex))
    elif cmd == "/s3_refresh":
      _S3_CACHE["services"] = (0, None)
      _S3_CACHE["countries"] = (0, None)
      _S3_CACHE["prices"] = {}
      await event.reply("\u2705 Server 3 cache cleared.")
  except Exception as ex:
    logger.warning("s3 admin command error: %s", ex)


try:
  _s3_ensure_table()
except Exception as _s3_ex:
  logger.warning("s3 table init failed: %s", _s3_ex)


# ---- admin commands --------------------------------------------------------
@bot.on(events.NewMessage(pattern=r"(?i)^/(s2wa_|fn_|s1_secure)(\w*)(?:@\w+)?(?:\s+.*)?$"))
async def _s2wa_admin_commands(event):
  try:
    uid = event.sender_id
    if not uid or uid != ADMIN_ID:
      return
    text = (event.raw_text or "").strip()
    parts = text.split(maxsplit=1)
    cmd = parts[0].split("@")[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "/s2wa_key":
      if not arg:
        await event.reply("Current key: <code>%s</code>\nUsage: /s2wa_key &lt;key&gt;" % (_s2wa_api_key() or "(none)"))
        return
      set_setting(_S2WA_K_KEY, arg)
      _S2WA_CACHE["countries"] = (0, None)
      _S2WA_CACHE["prices"] = {}
      await event.reply("\u2705 Server 2 API key saved.")
    elif cmd == "/s2wa_margin":
      try:
        set_setting(_S2WA_K_MARGIN, float(arg))
        await event.reply("\u2705 Margin set to %s%%" % arg)
      except Exception:
        await event.reply("Current margin: %s%%\nUsage: /s2wa_margin 25" % _s2wa_margin())
    elif cmd == "/s2wa_service":
      if arg:
        set_setting(_S2WA_K_SERVICE, arg)
        _S2WA_CACHE["prices"] = {}
        await event.reply("\u2705 Service code set to <code>%s</code>" % arg)
      else:
        await event.reply("Current service: <code>%s</code>\nUsage: /s2wa_service wa" % _s2wa_service())
    elif cmd == "/s2wa_toggle":
      cur_on = str(get_setting(_S2WA_K_ENABLED, "on")).lower() == "on"
      set_setting(_S2WA_K_ENABLED, "off" if cur_on else "on")
      await event.reply("\u2705 Server 2 %s." % ("disabled" if cur_on else "enabled"))
    elif cmd == "/s1_secure":
      if arg.lower() in ("others", "all", "off"):
        set_setting("s1_secure_mode", arg.lower())
        await event.reply("\u2705 Server 1 session mode set to <b>%s</b>." % arg.lower())
      else:
        await event.reply(
          "Current mode: <b>%s</b>\n\nUsage: <code>/s1_secure others|all|off</code>\n"
          "\u2022 <b>others</b> \u2014 kill other sessions after buy, bot session after code\n"
          "\u2022 <b>all</b> \u2014 kill everything right after buy\n"
          "\u2022 <b>off</b> \u2014 do nothing" % _s1_secure_mode())
    elif cmd == "/s2wa_balance":
      try:
        bal = await asyncio.to_thread(_S2waTiger(_s2wa_api_key()).balance)
        await event.reply("Provider balance: $%.4f" % bal)
      except Exception as ex:
        await event.reply("\u274c %s" % ex)
    elif cmd == "/fn_list":
      lines = ["<b>Features</b>"]
      for k, lbl, _d in _S2WA_FEATURES:
        lines.append("%s <code>%s</code> \u2014 %s" % ("\U0001F7E2" if _fnm_on(k) else "\U0001F534", k, lbl))
      await event.reply("\n".join(lines))
    elif cmd in ("/fn_on", "/fn_off"):
      if arg not in _S2WA_FEATURE_META:
        await event.reply("Usage: %s &lt;key&gt;\nKeys: %s" % (cmd, ", ".join(k for k, _l, _d in _S2WA_FEATURES)))
        return
      _fnm_set(arg, cmd == "/fn_on")
      await event.reply("%s -> %s" % (_S2WA_FEATURE_META[arg][0], "ON" if cmd == "/fn_on" else "OFF"))
  except Exception as ex:
    logger.warning("s2wa admin command error: %s", ex)


try:
  _s2wa_ensure_table()
  # Backfill historical sales so the first All Sales screen includes old orders too.
  for _r in cur.execute("SELECT bot_order_id,user_id,total_price,status FROM smm_orders").fetchall():
    _global_order_register('smm', _r[0], _r[1], _r[2], _r[3] or 'UNKNOWN')
  for _r in cur.execute("SELECT id,user_id,price,otp FROM orders").fetchall():
    _global_order_register('telegram', _r[0], _r[1], _r[2], 'COMPLETED')
  for _r in cur.execute("SELECT order_id,user_id,price,status FROM s2_orders").fetchall():
    _global_order_register('server1', _r[0], _r[1], _r[2], _r[3] or 'UNKNOWN')
  for _r in cur.execute("SELECT activation_id,uid,price_inr,status FROM s2_wa_orders").fetchall():
    _global_order_register('whatsapp', _r[0], _r[1], _r[2], _r[3] or 'UNKNOWN')
  for _r in cur.execute("SELECT id,user_id,price,status FROM shop_orders").fetchall():
    _global_order_register('shop', _r[0], _r[1], _r[2], _r[3] or 'UNKNOWN')
except Exception as _s2wa_ex:
  logger.warning("s2wa/global order table init failed: %s", _s2wa_ex)



@bot.on(events.CallbackQuery)
async def _extra_callback_posthook(e):
  """If a handler finished without replacing the 'Loading...' text, restore a useful screen."""
  try:
    if _LOADING_PENDING.pop((e.chat_id, e.message_id), None) is None:
      return
    m = await bot.get_messages(e.chat_id, ids=e.message_id)
    if m and (m.raw_text or '').startswith('\u23f3 Loading'):
      await bot.edit_message(
        e.chat_id, e.message_id,
        "\u26a0\ufe0f <b>Nothing to show right now.</b>\nPlease go back and try again.",
        buttons=[[Button.inline("Back to Main", "back_main")]], parse_mode='html')
  except Exception as ex:
    logger.debug(f"loading posthook: {ex}")


# ================= API LOW-BALANCE ALERTS + MANAGE CLONED BOTS =================
_BG_TASKS = set()


def _spawn_bg(coro):
  """Run a coroutine in the background without ever raising into the caller."""
  try:
    task = asyncio.get_running_loop().create_task(coro)
  except RuntimeError:
    try:
      coro.close()
    except Exception:
      pass
    return None
  _BG_TASKS.add(task)
  task.add_done_callback(_BG_TASKS.discard)
  return task


# ---------- API low balance alerts ----------
_LOWBAL_DEFAULT = 100.0
_LOWBAL_STATE = {}


def _lowbal_threshold(server_no):
  try:
    raw = get_setting("low_bal_s%s" % int(server_no), "")
    return max(0.0, float(raw)) if str(raw).strip() != "" else _LOWBAL_DEFAULT
  except Exception:
    return _LOWBAL_DEFAULT


def _lowbal_label(server_no):
  thr = _lowbal_threshold(server_no)
  return "OFF" if thr <= 0 else "₹%g" % thr


async def _api_balance_inr(server_no):
  """Current provider balance in INR (None when the server is not configured)."""
  server_no = int(server_no)
  conf = SERVER_DEFS.get(server_no) or {}
  if not conf:
    return None
  if conf.get("kind") == "tiger":
    key = _s2wa_api_key()
    if not key:
      return None
    usd = await asyncio.to_thread(_S2waTiger(key).balance)
    try:
      rate = float(get_usdt_rate())
    except Exception:
      rate = 94.0
    return float(usd) * rate
  if conf.get("kind") == "s3":
    if not _s3_key():
      return None
    usd = await asyncio.to_thread(_s3_tiger().balance)
    try:
      rate = float(get_usdt_rate())
    except Exception:
      rate = 94.0
    return float(usd) * rate
  api_url, api_key = get_server_api_config(server_no)
  if not (api_url and api_key):
    return None
  res = await asyncio.to_thread(fetch_phantom_balance, server_no)
  if isinstance(res, dict) and res.get("ok"):
    return float(res.get("balance"))
  return None


async def _check_api_balance_now(server_no, force=False):
  """Notify the admins when a server's API balance is below the alert limit."""
  try:
    server_no = int(server_no)
    st = _LOWBAL_STATE.setdefault(server_no, {"last_alert": 0.0, "last_check": 0.0, "low": False})
    now = time.time()
    if not force and now - st["last_check"] < 60:
      return
    st["last_check"] = now
    thr = _lowbal_threshold(server_no)
    if thr <= 0:
      st["low"] = False
      return
    bal = await _api_balance_inr(server_no)
    if bal is None:
      return
    if bal >= thr:
      st["low"] = False
      return
    if st["low"] and now - st["last_alert"] < 6 * 3600:
      return
    st["low"] = True
    st["last_alert"] = now
    conf = SERVER_DEFS.get(server_no) or {}
    await notify_admins(
      f"{P_WARN} <b>{html.escape(str(conf.get('name', 'Server')).upper())} API BALANCE LOW</b> {P_WARN}\n\n"
      f"{P_GEAR} <b>{html.escape(str(conf.get('label', 'Server')))}</b>\n"
      f"{P_MONEY} Current balance: <b>₹{bal:.2f}</b>\n"
      f"{P_RATE} Alert limit: <b>₹{thr:g}</b>\n\n"
      f"<i>Recharge the API wallet now, otherwise orders on this server can fail.</i>\n"
      f"{P_TIME} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
  except Exception as ex:
    logger.warning("API balance check failed (server %s): %s", server_no, ex)


async def _api_balance_watcher():
  await asyncio.sleep(60)
  while True:
    try:
      for _n in list(SERVER_DEFS):
        await _check_api_balance_now(_n, force=True)
    except Exception as ex:
      logger.warning("API balance watcher error: %s", ex)
    await asyncio.sleep(300)


async def _lowbal_set(event, uid, chat, action_data):
  try:
    server_no = int(action_data.split("|")[1])
  except Exception:
    return await safe_callback_answer(event, "Invalid server.", alert=True)
  conf = SERVER_DEFS.get(server_no)
  if not conf:
    return await safe_callback_answer(event, "Unknown server.", alert=True)
  await safe_callback_answer(event)
  async with _admin_conversation(chat, timeout=300) as conv:
    try:
      await conv.send_message(custom_emoji_text(
        f"{P_BELL} <b>{conf['name']} — Low Balance Alert</b>\n\n"
        f"Current limit: <b>{_lowbal_label(server_no)}</b>\n"
        f"You get a notification when the API balance falls below this amount (in ₹).\n"
        f"Send a number, or <code>0</code> to turn the alert off.\n\n<i>(Type /cancel to abort)</i>"))
      resp = await conv.get_response()
      raw = (resp.text or "").strip().replace("₹", "").replace(",", "")
      if raw == "/cancel":
        raise ValueError("Cancelled")
      val = float(raw)
      if not (0 <= val <= 10000000):
        raise ValueError("range")
      set_setting("low_bal_s%s" % server_no, "%g" % val)
      _LOWBAL_STATE.pop(server_no, None)
      await conv.send_message(custom_emoji_text(
        f"{P_YES} <b>Low balance alert set to {_lowbal_label(server_no)}</b> for {conf['name']}."))
    except asyncio.TimeoutError:
      return await conv.send_message(custom_emoji_text(f"{P_NO} Timed out. Nothing changed."))
    except ValueError:
      return await conv.send_message(custom_emoji_text(f"{P_NO} Cancelled or invalid number. Nothing changed."))
  _spawn_bg(_check_api_balance_now(server_no, force=True))
  return await admin_server_view(_AdminChatReply(chat, uid), server_no)


# ---------- Manage cloned bots ----------
_CBM_ID_RE = re.compile(r"^\d{5,15}$")
_CBM_PER_PAGE = 8
_CBM_ICON_ON = "5834600569242654097"
_CBM_ICON_OFF = "5834870091325378855"
_CBM_LOG_RE = re.compile(r"^\d{4}-\d\d-\d\d (\d\d:\d\d:\d\d)[,.]\d+ - \S+ - (\w+) - (.*)$")
_CBM_NAME_RE = re.compile(r"[\w .'\-|+!]{2,40}")


def _cbm_dir(bid):
  bid = str(bid or "")
  if not _CBM_ID_RE.match(bid):
    return None
  cdir = os.path.join(CLONES_ROOT, bid)
  return cdir if os.path.isfile(os.path.join(cdir, CLONE_CONFIG_FILE)) else None


def _cbm_cfg(cdir):
  try:
    with open(os.path.join(cdir, CLONE_CONFIG_FILE), "r", encoding="utf-8") as f:
      data = json.load(f)
    return data if isinstance(data, dict) else {}
  except Exception:
    return {}


def _cbm_save_cfg(cdir, cfg):
  path = os.path.join(cdir, CLONE_CONFIG_FILE)
  tmp = path + ".tmp"
  with open(tmp, "w", encoding="utf-8") as f:
    json.dump(cfg, f)
  try:
    os.chmod(tmp, 0o600)
  except Exception:
    pass
  os.replace(tmp, path)


def _cbm_all():
  out = []
  if not os.path.isdir(CLONES_ROOT):
    return out
  for name in sorted(os.listdir(CLONES_ROOT)):
    cdir = _cbm_dir(name)
    if cdir:
      out.append((name, cdir, _cbm_cfg(cdir)))
  return out


def _cbm_title(bid, cfg):
  name = str(cfg.get("store_name") or "").strip()
  uname = str(cfg.get("username") or "").strip()
  return name or (("@" + uname) if uname else str(bid))


def _cbm_fmt_dur(seconds):
  seconds = max(0, int(seconds))
  d, rem = divmod(seconds, 86400)
  h, rem = divmod(rem, 3600)
  m = rem // 60
  if d:
    return "%dd %dh %dm" % (d, h, m)
  if h:
    return "%dh %dm" % (h, m)
  return "%dm" % m


def _cbm_uptime(cdir):
  try:
    return _cbm_fmt_dur(time.time() - os.path.getmtime(os.path.join(cdir, "clone.pid")))
  except Exception:
    return "-"


def _cbm_db_stats(cdir):
  path = os.path.join(cdir, "otp_bot_final.db")
  if not os.path.isfile(path):
    return None
  con = None
  try:
    con = sqlite3.connect(path, timeout=3)
    users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    wallet = con.execute("SELECT COALESCE(SUM(balance),0) FROM users").fetchone()[0] or 0
    try:
      orders = con.execute("SELECT COUNT(*) FROM global_orders").fetchone()[0]
    except Exception:
      orders = 0
    return users, float(wallet), orders
  except Exception:
    return None
  finally:
    if con is not None:
      try:
        con.close()
      except Exception:
        pass


def _cbm_set_stopped(cdir, stopped):
  flag = os.path.join(cdir, "clone.stopped")
  try:
    if stopped:
      with open(flag, "w") as f:
        f.write(str(int(time.time())))
    elif os.path.exists(flag):
      os.remove(flag)
  except Exception:
    pass


def _cbm_kill(cdir):
  """Blocking: stop the clone process (and its children). Run with asyncio.to_thread."""
  running = _clone_is_running(cdir)
  proc = _CLONE_PROCS.pop(cdir, None)
  pid = None
  if proc is not None and proc.poll() is None:
    pid = proc.pid
  if pid is None:
    try:
      with open(os.path.join(cdir, "clone.pid"), "r") as f:
        pid = int(f.read().strip())
    except Exception:
      pid = None
  if running and pid:
    try:
      if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=20)
      else:
        try:
          os.killpg(pid, signal.SIGTERM)
        except Exception:
          os.kill(pid, signal.SIGTERM)
        for _ in range(60):
          if proc is not None:
            if proc.poll() is not None:
              break
          elif not _clone_pid_alive(pid):
            break
          time.sleep(0.1)
        else:
          try:
            os.killpg(pid, signal.SIGKILL)
          except Exception:
            try:
              os.kill(pid, signal.SIGKILL)
            except Exception:
              pass
    except Exception as ex:
      logger.warning("Clone stop failed (%s): %s", cdir, ex)
  if proc is not None:
    try:
      proc.wait(timeout=3)
    except Exception:
      pass
  try:
    os.remove(os.path.join(cdir, "clone.pid"))
  except Exception:
    pass
  return True


async def _cbm_stop(cdir):
  await asyncio.to_thread(_cbm_kill, cdir)
  _cbm_set_stopped(cdir, True)


async def _cbm_wait_online(proc, log_path, off, timeout=45):
  chunk = ""
  for _ in range(timeout):
    await asyncio.sleep(1)
    chunk = _clone_read_log(log_path, off)
    if "BOT STARTED SUCCESSFULLY" in chunk:
      return True, chunk
    if "Start attempt" in chunk or "BOT_TOKEN is invalid" in chunk or proc.poll() is not None:
      return False, chunk
  return None, chunk


async def _cbm_start(cdir, wait=True):
  """Returns (state, log_chunk). state: True online, None still connecting, False failed."""
  if _clone_is_running(cdir):
    return True, ""
  _cbm_set_stopped(cdir, False)
  log_path = os.path.join(cdir, "clone.log")
  off = os.path.getsize(log_path) if os.path.exists(log_path) else 0
  proc = await asyncio.to_thread(_clone_spawn, cdir)
  if not wait:
    return None, ""
  state, chunk = await _cbm_wait_online(proc, log_path, off)
  if state is False:
    try:
      await asyncio.to_thread(_cbm_kill, cdir)
    except Exception:
      pass
    _cbm_set_stopped(cdir, True)
  return state, chunk


def _cbm_scrub(text, cfg):
  text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text or "")
  token = str(cfg.get("bot_token") or "")
  for secret in (token, token.split(":", 1)[-1], str(cfg.get("api_hash") or ""),
                 str(cfg.get("gmail_app_password") or "")):
    if secret and len(secret) > 6:
      text = text.replace(secret, "***")
  return re.sub(r"\d{6,12}:[A-Za-z0-9_-]{30,}", "***", text)


def _cbm_err_tail(chunk, cfg, n=5):
  lines = [ln for ln in _cbm_scrub(chunk, cfg).splitlines() if ln.strip()][-n:]
  return html.escape("\n".join(lines)[-600:] or "No log output.")


def _cbm_drop_sessions(cdir):
  try:
    for fn in os.listdir(cdir):
      if fn.startswith("bot_session_"):
        try:
          os.remove(os.path.join(cdir, fn))
        except Exception:
          pass
  except Exception:
    pass


def _cbm_rename_db(cdir, old_name, new_name):
  path = os.path.join(cdir, "otp_bot_final.db")
  if not os.path.isfile(path):
    return
  con = None
  try:
    con = sqlite3.connect(path, timeout=5)
    olds = {"Aaditya Tg Store"}
    if old_name:
      olds.add(old_name)
    for o in olds:
      con.execute("UPDATE settings SET value=? WHERE key='fampay_name' AND value=?", (new_name, o))
      con.execute("UPDATE settings SET value=? WHERE key='manual_name' AND value=?", (new_name + " Manual", o + " Manual"))
    con.commit()
  except Exception as ex:
    logger.warning("Clone rename db update failed: %s", ex)
  finally:
    if con is not None:
      try:
        con.close()
      except Exception:
        pass


def _cbm_zip_dir(zf, cdir, prefix=""):
  import tempfile
  count = 0
  for root, dirs, files in os.walk(cdir):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for fn in files:
      low = fn.lower()
      if fn in ("clone.pid", "clone.stopped", "clone.log") or low.endswith((".pyc", "-journal", "-shm", "-wal", ".tmp")):
        continue
      full = os.path.join(root, fn)
      arc = os.path.join(prefix, os.path.relpath(full, cdir)).replace("\\", "/")
      tmp_copy = None
      try:
        if low.endswith(".db"):
          fd, tmp_copy = tempfile.mkstemp(suffix=".db")
          os.close(fd)
          src = sqlite3.connect(full, timeout=5)
          dst = sqlite3.connect(tmp_copy)
          try:
            src.backup(dst)
          finally:
            dst.close()
            src.close()
          zf.write(tmp_copy, arc)
        else:
          zf.write(full, arc)
        count += 1
      except Exception as ex:
        logger.warning("Clone backup skipped %s: %s", full, ex)
      finally:
        if tmp_copy:
          try:
            os.remove(tmp_copy)
          except Exception:
            pass
  return count


async def _cbm_send_backup(chat, items, label):
  import tempfile
  stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
  zip_path = os.path.join(tempfile.gettempdir(), "clones_backup_%s_%s.zip" % (label, stamp))

  def _build():
    total = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
      for bid, cdir, _cfg in items:
        total += _cbm_zip_dir(zf, cdir, prefix=(bid if len(items) > 1 else ""))
    return total

  try:
    n_files = await asyncio.to_thread(_build)
    size_mb = os.path.getsize(zip_path) / 1048576.0
    await bot.send_file(
      chat, zip_path, force_document=True,
      caption=custom_emoji_text(
        f"{P_FOLDER} <b>Cloned Bot Backup</b>\n"
        f"{P_DOC} Bots: <b>{len(items)}</b> | Files: <b>{n_files}</b> | {size_mb:.1f} MB\n"
        f"{P_TIME} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"<i>{P_WARN} Contains bot tokens and settings. Keep it private.</i>"))
    return True
  except Exception as ex:
    logger.error("Clone backup failed: %s", ex, exc_info=True)
    try:
      await bot.send_message(chat, custom_emoji_text(f"{P_NO} Backup failed: {html.escape(str(ex))}"))
    except Exception:
      pass
    return False
  finally:
    try:
      os.remove(zip_path)
    except Exception:
      pass


def _cbm_render_logs(cdir, cfg, errors_only=False, budget=3300):
  """Last log lines as custom-emoji rows. Returns (html_rows, shown, total)."""
  path = os.path.join(cdir, "clone.log")
  raw = ""
  try:
    size = os.path.getsize(path)
    with open(path, "rb") as f:
      f.seek(max(0, size - 90000))
      raw = f.read().decode("utf-8", "ignore")
  except Exception:
    raw = ""
  rows = []
  for ln in [x.rstrip() for x in _cbm_scrub(raw, cfg).splitlines() if x.strip()]:
    m = _CBM_LOG_RE.match(ln)
    if m:
      tm, lvl, msg = m.group(1), m.group(2).upper(), m.group(3)
    else:
      tm, lvl, msg = "", "TRACE", ln
    if errors_only and lvl not in ("ERROR", "CRITICAL", "WARNING", "TRACE"):
      continue
    if lvl in ("ERROR", "CRITICAL"):
      icon = P_NO
    elif lvl == "WARNING":
      icon = P_WARN
    elif lvl == "TRACE":
      icon = P_FLAG
    elif "STARTED" in msg or "Logged in" in msg:
      icon = P_YES
    else:
      icon = P_PIN
    text = ((tm + " ") if tm else "") + msg[:180]
    rows.append((icon, text))
  total = len(rows)
  picked, used = [], 0
  for icon, text in reversed(rows):
    if used + len(text) + 3 > budget:
      break
    picked.append(f"{icon} <code>{html.escape(text)}</code>")
    used += len(text) + 3
  picked.reverse()
  return "\n".join(picked), len(picked), total


async def _cbm_menu(event, page=0, note=""):
  items = _cbm_all()
  total = len(items)
  pages = max(1, (total + _CBM_PER_PAGE - 1) // _CBM_PER_PAGE)
  page = max(0, min(int(page), pages - 1))
  running = sum(1 for _b, _d, _c in items if _clone_is_running(_d))
  msg = ((note + "\n\n") if note else "") + (
    f"{P_PC} <b>MANAGE CLONED BOTS</b> {P_CROWN}\n"
    f"────────────────\n\n"
    f"{P_STATS} <b>Total:</b> {total}   {P_ON} <b>Running:</b> {running}   {P_OFF} <b>Stopped:</b> {total - running}\n\n"
    + ("<i>Select a bot to manage it.</i>" if total else "<i>No cloned bots yet. Tap Clone New Bot to create one.</i>"))
  if pages > 1:
    msg += f"\n\n<i>Page {page + 1}/{pages}</i>"
  btns = []
  for bid, cdir, cfg in items[page * _CBM_PER_PAGE:(page + 1) * _CBM_PER_PAGE]:
    on = _clone_is_running(cdir)
    btns.append([Button.inline(_cbm_title(bid, cfg)[:32], f"adm_cbm|view|{bid}",
                               icon_custom_emoji_id=(_CBM_ICON_ON if on else _CBM_ICON_OFF),
                               style=("success" if on else "danger"))])
  if pages > 1:
    nav = []
    if page > 0:
      nav.append(Button.inline("Prev", f"adm_cbm|menu|{page - 1}", style="primary"))
    if page < pages - 1:
      nav.append(Button.inline("Next", f"adm_cbm|menu|{page + 1}", style="primary"))
    if nav:
      btns.append(nav)
  if total:
    btns.append([Button.inline("Start All", "adm_cbm|all|start", style="success"),
                 Button.inline("Restart All", "adm_cbm|all|restart", style="primary")])
    btns.append([Button.inline("Stop All", "adm_cbm|all|stop", style="danger"),
                 Button.inline("Backup All", "adm_cbm|backupall", style="primary")])
  btns.append([Button.inline("Clone New Bot", "adm_clonebot", style="success"),
               Button.inline("Refresh", f"adm_cbm|menu|{page}", style="primary")])
  btns.append([Button.inline("Back to Admin", "adm_adminmain")])
  return await e_edit_or_send(event, custom_emoji_text(msg), btns)


async def _cbm_view(event, bid, note=""):
  cdir = _cbm_dir(bid)
  if not cdir:
    return await e_edit_or_send(
      event, custom_emoji_text(f"{P_NO} <b>Cloned bot not found.</b>"),
      [[Button.inline("Back", "adm_cbm|menu|0", style="primary")]])
  cfg = _cbm_cfg(cdir)
  running = _clone_is_running(cdir)
  stats = await asyncio.to_thread(_cbm_db_stats, cdir)
  uname = str(cfg.get("username") or "")
  lines = []
  if note:
    lines += [note, ""]
  lines += [
    f"{P_PC} <b>{html.escape(_cbm_title(bid, cfg))}</b> {P_CROWN}",
    "────────────────", "",
    f"{P_ON if running else P_OFF} <b>Status:</b> {'Running' if running else 'Stopped'}",
    f"{P_STORE} <b>Store Name:</b> {html.escape(str(cfg.get('store_name') or '-'))}",
    f"{P_TG} <b>Bot:</b> {('@' + html.escape(uname)) if uname else '-'}",
    f"{P_ID} <b>Bot ID:</b> <code>{bid}</code>",
    f"{P_ACC} <b>Owner ID:</b> <code>{html.escape(str(cfg.get('owner_id', '-')))}</code>",
  ]
  if running:
    lines.append(f"{P_TIME} <b>Uptime:</b> {_cbm_uptime(cdir)}")
  lines.append(f"{P_CAL} <b>Created:</b> {html.escape(str(cfg.get('created') or '-'))}")
  if stats:
    lines += [f"{P_USERS} <b>Users:</b> {stats[0]}",
              f"{P_MONEY} <b>Total Wallet:</b> ₹{stats[1]:.2f}",
              f"{P_CART} <b>Orders:</b> {stats[2]}"]
  btns = [
    [Button.inline("Stop", f"adm_cbm|stop|{bid}", style="danger") if running
     else Button.inline("Start", f"adm_cbm|start|{bid}", style="success"),
     Button.inline("Restart", f"adm_cbm|restart|{bid}", style="primary")],
    [Button.inline("View Logs", f"adm_cbm|logs|{bid}|all", style="primary"),
     Button.inline("Backup", f"adm_cbm|backup|{bid}", style="primary")],
    [Button.inline("Change Bot Token", f"adm_cbm|token|{bid}", style="primary"),
     Button.inline("Change Owner ID", f"adm_cbm|owner|{bid}", style="primary")],
    [Button.inline("Rename Store", f"adm_cbm|name|{bid}", style="primary"),
     Button.inline("Change API ID / Hash", f"adm_cbm|api|{bid}", style="primary")],
    [Button.inline("Refresh", f"adm_cbm|view|{bid}", style="primary"),
     Button.inline("Delete Bot", f"adm_cbm|del|{bid}", style="danger")],
    [Button.inline("Back to Cloned Bots", "adm_cbm|menu|0")],
  ]
  return await e_edit_or_send(event, custom_emoji_text("\n".join(lines)), btns)


async def _cbm_logs_view(event, bid, mode="all"):
  cdir = _cbm_dir(bid)
  if not cdir:
    return await safe_callback_answer(event, "Cloned bot not found.", alert=True)
  cfg = _cbm_cfg(cdir)
  errors_only = (mode == "err")
  rows, shown, total = await asyncio.to_thread(_cbm_render_logs, cdir, cfg, errors_only)
  head = (f"{P_DOC} <b>LOGS — {html.escape(_cbm_title(bid, cfg))}</b>\n"
          f"{P_STATS} Showing <b>{shown}</b> of <b>{total}</b> lines"
          f"{' (errors / warnings only)' if errors_only else ''}\n"
          f"{P_TIME} Updated: {datetime.now().strftime('%H:%M:%S')}\n"
          f"────────────────\n")
  body = rows if rows else "<i>No logs yet.</i>"
  btns = [
    [Button.inline("Refresh", f"adm_cbm|logs|{bid}|{mode}", style="primary"),
     Button.inline("All Logs" if errors_only else "Errors Only", f"adm_cbm|logs|{bid}|{'all' if errors_only else 'err'}", style="primary")],
    [Button.inline("Download Log", f"adm_cbm|logfile|{bid}", style="primary"),
     Button.inline("Clear Logs", f"adm_cbm|logclear|{bid}", style="danger")],
    [Button.inline("Back", f"adm_cbm|view|{bid}")],
  ]
  return await e_edit_or_send(event, custom_emoji_text(head + body), btns)


async def _cbm_bulk(kind):
  done = failed = 0
  for bid, cdir, _cfg in _cbm_all():
    try:
      if kind == "start":
        if not _clone_is_running(cdir):
          await _cbm_start(cdir, wait=False)
      elif kind == "stop":
        await _cbm_stop(cdir)
      elif kind == "restart":
        await _cbm_stop(cdir)
        await _cbm_start(cdir, wait=False)
      done += 1
    except Exception as ex:
      failed += 1
      logger.warning("Bulk %s failed for clone %s: %s", kind, bid, ex)
  return done, failed


async def _cbm_edit_conv(event, uid, chat, bid, kind):
  cdir = _cbm_dir(bid)
  if not cdir:
    return await safe_callback_answer(event, "Cloned bot not found.", alert=True)
  await safe_callback_answer(event)
  cfg = _cbm_cfg(cdir)
  title = html.escape(_cbm_title(bid, cfg))
  new_bid = bid
  note = ""
  async with _admin_conversation(chat, timeout=300) as conv:
    async def ask(txt, secret=False):
      await conv.send_message(custom_emoji_text(txt + "\n\n<i>(Type /cancel to abort)</i>"))
      resp = await conv.get_response()
      val = (resp.text or "").strip()
      if secret:
        try:
          await resp.delete()
        except Exception:
          pass
      if val == "/cancel":
        raise ValueError("Cancelled")
      return val

    try:
      if kind == "owner":
        val = await ask(f"{P_ACC} <b>Change Owner ID — {title}</b>\n\nCurrent: <code>{html.escape(str(cfg.get('owner_id', '-')))}</code>\n"
                        f"Send the new <b>Owner Telegram User ID</b> (numbers only).")
        if not re.fullmatch(r"\d{5,15}", val):
          return await conv.send_message(custom_emoji_text(f"{P_NO} <b>Invalid user ID.</b> Nothing changed."))
        was = _clone_is_running(cdir)
        if was:
          await _cbm_stop(cdir)
        cfg["owner_id"] = int(val)
        _cbm_save_cfg(cdir, cfg)
        note = f"{P_YES} <b>Owner ID changed to</b> <code>{val}</code>."
        if was:
          state, chunk = await _cbm_start(cdir)
          if state is False:
            note += f"\n{P_NO} <b>Restart failed:</b>\n<code>{_cbm_err_tail(chunk, cfg)}</code>"
          else:
            note += " Bot restarted."

      elif kind == "name":
        val = re.sub(r"\s+", " ", await ask(
          f"{P_STORE} <b>Rename Store — {title}</b>\n\nCurrent: <b>{html.escape(str(cfg.get('store_name') or '-'))}</b>\n"
          f"Send the new <b>Store Name</b> (example: <code>SHUBHAM TG STORE</code>).")).strip()
        if not _CBM_NAME_RE.fullmatch(val):
          return await conv.send_message(custom_emoji_text(
            f"{P_NO} <b>Invalid store name.</b> Use 2-40 letters, numbers or spaces. Nothing changed."))
        was = _clone_is_running(cdir)
        if was:
          await _cbm_stop(cdir)
        old_name = str(cfg.get("store_name") or "")
        cfg["store_name"] = val
        _cbm_save_cfg(cdir, cfg)
        await asyncio.to_thread(_cbm_rename_db, cdir, old_name, val)
        note = f"{P_YES} <b>Store renamed to</b> {html.escape(val)}."
        if was:
          state, chunk = await _cbm_start(cdir)
          if state is False:
            note += f"\n{P_NO} <b>Restart failed:</b>\n<code>{_cbm_err_tail(chunk, cfg)}</code>"
          else:
            note += " Bot restarted."

      elif kind == "api":
        api_id = await ask(f"{P_GEAR} <b>Change API ID / Hash — {title}</b>\n\nSend the new <b>API ID</b> (from my.telegram.org).")
        if not re.fullmatch(r"\d{4,12}", api_id):
          return await conv.send_message(custom_emoji_text(f"{P_NO} <b>Invalid API ID.</b> Nothing changed."))
        api_hash = await ask(f"{P_KEY} Now send the <b>API Hash</b> (32 characters). Your message is deleted after reading.", secret=True)
        if not re.fullmatch(r"[0-9a-fA-F]{32}", api_hash):
          return await conv.send_message(custom_emoji_text(f"{P_NO} <b>Invalid API Hash.</b> Nothing changed."))
        was = _clone_is_running(cdir)
        if was:
          await _cbm_stop(cdir)
        cfg["api_id"] = int(api_id)
        cfg["api_hash"] = api_hash
        _cbm_save_cfg(cdir, cfg)
        _cbm_drop_sessions(cdir)
        note = f"{P_YES} <b>API ID / Hash updated.</b>"
        if was:
          state, chunk = await _cbm_start(cdir)
          if state is False:
            note += f"\n{P_NO} <b>Restart failed:</b>\n<code>{_cbm_err_tail(chunk, cfg)}</code>"
          else:
            note += " Bot restarted."

      elif kind == "token":
        tok = await ask(f"{P_KEY} <b>Change Bot Token — {title}</b>\n\nSend the NEW bot token (from @BotFather). "
                        f"Your message is deleted right after it is read.", secret=True)
        if not re.fullmatch(r"\d{6,12}:[A-Za-z0-9_-]{30,}", tok):
          return await conv.send_message(custom_emoji_text(f"{P_NO} <b>Invalid bot token.</b> Nothing changed."))
        new_bid = tok.split(":")[0]
        if new_bid == str(BOT_TOKEN).split(":")[0]:
          new_bid = bid
          return await conv.send_message(custom_emoji_text(
            f"{P_NO} This is the main bot's own token. Create a NEW bot in @BotFather."))
        if new_bid != bid and os.path.exists(os.path.join(CLONES_ROOT, new_bid)):
          new_bid = bid
          return await conv.send_message(custom_emoji_text(f"{P_NO} This token already belongs to another cloned bot."))
        ok, uname = await asyncio.to_thread(_clone_check_token, tok)
        if not ok:
          new_bid = bid
          return await conv.send_message(custom_emoji_text(f"{P_NO} {html.escape(uname)}"))
        await conv.send_message(custom_emoji_text(f"{P_WAIT} <b>Applying the new token...</b> (up to 45 seconds)"))
        was = _clone_is_running(cdir)
        await _cbm_stop(cdir)
        old_cfg = dict(cfg)
        new_dir = cdir
        if new_bid != bid:
          new_dir = os.path.join(CLONES_ROOT, new_bid)
          os.rename(cdir, new_dir)
        cfg["bot_token"] = tok
        cfg["username"] = uname
        _cbm_save_cfg(new_dir, cfg)
        _cbm_drop_sessions(new_dir)
        if not was:
          note = (f"{P_YES} <b>Bot token changed</b> (@{html.escape(uname)}). "
                  f"The bot is stopped — tap Start to run it.")
        else:
          state, chunk = await _cbm_start(new_dir)
          if state is False:
            await _cbm_stop(new_dir)
            if new_dir != cdir:
              os.rename(new_dir, cdir)
            _cbm_save_cfg(cdir, old_cfg)
            _cbm_drop_sessions(cdir)
            new_bid = bid
            await _cbm_start(cdir)
            note = (f"{P_NO} <b>New token failed to start. The old token was restored.</b>\n"
                    f"<code>{_cbm_err_tail(chunk, cfg)}</code>")
          else:
            note = f"{P_YES} <b>Bot token changed.</b> Now running as @{html.escape(uname)}."
            if state is None:
              note += f"\n{P_WAIT} <i>Still connecting...</i>"
      else:
        return await conv.send_message(custom_emoji_text(f"{P_NO} Unknown action."))
    except asyncio.TimeoutError:
      return await conv.send_message(custom_emoji_text(f"{P_NO} Timed out. Nothing changed."))
    except ValueError:
      return await conv.send_message(custom_emoji_text(f"{P_NO} Cancelled."))
    except Exception as ex:
      logger.error("Clone manager edit failed: %s", ex, exc_info=True)
      return await conv.send_message(custom_emoji_text(f"{P_NO} Failed: {html.escape(str(ex))}"))
  return await _cbm_view(_AdminChatReply(chat, uid), new_bid, note)


async def _cbm_router(event, uid, chat, action_data):
  if IS_CLONE or uid != ADMIN_ID:
    return await safe_callback_answer(event, "Only the main owner can manage cloned bots.", alert=True)
  parts = action_data.split("|")
  op = parts[1] if len(parts) > 1 else "menu"
  arg = parts[2] if len(parts) > 2 else ""
  extra = parts[3] if len(parts) > 3 else ""
  try:
    if op == "menu":
      await safe_callback_answer(event)
      try:
        page = int(arg or 0)
      except Exception:
        page = 0
      return await _cbm_menu(event, page)

    if op == "all":
      if not _cbm_all():
        return await safe_callback_answer(event, "No cloned bots yet.", alert=True)
      if arg == "stop":
        await safe_callback_answer(event)
        return await e_edit_or_send(
          event, custom_emoji_text(f"{P_WARN} <b>Stop ALL cloned bots?</b>\n\nThey stay stopped until you start them again."),
          [[Button.inline("Yes, Stop All", "adm_cbm|all|stopyes", style="danger")],
           [Button.inline("Cancel", "adm_cbm|menu|0", style="primary")]])
      kind = {"start": "start", "restart": "restart", "stopyes": "stop"}.get(arg)
      if not kind:
        return await safe_callback_answer(event, "Unknown action.", alert=True)
      await safe_callback_answer(event, "Working...")
      done, failed = await _cbm_bulk(kind)
      verb = {"start": "started", "restart": "restarted", "stop": "stopped"}[kind]
      note = f"{P_YES} <b>{done}</b> bot(s) {verb}." + (f"\n{P_NO} <b>{failed}</b> failed." if failed else "")
      if kind != "stop":
        note += "\n<i>They may need up to a minute to come online.</i>"
      return await _cbm_menu(event, 0, note)

    if op == "backupall":
      items = _cbm_all()
      if not items:
        return await safe_callback_answer(event, "No cloned bots yet.", alert=True)
      await safe_callback_answer(event, "Preparing backup...")
      await _cbm_send_backup(chat, items, "all")
      return

    cdir = _cbm_dir(arg)
    if not cdir:
      return await safe_callback_answer(event, "Cloned bot not found.", alert=True)
    cfg = _cbm_cfg(cdir)

    if op == "view":
      await safe_callback_answer(event)
      return await _cbm_view(event, arg)

    if op == "start":
      if _clone_is_running(cdir):
        return await safe_callback_answer(event, "Already running.", alert=True)
      await safe_callback_answer(event, "Starting... please wait")
      state, chunk = await _cbm_start(cdir)
      if state:
        note = f"{P_YES} <b>Started successfully.</b>"
      elif state is None:
        note = f"{P_WAIT} <b>Started.</b> <i>Still connecting, it should be online within a minute.</i>"
      else:
        note = f"{P_NO} <b>Failed to start.</b>\n<code>{_cbm_err_tail(chunk, cfg)}</code>"
      return await _cbm_view(event, arg, note)

    if op == "stop":
      await safe_callback_answer(event, "Stopping...")
      await _cbm_stop(cdir)
      return await _cbm_view(event, arg, f"{P_YES} <b>Bot stopped.</b> It stays stopped until you start it.")

    if op == "restart":
      await safe_callback_answer(event, "Restarting... please wait")
      await _cbm_stop(cdir)
      state, chunk = await _cbm_start(cdir)
      if state:
        note = f"{P_YES} <b>Restarted successfully.</b>"
      elif state is None:
        note = f"{P_WAIT} <b>Restarted.</b> <i>Still connecting, it should be online within a minute.</i>"
      else:
        note = f"{P_NO} <b>Restart failed.</b>\n<code>{_cbm_err_tail(chunk, cfg)}</code>"
      return await _cbm_view(event, arg, note)

    if op == "logs":
      await safe_callback_answer(event)
      return await _cbm_logs_view(event, arg, "err" if extra == "err" else "all")

    if op == "logfile":
      import tempfile
      await safe_callback_answer(event, "Preparing log file...")
      path = os.path.join(cdir, "clone.log")
      if not os.path.isfile(path) or os.path.getsize(path) == 0:
        return await bot.send_message(chat, custom_emoji_text(f"{P_NO} No logs yet."))
      def _build_log():
        size = os.path.getsize(path)
        with open(path, "rb") as f:
          f.seek(max(0, size - 3000000))
          data = f.read().decode("utf-8", "ignore")
        out = os.path.join(tempfile.gettempdir(), "clone_%s_log.txt" % arg)
        with open(out, "w", encoding="utf-8") as g:
          g.write(_cbm_scrub(data, cfg))
        return out
      out_path = await asyncio.to_thread(_build_log)
      try:
        await bot.send_file(chat, out_path, force_document=True,
                            caption=custom_emoji_text(f"{P_DOC} <b>Full log — {html.escape(_cbm_title(arg, cfg))}</b>"))
      finally:
        try:
          os.remove(out_path)
        except Exception:
          pass
      return

    if op == "logclear":
      try:
        open(os.path.join(cdir, "clone.log"), "wb").close()
      except Exception:
        pass
      await safe_callback_answer(event, "Logs cleared.")
      return await _cbm_logs_view(event, arg, "all")

    if op == "backup":
      await safe_callback_answer(event, "Preparing backup...")
      await _cbm_send_backup(chat, [(arg, cdir, cfg)], arg)
      return

    if op == "del":
      await safe_callback_answer(event)
      return await e_edit_or_send(
        event,
        custom_emoji_text(f"{P_WARN} <b>Delete {html.escape(_cbm_title(arg, cfg))}?</b>\n\n"
                          f"The bot is stopped and its database, sessions and settings are deleted permanently. "
                          f"This cannot be undone.\n\n<i>Tip: take a backup first.</i>"),
        [[Button.inline("Backup & Delete", f"adm_cbm|delbk|{arg}", style="success")],
         [Button.inline("Yes, Delete", f"adm_cbm|delyes|{arg}", style="danger")],
         [Button.inline("Cancel", f"adm_cbm|view|{arg}", style="primary")]])

    if op in ("delyes", "delbk"):
      await safe_callback_answer(event, "Deleting...")
      title = _cbm_title(arg, cfg)
      if op == "delbk":
        if not await _cbm_send_backup(chat, [(arg, cdir, cfg)], arg):
          return await _cbm_view(event, arg, f"{P_NO} <b>Backup failed, the bot was NOT deleted.</b>")
      await _cbm_stop(cdir)
      root = os.path.abspath(CLONES_ROOT)
      target = os.path.abspath(cdir)
      if os.path.commonpath([root, target]) != root or target == root:
        return await _cbm_menu(event, 0, f"{P_NO} Unsafe path, nothing deleted.")
      await asyncio.to_thread(shutil.rmtree, target, True)
      _CLONE_PROCS.pop(cdir, None)
      return await _cbm_menu(event, 0, f"{P_YES} <b>{html.escape(title)}</b> was deleted.")

    if op in ("token", "owner", "name", "api"):
      return await _cbm_edit_conv(event, uid, chat, arg, op)

    return await safe_callback_answer(event, "Unknown action.", alert=True)
  except Exception as ex:
    logger.error("Clone manager error: %s", ex, exc_info=True)
    return await safe_callback_answer(event, "Error: %s" % str(ex)[:150], alert=True)


async def main():
  if not IS_CLONE:
    try:
      _autostart_clones()
    except Exception as _acex:
      logger.warning("Clone autostart skipped: %s", _acex)
  try:
    if not get_setting('selling_logs_link', '').strip():
      _lnk = await refresh_selling_logs_link()
      if _lnk:
        logger.info("Selling Logs link generated automatically: %s", _lnk)
  except Exception as _ex:
    logger.warning("Selling Logs link auto-generation skipped: %s", _ex)
  _s1_countries_load_disk()            # instant menu from the last saved list
  _s2_refresh_in_background()          # then refresh it in the background
  _spawn_bg(_api_balance_watcher())
  _redeem_purge_exhausted()
  if not IS_CLONE:
    _spawn_bg(_auto_backup_loop())      # server backup to the OWNER chat every 2 hours
  _spawn_bg(_daily_report_loop())        # nightly sales report to the owner
  print("BOT STARTED SUCCESSFULLY")
  # ---- DIAGNOSTIC: send Telethon info to the admin on Telegram ----
  try:
    import telethon as _tlv2
    _caps = _factory_caps(_ORIGINAL_BUTTON.inline)
    _diag = ("DIAGNOSTIC (fixed file running)\n"
             "Telethon version: %s\n"
             "Path: %s\n"
             "Custom emoji enabled: %s\n"
             "Button style/icon support: %s\n"
             "Python: %s" % (getattr(_tlv2, "__version__", "?"), getattr(_tlv2, "__file__", "?"),
                             CUSTOM_EMOJI_ENABLED, _caps, sys.version.split()[0]))
    _lg = None
    for _lp in (MCUB_LOG, "/tmp/mcub_install.log"):
      try:
        with open(_lp, "r", encoding="utf-8") as _f: _lg = _f.read()[-2500:]
        break
      except Exception:
        continue
    _diag += "\n\n--- MCUB LOG ---\n" + (_lg or "(no log file could be written/read)")
    print(_diag)
    await bot.send_message(ADMIN_ID, _diag, parse_mode=None)
  except Exception as _dex2:
    print("Diagnostic send failed:", _dex2)
  await bot.run_until_disconnected()


def _remove_broken_session():
  for ext in ('.session', '.session-journal', '.session-wal', '.session-shm'):
    try:
      p = session_name + ext
      if os.path.exists(p):
        os.remove(p)
        logger.warning("Removed broken session file %s", p)
    except Exception:
      pass


async def _start_bot_with_retry():
  """Connect + log in the bot. Retries on every transient error so the bot
  starts on the FIRST run instead of crashing and needing a second start."""
  attempt = 0
  while True:
    attempt += 1
    try:
      await bot.start(bot_token=BOT_TOKEN)
      me = await bot.get_me()
      logger.info("Logged in as @%s (attempt %d)", getattr(me, 'username', '?'), attempt)
      _spawn_bg(_prewarm_welcome_media())
      return
    except FloodWaitError as ex:
      wait = int(getattr(ex, 'seconds', 30)) + 2
      logger.warning("FloodWait on start: sleeping %ss", wait)
      await asyncio.sleep(wait)
    except (sqlite3.DatabaseError, ValueError) as ex:
      msg = str(ex).lower()
      if 'locked' in msg:
        logger.error("Session DB is locked - another copy of the bot is still running. "
                     "Stop it first. Retrying in 5s...")
        await asyncio.sleep(5)
      else:
        logger.error("Session file problem (%s). Recreating it.", ex)
        try:
          await bot.disconnect()
        except Exception:
          pass
        _remove_broken_session()
        await asyncio.sleep(1)
    except Exception as ex:
      if attempt >= 3 and 'token' in str(ex).lower() and ('invalid' in str(ex).lower() or 'access' in str(ex).lower()):
        logger.critical("BOT_TOKEN is invalid/revoked: %s", ex)
        raise
      delay = min(5 * attempt, 60)
      logger.warning("Start attempt %d failed (%s: %s). Retrying in %ss...",
                     attempt, type(ex).__name__, ex, delay)
      try:
        await bot.disconnect()
      except Exception:
        pass
      await asyncio.sleep(delay)


async def _run():
  # API key table must exist in every mode (main + clones), even if the web
  # server fails to bind a port. Generated keys are stored in this database.
  try:
    _api_init_tables()
  except Exception as _ex:
    logger.error("api_keys table init failed: %s", _ex, exc_info=True)
  await _start_reseller_api()
  await _start_bot_with_retry()
  await main()



# ============================================================================
# RESELLER API  (Server 1 Telegram accounts, Server 2 WhatsApp, Server 3 App OTP)
# Same bot, same database, same wallet, same prices as the Telegram bot.
# Served on $PORT together with the docs page ("/").
# Provider names, hosts and raw provider errors are never sent to API clients.
# ============================================================================
import secrets as _api_secrets
from collections import deque as _api_deque
from aiohttp import web as _api_web

API_PORT = int(os.environ.get("PORT", "10000"))
API_ORIGIN = os.environ.get("API_ALLOWED_ORIGIN", "*")
API_RATE_LIMIT = 120
_API_RATE = {}
_API_DOCS_FILE = os.path.join(_APP_DIR, "docs-index.html")
_API_SERVER_NAMES = {1: "Cheap TG Accounts", 2: "WhatsApp OTP", 3: "All App OTP"}


class _ApiErr(Exception):
  def __init__(self, status, code, message):
    super().__init__(message)
    self.status = status
    self.code = code
    self.message = message


def _api_init_tables():
  cur.execute(
    "CREATE TABLE IF NOT EXISTS api_keys ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " owner_id INTEGER NOT NULL,"
    " label TEXT DEFAULT '',"
    " prefix TEXT DEFAULT '',"
    " key_hash TEXT UNIQUE NOT NULL,"
    " status TEXT DEFAULT 'active',"
    " expires_at TEXT DEFAULT '',"
    " created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
    " last_used_at TEXT DEFAULT '')")
  try:
    cur.execute("ALTER TABLE api_keys ADD COLUMN raw_key TEXT DEFAULT ''")
  except Exception:
    pass
  db.commit()


def _api_hash(raw_key):
  return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _api_create_key(owner_id, days=30, label=""):
  raw = "ats_" + _api_secrets.token_urlsafe(24)
  exp = (datetime.utcnow() + timedelta(days=int(days))).isoformat()
  sql = ("INSERT INTO api_keys (owner_id, label, prefix, key_hash, status, expires_at, raw_key) "
         "VALUES (?,?,?,?,'active',?,?)")
  args = (int(owner_id), label, raw[:10], _api_hash(raw), exp, raw)
  try:
    cur.execute(sql, args)
  except sqlite3.OperationalError:
    # Table was missing (fresh DB / web server never started): create and retry.
    _api_init_tables()
    cur.execute(sql, args)
  db.commit()
  return raw, cur.lastrowid


def _api_extract_key(request):
  auth = request.headers.get("Authorization", "")
  if auth.lower().startswith("bearer "):
    return auth[7:].strip()
  return (request.headers.get("X-API-Key") or request.query.get("api_key")
          or request.query.get("key") or "").strip()


def _api_auth(request):
  raw = _api_extract_key(request)
  if not raw.startswith("ats_"):
    raise _ApiErr(401, "UNAUTHORIZED", "Missing or invalid API key.")
  row = cur.execute(
    "SELECT id, owner_id, status, expires_at FROM api_keys WHERE key_hash=?",
    (_api_hash(raw),)).fetchone()
  if not row:
    raise _ApiErr(401, "UNAUTHORIZED", "Missing or invalid API key.")
  key_id, owner_id, status, expires_at = row
  if status != "active":
    raise _ApiErr(403, "KEY_DISABLED", "This API key is disabled. Contact the admin.")
  if expires_at and expires_at < datetime.utcnow().isoformat():
    raise _ApiErr(403, "KEY_EXPIRED", "This API key has expired. Contact the admin.")
  urow = cur.execute("SELECT banned, frozen FROM users WHERE user_id=?", (owner_id,)).fetchone()
  if not urow or int(urow[0] or 0) or int(urow[1] or 0):
    raise _ApiErr(403, "KEY_DISABLED", "This account is restricted. Contact the admin.")
  now = time.time()
  window = _API_RATE.setdefault(key_id, _api_deque())
  while window and now - window[0] > 60:
    window.popleft()
  if len(window) >= API_RATE_LIMIT:
    raise _ApiErr(429, "RATE_LIMIT", "Too many requests. Slow down and retry in a few seconds.")
  window.append(now)
  cur.execute("UPDATE api_keys SET last_used_at=? WHERE id=?", (datetime.utcnow().isoformat(), key_id))
  db.commit()
  return key_id, int(owner_id)


def _api_ok(data, status=200):
  out = {"success": True}
  out.update(data)
  return _api_web.json_response(out, status=status)


def _api_fail(status, code, message):
  return _api_web.json_response({"success": False, "error": code, "message": message}, status=status)


def _api_int(value, name, allowed=None):
  try:
    n = int(str(value).strip())
  except Exception:
    raise _ApiErr(400, "INVALID_PARAMS", "%s is required." % name)
  if allowed and n not in allowed:
    raise _ApiErr(400, "INVALID_PARAMS", "%s must be one of %s." % (name, ", ".join(str(x) for x in allowed)))
  return n


def _api_flag(code):
  code = str(code or "").strip().upper()
  if len(code) == 2 and code.isalpha():
    return "".join(chr(0x1F1E6 + ord(ch) - 65) for ch in code)
  return ""


def _api_map_upstream_error(exc):
  # Never leak provider names, hosts or raw provider text to the client.
  text = str(exc).upper()
  if any(w in text for w in ("NO_KEY", "BAD_KEY", "MISSING_API_KEY", "NO_BALANCE", "LOW_BALANCE",
                             "NOT ENOUGH", "INSUFFICIENT")):
    return _ApiErr(503, "NOT_AVAILABLE", "This server is temporarily unavailable. Please try again later.")
  if any(w in text for w in ("NO_NUMBERS", "NO_NUMBER", "BAD_COUNTRY", "BAD_SERVICE", "NO_STOCK",
                             "NO MATCHING", "ACCOUNT_UNAVAILABLE", "SOLD")):
    return _ApiErr(400, "OUT_OF_STOCK", "No stock for this selection right now.")
  return _ApiErr(502, "UPSTREAM_ERROR", "Provider error. Any charge was refunded. Please retry in a few seconds.")


async def _api_thread(fn, *args):
  try:
    return await asyncio.to_thread(fn, *args)
  except _ApiErr:
    raise
  except Exception as ex:
    raise _api_map_upstream_error(ex)


def _api_require(srv):
  if srv == 2 and not (_s2wa_enabled() and _s2wa_api_key()):
    raise _ApiErr(503, "NOT_AVAILABLE", "This server is not available right now.")
  if srv == 3 and not (_s3_enabled() and _s3_key()):
    raise _ApiErr(503, "NOT_AVAILABLE", "This server is not available right now.")


def _api_debit(uid, amount):
  cur.execute("UPDATE users SET balance = balance - ? WHERE user_id=? AND balance >= ?", (amount, uid, amount))
  ok = cur.rowcount == 1
  db.commit()
  return ok


def _api_credit(uid, amount):
  cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, uid))
  db.commit()


async def _api_notify(server_no, uid, what, phone, price, order_id):
  try:
    await notify_admins(
      "\U0001F6D2 <b>API PURCHASE</b>\n\nServer: %s\nUser: <code>%s</code>\nItem: %s\n"
      "Number: <code>%s</code>\nPaid: \u20b9%s\nOrder: <code>%s</code>"
      % (server_no, uid, html.escape(str(what)), html.escape(str(phone)), price, html.escape(str(order_id))))
  except Exception:
    pass


def _api_public_env():
  return (os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")


def _api_public_base(request):
  base = _api_public_env()
  if base:
    return base
  proto = request.headers.get("X-Forwarded-Proto") or request.scheme
  return "%s://%s" % (proto, request.host)


# ---------------------------- public pages ----------------------------------
async def _api_h_health(request):
  return _api_ok({"status": "ok"})


async def _api_h_info(request):
  return _api_ok({"name": "Reseller API", "version": "1.5", "docs": "/",
                  "servers": {str(k): v for k, v in _API_SERVER_NAMES.items()}})


async def _api_h_docs(request):
  try:
    with open(_API_DOCS_FILE, "r", encoding="utf-8") as fh:
      page = fh.read()
  except Exception:
    return _api_web.Response(text="Docs file (docs-index.html) not found next to bot.py.", status=404)
  base = _api_public_base(request)
  host = re.sub(r"^https?://", "", base)
  page = page.replace("https://YOUR_DOMAIN.com", base).replace("YOUR_DOMAIN.com", host)
  return _api_web.Response(text=page, content_type="text/html")


# ---------------------------- API: info endpoints ---------------------------
async def _api_h_balance(request):
  _kid, uid = _api_auth(request)
  row = cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
  return _api_ok({"balance": round(float(row[0] or 0), 2) if row else 0.0, "currency": "INR", "user_id": uid})


async def _api_h_services(request):
  _api_auth(request)
  out = []
  for n, name in _API_SERVER_NAMES.items():
    on = True
    if n == 2:
      on = bool(_s2wa_enabled() and _s2wa_api_key())
    elif n == 3:
      on = bool(_s3_enabled() and _s3_key())
    out.append({"server": n, "name": name, "enabled": on})
  return _api_ok({"services": out})


async def _api_h_apps(request):
  _api_auth(request)
  _api_require(3)
  services = await _api_thread(_s3_services)
  return _api_ok({"count": len(services or []),
                  "apps": [{"code": s.get("code"), "name": s.get("name")} for s in services or []]})


async def _api_h_countries(request):
  _api_auth(request)
  srv = _api_int(request.query.get("server"), "server", (1, 2, 3))
  _api_require(srv)
  rows = []
  if srv == 1:
    data = await asyncio.to_thread(fetch_s2_countries)
    if isinstance(data, dict):
      raise _ApiErr(503, "LOADING", "Country list is loading. Try again in a minute.")
    for c in data or []:
      code = str(c.get("code") or "").upper()
      if not code:
        continue
      stock = c.get("stock")
      if stock is not None and int(stock) <= 0:
        continue
      price = server_sell_price(c.get("price"))
      if price <= 0:
        continue
      rows.append({"country_code": code, "name": clean_country_name(c.get("name") or code),
                   "flag": _api_flag(code), "price": price,
                   "stock": int(stock) if stock is not None else None})
  elif srv == 2:
    items = await _api_thread(_s2wa_countries)
    prices = await _api_thread(_s2wa_prices_map)
    for it in items or []:
      pr = (prices or {}).get(int(it["id"]))
      if not pr or int(pr[1] or 0) <= 0:
        continue
      code = str(it.get("code") or _s2wa_flag_code(it) or "").upper()
      rows.append({"id": int(it["id"]), "country_code": code,
                   "name": clean_country_name(it.get("name") or ""), "flag": _api_flag(code),
                   "price": _s2wa_sell_price(pr[0]), "stock": int(pr[1])})
  else:
    service = (request.query.get("service") or request.query.get("app") or "").strip()
    if not service:
      raise _ApiErr(400, "INVALID_PARAMS", "service is required for server 3. See GET /v1/apps.")
    items = await _api_thread(_s3_available, service)
    for it in items or []:
      code = str(it.get("code") or "").upper()
      rows.append({"id": int(it["id"]), "country_code": code,
                   "name": clean_country_name(it.get("name") or ""), "flag": _api_flag(code),
                   "price": _s3_sell_price(it.get("cost", 0)), "stock": int(it.get("count", 0) or 0)})
  rows.sort(key=lambda r: (r["price"], r["name"]))
  return _api_ok({"server": srv, "count": len(rows), "countries": rows})


# ---------------------------- API: buy --------------------------------------
async def _api_buy_s1(uid, body, max_price):
  code = str(body.get("country_code") or "").strip().upper()
  if not code and re.fullmatch(r"[A-Za-z]{2}", str(body.get("country") or "")):
    code = str(body.get("country")).upper()
  item_id = str(body.get("item_id") or "").strip()
  if not re.fullmatch(r"[A-Z]{2}", code):
    raise _ApiErr(400, "INVALID_PARAMS", "country_code is required for server 1 (example: IN).")
  if item_id:
    listed = await asyncio.to_thread(fetch_s1_items, code, True, None, 20, None, None, None)
    if isinstance(listed, dict):
      raise _api_map_upstream_error(RuntimeError(str(listed.get("error") or "")))
    pick = next((i for i in (listed or []) if i["id"] == item_id), None)
    if not pick:
      raise _ApiErr(400, "OUT_OF_STOCK", "This account was just sold. Pick another.")
    api_price = float(pick["price"])
  else:
    detail = await asyncio.to_thread(fetch_s1_country_detail, code)
    if not isinstance(detail, dict) or detail.get("error") or int(detail.get("stock") or 0) <= 0:
      raise _ApiErr(400, "OUT_OF_STOCK", "No stock for this country right now.")
    api_price = float(detail.get("price") or 0)
  if api_price <= 0:
    raise _ApiErr(503, "NOT_AVAILABLE", "Price is unavailable right now. Try again shortly.")
  price = server_sell_price(api_price)
  if max_price is not None and price > max_price:
    raise _ApiErr(400, "PRICE_TOO_HIGH", "Current price is above your max_price.")
  if _s1_wallet(uid)[0] < price:
    raise _ApiErr(402, "INSUFFICIENT_FUNDS", "Balance is too low for this purchase.")
  if item_id:
    res = await asyncio.to_thread(lambda: create_nobelots_order(account_id=item_id, max_price=api_price))
  else:
    res = await asyncio.to_thread(lambda: create_nobelots_order(country_code=code, quantity=1))
  if not res.get("ok"):
    raise _api_map_upstream_error(RuntimeError("%s %s" % (res.get("error", ""), res.get("message", ""))))
  batch_id = res["batch_id"]
  order = wait_nobelots_order(batch_id, 120)
  accounts = order.get("accounts") or []
  if not order.get("ok") or not accounts:
    raise _ApiErr(502, "UPSTREAM_ERROR", "Account delivery failed. You were not charged. Retry shortly.")
  name = clean_country_name(_lzt_country_name(code))
  # Charges the wallet exactly once and stores the order (same as the bot).
  _order_no, phone = _s1_finalize_purchase(uid, batch_id, order, code, name, price)
  oid = "T-" + batch_id
  await _api_notify(1, uid, name, phone, price, oid)
  return _api_ok({"order_id": oid, "phone": phone, "price": price, "server": 1, "country": name,
                  "status": "WAIT_CODE", "password": str(accounts[0].get("password") or ""),
                  "message": "Enter the phone in Telegram, then poll GET /v1/order/{order_id} for the login code."})


async def _api_buy_wa(uid, body, max_price):
  cid = _api_int(body.get("country"), "country")
  prices = await _api_thread(_s2wa_prices_map, True)
  pr = (prices or {}).get(cid)
  if not pr or int(pr[1] or 0) <= 0:
    raise _ApiErr(400, "OUT_OF_STOCK", "No stock for this country right now.")
  cost = pr[0]
  price = _s2wa_sell_price(cost)
  if max_price is not None and price > max_price:
    raise _ApiErr(400, "PRICE_TOO_HIGH", "Current price is above your max_price.")
  countries = await _api_thread(_s2wa_countries)
  item = next((c for c in (countries or []) if int(c["id"]) == cid), None)
  if not item:
    raise _ApiErr(400, "INVALID_PARAMS", "Unknown country id.")
  service = await _api_thread(_s2wa_resolve_service)
  if not _api_debit(uid, price):
    raise _ApiErr(402, "INSUFFICIENT_FUNDS", "Balance is too low for this purchase.")
  try:
    act_id, phone = await _api_thread(_S2waTiger(_s2wa_api_key()).get_number, service, cid, cost)
  except _ApiErr:
    _api_credit(uid, price)
    raise
  name = clean_country_name(item.get("name") or "")
  _s2wa_new_order(uid, act_id, phone, name, cid, service, cost, price)
  _global_order_register("whatsapp", act_id, uid, price, "WAIT_CODE")
  oid = "W-" + str(act_id)
  await _api_notify(2, uid, "WhatsApp " + name, phone, price, oid)
  return _api_ok({"order_id": oid, "phone": phone, "price": price, "server": 2, "country": name,
                  "status": "WAIT_CODE"})


async def _api_buy_s3(uid, body, max_price):
  service = str(body.get("service") or body.get("app") or "").strip()
  if not service:
    raise _ApiErr(400, "INVALID_PARAMS", "service is required for server 3. See GET /v1/apps.")
  cid = _api_int(body.get("country"), "country")
  items = await _api_thread(_s3_available, service, True)
  item = next((i for i in (items or []) if int(i["id"]) == cid), None)
  if not item:
    raise _ApiErr(400, "OUT_OF_STOCK", "No stock for this country right now.")
  cost = item["cost"]
  price = _s3_sell_price(cost)
  if max_price is not None and price > max_price:
    raise _ApiErr(400, "PRICE_TOO_HIGH", "Current price is above your max_price.")
  if not _api_debit(uid, price):
    raise _ApiErr(402, "INSUFFICIENT_FUNDS", "Balance is too low for this purchase.")
  try:
    act_id, phone = await _api_thread(_s3_tiger().get_number, service, cid, cost)
  except _ApiErr:
    _api_credit(uid, price)
    raise
  svc_name = await asyncio.to_thread(_s3_service_name, service)
  _s3_new_order(uid, act_id, phone, service, svc_name, item.get("name", ""), cid, cost, price)
  _global_order_register("s3otp", act_id, uid, price, "WAIT_CODE")
  oid = "A-" + str(act_id)
  await _api_notify(3, uid, "%s %s" % (svc_name, item.get("name", "")), phone, price, oid)
  return _api_ok({"order_id": oid, "phone": phone, "price": price, "server": 3,
                  "service": service, "country": clean_country_name(item.get("name", "")),
                  "status": "WAIT_CODE"})


async def _api_h_accounts(request):
  """Server 1 only: list individual Telegram accounts for a country.

  Mirrors the account list shown inside the Telegram bot (same upstream, same
  sell price, same filters). Only safe public fields are returned - session
  strings and provider internals are never exposed here."""
  _kid, uid = _api_auth(request)
  srv = _api_int(request.query.get("server", 1), "server", (1,))
  _api_require(srv)
  code = str(request.query.get("country_code") or request.query.get("country") or "").strip().upper()
  if not re.fullmatch(r"[A-Z]{2}", code):
    raise _ApiErr(400, "INVALID_PARAMS", "country_code is required (example: IN).")
  try:
    limit = max(1, min(50, int(request.query.get("limit", 20))))
  except Exception:
    raise _ApiErr(400, "INVALID_PARAMS", "limit must be 1-50.")
  spam = str(request.query.get("spam") or "").strip().lower()
  spam = spam if spam in ("yes", "no") else None
  premium = str(request.query.get("premium") or "").strip().lower()
  premium = premium if premium in ("yes", "no") else None
  email_f = str(request.query.get("email") or "").strip().lower()
  email_f = email_f if email_f in ("yes", "no") else None
  cat = str(request.query.get("category") or request.query.get("cat") or "").strip().lower()
  cat = cat if cat in ("push", "autoreg", "premium") else None
  listed = await asyncio.to_thread(fetch_s1_items, code, True, spam, limit, premium, email_f, cat)
  if isinstance(listed, dict):
    raise _api_map_upstream_error(RuntimeError(str(listed.get("error") or "")))
  rows = []
  for it in listed or []:
    price = server_sell_price(it.get("price"))
    if price <= 0:
      continue
    prem = it.get("premium")
    rows.append({
      "account_id": str(it.get("id")),
      "price": price,
      "premium": (bool(prem) if prem not in (None, "") else None),
      "premium_until": it.get("premium_end") or "",
      "spam_block": (bool(it.get("spam")) if it.get("spam") not in (None, "") else None),
      "twofa": bool(it.get("twofa")),
      "email": str(it.get("email") or ""),
      "channels": int(it.get("channels") or 0),
      "groups": int(it.get("groups") or 0),
      "admins": int(it.get("admins") or 0),
      "origin": str(it.get("origin") or ""),
      "uploaded": str(it.get("uploaded") or ""),
      "last_seen": str(it.get("last_seen") or ""),
    })
  rows.sort(key=lambda r: r["price"])
  return _api_ok({"server": 1, "country_code": code, "count": len(rows), "accounts": rows})


async def _api_h_buy(request):
  _kid, uid = _api_auth(request)
  try:
    body = await request.json()
    if not isinstance(body, dict):
      raise ValueError("not an object")
  except Exception:
    raise _ApiErr(400, "INVALID_PARAMS", "Body must be a JSON object.")
  srv = _api_int(body.get("server"), "server", (1, 2, 3))
  _api_require(srv)
  max_price = body.get("max_price")
  try:
    max_price = float(max_price) if max_price not in (None, "") else None
  except Exception:
    raise _ApiErr(400, "INVALID_PARAMS", "max_price must be a number.")
  lock = get_user_lock(uid)
  if lock.locked():
    raise _ApiErr(429, "ORDER_IN_PROGRESS", "Another purchase is in progress for this account. Wait a moment.")
  async with lock:
    if srv == 1:
      return await _api_buy_s1(uid, body, max_price)
    if srv == 2:
      return await _api_buy_wa(uid, body, max_price)
    return await _api_buy_s3(uid, body, max_price)


# ---------------------------- API: orders -----------------------------------
def _api_split(order_id):
  m = re.fullmatch(r"([TWA])-(.+)", str(order_id or "").strip())
  if not m:
    raise _ApiErr(404, "NOT_FOUND", "Order not found.")
  return m.group(1), m.group(2)


def _api_tg_row(batch, uid):
  r = cur.execute(
    "SELECT user_id, number, status, code, account_no, session_str, price, created_date, password "
    "FROM s2_orders WHERE order_id=?", (batch,)).fetchone()
  if not r or int(r[0] or 0) != int(uid):
    raise _ApiErr(404, "NOT_FOUND", "Order not found.")
  return {"phone": r[1], "status": r[2], "code": r[3] or "", "account_no": r[4], "session": r[5] or "",
          "price": r[6], "created_at": str(r[7] or ""), "password": r[8] or ""}


def _api_s1_status(status, code):
  st = str(status or "").lower()
  if st in ("cancelled", "refunded", "failed"):
    return "CANCELLED"
  return "DONE" if (code or st == "completed") else "WAIT_CODE"


def _api_wa_row(kind, ref, uid):
  row = _s2wa_get_order(ref) if kind == "W" else _s3_get_order(ref)
  if not row or int(row.get("uid") or 0) != int(uid):
    raise _ApiErr(404, "NOT_FOUND", "Order not found.")
  return row


async def _api_poll_tg(batch, uid):
  info = _api_tg_row(batch, uid)
  if not info["code"] and _api_s1_status(info["status"], "") != "CANCELLED":
    res = await _s1_get_code(batch, info["account_no"], deep=False)
    if isinstance(res, dict) and res.get("ok") and res.get("code"):
      cur.execute("UPDATE s2_orders SET code=? WHERE order_id=?", (str(res["code"]), batch))
      db.commit()
      _s1_mark_completed(batch)
      info = _api_tg_row(batch, uid)
  info["status_api"] = _api_s1_status(info["status"], info["code"])
  return info


async def _api_poll_wa(kind, ref, uid, row):
  if str(row.get("status") or "") in ("DONE", "CANCELLED"):
    return row
  tiger = _S2waTiger(_s2wa_api_key()) if kind == "W" else _s3_tiger()
  upd = _s2wa_update_order if kind == "W" else _s3_update_order
  raw = str(await _api_thread(tiger.status, ref) or "")
  if raw.startswith("STATUS_OK"):
    upd(ref, status="DONE", code=raw.split(":", 1)[1] if ":" in raw else "")
    try:
      await asyncio.to_thread(tiger.set_status, ref, 6)
    except Exception:
      pass
  elif raw.startswith("STATUS_WAIT_RETRY"):
    upd(ref, status="WAIT_RETRY", code=raw.split(":", 1)[1] if ":" in raw else "")
  elif raw.startswith("STATUS_CANCEL"):
    await asyncio.to_thread(_s2wa_refund_once if kind == "W" else _s3_refund_once, ref, uid)
  return _api_wa_row(kind, ref, uid)


async def _api_order_response(uid, order_id):
  kind, ref = _api_split(order_id)
  if kind == "T":
    info = await _api_poll_tg(ref, uid)
    return _api_ok({"order_id": order_id, "server": 1, "phone": info["phone"], "code": info["code"],
                    "password": info["password"], "status": info["status_api"], "price": info["price"]})
  row = _api_wa_row(kind, ref, uid)
  row = await _api_poll_wa(kind, ref, uid, row)
  return _api_ok({"order_id": order_id, "server": 2 if kind == "W" else 3, "phone": row.get("phone"),
                  "code": row.get("code") or "", "status": row.get("status"), "price": row.get("price_inr")})


async def _api_h_order(request):
  _kid, uid = _api_auth(request)
  order_id = request.match_info.get("order_id") or request.query.get("order_id", "")
  return await _api_order_response(uid, order_id)


async def _api_h_cancel(request):
  _kid, uid = _api_auth(request)
  order_id = request.match_info.get("order_id", "")
  kind, ref = _api_split(order_id)
  if kind == "T":
    _api_tg_row(ref, uid)
    raise _ApiErr(400, "NOT_CANCELLABLE", "Server 1 orders cannot be cancelled (no refund).")
  row = _api_wa_row(kind, ref, uid)
  if row.get("status") not in ("WAIT_CODE", "WAIT_RETRY"):
    raise _ApiErr(400, "NOT_CANCELLABLE", "This order cannot be cancelled now.")
  tiger = _S2waTiger(_s2wa_api_key()) if kind == "W" else _s3_tiger()
  raw = str(await _api_thread(tiger.set_status, ref, 8) or "")
  if raw.startswith("STATUS_OK"):
    upd = _s2wa_update_order if kind == "W" else _s3_update_order
    upd(ref, status="DONE", code=raw.split(":", 1)[1] if ":" in raw else "")
    raise _ApiErr(400, "NOT_CANCELLABLE", "The code already arrived, so this order cannot be cancelled.")
  if raw not in ("ACCESS_CANCEL", "STATUS_CANCEL"):
    raise _ApiErr(400, "NOT_CANCELLABLE", "Cancellation was not confirmed. No refund was issued.")
  fn = _s2wa_refund_once if kind == "W" else _s3_refund_once
  refunded, amount = await asyncio.to_thread(fn, ref, uid)
  return _api_ok({"order_id": order_id, "status": "CANCELLED", "refunded": bool(refunded),
                  "refund": amount if refunded else 0})


async def _api_h_retry(request):
  _kid, uid = _api_auth(request)
  order_id = request.match_info.get("order_id", "")
  kind, ref = _api_split(order_id)
  if kind == "T":
    _api_tg_row(ref, uid)
    raise _ApiErr(400, "NOT_RETRYABLE", "Retry is only available for server 2 and 3 orders.")
  row = _api_wa_row(kind, ref, uid)
  if row.get("status") != "WAIT_RETRY":
    raise _ApiErr(400, "NOT_RETRYABLE", "Retry is not available for this order right now.")
  tiger = _S2waTiger(_s2wa_api_key()) if kind == "W" else _s3_tiger()
  await _api_thread(tiger.set_status, ref, 3)
  (_s2wa_update_order if kind == "W" else _s3_update_order)(ref, status="WAIT_CODE", code="")
  return _api_ok({"order_id": order_id, "status": "WAIT_CODE", "message": "New SMS requested. Poll the order again."})


async def _api_h_session(request):
  _kid, uid = _api_auth(request)
  order_id = request.query.get("order_id", "")
  kind, ref = _api_split(order_id)
  if kind != "T":
    raise _ApiErr(404, "NOT_FOUND", "Session files exist only for server 1 orders.")
  info = _api_tg_row(ref, uid)
  if not info["session"]:
    raise _ApiErr(404, "NOT_FOUND", "Session is not available for this order.")
  return _api_ok({"order_id": order_id, "phone": info["phone"], "format": "telethon_string_session",
                  "session_string": info["session"]})


async def _api_h_orders(request):
  _kid, uid = _api_auth(request)
  try:
    limit = max(1, min(100, int(request.query.get("limit", 20))))
  except ValueError:
    raise _ApiErr(400, "INVALID_PARAMS", "limit must be 1-100.")
  items = []
  for r in cur.execute("SELECT order_id, number, status, code, price, created_date FROM s2_orders "
                       "WHERE user_id=? ORDER BY rowid DESC LIMIT ?", (uid, limit)).fetchall():
    items.append({"order_id": "T-" + str(r[0]), "server": 1, "phone": r[1], "code": r[3] or "",
                  "status": _api_s1_status(r[2], r[3]), "price": r[4],
                  "created_at": str(r[5] or "").replace(" ", "T")})
  for r in (await asyncio.to_thread(_s2wa_user_orders, uid, limit)) or []:
    items.append({"order_id": "W-" + str(r.get("activation_id")), "server": 2, "phone": r.get("phone"),
                  "code": r.get("code") or "", "status": r.get("status"), "price": r.get("price_inr"),
                  "created_at": str(r.get("created_at") or "")})
  for r in (await asyncio.to_thread(_s3_user_orders, uid, limit)) or []:
    items.append({"order_id": "A-" + str(r.get("activation_id")), "server": 3, "phone": r.get("phone"),
                  "code": r.get("code") or "", "status": r.get("status"), "price": r.get("price_inr"),
                  "created_at": str(r.get("created_at") or "")})
  items.sort(key=lambda x: x["created_at"], reverse=True)
  items = items[:limit]
  return _api_ok({"count": len(items), "orders": items})


@_api_web.middleware
async def _api_mw(request, handler):
  if request.method == "OPTIONS":
    resp = _api_web.Response(status=204)
  else:
    try:
      resp = await handler(request)
    except _ApiErr as ex:
      resp = _api_fail(ex.status, ex.code, ex.message)
    except _api_web.HTTPException as ex:
      resp = _api_fail(ex.status, "NOT_FOUND" if ex.status == 404 else "ERROR", ex.reason or "Error")
    except Exception as ex:
      logger.error("API internal error: %s", ex, exc_info=True)
      resp = _api_fail(500, "INTERNAL_ERROR", "Something went wrong. Please try again.")
  resp.headers["Access-Control-Allow-Origin"] = API_ORIGIN
  resp.headers["Access-Control-Allow-Headers"] = "Authorization, X-API-Key, Content-Type"
  resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
  return resp


async def _start_reseller_api():
  if IS_CLONE:
    return
  try:
    _api_init_tables()
    app = _api_web.Application(middlewares=[_api_mw])
    app.router.add_get("/", _api_h_docs)
    app.router.add_get("/docs", _api_h_docs)
    app.router.add_get("/health", _api_h_health)
    app.router.add_get("/api", _api_h_info)
    for pre in ("", "/api"):
      app.router.add_get(pre + "/v1/balance", _api_h_balance)
      app.router.add_get(pre + "/v1/services", _api_h_services)
      app.router.add_get(pre + "/v1/countries", _api_h_countries)
      app.router.add_get(pre + "/v1/accounts", _api_h_accounts)
      app.router.add_get(pre + "/v1/apps", _api_h_apps)
      app.router.add_post(pre + "/v1/buy", _api_h_buy)
      app.router.add_get(pre + "/v1/order/{order_id}", _api_h_order)
      app.router.add_get(pre + "/v1/otp", _api_h_order)
      app.router.add_get(pre + "/v1/orders", _api_h_orders)
      app.router.add_get(pre + "/v1/session", _api_h_session)
      app.router.add_post(pre + "/v1/cancel/{order_id}", _api_h_cancel)
      app.router.add_post(pre + "/v1/retry/{order_id}", _api_h_retry)
    runner = _api_web.AppRunner(app)
    await runner.setup()
    await _api_web.TCPSite(runner, "0.0.0.0", API_PORT).start()
    logger.info("Reseller API + docs listening on port %s", API_PORT)
  except Exception as ex:
    logger.error("Reseller API failed to start: %s", ex, exc_info=True)


# ---------------------------- admin panel: API Keys -------------------------
def _api_resolve_user(token):
  token = str(token or "").strip()
  if token.startswith("@"):
    token = token[1:]
    row = cur.execute("SELECT user_id FROM users WHERE LOWER(REPLACE(username,'@',''))=?", (token.lower(),)).fetchone()
    return int(row[0]) if row else None
  if token.isdigit():
    row = cur.execute("SELECT user_id FROM users WHERE user_id=?", (int(token),)).fetchone()
    return int(row[0]) if row else None
  row = cur.execute("SELECT user_id FROM users WHERE LOWER(REPLACE(username,'@',''))=?", (token.lower(),)).fetchone()
  return int(row[0]) if row else None


def _api_user_label(user_id):
  row = cur.execute("SELECT username FROM users WHERE user_id=?", (user_id,)).fetchone()
  un = ((row[0] if row else "") or "").lstrip("@")
  return ("@" + un) if un else str(user_id)


def _api_key_state(status, expires_at):
  if status != "active":
    return "Stopped"
  if expires_at and expires_at < datetime.utcnow().isoformat():
    return "Expired"
  return "Active"


async def _api_admin_menu(event, note=""):
  total = cur.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
  active = cur.execute("SELECT COUNT(*) FROM api_keys WHERE status='active'").fetchone()[0]
  base = _api_public_env() or "your Render URL"
  text = ("%s <b>API Keys</b>\n\nTotal keys: <b>%s</b> | Active: <b>%s</b>\nDocs &amp; API URL: <code>%s</code>\n\n"
          "<i>Create a key for a bot user. Their API purchases are charged from their bot balance.</i>"
          % (P_GEAR, total, active, html.escape(base)))
  if note:
    text = note + "\n\n" + text
  return await e_edit_or_send(event, custom_emoji_text(text), [
    [Button.inline("Create API Key", "adm_apik|new", style="success")],
    [Button.inline("View Keys", "adm_apik|list|0", style="primary")],
    [Button.inline("Back to Admin", "adm_adminmain")]])


async def _api_admin_list(event, page=0):
  rows = cur.execute("SELECT id, owner_id, status, expires_at FROM api_keys ORDER BY id DESC").fetchall()
  if not rows:
    return await _api_admin_menu(event, "%s No API keys yet." % P_WARN)
  per = 8
  pages = max(1, (len(rows) + per - 1) // per)
  page = max(0, min(int(page), pages - 1))
  btns = []
  for kid, owner, status, exp in rows[page * per:(page + 1) * per]:
    label = ("#%s %s %s" % (kid, _api_user_label(owner), _api_key_state(status, exp)))[:44]
    btns.append([Button.inline(label, "adm_apik|view|%s" % kid)])
  nav = []
  if page > 0:
    nav.append(Button.inline("Prev", "adm_apik|list|%s" % (page - 1), style="primary"))
  if page < pages - 1:
    nav.append(Button.inline("Next", "adm_apik|list|%s" % (page + 1), style="primary"))
  if nav:
    btns.append(nav)
  btns.append([Button.inline("Back", "adm_apik|menu")])
  return await e_edit_or_send(
    event, custom_emoji_text("%s <b>All API Keys</b> (page %s/%s)" % (P_GEAR, page + 1, pages)), btns)


async def _api_admin_view(event, kid, note=""):
  r = cur.execute("SELECT id, owner_id, prefix, status, expires_at, created_at, last_used_at, raw_key "
                  "FROM api_keys WHERE id=?", (kid,)).fetchone()
  if not r:
    return await safe_callback_answer(event, "Key not found.", alert=True)
  bal = cur.execute("SELECT balance FROM users WHERE user_id=?", (r[1],)).fetchone()
  state = _api_key_state(r[3], r[4])
  text = ("%s <b>API Key #%s</b>\n\nOwner: <b>%s</b> (<code>%s</code>)\nWallet balance: <b>\u20b9%s</b>\n"
          "Status: <b>%s</b>\nExpires: <b>%s</b>\nLast used: %s\nCreated: %s\nAPI Key: %s"
          % (P_GEAR, r[0], html.escape(_api_user_label(r[1])), r[1], round(float(bal[0] or 0), 2) if bal else 0,
             state, (r[4] or "-")[:10], (r[6] or "never")[:16], (r[5] or "-")[:16],
             ("<code>%s</code>" % html.escape(r[7])) if r[7] else ("<code>%s...</code> (full key not saved, made before this update)" % html.escape(r[2] or ""))))
  if note:
    text = note + "\n\n" + text
  toggle = (Button.inline("Resume Key", "adm_apik|resume|%s" % kid, style="success") if r[3] != "active"
            else Button.inline("Stop Key", "adm_apik|stop|%s" % kid, style="danger"))
  return await e_edit_or_send(event, custom_emoji_text(text), [
    [Button.inline("Change Duration", "adm_apik|dur|%s" % kid, style="primary"), toggle],
    [Button.inline("Delete Key", "adm_apik|del|%s" % kid, style="danger")],
    [Button.inline("Back", "adm_apik|list|0")]])


async def _api_admin_ask(conv, txt):
  await conv.send_message(custom_emoji_text(txt + "\n\n<i>(Type /cancel to abort)</i>"))
  resp = await conv.get_response()
  val = (resp.text or "").strip()
  if val == "/cancel":
    raise ValueError("Cancelled")
  return val


async def _api_admin_new(event, chat):
  await safe_callback_answer(event)
  async with _admin_conversation(chat, timeout=300) as conv:
    try:
      who = await _api_admin_ask(conv, "%s <b>Create API Key</b>\n\nSend the <b>@username</b> or <b>User ID</b> "
                                       "of a user who has joined this bot." % P_GEAR)
      target = _api_resolve_user(who)
      if not target:
        return await conv.send_message(custom_emoji_text(
          "%s <b>User not found.</b> The user must have started this bot." % P_NO))
      days_txt = await _api_admin_ask(conv, "Send the key validity in <b>days</b> (example: <code>30</code>).")
      if not (days_txt.isdigit() and 1 <= int(days_txt) <= 3650):
        return await conv.send_message(custom_emoji_text("%s <b>Invalid days.</b> Nothing created." % P_NO))
      raw, kid = _api_create_key(target, int(days_txt))
      await conv.send_message(custom_emoji_text(
        "%s <b>API key created</b> (ID %s)\n\nOwner: <b>%s</b>\nValid for: <b>%s days</b>\n\n<code>%s</code>\n\n"
        "<i>Copy it now. It is shown only once.</i>"
        % (P_YES, kid, html.escape(_api_user_label(target)), days_txt, raw)),
        buttons=[[Button.inline("Open API Keys", "adm_apik|menu")]])
    except ValueError:
      await conv.send_message(custom_emoji_text("%s Cancelled." % P_WARN))
    except Exception as ex:
      logger.warning("api key create conversation ended: %s", ex)
      await conv.send_message(custom_emoji_text("%s Timed out. Nothing created." % P_WARN))


async def _api_admin_duration(event, chat, kid):
  await safe_callback_answer(event)
  async with _admin_conversation(chat, timeout=300) as conv:
    try:
      days_txt = await _api_admin_ask(conv, "%s <b>Change Duration (key #%s)</b>\n\nSend the new validity in "
                                            "<b>days from today</b> (example: <code>60</code>)." % (P_GEAR, kid))
      if not (days_txt.isdigit() and 1 <= int(days_txt) <= 3650):
        return await conv.send_message(custom_emoji_text("%s <b>Invalid days.</b> Nothing changed." % P_NO))
      exp = (datetime.utcnow() + timedelta(days=int(days_txt))).isoformat()
      cur.execute("UPDATE api_keys SET expires_at=? WHERE id=?", (exp, kid))
      db.commit()
      await conv.send_message(custom_emoji_text("%s Key #%s now expires in <b>%s days</b>." % (P_YES, kid, days_txt)),
                              buttons=[[Button.inline("Open Key", "adm_apik|view|%s" % kid)]])
    except ValueError:
      await conv.send_message(custom_emoji_text("%s Cancelled." % P_WARN))
    except Exception as ex:
      logger.warning("api key duration conversation ended: %s", ex)
      await conv.send_message(custom_emoji_text("%s Timed out. Nothing changed." % P_WARN))


async def _api_admin_router(event, uid, chat, action_data):
  if uid != ADMIN_ID:
    return await safe_callback_answer(event, "Only the owner can use this option.", alert=True)
  parts = action_data.split("|")
  op = parts[1] if len(parts) > 1 else "menu"
  arg = parts[2] if len(parts) > 2 else ""
  try:
    if op == "menu":
      await safe_callback_answer(event)
      return await _api_admin_menu(event)
    if op == "new":
      return await _api_admin_new(event, chat)
    if op == "list":
      await safe_callback_answer(event)
      return await _api_admin_list(event, int(arg or 0))
    kid = int(arg) if arg.isdigit() else 0
    if op == "view":
      await safe_callback_answer(event)
      return await _api_admin_view(event, kid)
    if op == "dur":
      return await _api_admin_duration(event, chat, kid)
    if op in ("stop", "resume"):
      cur.execute("UPDATE api_keys SET status=? WHERE id=?", ("suspended" if op == "stop" else "active", kid))
      db.commit()
      await safe_callback_answer(event, "Key stopped." if op == "stop" else "Key resumed.")
      return await _api_admin_view(event, kid)
    if op == "del":
      await safe_callback_answer(event)
      return await e_edit_or_send(
        event, custom_emoji_text("%s <b>Delete API key #%s?</b>\n\nThis cannot be undone. Anyone using this key "
                                 "will stop working immediately." % (P_WARN, kid)),
        [[Button.inline("Yes, Delete", "adm_apik|delyes|%s" % kid, style="danger")],
         [Button.inline("Cancel", "adm_apik|view|%s" % kid, style="primary")]])
    if op == "delyes":
      cur.execute("DELETE FROM api_keys WHERE id=?", (kid,))
      db.commit()
      await safe_callback_answer(event, "Key deleted.")
      return await _api_admin_list(event, 0)
    return await safe_callback_answer(event, "Unknown action.", alert=True)
  except Exception as ex:
    logger.error("API key admin error: %s", ex, exc_info=True)
    return await safe_callback_answer(event, "Error: %s" % str(ex)[:150], alert=True)


@bot.on(events.NewMessage(pattern=r"^/apikey(\s|$)"))
async def _api_admin_cmd(event):
  if event.sender_id != ADMIN_ID:
    return
  parts = (event.raw_text or "").split()
  sub = parts[1].lower() if len(parts) > 1 else "help"
  args = parts[2:]
  try:
    if sub == "create" and args:
      target = _api_resolve_user(args[0])
      if not target:
        return await event.reply("User not found. Use a numeric user ID or @username of a user who started the bot.")
      days = int(args[1]) if len(args) > 1 else 30
      raw, kid = _api_create_key(target, days=days)
      return await event.reply("API key created (id %s) for user %s, valid %s days.\n\nKey (shown only once):\n%s"
                               % (kid, target, days, raw))
    return await event.reply("Use the admin panel: Admin > API Keys.\nQuick create: /apikey create <user_id|@username> [days]")
  except Exception as ex:
    logger.error("apikey command error: %s", ex, exc_info=True)
    await event.reply("Error: %s" % str(ex)[:200])


if __name__ == '__main__':
  try:
    try:
      _loop = asyncio.get_event_loop()
    except RuntimeError:
      _loop = asyncio.new_event_loop()
      asyncio.set_event_loop(_loop)
    _loop.run_until_complete(_run())
  except KeyboardInterrupt:
    pass
