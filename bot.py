"""
╔══════════════════════════════════════════════════════════╗
║            TSR ADVANCED DISCORD BOT                      ║
║  Features: Hardban · Verify · SetupLock · Tickets       ║
║            AutoMod · Snipe · TempBan · Logging           ║
╚══════════════════════════════════════════════════════════╝

Railway Hosting: Set BOT_TOKEN as a Railway environment variable.
All guild configs are saved to data/ folder (JSON).
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import asyncio
import random
import re
import os
import json
import string
from typing import Optional

# ╔══════════════════════════════════════════════════════════╗
# ║                    CONFIGURATION                         ║
# ╚══════════════════════════════════════════════════════════╝

# ── Token from Railway environment variable ──────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set!")

# ── Owner IDs (add your Discord user ID) ────────────────────
OWNER_IDS_RAW = os.environ.get("OWNER_IDS", "")
OWNER_IDS = [int(x.strip()) for x in OWNER_IDS_RAW.split(",") if x.strip().isdigit()]

# ── Brand colours ─────────────────────────────────────────────
C_RED    = 0xED4245
C_ORANGE = 0xFEA832
C_YELLOW = 0xFEE75C
C_GREEN  = 0x57F287
C_BLUE   = 0x5865F2
C_PURPLE = 0x9B59B6
C_PINK   = 0xFF73FA
C_TEAL   = 0x1ABC9C

# ── Emoji map ─────────────────────────────────────────────────
E = {
    "ban":"🔨","unban":"🔓","kick":"👢","timeout":"⏱️","warn":"⚠️",
    "purge":"🗑️","lock":"🔒","unlock":"🔓","slow":"🐢","nick":"✏️",
    "role":"🎭","success":"✅","error":"❌","shield":"🛡️","star":"⭐",
    "wave":"👋","crown":"👑","chart":"📊","clock":"🕐","ping":"🏓",
    "bot":"🤖","server":"🏠","user":"👤","log":"📝","fire":"🔥",
    "diamond":"💎","link":"🔗","mail":"📨","ticket":"🎫","verify":"✔️",
    "hardban":"💀","softban":"🧹","tempban":"⏳","snipe":"👻",
    "automod":"⚡","filter":"🚫","voice":"🔊","edit":"📝",
}

# ╔══════════════════════════════════════════════════════════╗
# ║                    DATA PERSISTENCE                       ║
# ╚══════════════════════════════════════════════════════════╝

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

def data_path(filename: str) -> str:
    return os.path.join(DATA_DIR, filename)

def load_json(filename: str, default=None):
    path = data_path(filename)
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return default if default is not None else {}

def save_json(filename: str, data):
    with open(data_path(filename), "w") as f:
        json.dump(data, f, indent=2)

# In-memory databases (loaded from JSON on startup)
warnings_db:   dict = load_json("warnings.json")
guild_config:  dict = load_json("guild_config.json")
hardban_db:    dict = load_json("hardbans.json")
tempban_db:    dict = load_json("tempbans.json")
snipe_db:      dict = {}   # ephemeral only
editsnipe_db:  dict = {}   # ephemeral only
antispam_db:   dict = {}   # ephemeral only

ANTISPAM_LIMIT  = 5
ANTISPAM_WINDOW = 5

# ╔══════════════════════════════════════════════════════════╗
# ║                    GUILD CONFIG HELPERS                   ║
# ╚══════════════════════════════════════════════════════════╝

def gcfg(guild_id: int) -> dict:
    """Get guild config dict, creating default if missing."""
    gid = str(guild_id)
    if gid not in guild_config:
        guild_config[gid] = {
            "log_channel":         None,
            "welcome_channel":     None,
            "welcome_message":     "Welcome {user} to **{server}**! You are member #{count}.",
            "goodbye_channel":     None,
            "goodbye_message":     "**{user}** has left the server. Goodbye!",
            "verify_channel":      None,
            "verify_role":         None,
            "verify_method":       "button",   # button | reaction | code
            "verify_message":      "Click the button below to verify and gain access to the server!",
            "lock_exempt_roles":   [],          # role IDs exempt from lock
            "lock_deny_perm":      "send_messages",  # permission to deny on lock
            "automod_links":       False,
            "automod_caps":        False,
            "automod_caps_pct":    80,
            "automod_caps_min":    10,
            "automod_badwords":    [],
            "automod_exempt_roles":[],
            "ticket_channel":      None,
            "ticket_category":     None,
            "ticket_support_role": None,
            "ticket_message":      "Click the button below to open a support ticket.",
            "ticket_count":        0,
        }
        save_json("guild_config.json", guild_config)
    return guild_config[gid]

def save_cfg():
    save_json("guild_config.json", guild_config)

# ╔══════════════════════════════════════════════════════════╗
# ║                      BOT SETUP                           ║
# ╚══════════════════════════════════════════════════════════╝

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ╔══════════════════════════════════════════════════════════╗
# ║                   EMBED BUILDERS                         ║
# ╚══════════════════════════════════════════════════════════╝

def embed_success(title: str, description: str = None) -> discord.Embed:
    e = discord.Embed(title=f"{E['success']} {title}", description=description, color=C_GREEN)
    e.timestamp = datetime.datetime.utcnow()
    return e

def embed_error(title: str, description: str = None) -> discord.Embed:
    e = discord.Embed(title=f"{E['error']} {title}", description=description, color=C_RED)
    e.timestamp = datetime.datetime.utcnow()
    return e

def embed_info(title: str, description: str = None, color=C_BLUE) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=color)
    e.timestamp = datetime.datetime.utcnow()
    return e

def embed_mod(action: str, emoji: str, moderator, target, reason: str, color: int, extra: dict = None) -> discord.Embed:
    e = discord.Embed(title=f"{emoji} {action}", color=color, timestamp=datetime.datetime.utcnow())
    e.set_author(name=f"Moderation • {moderator.guild.name}",
                 icon_url=moderator.guild.icon.url if moderator.guild.icon else None)
    e.set_thumbnail(url=target.display_avatar.url if hasattr(target, 'display_avatar') else None)
    e.add_field(name="👤 Target",    value=f"{target.mention if hasattr(target, 'mention') else target}\n`{target} • {target.id}`", inline=True)
    e.add_field(name="🛡️ Moderator", value=f"{moderator.mention}\n`{moderator}`", inline=True)
    e.add_field(name="📝 Reason",    value=f"```{reason or 'No reason provided'}```", inline=False)
    if extra:
        for k, v in extra.items():
            e.add_field(name=k, value=v, inline=True)
    e.set_footer(text="TSR Moderation System")
    return e

async def send_log(guild: discord.Guild, embed: discord.Embed):
    cfg = gcfg(guild.id)
    ch_id = cfg.get("log_channel")
    ch = guild.get_channel(int(ch_id)) if ch_id else None
    if ch:
        await ch.send(embed=embed)

async def dm_member(member: discord.Member, embed: discord.Embed):
    try:
        await member.send(embed=embed)
    except Exception:
        pass

def no_perm(action: str) -> discord.Embed:
    return embed_error("Missing Permissions", f"You need **{action}** permission.")

def role_too_high() -> discord.Embed:
    return embed_error("Role Hierarchy", "You cannot moderate someone with an equal or higher role.")

# ╔══════════════════════════════════════════════════════════╗
# ║                       HELPERS                            ║
# ╚══════════════════════════════════════════════════════════╝

def warn_user(guild_id: str, user_id: str, reason: str, mod_name: str) -> int:
    warnings_db.setdefault(guild_id, {}).setdefault(user_id, [])
    warnings_db[guild_id][user_id].append({
        "reason":    reason,
        "moderator": mod_name,
        "time":      datetime.datetime.utcnow().strftime("%b %d, %Y %H:%M UTC")
    })
    save_json("warnings.json", warnings_db)
    return len(warnings_db[guild_id][user_id])

def parse_duration(s: str) -> Optional[datetime.timedelta]:
    m = re.match(r"^(\d+)([smhd])$", s.lower())
    if not m:
        return None
    v, u = int(m.group(1)), m.group(2)
    return {"s": datetime.timedelta(seconds=v), "m": datetime.timedelta(minutes=v),
            "h": datetime.timedelta(hours=v),   "d": datetime.timedelta(days=v)}.get(u)

def duration_str(td: datetime.timedelta) -> str:
    total = int(td.total_seconds())
    d, r  = divmod(total, 86400)
    h, r  = divmod(r, 3600)
    m, s  = divmod(r, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s: parts.append(f"{s}s")
    return " ".join(parts) or "0s"

def is_automod_exempt(member: discord.Member) -> bool:
    cfg = gcfg(member.guild.id)
    exempt = cfg.get("automod_exempt_roles", [])
    if member.guild_permissions.manage_messages:
        return True
    return any(str(r.id) in exempt for r in member.roles)

# ╔══════════════════════════════════════════════════════════╗
# ║                        EVENTS                            ║
# ╚══════════════════════════════════════════════════════════╝

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"\n{'═'*50}\n  {E['bot']} Online: {bot.user}\n  Servers: {len(bot.guilds)}\n{'═'*50}\n")
    status_rotation.start()
    check_tempbans.start()

@tasks.loop(seconds=30)
async def status_rotation():
    statuses = [
        discord.Activity(type=discord.ActivityType.watching,  name=f"{sum(g.member_count for g in bot.guilds):,} members"),
        discord.Activity(type=discord.ActivityType.watching,  name=f"{len(bot.guilds)} servers"),
        discord.Activity(type=discord.ActivityType.playing,   name="Use /help"),
        discord.Activity(type=discord.ActivityType.listening, name="slash commands"),
        discord.Activity(type=discord.ActivityType.watching,  name="over the server"),
    ]
    await bot.change_presence(activity=random.choice(statuses))

@tasks.loop(seconds=60)
async def check_tempbans():
    now = datetime.datetime.utcnow().timestamp()
    to_remove = []
    for gid, bans in tempban_db.items():
        for uid, data in list(bans.items()):
            if now >= data["expires"]:
                guild = bot.get_guild(int(gid))
                if guild:
                    try:
                        user = await bot.fetch_user(int(uid))
                        await guild.unban(user, reason="Temporary ban expired")
                        log_e = embed_info(f"{E['unban']} TempBan Expired",
                                           f"**{user}** (`{user.id}`) has been automatically unbanned.", color=C_GREEN)
                        await send_log(guild, log_e)
                    except Exception:
                        pass
                to_remove.append((gid, uid))
    for gid, uid in to_remove:
        tempban_db.get(gid, {}).pop(uid, None)
    if to_remove:
        save_json("tempbans.json", tempban_db)

@bot.event
async def on_member_join(member: discord.Member):
    # ── Hardban check ───────────────────────────────────────
    gid = str(member.guild.id)
    uid = str(member.id)
    hb  = hardban_db.get(gid, {}).get(uid)
    if hb:
        try:
            dm_e = discord.Embed(title=f"⛔ You are hardbanned from {member.guild.name}",
                                  description=f"**Reason:** {hb.get('reason','No reason')}", color=C_RED)
            await member.send(embed=dm_e)
        except Exception:
            pass
        await member.ban(reason=f"Hardban: {hb.get('reason','')}", delete_message_days=0)
        return

    # ── Welcome message ──────────────────────────────────────
    cfg = gcfg(member.guild.id)
    ch_id = cfg.get("welcome_channel")
    if ch_id:
        ch = member.guild.get_channel(int(ch_id))
        if ch:
            msg = cfg.get("welcome_message", "Welcome {user}!")
            msg = msg.replace("{user}", member.mention)\
                     .replace("{username}", str(member))\
                     .replace("{server}", member.guild.name)\
                     .replace("{count}", str(member.guild.member_count))
            e = discord.Embed(description=msg, color=C_BLUE)
            e.set_author(name=f"Welcome to {member.guild.name}!", icon_url=member.guild.icon.url if member.guild.icon else None)
            e.set_thumbnail(url=member.display_avatar.url)
            e.set_footer(text=f"Account created {member.created_at.strftime('%b %d, %Y')}")
            e.timestamp = datetime.datetime.utcnow()
            await ch.send(embed=e)

@bot.event
async def on_member_remove(member: discord.Member):
    cfg = gcfg(member.guild.id)
    ch_id = cfg.get("goodbye_channel")
    if ch_id:
        ch = member.guild.get_channel(int(ch_id))
        if ch:
            msg = cfg.get("goodbye_message", "**{user}** has left the server.")
            msg = msg.replace("{user}", str(member))\
                     .replace("{username}", str(member))\
                     .replace("{server}", member.guild.name)
            e = embed_info("👋 Member Left", msg, color=C_ORANGE)
            e.set_thumbnail(url=member.display_avatar.url)
            await ch.send(embed=e)

@bot.event
async def on_message_delete(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    gid = str(message.guild.id)
    snipe_db[gid] = {
        "content":   message.content,
        "author":    str(message.author),
        "author_id": message.author.id,
        "avatar":    str(message.author.display_avatar.url),
        "channel":   message.channel.id,
        "time":      datetime.datetime.utcnow().timestamp()
    }
    # message delete log
    cfg = gcfg(message.guild.id)
    ch_id = cfg.get("log_channel")
    if ch_id:
        ch = message.guild.get_channel(int(ch_id))
        if ch and message.content:
            e = embed_info(f"{E['edit']} Message Deleted",
                           f"**Author:** {message.author.mention} (`{message.author}`)\n"
                           f"**Channel:** {message.channel.mention}\n"
                           f"**Content:**\n```{message.content[:1000]}```", color=C_ORANGE)
            await ch.send(embed=e)

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if before.author.bot or not before.guild or before.content == after.content:
        return
    gid = str(before.guild.id)
    editsnipe_db[gid] = {
        "before":    before.content,
        "after":     after.content,
        "author":    str(before.author),
        "author_id": before.author.id,
        "avatar":    str(before.author.display_avatar.url),
        "channel":   before.channel.id,
        "time":      datetime.datetime.utcnow().timestamp(),
        "jump_url":  after.jump_url,
    }
    cfg = gcfg(before.guild.id)
    ch_id = cfg.get("log_channel")
    if ch_id:
        ch = before.guild.get_channel(int(ch_id))
        if ch:
            e = embed_info(f"{E['edit']} Message Edited",
                           f"**Author:** {before.author.mention}\n**Channel:** {before.channel.mention}\n"
                           f"[Jump to message]({after.jump_url})", color=C_YELLOW)
            e.add_field(name="Before", value=f"```{before.content[:500] or '(empty)'}```", inline=False)
            e.add_field(name="After",  value=f"```{after.content[:500] or '(empty)'}```",  inline=False)
            await ch.send(embed=e)

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    cfg = gcfg(member.guild.id)
    ch_id = cfg.get("log_channel")
    if not ch_id:
        return
    ch = member.guild.get_channel(int(ch_id))
    if not ch:
        return
    if before.channel is None and after.channel is not None:
        e = embed_info(f"{E['voice']} Voice Join", f"{member.mention} joined **{after.channel.name}**", color=C_GREEN)
    elif before.channel is not None and after.channel is None:
        e = embed_info(f"{E['voice']} Voice Leave", f"{member.mention} left **{before.channel.name}**", color=C_ORANGE)
    elif before.channel != after.channel:
        e = embed_info(f"{E['voice']} Voice Move",
                       f"{member.mention} moved from **{before.channel.name}** → **{after.channel.name}**", color=C_YELLOW)
    else:
        return
    await ch.send(embed=e)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return

    guild_id = str(message.guild.id)
    user_id  = str(message.author.id)
    now      = datetime.datetime.utcnow().timestamp()
    cfg      = gcfg(message.guild.id)

    # ── Anti-spam ────────────────────────────────────────────
    antispam_db.setdefault(guild_id, {}).setdefault(user_id, [])
    antispam_db[guild_id][user_id] = [t for t in antispam_db[guild_id][user_id] if now - t < ANTISPAM_WINDOW]
    antispam_db[guild_id][user_id].append(now)
    if len(antispam_db[guild_id][user_id]) >= ANTISPAM_LIMIT:
        if not is_automod_exempt(message.author):
            antispam_db[guild_id][user_id] = []
            try:
                await message.channel.purge(limit=ANTISPAM_LIMIT, check=lambda m: m.author == message.author)
            except Exception:
                pass
            try:
                await message.author.timeout(datetime.timedelta(minutes=5), reason="AutoMod: Spam")
            except Exception:
                pass
            warn_user(guild_id, user_id, "AutoMod: Spamming", "AutoMod")
            e = embed_error("⚡ Anti-Spam", f"{message.author.mention} was timed out 5 min for spamming.")
            e.set_footer(text="AutoMod System")
            await message.channel.send(embed=e, delete_after=8)
            await send_log(message.guild, embed_mod("AutoMod: Spam", "⚡", message.guild.me, message.author, "Spamming", C_ORANGE))
            await bot.process_commands(message)
            return

    if not is_automod_exempt(message.author):
        # ── Anti-links ───────────────────────────────────────
        if cfg.get("automod_links") and re.search(r"(https?://|discord\.gg/|www\.)", message.content, re.I):
            try:
                await message.delete()
            except Exception:
                pass
            await message.channel.send(embed=embed_error("🚫 Links Blocked", f"{message.author.mention}, links are not allowed here."), delete_after=6)
            await bot.process_commands(message)
            return

        # ── Anti-caps ────────────────────────────────────────
        if cfg.get("automod_caps"):
            content = message.content
            if len(content) >= cfg.get("automod_caps_min", 10):
                caps_count = sum(1 for c in content if c.isupper())
                total_alpha = sum(1 for c in content if c.isalpha())
                if total_alpha > 0 and (caps_count / total_alpha * 100) >= cfg.get("automod_caps_pct", 80):
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    await message.channel.send(embed=embed_error("🚫 Caps Filter", f"{message.author.mention}, please avoid excessive caps."), delete_after=6)
                    await bot.process_commands(message)
                    return

        # ── Bad words filter ─────────────────────────────────
        bad_words = cfg.get("automod_badwords", [])
        if bad_words:
            content_lower = message.content.lower()
            for word in bad_words:
                if word.lower() in content_lower:
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    await message.channel.send(embed=embed_error("🚫 Filtered Word", f"{message.author.mention}, that word is not allowed here."), delete_after=6)
                    warn_user(guild_id, user_id, f"AutoMod: Filtered word", "AutoMod")
                    await bot.process_commands(message)
                    return

    await bot.process_commands(message)

# ╔══════════════════════════════════════════════════════════╗
# ║              SETUP COMMANDS (ADMIN)                      ║
# ╚══════════════════════════════════════════════════════════╝

# ── /setuplog ────────────────────────────────────────────────
@bot.tree.command(name="setuplog", description="Set the moderation log channel")
@app_commands.describe(channel="The channel to send logs to")
@app_commands.default_permissions(administrator=True)
async def setuplog(interaction: discord.Interaction, channel: discord.TextChannel):
    cfg = gcfg(interaction.guild.id)
    cfg["log_channel"] = str(channel.id)
    save_cfg()
    await interaction.response.send_message(
        embed=embed_success("Log Channel Set", f"All mod logs will be sent to {channel.mention}."))

# ── /setupwelcome ────────────────────────────────────────────
@bot.tree.command(name="setupwelcome", description="Configure the welcome message")
@app_commands.describe(
    channel="Welcome channel",
    message="Message (use {user} {username} {server} {count})"
)
@app_commands.default_permissions(administrator=True)
async def setupwelcome(interaction: discord.Interaction, channel: discord.TextChannel, message: str = None):
    cfg = gcfg(interaction.guild.id)
    cfg["welcome_channel"] = str(channel.id)
    if message:
        cfg["welcome_message"] = message
    save_cfg()
    e = embed_success("Welcome Configured", f"Welcome messages will be sent to {channel.mention}.")
    e.add_field(name="Message Template", value=cfg["welcome_message"], inline=False)
    e.add_field(name="Variables", value="`{user}` `{username}` `{server}` `{count}`", inline=False)
    await interaction.response.send_message(embed=e)

# ── /setupgoodbye ────────────────────────────────────────────
@bot.tree.command(name="setupgoodbye", description="Configure the goodbye message")
@app_commands.describe(channel="Goodbye channel", message="Message (use {user} {username} {server})")
@app_commands.default_permissions(administrator=True)
async def setupgoodbye(interaction: discord.Interaction, channel: discord.TextChannel, message: str = None):
    cfg = gcfg(interaction.guild.id)
    cfg["goodbye_channel"] = str(channel.id)
    if message:
        cfg["goodbye_message"] = message
    save_cfg()
    e = embed_success("Goodbye Configured", f"Goodbye messages will be sent to {channel.mention}.")
    e.add_field(name="Message Template", value=cfg["goodbye_message"], inline=False)
    await interaction.response.send_message(embed=e)

# ── /setuplock ───────────────────────────────────────────────
@bot.tree.command(name="setuplock", description="Configure what /lock and /unlock affect")
@app_commands.describe(
    exempt_role="Role that stays exempt from locks (can be used multiple times; use 'clear' name to reset)",
    permission="Permission to deny on lock: send_messages | add_reactions | use_slash_commands | all"
)
@app_commands.default_permissions(administrator=True)
async def setuplock(interaction: discord.Interaction,
                    exempt_role: discord.Role = None,
                    permission: str = "send_messages"):
    cfg = gcfg(interaction.guild.id)
    valid_perms = ["send_messages", "add_reactions", "use_application_commands", "all"]
    if permission not in valid_perms:
        return await interaction.response.send_message(
            embed=embed_error("Invalid Permission", f"Choose from: `{'`, `'.join(valid_perms)}`"), ephemeral=True)

    if exempt_role:
        rid = str(exempt_role.id)
        if rid in cfg["lock_exempt_roles"]:
            cfg["lock_exempt_roles"].remove(rid)
            action = f"Removed {exempt_role.mention} from exempt roles."
        else:
            cfg["lock_exempt_roles"].append(rid)
            action = f"Added {exempt_role.mention} as exempt from locks."
    else:
        action = "No role changed."

    cfg["lock_deny_perm"] = permission
    save_cfg()

    exempt_roles = [interaction.guild.get_role(int(r)) for r in cfg["lock_exempt_roles"] if interaction.guild.get_role(int(r))]
    e = embed_success("Lock Setup Updated", action)
    e.add_field(name="Locked Permission",
                value=f"`{cfg['lock_deny_perm']}` (denied for @everyone on lock)", inline=False)
    e.add_field(name="Exempt Roles",
                value=" ".join(r.mention for r in exempt_roles) or "@everyone (none exempt)", inline=False)
    e.add_field(name="Tip", value="Run `/setuplock` again with a role to toggle it on/off the exempt list.", inline=False)
    await interaction.response.send_message(embed=e)

# ── /setupverify ─────────────────────────────────────────────
class VerifyButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify Me", style=discord.ButtonStyle.success, emoji="✔️", custom_id="verify_button")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = gcfg(interaction.guild.id)
        role_id = cfg.get("verify_role")
        if not role_id:
            return await interaction.response.send_message(embed=embed_error("Not Configured", "Verify role not set."), ephemeral=True)
        role = interaction.guild.get_role(int(role_id))
        if not role:
            return await interaction.response.send_message(embed=embed_error("Role Missing", "Verify role not found."), ephemeral=True)
        if role in interaction.user.roles:
            return await interaction.response.send_message(embed=embed_info("Already Verified", "You are already verified!"), ephemeral=True)
        await interaction.user.add_roles(role, reason="Self-verification")
        await interaction.response.send_message(
            embed=embed_success("Verified!", f"Welcome! You've been given the **{role.name}** role."), ephemeral=True)
        await send_log(interaction.guild, embed_info(
            f"{E['verify']} Member Verified",
            f"{interaction.user.mention} (`{interaction.user}`) verified.", color=C_GREEN))

@bot.tree.command(name="setupverify", description="Set up the verification system (like Carl-bot)")
@app_commands.describe(
    channel="Channel to send the verify message in",
    role="Role to give upon verification",
    method="Verification method: button | reaction | code",
    message="Custom verification message"
)
@app_commands.default_permissions(administrator=True)
async def setupverify(interaction: discord.Interaction,
                       channel: discord.TextChannel,
                       role: discord.Role,
                       method: str = "button",
                       message: str = None):
    if method not in ("button", "reaction", "code"):
        return await interaction.response.send_message(
            embed=embed_error("Invalid Method", "Choose: `button`, `reaction`, or `code`"), ephemeral=True)

    cfg = gcfg(interaction.guild.id)
    cfg["verify_channel"] = str(channel.id)
    cfg["verify_role"]    = str(role.id)
    cfg["verify_method"]  = method
    if message:
        cfg["verify_message"] = message
    save_cfg()

    verify_msg = cfg["verify_message"]
    e = discord.Embed(title=f"{E['shield']} Verification Required",
                      description=verify_msg, color=C_BLUE)
    e.set_footer(text=f"{interaction.guild.name} • Verification System")

    if method == "button":
        await channel.send(embed=e, view=VerifyButton())
    elif method == "reaction":
        sent = await channel.send(embed=e)
        await sent.add_reaction("✅")
        cfg["verify_message_id"] = str(sent.id)
        save_cfg()
    elif method == "code":
        e.description = verify_msg + "\n\n> Run `/verify <code>` — a code will be sent to your DMs."
        await channel.send(embed=e)

    await interaction.response.send_message(
        embed=embed_success("Verification Set Up",
                            f"Verify channel: {channel.mention}\nRole: {role.mention}\nMethod: `{method}`"))

# ── Reaction-based verify ────────────────────────────────────
@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    cfg = gcfg(guild.id)
    if cfg.get("verify_method") != "reaction":
        return
    if str(payload.message_id) != cfg.get("verify_message_id"):
        return
    if str(payload.emoji) != "✅":
        return
    role_id = cfg.get("verify_role")
    if not role_id:
        return
    role   = guild.get_role(int(role_id))
    member = guild.get_member(payload.user_id)
    if role and member and role not in member.roles:
        await member.add_roles(role, reason="Reaction verification")
        await send_log(guild, embed_info(f"{E['verify']} Member Verified",
                                         f"{member.mention} verified via reaction.", color=C_GREEN))

# ── Code-based verify ────────────────────────────────────────
pending_codes: dict = {}   # {user_id: code}

@bot.tree.command(name="getcode", description="Get a verification code sent to your DMs")
async def getcode(interaction: discord.Interaction):
    cfg = gcfg(interaction.guild.id)
    if cfg.get("verify_method") != "code":
        return await interaction.response.send_message(embed=embed_error("Not Enabled", "Code verification is not the active method."), ephemeral=True)
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    pending_codes[interaction.user.id] = code
    try:
        dm_e = discord.Embed(title="🔑 Your Verification Code",
                              description=f"Your code for **{interaction.guild.name}**:\n\n## `{code}`\n\nUse `/verify {code}` in the server.",
                              color=C_BLUE)
        await interaction.user.send(embed=dm_e)
        await interaction.response.send_message(embed=embed_success("Code Sent", "Check your DMs for the verification code."), ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(embed=embed_error("DMs Closed", "Please enable DMs from server members first."), ephemeral=True)

@bot.tree.command(name="verify", description="Enter your verification code")
@app_commands.describe(code="The 6-character code from your DMs")
async def verify_code(interaction: discord.Interaction, code: str):
    cfg = gcfg(interaction.guild.id)
    if cfg.get("verify_method") != "code":
        return await interaction.response.send_message(embed=embed_error("Not Enabled", "Code verification is not active."), ephemeral=True)
    expected = pending_codes.get(interaction.user.id)
    if not expected or code.upper() != expected:
        return await interaction.response.send_message(embed=embed_error("Invalid Code", "Incorrect code. Use `/getcode` to get a new one."), ephemeral=True)
    role_id = cfg.get("verify_role")
    role    = interaction.guild.get_role(int(role_id)) if role_id else None
    if not role:
        return await interaction.response.send_message(embed=embed_error("Role Missing", "Verify role not configured."), ephemeral=True)
    del pending_codes[interaction.user.id]
    await interaction.user.add_roles(role, reason="Code verification")
    await interaction.response.send_message(embed=embed_success("Verified!", f"You've been given the **{role.name}** role."), ephemeral=True)
    await send_log(interaction.guild, embed_info(f"{E['verify']} Member Verified",
                                                  f"{interaction.user.mention} verified via code.", color=C_GREEN))

# ── /setuptickets ────────────────────────────────────────────
class TicketButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="ticket_open")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = gcfg(interaction.guild.id)
        cat_id = cfg.get("ticket_category")
        cat    = interaction.guild.get_channel(int(cat_id)) if cat_id else None

        # Check if user already has an open ticket
        existing = discord.utils.get(interaction.guild.text_channels, name=f"ticket-{interaction.user.name.lower()}")
        if existing:
            return await interaction.response.send_message(
                embed=embed_error("Ticket Exists", f"You already have an open ticket: {existing.mention}"), ephemeral=True)

        cfg["ticket_count"] = cfg.get("ticket_count", 0) + 1
        save_cfg()
        ticket_num = cfg["ticket_count"]

        # Build overwrites
        support_role_id = cfg.get("ticket_support_role")
        support_role    = interaction.guild.get_role(int(support_role_id)) if support_role_id else None
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user:               discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            interaction.guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        try:
            channel = await interaction.guild.create_text_channel(
                name=f"ticket-{ticket_num:04d}",
                category=cat,
                overwrites=overwrites,
                reason=f"Ticket by {interaction.user}"
            )
        except Exception as ex:
            return await interaction.response.send_message(embed=embed_error("Failed", str(ex)), ephemeral=True)

        e = discord.Embed(title=f"🎫 Ticket #{ticket_num:04d}",
                          description=f"Hello {interaction.user.mention}!\n\nDescribe your issue and our staff will assist you shortly.\n\nTo close this ticket, click the button below.",
                          color=C_BLUE)
        e.set_footer(text=f"Opened by {interaction.user}")
        e.timestamp = datetime.datetime.utcnow()
        await channel.send(
            content=f"{interaction.user.mention}" + (f" {support_role.mention}" if support_role else ""),
            embed=e,
            view=TicketCloseButton()
        )
        await interaction.response.send_message(
            embed=embed_success("Ticket Opened", f"Your ticket has been created: {channel.mention}"), ephemeral=True)

class TicketCloseButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket_close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message(embed=no_perm("Manage Channels"), ephemeral=True)
        await interaction.response.send_message(embed=embed_info("Closing...", "This ticket will be deleted in 5 seconds."))
        await asyncio.sleep(5)
        await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")

@bot.tree.command(name="setuptickets", description="Set up the ticket system")
@app_commands.describe(channel="Channel to send ticket panel in", category="Category for ticket channels",
                        support_role="Role that can see tickets", message="Ticket panel message")
@app_commands.default_permissions(administrator=True)
async def setuptickets(interaction: discord.Interaction,
                        channel: discord.TextChannel,
                        category: discord.CategoryChannel = None,
                        support_role: discord.Role = None,
                        message: str = None):
    cfg = gcfg(interaction.guild.id)
    cfg["ticket_channel"]      = str(channel.id)
    cfg["ticket_category"]     = str(category.id) if category else None
    cfg["ticket_support_role"] = str(support_role.id) if support_role else None
    if message:
        cfg["ticket_message"] = message
    save_cfg()

    e = discord.Embed(title="🎫 Support Tickets",
                      description=cfg["ticket_message"], color=C_BLUE)
    e.set_footer(text=interaction.guild.name)
    await channel.send(embed=e, view=TicketButton())
    await interaction.response.send_message(embed=embed_success("Tickets Set Up", f"Ticket panel sent to {channel.mention}."))

# ── /setupautomod ─────────────────────────────────────────────
@bot.tree.command(name="setupautomod", description="Configure AutoMod filters")
@app_commands.describe(
    links="Block links for non-mods (true/false)",
    caps="Block excessive caps (true/false)",
    caps_percent="Caps % threshold (default 80)",
    caps_min_length="Minimum message length to check caps (default 10)",
    exempt_role="Role exempt from all automod filters (toggles on/off)"
)
@app_commands.default_permissions(administrator=True)
async def setupautomod(interaction: discord.Interaction,
                        links: bool = None,
                        caps: bool = None,
                        caps_percent: int = None,
                        caps_min_length: int = None,
                        exempt_role: discord.Role = None):
    cfg = gcfg(interaction.guild.id)
    changes = []
    if links is not None:
        cfg["automod_links"] = links
        changes.append(f"Anti-Links: `{'ON' if links else 'OFF'}`")
    if caps is not None:
        cfg["automod_caps"] = caps
        changes.append(f"Anti-Caps: `{'ON' if caps else 'OFF'}`")
    if caps_percent is not None:
        cfg["automod_caps_pct"] = caps_percent
        changes.append(f"Caps Threshold: `{caps_percent}%`")
    if caps_min_length is not None:
        cfg["automod_caps_min"] = caps_min_length
        changes.append(f"Caps Min Length: `{caps_min_length}`")
    if exempt_role:
        rid = str(exempt_role.id)
        if rid in cfg["automod_exempt_roles"]:
            cfg["automod_exempt_roles"].remove(rid)
            changes.append(f"Removed exempt role: {exempt_role.mention}")
        else:
            cfg["automod_exempt_roles"].append(rid)
            changes.append(f"Added exempt role: {exempt_role.mention}")
    save_cfg()

    e = embed_success("AutoMod Updated", "\n".join(changes) if changes else "No changes made.")
    e.add_field(name="Current Settings",
                value=(f"Anti-Links: `{'ON' if cfg['automod_links'] else 'OFF'}`\n"
                       f"Anti-Caps: `{'ON' if cfg['automod_caps'] else 'OFF'}` ({cfg['automod_caps_pct']}% / min {cfg['automod_caps_min']} chars)\n"
                       f"Bad Words: `{len(cfg['automod_badwords'])} words`\n"
                       f"Exempt Roles: {len(cfg['automod_exempt_roles'])}"), inline=False)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="badword", description="Add or remove a word from the filter list")
@app_commands.describe(word="Word to add/remove", action="add or remove")
@app_commands.default_permissions(administrator=True)
async def badword(interaction: discord.Interaction, word: str, action: str = "add"):
    cfg = gcfg(interaction.guild.id)
    word = word.lower()
    if action == "add":
        if word not in cfg["automod_badwords"]:
            cfg["automod_badwords"].append(word)
            save_cfg()
        await interaction.response.send_message(embed=embed_success("Word Added", f"`{word}` added to filter."), ephemeral=True)
    elif action == "remove":
        if word in cfg["automod_badwords"]:
            cfg["automod_badwords"].remove(word)
            save_cfg()
        await interaction.response.send_message(embed=embed_success("Word Removed", f"`{word}` removed from filter."), ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed_error("Invalid Action", "Use `add` or `remove`."), ephemeral=True)

@bot.tree.command(name="filterlist", description="View all filtered words")
@app_commands.default_permissions(administrator=True)
async def filterlist(interaction: discord.Interaction):
    cfg = gcfg(interaction.guild.id)
    words = cfg.get("automod_badwords", [])
    if not words:
        return await interaction.response.send_message(embed=embed_info("Filter List", "No words in the filter."), ephemeral=True)
    await interaction.response.send_message(
        embed=embed_info("🚫 Filter List", "```" + ", ".join(words) + "```"), ephemeral=True)

# ╔══════════════════════════════════════════════════════════╗
# ║                  MODERATION COMMANDS                     ║
# ╚══════════════════════════════════════════════════════════╝

@bot.tree.command(name="ban", description="Ban a member from the server")
@app_commands.describe(member="Member to ban", reason="Reason", delete_days="Days of messages to delete (0-7)")
@app_commands.default_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = None, delete_days: int = 1):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message(embed=no_perm("Ban Members"), ephemeral=True)
    if member.top_role >= interaction.user.top_role and interaction.user.id not in OWNER_IDS:
        return await interaction.response.send_message(embed=role_too_high(), ephemeral=True)
    if member == interaction.user:
        return await interaction.response.send_message(embed=embed_error("Invalid", "You cannot ban yourself."), ephemeral=True)
    dm_e = discord.Embed(title=f"{E['ban']} Banned from {interaction.guild.name}", color=C_RED)
    dm_e.add_field(name="Reason", value=reason or "No reason provided")
    dm_e.set_footer(text="Contact an admin if you believe this is a mistake.")
    await dm_member(member, dm_e)
    await member.ban(reason=reason, delete_message_days=min(max(delete_days, 0), 7))
    res_e = embed_success("Member Banned", f"{member.mention} has been permanently banned.")
    res_e.add_field(name="User", value=f"`{member}`", inline=True)
    res_e.add_field(name="Reason", value=reason or "No reason", inline=True)
    await interaction.response.send_message(embed=res_e)
    await send_log(interaction.guild, embed_mod("Member Banned", E["ban"], interaction.user, member, reason, C_RED,
                                                {"Deleted Messages": f"{delete_days} day(s)"}))

@bot.tree.command(name="hardban", description="Permanently ban a user — they will be re-banned if they try to rejoin")
@app_commands.describe(member="Member to hardban", reason="Reason")
@app_commands.default_permissions(administrator=True)
async def hardban(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(embed=no_perm("Administrator"), ephemeral=True)
    if member.top_role >= interaction.user.top_role and interaction.user.id not in OWNER_IDS:
        return await interaction.response.send_message(embed=role_too_high(), ephemeral=True)
    gid = str(interaction.guild.id)
    uid = str(member.id)
    hardban_db.setdefault(gid, {})[uid] = {
        "reason":    reason or "No reason provided",
        "moderator": str(interaction.user),
        "time":      datetime.datetime.utcnow().isoformat()
    }
    save_json("hardbans.json", hardban_db)
    dm_e = discord.Embed(title=f"{E['hardban']} You've been hardbanned from {interaction.guild.name}", color=C_RED)
    dm_e.add_field(name="Reason", value=reason or "No reason provided")
    dm_e.set_footer(text="This ban is permanent. You cannot rejoin this server.")
    await dm_member(member, dm_e)
    await member.ban(reason=f"HARDBAN: {reason or 'No reason'}", delete_message_days=7)
    res_e = embed_success("Member Hardbanned", f"{member.mention} has been hardbanned. They will be re-banned if they attempt to rejoin.")
    res_e.add_field(name="User", value=f"`{member}`", inline=True)
    res_e.add_field(name="Reason", value=reason or "No reason", inline=True)
    await interaction.response.send_message(embed=res_e)
    await send_log(interaction.guild, embed_mod("💀 HARDBAN", E["hardban"], interaction.user, member, reason, C_RED))

@bot.tree.command(name="hardban_id", description="Hardban a user by ID (they don't need to be in the server)")
@app_commands.describe(user_id="User ID to hardban", reason="Reason")
@app_commands.default_permissions(administrator=True)
async def hardban_id(interaction: discord.Interaction, user_id: str, reason: str = None):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(embed=no_perm("Administrator"), ephemeral=True)
    try:
        user = await bot.fetch_user(int(user_id))
    except (discord.NotFound, ValueError):
        return await interaction.response.send_message(embed=embed_error("Not Found", "User not found."), ephemeral=True)
    gid = str(interaction.guild.id)
    hardban_db.setdefault(gid, {})[user_id] = {
        "reason":    reason or "No reason",
        "moderator": str(interaction.user),
        "time":      datetime.datetime.utcnow().isoformat()
    }
    save_json("hardbans.json", hardban_db)
    await interaction.guild.ban(user, reason=f"HARDBAN: {reason}", delete_message_days=7)
    res_e = embed_success("User Hardbanned", f"**{user}** has been hardbanned.")
    await interaction.response.send_message(embed=res_e)
    await send_log(interaction.guild, embed_info(f"{E['hardban']} Hardban by ID",
                                                  f"**{user}** (`{user.id}`) hardbanned by {interaction.user.mention}\n**Reason:** {reason}", color=C_RED))

@bot.tree.command(name="unhardban", description="Remove a hardban so the user can rejoin")
@app_commands.describe(user_id="User ID to unhardban")
@app_commands.default_permissions(administrator=True)
async def unhardban(interaction: discord.Interaction, user_id: str):
    gid = str(interaction.guild.id)
    if user_id not in hardban_db.get(gid, {}):
        return await interaction.response.send_message(embed=embed_error("Not Hardbanned", "That user is not hardbanned."), ephemeral=True)
    del hardban_db[gid][user_id]
    save_json("hardbans.json", hardban_db)
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user, reason=f"Hardban removed by {interaction.user}")
        name = str(user)
    except Exception:
        name = user_id
    await interaction.response.send_message(embed=embed_success("Hardban Removed", f"**{name}** can now rejoin the server."))

@bot.tree.command(name="hardbans", description="List all hardbanned users in this server")
@app_commands.default_permissions(administrator=True)
async def hardbans_list(interaction: discord.Interaction):
    gid = str(interaction.guild.id)
    bans = hardban_db.get(gid, {})
    if not bans:
        return await interaction.response.send_message(embed=embed_info("Hardbans", "No users are hardbanned."), ephemeral=True)
    e = embed_info(f"{E['hardban']} Hardbanned Users ({len(bans)})", color=C_RED)
    for uid, data in list(bans.items())[:25]:
        e.add_field(name=f"ID: {uid}", value=f"**Reason:** {data['reason']}\n**By:** {data['moderator']}", inline=True)
    await interaction.response.send_message(embed=e, ephemeral=True)

@bot.tree.command(name="softban", description="Ban then immediately unban to delete their messages")
@app_commands.describe(member="Member to softban", delete_days="Days of messages to delete (default 7)", reason="Reason")
@app_commands.default_permissions(ban_members=True)
async def softban(interaction: discord.Interaction, member: discord.Member, delete_days: int = 7, reason: str = None):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message(embed=no_perm("Ban Members"), ephemeral=True)
    if member.top_role >= interaction.user.top_role and interaction.user.id not in OWNER_IDS:
        return await interaction.response.send_message(embed=role_too_high(), ephemeral=True)
    dm_e = discord.Embed(title=f"{E['softban']} Softbanned from {interaction.guild.name}", color=C_ORANGE)
    dm_e.add_field(name="Reason", value=reason or "No reason")
    dm_e.set_footer(text="You may rejoin with a valid invite.")
    await dm_member(member, dm_e)
    await member.ban(reason=f"Softban: {reason}", delete_message_days=min(delete_days, 7))
    await interaction.guild.unban(member, reason="Softban: auto-unban")
    await interaction.response.send_message(embed=embed_success("Member Softbanned", f"{member.mention} was softbanned. Their messages ({delete_days}d) were deleted. They may rejoin."))
    await send_log(interaction.guild, embed_mod("Member Softbanned", E["softban"], interaction.user, member, reason, C_ORANGE))

@bot.tree.command(name="tempban", description="Temporarily ban a member — auto-unbans after duration")
@app_commands.describe(member="Member to tempban", duration="Duration e.g. 1h 1d 7d", reason="Reason")
@app_commands.default_permissions(ban_members=True)
async def tempban(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = None):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message(embed=no_perm("Ban Members"), ephemeral=True)
    if member.top_role >= interaction.user.top_role and interaction.user.id not in OWNER_IDS:
        return await interaction.response.send_message(embed=role_too_high(), ephemeral=True)
    td = parse_duration(duration)
    if not td:
        return await interaction.response.send_message(embed=embed_error("Invalid Duration", "Use `10m`, `2h`, `7d` format."), ephemeral=True)
    gid = str(interaction.guild.id)
    uid = str(member.id)
    expires = (datetime.datetime.utcnow() + td).timestamp()
    tempban_db.setdefault(gid, {})[uid] = {"expires": expires, "reason": reason or "No reason"}
    save_json("tempbans.json", tempban_db)
    dm_e = discord.Embed(title=f"⏳ Temporarily Banned from {interaction.guild.name}", color=C_ORANGE)
    dm_e.add_field(name="Duration", value=duration_str(td))
    dm_e.add_field(name="Reason",   value=reason or "No reason provided")
    dm_e.set_footer(text="You will be automatically unbanned when the time is up.")
    await dm_member(member, dm_e)
    await member.ban(reason=f"Tempban ({duration}): {reason}", delete_message_days=1)
    res_e = embed_success("Member Tempbanned", f"{member.mention} banned for **{duration_str(td)}**.")
    res_e.add_field(name="Expires", value=f"<t:{int(expires)}:R>", inline=True)
    await interaction.response.send_message(embed=res_e)
    await send_log(interaction.guild, embed_mod("Temp Ban", E["tempban"], interaction.user, member, reason, C_ORANGE,
                                                {"Duration": duration_str(td), "Expires": f"<t:{int(expires)}:R>"}))

@bot.tree.command(name="unban", description="Unban a user by their ID")
@app_commands.describe(user_id="User ID to unban", reason="Reason")
@app_commands.default_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: str, reason: str = None):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message(embed=no_perm("Ban Members"), ephemeral=True)
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user, reason=reason)
        # Remove from tempban if present
        tempban_db.get(str(interaction.guild.id), {}).pop(user_id, None)
        save_json("tempbans.json", tempban_db)
        res_e = embed_success("Member Unbanned", f"**{user}** has been unbanned.")
        res_e.add_field(name="Reason", value=reason or "No reason provided")
        await interaction.response.send_message(embed=res_e)
        await send_log(interaction.guild, embed_info(f"{E['unban']} Member Unbanned",
                                                      f"**{user}** unbanned by {interaction.user.mention}", color=C_GREEN))
    except (discord.NotFound, ValueError):
        await interaction.response.send_message(embed=embed_error("Not Found", "User not found or not banned."), ephemeral=True)

@bot.tree.command(name="kick", description="Kick a member from the server")
@app_commands.describe(member="Member to kick", reason="Reason")
@app_commands.default_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if not interaction.user.guild_permissions.kick_members:
        return await interaction.response.send_message(embed=no_perm("Kick Members"), ephemeral=True)
    if member.top_role >= interaction.user.top_role and interaction.user.id not in OWNER_IDS:
        return await interaction.response.send_message(embed=role_too_high(), ephemeral=True)
    dm_e = discord.Embed(title=f"{E['kick']} Kicked from {interaction.guild.name}", color=C_ORANGE)
    dm_e.add_field(name="Reason", value=reason or "No reason provided")
    dm_e.set_footer(text="You may rejoin with a valid invite.")
    await dm_member(member, dm_e)
    await member.kick(reason=reason)
    res_e = embed_success("Member Kicked", f"{member.mention} has been kicked.")
    res_e.add_field(name="User", value=f"`{member}`", inline=True)
    res_e.add_field(name="Reason", value=reason or "No reason", inline=True)
    await interaction.response.send_message(embed=res_e)
    await send_log(interaction.guild, embed_mod("Member Kicked", E["kick"], interaction.user, member, reason, C_ORANGE))

@bot.tree.command(name="timeout", description="Timeout a member — e.g. 10m, 2h, 1d")
@app_commands.describe(member="Member to timeout", duration="Duration e.g. 10m 2h 1d", reason="Reason")
@app_commands.default_permissions(moderate_members=True)
async def timeout_cmd(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = None):
    if not interaction.user.guild_permissions.moderate_members:
        return await interaction.response.send_message(embed=no_perm("Moderate Members"), ephemeral=True)
    if member.top_role >= interaction.user.top_role and interaction.user.id not in OWNER_IDS:
        return await interaction.response.send_message(embed=role_too_high(), ephemeral=True)
    td = parse_duration(duration)
    if not td:
        return await interaction.response.send_message(embed=embed_error("Invalid Duration", "Use `10m`, `2h`, `1d` format."), ephemeral=True)
    await member.timeout(td, reason=reason)
    res_e = embed_success("Member Timed Out", f"{member.mention} timed out for **{duration_str(td)}**.")
    res_e.add_field(name="Duration", value=duration_str(td), inline=True)
    res_e.add_field(name="Reason",   value=reason or "No reason", inline=True)
    await interaction.response.send_message(embed=res_e)
    dm_e = discord.Embed(title=f"{E['timeout']} Timed out in {interaction.guild.name}", color=C_YELLOW)
    dm_e.add_field(name="Duration", value=duration_str(td))
    dm_e.add_field(name="Reason",   value=reason or "No reason provided")
    await dm_member(member, dm_e)
    await send_log(interaction.guild, embed_mod("Member Timed Out", E["timeout"], interaction.user, member, reason, C_YELLOW,
                                                {"Duration": duration_str(td)}))

@bot.tree.command(name="untimeout", description="Remove a member's timeout")
@app_commands.describe(member="Member to untimeout", reason="Reason")
@app_commands.default_permissions(moderate_members=True)
async def untimeout(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if not interaction.user.guild_permissions.moderate_members:
        return await interaction.response.send_message(embed=no_perm("Moderate Members"), ephemeral=True)
    await member.timeout(None, reason=reason)
    await interaction.response.send_message(embed=embed_success("Timeout Removed", f"{member.mention}'s timeout has been removed."))
    await send_log(interaction.guild, embed_mod("Timeout Removed", E["unlock"], interaction.user, member, reason, C_GREEN))

@bot.tree.command(name="warn", description="Warn a member")
@app_commands.describe(member="Member to warn", reason="Reason")
@app_commands.default_permissions(manage_messages=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message(embed=no_perm("Manage Messages"), ephemeral=True)
    count = warn_user(str(interaction.guild.id), str(member.id), reason or "No reason", str(interaction.user))
    dm_e = discord.Embed(title=f"{E['warn']} Warning in {interaction.guild.name}", color=C_YELLOW)
    dm_e.add_field(name="Reason",         value=reason or "No reason")
    dm_e.add_field(name="Total Warnings", value=str(count))
    dm_e.set_footer(text="Please follow the server rules.")
    await dm_member(member, dm_e)
    res_e = embed_success("Member Warned", f"{member.mention} warned. They now have **{count}** warning(s).")
    res_e.add_field(name="Reason", value=reason or "No reason")
    await interaction.response.send_message(embed=res_e)
    await send_log(interaction.guild, embed_mod("Member Warned", E["warn"], interaction.user, member, reason, C_YELLOW,
                                                {"Total Warnings": str(count)}))

@bot.tree.command(name="warnings", description="View warnings for a member")
@app_commands.describe(member="Member to check")
async def warnings_cmd(interaction: discord.Interaction, member: discord.Member):
    guild_id = str(interaction.guild.id)
    user_warns = warnings_db.get(guild_id, {}).get(str(member.id), [])
    if not user_warns:
        return await interaction.response.send_message(embed=embed_success("No Warnings", f"{member.mention} has no warnings."), ephemeral=True)
    e = embed_info(f"{E['warn']} Warnings for {member}", color=C_YELLOW)
    e.set_thumbnail(url=member.display_avatar.url)
    for i, w in enumerate(user_warns, 1):
        e.add_field(name=f"Warning {i}", value=f"**Reason:** {w['reason']}\n**By:** {w['moderator']}\n**At:** {w['time']}", inline=False)
    e.set_footer(text=f"Total: {len(user_warns)} warning(s)")
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="clearwarnings", description="Clear all warnings for a member")
@app_commands.describe(member="Member to clear warnings for")
@app_commands.default_permissions(manage_messages=True)
async def clearwarnings(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message(embed=no_perm("Manage Messages"), ephemeral=True)
    warnings_db.setdefault(str(interaction.guild.id), {})[str(member.id)] = []
    save_json("warnings.json", warnings_db)
    await interaction.response.send_message(embed=embed_success("Warnings Cleared", f"All warnings cleared for {member.mention}."))

@bot.tree.command(name="delwarn", description="Delete a specific warning by number")
@app_commands.describe(member="Member", warning_number="Warning number to remove")
@app_commands.default_permissions(manage_messages=True)
async def delwarn(interaction: discord.Interaction, member: discord.Member, warning_number: int):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message(embed=no_perm("Manage Messages"), ephemeral=True)
    gid = str(interaction.guild.id)
    uid = str(member.id)
    user_warns = warnings_db.get(gid, {}).get(uid, [])
    if warning_number < 1 or warning_number > len(user_warns):
        return await interaction.response.send_message(embed=embed_error("Invalid", f"Warning #{warning_number} does not exist."), ephemeral=True)
    removed = user_warns.pop(warning_number - 1)
    save_json("warnings.json", warnings_db)
    await interaction.response.send_message(embed=embed_success("Warning Removed", f"Warning #{warning_number} removed from {member.mention}.\nReason was: `{removed['reason']}`"))

@bot.tree.command(name="purge", description="Delete messages from this channel")
@app_commands.describe(amount="Number of messages (1–100)", member="Only delete from this member")
@app_commands.default_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: int, member: discord.Member = None):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message(embed=no_perm("Manage Messages"), ephemeral=True)
    if not 1 <= amount <= 100:
        return await interaction.response.send_message(embed=embed_error("Invalid Amount", "Amount must be between 1 and 100."), ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    check = (lambda m: m.author == member) if member else None
    deleted = await interaction.channel.purge(limit=amount, check=check)
    target_str = f" from {member.mention}" if member else ""
    await interaction.followup.send(embed=embed_success("Messages Purged", f"Deleted **{len(deleted)}** message(s){target_str}."), ephemeral=True)
    log_e = embed_info(f"{E['purge']} Purge", f"**{len(deleted)}** messages purged in {interaction.channel.mention}{target_str} by {interaction.user.mention}", color=C_BLUE)
    await send_log(interaction.guild, log_e)

@bot.tree.command(name="slowmode", description="Set slowmode for this channel")
@app_commands.describe(seconds="Seconds (0 to disable, max 21600)")
@app_commands.default_permissions(manage_channels=True)
async def slowmode(interaction: discord.Interaction, seconds: int):
    if not interaction.user.guild_permissions.manage_channels:
        return await interaction.response.send_message(embed=no_perm("Manage Channels"), ephemeral=True)
    if not 0 <= seconds <= 21600:
        return await interaction.response.send_message(embed=embed_error("Invalid Value", "Must be 0–21600 seconds."), ephemeral=True)
    await interaction.channel.edit(slowmode_delay=seconds)
    msg = f"Slowmode set to **{seconds}s**." if seconds else "Slowmode **disabled**."
    await interaction.response.send_message(embed=embed_success("Slowmode Updated", msg))

@bot.tree.command(name="lock", description="Lock the current channel")
@app_commands.describe(reason="Reason for locking")
@app_commands.default_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction, reason: str = None):
    if not interaction.user.guild_permissions.manage_channels:
        return await interaction.response.send_message(embed=no_perm("Manage Channels"), ephemeral=True)
    cfg   = gcfg(interaction.guild.id)
    perm  = cfg.get("lock_deny_perm", "send_messages")
    ch    = interaction.channel
    # Deny @everyone
    ow = ch.overwrites_for(interaction.guild.default_role)
    if perm == "all":
        ow.send_messages = False
        ow.add_reactions = False
        ow.use_application_commands = False
    elif perm == "send_messages":
        ow.send_messages = False
    elif perm == "add_reactions":
        ow.add_reactions = False
    elif perm == "use_application_commands":
        ow.use_application_commands = False
    await ch.set_permissions(interaction.guild.default_role, overwrite=ow)
    # Allow exempt roles
    for rid in cfg.get("lock_exempt_roles", []):
        role = interaction.guild.get_role(int(rid))
        if role:
            role_ow = ch.overwrites_for(role)
            if perm in ("all", "send_messages"):
                role_ow.send_messages = True
            if perm in ("all", "add_reactions"):
                role_ow.add_reactions = True
            if perm in ("all", "use_application_commands"):
                role_ow.use_application_commands = True
            await ch.set_permissions(role, overwrite=role_ow)
    e = embed_info(f"{E['lock']} Channel Locked", f"**Reason:** {reason or 'No reason'}", color=C_RED)
    e.add_field(name="Locked Permission", value=f"`{perm}`", inline=True)
    exempt = [interaction.guild.get_role(int(r)) for r in cfg.get("lock_exempt_roles", []) if interaction.guild.get_role(int(r))]
    if exempt:
        e.add_field(name="Exempt Roles", value=" ".join(r.mention for r in exempt), inline=True)
    await interaction.response.send_message(embed=e)
    await send_log(interaction.guild, embed_info(f"{E['lock']} Channel Locked",
                                                  f"{interaction.channel.mention} locked by {interaction.user.mention}\n**Reason:** {reason}", color=C_RED))

@bot.tree.command(name="unlock", description="Unlock the current channel")
@app_commands.default_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_channels:
        return await interaction.response.send_message(embed=no_perm("Manage Channels"), ephemeral=True)
    cfg  = gcfg(interaction.guild.id)
    perm = cfg.get("lock_deny_perm", "send_messages")
    ow   = interaction.channel.overwrites_for(interaction.guild.default_role)
    if perm in ("all", "send_messages"):
        ow.send_messages = None
    if perm in ("all", "add_reactions"):
        ow.add_reactions = None
    if perm in ("all", "use_application_commands"):
        ow.use_application_commands = None
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=ow)
    await interaction.response.send_message(embed=embed_info(f"{E['unlock']} Channel Unlocked", "This channel is now open.", color=C_GREEN))

@bot.tree.command(name="lockdown", description="Lock ALL channels (emergency)")
@app_commands.describe(reason="Reason for lockdown")
@app_commands.default_permissions(administrator=True)
async def lockdown(interaction: discord.Interaction, reason: str = None):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(embed=no_perm("Administrator"), ephemeral=True)
    await interaction.response.defer()
    count = 0
    for ch in interaction.guild.text_channels:
        try:
            ow = ch.overwrites_for(interaction.guild.default_role)
            ow.send_messages = False
            await ch.set_permissions(interaction.guild.default_role, overwrite=ow)
            count += 1
        except Exception:
            pass
    await interaction.followup.send(embed=embed_info("🚨 SERVER LOCKDOWN",
                                                       f"**{count}** channels locked.\n**Reason:** {reason or 'No reason'}\n**By:** {interaction.user.mention}", color=C_RED))

@bot.tree.command(name="endlockdown", description="End server lockdown and unlock all channels")
@app_commands.default_permissions(administrator=True)
async def endlockdown(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(embed=no_perm("Administrator"), ephemeral=True)
    await interaction.response.defer()
    count = 0
    for ch in interaction.guild.text_channels:
        try:
            ow = ch.overwrites_for(interaction.guild.default_role)
            ow.send_messages = None
            await ch.set_permissions(interaction.guild.default_role, overwrite=ow)
            count += 1
        except Exception:
            pass
    await interaction.followup.send(embed=embed_success("Lockdown Ended", f"**{count}** channels unlocked."))

@bot.tree.command(name="nick", description="Change a member's nickname")
@app_commands.describe(member="Target member", nickname="New nickname (blank to reset)")
@app_commands.default_permissions(manage_nicknames=True)
async def nick(interaction: discord.Interaction, member: discord.Member, nickname: str = None):
    if not interaction.user.guild_permissions.manage_nicknames:
        return await interaction.response.send_message(embed=no_perm("Manage Nicknames"), ephemeral=True)
    old = member.display_name
    await member.edit(nick=nickname)
    await interaction.response.send_message(embed=embed_success("Nickname Updated", f"**{old}** → **{nickname or member.name}**"))

@bot.tree.command(name="role", description="Add or remove a role from a member")
@app_commands.describe(member="Target member", role="Role to toggle")
@app_commands.default_permissions(manage_roles=True)
async def role_cmd(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not interaction.user.guild_permissions.manage_roles:
        return await interaction.response.send_message(embed=no_perm("Manage Roles"), ephemeral=True)
    if role >= interaction.guild.me.top_role:
        return await interaction.response.send_message(embed=embed_error("Role Too High", "I can't manage that role."), ephemeral=True)
    if role in member.roles:
        await member.remove_roles(role)
        await interaction.response.send_message(embed=embed_success("Role Removed", f"Removed {role.mention} from {member.mention}."))
    else:
        await member.add_roles(role)
        await interaction.response.send_message(embed=embed_success("Role Added", f"Added {role.mention} to {member.mention}."))

@bot.tree.command(name="massrole", description="Add or remove a role from ALL members")
@app_commands.describe(role="Role to give/remove", action="add or remove")
@app_commands.default_permissions(administrator=True)
async def massrole(interaction: discord.Interaction, role: discord.Role, action: str = "add"):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(embed=no_perm("Administrator"), ephemeral=True)
    await interaction.response.defer()
    count = 0
    for member in interaction.guild.members:
        try:
            if action == "add" and role not in member.roles:
                await member.add_roles(role)
                count += 1
            elif action == "remove" and role in member.roles:
                await member.remove_roles(role)
                count += 1
        except Exception:
            pass
    await interaction.followup.send(embed=embed_success("Mass Role", f"{'Added' if action == 'add' else 'Removed'} {role.mention} for/from **{count}** members."))

@bot.tree.command(name="vcmute", description="Voice mute a member")
@app_commands.describe(member="Member to mute", reason="Reason")
@app_commands.default_permissions(mute_members=True)
async def vcmute(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if not interaction.user.guild_permissions.mute_members:
        return await interaction.response.send_message(embed=no_perm("Mute Members"), ephemeral=True)
    await member.edit(mute=True, reason=reason)
    await interaction.response.send_message(embed=embed_success("Voice Muted", f"{member.mention} has been voice muted."))

@bot.tree.command(name="vcunmute", description="Remove voice mute from a member")
@app_commands.describe(member="Member to unmute")
@app_commands.default_permissions(mute_members=True)
async def vcunmute(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.mute_members:
        return await interaction.response.send_message(embed=no_perm("Mute Members"), ephemeral=True)
    await member.edit(mute=False)
    await interaction.response.send_message(embed=embed_success("Voice Unmuted", f"{member.mention}'s voice mute has been removed."))

@bot.tree.command(name="deafen", description="Deafen a member in voice")
@app_commands.describe(member="Member to deafen", reason="Reason")
@app_commands.default_permissions(deafen_members=True)
async def deafen(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if not interaction.user.guild_permissions.deafen_members:
        return await interaction.response.send_message(embed=no_perm("Deafen Members"), ephemeral=True)
    await member.edit(deafen=True, reason=reason)
    await interaction.response.send_message(embed=embed_success("Member Deafened", f"{member.mention} has been deafened."))

@bot.tree.command(name="undeafen", description="Undeafen a member")
@app_commands.describe(member="Member to undeafen")
@app_commands.default_permissions(deafen_members=True)
async def undeafen(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.deafen_members:
        return await interaction.response.send_message(embed=no_perm("Deafen Members"), ephemeral=True)
    await member.edit(deafen=False)
    await interaction.response.send_message(embed=embed_success("Member Undeafened", f"{member.mention} can hear again."))

@bot.tree.command(name="move", description="Move a member to a different voice channel")
@app_commands.describe(member="Member to move", channel="Destination voice channel")
@app_commands.default_permissions(move_members=True)
async def move(interaction: discord.Interaction, member: discord.Member, channel: discord.VoiceChannel):
    if not interaction.user.guild_permissions.move_members:
        return await interaction.response.send_message(embed=no_perm("Move Members"), ephemeral=True)
    if not member.voice:
        return await interaction.response.send_message(embed=embed_error("Not in Voice", f"{member.mention} is not in a voice channel."), ephemeral=True)
    await member.move_to(channel)
    await interaction.response.send_message(embed=embed_success("Member Moved", f"{member.mention} moved to **{channel.name}**."))

@bot.tree.command(name="banlist", description="View all banned users in this server")
@app_commands.default_permissions(ban_members=True)
async def banlist(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message(embed=no_perm("Ban Members"), ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    bans = [entry async for entry in interaction.guild.bans()]
    if not bans:
        return await interaction.followup.send(embed=embed_info("Ban List", "No users are currently banned."), ephemeral=True)
    e = embed_info(f"🔨 Ban List ({len(bans)} bans)", color=C_RED)
    entries = "\n".join(f"`{b.user.id}` — **{b.user}** — {b.reason or 'No reason'}" for b in bans[:20])
    e.description = entries
    if len(bans) > 20:
        e.set_footer(text=f"Showing 20 of {len(bans)} bans")
    await interaction.followup.send(embed=e, ephemeral=True)

# ╔══════════════════════════════════════════════════════════╗
# ║                   UTILITY COMMANDS                       ║
# ╚══════════════════════════════════════════════════════════╝

@bot.tree.command(name="userinfo", description="Get info about a user")
@app_commands.describe(member="Member to look up")
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    m = member or interaction.user
    roles = [r.mention for r in reversed(m.roles) if r.name != "@everyone"]
    badges = []
    if m.public_flags.staff:           badges.append("👮 Discord Staff")
    if m.public_flags.partner:         badges.append("🤝 Partner")
    if m.public_flags.bug_hunter:      badges.append("🐛 Bug Hunter")
    if m.public_flags.early_supporter: badges.append("⭐ Early Supporter")
    if m.bot:                          badges.append("🤖 Bot")
    warns = len(warnings_db.get(str(interaction.guild.id), {}).get(str(m.id), []))
    gid = str(interaction.guild.id)
    is_hb = str(m.id) in hardban_db.get(gid, {})
    e = discord.Embed(title=f"{E['user']} User Information", color=m.color if m.color.value else C_BLUE)
    e.set_thumbnail(url=m.display_avatar.url)
    e.set_author(name=str(m), icon_url=m.display_avatar.url)
    e.add_field(name="🏷️ Username",       value=f"`{m}`",                                 inline=True)
    e.add_field(name="🆔 User ID",         value=f"`{m.id}`",                              inline=True)
    e.add_field(name="✏️ Nickname",        value=m.nick or "None",                         inline=True)
    e.add_field(name="📅 Account Created", value=f"<t:{int(m.created_at.timestamp())}:R>", inline=True)
    e.add_field(name="📥 Joined Server",   value=f"<t:{int(m.joined_at.timestamp())}:R>",  inline=True)
    e.add_field(name="👑 Top Role",        value=m.top_role.mention,                       inline=True)
    e.add_field(name=f"🎭 Roles ({len(roles)})", value=" ".join(roles[:10]) or "None",     inline=False)
    if badges:
        e.add_field(name="🏅 Badges", value="\n".join(badges), inline=False)
    e.add_field(name="⚠️ Warnings", value=str(warns), inline=True)
    if is_hb:
        e.add_field(name="💀 Hardban", value="This user is hardbanned", inline=True)
    e.set_footer(text=f"Requested by {interaction.user}")
    e.timestamp = datetime.datetime.utcnow()
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="serverinfo", description="Get info about the server")
async def serverinfo(interaction: discord.Interaction):
    g = interaction.guild
    bots   = sum(1 for m in g.members if m.bot)
    humans = g.member_count - bots
    online = sum(1 for m in g.members if m.status != discord.Status.offline and not m.bot)
    e = discord.Embed(title=f"{E['server']} Server Information", color=C_BLUE)
    if g.icon:
        e.set_thumbnail(url=g.icon.url)
    if g.banner:
        e.set_image(url=g.banner.url)
    e.set_author(name=g.name, icon_url=g.icon.url if g.icon else None)
    e.add_field(name="🏠 Name",         value=g.name,                                                       inline=True)
    e.add_field(name="🆔 ID",           value=f"`{g.id}`",                                                   inline=True)
    e.add_field(name="👑 Owner",        value=g.owner.mention,                                               inline=True)
    e.add_field(name="👥 Members",      value=f"👤 {humans} humans\n🤖 {bots} bots",                         inline=True)
    e.add_field(name="🟢 Online",       value=str(online),                                                   inline=True)
    e.add_field(name="💬 Channels",     value=f"💬 {len(g.text_channels)} text\n🔊 {len(g.voice_channels)} voice", inline=True)
    e.add_field(name="🎭 Roles",        value=str(len(g.roles)),                                             inline=True)
    e.add_field(name="😀 Emojis",       value=str(len(g.emojis)),                                            inline=True)
    e.add_field(name="💎 Boosts",       value=f"Level {g.premium_tier} ({g.premium_subscription_count})",   inline=True)
    e.add_field(name="📅 Created",      value=f"<t:{int(g.created_at.timestamp())}:R>",                     inline=True)
    e.add_field(name="🔒 Verification", value=str(g.verification_level).title(),                            inline=True)
    e.add_field(name="🌐 Region",       value="Automatic",                                                  inline=True)
    e.set_footer(text=f"Requested by {interaction.user}")
    e.timestamp = datetime.datetime.utcnow()
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="roleinfo", description="Get information about a role")
@app_commands.describe(role="The role to inspect")
async def roleinfo(interaction: discord.Interaction, role: discord.Role):
    members_with_role = [m for m in interaction.guild.members if role in m.roles]
    perms = [p.replace("_", " ").title() for p, v in role.permissions if v]
    e = discord.Embed(title=f"🎭 Role Info — {role.name}", color=role.color)
    e.add_field(name="🆔 ID",          value=f"`{role.id}`",                               inline=True)
    e.add_field(name="🎨 Color",       value=str(role.color),                               inline=True)
    e.add_field(name="👤 Members",     value=str(len(members_with_role)),                   inline=True)
    e.add_field(name="📌 Position",    value=str(role.position),                            inline=True)
    e.add_field(name="🤖 Managed",     value="Yes" if role.managed else "No",               inline=True)
    e.add_field(name="📢 Mentionable", value="Yes" if role.mentionable else "No",           inline=True)
    e.add_field(name="📅 Created",     value=f"<t:{int(role.created_at.timestamp())}:R>",  inline=True)
    if perms:
        e.add_field(name=f"🔑 Permissions ({len(perms)})", value=", ".join(perms[:15]) or "None", inline=False)
    e.set_footer(text=f"Requested by {interaction.user}")
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="channelinfo", description="Get information about a channel")
@app_commands.describe(channel="The channel to inspect")
async def channelinfo(interaction: discord.Interaction, channel: discord.TextChannel = None):
    ch = channel or interaction.channel
    e = discord.Embed(title=f"💬 Channel Info — #{ch.name}", color=C_BLUE)
    e.add_field(name="🆔 ID",         value=f"`{ch.id}`",                              inline=True)
    e.add_field(name="📂 Category",   value=ch.category.name if ch.category else "None", inline=True)
    e.add_field(name="📌 Position",   value=str(ch.position),                          inline=True)
    e.add_field(name="🐢 Slowmode",   value=f"{ch.slowmode_delay}s",                   inline=True)
    e.add_field(name="🔞 NSFW",       value="Yes" if ch.nsfw else "No",                inline=True)
    e.add_field(name="📅 Created",    value=f"<t:{int(ch.created_at.timestamp())}:R>", inline=True)
    if ch.topic:
        e.add_field(name="📝 Topic", value=ch.topic[:256], inline=False)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="avatar", description="Get a member's avatar")
@app_commands.describe(member="Member to get avatar of")
async def avatar(interaction: discord.Interaction, member: discord.Member = None):
    m = member or interaction.user
    e = discord.Embed(title=f"{m.display_name}'s Avatar", color=C_BLUE)
    e.set_image(url=m.display_avatar.url)
    e.add_field(name="🔗 Links", value=(
        f"[PNG]({m.display_avatar.with_format('png').url}) | "
        f"[JPG]({m.display_avatar.with_format('jpg').url}) | "
        f"[WEBP]({m.display_avatar.with_format('webp').url})"
    ))
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="banner", description="Get a member's profile banner")
@app_commands.describe(member="Member to get banner of")
async def banner(interaction: discord.Interaction, member: discord.Member = None):
    m = member or interaction.user
    user = await bot.fetch_user(m.id)
    if not user.banner:
        return await interaction.response.send_message(embed=embed_error("No Banner", f"{m.display_name} has no profile banner."), ephemeral=True)
    e = discord.Embed(title=f"{m.display_name}'s Banner", color=C_BLUE)
    e.set_image(url=user.banner.url)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    quality = "🟢 Excellent" if latency < 100 else "🟡 Good" if latency < 200 else "🔴 High"
    e = embed_info(f"{E['ping']} Pong!", f"**Latency:** `{latency}ms`\n**Status:** {quality}", color=C_BLUE)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="snipe", description="Show the last deleted message in this channel")
async def snipe(interaction: discord.Interaction):
    gid = str(interaction.guild.id)
    data = snipe_db.get(gid)
    if not data or data.get("channel") != interaction.channel.id:
        return await interaction.response.send_message(embed=embed_error("Nothing to Snipe", "No recently deleted messages in this channel."), ephemeral=True)
    e = discord.Embed(description=data["content"] or "(no text)", color=C_PURPLE)
    e.set_author(name=data["author"], icon_url=data["avatar"])
    e.set_footer(text=f"{E['snipe']} Sniped by {interaction.user}")
    e.timestamp = datetime.datetime.fromtimestamp(data["time"], tz=datetime.timezone.utc)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="editsnipe", description="Show the last edited message in this channel")
async def editsnipe(interaction: discord.Interaction):
    gid = str(interaction.guild.id)
    data = editsnipe_db.get(gid)
    if not data or data.get("channel") != interaction.channel.id:
        return await interaction.response.send_message(embed=embed_error("Nothing to Snipe", "No recently edited messages."), ephemeral=True)
    e = discord.Embed(color=C_YELLOW)
    e.set_author(name=data["author"], icon_url=data["avatar"])
    e.add_field(name="Before", value=data["before"][:500] or "(empty)", inline=False)
    e.add_field(name="After",  value=data["after"][:500]  or "(empty)", inline=False)
    e.add_field(name="🔗 Jump", value=f"[Go to message]({data['jump_url']})", inline=False)
    e.set_footer(text=f"{E['snipe']} Edit-sniped by {interaction.user}")
    e.timestamp = datetime.datetime.fromtimestamp(data["time"], tz=datetime.timezone.utc)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="say", description="Make the bot send a message")
@app_commands.describe(message="Message content", channel="Channel to send to")
@app_commands.default_permissions(manage_messages=True)
async def say(interaction: discord.Interaction, message: str, channel: discord.TextChannel = None):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message(embed=no_perm("Manage Messages"), ephemeral=True)
    target = channel or interaction.channel
    await target.send(message)
    await interaction.response.send_message(embed=embed_success("Message Sent", f"Sent to {target.mention}."), ephemeral=True)

@bot.tree.command(name="embed", description="Send a custom embed message")
@app_commands.describe(title="Title", description="Description", color="Hex color (e.g. ff0000)", channel="Channel")
@app_commands.default_permissions(manage_messages=True)
async def embed_cmd(interaction: discord.Interaction, title: str, description: str, color: str = "5865f2", channel: discord.TextChannel = None):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message(embed=no_perm("Manage Messages"), ephemeral=True)
    try:
        col = int(color.replace("#", ""), 16)
    except Exception:
        col = C_BLUE
    target = channel or interaction.channel
    e = discord.Embed(title=title, description=description, color=col)
    e.set_footer(text=f"Sent by {interaction.user}")
    e.timestamp = datetime.datetime.utcnow()
    await target.send(embed=e)
    await interaction.response.send_message(embed=embed_success("Embed Sent", f"Sent to {target.mention}."), ephemeral=True)

@bot.tree.command(name="poll", description="Create a yes/no poll")
@app_commands.describe(question="Poll question")
async def poll(interaction: discord.Interaction, question: str):
    e = discord.Embed(title="📊 Poll", description=f"**{question}**", color=C_PURPLE)
    e.set_footer(text=f"Poll by {interaction.user}")
    e.timestamp = datetime.datetime.utcnow()
    await interaction.response.send_message(embed=e)
    msg = await interaction.original_response()
    await msg.add_reaction("✅")
    await msg.add_reaction("❌")

@bot.tree.command(name="multipoll", description="Create a poll with up to 5 custom options")
@app_commands.describe(question="Poll question", options="Options separated by | e.g. Option A|Option B|Option C")
async def multipoll(interaction: discord.Interaction, question: str, options: str):
    opts = [o.strip() for o in options.split("|")][:5]
    if len(opts) < 2:
        return await interaction.response.send_message(embed=embed_error("Invalid", "Provide at least 2 options separated by `|`."), ephemeral=True)
    emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣"]
    desc = f"**{question}**\n\n" + "\n".join(f"{emojis[i]} {o}" for i, o in enumerate(opts))
    e = discord.Embed(title="📊 Poll", description=desc, color=C_PURPLE)
    e.set_footer(text=f"Poll by {interaction.user}")
    e.timestamp = datetime.datetime.utcnow()
    await interaction.response.send_message(embed=e)
    msg = await interaction.original_response()
    for i in range(len(opts)):
        await msg.add_reaction(emojis[i])

@bot.tree.command(name="giveaway", description="Start a simple giveaway (ends after duration)")
@app_commands.describe(prize="What to give away", duration="Duration e.g. 1h 1d", winners="Number of winners")
@app_commands.default_permissions(manage_guild=True)
async def giveaway(interaction: discord.Interaction, prize: str, duration: str, winners: int = 1):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message(embed=no_perm("Manage Guild"), ephemeral=True)
    td = parse_duration(duration)
    if not td:
        return await interaction.response.send_message(embed=embed_error("Invalid Duration", "Use e.g. `1h`, `1d`."), ephemeral=True)
    ends_at = datetime.datetime.utcnow() + td
    e = discord.Embed(title="🎉 GIVEAWAY!", description=f"**Prize:** {prize}\n\nReact with 🎉 to enter!", color=C_PINK)
    e.add_field(name="⏰ Ends",   value=f"<t:{int(ends_at.timestamp())}:R>", inline=True)
    e.add_field(name="🏆 Winners", value=str(winners), inline=True)
    e.set_footer(text=f"Hosted by {interaction.user}")
    await interaction.response.send_message(embed=e)
    msg = await interaction.original_response()
    await msg.add_reaction("🎉")

    await asyncio.sleep(td.total_seconds())
    msg = await interaction.channel.fetch_message(msg.id)
    reaction = discord.utils.get(msg.reactions, emoji="🎉")
    if reaction:
        users = [u async for u in reaction.users() if not u.bot]
        if users:
            win_list = random.sample(users, min(winners, len(users)))
            win_mentions = " ".join(w.mention for w in win_list)
            e2 = discord.Embed(title="🎉 Giveaway Ended!", description=f"**Prize:** {prize}\n**Winners:** {win_mentions}", color=C_GREEN)
            await interaction.channel.send(content=win_mentions, embed=e2)
        else:
            await interaction.channel.send(embed=embed_error("No Winners", "Nobody entered the giveaway."))

@bot.tree.command(name="announce", description="Send an announcement embed to a channel")
@app_commands.describe(channel="Announcement channel", title="Title", message="Announcement text", ping="Role to ping (optional)")
@app_commands.default_permissions(manage_guild=True)
async def announce(interaction: discord.Interaction, channel: discord.TextChannel, title: str, message: str, ping: discord.Role = None):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message(embed=no_perm("Manage Guild"), ephemeral=True)
    e = discord.Embed(title=f"📢 {title}", description=message, color=C_BLUE)
    e.set_footer(text=f"Announced by {interaction.user}")
    e.timestamp = datetime.datetime.utcnow()
    content = ping.mention if ping else None
    await channel.send(content=content, embed=e)
    await interaction.response.send_message(embed=embed_success("Announcement Sent", f"Sent to {channel.mention}."), ephemeral=True)

# ── Fun commands ─────────────────────────────────────────────
@bot.tree.command(name="8ball", description="Ask the magic 8-ball a question")
@app_commands.describe(question="Your question")
async def eightball(interaction: discord.Interaction, question: str):
    answers = [
        "It is certain.", "It is decidedly so.", "Without a doubt.",
        "Yes, definitely.", "You may rely on it.", "As I see it, yes.",
        "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
        "Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
        "Cannot predict now.", "Concentrate and ask again.",
        "Don't count on it.", "My reply is no.", "My sources say no.",
        "Outlook not so good.", "Very doubtful."
    ]
    e = discord.Embed(title="🎱 Magic 8-Ball", color=C_PURPLE)
    e.add_field(name="Question", value=question, inline=False)
    e.add_field(name="Answer",   value=random.choice(answers), inline=False)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="coinflip", description="Flip a coin")
async def coinflip(interaction: discord.Interaction):
    result = random.choice(["🪙 Heads!", "🪙 Tails!"])
    await interaction.response.send_message(embed=embed_info("Coin Flip", result, color=C_YELLOW))

@bot.tree.command(name="roll", description="Roll dice — e.g. 2d6 or d20")
@app_commands.describe(dice="Dice notation e.g. 2d6 d20 3d8")
async def roll(interaction: discord.Interaction, dice: str = "d6"):
    m = re.match(r"^(\d*)d(\d+)$", dice.lower())
    if not m:
        return await interaction.response.send_message(embed=embed_error("Invalid", "Use dice notation like `2d6` or `d20`."), ephemeral=True)
    count = int(m.group(1) or 1)
    sides = int(m.group(2))
    if count > 50 or sides > 1000:
        return await interaction.response.send_message(embed=embed_error("Too Large", "Max 50 dice, 1000 sides."), ephemeral=True)
    rolls = [random.randint(1, sides) for _ in range(count)]
    e = embed_info(f"🎲 Roll {dice.upper()}", color=C_TEAL)
    e.add_field(name="Rolls",  value=str(rolls), inline=True)
    e.add_field(name="Total",  value=str(sum(rolls)), inline=True)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="choose", description="Let the bot choose between options")
@app_commands.describe(options="Options separated by | e.g. Pizza|Tacos|Burgers")
async def choose(interaction: discord.Interaction, options: str):
    choices = [o.strip() for o in options.split("|") if o.strip()]
    if len(choices) < 2:
        return await interaction.response.send_message(embed=embed_error("Invalid", "Provide at least 2 options separated by `|`."), ephemeral=True)
    winner = random.choice(choices)
    e = embed_info("🤔 I Choose...", f"**{winner}**", color=C_PURPLE)
    e.set_footer(text=f"Picked from: {', '.join(choices)}")
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="stats", description="View bot statistics")
async def stats(interaction: discord.Interaction):
    total_warns = sum(len(u) for g in warnings_db.values() for u in g.values())
    total_hardbans = sum(len(g) for g in hardban_db.values())
    e = embed_info(f"{E['bot']} Bot Statistics", color=C_BLUE)
    e.add_field(name="🏠 Servers",      value=str(len(bot.guilds)), inline=True)
    e.add_field(name="👥 Total Members", value=f"{sum(g.member_count for g in bot.guilds):,}", inline=True)
    e.add_field(name="⏱️ Ping",         value=f"{round(bot.latency*1000)}ms", inline=True)
    e.add_field(name="⚠️ Total Warns",  value=str(total_warns), inline=True)
    e.add_field(name="💀 Hardbans",     value=str(total_hardbans), inline=True)
    e.add_field(name="🤖 Bot ID",       value=f"`{bot.user.id}`", inline=True)
    e.set_thumbnail(url=bot.user.display_avatar.url)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="help", description="View all available commands")
async def help_cmd(interaction: discord.Interaction):
    e = discord.Embed(title=f"{E['bot']} Command Reference", color=C_BLUE)
    e.set_thumbnail(url=bot.user.display_avatar.url)
    e.add_field(name="🔨 Core Moderation", value=(
        "`/ban` `/unban` `/kick`\n"
        "`/timeout` `/untimeout`\n"
        "`/warn` `/warnings` `/clearwarnings` `/delwarn`\n"
        "`/purge` `/slowmode` `/nick` `/role`"
    ), inline=True)
    e.add_field(name="⚡ Advanced Mod", value=(
        "`/hardban` `/hardban_id` `/unhardban` `/hardbans`\n"
        "`/softban` `/tempban` `/banlist`\n"
        "`/massrole` `/vcmute` `/vcunmute`\n"
        "`/deafen` `/undeafen` `/move`"
    ), inline=True)
    e.add_field(name="🔒 Channels", value=(
        "`/lock` `/unlock`\n"
        "`/lockdown` `/endlockdown`"
    ), inline=True)
    e.add_field(name="⚙️ Setup (Admin)", value=(
        "`/setuplog` `/setupwelcome` `/setupgoodbye`\n"
        "`/setuplock` `/setupverify` `/setuptickets`\n"
        "`/setupautomod` `/badword` `/filterlist`"
    ), inline=True)
    e.add_field(name="✔️ Verification", value=(
        "`/setupverify` — button/reaction/code\n"
        "`/getcode` `/verify`"
    ), inline=True)
    e.add_field(name="🎫 Tickets", value=(
        "`/setuptickets`\n"
        "Panel with open/close buttons"
    ), inline=True)
    e.add_field(name="🛠️ Utility", value=(
        "`/userinfo` `/serverinfo` `/roleinfo`\n"
        "`/channelinfo` `/avatar` `/banner`\n"
        "`/ping` `/stats` `/snipe` `/editsnipe`\n"
        "`/say` `/embed` `/announce`"
    ), inline=True)
    e.add_field(name="🎉 Fun & Events", value=(
        "`/poll` `/multipoll` `/giveaway`\n"
        "`/8ball` `/coinflip` `/roll` `/choose`"
    ), inline=True)
    e.add_field(name="⚡ AutoMod (auto)", value=(
        "• Anti-Spam (timeout + warn)\n"
        "• Anti-Links (configurable)\n"
        "• Anti-Caps (configurable)\n"
        "• Bad Word Filter (configurable)\n"
        "• Message/Voice/Edit logging"
    ), inline=True)
    e.set_footer(text="TSR Advanced Bot • Use /setuplog to enable logging first!")
    e.timestamp = datetime.datetime.utcnow()
    await interaction.response.send_message(embed=e, ephemeral=True)

# ── Register persistent views on startup ─────────────────────
@bot.event
async def on_ready_views():
    bot.add_view(VerifyButton())
    bot.add_view(TicketButton())
    bot.add_view(TicketCloseButton())

# ╔══════════════════════════════════════════════════════════╗
# ║                        RUN                               ║
# ╚══════════════════════════════════════════════════════════╝

async def main():
    async with bot:
        bot.add_view(VerifyButton())
        bot.add_view(TicketButton())
        bot.add_view(TicketCloseButton())
        await bot.start(BOT_TOKEN)

import asyncio
asyncio.run(main())
