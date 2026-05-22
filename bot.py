"""
╔══════════════════════════════════════════════════════════════════════════╗
║            TSR ADVANCED DISCORD BOT  ·  v4.0                            ║
║  Moderation · ModMail · Tickets · AutoMod · Anti-Nuke · Giveaways       ║
║  Honeypot · Invite Tracking · Stats Channels · Roblox Watcher v4        ║
║  Music (Spotify-style) · play/pause/skip/queue/loop/shuffle/volume       ║
║  Verification · Comprehensive Logging · AFK · Levels · Reminders        ║
╚══════════════════════════════════════════════════════════════════════════╝

Railway: Set BOT_TOKEN as a Railway environment variable.
All guild data is stored in the data/ folder (JSON files).
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime, asyncio, random, re, os, json, string, aiohttp, io, math
from typing import Optional

try:
    import yt_dlp
    YT_DLP_OK = True
except ImportError:
    YT_DLP_OK = False

try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    SPOTIPY_OK = True
except ImportError:
    SPOTIPY_OK = False

# ═══════════════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════════════

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set!")

OWNER_IDS_RAW = os.environ.get("OWNER_IDS", "")
OWNER_IDS = [int(x.strip()) for x in OWNER_IDS_RAW.split(",") if x.strip().isdigit()]

# ── Colours ─────────────────────────────────────────────────────────────────
C_RED     = 0xED4245
C_ORANGE  = 0xFEA832
C_YELLOW  = 0xFEE75C
C_GREEN   = 0x2ECC71
C_BLUE    = 0x3498DB
C_PURPLE  = 0x9B59B6
C_PINK    = 0xFF73FA
C_TEAL    = 0x1ABC9C
C_BLURPLE = 0x5865F2
C_DARK    = 0x2F3136
C_GOLD    = 0xF1C40F
C_NAVY    = 0x2C3E50

# ── Command permission groups ─────────────────────────────────────────────
# Admins manage these groups; members/verified get roles assigned to groups
CMD_GROUPS = {
    "moderation": ["ban","unban","kick","timeout","untimeout","warn","warnings",
                   "clearwarnings","delwarn","purge","slowmode","nick","role",
                   "softban","tempban","hardban","hardban_id","unhardban","hardbans",
                   "vcmute","vcunmute","deafen","undeafen","move","massrole",
                   "lock","unlock","lockdown","endlockdown","closeticket",
                   "mmclose","mmreply","modlogs","note","massban","case"],
    "utility":    ["userinfo","serverinfo","roleinfo","channelinfo","avatar","banner",
                   "ping","stats","snipe","editsnipe","say","embed","announce","poll",
                   "multipoll","inviteinfo","inviteleaderboard"],
    "music":      ["play","pause","resume","skip","stop","nowplaying","queue",
                   "volume","loop","shuffle","disconnect","search"],
    "community":  ["suggest","rank","leaderboard","afk","remind","8ball","coinflip",
                   "roll","choose","giveaway","greroll","gend","verify","getcode"],
    "setup":      ["setuplog","setupwelcome","setupgoodbye","setuplock","setupverify",
                   "setuptickets","setupautomod","setupmodmail","setuplevels",
                   "setupsuggestions","setuproblox","setupantinuke","setuphoneypot",
                   "setupstatschannels","setupmusic","antiraid","warnthreshold",
                   "badword","filterlist","setpermission","viewpermissions","help"],
}

# ═══════════════════════════════════════════════════════════════════════════
#  DATA PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

def _path(f): return os.path.join(DATA_DIR, f)
def load_json(f, default=None):
    p = _path(f)
    if os.path.exists(p):
        try:
            with open(p) as fp: return json.load(fp)
        except Exception: pass
    return default if default is not None else {}
def save_json(f, data):
    with open(_path(f), "w") as fp: json.dump(data, fp, indent=2)

warnings_db   = load_json("warnings.json")
guild_config  = load_json("guild_config.json")
hardban_db    = load_json("hardbans.json")
tempban_db    = load_json("tempbans.json")
giveaway_db   = load_json("giveaways.json")
levels_db     = load_json("levels.json")
afk_db        = load_json("afk.json")
reminders_db  = load_json("reminders.json", default=[])
suggestions_db= load_json("suggestions.json")
roblox_db     = load_json("roblox.json")
modmail_db    = load_json("modmail.json")
cmd_perms_db  = load_json("cmd_perms.json")   # {gid: {cmd_group: [role_ids]}}
antinuke_db   = load_json("antinuke.json")
invite_db     = load_json("invite_db.json")   # {gid: {inviter_id: {uses, members[]}}}
note_db       = load_json("note_db.json")     # {gid: {uid: [{text, author, ts}]}}
cases_db      = load_json("cases_db.json")    # {gid: [case dicts]}

snipe_db:      dict = {}
editsnipe_db:  dict = {}
antispam_db:   dict = {}
ANTISPAM_LIMIT  = 5
ANTISPAM_WINDOW = 5

# Anti-nuke tracking (in-memory, reset each run is fine)
nuke_tracker: dict = {}   # {gid: {uid: {action: [ts, ts, ...]}}}

# Invite cache: {gid: {code: uses}} — used to detect which invite was used on join
invite_cache: dict = {}

# Pending verification codes / math CAPTCHAs
pending_codes:  dict = {}   # uid -> code
pending_math:   dict = {}   # uid -> answer

XP_PER_MSG   = 15
XP_COOLDOWN  = 60
_xp_cooldown: dict = {}

# ═══════════════════════════════════════════════════════════════════════════
#  GUILD CONFIG
# ═══════════════════════════════════════════════════════════════════════════

_DEFAULTS = {
    "log_channel": None, "welcome_channel": None,
    "welcome_message": "Welcome {user} to **{server}**! You are member #{count}.",
    "goodbye_channel": None,
    "goodbye_message": "**{user}** has left the server. Goodbye!",
    "verify_channel": None, "verify_role": None, "verify_method": "button",
    "verify_message": "Click **Verify Me** to gain access to the server.",
    "verify_min_age_days": 0,
    "verify_require_phone": False,
    "lock_exempt_roles": [], "lock_deny_perm": "send_messages",
    # AutoMod (v4 expanded)
    "automod_links": False,
    "automod_caps": False,
    "automod_caps_pct": 80, "automod_caps_min": 10,
    "automod_badwords": [],
    "automod_exempt_roles": [],
    "automod_invites": False,           # block Discord server invites (discord.gg)
    "automod_mentions": False,          # block excessive @mentions
    "automod_mentions_limit": 5,        # max @mentions per message
    "automod_emojis": False,            # block emoji spam
    "automod_emojis_limit": 10,         # max emojis per message
    "automod_zalgo": False,             # block zalgo/unicode pollution text
    "automod_repeated_chars": False,    # block e.g. "aaaaaaaaa" runs
    "automod_repeated_limit": 8,        # char run length to trigger
    "automod_mass_caps_bypass": False,  # detect l33tspeak caps bypass (HeLLo)
    # Honeypot
    "honeypot_channels": [],            # list of channel IDs — anyone who types here gets actioned
    "honeypot_action": "softban",       # softban | ban | kick | timeout
    "honeypot_log": True,
    # Stats channels (voice channels with auto-updating names)
    "stat_ch_members": None,
    "stat_ch_online": None,
    "stat_ch_bots": None,
    "stat_ch_channels": None,
    "stat_ch_roles": None,
    # Tickets
    "ticket_channel": None, "ticket_category": None,
    "ticket_support_role": None, "ticket_transcript_channel": None,
    "ticket_message": "Click the button below to open a support ticket.",
    "ticket_count": 0,
    # ModMail
    "modmail_channel": None, "modmail_category": None, "modmail_log_channel": None,
    "suggestion_channel": None,
    "level_channel": None,
    "level_up_msg": "{user} levelled up to **Level {level}**! 🎉",
    # Roblox watcher (v4)
    "roblox_channel": None,
    "roblox_ping_role": None,           # role ID to ping on live update
    "roblox_future_ping_role": None,    # role ID to ping on future update
    "roblox_last_player_version": None,
    "roblox_last_studio_version": None,
    # Anti-nuke
    "antinuke_enabled": False,
    "antinuke_threshold_bans": 3,
    "antinuke_threshold_kicks": 5,
    "antinuke_threshold_channels": 3,
    "antinuke_threshold_roles": 3,
    "antinuke_threshold_webhooks": 3,
    "antinuke_anti_everyone": True,
    "antinuke_window": 10,
    "antinuke_action": "strip",
    "antinuke_whitelist": [],
    # Anti-Raid
    "antiraid_enabled": False,
    "antiraid_min_age_days": 7,
    "antiraid_action": "kick",          # kick | ban | timeout
    "antiraid_dm": True,
    # Auto-warn escalation
    "warn_thresholds": {},              # {"3": "timeout_1h", "5": "kick", "7": "ban"}
    # Music channel lock
    "music_channel": None,             # voice channel ID the bot should always stay in
    "music_auto_rejoin": True,         # auto-rejoin music_channel if kicked
}

def gcfg(guild_id: int) -> dict:
    gid = str(guild_id)
    guild_config.setdefault(gid, {})
    for k, v in _DEFAULTS.items():
        guild_config[gid].setdefault(k, v)
    return guild_config[gid]

def save_cfg(): save_json("guild_config.json", guild_config)

# ═══════════════════════════════════════════════════════════════════════════
#  BOT SETUP
# ═══════════════════════════════════════════════════════════════════════════

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

def now_utc(): return datetime.datetime.now(datetime.UTC)

# ═══════════════════════════════════════════════════════════════════════════
#  COMMAND PERMISSION SYSTEM
# ═══════════════════════════════════════════════════════════════════════════

def _get_cmd_group(cmd_name: str) -> Optional[str]:
    for group, cmds in CMD_GROUPS.items():
        if cmd_name in cmds:
            return group
    return None

def has_cmd_perm(interaction: discord.Interaction, cmd_name: str) -> bool:
    """
    Permission check for custom role-based command access.

    Rules (evaluated in order — first match wins):
      1. Bot owner → always allowed
      2. Server administrator → always allowed
      3. Individual command override configured → user must have that role
      4. Group configured → user must have a role in that group
      5. No config at all → pass through (Discord's native @default_permissions protects mod cmds)

    Intent: use /setpermission to GRANT community commands (rank, leaderboard, suggest…)
    to specific roles.  Moderation commands are always protected by Discord's own
    permission system (@app_commands.default_permissions) regardless of this check.
    """
    if interaction.user.id in OWNER_IDS:
        return True
    if interaction.user.guild_permissions.administrator:
        return True

    gid           = str(interaction.guild.id)
    group         = _get_cmd_group(cmd_name)
    perms         = cmd_perms_db.get(gid, {})
    user_role_ids = {str(r.id) for r in interaction.user.roles}

    # Individual command override takes highest priority
    if cmd_name in perms:
        return bool(user_role_ids & set(perms[cmd_name]))

    # Group-level check
    if group and group in perms:
        return bool(user_role_ids & set(perms[group]))

    # Nothing configured — pass through.
    # Moderation/setup commands are already gated by Discord's built-in
    # @app_commands.default_permissions so non-mods can't reach them anyway.
    return True

def perm_denied() -> discord.Embed:
    return _e_error("Permission Denied",
                    "You don't have permission to use this command.\n"
                    "Ask an admin to use `/setpermission` to grant access.")

# ═══════════════════════════════════════════════════════════════════════════
#  EMBED BUILDERS  (redesigned for v3)
# ═══════════════════════════════════════════════════════════════════════════

_BOT_ICON = None   # set in on_ready

def _stamp(e: discord.Embed) -> discord.Embed:
    e.timestamp = now_utc()
    return e

def _footer(e: discord.Embed, text: str = "TSR Bot") -> discord.Embed:
    e.set_footer(text=text)
    return _stamp(e)

def _e_success(title: str, desc: str = None, *, color: int = C_GREEN) -> discord.Embed:
    e = discord.Embed(title=f"✅  {title}", description=desc, color=color)
    return _footer(e)

def _e_error(title: str, desc: str = None) -> discord.Embed:
    e = discord.Embed(title=f"❌  {title}", description=desc, color=C_RED)
    return _footer(e)

def _e_info(title: str, desc: str = None, color: int = C_BLUE) -> discord.Embed:
    e = discord.Embed(title=title, description=desc, color=color)
    return _footer(e)

def _e_warn(title: str, desc: str = None) -> discord.Embed:
    e = discord.Embed(title=f"⚠️  {title}", description=desc, color=C_YELLOW)
    return _footer(e)

def _log_embed(
    action: str,
    color: int,
    *,
    icon: str = "📋",
    description: str = None,
    fields: list[tuple] = None,
    thumbnail: str = None,
    author_name: str = None,
    author_icon: str = None,
) -> discord.Embed:
    """Unified log embed — clean, consistent, readable."""
    e = discord.Embed(color=color, description=description)
    e.set_author(
        name=f"  {icon}  {action}",
        icon_url=author_icon
    )
    if thumbnail:
        e.set_thumbnail(url=thumbnail)
    if fields:
        for name, value, inline in fields:
            e.add_field(name=name, value=value, inline=inline)
    e.timestamp = now_utc()
    e.set_footer(text="TSR Log System")
    return e

def _mod_embed(
    action: str,
    icon: str,
    color: int,
    moderator: discord.Member,
    target,
    reason: str,
    extra: dict = None,
) -> discord.Embed:
    """Rich moderation log embed."""
    reason = reason or "No reason provided"
    e = discord.Embed(color=color)
    e.set_author(
        name=f"  {icon}  {action}",
        icon_url=moderator.guild.icon.url if moderator.guild.icon else None
    )
    if hasattr(target, "display_avatar"):
        e.set_thumbnail(url=target.display_avatar.url)

    e.description = (
        f"```yaml\n"
        f"Action   : {action}\n"
        f"Target   : {target} ({getattr(target,'id',target)})\n"
        f"Moderator: {moderator} ({moderator.id})\n"
        f"Reason   : {reason}\n"
        f"```"
    )
    e.add_field(
        name="👤  Target",
        value=f"{target.mention if hasattr(target,'mention') else target}\n`{target.id if hasattr(target,'id') else target}`",
        inline=True
    )
    e.add_field(
        name="🛡️  Moderator",
        value=f"{moderator.mention}\n`{moderator.id}`",
        inline=True
    )
    if extra:
        for k, v in extra.items():
            e.add_field(name=k, value=v, inline=True)
    e.add_field(name="📝  Reason", value=f"```{reason}```", inline=False)
    e.timestamp = now_utc()
    e.set_footer(text="TSR Moderation System")
    return e

# ═══════════════════════════════════════════════════════════════════════════
#  LOG CHANNEL HELPER
# ═══════════════════════════════════════════════════════════════════════════

async def send_log(guild: discord.Guild, embed: discord.Embed, content: str = None):
    cfg   = gcfg(guild.id)
    ch_id = cfg.get("log_channel")
    if not ch_id:
        return
    ch = guild.get_channel(int(ch_id))
    if ch:
        try:
            await ch.send(content=content, embed=embed)
        except Exception:
            pass

async def dm_user(user, embed: discord.Embed):
    try:
        await user.send(embed=embed)
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def warn_user(gid, uid, reason, mod_name):
    warnings_db.setdefault(gid, {}).setdefault(uid, [])
    warnings_db[gid][uid].append({
        "reason": reason, "moderator": mod_name,
        "time":   now_utc().strftime("%b %d %Y %H:%M UTC")
    })
    save_json("warnings.json", warnings_db)
    return len(warnings_db[gid][uid])

def parse_dur(s: str) -> Optional[datetime.timedelta]:
    m = re.match(r"^(\d+)([smhd])$", s.lower())
    if not m: return None
    v, u = int(m.group(1)), m.group(2)
    return {"s": datetime.timedelta(seconds=v), "m": datetime.timedelta(minutes=v),
            "h": datetime.timedelta(hours=v),   "d": datetime.timedelta(days=v)}[u]

def dur_str(td: datetime.timedelta) -> str:
    t = int(td.total_seconds())
    d, r = divmod(t, 86400); h, r = divmod(r, 3600); m, s = divmod(r, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s: parts.append(f"{s}s")
    return " ".join(parts) or "0s"

def xp_for_level(lvl): return 100 * (lvl ** 2)

def add_xp(gid, uid):
    key = f"{gid}:{uid}"; now = now_utc().timestamp()
    if now - _xp_cooldown.get(key, 0) < XP_COOLDOWN:
        data = levels_db.get(gid, {}).get(uid, {"xp": 0, "level": 0})
        return data["xp"], data["level"], False
    _xp_cooldown[key] = now
    levels_db.setdefault(gid, {}).setdefault(uid, {"xp": 0, "level": 0})
    entry = levels_db[gid][uid]; entry["xp"] += XP_PER_MSG
    up = False
    while entry["xp"] >= xp_for_level(entry["level"] + 1):
        entry["level"] += 1; up = True
    save_json("levels.json", levels_db)
    return entry["xp"], entry["level"], up

def is_automod_exempt(member: discord.Member) -> bool:
    cfg   = gcfg(member.guild.id)
    roles = [str(r.id) for r in member.roles]
    return (member.guild_permissions.manage_messages or
            any(r in roles for r in cfg.get("automod_exempt_roles", [])))

def is_whitelisted(member: discord.Member, cfg: dict) -> bool:
    """Check if a member is on the anti-nuke whitelist."""
    if member.guild_permissions.administrator:
        return True
    roles = [str(r.id) for r in member.roles]
    return any(r in roles for r in cfg.get("antinuke_whitelist", []))

# ═══════════════════════════════════════════════════════════════════════════
#  ANTI-NUKE ENGINE
# ═══════════════════════════════════════════════════════════════════════════

async def antinuke_check(guild: discord.Guild, user_id: int, action: str) -> bool:
    """
    Returns True if this action triggered the anti-nuke.
    action: 'ban' | 'kick' | 'channel_delete' | 'role_delete' | 'webhook_create'
    """
    cfg = gcfg(guild.id)
    if not cfg.get("antinuke_enabled"):
        return False
    # Whitelist check
    member = guild.get_member(user_id)
    if member:
        wl = cfg.get("antinuke_whitelist", [])
        if any(str(r.id) in wl for r in member.roles):
            return False
        if member.guild_permissions.administrator and user_id not in OWNER_IDS:
            pass  # admins can still trigger anti-nuke if they abuse it

    thresholds = {
        "ban":            cfg.get("antinuke_threshold_bans", 3),
        "kick":           cfg.get("antinuke_threshold_kicks", 5),
        "channel_delete": cfg.get("antinuke_threshold_channels", 3),
        "role_delete":    cfg.get("antinuke_threshold_roles", 3),
        "webhook_create": cfg.get("antinuke_threshold_webhooks", 3),
    }
    window = cfg.get("antinuke_window", 10)
    gid    = str(guild.id)
    uid    = str(user_id)
    now    = now_utc().timestamp()

    nuke_tracker.setdefault(gid, {}).setdefault(uid, {}).setdefault(action, [])
    # Prune old entries
    nuke_tracker[gid][uid][action] = [t for t in nuke_tracker[gid][uid][action] if now - t < window]
    nuke_tracker[gid][uid][action].append(now)

    count = len(nuke_tracker[gid][uid][action])
    limit = thresholds.get(action, 3)

    if count >= limit:
        nuke_tracker[gid][uid][action] = []  # reset to avoid repeated triggers
        await _trigger_antinuke(guild, user_id, action, count)
        return True
    return False

async def _trigger_antinuke(guild: discord.Guild, user_id: int, action: str, count: int,
                            reason: str = None, mode: str = "Enhanced"):
    cfg    = gcfg(guild.id)
    nk_act = cfg.get("antinuke_action", "strip")
    member = guild.get_member(user_id)

    action_label = {
        "ban": "Mass Ban",
        "kick": "Mass Kick",
        "channel_delete": "Mass Channel Delete",
        "role_delete": "Mass Role Delete",
        "webhook_create": "Mass Webhook Create",
        "everyone_ping": "Anti Everyone",
    }.get(action, action.replace("_"," ").title())

    reason_label = reason or {
        "ban": f"Performed {count} bans in {cfg.get('antinuke_window',10)}s",
        "kick": f"Performed {count} kicks in {cfg.get('antinuke_window',10)}s",
        "channel_delete": f"Deleted {count} channels in {cfg.get('antinuke_window',10)}s",
        "role_delete": f"Deleted {count} roles in {cfg.get('antinuke_window',10)}s",
        "webhook_create": f"Created {count} webhooks in {cfg.get('antinuke_window',10)}s",
        "everyone_ping": "Unauthorized @everyone/@here ping",
    }.get(action, "Automated anti-nuke response")

    # Determine what roles were stripped for the action field
    removable = []
    action_taken_str = nk_act.title()
    if member and nk_act in ("strip", "strip+ban"):
        removable = [r for r in member.roles if not r.is_default() and not r.managed and r < guild.me.top_role]
        stripped_names = ", ".join(r.name for r in removable[:6])
        if len(removable) > 6:
            stripped_names += f" +{len(removable)-6} more"
        action_taken_str = f"Removed {len(removable)} role(s) [{stripped_names}]"
        if nk_act in ("strip+ban", "ban"):
            action_taken_str += " + Banned"

    # Build embed matching the screenshot style
    log_e = discord.Embed(color=C_RED)
    log_e.set_author(name="✅  AntiNuke Action", icon_url=guild.icon.url if guild.icon else None)
    log_e.add_field(name="Event Type",  value=f"`{action_label}`",     inline=True)
    log_e.add_field(name="Mode",        value=f"`{mode}`",              inline=True)
    log_e.add_field(name="Action",      value=action_taken_str,         inline=False)
    log_e.add_field(name="Executor",
                    value=f"<@{user_id}> (`{user_id}`)",               inline=False)
    log_e.add_field(name="Reason",      value=reason_label,             inline=False)
    log_e.set_footer(text=f"Guild ID: {guild.id}")
    log_e.timestamp = now_utc()
    await send_log(guild, log_e)

    # DM owner
    if guild.owner:
        dm_e = discord.Embed(
            title="🚨  Anti-Nuke Alert",
            description=(
                f"**Threat detected in {guild.name}**\n\n"
                f"**Type:** `{action_label}`\n"
                f"**User:** <@{user_id}> (`{user_id}`)\n"
                f"**Reason:** {reason_label}\n"
                f"**Action taken:** {action_taken_str}"
            ),
            color=C_RED
        )
        dm_e.timestamp = now_utc()
        await dm_user(guild.owner, dm_e)

    if not member:
        return

    if nk_act in ("strip", "strip+ban"):
        if removable:
            try:
                await member.remove_roles(*removable, reason=f"Anti-Nuke: {reason_label}")
            except Exception:
                pass
        if nk_act == "strip+ban":
            try:
                await member.ban(reason=f"Anti-Nuke: {reason_label}", delete_message_days=0)
            except Exception:
                pass
    elif nk_act == "kick":
        try:
            await member.kick(reason=f"Anti-Nuke: {reason_label}")
        except Exception:
            pass
    elif nk_act == "ban":
        try:
            await member.ban(reason=f"Anti-Nuke: {reason_label}", delete_message_days=0)
        except Exception:
            pass

# ═══════════════════════════════════════════════════════════════════════════
#  EVENTS
# ═══════════════════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    global _BOT_ICON
    _BOT_ICON = str(bot.user.display_avatar.url)
    await bot.tree.sync()
    bot.add_view(VerifyButton())
    bot.add_view(TicketButton())
    bot.add_view(TicketCloseView())
    bot.add_view(GiveawayView())
    bot.add_view(SuggestionVoteView())
    # Cache all guild invites for invite tracking
    for guild in bot.guilds:
        try:
            invites = await guild.invites()
            invite_cache[str(guild.id)] = {inv.code: inv.uses for inv in invites}
        except Exception:
            invite_cache[str(guild.id)] = {}
    status_loop.start()
    check_tempbans.start()
    check_reminders.start()
    check_roblox.start()
    update_stat_channels.start()
    print(f"\n{'═'*55}")
    print(f"  🤖  Online: {bot.user} (v4.0)")
    print(f"  Servers : {len(bot.guilds)}")
    print(f"  Invites : cached for {len(invite_cache)} guilds")
    print(f"{'═'*55}\n")

@tasks.loop(seconds=30)
async def status_loop():
    choices = [
        discord.Activity(type=discord.ActivityType.watching,
                         name=f"{sum(g.member_count for g in bot.guilds):,} members"),
        discord.Activity(type=discord.ActivityType.playing,   name="Use /help"),
        discord.Activity(type=discord.ActivityType.watching,  name="over the server 👀"),
        discord.Activity(type=discord.ActivityType.listening, name="your slash commands"),
    ]
    await bot.change_presence(activity=random.choice(choices), status=discord.Status.online)

@tasks.loop(seconds=60)
async def check_tempbans():
    now = now_utc().timestamp()
    removes = []
    for gid, bans in tempban_db.items():
        for uid, data in list(bans.items()):
            if now >= data["expires"]:
                guild = bot.get_guild(int(gid))
                if guild:
                    try:
                        user = await bot.fetch_user(int(uid))
                        await guild.unban(user, reason="Temp-ban expired")
                        await send_log(guild, _log_embed(
                            "TempBan Expired", C_GREEN, icon="⏳",
                            fields=[("👤  User", f"{user} (`{user.id}`)", True),
                                    ("📋  Was banned by", data.get("moderator","?"), True)]))
                    except Exception: pass
                removes.append((gid, uid))
    for gid, uid in removes:
        tempban_db.get(gid, {}).pop(uid, None)
    if removes: save_json("tempbans.json", tempban_db)

@tasks.loop(seconds=30)
async def check_reminders():
    now = now_utc().timestamp()
    remaining = []
    changed   = False
    for r in reminders_db:
        if now >= r["remind_at"]:
            try:
                user = await bot.fetch_user(r["user_id"])
                e = discord.Embed(
                    title="⏰  Reminder!",
                    description=r["message"],
                    color=C_YELLOW
                )
                e.set_footer(text=f"You asked to be reminded {r['set_ago']} ago")
                await user.send(embed=e)
            except Exception: pass
            changed = True
        else:
            remaining.append(r)
    if changed:
        reminders_db.clear(); reminders_db.extend(remaining)
        save_json("reminders.json", reminders_db)

async def _fetch_roblox_version(platform: str) -> Optional[str]:
    """Fetch current version hash from Roblox clientsettings CDN."""
    url = f"https://clientsettingscdn.roblox.com/v2/client-version/{platform}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                return data.get("clientVersionUpload") or data.get("version")
    except Exception:
        return None

@tasks.loop(minutes=3)
async def check_roblox():
    """
    Roblox Update Watcher v4
    - WindowsPlayer = the live version players use
    - WindowsStudio  = ahead of player — signals a future/pending update
    When Studio has a newer version than Player → "Future Update" (yellow warning)
    When Player version changes               → "Live Update"   (red siren)
    """
    player_ver = await _fetch_roblox_version("WindowsPlayer")
    studio_ver = await _fetch_roblox_version("WindowsStudio64")

    if not player_ver:
        return

    now_ts = now_utc()
    date_str = now_ts.strftime("%A, %B %d, %Y %I:%M %p")
    short_ts = now_ts.strftime("%m/%d/%Y %I:%M %p")

    for gid, cfg in guild_config.items():
        ch_id = cfg.get("roblox_channel")
        if not ch_id:
            continue
        guild = bot.get_guild(int(gid))
        if not guild:
            continue
        ch = guild.get_channel(int(ch_id))
        if not ch:
            continue

        stored_player = cfg.get("roblox_last_player_version")
        stored_studio = cfg.get("roblox_last_studio_version")

        ping_role_id        = cfg.get("roblox_ping_role")
        future_ping_role_id = cfg.get("roblox_future_ping_role")

        # ── Future update: studio has a version the player doesn't have yet ──
        if studio_ver and studio_ver != player_ver and studio_ver != stored_studio:
            ping_content = None
            if future_ping_role_id:
                r = guild.get_role(int(future_ping_role_id))
                if r:
                    ping_content = r.mention
            e = discord.Embed(
                title="⚠️  A Future Roblox Update Has Been Detected!",
                description="This is a future update, it has not yet reached the Windows Player.",
                color=C_YELLOW
            )
            e.add_field(name="**Platform**",      value="Windows Studio (Pre-release)", inline=False)
            e.add_field(name="**Version Hash**",  value=f"`{studio_ver}`",              inline=False)
            e.add_field(name="**Date**",          value=f"{date_str}\n\n{short_ts}",    inline=False)
            dl_url = f"https://setup.rbxcdn.com/{studio_ver}-RobloxStudioLauncher.exe"
            e.add_field(name="**Download**",      value=f"[Click to download]({dl_url})", inline=False)
            e.set_footer(text="TSR Roblox Watcher v4  •  Future update — not live yet")
            e.timestamp = now_ts
            try:
                await ch.send(content=ping_content, embed=e)
            except Exception:
                pass
            cfg["roblox_last_studio_version"] = studio_ver

        # ── Live update: player version changed ──
        if stored_player and stored_player != player_ver:
            ping_content = None
            if ping_role_id:
                r = guild.get_role(int(ping_role_id))
                if r:
                    ping_content = r.mention
            e = discord.Embed(
                title="🚨  Roblox Update Detected!",
                description="This is a **live update** — all Windows Player clients will update shortly.",
                color=C_RED
            )
            e.add_field(name="**Platform**",      value="Windows Player (Live)",        inline=False)
            e.add_field(name="**Version Hash**",  value=f"`{player_ver}`",              inline=False)
            e.add_field(name="**Date**",          value=f"{date_str}\n\n{short_ts}",    inline=False)
            dl_url = f"https://setup.rbxcdn.com/{player_ver}-RobloxPlayerLauncher.exe"
            e.add_field(name="**Download**",      value=f"[Click to download]({dl_url})", inline=False)
            e.set_footer(text="TSR Roblox Watcher v4  •  Live update detected")
            e.timestamp = now_ts
            try:
                await ch.send(content=ping_content, embed=e)
            except Exception:
                pass

        # Always update stored player version
        cfg["roblox_last_player_version"] = player_ver
        if studio_ver:
            cfg["roblox_last_studio_version"] = studio_ver

    save_cfg()

@tasks.loop(minutes=10)
async def update_stat_channels():
    """Auto-update voice channel name stats every 10 minutes."""
    for gid, cfg in guild_config.items():
        guild = bot.get_guild(int(gid))
        if not guild:
            continue
        stats = {
            "stat_ch_members":  f"👥 Members: {guild.member_count:,}",
            "stat_ch_online":   f"🟢 Online: {sum(1 for m in guild.members if m.status != discord.Status.offline and not m.bot):,}",
            "stat_ch_bots":     f"🤖 Bots: {sum(1 for m in guild.members if m.bot):,}",
            "stat_ch_channels": f"💬 Channels: {len(guild.channels):,}",
            "stat_ch_roles":    f"🎭 Roles: {len(guild.roles):,}",
        }
        for key, name in stats.items():
            ch_id = cfg.get(key)
            if not ch_id:
                continue
            ch = guild.get_channel(int(ch_id))
            if ch and ch.name != name:
                try:
                    await ch.edit(name=name)
                except Exception:
                    pass

# ── Member Events ──────────────────────────────────────────────────────────

@bot.event
async def on_member_join(member: discord.Member):
    gid = str(member.guild.id)
    uid = str(member.id)
    hb  = hardban_db.get(gid, {}).get(uid)
    if hb:
        try:
            await member.send(embed=discord.Embed(
                title=f"⛔  Hardbanned from {member.guild.name}",
                description=f"**Reason:** {hb.get('reason','No reason')}",
                color=C_RED))
        except Exception: pass
        await member.ban(reason=f"Hardban: {hb.get('reason','')}", delete_message_days=0)
        return

    # ── Anti-Raid: new account gate ────────────────────────────────────────
    cfg_join = gcfg(member.guild.id)
    if cfg_join.get("antiraid_enabled"):
        min_days   = cfg_join.get("antiraid_min_age_days", 7)
        acct_age   = (datetime.datetime.utcnow() - member.created_at.replace(tzinfo=None)).days
        if acct_age < min_days:
            ar_act = cfg_join.get("antiraid_action", "kick")
            reason = f"Anti-Raid: Account is {acct_age}d old (minimum {min_days}d)"
            if cfg_join.get("antiraid_dm", True):
                try:
                    await member.send(embed=discord.Embed(
                        title=f"🛡️  Blocked from {member.guild.name}",
                        description=f"Your account is too new to join.\n**Reason:** {reason}",
                        color=C_ORANGE))
                except Exception: pass
            try:
                if ar_act == "kick":
                    await member.kick(reason=reason)
                elif ar_act == "ban":
                    await member.ban(reason=reason, delete_message_days=0)
                elif ar_act == "timeout":
                    await member.timeout(datetime.timedelta(hours=24), reason=reason)
            except Exception: pass
            await send_log(member.guild, _log_embed(
                "🛡️  Anti-Raid Triggered", C_ORANGE, icon="🛡️",
                thumbnail=member.display_avatar.url,
                fields=[
                    ("👤  User",    f"{member.mention} `{member.id}`", True),
                    ("📅  Age",     f"{acct_age} day(s)",              True),
                    ("⚡  Action",  ar_act.title(),                    True),
                ]
            ))
            return

    # ── Invite tracking ────────────────────────────────────────────────────
    used_invite = None
    used_inviter = None
    try:
        invites_after = await member.guild.invites()
        old_cache = invite_cache.get(gid, {})
        for inv in invites_after:
            if inv.uses > old_cache.get(inv.code, 0):
                used_invite = inv
                used_inviter = inv.inviter
                break
        invite_cache[gid] = {inv.code: inv.uses for inv in invites_after}
        if used_inviter:
            inv_gid = invite_db.setdefault(gid, {})
            inv_uid = inv_gid.setdefault(str(used_inviter.id), {"uses": 0, "members": []})
            inv_uid["uses"] += 1
            inv_uid["members"].append(uid)
            save_json("invite_db.json", invite_db)
    except Exception:
        pass

    cfg   = gcfg(member.guild.id)
    ch_id = cfg.get("welcome_channel")
    if ch_id:
        ch = member.guild.get_channel(int(ch_id))
        if ch:
            msg = (cfg.get("welcome_message")
                   .replace("{user}", member.mention)
                   .replace("{username}", str(member))
                   .replace("{server}", member.guild.name)
                   .replace("{count}", str(member.guild.member_count)))
            e = discord.Embed(description=msg, color=C_BLUE)
            e.set_author(name=f"Welcome to {member.guild.name}!", icon_url=member.guild.icon.url if member.guild.icon else None)
            e.set_thumbnail(url=member.display_avatar.url)
            e.add_field(name="📅  Account Age", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
            e.add_field(name="👥  Member #",    value=str(member.guild.member_count), inline=True)
            if used_inviter:
                e.add_field(name="📨  Invited By", value=f"{used_inviter.mention} (`{used_invite.code}`)", inline=True)
            e.set_footer(text="TSR Bot  •  Member Join")
            e.timestamp = now_utc()
            await ch.send(embed=e)

    invite_field = f"{used_inviter.mention} via `{used_invite.code}`" if used_inviter else "Unknown"
    await send_log(member.guild, _log_embed(
        "Member Joined", C_GREEN, icon="📥",
        thumbnail=member.display_avatar.url,
        fields=[
            ("👤  User",           f"{member.mention}\n`{member}` • `{member.id}`",  True),
            ("📅  Account Created", f"<t:{int(member.created_at.timestamp())}:R>",   True),
            ("👥  Total Members",   str(member.guild.member_count),                  True),
            ("📨  Invited By",      invite_field,                                    True),
        ]
    ))

@bot.event
async def on_member_remove(member: discord.Member):
    cfg   = gcfg(member.guild.id)
    ch_id = cfg.get("goodbye_channel")
    if ch_id:
        ch = member.guild.get_channel(int(ch_id))
        if ch:
            msg = (cfg.get("goodbye_message")
                   .replace("{user}", str(member))
                   .replace("{username}", str(member))
                   .replace("{server}", member.guild.name))
            e = discord.Embed(description=msg, color=C_ORANGE)
            e.set_thumbnail(url=member.display_avatar.url)
            e.set_footer(text="TSR Bot  •  Member Leave")
            e.timestamp = now_utc()
            await ch.send(embed=e)

    await send_log(member.guild, _log_embed(
        "Member Left", C_ORANGE, icon="📤",
        thumbnail=member.display_avatar.url,
        fields=[
            ("👤  User",    f"`{member}` • `{member.id}`", True),
            ("🎭  Roles",   ", ".join(r.mention for r in member.roles if not r.is_default())[:200] or "None", False),
        ]
    ))

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    # Role changes
    added   = [r for r in after.roles  if r not in before.roles]
    removed = [r for r in before.roles if r not in after.roles]
    if added or removed:
        fields = []
        if added:   fields.append(("➕  Roles Added",   " ".join(r.mention for r in added),   True))
        if removed: fields.append(("➖  Roles Removed", " ".join(r.mention for r in removed), True))
        fields.append(("👤  User", f"{after.mention} `{after.id}`", True))
        await send_log(after.guild, _log_embed(
            "Member Roles Updated", C_BLUE, icon="🎭",
            thumbnail=after.display_avatar.url,
            fields=fields
        ))
    # Nickname changes
    if before.nick != after.nick:
        await send_log(after.guild, _log_embed(
            "Nickname Changed", C_YELLOW, icon="✏️",
            thumbnail=after.display_avatar.url,
            fields=[
                ("👤  User",    f"{after.mention} `{after.id}`", False),
                ("📛  Before",  f"`{before.nick or before.name}`", True),
                ("📛  After",   f"`{after.nick or after.name}`",   True),
            ]
        ))

@bot.event
async def on_member_ban(guild: discord.Guild, user):
    # Anti-nuke tracking
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
        if entry.target and entry.target.id == user.id:
            await antinuke_check(guild, entry.user.id, "ban")
            break

@bot.event
async def on_member_unban(guild: discord.Guild, user):
    await send_log(guild, _log_embed(
        "Member Unbanned", C_GREEN, icon="🔓",
        fields=[("👤  User", f"`{user}` • `{user.id}`", True)]
    ))

@bot.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel):
    await send_log(channel.guild, _log_embed(
        "Channel Created", C_GREEN, icon="📢",
        fields=[
            ("📂  Name",     channel.mention,                 True),
            ("🏷️  Type",     str(channel.type).title(),       True),
            ("📁  Category", channel.category.name if channel.category else "None", True),
        ]
    ))

@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    # Anti-nuke tracking
    async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
        if entry.target and entry.target.id == channel.id:
            await antinuke_check(channel.guild, entry.user.id, "channel_delete")
            break
    await send_log(channel.guild, _log_embed(
        "Channel Deleted", C_RED, icon="🗑️",
        fields=[
            ("📂  Name",     f"`#{channel.name}`",            True),
            ("🏷️  Type",     str(channel.type).title(),       True),
            ("📁  Category", channel.category.name if channel.category else "None", True),
        ]
    ))

@bot.event
async def on_guild_channel_update(before, after):
    changes = []
    if before.name != after.name:
        changes.append(("📛  Name", f"`{before.name}` → `{after.name}`", True))
    if hasattr(before, "topic") and before.topic != after.topic:
        changes.append(("📝  Topic", f"*changed*", True))
    if hasattr(before, "slowmode_delay") and before.slowmode_delay != after.slowmode_delay:
        changes.append(("🐢  Slowmode", f"{before.slowmode_delay}s → {after.slowmode_delay}s", True))
    if changes:
        await send_log(after.guild, _log_embed(
            "Channel Updated", C_YELLOW, icon="✏️",
            fields=[("📂  Channel", after.mention, False)] + changes
        ))

@bot.event
async def on_guild_role_create(role: discord.Role):
    await send_log(role.guild, _log_embed(
        "Role Created", C_GREEN, icon="🎭",
        fields=[
            ("🏷️  Name",  role.mention, True),
            ("🎨  Color", str(role.color), True),
        ]
    ))

@bot.event
async def on_guild_role_delete(role: discord.Role):
    async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
        if entry.target and entry.target.id == role.id:
            await antinuke_check(role.guild, entry.user.id, "role_delete")
            break
    await send_log(role.guild, _log_embed(
        "Role Deleted", C_RED, icon="🗑️",
        fields=[
            ("🏷️  Name",  f"`{role.name}`", True),
            ("🎨  Color", str(role.color),  True),
        ]
    ))

@bot.event
async def on_guild_role_update(before: discord.Role, after: discord.Role):
    changes = []
    if before.name != after.name:
        changes.append(("📛  Name",  f"`{before.name}` → `{after.name}`",     True))
    if before.color != after.color:
        changes.append(("🎨  Color", f"`{before.color}` → `{after.color}`",   True))
    if before.permissions != after.permissions:
        changes.append(("🔑  Permissions", "*permissions changed*", True))
    if changes:
        await send_log(after.guild, _log_embed(
            "Role Updated", C_YELLOW, icon="✏️",
            fields=[("🎭  Role", after.mention, False)] + changes
        ))

@bot.event
async def on_invite_create(invite: discord.Invite):
    # Update cache
    gid = str(invite.guild.id)
    invite_cache.setdefault(gid, {})[invite.code] = invite.uses
    await send_log(invite.guild, _log_embed(
        "Invite Created", C_TEAL, icon="🔗",
        fields=[
            ("🔗  Code",     f"`{invite.code}`",                                          True),
            ("👤  Creator",  f"{invite.inviter.mention if invite.inviter else 'Unknown'}", True),
            ("📌  Channel",  invite.channel.mention if invite.channel else "?",            True),
            ("🔢  Max Uses", str(invite.max_uses) if invite.max_uses else "∞",            True),
            ("⏱️  Expires",  f"<t:{int((now_utc()+datetime.timedelta(seconds=invite.max_age)).timestamp())}:R>" if invite.max_age else "Never", True),
        ]
    ))

@bot.event
async def on_invite_delete(invite: discord.Invite):
    # Update cache
    gid = str(invite.guild.id)
    invite_cache.get(gid, {}).pop(invite.code, None)
    await send_log(invite.guild, _log_embed(
        "Invite Deleted", C_ORANGE, icon="🚫",
        fields=[("🔗  Code", f"`{invite.code}`", True)]
    ))

@bot.event
async def on_webhooks_update(channel: discord.TextChannel):
    # Anti-nuke: detect webhook creation
    async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.webhook_create):
        await antinuke_check(channel.guild, entry.user.id, "webhook_create")
        break

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if before.channel is None and after.channel is not None:
        log = f"{member.mention} joined **{after.channel.name}**"
        icon, col = "🔊", C_GREEN
    elif before.channel is not None and after.channel is None:
        log = f"{member.mention} left **{before.channel.name}**"
        icon, col = "🔇", C_ORANGE
    elif before.channel != after.channel:
        log = f"{member.mention} moved **{before.channel.name}** → **{after.channel.name}**"
        icon, col = "🔀", C_YELLOW
    else:
        return
    await send_log(member.guild, _log_embed(
        "Voice State Update", col, icon=icon,
        thumbnail=member.display_avatar.url,
        fields=[("👤  Member", f"`{member}`", True), ("📝  Detail", log, False)]
    ))

@bot.event
async def on_message_delete(message: discord.Message):
    if message.author.bot or not message.guild: return
    gid = str(message.guild.id)
    snipe_db[gid] = {
        "content": message.content, "author": str(message.author),
        "author_id": message.author.id, "avatar": str(message.author.display_avatar.url),
        "channel": message.channel.id, "time": now_utc().timestamp()
    }
    if message.content:
        await send_log(message.guild, _log_embed(
            "Message Deleted", C_ORANGE, icon="🗑️",
            thumbnail=message.author.display_avatar.url,
            fields=[
                ("👤  Author",  f"{message.author.mention} `{message.author}`",  True),
                ("📂  Channel", message.channel.mention,                         True),
                ("📝  Content", f"```{message.content[:900]}```",                False),
            ]
        ))

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if before.author.bot or not before.guild or before.content == after.content: return
    gid = str(before.guild.id)
    editsnipe_db[gid] = {
        "before": before.content, "after": after.content,
        "author": str(before.author), "author_id": before.author.id,
        "avatar": str(before.author.display_avatar.url),
        "channel": before.channel.id, "time": now_utc().timestamp(),
        "jump_url": after.jump_url,
    }
    await send_log(before.guild, _log_embed(
        "Message Edited", C_YELLOW, icon="✏️",
        thumbnail=before.author.display_avatar.url,
        fields=[
            ("👤  Author",  f"{before.author.mention} `{before.author}`", False),
            ("📂  Channel", before.channel.mention, True),
            ("🔗  Jump",    f"[View message]({after.jump_url})",          True),
            ("📝  Before",  f"```{before.content[:400] or '(empty)'}```", False),
            ("📝  After",   f"```{after.content[:400] or '(empty)'}```",  False),
        ]
    ))

# ── Main message handler ───────────────────────────────────────────────────

@bot.event
async def on_message(message: discord.Message):
    # DM → ModMail
    if not message.guild and not message.author.bot:
        await _handle_modmail_dm(message)
        return

    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return

    guild_id = str(message.guild.id)
    user_id  = str(message.author.id)
    now      = now_utc().timestamp()
    cfg      = gcfg(message.guild.id)

    # AFK return
    gafk = afk_db.get(guild_id, {})
    if user_id in gafk:
        del gafk[user_id]
        afk_db[guild_id] = gafk
        save_json("afk.json", afk_db)
        try:
            await message.channel.send(
                embed=_e_success("Welcome Back!", f"{message.author.mention}, your AFK has been removed."),
                delete_after=6)
        except Exception: pass
        try:
            nick = message.author.display_name
            if nick.startswith("[AFK] "): nick = nick[6:]
            await message.author.edit(nick=nick)
        except Exception: pass

    # Notify when pinging an AFK user
    for m in message.mentions:
        mid = str(m.id)
        if mid in gafk:
            d = gafk[mid]
            e = discord.Embed(
                title="💤  User is AFK",
                description=(f"{m.mention} is AFK.\n"
                             f"**Reason:** {d.get('reason','AFK')}\n"
                             f"**Since:** <t:{int(d.get('since',now))}:R>"),
                color=C_YELLOW
            )
            await message.channel.send(embed=e, delete_after=10)

    # XP
    xp, level, levelled = add_xp(guild_id, user_id)
    if levelled:
        lvl_ch_id = cfg.get("level_channel")
        lvl_ch    = message.guild.get_channel(int(lvl_ch_id)) if lvl_ch_id else message.channel
        msg_text  = (cfg.get("level_up_msg", "{user} levelled up to **Level {level}**! 🎉")
                     .replace("{user}", message.author.mention).replace("{level}", str(level)))
        e = discord.Embed(title="🏅  Level Up!", description=msg_text, color=C_PINK)
        e.set_thumbnail(url=message.author.display_avatar.url)
        e.add_field(name="✨  XP",    value=f"{xp:,}", inline=True)
        e.add_field(name="🏅  Level", value=str(level), inline=True)
        try: await lvl_ch.send(embed=e)
        except Exception: pass

    # Anti-spam
    antispam_db.setdefault(guild_id, {}).setdefault(user_id, [])
    antispam_db[guild_id][user_id] = [t for t in antispam_db[guild_id][user_id] if now - t < ANTISPAM_WINDOW]
    antispam_db[guild_id][user_id].append(now)
    if len(antispam_db[guild_id][user_id]) >= ANTISPAM_LIMIT and not is_automod_exempt(message.author):
        antispam_db[guild_id][user_id] = []
        try: await message.channel.purge(limit=ANTISPAM_LIMIT, check=lambda m: m.author == message.author)
        except Exception: pass
        try: await message.author.timeout(datetime.timedelta(minutes=5), reason="AutoMod: Spam")
        except Exception: pass
        warn_user(guild_id, user_id, "AutoMod: Spamming", "AutoMod")
        e = discord.Embed(
            title="⚡  Anti-Spam Triggered",
            description=f"{message.author.mention} was **timed out 5 minutes** for spamming.",
            color=C_ORANGE
        )
        e.set_footer(text="AutoMod System")
        await message.channel.send(embed=e, delete_after=8)
        await send_log(message.guild, _log_embed(
            "AutoMod: Spam Detected", C_ORANGE, icon="⚡",
            thumbnail=message.author.display_avatar.url,
            fields=[
                ("👤  User",    f"{message.author.mention} `{message.author.id}`", True),
                ("📂  Channel", message.channel.mention,                           True),
                ("⏱️  Timeout", "5 minutes",                                       True),
            ]
        ))
        await bot.process_commands(message)
        return

    # ── Honeypot check ─────────────────────────────────────────────────────
    honeypot_channels = [str(c) for c in cfg.get("honeypot_channels", [])]
    _hp_exempt = (message.author.guild_permissions.administrator or
                  message.author.guild_permissions.ban_members or
                  message.author.guild_permissions.manage_guild)
    if honeypot_channels and str(message.channel.id) in honeypot_channels and not _hp_exempt:
        hp_action = cfg.get("honeypot_action", "softban")
        reason    = f"Honeypot channel triggered (#{message.channel.name})"
        try: await message.delete()
        except Exception: pass
        if hp_action == "softban":
            try:
                await message.guild.ban(message.author, reason=reason, delete_message_days=1)
                await message.guild.unban(message.author, reason="Softban cleanup")
            except Exception: pass
        elif hp_action == "ban":
            try: await message.guild.ban(message.author, reason=reason, delete_message_days=0)
            except Exception: pass
        elif hp_action == "kick":
            try: await message.author.kick(reason=reason)
            except Exception: pass
        elif hp_action == "timeout":
            try: await message.author.timeout(datetime.timedelta(hours=24), reason=reason)
            except Exception: pass
        if cfg.get("honeypot_log", True):
            await send_log(message.guild, _log_embed(
                "🍯  Honeypot Triggered", C_RED, icon="🍯",
                thumbnail=message.author.display_avatar.url,
                fields=[
                    ("👤  User",    f"{message.author.mention} `{message.author.id}`", True),
                    ("📂  Channel", message.channel.mention,                           True),
                    ("⚡  Action",  hp_action.title(),                                 True),
                    ("📝  Content", f"```{message.content[:300] or '(no text)'}```",   False),
                ]
            ))
        await bot.process_commands(message)
        return

    # ── Anti-nuke: @everyone/@here detection ───────────────────────────────
    if (cfg.get("antinuke_enabled") and cfg.get("antinuke_anti_everyone", True)
            and (message.mention_everyone)
            and not is_whitelisted(message.author, cfg)):
        # Check if user has Mention Everyone permission from roles
        has_perm = (message.author.guild_permissions.mention_everyone or
                    message.author.guild_permissions.administrator)
        if not has_perm:
            await _trigger_antinuke(message.guild, message.author.id, "everyone_ping", 1,
                                    reason="Unauthorized @everyone/@here ping")
            try: await message.delete()
            except Exception: pass
            await bot.process_commands(message)
            return

    if not is_automod_exempt(message.author):
        content = message.content

        # Anti-links
        if cfg.get("automod_links") and re.search(r"(https?://|discord\.gg/|www\.)", content, re.I):
            try: await message.delete()
            except Exception: pass
            await message.channel.send(
                embed=discord.Embed(title="🚫  Links Blocked",
                                    description=f"{message.author.mention}, links are not allowed here.",
                                    color=C_RED),
                delete_after=6)
            await send_log(message.guild, _log_embed(
                "AutoMod: Link Blocked", C_RED, icon="🔗",
                thumbnail=message.author.display_avatar.url,
                fields=[
                    ("👤  User",    f"{message.author.mention}", True),
                    ("📂  Channel", message.channel.mention,     True),
                    ("📝  Content", f"```{content[:300]}```",    False),
                ]
            ))
            await bot.process_commands(message)
            return

        # Anti-invites (discord.gg links)
        if cfg.get("automod_invites") and re.search(r"discord\.(gg|com/invite)/[a-zA-Z0-9-]+", content, re.I):
            try: await message.delete()
            except Exception: pass
            await message.channel.send(
                embed=discord.Embed(title="🚫  Invites Blocked",
                                    description=f"{message.author.mention}, Discord server invites are not allowed here.",
                                    color=C_RED),
                delete_after=6)
            await send_log(message.guild, _log_embed(
                "AutoMod: Invite Blocked", C_RED, icon="📩",
                thumbnail=message.author.display_avatar.url,
                fields=[
                    ("👤  User",    f"{message.author.mention}", True),
                    ("📂  Channel", message.channel.mention,     True),
                    ("📝  Content", f"```{content[:200]}```",    False),
                ]
            ))
            await bot.process_commands(message)
            return

        # Anti-mentions
        if cfg.get("automod_mentions"):
            mention_count = len(message.mentions) + len(message.role_mentions)
            if mention_count > cfg.get("automod_mentions_limit", 5):
                try: await message.delete()
                except Exception: pass
                try: await message.author.timeout(datetime.timedelta(minutes=5), reason="AutoMod: Mass mentions")
                except Exception: pass
                await message.channel.send(
                    embed=discord.Embed(title="🚫  Too Many Mentions",
                                        description=f"{message.author.mention}, you mentioned {mention_count} users/roles at once.",
                                        color=C_RED),
                    delete_after=6)
                await send_log(message.guild, _log_embed(
                    "AutoMod: Mass Mention", C_RED, icon="@",
                    thumbnail=message.author.display_avatar.url,
                    fields=[
                        ("👤  User",     f"{message.author.mention}", True),
                        ("📂  Channel",  message.channel.mention,     True),
                        ("🔢  Mentions", str(mention_count),          True),
                    ]
                ))
                await bot.process_commands(message)
                return

        # Anti-emoji spam
        if cfg.get("automod_emojis"):
            # Match unicode emoji + custom discord emoji
            emoji_count = len(re.findall(
                r"[\U0001F300-\U0001FAFF\U00002702-\U000027B0\U0000FE00-\U0000FEFF]|<a?:[^:]+:\d+>",
                content))
            if emoji_count > cfg.get("automod_emojis_limit", 10):
                try: await message.delete()
                except Exception: pass
                await message.channel.send(
                    embed=discord.Embed(title="🚫  Emoji Spam",
                                        description=f"{message.author.mention}, please don't spam emojis ({emoji_count} found).",
                                        color=C_RED),
                    delete_after=6)
                await send_log(message.guild, _log_embed(
                    "AutoMod: Emoji Spam", C_ORANGE, icon="😀",
                    thumbnail=message.author.display_avatar.url,
                    fields=[
                        ("👤  User",    f"{message.author.mention}", True),
                        ("📂  Channel", message.channel.mention,     True),
                        ("🔢  Count",   str(emoji_count),            True),
                    ]
                ))
                await bot.process_commands(message)
                return

        # Anti-zalgo (Unicode combining character pollution)
        if cfg.get("automod_zalgo"):
            zalgo_count = len(re.findall(r"[\u0300-\u036f\u0489\u1dc0-\u1dff\u20d0-\u20ff\ufe20-\ufe2f]", content))
            if zalgo_count > 5:
                try: await message.delete()
                except Exception: pass
                await message.channel.send(
                    embed=discord.Embed(title="🚫  Zalgo Text Blocked",
                                        description=f"{message.author.mention}, corrupted/zalgo text is not allowed.",
                                        color=C_RED),
                    delete_after=6)
                await send_log(message.guild, _log_embed(
                    "AutoMod: Zalgo Text", C_ORANGE, icon="🌀",
                    thumbnail=message.author.display_avatar.url,
                    fields=[
                        ("👤  User",    f"{message.author.mention}", True),
                        ("📂  Channel", message.channel.mention,     True),
                    ]
                ))
                await bot.process_commands(message)
                return

        # Anti-repeated characters (aaaaaa / !!!!! etc.)
        if cfg.get("automod_repeated_chars"):
            limit = cfg.get("automod_repeated_limit", 8)
            if re.search(rf"(.)\1{{{limit},}}", content):
                try: await message.delete()
                except Exception: pass
                await message.channel.send(
                    embed=discord.Embed(title="🚫  Repeated Characters",
                                        description=f"{message.author.mention}, please don't repeat characters excessively.",
                                        color=C_RED),
                    delete_after=6)
                await send_log(message.guild, _log_embed(
                    "AutoMod: Repeated Chars", C_ORANGE, icon="🔁",
                    thumbnail=message.author.display_avatar.url,
                    fields=[
                        ("👤  User",    f"{message.author.mention}", True),
                        ("📂  Channel", message.channel.mention,     True),
                    ]
                ))
                await bot.process_commands(message)
                return

        # Anti-caps
        if cfg.get("automod_caps"):
            if len(content) >= cfg.get("automod_caps_min", 10):
                caps  = sum(1 for c in content if c.isupper())
                total = sum(1 for c in content if c.isalpha())
                if total > 0 and (caps / total * 100) >= cfg.get("automod_caps_pct", 80):
                    try: await message.delete()
                    except Exception: pass
                    await message.channel.send(
                        embed=discord.Embed(title="🚫  Excessive Caps",
                                            description=f"{message.author.mention}, please avoid excessive caps.",
                                            color=C_RED),
                        delete_after=6)
                    await send_log(message.guild, _log_embed(
                        "AutoMod: Caps Filter", C_ORANGE, icon="🔤",
                        thumbnail=message.author.display_avatar.url,
                        fields=[("👤  User", f"{message.author.mention}", True),
                                ("📂  Channel", message.channel.mention, True)]
                    ))
                    await bot.process_commands(message)
                    return

        # Bad words
        for word in cfg.get("automod_badwords", []):
            if word.lower() in content.lower():
                try: await message.delete()
                except Exception: pass
                await message.channel.send(
                    embed=discord.Embed(title="🚫  Filtered Word",
                                        description=f"{message.author.mention}, that word is not allowed.",
                                        color=C_RED),
                    delete_after=6)
                warn_user(guild_id, user_id, "AutoMod: Filtered word", "AutoMod")
                await send_log(message.guild, _log_embed(
                    "AutoMod: Bad Word", C_RED, icon="🤐",
                    thumbnail=message.author.display_avatar.url,
                    fields=[("👤  User", f"{message.author.mention}", True),
                            ("📂  Channel", message.channel.mention, True),
                            ("🔤  Word", f"||{word}||", True)]
                ))
                await bot.process_commands(message)
                return

    await bot.process_commands(message)

# Staff replies in modmail threads
@bot.listen("on_message")
async def on_modmail_staff_reply(message: discord.Message):
    if message.author.bot or not message.guild: return
    ch_id = str(message.channel.id)
    uid   = next((u for u, t in modmail_db.items() if t == ch_id), None)
    if uid is None: return
    if message.content.startswith("/") or message.content.startswith("!"): return
    try:
        user = await bot.fetch_user(int(uid))
        e = discord.Embed(
            title=f"📨  Reply from {message.guild.name} Staff",
            description=message.content or "(no text)",
            color=C_PURPLE
        )
        e.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        e.set_footer(text="Reply to this DM to continue • TSR ModMail")
        e.timestamp = now_utc()
        files = []
        for att in message.attachments:
            try: files.append(await att.to_file())
            except Exception: pass
        await user.send(embed=e, files=files)
        await message.add_reaction("📨")
    except discord.Forbidden:
        await message.channel.send(embed=_e_error("DMs Closed", "User has DMs disabled."), delete_after=8)
    except Exception as ex:
        await message.channel.send(embed=_e_error("Failed", str(ex)), delete_after=8)

# ── ModMail DM handler ─────────────────────────────────────────────────────

async def _handle_modmail_dm(message: discord.Message):
    uid = str(message.author.id)
    handled = False
    for gid, cfg in guild_config.items():
        mm_ch_id = cfg.get("modmail_channel")
        if not mm_ch_id: continue
        guild  = bot.get_guild(int(gid))
        if not guild: continue
        member = guild.get_member(message.author.id)
        if not member: continue
        mm_ch  = guild.get_channel(int(mm_ch_id))
        if not mm_ch: continue

        thread_id = modmail_db.get(uid)
        thread    = None
        if thread_id:
            try: thread = await guild.fetch_channel(int(thread_id))
            except Exception: thread = None

        if thread is None:
            cat_id = cfg.get("modmail_category")
            cat    = guild.get_channel(int(cat_id)) if cat_id else None
            ow = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
            }
            sr_id = cfg.get("ticket_support_role")
            if sr_id:
                sr = guild.get_role(int(sr_id))
                if sr: ow[sr] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
            try:
                thread = await guild.create_text_channel(
                    name=f"mail-{message.author.name[:20]}", category=cat,
                    overwrites=ow, reason=f"ModMail: {message.author}")
            except Exception: continue
            modmail_db[uid] = str(thread.id)
            save_json("modmail.json", modmail_db)

            intro = discord.Embed(
                title="📨  New ModMail Thread",
                description=(
                    f"**From:** {message.author.mention} (`{message.author}` • `{message.author.id}`)\n"
                    f"**Account Created:** <t:{int(message.author.created_at.timestamp())}:R>\n\n"
                    f"Reply in this channel — the user will receive your message as a DM.\n"
                    f"Use `/mmclose` to archive and close."
                ),
                color=C_BLUE
            )
            intro.set_thumbnail(url=message.author.display_avatar.url)
            intro.set_footer(text="TSR ModMail System")
            intro.timestamp = now_utc()
            await thread.send(embed=intro)

            await message.author.send(embed=discord.Embed(
                title="📨  ModMail Opened",
                description=(f"Your message has been forwarded to the staff of **{guild.name}**.\n"
                             f"Staff will reply here. Please be patient!"),
                color=C_GREEN
            ))

        # Forward the DM
        e = discord.Embed(description=message.content or "(no text)", color=C_BLUE)
        e.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        e.set_footer(text=f"UserID: {message.author.id}  •  DM Message")
        e.timestamp = now_utc()
        files = []
        for att in message.attachments:
            try: files.append(await att.to_file())
            except Exception: pass
        await thread.send(embed=e, files=files)
        handled = True

    if handled:
        try: await message.add_reaction("✅")
        except Exception: pass

# ═══════════════════════════════════════════════════════════════════════════
#  PERMISSION MANAGEMENT COMMANDS
# ═══════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="setpermission",
                  description="Grant or revoke a role's access to a command group")
@app_commands.describe(
    group="Command group: moderation | utility | community | setup",
    role="Role to grant/revoke access to this group",
    command="Optional: override for a single command name"
)
@app_commands.default_permissions(administrator=True)
async def setpermission(interaction: discord.Interaction,
                         group: str, role: discord.Role, command: str = None):
    if group not in CMD_GROUPS and not command:
        return await interaction.response.send_message(
            embed=_e_error("Invalid Group",
                           f"Choose from: `{'` `'.join(CMD_GROUPS.keys())}`"),
            ephemeral=True)

    gid = str(interaction.guild.id)
    cmd_perms_db.setdefault(gid, {})
    key = command if command else group
    cmd_perms_db[gid].setdefault(key, [])
    rid = str(role.id)

    if rid in cmd_perms_db[gid][key]:
        cmd_perms_db[gid][key].remove(rid)
        action = f"Removed {role.mention} from `{key}`"
    else:
        cmd_perms_db[gid][key].append(rid)
        action = f"Granted {role.mention} access to `{key}`"

    save_json("cmd_perms.json", cmd_perms_db)
    e = _e_success("Permission Updated", action)
    e.add_field(name="Group/Command", value=f"`{key}`", inline=True)
    e.add_field(name="Role",          value=role.mention, inline=True)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="viewpermissions", description="View which roles can access a command group")
@app_commands.describe(group="Command group to inspect")
@app_commands.default_permissions(administrator=True)
async def viewpermissions(interaction: discord.Interaction, group: str = None):
    gid  = str(interaction.guild.id)
    data = cmd_perms_db.get(gid, {})
    e    = discord.Embed(title="🔑  Command Permissions", color=C_BLUE)
    e.set_footer(text="TSR Permission System")
    keys = [group] if group else list(CMD_GROUPS.keys())
    for k in keys:
        role_ids = data.get(k, [])
        roles    = [interaction.guild.get_role(int(r)) for r in role_ids if interaction.guild.get_role(int(r))]
        e.add_field(
            name=f"📂  {k.title()}",
            value=" ".join(r.mention for r in roles) if roles else "*(admins only)*",
            inline=False
        )
    await interaction.response.send_message(embed=e, ephemeral=True)

# ═══════════════════════════════════════════════════════════════════════════
#  ANTI-NUKE SETUP
# ═══════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="setupantinuke", description="Configure the Anti-Nuke protection system")
@app_commands.describe(
    enabled="Enable or disable anti-nuke (true/false)",
    action="Response action: strip | strip+ban | kick | ban",
    anti_everyone="Trigger anti-nuke on unauthorized @everyone/@here pings",
    bans="Max bans before triggering (default 3)",
    kicks="Max kicks before triggering (default 5)",
    channels="Max channel deletes before triggering (default 3)",
    roles="Max role deletes before triggering (default 3)",
    window="Time window in seconds (default 10)",
    whitelist_role="Role immune to anti-nuke (toggle)"
)
@app_commands.default_permissions(administrator=True)
async def setupantinuke(interaction: discord.Interaction,
                         enabled: bool = None, action: str = None,
                         anti_everyone: bool = None,
                         bans: int = None, kicks: int = None,
                         channels: int = None, roles: int = None,
                         window: int = None, whitelist_role: discord.Role = None):
    cfg = gcfg(interaction.guild.id)
    changes = []
    if enabled        is not None:
        cfg["antinuke_enabled"] = enabled
        changes.append(f"Enabled: `{enabled}`")
    if anti_everyone  is not None:
        cfg["antinuke_anti_everyone"] = anti_everyone
        changes.append(f"Anti-@everyone: `{anti_everyone}`")
    if action         is not None:
        if action not in ("strip", "strip+ban", "kick", "ban"):
            return await interaction.response.send_message(
                embed=_e_error("Invalid Action", "Choose `strip`, `strip+ban`, `kick`, or `ban`."),
                ephemeral=True)
        cfg["antinuke_action"] = action
        changes.append(f"Action: `{action}`")
    if bans     is not None: cfg["antinuke_threshold_bans"]     = bans;     changes.append(f"Ban threshold: `{bans}`")
    if kicks    is not None: cfg["antinuke_threshold_kicks"]    = kicks;    changes.append(f"Kick threshold: `{kicks}`")
    if channels is not None: cfg["antinuke_threshold_channels"] = channels; changes.append(f"Channel del threshold: `{channels}`")
    if roles    is not None: cfg["antinuke_threshold_roles"]    = roles;    changes.append(f"Role del threshold: `{roles}`")
    if window   is not None: cfg["antinuke_window"]             = window;   changes.append(f"Window: `{window}s`")
    if whitelist_role:
        rid = str(whitelist_role.id)
        if rid in cfg["antinuke_whitelist"]:
            cfg["antinuke_whitelist"].remove(rid)
            changes.append(f"Removed whitelist: {whitelist_role.mention}")
        else:
            cfg["antinuke_whitelist"].append(rid)
            changes.append(f"Added whitelist: {whitelist_role.mention}")
    save_cfg()

    wl_roles = [interaction.guild.get_role(int(r)) for r in cfg["antinuke_whitelist"] if interaction.guild.get_role(int(r))]
    e = _e_success("Anti-Nuke Updated", "\n".join(changes) or "No changes.")
    e.add_field(name="Status",         value="`ON`" if cfg["antinuke_enabled"] else "`OFF`", inline=True)
    e.add_field(name="Action",         value=f"`{cfg['antinuke_action']}`",                  inline=True)
    e.add_field(name="Anti-@everyone", value="`ON`" if cfg.get("antinuke_anti_everyone") else "`OFF`", inline=True)
    e.add_field(name="Window",         value=f"`{cfg['antinuke_window']}s`",                 inline=True)
    e.add_field(name="Thresholds", value=(
        f"Bans: `{cfg['antinuke_threshold_bans']}`  •  "
        f"Kicks: `{cfg['antinuke_threshold_kicks']}`  •  "
        f"Ch-Del: `{cfg['antinuke_threshold_channels']}`  •  "
        f"Role-Del: `{cfg['antinuke_threshold_roles']}`"
    ), inline=False)
    e.add_field(name="Whitelist", value=" ".join(r.mention for r in wl_roles) or "None", inline=False)
    e.add_field(name="Actions explained", value=(
        "• `strip` — Remove all roles from executor\n"
        "• `strip+ban` — Remove all roles **and** ban executor\n"
        "• `kick` — Kick executor\n"
        "• `ban` — Permanently ban executor"
    ), inline=False)
    await interaction.response.send_message(embed=e)

# ═══════════════════════════════════════════════════════════════════════════
#  SETUP COMMANDS
# ═══════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="setuplog", description="Set the server log channel")
@app_commands.default_permissions(administrator=True)
async def setuplog(interaction: discord.Interaction, channel: discord.TextChannel):
    gcfg(interaction.guild.id)["log_channel"] = str(channel.id); save_cfg()
    e = _e_success("Log Channel Set",
                   f"All events will be logged in {channel.mention}.\n\n"
                   f"**Logged events include:**\n"
                   f"Bans, kicks, timeouts, warns, purges, message edits/deletes, "
                   f"member joins/leaves, voice changes, role changes, nickname changes, "
                   f"channel create/delete, anti-spam, anti-nuke, filtered words, and more.")
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="setupwelcome", description="Configure the welcome message")
@app_commands.describe(channel="Welcome channel", message="Use {user} {username} {server} {count}")
@app_commands.default_permissions(administrator=True)
async def setupwelcome(interaction: discord.Interaction, channel: discord.TextChannel, message: str = None):
    cfg = gcfg(interaction.guild.id)
    cfg["welcome_channel"] = str(channel.id)
    if message: cfg["welcome_message"] = message
    save_cfg()
    e = _e_success("Welcome Configured", f"Welcome messages → {channel.mention}")
    e.add_field(name="Template", value=cfg["welcome_message"], inline=False)
    e.add_field(name="Variables", value="`{user}` `{username}` `{server}` `{count}`", inline=False)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="setupgoodbye", description="Configure the goodbye message")
@app_commands.default_permissions(administrator=True)
async def setupgoodbye(interaction: discord.Interaction, channel: discord.TextChannel, message: str = None):
    cfg = gcfg(interaction.guild.id)
    cfg["goodbye_channel"] = str(channel.id)
    if message: cfg["goodbye_message"] = message
    save_cfg()
    e = _e_success("Goodbye Configured", f"Goodbye messages → {channel.mention}")
    e.add_field(name="Template", value=cfg["goodbye_message"], inline=False)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="setuproblox", description="Enable Roblox update notifications (v4 — future + live detection)")
@app_commands.describe(
    channel="Channel to post update alerts in",
    live_ping_role="Role to ping on a LIVE update (player version changed)",
    future_ping_role="Role to ping on a FUTURE/pre-release update (studio ahead of player)"
)
@app_commands.default_permissions(administrator=True)
async def setuproblox(interaction: discord.Interaction,
                       channel: discord.TextChannel,
                       live_ping_role: discord.Role = None,
                       future_ping_role: discord.Role = None):
    cfg = gcfg(interaction.guild.id)
    cfg["roblox_channel"] = str(channel.id)
    if live_ping_role:   cfg["roblox_ping_role"]        = str(live_ping_role.id)
    if future_ping_role: cfg["roblox_future_ping_role"] = str(future_ping_role.id)
    # Seed version so first run doesn't false-alarm
    player_ver = None
    studio_ver = None
    try:
        player_ver = await _fetch_roblox_version("WindowsPlayer")
        studio_ver = await _fetch_roblox_version("WindowsStudio64")
    except Exception:
        pass
    if player_ver: cfg["roblox_last_player_version"] = player_ver
    if studio_ver: cfg["roblox_last_studio_version"] = studio_ver
    save_cfg()
    e = _e_success(
        "Roblox Watcher v4 Enabled",
        f"Update alerts → {channel.mention}\n"
        f"Checks every **3 minutes** for both **live** and **future** updates."
    )
    e.add_field(name="🔴  Live Update Ping",   value=live_ping_role.mention   if live_ping_role   else "None set", inline=True)
    e.add_field(name="🟡  Future Update Ping", value=future_ping_role.mention if future_ping_role else "None set", inline=True)
    e.add_field(name="Current Player Version", value=f"`{player_ver or 'unknown'}`", inline=False)
    e.add_field(name="Current Studio Version", value=f"`{studio_ver or 'unknown'}`", inline=False)
    e.add_field(name="How it works", value=(
        "🟡 **Future** — Studio has a version newer than Player (update coming soon)\n"
        "🔴 **Live** — Player version changed (players must update now)"
    ), inline=False)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="setupsuggestions", description="Set the suggestions channel")
@app_commands.default_permissions(administrator=True)
async def setupsuggestions(interaction: discord.Interaction, channel: discord.TextChannel):
    gcfg(interaction.guild.id)["suggestion_channel"] = str(channel.id); save_cfg()
    await interaction.response.send_message(embed=_e_success(
        "Suggestions Configured", f"Suggestions → {channel.mention}"))

@bot.tree.command(name="setuplevels", description="Configure the levelling system")
@app_commands.describe(channel="Level-up channel (blank = same channel)", message="Use {user} and {level}")
@app_commands.default_permissions(administrator=True)
async def setuplevels(interaction: discord.Interaction, channel: discord.TextChannel = None, message: str = None):
    cfg = gcfg(interaction.guild.id)
    if channel: cfg["level_channel"] = str(channel.id)
    if message: cfg["level_up_msg"]  = message
    save_cfg()
    e = _e_success("Levels Configured", f"Level-up channel: {channel.mention if channel else 'same channel'}")
    e.add_field(name="Message", value=cfg["level_up_msg"], inline=False)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="setuplock", description="Configure lock/unlock behaviour")
@app_commands.describe(exempt_role="Toggle a role as exempt from locks",
                        permission="Permission to deny: send_messages | add_reactions | all")
@app_commands.default_permissions(administrator=True)
async def setuplock(interaction: discord.Interaction,
                     exempt_role: discord.Role = None, permission: str = "send_messages"):
    cfg = gcfg(interaction.guild.id)
    valid = ["send_messages","add_reactions","use_application_commands","all"]
    if permission not in valid:
        return await interaction.response.send_message(
            embed=_e_error("Invalid Permission",f"Choose: `{'` `'.join(valid)}`"), ephemeral=True)
    if exempt_role:
        rid = str(exempt_role.id)
        if rid in cfg["lock_exempt_roles"]: cfg["lock_exempt_roles"].remove(rid); msg = f"Removed {exempt_role.mention} from exempt."
        else: cfg["lock_exempt_roles"].append(rid); msg = f"Added {exempt_role.mention} as exempt."
    else:
        msg = "No role changed."
    cfg["lock_deny_perm"] = permission
    save_cfg()
    exempt = [interaction.guild.get_role(int(r)) for r in cfg["lock_exempt_roles"] if interaction.guild.get_role(int(r))]
    e = _e_success("Lock Setup Updated", msg)
    e.add_field(name="Locked Permission", value=f"`{cfg['lock_deny_perm']}`", inline=True)
    e.add_field(name="Exempt Roles", value=" ".join(r.mention for r in exempt) or "None", inline=True)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="setupautomod", description="Configure AutoMod filters (v4 — smart detection)")
@app_commands.describe(
    links="Block external links",
    caps="Block excessive CAPS",
    caps_percent="Caps % to trigger (default 80)",
    caps_min_length="Min message length to check caps (default 10)",
    invites="Block Discord server invite links (discord.gg)",
    mentions="Block excessive @mentions in one message",
    mentions_limit="Max @mentions before deletion (default 5)",
    emojis="Block emoji spam",
    emojis_limit="Max emojis before deletion (default 10)",
    zalgo="Block zalgo/Unicode pollution text",
    repeated_chars="Block repeated character runs (aaaaaa)",
    repeated_limit="How many repeated chars trigger (default 8)",
    exempt_role="Toggle AutoMod-exempt role"
)
@app_commands.default_permissions(administrator=True)
async def setupautomod(interaction: discord.Interaction,
                        links: bool = None, caps: bool = None,
                        caps_percent: int = None, caps_min_length: int = None,
                        invites: bool = None,
                        mentions: bool = None, mentions_limit: int = None,
                        emojis: bool = None, emojis_limit: int = None,
                        zalgo: bool = None,
                        repeated_chars: bool = None, repeated_limit: int = None,
                        exempt_role: discord.Role = None):
    cfg = gcfg(interaction.guild.id); changes = []
    def _tog(key, val, label):
        cfg[key] = val
        changes.append(f"{label}: `{'ON' if val else 'OFF'}`")
    if links          is not None: _tog("automod_links",          links,          "Anti-Links")
    if caps           is not None: _tog("automod_caps",           caps,           "Anti-Caps")
    if invites        is not None: _tog("automod_invites",        invites,        "Anti-Invites")
    if mentions       is not None: _tog("automod_mentions",       mentions,       "Anti-Mentions")
    if emojis         is not None: _tog("automod_emojis",         emojis,         "Anti-Emoji-Spam")
    if zalgo          is not None: _tog("automod_zalgo",          zalgo,          "Anti-Zalgo")
    if repeated_chars is not None: _tog("automod_repeated_chars", repeated_chars, "Anti-Repeated-Chars")
    if caps_percent   is not None: cfg["automod_caps_pct"]         = caps_percent;  changes.append(f"Caps %: `{caps_percent}`")
    if caps_min_length is not None: cfg["automod_caps_min"]        = caps_min_length; changes.append(f"Caps min-len: `{caps_min_length}`")
    if mentions_limit is not None: cfg["automod_mentions_limit"]   = mentions_limit; changes.append(f"Mention limit: `{mentions_limit}`")
    if emojis_limit   is not None: cfg["automod_emojis_limit"]     = emojis_limit;   changes.append(f"Emoji limit: `{emojis_limit}`")
    if repeated_limit is not None: cfg["automod_repeated_limit"]   = repeated_limit; changes.append(f"Repeat limit: `{repeated_limit}`")
    if exempt_role:
        rid = str(exempt_role.id)
        if rid in cfg["automod_exempt_roles"]:
            cfg["automod_exempt_roles"].remove(rid); changes.append(f"Removed exempt: {exempt_role.mention}")
        else:
            cfg["automod_exempt_roles"].append(rid); changes.append(f"Added exempt: {exempt_role.mention}")
    save_cfg()
    e = _e_success("AutoMod v4 Updated", "\n".join(changes) or "No changes.")
    def _s(k): return "`ON`" if cfg.get(k) else "`OFF`"
    e.add_field(name="🔗  Anti-Links",    value=_s("automod_links"),          inline=True)
    e.add_field(name="🔤  Anti-Caps",     value=f"{_s('automod_caps')} {cfg['automod_caps_pct']}%", inline=True)
    e.add_field(name="📩  Anti-Invites",  value=_s("automod_invites"),         inline=True)
    e.add_field(name="@  Anti-Mentions",  value=f"{_s('automod_mentions')} max {cfg['automod_mentions_limit']}", inline=True)
    e.add_field(name="😀  Anti-Emojis",   value=f"{_s('automod_emojis')} max {cfg['automod_emojis_limit']}", inline=True)
    e.add_field(name="🌀  Anti-Zalgo",    value=_s("automod_zalgo"),           inline=True)
    e.add_field(name="🔁  Anti-Repeat",   value=f"{_s('automod_repeated_chars')} run {cfg['automod_repeated_limit']}", inline=True)
    e.add_field(name="🚫  Bad Words",     value=f"`{len(cfg['automod_badwords'])} words`", inline=True)
    exempt = [interaction.guild.get_role(int(r)) for r in cfg["automod_exempt_roles"] if interaction.guild.get_role(int(r))]
    e.add_field(name="✅  Exempt Roles",  value=" ".join(r.mention for r in exempt) or "None", inline=False)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="badword", description="Add or remove a word from the filter")
@app_commands.default_permissions(administrator=True)
async def badword(interaction: discord.Interaction, word: str, action: str = "add"):
    cfg = gcfg(interaction.guild.id); word = word.lower()
    if action == "add":
        if word not in cfg["automod_badwords"]: cfg["automod_badwords"].append(word); save_cfg()
        await interaction.response.send_message(embed=_e_success("Word Added", f"`{word}` added to filter."), ephemeral=True)
    elif action == "remove":
        if word in cfg["automod_badwords"]: cfg["automod_badwords"].remove(word); save_cfg()
        await interaction.response.send_message(embed=_e_success("Word Removed", f"`{word}` removed."), ephemeral=True)
    else:
        await interaction.response.send_message(embed=_e_error("Invalid", "Use `add` or `remove`."), ephemeral=True)

@bot.tree.command(name="filterlist", description="List all filtered words")
@app_commands.default_permissions(administrator=True)
async def filterlist(interaction: discord.Interaction):
    cfg = gcfg(interaction.guild.id); words = cfg.get("automod_badwords", [])
    if not words:
        return await interaction.response.send_message(embed=_e_info("Filter List","No words in filter."), ephemeral=True)
    await interaction.response.send_message(
        embed=_e_info("🚫  Filter List", "```" + ", ".join(words) + "```"), ephemeral=True)

# ═══════════════════════════════════════════════════════════════════════════
#  VERIFICATION  (v3 — hardened)
# ═══════════════════════════════════════════════════════════════════════════

async def _verify_prereqs(interaction: discord.Interaction, member: discord.Member = None) -> tuple[bool, str]:
    """Check account age and phone-verification requirements. Returns (passed, reason)."""
    m   = member or interaction.user
    cfg = gcfg(interaction.guild.id)
    min_age = cfg.get("verify_min_age_days", 0)
    if min_age > 0:
        age_days = (now_utc() - m.created_at).days
        if age_days < min_age:
            return False, (f"Your Discord account must be at least **{min_age} days old** to verify.\n"
                           f"Your account is `{age_days}` day(s) old.")
    if cfg.get("verify_require_phone") and not m.public_flags.verified_phone:
        return False, "Your Discord account must have a **verified phone number** to join this server."
    return True, ""

class VerifyButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify Me", style=discord.ButtonStyle.success,
                       emoji="✔️", custom_id="tsr_verify_v3")
    async def do_verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = gcfg(interaction.guild.id)
        # Prereqs
        ok, reason = await _verify_prereqs(interaction)
        if not ok:
            return await interaction.response.send_message(
                embed=_e_error("Cannot Verify", reason), ephemeral=True)

        method = cfg.get("verify_method", "button")
        role_id = cfg.get("verify_role")
        if not role_id:
            return await interaction.response.send_message(embed=_e_error("Not Configured","Verify role not set."), ephemeral=True)
        role = interaction.guild.get_role(int(role_id))
        if not role:
            return await interaction.response.send_message(embed=_e_error("Role Missing","Verify role not found."), ephemeral=True)
        if role in interaction.user.roles:
            return await interaction.response.send_message(embed=_e_info("Already Verified","You are already verified!"), ephemeral=True)

        if method == "button":
            await interaction.user.add_roles(role, reason="Verification: button")
            e = discord.Embed(title="✅  Verified!", description=f"You've been given **{role.name}**. Welcome!", color=C_GREEN)
            e.set_thumbnail(url=interaction.user.display_avatar.url)
            e.set_footer(text=interaction.guild.name)
            await interaction.response.send_message(embed=e, ephemeral=True)
            await send_log(interaction.guild, _log_embed(
                "Member Verified (Button)", C_GREEN, icon="✔️",
                thumbnail=interaction.user.display_avatar.url,
                fields=[("👤  User", f"{interaction.user.mention} `{interaction.user.id}`", True),
                        ("🎭  Role", role.mention, True)]
            ))
        elif method == "math":
            a, b = random.randint(10, 99), random.randint(10, 99)
            ans  = a + b
            pending_math[interaction.user.id] = {"answer": ans, "role_id": role_id, "guild_id": interaction.guild.id}
            dm_e = discord.Embed(
                title="🧮  Math Verification",
                description=(
                    f"To verify in **{interaction.guild.name}**, solve this:\n\n"
                    f"## `{a} + {b} = ?`\n\n"
                    f"Use `/verify <answer>` in the server."
                ),
                color=C_BLUE
            )
            dm_e.set_footer(text="This code expires in 5 minutes.")
            try:
                await interaction.user.send(embed=dm_e)
                await interaction.response.send_message(
                    embed=_e_info("📩  Check Your DMs", "A math verification was sent to your DMs."), ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message(
                    embed=_e_error("DMs Closed", "Enable DMs from server members, then try again."), ephemeral=True)
        elif method == "code":
            code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
            pending_codes[interaction.user.id] = {"code": code, "role_id": role_id, "guild_id": interaction.guild.id}
            dm_e = discord.Embed(
                title="🔑  Verification Code",
                description=(
                    f"Your code for **{interaction.guild.name}**:\n\n"
                    f"## `{code}`\n\n"
                    f"Use `/verify {code}` in the server."
                ),
                color=C_BLUE
            )
            dm_e.set_footer(text="Code expires in 5 minutes.")
            try:
                await interaction.user.send(embed=dm_e)
                await interaction.response.send_message(
                    embed=_e_info("📩  Check Your DMs","A verification code was sent to your DMs."), ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message(
                    embed=_e_error("DMs Closed","Enable DMs from server members."), ephemeral=True)

@bot.tree.command(name="verify", description="Submit your verification code or answer")
@app_commands.describe(answer="Your verification code or math answer")
async def verify_cmd(interaction: discord.Interaction, answer: str):
    uid = interaction.user.id

    # Math CAPTCHA path
    if uid in pending_math:
        d = pending_math[uid]
        if str(answer).strip() == str(d["answer"]):
            guild = bot.get_guild(d["guild_id"])
            role  = guild.get_role(int(d["role_id"])) if guild else None
            if role and guild:
                m = guild.get_member(uid)
                if m: await m.add_roles(role, reason="Verification: math CAPTCHA")
            del pending_math[uid]
            await interaction.response.send_message(embed=_e_success("Verified!",f"You've been given **{role.name if role else 'the verify role'}**."), ephemeral=True)
            if guild and role:
                await send_log(guild, _log_embed(
                    "Member Verified (Math CAPTCHA)", C_GREEN, icon="🧮",
                    thumbnail=interaction.user.display_avatar.url,
                    fields=[("👤  User", f"{interaction.user.mention} `{interaction.user.id}`", True),
                            ("🎭  Role", role.mention, True)]
                ))
        else:
            await interaction.response.send_message(embed=_e_error("Wrong Answer","Incorrect. Click the verify button again to get a new question."), ephemeral=True)
        return

    # Code path
    if uid in pending_codes:
        d = pending_codes[uid]
        if answer.upper().strip() == d["code"].upper():
            guild = bot.get_guild(d["guild_id"])
            role  = guild.get_role(int(d["role_id"])) if guild else None
            if role and guild:
                m = guild.get_member(uid)
                if m: await m.add_roles(role, reason="Verification: code")
            del pending_codes[uid]
            await interaction.response.send_message(embed=_e_success("Verified!",f"You've been given **{role.name if role else 'the verify role'}**."), ephemeral=True)
        else:
            await interaction.response.send_message(embed=_e_error("Wrong Code","Incorrect. Click the verify button again for a new code."), ephemeral=True)
        return

    await interaction.response.send_message(embed=_e_error("No Pending Verification","Click the verify button first."), ephemeral=True)

@bot.tree.command(name="setupverify", description="Set up the verification system")
@app_commands.describe(channel="Channel to post the verify panel",
                        role="Role granted on verification",
                        method="button | code | math | reaction",
                        min_age_days="Minimum Discord account age in days (0 = any)",
                        require_phone="Require phone-verified account",
                        message="Custom panel message")
@app_commands.default_permissions(administrator=True)
async def setupverify(interaction: discord.Interaction,
                       channel: discord.TextChannel, role: discord.Role,
                       method: str = "button", min_age_days: int = 0,
                       require_phone: bool = False, message: str = None):
    valid_methods = ("button","code","math","reaction")
    if method not in valid_methods:
        return await interaction.response.send_message(
            embed=_e_error("Invalid Method", f"Choose: `{'` `'.join(valid_methods)}`"), ephemeral=True)
    cfg = gcfg(interaction.guild.id)
    cfg["verify_channel"]       = str(channel.id)
    cfg["verify_role"]          = str(role.id)
    cfg["verify_method"]        = method
    cfg["verify_min_age_days"]  = max(0, min_age_days)
    cfg["verify_require_phone"] = require_phone
    if message: cfg["verify_message"] = message
    save_cfg()

    age_txt   = f"`{min_age_days}d`" if min_age_days > 0 else "None"
    phone_txt = "Required" if require_phone else "Not required"
    method_desc = {
        "button":   "• Click the button — instant verify",
        "code":     "• Click button → receive a DM code → `/verify <code>`",
        "math":     "• Click button → receive a DM math question → `/verify <answer>`",
        "reaction": "• React with ✅ to verify",
    }[method]
    e = discord.Embed(
        title=f"🛡️  Verification System",
        description=cfg["verify_message"],
        color=C_BLUE
    )
    e.add_field(name="How to Verify", value=method_desc, inline=False)
    e.set_footer(text=f"{interaction.guild.name}  •  Verification")
    e.timestamp = now_utc()
    if method in ("button","code","math"):
        await channel.send(embed=e, view=VerifyButton())
    else:
        sent = await channel.send(embed=e)
        await sent.add_reaction("✅")
        cfg["verify_message_id"] = str(sent.id)
        save_cfg()

    res = _e_success("Verification Set Up",
                     f"Channel: {channel.mention}\nRole: {role.mention}\nMethod: `{method}`")
    res.add_field(name="Min Account Age", value=age_txt, inline=True)
    res.add_field(name="Phone Verified",  value=phone_txt, inline=True)
    await interaction.response.send_message(embed=res)

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id: return
    guild = bot.get_guild(payload.guild_id)
    if not guild: return
    cfg = gcfg(guild.id)
    if cfg.get("verify_method") != "reaction": return
    if str(payload.message_id) != cfg.get("verify_message_id"): return
    if str(payload.emoji) != "✅": return
    role_id = cfg.get("verify_role")
    if not role_id: return
    role   = guild.get_role(int(role_id))
    member = guild.get_member(payload.user_id)
    if not role or not member or role in member.roles: return
    ok, reason = await _verify_prereqs(None, member)
    if not ok:
        await dm_user(member, _e_error("Cannot Verify", reason))
        return
    await member.add_roles(role, reason="Verification: reaction")
    await send_log(guild, _log_embed(
        "Member Verified (Reaction)", C_GREEN, icon="✔️",
        thumbnail=member.display_avatar.url,
        fields=[("👤  User", f"{member.mention} `{member.id}`", True),
                ("🎭  Role", role.mention, True)]
    ))

# ═══════════════════════════════════════════════════════════════════════════
#  TICKET SYSTEM
# ═══════════════════════════════════════════════════════════════════════════

class TicketButton(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Open a Ticket", style=discord.ButtonStyle.primary,
                       emoji="🎫", custom_id="tsr_ticket_open_v3")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = gcfg(interaction.guild.id)
        cat  = interaction.guild.get_channel(int(cfg["ticket_category"])) if cfg.get("ticket_category") else None
        existing = discord.utils.get(interaction.guild.text_channels,
                                      name=f"ticket-{interaction.user.name.lower()[:20]}")
        if existing:
            return await interaction.response.send_message(
                embed=_e_error("Ticket Exists", f"You already have a ticket: {existing.mention}"), ephemeral=True)
        cfg["ticket_count"] = cfg.get("ticket_count", 0) + 1; save_cfg()
        num = cfg["ticket_count"]
        sr  = interaction.guild.get_role(int(cfg["ticket_support_role"])) if cfg.get("ticket_support_role") else None
        ow  = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user:               discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            interaction.guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        if sr: ow[sr] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        try:
            ch = await interaction.guild.create_text_channel(
                name=f"ticket-{num:04d}", category=cat, overwrites=ow,
                reason=f"Ticket by {interaction.user}")
        except Exception as ex:
            return await interaction.response.send_message(embed=_e_error("Failed", str(ex)), ephemeral=True)

        e = discord.Embed(
            title=f"🎫  Ticket #{num:04d}",
            description=(
                f"Hello {interaction.user.mention}!\n\n"
                f"Please describe your issue and a staff member will assist you shortly.\n\n"
                f"> Press **Close Ticket** when your issue is resolved."
            ),
            color=C_BLUE
        )
        e.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
        e.set_footer(text=f"Ticket #{num:04d}  •  TSR Support")
        e.timestamp = now_utc()
        await ch.send(content=f"{interaction.user.mention}" + (f" {sr.mention}" if sr else ""),
                      embed=e, view=TicketCloseView())
        await interaction.response.send_message(embed=_e_success("Ticket Opened", f"Your ticket: {ch.mention}"), ephemeral=True)
        await send_log(interaction.guild, _log_embed(
            "Ticket Opened", C_BLUE, icon="🎫",
            thumbnail=interaction.user.display_avatar.url,
            fields=[("👤  User",    f"{interaction.user.mention} `{interaction.user.id}`", True),
                    ("📂  Channel", ch.mention,                                             True),
                    ("🔢  Number",  f"#{num:04d}",                                         True)]
        ))

class TicketCloseView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger,
                       emoji="🔒", custom_id="tsr_ticket_close_v3")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
        await interaction.response.defer()
        await _close_ticket(interaction.channel, interaction.user, interaction.guild)

async def _close_ticket(channel: discord.TextChannel, closer, guild: discord.Guild, reason: str = "Resolved"):
    cfg = gcfg(guild.id)
    msgs = []
    async for m in channel.history(limit=1000, oldest_first=True):
        ts = m.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        content = m.content
        if not content and m.embeds: content = m.embeds[0].description or "(embed)"
        msgs.append(f"[{ts}] {m.author}: {content or '(no content)'}")
    transcript_file = discord.File(
        io.BytesIO("\n".join(msgs).encode()),
        filename=f"transcript-{channel.name}.txt"
    )
    tc_id = cfg.get("ticket_transcript_channel") or cfg.get("log_channel")
    if tc_id:
        tc = guild.get_channel(int(tc_id))
        if tc:
            le = discord.Embed(
                title="📋  Ticket Transcript",
                description=(f"**Channel:** `#{channel.name}`\n"
                             f"**Closed by:** {closer.mention}\n"
                             f"**Reason:** {reason}"),
                color=C_PURPLE
            )
            le.timestamp = now_utc()
            le.set_footer(text="TSR Ticket System")
            await tc.send(embed=le, file=transcript_file)
    await channel.send(embed=_e_info("🔒  Closing Ticket",
                                     f"Reason: **{reason}**\nDeleting in 5 seconds…", color=C_RED))
    await asyncio.sleep(5)
    try: await channel.delete(reason=f"Ticket closed: {reason}")
    except Exception: pass

@bot.tree.command(name="setuptickets", description="Set up the ticket system")
@app_commands.describe(channel="Ticket panel channel", category="Category for ticket channels",
                        support_role="Role that sees tickets",
                        transcript_channel="Channel for transcripts",
                        message="Panel message")
@app_commands.default_permissions(administrator=True)
async def setuptickets(interaction: discord.Interaction,
                        channel: discord.TextChannel, category: discord.CategoryChannel = None,
                        support_role: discord.Role = None,
                        transcript_channel: discord.TextChannel = None,
                        message: str = None):
    cfg = gcfg(interaction.guild.id)
    cfg["ticket_channel"]            = str(channel.id)
    cfg["ticket_category"]           = str(category.id) if category else None
    cfg["ticket_support_role"]       = str(support_role.id) if support_role else None
    cfg["ticket_transcript_channel"] = str(transcript_channel.id) if transcript_channel else None
    if message: cfg["ticket_message"] = message
    save_cfg()
    e = discord.Embed(title="🎫  Support Tickets", description=cfg["ticket_message"], color=C_BLUE)
    e.set_footer(text=f"{interaction.guild.name}  •  Support")
    e.timestamp = now_utc()
    await channel.send(embed=e, view=TicketButton())
    res = _e_success("Tickets Configured", f"Panel sent to {channel.mention}.")
    res.add_field(name="Support Role",        value=support_role.mention if support_role else "None", inline=True)
    res.add_field(name="Transcript Channel",  value=transcript_channel.mention if transcript_channel else "Uses log channel", inline=True)
    await interaction.response.send_message(embed=res)

@bot.tree.command(name="closeticket", description="Close the current ticket")
@app_commands.describe(reason="Reason for closing")
@app_commands.default_permissions(manage_channels=True)
async def closeticket(interaction: discord.Interaction, reason: str = "Resolved by staff"):
    if not interaction.channel.name.startswith("ticket-"):
        return await interaction.response.send_message(embed=_e_error("Not a Ticket","Run inside a ticket channel."), ephemeral=True)
    await interaction.response.defer()
    await _close_ticket(interaction.channel, interaction.user, interaction.guild, reason)

# ═══════════════════════════════════════════════════════════════════════════
#  MOD MAIL COMMANDS
# ═══════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="setupmodmail", description="Set up the ModMail system")
@app_commands.describe(channel="Channel to create modmail threads in",
                        category="Category for threads (optional)",
                        log_channel="Log channel (optional)")
@app_commands.default_permissions(administrator=True)
async def setupmodmail(interaction: discord.Interaction,
                        channel: discord.TextChannel,
                        category: discord.CategoryChannel = None,
                        log_channel: discord.TextChannel = None):
    cfg = gcfg(interaction.guild.id)
    cfg["modmail_channel"]     = str(channel.id)
    cfg["modmail_category"]    = str(category.id) if category else None
    cfg["modmail_log_channel"] = str(log_channel.id) if log_channel else None
    save_cfg()
    e = _e_success("ModMail Configured",
                   f"Users can DM {bot.user.mention} to contact staff.\n\n"
                   f"**Thread channel:** {channel.mention}\n"
                   f"**Log channel:** {log_channel.mention if log_channel else 'None'}")
    e.add_field(name="How it works", value=(
        "• Member DMs the bot → private thread created\n"
        "• Staff reply in thread → user receives as DM\n"
        "• `/mmclose` — archive and close thread"
    ), inline=False)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="mmclose", description="Close and archive a ModMail thread")
@app_commands.describe(reason="Reason for closing")
@app_commands.default_permissions(manage_channels=True)
async def mmclose(interaction: discord.Interaction, reason: str = "Resolved"):
    ch_id = str(interaction.channel.id)
    uid   = next((u for u, t in modmail_db.items() if t == ch_id), None)
    if uid is None:
        return await interaction.response.send_message(embed=_e_error("Not a ModMail Thread","Use in an active modmail thread."), ephemeral=True)
    await interaction.response.defer()
    cfg = gcfg(interaction.guild.id)
    msgs = []
    async for m in interaction.channel.history(limit=500, oldest_first=True):
        ts = m.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        content = m.content or (m.embeds[0].description if m.embeds else "(embed)")
        msgs.append(f"[{ts}] {m.author}: {content}")
    tf = discord.File(io.BytesIO("\n".join(msgs).encode()), filename=f"modmail-{uid}.txt")
    log_ch_id = cfg.get("modmail_log_channel") or cfg.get("log_channel")
    if log_ch_id:
        lc = interaction.guild.get_channel(int(log_ch_id))
        if lc:
            le = discord.Embed(
                title="📋  ModMail Transcript",
                description=(f"**User:** <@{uid}> (`{uid}`)\n"
                             f"**Closed by:** {interaction.user.mention}\n"
                             f"**Reason:** {reason}"),
                color=C_PURPLE
            )
            le.timestamp = now_utc()
            le.set_footer(text="TSR ModMail System")
            await lc.send(embed=le, file=tf)
    try:
        user = await bot.fetch_user(int(uid))
        close_e = discord.Embed(
            title="📨  Thread Closed",
            description=(f"Your modmail in **{interaction.guild.name}** has been closed.\n"
                         f"**Reason:** {reason}\n\nOpen a new one by DMing the bot again."),
            color=C_ORANGE
        )
        await user.send(embed=close_e)
    except Exception: pass
    del modmail_db[uid]; save_json("modmail.json", modmail_db)
    await interaction.followup.send(embed=_e_success("Thread Closed","Transcript sent."))
    await asyncio.sleep(3)
    try: await interaction.channel.delete(reason=f"ModMail closed: {reason}")
    except Exception: pass

@bot.tree.command(name="mmreply", description="Reply to a modmail user (slash command)")
@app_commands.describe(message="Your reply")
@app_commands.default_permissions(manage_channels=True)
async def mmreply(interaction: discord.Interaction, message: str):
    ch_id = str(interaction.channel.id)
    uid   = next((u for u, t in modmail_db.items() if t == ch_id), None)
    if uid is None:
        return await interaction.response.send_message(embed=_e_error("Not a ModMail Thread",""), ephemeral=True)
    try:
        user = await bot.fetch_user(int(uid))
        e = discord.Embed(title=f"📨  Reply from {interaction.guild.name} Staff",
                          description=message, color=C_PURPLE)
        e.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
        e.set_footer(text="Reply to continue the conversation  •  TSR ModMail")
        e.timestamp = now_utc()
        await user.send(embed=e)
        echo = discord.Embed(description=message, color=C_PURPLE)
        echo.set_author(name=f"[STAFF] {interaction.user}", icon_url=interaction.user.display_avatar.url)
        echo.timestamp = now_utc()
        await interaction.channel.send(embed=echo)
        await interaction.response.send_message(embed=_e_success("Reply Sent",""), ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(embed=_e_error("DMs Closed","User has DMs disabled."), ephemeral=True)

# ═══════════════════════════════════════════════════════════════════════════
#  MODERATION COMMANDS
# ═══════════════════════════════════════════════════════════════════════════

def _can_target(interaction: discord.Interaction, member: discord.Member) -> bool:
    if member == interaction.user: return False
    if member.top_role >= interaction.user.top_role and interaction.user.id not in OWNER_IDS: return False
    return True

@bot.tree.command(name="ban", description="Permanently ban a member")
@app_commands.describe(member="Member to ban", reason="Reason", delete_days="Days of messages to delete")
@app_commands.default_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = None, delete_days: int = 1):
    if not has_cmd_perm(interaction, "ban"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    if not interaction.user.guild_permissions.ban_members: return await interaction.response.send_message(embed=_e_error("No Permission","You need Ban Members."), ephemeral=True)
    if not _can_target(interaction, member): return await interaction.response.send_message(embed=_e_error("Role Hierarchy","You can't moderate that member."), ephemeral=True)
    await dm_user(member, discord.Embed(title=f"🔨  Banned from {interaction.guild.name}",
                                        description=f"**Reason:** {reason or 'No reason'}",
                                        color=C_RED))
    await member.ban(reason=reason, delete_message_days=min(max(delete_days,0),7))
    e = _e_success("Member Banned", f"{member.mention} has been permanently banned.")
    e.add_field(name="User",   value=f"`{member}`",         inline=True)
    e.add_field(name="Reason", value=reason or "No reason", inline=True)
    await interaction.response.send_message(embed=e)
    await send_log(interaction.guild, _mod_embed("Member Banned","🔨",C_RED,interaction.user,member,reason,
                                                  {"Deleted Messages":f"{delete_days}d"}))

@bot.tree.command(name="hardban", description="Hardban — user is re-banned if they rejoin")
@app_commands.default_permissions(administrator=True)
async def hardban(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if not has_cmd_perm(interaction, "hardban"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    if not _can_target(interaction, member): return await interaction.response.send_message(embed=_e_error("Role Hierarchy",""), ephemeral=True)
    gid = str(interaction.guild.id); uid = str(member.id)
    hardban_db.setdefault(gid,{})[uid] = {"reason": reason or "No reason", "moderator": str(interaction.user), "time": now_utc().isoformat()}
    save_json("hardbans.json", hardban_db)
    await dm_user(member, discord.Embed(title=f"💀  Hardbanned from {interaction.guild.name}",
                                         description=f"**Reason:** {reason or 'No reason'}\n*This ban is permanent.*", color=C_RED))
    await member.ban(reason=f"HARDBAN: {reason}", delete_message_days=7)
    await interaction.response.send_message(embed=_e_success("Hardbanned", f"{member.mention} has been hardbanned."))
    await send_log(interaction.guild, _mod_embed("Hard Ban","💀",C_RED,interaction.user,member,reason))

@bot.tree.command(name="hardban_id", description="Hardban by User ID (even if not in server)")
@app_commands.default_permissions(administrator=True)
async def hardban_id(interaction: discord.Interaction, user_id: str, reason: str = None):
    if not has_cmd_perm(interaction, "hardban_id"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    try: user = await bot.fetch_user(int(user_id))
    except (discord.NotFound,ValueError): return await interaction.response.send_message(embed=_e_error("Not Found","User not found."), ephemeral=True)
    gid = str(interaction.guild.id)
    hardban_db.setdefault(gid,{})[user_id] = {"reason": reason or "No reason", "moderator": str(interaction.user), "time": now_utc().isoformat()}
    save_json("hardbans.json", hardban_db)
    try: await interaction.guild.ban(user, reason=f"HARDBAN: {reason or ''}", delete_message_days=0)
    except Exception: pass
    await interaction.response.send_message(embed=_e_success("Hardbanned", f"**{user}** (`{user.id}`) hardbanned."))

@bot.tree.command(name="unhardban", description="Remove a hardban")
@app_commands.default_permissions(administrator=True)
async def unhardban(interaction: discord.Interaction, user_id: str):
    gid = str(interaction.guild.id)
    if hardban_db.get(gid,{}).pop(user_id,None) is None:
        return await interaction.response.send_message(embed=_e_error("Not Hardbanned","User not hardbanned."), ephemeral=True)
    save_json("hardbans.json", hardban_db)
    try: user = await bot.fetch_user(int(user_id)); await interaction.guild.unban(user, reason="Hardban removed")
    except Exception: pass
    await interaction.response.send_message(embed=_e_success("Hardban Removed", f"User `{user_id}` un-hardbanned."))

@bot.tree.command(name="hardbans", description="List all hardbanned users")
@app_commands.default_permissions(administrator=True)
async def hardbans(interaction: discord.Interaction):
    gid = str(interaction.guild.id); hbs = hardban_db.get(gid,{})
    if not hbs: return await interaction.response.send_message(embed=_e_info("No Hardbans","None."), ephemeral=True)
    e = discord.Embed(title=f"💀  Hardbanned Users ({len(hbs)})", color=C_RED)
    lines = [f"`{uid}` — {d.get('reason','?')} — by {d.get('moderator','?')}" for uid,d in list(hbs.items())[:20]]
    e.description = "\n".join(lines)
    await interaction.response.send_message(embed=e, ephemeral=True)

@bot.tree.command(name="softban", description="Ban then immediately unban (clears messages)")
@app_commands.default_permissions(ban_members=True)
async def softban(interaction: discord.Interaction, member: discord.Member, reason: str = None, delete_days: int = 7):
    if not has_cmd_perm(interaction, "softban"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    if not _can_target(interaction, member): return await interaction.response.send_message(embed=_e_error("Role Hierarchy",""), ephemeral=True)
    await dm_user(member, discord.Embed(title=f"🧹  Softbanned from {interaction.guild.name}",
                                         description=f"**Reason:** {reason or 'No reason'}\n*You may rejoin with a valid invite.*", color=C_ORANGE))
    await member.ban(reason=f"Softban: {reason}", delete_message_days=min(max(delete_days,1),7))
    await interaction.guild.unban(member, reason="Softban unban")
    await interaction.response.send_message(embed=_e_success("Member Softbanned",f"{member.mention} softbanned (messages cleared)."))
    await send_log(interaction.guild, _mod_embed("Soft Ban","🧹",C_ORANGE,interaction.user,member,reason))

@bot.tree.command(name="tempban", description="Temporarily ban a member")
@app_commands.describe(member="Member", duration="e.g. 1h 1d 7d", reason="Reason")
@app_commands.default_permissions(ban_members=True)
async def tempban(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = None):
    if not has_cmd_perm(interaction, "tempban"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    if not _can_target(interaction, member): return await interaction.response.send_message(embed=_e_error("Role Hierarchy",""), ephemeral=True)
    td = parse_dur(duration)
    if not td: return await interaction.response.send_message(embed=_e_error("Invalid Duration","Use `10m`,`2h`,`1d`."), ephemeral=True)
    expires = (now_utc() + td).timestamp()
    gid = str(interaction.guild.id); uid = str(member.id)
    tempban_db.setdefault(gid,{})[uid] = {"expires": expires, "reason": reason or "No reason", "moderator": str(interaction.user)}
    save_json("tempbans.json", tempban_db)
    await dm_user(member, discord.Embed(title=f"⏳  Temp Banned from {interaction.guild.name}",
                                         description=(f"**Duration:** {dur_str(td)}\n"
                                                      f"**Expires:** <t:{int(expires)}:F>\n"
                                                      f"**Reason:** {reason or 'No reason'}"),
                                         color=C_ORANGE))
    await member.ban(reason=f"Tempban ({duration}): {reason}", delete_message_days=1)
    e = _e_success("Member Tempbanned", f"{member.mention} banned for **{dur_str(td)}**.")
    e.add_field(name="Expires", value=f"<t:{int(expires)}:R>", inline=True)
    await interaction.response.send_message(embed=e)
    await send_log(interaction.guild, _mod_embed("Temp Ban","⏳",C_ORANGE,interaction.user,member,reason,
                                                  {"Duration":dur_str(td),"Expires":f"<t:{int(expires)}:R>"}))

@bot.tree.command(name="unban", description="Unban a user by their ID")
@app_commands.default_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: str, reason: str = None):
    if not has_cmd_perm(interaction, "unban"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user, reason=reason)
        tempban_db.get(str(interaction.guild.id),{}).pop(user_id,None); save_json("tempbans.json",tempban_db)
        e = _e_success("Member Unbanned",f"**{user}** has been unbanned.")
        e.add_field(name="Reason", value=reason or "No reason")
        await interaction.response.send_message(embed=e)
        await send_log(interaction.guild, _log_embed("Member Unbanned", C_GREEN, icon="🔓",
            fields=[("👤  User", f"`{user}` `{user.id}`", True),
                    ("🛡️  By",   interaction.user.mention, True),
                    ("📝  Reason", reason or "No reason", True)]))
    except (discord.NotFound,ValueError):
        await interaction.response.send_message(embed=_e_error("Not Found","User not found or not banned."), ephemeral=True)

@bot.tree.command(name="kick", description="Kick a member")
@app_commands.default_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if not has_cmd_perm(interaction, "kick"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    if not interaction.user.guild_permissions.kick_members: return await interaction.response.send_message(embed=_e_error("No Permission",""), ephemeral=True)
    if not _can_target(interaction, member): return await interaction.response.send_message(embed=_e_error("Role Hierarchy",""), ephemeral=True)
    await dm_user(member, discord.Embed(title=f"👢  Kicked from {interaction.guild.name}",
                                         description=f"**Reason:** {reason or 'No reason'}\n*You may rejoin.*", color=C_ORANGE))
    await member.kick(reason=reason)
    e = _e_success("Member Kicked", f"{member.mention} has been kicked.")
    e.add_field(name="Reason", value=reason or "No reason")
    await interaction.response.send_message(embed=e)
    await send_log(interaction.guild, _mod_embed("Member Kicked","👢",C_ORANGE,interaction.user,member,reason))
    # Anti-nuke kick tracking
    async for entry in interaction.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
        if entry.target and entry.target.id == member.id:
            await antinuke_check(interaction.guild, entry.user.id, "kick")
            break

@bot.tree.command(name="timeout", description="Timeout a member  e.g. 10m 2h 1d")
@app_commands.default_permissions(moderate_members=True)
async def timeout_cmd(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = None):
    if not has_cmd_perm(interaction, "timeout"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    if not _can_target(interaction, member): return await interaction.response.send_message(embed=_e_error("Role Hierarchy",""), ephemeral=True)
    td = parse_dur(duration)
    if not td: return await interaction.response.send_message(embed=_e_error("Invalid Duration","Use `10m`,`2h`,`1d`."), ephemeral=True)
    await member.timeout(td, reason=reason)
    e = _e_success("Member Timed Out", f"{member.mention} timed out for **{dur_str(td)}**.")
    e.add_field(name="Duration", value=dur_str(td), inline=True)
    e.add_field(name="Reason",   value=reason or "No reason", inline=True)
    await interaction.response.send_message(embed=e)
    await dm_user(member, discord.Embed(title=f"⏱️  Timed Out in {interaction.guild.name}",
                                         description=f"**Duration:** {dur_str(td)}\n**Reason:** {reason or 'No reason'}",
                                         color=C_YELLOW))
    await send_log(interaction.guild, _mod_embed("Timeout","⏱️",C_YELLOW,interaction.user,member,reason,{"Duration":dur_str(td)}))

@bot.tree.command(name="untimeout", description="Remove a member's timeout")
@app_commands.default_permissions(moderate_members=True)
async def untimeout(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if not has_cmd_perm(interaction, "untimeout"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    await member.timeout(None, reason=reason)
    await interaction.response.send_message(embed=_e_success("Timeout Removed",f"{member.mention}'s timeout removed."))
    await send_log(interaction.guild, _log_embed("Timeout Removed", C_GREEN, icon="🔓",
        thumbnail=member.display_avatar.url,
        fields=[("👤  User", f"{member.mention}", True), ("🛡️  By", interaction.user.mention, True)]))

@bot.tree.command(name="warn", description="Issue a formal warning to a member")
@app_commands.describe(member="Member to warn", reason="Reason for the warning")
@app_commands.default_permissions(manage_messages=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
    if not has_cmd_perm(interaction, "warn"):
        return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    gid   = str(interaction.guild.id)
    count = warn_user(gid, str(member.id), reason, str(interaction.user))

    # DM the warned user
    await dm_user(member, discord.Embed(
        title=f"⚠️  Warning in {interaction.guild.name}",
        description=f"**Reason:** {reason}\n**Total warnings:** {count}",
        color=C_YELLOW))

    # Response embed — show threshold hint if configured
    cfg_w = gcfg(interaction.guild.id)
    thr   = cfg_w.get("warn_thresholds", {})
    next_thr = next((k for k in sorted(thr, key=int) if int(k) > count), None)
    e = _e_success("⚠️  Warning Issued",
                   f"{member.mention} warned — they now have **{count}** warning(s).")
    e.add_field(name="Reason", value=reason, inline=False)
    if next_thr and str(next_thr) in thr:
        e.add_field(name="⚡  Next Threshold",
                    value=f"Action `{thr[str(next_thr)]}` triggers at **{next_thr}** warns",
                    inline=False)
    await interaction.response.send_message(embed=e)
    await send_log(interaction.guild, _mod_embed(
        "Warning Issued", "⚠️", C_YELLOW, interaction.user, member, reason,
        {"Total Warns": str(count)}))

    # Log case
    _add_case(gid, {
        "action":    "warn",
        "user_id":   str(member.id),
        "mod_id":    str(interaction.user.id),
        "reason":    reason,
        "timestamp": int(now_utc().timestamp()),
        "extra":     f"warn #{count}",
    })

    # Auto-escalate if threshold hit
    await _apply_warn_escalation(interaction, member, count)

@bot.tree.command(name="warnings", description="View warnings for a member")
async def warnings_cmd(interaction: discord.Interaction, member: discord.Member):
    gid = str(interaction.guild.id); uid = str(member.id)
    warns = warnings_db.get(gid,{}).get(uid,[])
    if not warns: return await interaction.response.send_message(embed=_e_success("No Warnings",f"{member.mention} has no warnings."), ephemeral=True)
    e = discord.Embed(title=f"⚠️  Warnings for {member}", color=C_YELLOW)
    e.set_thumbnail(url=member.display_avatar.url)
    e.set_footer(text=f"Total: {len(warns)}")
    for i, w in enumerate(warns,1):
        e.add_field(name=f"#{i}",
                    value=f"**Reason:** {w['reason']}\n**By:** {w['moderator']}\n**At:** {w['time']}",
                    inline=False)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="clearwarnings", description="Clear all warnings for a member")
@app_commands.default_permissions(manage_messages=True)
async def clearwarnings(interaction: discord.Interaction, member: discord.Member):
    if not has_cmd_perm(interaction, "clearwarnings"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    warnings_db.setdefault(str(interaction.guild.id),{})[str(member.id)] = []
    save_json("warnings.json", warnings_db)
    await interaction.response.send_message(embed=_e_success("Warnings Cleared",f"All warnings cleared for {member.mention}."))

@bot.tree.command(name="delwarn", description="Delete a specific warning by number")
@app_commands.default_permissions(manage_messages=True)
async def delwarn(interaction: discord.Interaction, member: discord.Member, warning_number: int):
    if not has_cmd_perm(interaction, "delwarn"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    gid = str(interaction.guild.id); uid = str(member.id)
    w = warnings_db.get(gid,{}).get(uid,[])
    if warning_number < 1 or warning_number > len(w):
        return await interaction.response.send_message(embed=_e_error("Invalid","Warning not found."), ephemeral=True)
    removed = w.pop(warning_number-1); save_json("warnings.json",warnings_db)
    await interaction.response.send_message(embed=_e_success("Warning Removed",f"Warning #{warning_number} removed.\n**Was:** `{removed['reason']}`"))

@bot.tree.command(name="purge", description="Delete messages from this channel")
@app_commands.describe(amount="1–100", member="Only delete from this member")
@app_commands.default_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: int, member: discord.Member = None):
    if not has_cmd_perm(interaction, "purge"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    if not 1 <= amount <= 100: return await interaction.response.send_message(embed=_e_error("Invalid","1–100 only."), ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    try:
        ch = interaction.channel
        # Build kwargs — do NOT pass check=None; omit it entirely when no filter
        purge_kwargs: dict = {"limit": amount}
        if member is not None:
            # Capture member.id in closure to avoid reference issues
            _mid = member.id
            purge_kwargs["check"] = lambda m: m.author.id == _mid
        deleted = await ch.purge(**purge_kwargs)
        target_str = f" from {member.mention}" if member else ""
        await interaction.followup.send(
            embed=_e_success("Purged", f"Deleted **{len(deleted)}** message(s){target_str}."),
            ephemeral=True)
        await send_log(interaction.guild, _log_embed("Messages Purged", C_BLUE, icon="🗑️",
            fields=[("📂  Channel", ch.mention, True),
                    ("🛡️  By",      interaction.user.mention,    True),
                    ("🔢  Count",   str(len(deleted)),           True),
                    ("👤  Target",  member.mention if member else "Everyone", True)]))
    except discord.Forbidden:
        await interaction.followup.send(embed=_e_error("Missing Permissions",
            "I need **Manage Messages** permission in this channel."), ephemeral=True)
    except discord.HTTPException as ex:
        await interaction.followup.send(embed=_e_error("Purge Failed", str(ex)), ephemeral=True)

@bot.tree.command(name="slowmode", description="Set channel slowmode")
@app_commands.describe(seconds="0 to disable, max 21600")
@app_commands.default_permissions(manage_channels=True)
async def slowmode(interaction: discord.Interaction, seconds: int):
    if not has_cmd_perm(interaction, "slowmode"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    if not 0 <= seconds <= 21600: return await interaction.response.send_message(embed=_e_error("Invalid","0–21600."), ephemeral=True)
    await interaction.channel.edit(slowmode_delay=seconds)
    msg = f"Slowmode set to **{seconds}s**." if seconds else "Slowmode **disabled**."
    await interaction.response.send_message(embed=_e_success("Slowmode Updated",msg))
    await send_log(interaction.guild, _log_embed("Slowmode Changed", C_YELLOW, icon="🐢",
        fields=[("📂  Channel", interaction.channel.mention, True),
                ("⏱️  Delay",   f"{seconds}s",               True),
                ("🛡️  By",      interaction.user.mention,    True)]))

@bot.tree.command(name="lock", description="Lock this channel — denies @everyone and an optional extra role")
@app_commands.describe(
    reason="Reason for locking",
    role="Extra role to also deny (e.g. @Verified) — @everyone is always denied")
@app_commands.default_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction, reason: str = None, role: discord.Role = None):
    if not has_cmd_perm(interaction, "lock"):
        return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    # Defer FIRST — set_permissions is an API call and can exceed the 3s interaction timeout
    await interaction.response.defer()
    cfg = gcfg(interaction.guild.id)
    perm = cfg.get("lock_deny_perm", "send_messages")
    ch = interaction.channel

    def _apply_deny(ow):
        if perm in ("all", "send_messages"):            ow.send_messages = False
        if perm in ("all", "add_reactions"):            ow.add_reactions = False
        if perm in ("all", "use_application_commands"): ow.use_application_commands = False
        return ow

    try:
        # Deny @everyone
        ow = ch.overwrites_for(interaction.guild.default_role)
        await ch.set_permissions(interaction.guild.default_role, overwrite=_apply_deny(ow))

        # Deny the extra role if provided
        if role:
            row = ch.overwrites_for(role)
            await ch.set_permissions(role, overwrite=_apply_deny(row))

        # Restore access for exempt roles (staff/mods who should still chat)
        for rid in cfg.get("lock_exempt_roles", []):
            exempt = interaction.guild.get_role(int(rid))
            if exempt and exempt != role:
                eow = ch.overwrites_for(exempt)
                if perm in ("all", "send_messages"):            eow.send_messages = True
                if perm in ("all", "add_reactions"):            eow.add_reactions = True
                if perm in ("all", "use_application_commands"): eow.use_application_commands = True
                await ch.set_permissions(exempt, overwrite=eow)

        locked_roles = f"@everyone" + (f", {role.mention}" if role else "")
        e = discord.Embed(title="🔒  Channel Locked",
                          description=f"**Locked for:** {locked_roles}\n**Reason:** {reason or 'No reason'}\n**By:** {interaction.user.mention}",
                          color=C_RED)
        e.timestamp = now_utc()
        e.set_footer(text="TSR Bot  •  Use /unlock to reopen")
        await interaction.followup.send(embed=e)
        await send_log(interaction.guild, _log_embed("Channel Locked", C_RED, icon="🔒",
            fields=[("📂  Channel",     ch.mention,                     True),
                    ("🔒  Locked For",  locked_roles,                   True),
                    ("🛡️  By",          interaction.user.mention,       True),
                    ("📝  Reason",      reason or "No reason",          False)]))
    except discord.Forbidden:
        await interaction.followup.send(embed=_e_error("Missing Permissions",
            "I need **Manage Channels** permission and my role must be above the role being locked."))
    except Exception as ex:
        await interaction.followup.send(embed=_e_error("Lock Failed", str(ex)))

@bot.tree.command(name="unlock", description="Unlock this channel")
@app_commands.describe(role="Role that was denied on lock — restores their access too (e.g. @Verified)")
@app_commands.default_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction, role: discord.Role = None):
    if not has_cmd_perm(interaction, "unlock"):
        return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    # Defer FIRST — API call can exceed 3s interaction timeout
    await interaction.response.defer()
    cfg = gcfg(interaction.guild.id)
    perm = cfg.get("lock_deny_perm", "send_messages")
    ch = interaction.channel

    def _apply_reset(ow):
        if perm in ("all", "send_messages"):            ow.send_messages = None
        if perm in ("all", "add_reactions"):            ow.add_reactions = None
        if perm in ("all", "use_application_commands"): ow.use_application_commands = None
        return ow

    try:
        # Restore @everyone
        ow = ch.overwrites_for(interaction.guild.default_role)
        await ch.set_permissions(interaction.guild.default_role, overwrite=_apply_reset(ow))

        # Restore the extra role if provided
        if role:
            row = ch.overwrites_for(role)
            await ch.set_permissions(role, overwrite=_apply_reset(row))

        unlocked_roles = "@everyone" + (f", {role.mention}" if role else "")
        e = discord.Embed(title="🔓  Channel Unlocked",
                          description=f"**Restored for:** {unlocked_roles}\n**By:** {interaction.user.mention}",
                          color=C_GREEN)
        e.timestamp = now_utc()
        await interaction.followup.send(embed=e)
        await send_log(interaction.guild, _log_embed("Channel Unlocked", C_GREEN, icon="🔓",
            fields=[("📂  Channel",      ch.mention,                True),
                    ("🔓  Restored For", unlocked_roles,            True),
                    ("🛡️  By",           interaction.user.mention,  True)]))
    except discord.Forbidden:
        await interaction.followup.send(embed=_e_error("Missing Permissions",
            "I need **Manage Channels** permission."))
    except Exception as ex:
        await interaction.followup.send(embed=_e_error("Unlock Failed", str(ex)))

@bot.tree.command(name="lockdown", description="🚨 Lock ALL channels (emergency)")
@app_commands.default_permissions(administrator=True)
async def lockdown(interaction: discord.Interaction, reason: str = None):
    if not has_cmd_perm(interaction, "lockdown"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    await interaction.response.defer()
    count = 0
    for ch in interaction.guild.text_channels:
        try:
            ow = ch.overwrites_for(interaction.guild.default_role); ow.send_messages = False
            await ch.set_permissions(interaction.guild.default_role, overwrite=ow); count += 1
        except Exception: pass
    e = discord.Embed(title="🚨  SERVER LOCKDOWN ACTIVE",
                      description=f"**{count}** channels locked.\n**Reason:** {reason or 'No reason'}\n**By:** {interaction.user.mention}",
                      color=C_RED)
    e.timestamp = now_utc()
    await interaction.followup.send(embed=e)
    await send_log(interaction.guild, _log_embed("SERVER LOCKDOWN", C_RED, icon="🚨",
        fields=[("🛡️  By",interaction.user.mention,True),("🔢  Channels",str(count),True),
                ("📝  Reason",reason or "No reason",True)]))

@bot.tree.command(name="endlockdown", description="End server lockdown")
@app_commands.default_permissions(administrator=True)
async def endlockdown(interaction: discord.Interaction):
    if not has_cmd_perm(interaction, "endlockdown"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    await interaction.response.defer()
    count = 0
    for ch in interaction.guild.text_channels:
        try:
            ow = ch.overwrites_for(interaction.guild.default_role); ow.send_messages = None
            await ch.set_permissions(interaction.guild.default_role, overwrite=ow); count += 1
        except Exception: pass
    await interaction.followup.send(embed=_e_success("Lockdown Ended",f"**{count}** channels unlocked."))

@bot.tree.command(name="nick", description="Change a member's nickname")
@app_commands.default_permissions(manage_nicknames=True)
async def nick(interaction: discord.Interaction, member: discord.Member, nickname: str = None):
    if not has_cmd_perm(interaction, "nick"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    old = member.display_name; await member.edit(nick=nickname)
    await interaction.response.send_message(embed=_e_success("Nickname Updated",f"`{old}` → `{nickname or member.name}`"))

@bot.tree.command(name="role", description="Add or remove a role from a member")
@app_commands.default_permissions(manage_roles=True)
async def role_cmd(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not has_cmd_perm(interaction, "role"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    if role >= interaction.guild.me.top_role: return await interaction.response.send_message(embed=_e_error("Role Too High","I can't manage that role."), ephemeral=True)
    if role in member.roles:
        await member.remove_roles(role)
        await interaction.response.send_message(embed=_e_success("Role Removed",f"Removed {role.mention} from {member.mention}."))
    else:
        await member.add_roles(role)
        await interaction.response.send_message(embed=_e_success("Role Added",f"Added {role.mention} to {member.mention}."))

@bot.tree.command(name="massrole", description="Add or remove a role from ALL members")
@app_commands.default_permissions(administrator=True)
async def massrole(interaction: discord.Interaction, role: discord.Role, action: str = "add"):
    if not has_cmd_perm(interaction, "massrole"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    await interaction.response.defer()
    count = 0
    for m in interaction.guild.members:
        try:
            if action == "add" and role not in m.roles: await m.add_roles(role); count += 1
            elif action == "remove" and role in m.roles: await m.remove_roles(role); count += 1
        except Exception: pass
    await interaction.followup.send(embed=_e_success("Mass Role",
        f"{'Added' if action=='add' else 'Removed'} {role.mention} for **{count}** members."))

@bot.tree.command(name="vcmute",   description="Voice mute a member")
@app_commands.default_permissions(mute_members=True)
async def vcmute(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if not has_cmd_perm(interaction, "vcmute"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    await member.edit(mute=True, reason=reason)
    await interaction.response.send_message(embed=_e_success("Voice Muted",f"{member.mention} voice muted."))

@bot.tree.command(name="vcunmute", description="Remove voice mute")
@app_commands.default_permissions(mute_members=True)
async def vcunmute(interaction: discord.Interaction, member: discord.Member):
    if not has_cmd_perm(interaction, "vcunmute"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    await member.edit(mute=False)
    await interaction.response.send_message(embed=_e_success("Voice Unmuted",f"{member.mention} unmuted."))

@bot.tree.command(name="deafen", description="Deafen a member in voice")
@app_commands.default_permissions(deafen_members=True)
async def deafen(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if not has_cmd_perm(interaction, "deafen"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    await member.edit(deafen=True, reason=reason)
    await interaction.response.send_message(embed=_e_success("Deafened",f"{member.mention} deafened."))

@bot.tree.command(name="undeafen", description="Undeafen a member")
@app_commands.default_permissions(deafen_members=True)
async def undeafen(interaction: discord.Interaction, member: discord.Member):
    if not has_cmd_perm(interaction, "undeafen"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    await member.edit(deafen=False)
    await interaction.response.send_message(embed=_e_success("Undeafened",f"{member.mention} undeafened."))

@bot.tree.command(name="move", description="Move a member to another voice channel")
@app_commands.default_permissions(move_members=True)
async def move(interaction: discord.Interaction, member: discord.Member, channel: discord.VoiceChannel):
    if not has_cmd_perm(interaction, "move"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    if not member.voice: return await interaction.response.send_message(embed=_e_error("Not in Voice",""), ephemeral=True)
    await member.move_to(channel)
    await interaction.response.send_message(embed=_e_success("Moved",f"{member.mention} moved to **{channel.name}**."))


# ═══════════════════════════════════════════════════════════════════════════
#  GIVEAWAY SYSTEM
# ═══════════════════════════════════════════════════════════════════════════

class GiveawayView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Enter Giveaway", style=discord.ButtonStyle.success,
                       emoji="🎉", custom_id="tsr_giveaway_v3")
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg_id = str(interaction.message.id); gid = str(interaction.guild.id)
        ga = giveaway_db.get(gid,{}).get(msg_id)
        if not ga or ga.get("ended"):
            return await interaction.response.send_message(embed=_e_error("Giveaway Ended","This giveaway is no longer active."), ephemeral=True)
        uid = str(interaction.user.id)
        ga.setdefault("entries",[])
        if uid in ga["entries"]:
            ga["entries"].remove(uid); save_json("giveaways.json",giveaway_db)
            return await interaction.response.send_message(embed=_e_info("Entry Removed","You've left the giveaway."), ephemeral=True)
        ga["entries"].append(uid); save_json("giveaways.json",giveaway_db)
        await interaction.response.send_message(embed=_e_success("Entered!",f"You're in! **{len(ga['entries'])}** total entries."), ephemeral=True)

async def _pick_winners(ga, count, guild):
    members = [guild.get_member(int(u)) for u in ga.get("entries",[]) if guild.get_member(int(u))]
    return random.sample(members, min(count, len(members))) if members else []

async def _end_giveaway(gid, msg_id, guild, channel, reroll=False):
    ga = giveaway_db.get(gid,{}).get(msg_id)
    if not ga or (ga.get("ended") and not reroll): return
    ga["ended"] = True; save_json("giveaways.json",giveaway_db)
    winners = await _pick_winners(ga, ga["winners"], guild)
    if winners:
        mentions = " ".join(w.mention for w in winners)
        e = discord.Embed(title="🎉  Giveaway Ended — We Have a Winner!",
                          description=f"**Prize:** {ga['prize']}\n**Winner(s):** {mentions}",
                          color=C_GREEN)
        e.set_footer(text="🎊  Congratulations!  •  TSR Giveaways")
        e.timestamp = now_utc()
        try: await channel.send(content=mentions, embed=e)
        except Exception: pass
    else:
        try: await channel.send(embed=_e_error("No Winners","Nobody entered the giveaway."))
        except Exception: pass

@bot.tree.command(name="giveaway", description="Start a giveaway")
@app_commands.describe(prize="Prize description", duration="e.g. 1h 24h 7d", winners="Number of winners")
@app_commands.default_permissions(manage_guild=True)
async def giveaway_cmd(interaction: discord.Interaction, prize: str, duration: str, winners: int = 1):
    if not has_cmd_perm(interaction, "giveaway"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    td = parse_dur(duration)
    if not td: return await interaction.response.send_message(embed=_e_error("Invalid Duration","Use `1h`,`1d`."), ephemeral=True)
    ends = now_utc() + td
    e = discord.Embed(title="🎉  GIVEAWAY!", color=C_PINK)
    e.description = (f"**Prize:** {prize}\n\n"
                     f"Press **Enter Giveaway** below to participate!\n"
                     f"Clicking again removes your entry.")
    e.add_field(name="⏰  Ends",    value=f"<t:{int(ends.timestamp())}:R>", inline=True)
    e.add_field(name="🏆  Winners", value=str(winners),                     inline=True)
    e.add_field(name="👤  Entries", value="0",                              inline=True)
    e.set_footer(text=f"Hosted by {interaction.user}  •  TSR Giveaways")
    e.timestamp = now_utc()
    await interaction.response.send_message(embed=e, view=GiveawayView())
    msg = await interaction.original_response()
    gid = str(interaction.guild.id)
    giveaway_db.setdefault(gid,{})[str(msg.id)] = {
        "prize": prize, "winners": winners, "ends_at": ends.timestamp(),
        "host_id": str(interaction.user.id), "channel": str(interaction.channel.id),
        "entries": [], "ended": False,
    }
    save_json("giveaways.json",giveaway_db)
    async def _end():
        await asyncio.sleep(td.total_seconds())
        await _end_giveaway(gid, str(msg.id), interaction.guild, interaction.channel)
    bot.loop.create_task(_end())

@bot.tree.command(name="greroll", description="Reroll a giveaway winner")
@app_commands.describe(message_id="Message ID of the giveaway")
@app_commands.default_permissions(manage_guild=True)
async def greroll(interaction: discord.Interaction, message_id: str):
    if not has_cmd_perm(interaction, "greroll"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    gid = str(interaction.guild.id); ga = giveaway_db.get(gid,{}).get(message_id)
    if not ga: return await interaction.response.send_message(embed=_e_error("Not Found","Giveaway not found. Right-click the giveaway → Copy Message ID."), ephemeral=True)
    await interaction.response.defer()
    ch = interaction.guild.get_channel(int(ga["channel"]))
    await _end_giveaway(gid, message_id, interaction.guild, ch, reroll=True)
    await interaction.followup.send(embed=_e_success("Rerolled!","New winner(s) picked."))

@bot.tree.command(name="gend", description="End a giveaway early")
@app_commands.describe(message_id="Message ID of the giveaway")
@app_commands.default_permissions(manage_guild=True)
async def gend(interaction: discord.Interaction, message_id: str):
    if not has_cmd_perm(interaction, "gend"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    gid = str(interaction.guild.id); ga = giveaway_db.get(gid,{}).get(message_id)
    if not ga: return await interaction.response.send_message(embed=_e_error("Not Found","Giveaway not found."), ephemeral=True)
    if ga.get("ended"): return await interaction.response.send_message(embed=_e_error("Already Ended",""), ephemeral=True)
    await interaction.response.defer()
    ch = interaction.guild.get_channel(int(ga["channel"]))
    await _end_giveaway(gid, message_id, interaction.guild, ch)
    await interaction.followup.send(embed=_e_success("Giveaway Ended","Winners picked."))

# ═══════════════════════════════════════════════════════════════════════════
#  SUGGESTION SYSTEM
# ═══════════════════════════════════════════════════════════════════════════

class SuggestionVoteView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Upvote",   style=discord.ButtonStyle.success, emoji="👍", custom_id="tsr_suggest_up_v3")
    async def upvote(self,   i: discord.Interaction, b): await _vote(i, "up")
    @discord.ui.button(label="Downvote", style=discord.ButtonStyle.danger,  emoji="👎", custom_id="tsr_suggest_dn_v3")
    async def downvote(self, i: discord.Interaction, b): await _vote(i, "down")

async def _vote(interaction: discord.Interaction, vtype: str):
    msg_id = str(interaction.message.id); gid = str(interaction.guild.id); uid = str(interaction.user.id)
    suggestions_db.setdefault(gid,{}).setdefault(msg_id,{"up":[],"down":[]})
    d = suggestions_db[gid][msg_id]; other = "down" if vtype=="up" else "up"
    if uid in d[other]: d[other].remove(uid)
    if uid in d[vtype]: d[vtype].remove(uid); action = "removed"
    else: d[vtype].append(uid); action = "added"
    save_json("suggestions.json",suggestions_db)
    try:
        emb = interaction.message.embeds[0]
        new = []
        for f in emb.fields:
            if "👍" in f.name: new.append(("👍  Upvotes",   str(len(d["up"])),   True))
            elif "👎" in f.name: new.append(("👎  Downvotes", str(len(d["down"])), True))
            else: new.append((f.name, f.value, f.inline))
        emb.clear_fields()
        for n,v,i in new: emb.add_field(name=n,value=v,inline=i)
        await interaction.message.edit(embed=emb)
    except Exception: pass
    await interaction.response.send_message(embed=_e_info("Vote Recorded",f"Your {vtype}vote has been {action}."), ephemeral=True)

@bot.tree.command(name="suggest", description="Submit a suggestion")
async def suggest(interaction: discord.Interaction, suggestion: str):
    cfg = gcfg(interaction.guild.id); ch_id = cfg.get("suggestion_channel")
    if not ch_id: return await interaction.response.send_message(embed=_e_error("Not Set Up","Ask an admin to use `/setupsuggestions`."), ephemeral=True)
    ch = interaction.guild.get_channel(int(ch_id))
    if not ch: return await interaction.response.send_message(embed=_e_error("Channel Missing",""), ephemeral=True)
    e = discord.Embed(title="💡  New Suggestion", description=f"```{suggestion}```", color=C_YELLOW)
    e.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
    e.add_field(name="👍  Upvotes",   value="0", inline=True)
    e.add_field(name="👎  Downvotes", value="0", inline=True)
    e.set_footer(text=f"Submitted by {interaction.user}  •  UserID: {interaction.user.id}")
    e.timestamp = now_utc()
    msg = await ch.send(embed=e, view=SuggestionVoteView())
    suggestions_db.setdefault(str(interaction.guild.id),{})[str(msg.id)] = {"up":[],"down":[]}
    save_json("suggestions.json",suggestions_db)
    await interaction.response.send_message(embed=_e_success("Suggestion Submitted",f"Posted in {ch.mention}."), ephemeral=True)

# ═══════════════════════════════════════════════════════════════════════════
#  AFK / REMIND / LEVELS
# ═══════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="afk", description="Set yourself as AFK")
async def afk(interaction: discord.Interaction, reason: str = "AFK"):
    gid = str(interaction.guild.id); uid = str(interaction.user.id)
    afk_db.setdefault(gid,{})[uid] = {"reason": reason, "since": now_utc().timestamp()}
    save_json("afk.json",afk_db)
    try: await interaction.user.edit(nick=f"[AFK] {interaction.user.display_name[:28]}")
    except Exception: pass
    await interaction.response.send_message(embed=_e_success("AFK Set",f"You are now AFK.\n**Reason:** {reason}"))

@bot.tree.command(name="remind", description="Set a reminder — bot will DM you")
@app_commands.describe(duration="When to remind you e.g. 10m 2h 1d", message="Reminder message")
async def remind(interaction: discord.Interaction, duration: str, message: str):
    td = parse_dur(duration)
    if not td: return await interaction.response.send_message(embed=_e_error("Invalid Duration","Use `10m`,`2h`,`1d`."), ephemeral=True)
    remind_at = now_utc().timestamp() + td.total_seconds()
    reminders_db.append({"user_id": interaction.user.id, "message": message, "remind_at": remind_at, "set_ago": dur_str(td)})
    save_json("reminders.json",reminders_db)
    e = _e_success("Reminder Set",f"I'll DM you in **{dur_str(td)}**.\n**Message:** {message}")
    e.add_field(name="Reminds at", value=f"<t:{int(remind_at)}:F>", inline=True)
    await interaction.response.send_message(embed=e, ephemeral=True)

@bot.tree.command(name="rank", description="View your level and XP rank")
async def rank(interaction: discord.Interaction, member: discord.Member = None):
    m   = member or interaction.user; gid = str(interaction.guild.id)
    d   = levels_db.get(gid,{}).get(str(m.id),{"xp":0,"level":0})
    lvl = d["level"]; xp = d["xp"]; needed = xp_for_level(lvl+1)
    all_u   = sorted(levels_db.get(gid,{}).items(), key=lambda x: x[1].get("xp",0), reverse=True)
    rank_pos = next((i+1 for i,(uid,_) in enumerate(all_u) if uid==str(m.id)),"?")
    # Progress bar
    pct   = min(xp / needed, 1.0) if needed else 1.0
    filled = int(pct * 20); bar = "█" * filled + "░" * (20 - filled)
    e = discord.Embed(title=f"🏅  Rank Card — {m.display_name}", color=C_PINK)
    e.set_thumbnail(url=m.display_avatar.url)
    e.description = f"```{bar}  {int(pct*100)}%```"
    e.add_field(name="🏅  Level",    value=f"**{lvl}**",               inline=True)
    e.add_field(name="✨  XP",       value=f"{xp:,} / {needed:,}",     inline=True)
    e.add_field(name="📊  Rank",     value=f"**#{rank_pos}**",         inline=True)
    e.set_footer(text=f"Requested by {interaction.user}")
    e.timestamp = now_utc()
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="leaderboard", description="Top XP leaderboard")
async def leaderboard(interaction: discord.Interaction):
    gid  = str(interaction.guild.id); all_d = levels_db.get(gid,{})
    top  = sorted(all_d.items(), key=lambda x: x[1].get("xp",0), reverse=True)[:10]
    if not top: return await interaction.response.send_message(embed=_e_info("Leaderboard","No data yet."), ephemeral=True)
    medals = ["🥇","🥈","🥉"]
    e = discord.Embed(title=f"📊  XP Leaderboard", color=C_GOLD)
    e.set_author(name=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
    lines = []
    for i,(uid,d) in enumerate(top):
        medal  = medals[i] if i<3 else f"`#{i+1}`"
        member = interaction.guild.get_member(int(uid))
        name   = member.display_name if member else f"<@{uid}>"
        lines.append(f"{medal}  **{name}**  —  Lvl {d.get('level',0)}  ·  {d.get('xp',0):,} XP")
    e.description = "\n".join(lines)
    e.set_footer(text=f"Requested by {interaction.user}")
    e.timestamp = now_utc()
    await interaction.response.send_message(embed=e)

# ═══════════════════════════════════════════════════════════════════════════
#  UTILITY COMMANDS
# ═══════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="userinfo", description="Get info about a member")
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    m      = member or interaction.user
    roles  = [r.mention for r in reversed(m.roles) if not r.is_default()]
    flags  = []
    if m.public_flags.staff:           flags.append("👮  Discord Staff")
    if m.public_flags.partner:         flags.append("🤝  Partner")
    if m.public_flags.bug_hunter:      flags.append("🐛  Bug Hunter")
    if m.public_flags.early_supporter: flags.append("⭐  Early Supporter")
    if m.public_flags.verified_phone:  flags.append("📱  Phone Verified")
    if m.bot:                          flags.append("🤖  Bot")
    gid    = str(interaction.guild.id)
    warns  = len(warnings_db.get(gid,{}).get(str(m.id),[]))
    is_hb  = str(m.id) in hardban_db.get(gid,{})
    ld     = levels_db.get(gid,{}).get(str(m.id),{"xp":0,"level":0})
    status = {"online":"🟢","idle":"🟡","dnd":"🔴","offline":"⚫"}.get(str(m.status),"⚫")
    e = discord.Embed(color=m.color if m.color.value else C_BLUE)
    e.set_author(name=f"{m}  •  User Info", icon_url=m.display_avatar.url)
    e.set_thumbnail(url=m.display_avatar.url)
    e.add_field(name="🏷️  Username",       value=f"`{m}`",                                  inline=True)
    e.add_field(name="🆔  User ID",         value=f"`{m.id}`",                               inline=True)
    e.add_field(name=f"{status}  Status",   value=str(m.status).title(),                     inline=True)
    e.add_field(name="✏️  Nickname",        value=m.nick or "None",                          inline=True)
    e.add_field(name="📅  Account Created", value=f"<t:{int(m.created_at.timestamp())}:R>",  inline=True)
    e.add_field(name="📥  Joined Server",   value=f"<t:{int(m.joined_at.timestamp())}:R>",   inline=True)
    e.add_field(name="👑  Top Role",        value=m.top_role.mention,                        inline=True)
    e.add_field(name="🏅  Level",           value=f"Lvl {ld['level']} ({ld['xp']:,} XP)",   inline=True)
    e.add_field(name="⚠️  Warnings",       value=str(warns),                                 inline=True)
    if flags: e.add_field(name="🏅  Badges", value="\n".join(flags), inline=False)
    e.add_field(name=f"🎭  Roles ({len(roles)})", value=" ".join(roles[:10]) or "None", inline=False)
    if is_hb: e.add_field(name="💀  Hardbanned", value="⚠️  This user is hardbanned", inline=True)
    e.set_footer(text=f"Requested by {interaction.user}")
    e.timestamp = now_utc()
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="serverinfo", description="Get info about this server")
async def serverinfo(interaction: discord.Interaction):
    g     = interaction.guild
    bots  = sum(1 for m in g.members if m.bot)
    humans = g.member_count - bots
    online = sum(1 for m in g.members if m.status != discord.Status.offline and not m.bot)
    e = discord.Embed(title=g.name, description=g.description or "*No description set*", color=C_BLURPLE)
    if g.icon:   e.set_thumbnail(url=g.icon.url)
    if g.banner: e.set_image(url=g.banner.url)
    e.set_author(name="Server Information", icon_url=g.icon.url if g.icon else None)
    e.add_field(name="🆔  Server ID",    value=f"`{g.id}`",                                  inline=True)
    e.add_field(name="👑  Owner",         value=g.owner.mention,                              inline=True)
    e.add_field(name="🌍  Region",        value=str(g.preferred_locale),                      inline=True)
    e.add_field(name="👥  Members",       value=f"👤 {humans} humans\n🤖 {bots} bots",         inline=True)
    e.add_field(name="🟢  Online",        value=str(online),                                  inline=True)
    e.add_field(name="💬  Channels",      value=f"💬 {len(g.text_channels)} text  🔊 {len(g.voice_channels)} voice", inline=True)
    e.add_field(name="🎭  Roles",         value=str(len(g.roles)),                            inline=True)
    e.add_field(name="😀  Emojis",        value=str(len(g.emojis)),                           inline=True)
    e.add_field(name="💎  Boost",         value=f"Level {g.premium_tier}  ({g.premium_subscription_count} boosts)", inline=True)
    e.add_field(name="🔒  Verification",  value=str(g.verification_level).title(),            inline=True)
    e.add_field(name="📅  Created",       value=f"<t:{int(g.created_at.timestamp())}:R>",     inline=True)
    e.set_footer(text=f"Requested by {interaction.user}")
    e.timestamp = now_utc()
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="roleinfo", description="Get info about a role")
async def roleinfo(interaction: discord.Interaction, role: discord.Role):
    with_role = [m for m in interaction.guild.members if role in m.roles]
    perms = [p.replace("_"," ").title() for p,v in role.permissions if v]
    e = discord.Embed(title=f"  {role.name}", color=role.color)
    e.set_author(name="Role Information")
    e.add_field(name="🆔  ID",          value=f"`{role.id}`",                               inline=True)
    e.add_field(name="🎨  Color",       value=str(role.color),                               inline=True)
    e.add_field(name="👤  Members",     value=str(len(with_role)),                           inline=True)
    e.add_field(name="📌  Position",    value=str(role.position),                            inline=True)
    e.add_field(name="🤖  Managed",     value="Yes" if role.managed else "No",               inline=True)
    e.add_field(name="📢  Mentionable", value="Yes" if role.mentionable else "No",           inline=True)
    e.add_field(name="📅  Created",     value=f"<t:{int(role.created_at.timestamp())}:R>",  inline=True)
    if perms: e.add_field(name=f"🔑  Permissions ({len(perms)})", value=", ".join(perms[:20]) or "None", inline=False)
    e.set_footer(text=f"Requested by {interaction.user}")
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="channelinfo", description="Get info about a channel")
async def channelinfo(interaction: discord.Interaction, channel: discord.TextChannel = None):
    ch = channel or interaction.channel
    e = discord.Embed(title=f"#{ch.name}", color=C_BLUE)
    e.set_author(name="Channel Information")
    e.add_field(name="🆔  ID",         value=f"`{ch.id}`",                              inline=True)
    e.add_field(name="📂  Category",   value=ch.category.name if ch.category else "None", inline=True)
    e.add_field(name="📌  Position",   value=str(ch.position),                          inline=True)
    e.add_field(name="🐢  Slowmode",   value=f"{ch.slowmode_delay}s",                   inline=True)
    e.add_field(name="🔞  NSFW",       value="Yes" if ch.nsfw else "No",                inline=True)
    e.add_field(name="📅  Created",    value=f"<t:{int(ch.created_at.timestamp())}:R>", inline=True)
    if ch.topic: e.add_field(name="📝  Topic", value=ch.topic[:200], inline=False)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="avatar", description="Get a member's avatar")
async def avatar(interaction: discord.Interaction, member: discord.Member = None):
    m = member or interaction.user
    e = discord.Embed(title=f"🖼️  {m.display_name}'s Avatar", color=C_BLUE)
    e.set_image(url=m.display_avatar.url)
    e.add_field(name="🔗  Download",
                value=f"[PNG]({m.display_avatar.with_format('png').url})  |  [JPG]({m.display_avatar.with_format('jpg').url})")
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="banner", description="Get a member's profile banner")
async def banner(interaction: discord.Interaction, member: discord.Member = None):
    m    = member or interaction.user
    user = await bot.fetch_user(m.id)
    if not user.banner:
        return await interaction.response.send_message(embed=_e_error("No Banner",f"{m.display_name} has no banner."), ephemeral=True)
    e = discord.Embed(title=f"🖼️  {m.display_name}'s Banner", color=C_BLUE)
    e.set_image(url=user.banner.url)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    lat = round(bot.latency * 1000)
    bar_pct = min(lat / 400, 1.0); filled = int(bar_pct * 20); bar = "▓" * filled + "░" * (20 - filled)
    col = C_GREEN if lat < 100 else C_YELLOW if lat < 200 else C_RED
    qual = "Excellent" if lat < 100 else "Good" if lat < 200 else "High"
    e = discord.Embed(title="🏓  Pong!", color=col)
    e.description = f"```{bar}```"
    e.add_field(name="📡  API Latency", value=f"`{lat}ms`", inline=True)
    e.add_field(name="📶  Quality",     value=qual,          inline=True)
    e.set_footer(text="TSR Bot")
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="snipe", description="Show the last deleted message")
async def snipe(interaction: discord.Interaction):
    gid = str(interaction.guild.id); d = snipe_db.get(gid)
    if not d or d.get("channel") != interaction.channel.id:
        return await interaction.response.send_message(embed=_e_error("Nothing to Snipe","No recently deleted messages."), ephemeral=True)
    e = discord.Embed(description=d["content"] or "(no text)", color=C_PURPLE)
    e.set_author(name=d["author"], icon_url=d["avatar"])
    e.set_footer(text=f"👻  Sniped by {interaction.user}")
    e.timestamp = datetime.datetime.fromtimestamp(d["time"], tz=datetime.timezone.utc)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="editsnipe", description="Show the last edited message")
async def editsnipe(interaction: discord.Interaction):
    gid = str(interaction.guild.id); d = editsnipe_db.get(gid)
    if not d or d.get("channel") != interaction.channel.id:
        return await interaction.response.send_message(embed=_e_error("Nothing to Snipe","No recently edited messages."), ephemeral=True)
    e = discord.Embed(color=C_YELLOW)
    e.set_author(name=d["author"], icon_url=d["avatar"])
    e.add_field(name="Before", value=d["before"][:500] or "(empty)", inline=False)
    e.add_field(name="After",  value=d["after"][:500]  or "(empty)", inline=False)
    e.add_field(name="🔗  Jump", value=f"[Go to message]({d['jump_url']})", inline=False)
    e.set_footer(text=f"👻  Edit-sniped by {interaction.user}")
    e.timestamp = datetime.datetime.fromtimestamp(d["time"], tz=datetime.timezone.utc)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="say", description="Make the bot say something")
@app_commands.default_permissions(manage_messages=True)
async def say(interaction: discord.Interaction, message: str, channel: discord.TextChannel = None):
    if not has_cmd_perm(interaction, "say"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    target = channel or interaction.channel
    await target.send(message)
    await interaction.response.send_message(embed=_e_success("Sent",f"Message sent to {target.mention}."), ephemeral=True)

@bot.tree.command(name="embed", description="Send a custom embed")
@app_commands.describe(title="Title", description="Description",
                        color="Hex color e.g. ff0000 (no #)", channel="Channel to send to")
@app_commands.default_permissions(manage_messages=True)
async def embed_cmd(interaction: discord.Interaction, title: str, description: str,
                     color: str = "5865f2", channel: discord.TextChannel = None):
    if not has_cmd_perm(interaction, "embed"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    try: col = int(color.replace("#",""),16)
    except Exception: col = C_BLUE
    target = channel or interaction.channel
    e = discord.Embed(title=title, description=description, color=col)
    e.set_footer(text=f"Sent by {interaction.user}"); e.timestamp = now_utc()
    await target.send(embed=e)
    await interaction.response.send_message(embed=_e_success("Embed Sent",f"Sent to {target.mention}."), ephemeral=True)

@bot.tree.command(name="announce", description="Send an announcement embed")
@app_commands.default_permissions(manage_guild=True)
async def announce(interaction: discord.Interaction, channel: discord.TextChannel,
                    title: str, message: str, ping: discord.Role = None):
    if not has_cmd_perm(interaction, "announce"): return await interaction.response.send_message(embed=perm_denied(), ephemeral=True)
    e = discord.Embed(title=f"📢  {title}", description=message, color=C_BLUE)
    e.set_footer(text=f"Announced by {interaction.user}"); e.timestamp = now_utc()
    await channel.send(content=ping.mention if ping else None, embed=e)
    await interaction.response.send_message(embed=_e_success("Announcement Sent",f"Sent to {channel.mention}."), ephemeral=True)

@bot.tree.command(name="poll", description="Create a yes/no poll")
async def poll(interaction: discord.Interaction, question: str):
    e = discord.Embed(title="📊  Poll", description=f"**{question}**", color=C_PURPLE)
    e.set_footer(text=f"Poll by {interaction.user}"); e.timestamp = now_utc()
    await interaction.response.send_message(embed=e)
    msg = await interaction.original_response()
    await msg.add_reaction("✅"); await msg.add_reaction("❌")

@bot.tree.command(name="multipoll", description="Create a poll with up to 5 options")
@app_commands.describe(question="Question", options="Options separated by |  e.g. Option A|Option B|Option C")
async def multipoll(interaction: discord.Interaction, question: str, options: str):
    opts = [o.strip() for o in options.split("|")][:5]
    if len(opts) < 2: return await interaction.response.send_message(embed=_e_error("Invalid","At least 2 options."), ephemeral=True)
    emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣"]
    desc = f"**{question}**\n\n" + "\n".join(f"{emojis[i]}  {o}" for i,o in enumerate(opts))
    e = discord.Embed(title="📊  Multi-Poll", description=desc, color=C_PURPLE)
    e.set_footer(text=f"Poll by {interaction.user}"); e.timestamp = now_utc()
    await interaction.response.send_message(embed=e)
    msg = await interaction.original_response()
    for i in range(len(opts)): await msg.add_reaction(emojis[i])

@bot.tree.command(name="stats", description="View bot statistics")
async def stats(interaction: discord.Interaction):
    total_warns = sum(len(u) for g in warnings_db.values() for u in g.values())
    e = discord.Embed(title="🤖  TSR Bot — Statistics", color=C_BLURPLE)
    e.set_thumbnail(url=bot.user.display_avatar.url)
    e.add_field(name="🏠  Servers",       value=str(len(bot.guilds)),                              inline=True)
    e.add_field(name="👥  Total Members", value=f"{sum(g.member_count for g in bot.guilds):,}",   inline=True)
    e.add_field(name="📡  Ping",          value=f"{round(bot.latency*1000)}ms",                   inline=True)
    e.add_field(name="⚠️  Total Warns",   value=str(total_warns),                                 inline=True)
    e.add_field(name="💀  Hardbans",      value=str(sum(len(g) for g in hardban_db.values())),    inline=True)
    e.add_field(name="🎫  Tickets",       value=str(sum(c.get("ticket_count",0) for c in guild_config.values())), inline=True)
    e.set_footer(text="TSR Bot v3.0"); e.timestamp = now_utc()
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="8ball", description="Ask the magic 8-ball")
async def eightball(interaction: discord.Interaction, question: str):
    answers = [
        "✅  It is certain.","✅  Without a doubt.","✅  Yes, definitely.",
        "✅  Signs point to yes.","✅  Most likely.","✅  Outlook good.",
        "⚠️  Ask again later.","⚠️  Cannot predict now.","⚠️  Better not tell you now.",
        "❌  Don't count on it.","❌  My sources say no.","❌  Very doubtful.",
    ]
    e = discord.Embed(title="🎱  Magic 8-Ball", color=C_PURPLE)
    e.add_field(name="❓  Question", value=question,               inline=False)
    e.add_field(name="🎱  Answer",   value=random.choice(answers), inline=False)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="coinflip", description="Flip a coin")
async def coinflip(interaction: discord.Interaction):
    r = random.choice(["🪙  **Heads!**","🪙  **Tails!**"])
    await interaction.response.send_message(embed=_e_info("Coin Flip", r, color=C_GOLD))

@bot.tree.command(name="roll", description="Roll dice  e.g. 2d6 d20")
async def roll(interaction: discord.Interaction, dice: str = "d6"):
    m = re.match(r"^(\d*)d(\d+)$", dice.lower())
    if not m: return await interaction.response.send_message(embed=_e_error("Invalid","Use `2d6` or `d20`."), ephemeral=True)
    count = int(m.group(1) or 1); sides = int(m.group(2))
    if count > 50 or sides > 1000: return await interaction.response.send_message(embed=_e_error("Too Large","Max 50d1000."), ephemeral=True)
    rolls = [random.randint(1,sides) for _ in range(count)]
    e = _e_info(f"🎲  {dice.upper()}", color=C_TEAL)
    e.add_field(name="Rolls", value=str(rolls), inline=True)
    e.add_field(name="Total", value=str(sum(rolls)), inline=True)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="choose", description="Let the bot choose between options")
@app_commands.describe(options="Options separated by |")
async def choose(interaction: discord.Interaction, options: str):
    choices = [o.strip() for o in options.split("|") if o.strip()]
    if len(choices) < 2: return await interaction.response.send_message(embed=_e_error("Invalid","At least 2 options."), ephemeral=True)
    winner = random.choice(choices)
    e = _e_info("🤔  I Choose…", f"**{winner}**", color=C_PURPLE)
    e.set_footer(text=f"Options: {', '.join(choices)}")
    await interaction.response.send_message(embed=e)

# ═══════════════════════════════════════════════════════════════════════════
#  HELP COMMAND
# ═══════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="help", description="Full command reference")
async def help_cmd(interaction: discord.Interaction):
    e = discord.Embed(
        title="TSR Advanced Bot  ·  Command Reference",
        description=(
            "All commands use `/` (slash). Use `/setpermission` to control access.\n"
            "Admins always have access to all commands."
        ),
        color=C_BLURPLE
    )
    e.set_thumbnail(url=bot.user.display_avatar.url)
    e.add_field(name="🔨  Core Moderation", value=(
        "`/ban` `/kick` `/unban`\n"
        "`/timeout` `/untimeout`\n"
        "`/warn` `/warnings` `/clearwarnings` `/delwarn`\n"
        "`/purge` `/slowmode` `/nick` `/role`"
    ), inline=True)
    e.add_field(name="⚡  Advanced Mod", value=(
        "`/hardban` `/hardban_id` `/unhardban` `/hardbans`\n"
        "`/softban` `/tempban` `/massban`\n"
        "`/massrole` `/vcmute` `/vcunmute`\n"
        "`/deafen` `/undeafen` `/move`\n"
        "`/lock` `/unlock` `/lockdown` `/endlockdown`"
    ), inline=True)
    e.add_field(name="🛡️  Anti-Nuke", value=(
        "`/setupantinuke` — configure protection\n"
        "Detects: mass bans, kicks, channel deletes,\n"
        "role deletes, webhook creations\n"
        "Actions: strip roles, kick, or ban\n"
        "Whitelist roles are immune"
    ), inline=True)
    e.add_field(name="🔑  Permission Control", value=(
        "`/setpermission` — assign roles to cmd groups\n"
        "`/viewpermissions` — view current permissions\n\n"
        "Groups: `moderation` `utility` `community` `setup`\n"
        "Prevents members using mod commands"
    ), inline=True)
    e.add_field(name="📨  ModMail", value=(
        "`/setupmodmail` — configure\n"
        "`/mmclose` — close + transcript\n"
        "`/mmreply` — reply via slash\n"
        "Users DM the bot to open a thread"
    ), inline=True)
    e.add_field(name="🎫  Tickets", value=(
        "`/setuptickets` — panel + transcript\n"
        "`/closeticket` — close + save transcript\n"
        "Auto-transcript on every close"
    ), inline=True)
    e.add_field(name="✔️  Verification (secure)", value=(
        "`/setupverify` — method + min age + phone check\n"
        "Methods: `button` `code` `math` `reaction`\n"
        "Math CAPTCHA: solve a DM math question\n"
        "Min account age gate configurable"
    ), inline=True)
    e.add_field(name="🎉  Giveaways", value=(
        "`/giveaway` — start\n"
        "`/greroll` — reroll winner\n"
        "`/gend` — end early"
    ), inline=True)
    e.add_field(name="🏅  Levels & Community", value=(
        "`/rank` `/leaderboard`\n"
        "`/suggest` `/poll` `/multipoll`\n"
        "`/afk` `/remind`\n"
        "`/setuplevels` `/setupsuggestions`"
    ), inline=True)
    e.add_field(name="🎮  Roblox Watcher v4", value=(
        "`/setuproblox` — set channel + ping roles\n"
        "🟡 **Future update** when Studio > Player\n"
        "🔴 **Live update** when Player version changes\n"
        "Checks every **3 minutes**, posts version hash + download"
    ), inline=True)
    e.add_field(name="🍯  Honeypot", value=(
        "`/setuphoneypot` — set channels + action\n"
        "Anyone who types in honeypot → actioned\n"
        "Actions: softban, ban, kick, timeout\n"
        "Auto-logs every trigger"
    ), inline=True)
    e.add_field(name="📊  Stats Channels", value=(
        "`/setupstatschannels` — auto-updating voice channels\n"
        "Shows: members, online, bots, channels, roles\n"
        "Updates every 10 minutes"
    ), inline=True)
    e.add_field(name="📨  Invite Tracking", value=(
        "`/inviteleaderboard` — top inviters\n"
        "`/inviteinfo` — per-user invite stats\n"
        "Tracks which invite each member used on join\n"
        "Displayed in welcome message + join log"
    ), inline=True)
    e.add_field(name="🎵  Music (Spotify-style)", value=(
        "`/play` — Spotify link / YouTube URL / song name\n"
        "`/pause` `/resume` `/skip` `/stop` `/disconnect`\n"
        "`/queue` `/nowplaying` `/search`\n"
        "`/volume` `/loop` `/shuffle`\n"
        "Playlists & albums supported via Spotify links"
    ), inline=False)
    e.add_field(name="🛠️  Utility", value=(
        "`/userinfo` `/serverinfo` `/roleinfo` `/channelinfo`\n"
        "`/avatar` `/banner` `/ping` `/stats`\n"
        "`/snipe` `/editsnipe` `/say` `/embed` `/announce`"
    ), inline=True)
    e.add_field(name="🎲  Fun", value=(
        "`/8ball` `/coinflip` `/roll` `/choose`"
    ), inline=True)
    e.add_field(name="📋  Auto-Logging (log channel)", value=(
        "All mod actions  •  Message edits & deletes\n"
        "Member join/leave (with invite used)  •  Role changes  •  Nickname changes\n"
        "Voice state changes  •  Channel create/delete\n"
        "Anti-spam, anti-nuke, honeypot, bad words, link blocks\n"
        "Invite create/delete (with expiry)  •  Webhook activity"
    ), inline=False)
    e.set_footer(text="TSR Advanced Discord Bot v4.0  •  /setuplog first to enable logging!")
    e.timestamp = now_utc()
    await interaction.response.send_message(embed=e, ephemeral=True)

# ═══════════════════════════════════════════════════════════════════════════
#  HONEYPOT SETUP
# ═══════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="setuphoneypot", description="Configure honeypot channels — anyone who types gets actioned")
@app_commands.describe(
    channel="Channel to designate as a honeypot (add to list or remove if already set)",
    action="Action to take: softban | ban | kick | timeout",
    log="Whether to log honeypot triggers to the log channel"
)
@app_commands.default_permissions(administrator=True)
async def setuphoneypot(interaction: discord.Interaction,
                         channel: discord.TextChannel = None,
                         action: str = None,
                         log: bool = None):
    cfg = gcfg(interaction.guild.id)
    changes = []

    if channel:
        ch_list = cfg.setdefault("honeypot_channels", [])
        ch_id = str(channel.id)
        if ch_id in ch_list:
            ch_list.remove(ch_id)
            changes.append(f"Removed honeypot: {channel.mention}")
        else:
            ch_list.append(ch_id)
            changes.append(f"Added honeypot: {channel.mention}")

    if action:
        if action not in ("softban", "ban", "kick", "timeout"):
            return await interaction.response.send_message(
                embed=_e_error("Invalid Action", "Choose `softban`, `ban`, `kick`, or `timeout`."),
                ephemeral=True)
        cfg["honeypot_action"] = action
        changes.append(f"Action: `{action}`")

    if log is not None:
        cfg["honeypot_log"] = log
        changes.append(f"Log: `{log}`")

    save_cfg()

    active_channels = [
        interaction.guild.get_channel(int(c))
        for c in cfg.get("honeypot_channels", [])
        if interaction.guild.get_channel(int(c))
    ]

    e = _e_success("Honeypot Updated", "\n".join(changes) or "No changes made.")
    e.add_field(name="Active Honeypots",
                value="\n".join(c.mention for c in active_channels) or "None",
                inline=False)
    e.add_field(name="Action",  value=f"`{cfg.get('honeypot_action', 'softban')}`", inline=True)
    e.add_field(name="Logging", value="`ON`" if cfg.get("honeypot_log", True) else "`OFF`", inline=True)
    e.add_field(name="How it works", value=(
        "Any **non-bot, non-admin** member who sends a message in a honeypot channel "
        "will be automatically actioned.\n\n"
        "Make these channels invisible to mods/admins but visible to raid bots."
    ), inline=False)
    await interaction.response.send_message(embed=e)

# ═══════════════════════════════════════════════════════════════════════════
#  STATS CHANNELS SETUP
# ═══════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="setupstatschannels", description="Set voice channels that auto-display server statistics")
@app_commands.describe(
    members_channel="Voice channel to show total member count",
    online_channel="Voice channel to show online member count",
    bots_channel="Voice channel to show bot count",
    channels_channel="Voice channel to show total channel count",
    roles_channel="Voice channel to show total role count"
)
@app_commands.default_permissions(administrator=True)
async def setupstatschannels(interaction: discord.Interaction,
                              members_channel: discord.VoiceChannel = None,
                              online_channel: discord.VoiceChannel = None,
                              bots_channel: discord.VoiceChannel = None,
                              channels_channel: discord.VoiceChannel = None,
                              roles_channel: discord.VoiceChannel = None):
    cfg = gcfg(interaction.guild.id)
    changes = []

    def _set(key, ch, label):
        if ch:
            cfg[key] = str(ch.id)
            changes.append(f"{label}: {ch.mention}")

    _set("stat_ch_members",  members_channel,  "Members counter")
    _set("stat_ch_online",   online_channel,   "Online counter")
    _set("stat_ch_bots",     bots_channel,     "Bots counter")
    _set("stat_ch_channels", channels_channel, "Channels counter")
    _set("stat_ch_roles",    roles_channel,    "Roles counter")

    if not changes:
        return await interaction.response.send_message(
            embed=_e_error("No Channels Set", "Pass at least one voice channel parameter."),
            ephemeral=True)

    save_cfg()

    e = _e_success("Stats Channels Configured", "\n".join(changes))
    e.add_field(name="Update frequency", value="Every 10 minutes (Discord rate-limits channel edits)", inline=False)
    e.add_field(name="Tip", value="Create locked voice channels (no connect permission) and the bot will rename them automatically.", inline=False)
    await interaction.response.send_message(embed=e)

# ═══════════════════════════════════════════════════════════════════════════
#  INVITE COMMANDS
# ═══════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="inviteleaderboard", description="Show top inviters in this server")
async def inviteleaderboard(interaction: discord.Interaction):
    if not has_cmd_perm(interaction, "inviteleaderboard"):
        return await interaction.response.send_message(embed=_e_error("No Permission", "You don't have permission to use this command."), ephemeral=True)
    await interaction.response.defer()
    gid = str(interaction.guild.id)
    data = invite_db.get(gid, {})
    if not data:
        return await interaction.followup.send(embed=_e_error("No Data", "No invite data recorded yet. Make sure members have joined via tracked invites."))

    sorted_inviters = sorted(data.items(), key=lambda x: x[1].get("uses", 0), reverse=True)[:15]

    e = discord.Embed(title="📨  Invite Leaderboard", color=C_GOLD)
    e.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)

    rows = []
    for rank, (uid, info) in enumerate(sorted_inviters, 1):
        member = interaction.guild.get_member(int(uid))
        name   = member.mention if member else f"`{uid}`"
        uses   = info.get("uses", 0)
        medal  = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"`#{rank}`")
        rows.append(f"{medal} {name} — **{uses}** invite{'s' if uses != 1 else ''}")

    e.description = "\n".join(rows) or "No invites tracked yet."
    e.set_footer(text=f"Top {len(sorted_inviters)} inviters  •  TSR Bot v4")
    e.timestamp = now_utc()
    await interaction.followup.send(embed=e)

@bot.tree.command(name="inviteinfo", description="See how many invites a member has")
@app_commands.describe(member="Member to look up (leave blank for yourself)")
async def inviteinfo(interaction: discord.Interaction, member: discord.Member = None):
    if not has_cmd_perm(interaction, "inviteinfo"):
        return await interaction.response.send_message(embed=_e_error("No Permission", "You don't have permission to use this command."), ephemeral=True)
    target = member or interaction.user
    gid    = str(interaction.guild.id)
    info   = invite_db.get(gid, {}).get(str(target.id), {})
    uses   = info.get("uses", 0)
    invited_ids = info.get("members", [])

    e = discord.Embed(
        title=f"📨  Invite Info — {target.display_name}",
        color=C_BLUE
    )
    e.set_thumbnail(url=target.display_avatar.url)
    e.add_field(name="Total Invites",  value=str(uses), inline=True)
    e.add_field(name="Members Invited", value=str(len(invited_ids)), inline=True)

    # Show last 8 invited members
    if invited_ids:
        names = []
        for uid in invited_ids[-8:]:
            m = interaction.guild.get_member(int(uid))
            names.append(m.mention if m else f"`{uid}` (left)")
        e.add_field(name="Recently Invited", value="\n".join(reversed(names)), inline=False)

    e.set_footer(text="TSR Invite Tracker v4")
    e.timestamp = now_utc()
    await interaction.response.send_message(embed=e)

# ═══════════════════════════════════════════════════════════════════════════
#  MUSIC SYSTEM  —  Spotify-style (audio sourced from YouTube via yt-dlp)
# ═══════════════════════════════════════════════════════════════════════════

C_SPOTIFY = 0x1DB954   # Spotify green

YDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "socket_timeout": 30,
    "retries": 3,
    "extractor_retries": 3,
    # Use TV-embedded + Android clients — these bypass YouTube datacenter IP blocks
    "extractor_args": {
        "youtube": {
            "player_client": ["tv_embedded", "android", "web"],
            "player_skip": ["webpage"],
        }
    },
}
# SoundCloud fallback — used when YouTube is blocked (common on Railway/cloud IPs)
YDL_OPTS_SC = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "scsearch",
    "source_address": "0.0.0.0",
    "socket_timeout": 30,
    "retries": 3,
}
FFMPEG_OPTS = {
    "before_options": (
        "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
        "-nostdin -loglevel warning"
    ),
    "options": "-vn",
}

# Per-guild music state (in-memory)
music_queues:   dict = {}   # gid -> list[track dict]
music_playing:  dict = {}   # gid -> track dict | None
music_loop:     dict = {}   # gid -> bool
music_volume:   dict = {}   # gid -> float (0.0 – 2.0, default 1.0)
music_vc:       dict = {}   # gid -> discord.VoiceClient
music_dc_tasks: dict = {}   # gid -> asyncio.Task (pending auto-disconnect)

# ── Spotify client factory ────────────────────────────────────────────────

def _get_spotify():
    if not SPOTIPY_OK:
        return None
    cid  = os.environ.get("SPOTIFY_CLIENT_ID", "")
    csec = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
    if not cid or not csec:
        return None
    try:
        return spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(client_id=cid, client_secret=csec))
    except Exception:
        return None

# ── Helpers ───────────────────────────────────────────────────────────────

def _fmt_dur(seconds) -> str:
    if not seconds:
        return "?:??"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def _sp_id(url: str, kind: str) -> Optional[str]:
    m = re.search(rf"spotify\.com/{kind}/([A-Za-z0-9]+)", url)
    return m.group(1) if m else None

def _extract_with_opts(query: str, opts: dict) -> Optional[dict]:
    """Run a single yt-dlp extraction with the given opts dict."""
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if info and "entries" in info:
                entries = [e for e in info["entries"] if e]
                if not entries:
                    return None
                info = entries[0]
            if not info or not info.get("url"):
                return None
            return {
                "url":         info["url"],
                "webpage_url": info.get("webpage_url", ""),
                "title":       info.get("title", "Unknown"),
                "duration":    info.get("duration", 0),
                "thumbnail":   info.get("thumbnail", ""),
                "uploader":    info.get("uploader", ""),
            }
    except Exception as exc:
        return None

def _ytdl_fetch(query: str) -> Optional[dict]:
    """
    Try YouTube (with TV/Android client to bypass datacenter IP blocks),
    then fall back to SoundCloud if YouTube fails.
    """
    if not YT_DLP_OK:
        return None

    is_url = query.startswith("http")

    # ── Attempt 1: YouTube with TV-embedded / Android client ──────────────
    result = _extract_with_opts(query, YDL_OPTS)
    if result:
        return result

    # ── Attempt 2: SoundCloud fallback (cloud IPs are NOT blocked there) ──
    # For direct URLs that failed, extract a search term and try SoundCloud.
    # For plain text queries, search SoundCloud directly.
    sc_query = query
    if is_url:
        # Try to get the video title from the URL path as a search hint
        # e.g. "watch?v=..." → not useful, just use "music" as generic fallback
        # Better: strip the URL and use it as a ytsearch on SoundCloud
        sc_query = re.sub(r"https?://[^\s]+", "", query).strip() or query

    sc_result = _extract_with_opts(
        f"scsearch:{sc_query}" if not sc_query.startswith("http") else sc_query,
        YDL_OPTS_SC)
    if sc_result:
        print(f"[Music] YouTube blocked, playing from SoundCloud: {sc_result['title']}")
        return sc_result

    print(f"[Music] All sources failed for: {query!r}")
    return None

async def _yt_async(query: str) -> Optional[dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _ytdl_fetch, query)

async def _resolve_input(raw: str, sp) -> list:
    """
    Returns a list of track dicts ready to queue.
    Handles: Spotify track URL, Spotify playlist URL, Spotify album URL,
             YouTube URL, or plain search query.
    """
    tracks = []

    if "open.spotify.com" in raw:
        # ── Spotify track ──────────────────────────────────────────────────
        if "/track/" in raw:
            tid = _sp_id(raw, "track")
            if sp and tid:
                try:
                    t = sp.track(tid)
                    tracks.append({
                        "title":        t["name"],
                        "artist":       ", ".join(a["name"] for a in t["artists"]),
                        "search_query": f"{t['name']} {t['artists'][0]['name']} official audio",
                        "album_art":    t["album"]["images"][0]["url"] if t["album"]["images"] else "",
                        "spotify_url":  raw,
                        "duration":     t["duration_ms"] // 1000,
                    })
                except Exception:
                    pass

        # ── Spotify playlist ───────────────────────────────────────────────
        elif "/playlist/" in raw:
            pid = _sp_id(raw, "playlist")
            if sp and pid:
                try:
                    result = sp.playlist_tracks(pid, limit=50)
                    for item in result.get("items", []):
                        t = item.get("track")
                        if not t or not t.get("name"):
                            continue
                        tracks.append({
                            "title":        t["name"],
                            "artist":       ", ".join(a["name"] for a in t["artists"]),
                            "search_query": f"{t['name']} {t['artists'][0]['name']} official audio",
                            "album_art":    t["album"]["images"][0]["url"] if t["album"]["images"] else "",
                            "spotify_url":  f"https://open.spotify.com/track/{t['id']}",
                            "duration":     t["duration_ms"] // 1000,
                        })
                except Exception:
                    pass

        # ── Spotify album ──────────────────────────────────────────────────
        elif "/album/" in raw:
            aid = _sp_id(raw, "album")
            if sp and aid:
                try:
                    album = sp.album(aid)
                    art   = album["images"][0]["url"] if album["images"] else ""
                    for t in album["tracks"]["items"]:
                        tracks.append({
                            "title":        t["name"],
                            "artist":       ", ".join(a["name"] for a in t["artists"]),
                            "search_query": f"{t['name']} {t['artists'][0]['name']} official audio",
                            "album_art":    art,
                            "spotify_url":  f"https://open.spotify.com/track/{t['id']}",
                            "duration":     t["duration_ms"] // 1000,
                        })
                except Exception:
                    pass

    # ── Fallback: YouTube URL or plain search ──────────────────────────────
    if not tracks:
        if "open.spotify.com" in raw and not sp:
            tracks.append({
                "title":        "⚠️ Spotify credentials not set",
                "artist":       "",
                "search_query": None,
                "album_art":    "",
                "spotify_url":  raw,
                "duration":     0,
                "_error":       "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in Railway → Variables to use Spotify links. For now, try `/play Song Name Artist`.",
            })
        else:
            # For YouTube URLs: use the URL as webpage_url so we fetch the real title at play time.
            # For plain searches: use raw as search_query.
            is_yt_url = raw.startswith("http") and ("youtube.com" in raw or "youtu.be" in raw)
            tracks.append({
                "title":        raw if not is_yt_url else "Loading...",
                "artist":       "",
                "search_query": raw,
                "webpage_url":  raw if is_yt_url else "",
                "album_art":    "",
                "spotify_url":  "",
                "duration":     0,
            })

    return tracks

async def _cancel_dc_task(gid: str):
    """Cancel any pending auto-disconnect task for this guild."""
    task = music_dc_tasks.pop(gid, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

async def _auto_dc(guild: discord.Guild, gid: str):
    """Wait 3 minutes of silence then disconnect — cancellable."""
    await asyncio.sleep(180)
    vc = music_vc.get(gid)
    if vc and vc.is_connected() and not vc.is_playing():
        try:
            await vc.disconnect()
        except Exception:
            pass
        music_vc.pop(gid, None)
    music_dc_tasks.pop(gid, None)

async def _play_next(guild: discord.Guild, err_channel=None):
    """Dequeue next track and start playback. Called after each track ends."""
    gid = str(guild.id)
    vc  = music_vc.get(gid)
    if not vc or not vc.is_connected():
        return

    # Cancel any pending auto-disconnect — we're about to do something
    await _cancel_dc_task(gid)

    # ── Loop mode: replay current track ───────────────────────────────────
    if music_loop.get(gid) and music_playing.get(gid):
        cur  = music_playing[gid]
        info = await _yt_async(cur.get("webpage_url") or cur.get("search_query") or cur["title"])
        if info:
            cur["url"] = info["url"]
            vol = music_volume.get(gid, 1.0)
            src = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(info["url"], **FFMPEG_OPTS), volume=vol)
            vc.play(src, after=lambda e: asyncio.run_coroutine_threadsafe(
                _play_next(guild, err_channel), bot.loop))
            return
        # If re-fetch fails, fall through to next track

    # ── Get next track from queue ──────────────────────────────────────────
    q = music_queues.get(gid, [])
    if not q:
        music_playing[gid] = None
        # Schedule auto-disconnect as a cancellable background task
        task = asyncio.ensure_future(_auto_dc(guild, gid))
        music_dc_tasks[gid] = task
        return

    track = q.pop(0)
    music_queues[gid] = q
    music_playing[gid] = track

    # ── Resolve stream URL fresh (stream URLs expire quickly) ──────────────
    query = track.get("webpage_url") or track.get("search_query") or track["title"]
    info  = await _yt_async(query)

    # Fallback: try search_query if webpage_url failed
    if not info and track.get("search_query") and track.get("search_query") != query:
        info = await _yt_async(track["search_query"])

    if not info:
        # Notify channel and skip to next track
        ch = err_channel or track.get("np_channel")
        if ch:
            try:
                await ch.send(embed=_e_error(
                    "Track Unavailable",
                    f"Couldn't load **{track['title'][:80]}** — it may be age-restricted, region-locked, or unavailable. Skipping."))
            except Exception:
                pass
        await _play_next(guild, err_channel)
        return

    # Update track with real info from yt-dlp
    track.update({
        "url":         info["url"],
        "webpage_url": info.get("webpage_url") or track.get("webpage_url", ""),
        "thumbnail":   track.get("album_art") or info.get("thumbnail", ""),
        "duration":    track.get("duration") or info.get("duration", 0),
        # Only overwrite title if it was a placeholder URL
        "title":       (info.get("title") or track["title"])
                       if (track["title"] == "Loading..." or track["title"].startswith("http"))
                       else track["title"],
    })

    vol = music_volume.get(gid, 1.0)
    try:
        src = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(track["url"], **FFMPEG_OPTS), volume=vol)
    except Exception as ex:
        ch = err_channel or track.get("np_channel")
        if ch:
            try:
                await ch.send(embed=_e_error("Playback Error", f"FFmpeg failed: {ex}"))
            except Exception:
                pass
        await _play_next(guild, err_channel)
        return

    def _after(err):
        if err:
            print(f"[Music] Playback error in {guild.name}: {err}")
        asyncio.run_coroutine_threadsafe(_play_next(guild, err_channel), bot.loop)

    vc.play(src, after=_after)

    # Update bot presence
    try:
        await bot.change_presence(activity=discord.Activity(
            type=discord.ActivityType.listening,
            name=track["title"] + (f" · {track['artist']}" if track.get("artist") else "")))
    except Exception:
        pass

    # Post now-playing card
    np_ch = track.get("np_channel") or err_channel
    if np_ch:
        await _send_np(np_ch, track, gid)

async def _send_np(channel, track: dict, gid: str):
    queue_len = len(music_queues.get(gid, []))
    title_md  = (f"[{track['title']}]({track['webpage_url']})"
                 if track.get("webpage_url") else track["title"])
    desc      = f"**{title_md}**"
    if track.get("artist"):
        desc += f"\nby **{track['artist']}**"

    e = discord.Embed(title="▶️  Now Playing", description=desc, color=C_SPOTIFY)
    if track.get("thumbnail"):
        e.set_thumbnail(url=track["thumbnail"])
    e.add_field(name="⏱️  Duration",      value=_fmt_dur(track.get("duration")), inline=True)
    e.add_field(name="🔊  Volume",         value=f"{int(music_volume.get(gid, 1.0)*100)}%", inline=True)
    e.add_field(name="🔁  Loop",           value="`ON`" if music_loop.get(gid) else "`OFF`", inline=True)
    e.add_field(name="👤  Requested by",   value=track.get("requester_mention", "?"), inline=True)
    if track.get("spotify_url"):
        e.add_field(name="🎵  Spotify",    value=f"[Open track]({track['spotify_url']})", inline=True)
    e.set_footer(text=f"TSR Music  •  {queue_len} track{'s' if queue_len != 1 else ''} in queue")
    e.timestamp = now_utc()
    try:
        await channel.send(embed=e)
    except Exception:
        pass

# ── /play ─────────────────────────────────────────────────────────────────

@bot.tree.command(name="play", description="Play a song — paste a Spotify link, YouTube link, or just type a song name")
@app_commands.describe(song="Spotify URL / YouTube URL / song name to search")
async def music_play(interaction: discord.Interaction, song: str):
    if not has_cmd_perm(interaction, "play"):
        return await interaction.response.send_message(
            embed=_e_error("No Permission", "You don't have permission to use music commands."), ephemeral=True)

    if not YT_DLP_OK:
        return await interaction.response.send_message(
            embed=_e_error("Not Ready", "yt-dlp is not installed. Check `requirements.txt`."), ephemeral=True)

    if not interaction.user.voice or not interaction.user.voice.channel:
        return await interaction.response.send_message(
            embed=_e_error("Not in Voice", "Join a voice channel first, then use `/play`."), ephemeral=True)

    await interaction.response.defer()

    gid        = str(interaction.guild.id)
    sp         = _get_spotify()
    cfg_play   = gcfg(interaction.guild.id)

    # Respect music channel lock — bot always joins the designated VC
    locked_ch_id = cfg_play.get("music_channel")
    if locked_ch_id:
        locked_ch = interaction.guild.get_channel(int(locked_ch_id))
        vc_channel = locked_ch if locked_ch else interaction.user.voice.channel
    else:
        vc_channel = interaction.user.voice.channel

    # Connect or move to target VC
    vc = music_vc.get(gid)
    if not vc or not vc.is_connected():
        try:
            vc = await vc_channel.connect()
            music_vc[gid] = vc
        except Exception as exc:
            return await interaction.followup.send(
                embed=_e_error("Cannot Join VC", str(exc)))
    elif vc.channel != vc_channel:
        try:
            await vc.move_to(vc_channel)
        except Exception:
            pass

    # Resolve Spotify / YouTube / search
    tracks = await _resolve_input(song, sp)

    if not tracks:
        return await interaction.followup.send(
            embed=_e_error("Nothing Found", f"No results for `{song[:200]}`."))

    # Handle Spotify-no-credentials sentinel
    if tracks[0].get("_error"):
        return await interaction.followup.send(
            embed=_e_error("Spotify Not Configured", tracks[0]["_error"]))

    # Attach metadata to every track
    for t in tracks:
        t["requester_mention"] = interaction.user.mention
        t["np_channel"]        = interaction.channel

    q = music_queues.setdefault(gid, [])

    if len(tracks) == 1:
        t = tracks[0]
        if vc.is_playing() or vc.is_paused():
            # Bot is already playing — add to queue
            q.append(t)
            pos = len(q)
            display = t["title"] if not t["title"].startswith("http") else song[:60]
            e = discord.Embed(
                title="➕  Added to Queue",
                description=f"**{display}**" + (f"\nby **{t['artist']}**" if t.get("artist") else ""),
                color=C_SPOTIFY)
            if t.get("album_art"):
                e.set_thumbnail(url=t["album_art"])
            e.add_field(name="Position",  value=f"#{pos}", inline=True)
            e.add_field(name="Duration",  value=_fmt_dur(t.get("duration")), inline=True)
            if t.get("spotify_url"):
                e.add_field(name="Spotify", value=f"[Open]({t['spotify_url']})", inline=True)
            e.set_footer(text="TSR Music")
            await interaction.followup.send(embed=e)
        else:
            # Nothing playing — send feedback immediately then start playback
            q.append(t)
            music_queues[gid] = q
            display = t["title"] if not t["title"].startswith("http") else "your track"
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"🎵  Loading **{display}**...",
                    color=C_SPOTIFY))
            # _play_next fetches the stream URL, posts the now-playing card, and starts FFmpeg
            await _play_next(interaction.guild, err_channel=interaction.channel)
    else:
        # Playlist / album — add all, start if idle
        q.extend(tracks)
        music_queues[gid] = q
        e = discord.Embed(
            title="📋  Playlist Added to Queue",
            description=f"Added **{len(tracks)} tracks** to the queue.",
            color=C_SPOTIFY)
        if tracks[0].get("album_art"):
            e.set_thumbnail(url=tracks[0]["album_art"])
        e.add_field(name="Queue length", value=str(len(q)), inline=True)
        if sp and "open.spotify.com" in song:
            e.add_field(name="Source", value=f"[Spotify]({song})", inline=True)
        e.set_footer(text="TSR Music  •  First track will play momentarily")
        await interaction.followup.send(embed=e)
        if not vc.is_playing() and not vc.is_paused():
            await _play_next(interaction.guild, err_channel=interaction.channel)

# ── /pause ────────────────────────────────────────────────────────────────

@bot.tree.command(name="pause", description="Pause the current track")
async def music_pause(interaction: discord.Interaction):
    gid = str(interaction.guild.id)
    vc  = music_vc.get(gid)
    if not vc or not vc.is_playing():
        return await interaction.response.send_message(
            embed=_e_error("Nothing Playing", "Nothing is currently playing."), ephemeral=True)
    vc.pause()
    await interaction.response.send_message(
        embed=discord.Embed(description="⏸️  Paused. Use `/resume` to continue.", color=C_SPOTIFY))

# ── /resume ───────────────────────────────────────────────────────────────

@bot.tree.command(name="resume", description="Resume the paused track")
async def music_resume(interaction: discord.Interaction):
    gid = str(interaction.guild.id)
    vc  = music_vc.get(gid)
    if not vc or not vc.is_paused():
        return await interaction.response.send_message(
            embed=_e_error("Not Paused", "Nothing is paused right now."), ephemeral=True)
    vc.resume()
    t   = music_playing.get(gid, {})
    e   = discord.Embed(
        description=f"▶️  Resumed **{t.get('title', 'track')}**.",
        color=C_SPOTIFY)
    await interaction.response.send_message(embed=e)

# ── /skip ─────────────────────────────────────────────────────────────────

@bot.tree.command(name="skip", description="Skip the current track (or skip N tracks)")
@app_commands.describe(count="How many tracks to skip (default 1)")
async def music_skip(interaction: discord.Interaction, count: int = 1):
    gid = str(interaction.guild.id)
    vc  = music_vc.get(gid)
    if not vc or (not vc.is_playing() and not vc.is_paused()):
        return await interaction.response.send_message(
            embed=_e_error("Nothing Playing", "Nothing to skip."), ephemeral=True)
    count = max(1, min(count, 20))
    # Skip additional tracks from queue if count > 1
    q = music_queues.get(gid, [])
    if count > 1:
        del q[:count - 1]
        music_queues[gid] = q
    t = music_playing.get(gid, {})
    vc.stop()  # triggers _after → _play_next
    e = discord.Embed(
        description=f"⏭️  Skipped **{t.get('title', 'track')}**" +
                    (f" and {count-1} more" if count > 1 else "") + ".",
        color=C_SPOTIFY)
    await interaction.response.send_message(embed=e)

# ── /stop ─────────────────────────────────────────────────────────────────

@bot.tree.command(name="stop", description="Stop playback and clear the queue")
async def music_stop(interaction: discord.Interaction):
    gid = str(interaction.guild.id)
    vc  = music_vc.get(gid)
    music_queues[gid]  = []
    music_playing[gid] = None
    music_loop[gid]    = False
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
    await interaction.response.send_message(
        embed=discord.Embed(description="⏹️  Stopped and queue cleared.", color=C_SPOTIFY))

# ── /nowplaying ───────────────────────────────────────────────────────────

@bot.tree.command(name="nowplaying", description="Show what's currently playing")
async def music_np(interaction: discord.Interaction):
    gid   = str(interaction.guild.id)
    track = music_playing.get(gid)
    vc    = music_vc.get(gid)
    if not track or not vc or not vc.is_playing():
        return await interaction.response.send_message(
            embed=_e_error("Nothing Playing", "Nothing is playing right now."), ephemeral=True)
    await interaction.response.defer()
    await _send_np(interaction.channel, track, gid)
    await interaction.followup.send(
        embed=discord.Embed(description="⬆️  Now playing info above.", color=C_SPOTIFY),
        ephemeral=True)

# ── /queue ────────────────────────────────────────────────────────────────

@bot.tree.command(name="queue", description="Show the current music queue")
async def music_queue(interaction: discord.Interaction):
    gid = str(interaction.guild.id)
    q   = music_queues.get(gid, [])
    cur = music_playing.get(gid)

    e = discord.Embed(title="📋  Music Queue", color=C_SPOTIFY)
    e.timestamp = now_utc()

    if cur:
        desc = f"▶️  **{cur['title']}**"
        if cur.get("artist"):
            desc += f" — {cur['artist']}"
        desc += f" `{_fmt_dur(cur.get('duration'))}`"
        if music_loop.get(gid):
            desc += " 🔁"
        e.add_field(name="Now Playing", value=desc, inline=False)
    else:
        e.add_field(name="Now Playing", value="*Nothing*", inline=False)

    if q:
        rows = []
        for i, t in enumerate(q[:15], 1):
            line = f"`{i}.` **{t['title']}**"
            if t.get("artist"):
                line += f" — {t['artist']}"
            line += f" `{_fmt_dur(t.get('duration'))}`"
            rows.append(line)
        if len(q) > 15:
            rows.append(f"*… and {len(q)-15} more tracks*")
        e.add_field(name=f"Up Next ({len(q)} tracks)", value="\n".join(rows), inline=False)
    else:
        e.add_field(name="Up Next", value="*Queue is empty*", inline=False)

    total_dur = sum(t.get("duration", 0) for t in q)
    e.set_footer(text=f"Total queue time: {_fmt_dur(total_dur)}  •  Volume: {int(music_volume.get(gid,1.0)*100)}%")
    await interaction.response.send_message(embed=e)

# ── /volume ───────────────────────────────────────────────────────────────

@bot.tree.command(name="volume", description="Set the playback volume (0–200%)")
@app_commands.describe(level="Volume level: 0 (mute) to 200 (max). Default is 100.")
async def music_volume_cmd(interaction: discord.Interaction, level: int):
    gid = str(interaction.guild.id)
    vc  = music_vc.get(gid)
    level = max(0, min(level, 200))
    vol   = level / 100.0
    music_volume[gid] = vol
    if vc and vc.source and hasattr(vc.source, "volume"):
        vc.source.volume = vol
    bar = "█" * (level // 10) + "░" * (20 - level // 10)
    e = discord.Embed(
        description=f"🔊  Volume set to **{level}%**\n`{bar}`",
        color=C_SPOTIFY)
    await interaction.response.send_message(embed=e)

# ── /loop ─────────────────────────────────────────────────────────────────

@bot.tree.command(name="loop", description="Toggle looping of the current track")
async def music_loop_cmd(interaction: discord.Interaction):
    gid  = str(interaction.guild.id)
    mode = not music_loop.get(gid, False)
    music_loop[gid] = mode
    e = discord.Embed(
        description=f"🔁  Loop is now **{'ON — current track will repeat' if mode else 'OFF'}**.",
        color=C_SPOTIFY)
    await interaction.response.send_message(embed=e)

# ── /shuffle ──────────────────────────────────────────────────────────────

@bot.tree.command(name="shuffle", description="Shuffle the queue")
async def music_shuffle(interaction: discord.Interaction):
    gid = str(interaction.guild.id)
    q   = music_queues.get(gid, [])
    if not q:
        return await interaction.response.send_message(
            embed=_e_error("Empty Queue", "There are no tracks to shuffle."), ephemeral=True)
    random.shuffle(q)
    music_queues[gid] = q
    e = discord.Embed(
        description=f"🔀  Shuffled **{len(q)} tracks** in the queue.",
        color=C_SPOTIFY)
    await interaction.response.send_message(embed=e)

# ── /disconnect ───────────────────────────────────────────────────────────

@bot.tree.command(name="disconnect", description="Disconnect the bot from voice and clear the queue")
async def music_disconnect(interaction: discord.Interaction):
    gid = str(interaction.guild.id)
    vc  = music_vc.get(gid)
    await _cancel_dc_task(gid)
    music_queues[gid]  = []
    music_playing[gid] = None
    music_loop[gid]    = False
    if vc and vc.is_connected():
        try:
            await vc.disconnect()
        except Exception:
            pass
    music_vc.pop(gid, None)
    await interaction.response.send_message(
        embed=discord.Embed(description="👋  Disconnected and queue cleared.", color=C_SPOTIFY))

# ── /search ───────────────────────────────────────────────────────────────

@bot.tree.command(name="search", description="Search for a song and pick from the top 5 results")
@app_commands.describe(query="Song name or artist to search for")
async def music_search(interaction: discord.Interaction, query: str):
    if not YT_DLP_OK:
        return await interaction.response.send_message(
            embed=_e_error("Not Ready", "yt-dlp is not installed."), ephemeral=True)
    await interaction.response.defer()

    def _fetch_multi(q):
        if not YT_DLP_OK:
            return []
        opts = dict(YDL_OPTS)
        opts["default_search"] = "ytsearch5"
        opts["noplaylist"] = False
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(q, download=False)
                return info.get("entries", [])[:5] if info else []
        except Exception:
            return []

    loop    = asyncio.get_event_loop()
    entries = await loop.run_in_executor(None, _fetch_multi, query)
    if not entries:
        return await interaction.followup.send(
            embed=_e_error("No Results", f"No YouTube results for `{query[:200]}`."))

    e = discord.Embed(
        title=f"🔍  Search results for: {query[:60]}",
        color=C_SPOTIFY)
    lines = []
    for i, ent in enumerate(entries, 1):
        dur  = _fmt_dur(ent.get("duration", 0))
        line = f"`{i}.` **[{ent.get('title','?')}]({ent.get('webpage_url','')})** `{dur}`"
        lines.append(line)
    e.description = "\n".join(lines)
    e.set_footer(text="Use /play with the song name or YouTube URL to play one of these.")
    await interaction.followup.send(embed=e)

# ═══════════════════════════════════════════════════════════════════════════
#  VOICE STATE — auto-rejoin music channel if bot is kicked
# ═══════════════════════════════════════════════════════════════════════════

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if member.id != bot.user.id:
        return
    # Bot was disconnected from a VC
    if before.channel and not after.channel:
        gid     = str(member.guild.id)
        cfg_vs  = gcfg(member.guild.id)
        mc_id   = cfg_vs.get("music_channel")
        rejoin  = cfg_vs.get("music_auto_rejoin", True)

        # Clear stale VC ref
        vc_old = music_vc.get(gid)
        if vc_old and not vc_old.is_connected():
            music_vc.pop(gid, None)

        # Auto-rejoin the locked channel if we were kicked from it
        if rejoin and mc_id and str(before.channel.id) == str(mc_id):
            await asyncio.sleep(3)   # brief pause before reconnect
            ch = member.guild.get_channel(int(mc_id))
            if ch:
                try:
                    vc_new = await ch.connect()
                    music_vc[gid] = vc_new
                except Exception:
                    pass

# ═══════════════════════════════════════════════════════════════════════════
#  NEW MOD + SETUP COMMANDS
# ═══════════════════════════════════════════════════════════════════════════

# ── /setupmusic ───────────────────────────────────────────────────────────

@bot.tree.command(name="setupmusic", description="Lock the bot to a voice channel and optionally enable auto-rejoin")
@app_commands.describe(
    channel="The voice channel the bot should always stay in",
    auto_rejoin="Automatically rejoin if someone kicks the bot (default: True)")
@app_commands.default_permissions(manage_guild=True)
async def setupmusic(interaction: discord.Interaction,
                     channel: discord.VoiceChannel,
                     auto_rejoin: bool = True):
    if not has_cmd_perm(interaction, "setupmusic"):
        return await interaction.response.send_message(
            embed=_e_error("No Permission", "You need **Manage Server** to run this."), ephemeral=True)
    cfg = gcfg(interaction.guild.id)
    cfg["music_channel"]     = channel.id
    cfg["music_auto_rejoin"] = auto_rejoin
    save_json("guild_config.json", guild_config)
    e = discord.Embed(
        title="🎵  Music Channel Set",
        description=(f"Bot will always join **{channel.mention}** when music is played.\n"
                     f"Auto-rejoin if kicked: **{'✅ On' if auto_rejoin else '❌ Off'}**\n\n"
                     f"Use `/play` normally — it will always come back to this channel.\n"
                     f"To clear the lock, run `/setupmusic` again with a different channel "
                     f"or contact your server owner."),
        color=C_SPOTIFY)
    e.set_footer(text="TSR Music Setup")
    await interaction.response.send_message(embed=e)
    await send_log(interaction.guild, _log_embed(
        "Music Channel Configured", C_SPOTIFY, icon="🎵",
        fields=[
            ("📢  Channel",    channel.mention,          True),
            ("🔄  Auto-Rejoin", "Yes" if auto_rejoin else "No", True),
            ("👤  Set by",     interaction.user.mention, True),
        ]
    ))

# ── /antiraid ─────────────────────────────────────────────────────────────

@bot.tree.command(name="antiraid", description="Configure automatic anti-raid protection for new accounts")
@app_commands.describe(
    enabled="Enable or disable anti-raid",
    min_age_days="Minimum account age in days to join (default 7)",
    action="Action when triggered: kick | ban | timeout",
    dm_user="DM the blocked user with a reason (default True)")
@app_commands.choices(action=[
    app_commands.Choice(name="kick",    value="kick"),
    app_commands.Choice(name="ban",     value="ban"),
    app_commands.Choice(name="timeout (24h)", value="timeout"),
])
@app_commands.default_permissions(manage_guild=True)
async def cmd_antiraid(interaction: discord.Interaction,
                       enabled: bool,
                       min_age_days: int = 7,
                       action: str = "kick",
                       dm_user: bool = True):
    if not has_cmd_perm(interaction, "antiraid"):
        return await interaction.response.send_message(
            embed=_e_error("No Permission", "Manage Server required."), ephemeral=True)
    cfg = gcfg(interaction.guild.id)
    cfg["antiraid_enabled"]      = enabled
    cfg["antiraid_min_age_days"] = max(1, min_age_days)
    cfg["antiraid_action"]       = action
    cfg["antiraid_dm"]           = dm_user
    save_json("guild_config.json", guild_config)
    colour = C_GREEN if enabled else C_RED
    e = discord.Embed(
        title=f"🛡️  Anti-Raid {'Enabled' if enabled else 'Disabled'}",
        colour=colour)
    if enabled:
        e.description = (f"Accounts younger than **{min_age_days} days** will be **{action}ed** on join.\n"
                         f"DM notification: **{'On' if dm_user else 'Off'}**")
    else:
        e.description = "Anti-Raid is now **disabled**. All accounts can join freely."
    e.set_footer(text="TSR Anti-Raid")
    await interaction.response.send_message(embed=e)
    await send_log(interaction.guild, _log_embed(
        f"🛡️  Anti-Raid {'Enabled' if enabled else 'Disabled'}", colour, icon="🛡️",
        fields=[
            ("Status",       "Enabled" if enabled else "Disabled", True),
            ("Min Age",      f"{min_age_days} day(s)",             True),
            ("Action",       action.title(),                        True),
            ("Set by",       interaction.user.mention,             True),
        ]
    ))

# ── /warnthreshold ────────────────────────────────────────────────────────

@bot.tree.command(name="warnthreshold", description="Set automatic actions when a user reaches a warn count")
@app_commands.describe(
    warn_count="Warn count that triggers the action (e.g. 3)",
    action="Action to take: timeout_1h | timeout_12h | timeout_24h | kick | ban",
    remove="Remove an existing threshold instead of adding")
@app_commands.choices(action=[
    app_commands.Choice(name="timeout 1 hour",   value="timeout_1h"),
    app_commands.Choice(name="timeout 12 hours", value="timeout_12h"),
    app_commands.Choice(name="timeout 24 hours", value="timeout_24h"),
    app_commands.Choice(name="kick",             value="kick"),
    app_commands.Choice(name="ban",              value="ban"),
])
@app_commands.default_permissions(manage_guild=True)
async def cmd_warnthreshold(interaction: discord.Interaction,
                             warn_count: int,
                             action: str = "kick",
                             remove: bool = False):
    if not has_cmd_perm(interaction, "warnthreshold"):
        return await interaction.response.send_message(
            embed=_e_error("No Permission", "Manage Server required."), ephemeral=True)
    cfg = gcfg(interaction.guild.id)
    thresholds: dict = cfg.setdefault("warn_thresholds", {})
    key = str(warn_count)
    if remove:
        thresholds.pop(key, None)
        save_json("guild_config.json", guild_config)
        return await interaction.response.send_message(
            embed=discord.Embed(
                description=f"✅  Removed threshold at **{warn_count} warns**.",
                color=C_GREEN))
    thresholds[key] = action
    save_json("guild_config.json", guild_config)

    # Build pretty summary
    lines = []
    for k in sorted(thresholds, key=lambda x: int(x)):
        lines.append(f"**{k} warns** → `{thresholds[k]}`")
    e = discord.Embed(
        title="⚠️  Warn Thresholds Updated",
        description="\n".join(lines) if lines else "*No thresholds set*",
        color=C_ORANGE)
    e.set_footer(text="These trigger automatically when /warn is used.")
    await interaction.response.send_message(embed=e)

# ── /modlogs ──────────────────────────────────────────────────────────────

@bot.tree.command(name="modlogs", description="View the full moderation history for a user")
@app_commands.describe(user="The user whose mod history you want to see", page="Page number (default 1)")
async def cmd_modlogs(interaction: discord.Interaction,
                      user: discord.User,
                      page: int = 1):
    if not has_cmd_perm(interaction, "modlogs"):
        return await interaction.response.send_message(
            embed=_e_error("No Permission", "You don't have permission to view mod logs."), ephemeral=True)
    gid    = str(interaction.guild.id)
    cases  = cases_db.get(gid, [])
    user_cases = [c for c in cases if str(c.get("user_id")) == str(user.id)]

    if not user_cases:
        return await interaction.response.send_message(
            embed=discord.Embed(
                title=f"📋  Mod Logs — {user}",
                description="✅  **No moderation actions** on record for this user.",
                color=C_GREEN))

    per_page = 8
    total_pages = max(1, math.ceil(len(user_cases) / per_page))
    page = max(1, min(page, total_pages))
    chunk = user_cases[-(page * per_page) : len(user_cases) - (page-1)*per_page]
    chunk.reverse()   # newest first

    e = discord.Embed(
        title=f"📋  Mod Logs — {user}",
        colour=C_ORANGE)
    e.set_thumbnail(url=user.display_avatar.url)

    lines = []
    for c in chunk:
        ts  = f"<t:{int(c.get('timestamp', 0))}:d>" if c.get("timestamp") else "?"
        mod = f"<@{c['mod_id']}>" if c.get("mod_id") else "System"
        reason = (c.get("reason") or "No reason")[:80]
        lines.append(
            f"`#{c.get('case_id','?')}` **{c.get('action','?').upper()}** — {ts} by {mod}\n"
            f"↳ {reason}")

    e.description = "\n\n".join(lines)
    warns_total = len([c for c in user_cases if c.get("action") == "warn"])
    e.set_footer(text=f"Page {page}/{total_pages}  •  {len(user_cases)} total actions  •  {warns_total} warns")
    await interaction.response.send_message(embed=e)

# ── /case ─────────────────────────────────────────────────────────────────

@bot.tree.command(name="case", description="Look up a specific moderation case by its case ID")
@app_commands.describe(case_id="The numeric case ID (shown in mod logs and action messages)")
async def cmd_case(interaction: discord.Interaction, case_id: int):
    if not has_cmd_perm(interaction, "case"):
        return await interaction.response.send_message(
            embed=_e_error("No Permission", "You need moderation permissions."), ephemeral=True)
    gid   = str(interaction.guild.id)
    cases = cases_db.get(gid, [])
    c     = next((x for x in cases if x.get("case_id") == case_id), None)
    if not c:
        return await interaction.response.send_message(
            embed=_e_error("Not Found", f"Case `#{case_id}` does not exist."), ephemeral=True)

    user_obj = await bot.fetch_user(int(c["user_id"])) if c.get("user_id") else None
    mod_obj  = await bot.fetch_user(int(c["mod_id"])) if c.get("mod_id") else None
    colour   = {"ban": C_RED, "kick": C_ORANGE, "warn": C_YELLOW,
                "timeout": C_ORANGE, "unban": C_GREEN}.get(c.get("action", ""), C_BLUE)
    e = discord.Embed(title=f"📋  Case #{case_id} — {c.get('action','?').upper()}", colour=colour)
    if user_obj:
        e.set_thumbnail(url=user_obj.display_avatar.url)
    e.add_field(name="👤  User",   value=f"{user_obj or c.get('user_id')}", inline=True)
    e.add_field(name="🔨  Mod",    value=f"{mod_obj or c.get('mod_id', 'System')}", inline=True)
    e.add_field(name="📅  Date",   value=f"<t:{int(c.get('timestamp',0))}:F>" if c.get("timestamp") else "?", inline=True)
    e.add_field(name="📝  Reason", value=c.get("reason") or "No reason provided", inline=False)
    if c.get("extra"):
        e.add_field(name="ℹ️  Extra", value=str(c["extra"])[:200], inline=False)
    e.set_footer(text=f"TSR Moderation  •  Total cases: {len(cases)}")
    await interaction.response.send_message(embed=e)

# ── /note ─────────────────────────────────────────────────────────────────

@bot.tree.command(name="note", description="Add, list, or remove a private staff note on a user")
@app_commands.describe(
    user="The user to attach a note to",
    action="add / list / remove",
    text="Note text (required for add)",
    index="Note number to remove (required for remove, see list first)")
@app_commands.choices(action=[
    app_commands.Choice(name="add",    value="add"),
    app_commands.Choice(name="list",   value="list"),
    app_commands.Choice(name="remove", value="remove"),
])
async def cmd_note(interaction: discord.Interaction,
                   user: discord.User,
                   action: str = "list",
                   text: str = "",
                   index: int = 0):
    if not has_cmd_perm(interaction, "note"):
        return await interaction.response.send_message(
            embed=_e_error("No Permission", "You need moderation permissions."), ephemeral=True)
    gid  = str(interaction.guild.id)
    uid  = str(user.id)
    notes: list = note_db.setdefault(gid, {}).setdefault(uid, [])

    if action == "add":
        if not text.strip():
            return await interaction.response.send_message(
                embed=_e_error("No Text", "Provide the note text with `text:`."), ephemeral=True)
        notes.append({
            "text":      text.strip(),
            "author_id": str(interaction.user.id),
            "author":    str(interaction.user),
            "ts":        int(now_utc().timestamp()),
        })
        save_json("note_db.json", note_db)
        return await interaction.response.send_message(
            embed=discord.Embed(
                description=f"📝  Note added for {user.mention} (note #{len(notes)}).",
                color=C_GREEN), ephemeral=True)

    if action == "remove":
        if index < 1 or index > len(notes):
            return await interaction.response.send_message(
                embed=_e_error("Invalid Index", f"Use `/note user:@ action:list` to see note numbers first."), ephemeral=True)
        removed = notes.pop(index - 1)
        save_json("note_db.json", note_db)
        return await interaction.response.send_message(
            embed=discord.Embed(
                description=f"🗑️  Removed note #{index}: *{removed['text'][:80]}*",
                color=C_ORANGE), ephemeral=True)

    # List
    if not notes:
        return await interaction.response.send_message(
            embed=discord.Embed(
                title=f"📝  Notes — {user}",
                description="No notes on this user.",
                color=C_GREEN), ephemeral=True)
    e = discord.Embed(title=f"📝  Notes — {user}", colour=C_YELLOW)
    e.set_thumbnail(url=user.display_avatar.url)
    lines = []
    for i, n in enumerate(notes, 1):
        ts  = f"<t:{n['ts']}:d>" if n.get("ts") else "?"
        lines.append(f"`{i}.` {n['text'][:120]}\n    — {n['author']} on {ts}")
    e.description = "\n\n".join(lines)
    e.set_footer(text=f"{len(notes)} note(s)  •  Staff only — not visible to users")
    await interaction.response.send_message(embed=e, ephemeral=True)


# ── /massban ──────────────────────────────────────────────────────────────

@bot.tree.command(name="massban", description="Ban multiple users by ID at once — separate IDs with spaces")
@app_commands.describe(
    user_ids="Space-separated list of user IDs to ban",
    reason="Reason to attach to all bans")
@app_commands.default_permissions(ban_members=True)
async def cmd_massban(interaction: discord.Interaction,
                      user_ids: str,
                      reason: str = "Mass ban"):
    if not has_cmd_perm(interaction, "massban"):
        return await interaction.response.send_message(
            embed=_e_error("No Permission", "You need **Ban Members** permission."), ephemeral=True)

    await interaction.response.defer()
    ids     = [x.strip() for x in user_ids.replace(",", " ").split() if x.strip().isdigit()]
    if not ids:
        return await interaction.followup.send(
            embed=_e_error("No Valid IDs", "Provide space-separated numeric user IDs."))

    gid      = str(interaction.guild.id)
    banned   = []
    failed   = []
    audit    = f"Massban by {interaction.user} — {reason}"
    for uid in ids[:100]:   # cap at 100 per invocation
        try:
            await interaction.guild.ban(discord.Object(int(uid)),
                                        reason=audit,
                                        delete_message_days=0)
            banned.append(uid)
            # Log case
            _add_case(gid, {
                "action":    "ban",
                "user_id":   uid,
                "mod_id":    str(interaction.user.id),
                "reason":    reason,
                "timestamp": int(now_utc().timestamp()),
                "extra":     "massban",
            })
        except Exception:
            failed.append(uid)

    lines = [f"✅  Banned **{len(banned)}** user(s)."]
    if failed:
        lines.append(f"❌  Failed on {len(failed)} ID(s): `{'`, `'.join(failed[:10])}`")
    e = discord.Embed(
        title="🔨  Mass Ban Complete",
        description="\n".join(lines),
        colour=C_RED if failed else C_GREEN)
    e.add_field(name="Reason", value=reason, inline=False)
    e.set_footer(text=f"Executed by {interaction.user}")
    await interaction.followup.send(embed=e)
    await send_log(interaction.guild, _log_embed(
        "🔨  Mass Ban", C_RED, icon="🔨",
        fields=[
            ("👤  Executor",  interaction.user.mention,    True),
            ("✅  Banned",    str(len(banned)),            True),
            ("❌  Failed",    str(len(failed)),            True),
            ("📝  Reason",   reason,                      False),
            ("🆔  IDs",      " ".join(banned[:20]) or "-", False),
        ]
    ))

# ── Helper: log a case to cases_db ───────────────────────────────────────

def _add_case(gid: str, data: dict) -> int:
    cases = cases_db.setdefault(gid, [])
    case_id = len(cases) + 1
    data["case_id"] = case_id
    cases.append(data)
    save_json("cases_db.json", cases_db)
    return case_id

# ── Patch existing /warn to auto-escalate and log cases ───────────────────
# (Intercept applied via on_warn_issued helper called from the warn command)

async def _apply_warn_escalation(interaction: discord.Interaction, member: discord.Member, total_warns: int):
    """Check warn thresholds and apply the configured escalation action."""
    cfg   = gcfg(interaction.guild.id)
    thr   = cfg.get("warn_thresholds", {})
    key   = str(total_warns)
    if key not in thr:
        return
    action = thr[key]
    reason = f"Auto-escalation: {total_warns} warns reached"
    e_desc = None

    try:
        if action == "kick":
            await member.kick(reason=reason)
            e_desc = f"Kicked after reaching {total_warns} warnings."
        elif action == "ban":
            await member.ban(reason=reason, delete_message_days=0)
            e_desc = f"Banned after reaching {total_warns} warnings."
        elif action == "timeout_1h":
            await member.timeout(datetime.timedelta(hours=1), reason=reason)
            e_desc = f"Timed out 1 hour after reaching {total_warns} warnings."
        elif action == "timeout_12h":
            await member.timeout(datetime.timedelta(hours=12), reason=reason)
            e_desc = f"Timed out 12 hours after reaching {total_warns} warnings."
        elif action == "timeout_24h":
            await member.timeout(datetime.timedelta(hours=24), reason=reason)
            e_desc = f"Timed out 24 hours after reaching {total_warns} warnings."
    except Exception:
        return

    if e_desc:
        try:
            await member.send(embed=discord.Embed(
                title=f"⚠️  Auto-Escalation — {interaction.guild.name}",
                description=e_desc,
                color=C_ORANGE))
        except Exception: pass
        await send_log(interaction.guild, _log_embed(
            "⚠️  Warn Threshold Reached", C_ORANGE, icon="⚠️",
            thumbnail=member.display_avatar.url,
            fields=[
                ("👤  User",      f"{member.mention} `{member.id}`", True),
                ("⚠️  Warns",     str(total_warns),                 True),
                ("⚡  Action",    action,                           True),
            ]
        ))

# ═══════════════════════════════════════════════════════════════════════════
#  GLOBAL ERROR HANDLER  — nothing silently fails
# ═══════════════════════════════════════════════════════════════════════════

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Catch-all so the user always gets a visible error instead of "Interaction failed"."""
    msg = None

    if isinstance(error, app_commands.MissingPermissions):
        msg = (_e_error("Missing Permissions",
                        "You don't have the Discord permission required to use this command.\n"
                        f"Required: `{'`, `'.join(error.missing_permissions)}`"))
    elif isinstance(error, app_commands.BotMissingPermissions):
        msg = (_e_error("Bot Missing Permissions",
                        f"I'm missing: `{'`, `'.join(error.missing_permissions)}`\n"
                        "Please give me the required permissions and try again."))
    elif isinstance(error, app_commands.CommandOnCooldown):
        msg = _e_error("Slow Down!", f"Try again in **{error.retry_after:.1f}s**.")
    elif isinstance(error, app_commands.NoPrivateMessage):
        msg = _e_error("Server Only", "This command can only be used in a server.")
    else:
        # Unwrap the original exception if wrapped
        orig = getattr(error, "original", error)
        if isinstance(orig, discord.Forbidden):
            msg = _e_error("Permission Denied",
                           "I don't have permission to do that. Check my role permissions.")
        elif isinstance(orig, discord.HTTPException):
            msg = _e_error("Discord Error", f"`{orig.status}` — {orig.text[:200]}")
        else:
            msg = _e_error("Unexpected Error", f"```{str(orig)[:500]}```")
            print(f"[ERROR] /{interaction.command.name if interaction.command else '?'}: {orig}")

    if msg:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=msg, ephemeral=True)
            else:
                await interaction.response.send_message(embed=msg, ephemeral=True)
        except Exception:
            pass

# ═══════════════════════════════════════════════════════════════════════════
#  RUN
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    async with bot:
        await bot.start(BOT_TOKEN)

asyncio.run(main())
