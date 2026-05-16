import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import asyncio
import random
import re
import os

# ╔══════════════════════════════════════════════════════════╗
# ║                    CONFIGURATION                         ║
# ╚══════════════════════════════════════════════════════════╝
#
#  ⚠️  NEVER put your token here!
#  Put it in an environment variable called DISCORD_TOKEN
#  On Railway: go to Variables tab and add DISCORD_TOKEN = your_token
#
BOT_TOKEN       = os.environ["DISCORD_TOKEN"]   # reads from environment — safe ✅
LOG_CHANNEL     = "mod-logs"
WELCOME_CHANNEL = "welcome"
OWNER_IDS       = [1341036065397411926]          # your Discord user ID

# ── Brand colours ────────────────────────────────────────────
C_RED    = 0xED4245
C_ORANGE = 0xFEA832
C_YELLOW = 0xFEE75C
C_GREEN  = 0x57F287
C_BLUE   = 0x5865F2
C_PURPLE = 0x9B59B6

# ── Emoji map ────────────────────────────────────────────────
E = {
    "ban":     "🔨", "unban":   "🔓", "kick":    "👢",
    "timeout": "⏱️", "warn":    "⚠️", "purge":   "🗑️",
    "lock":    "🔒", "unlock":  "🔓", "slow":    "🐢",
    "nick":    "✏️", "role":    "🎭", "success": "✅",
    "error":   "❌", "shield":  "🛡️", "star":    "⭐",
    "wave":    "👋", "crown":   "👑", "chart":   "📊",
    "clock":   "🕐", "ping":    "🏓", "bot":     "🤖",
    "server":  "🏠", "user":    "👤", "log":     "📝",
    "fire":    "🔥", "diamond": "💎", "link":    "🔗",
    "mail":    "📨",
}

# ╔══════════════════════════════════════════════════════════╗
# ║                      BOT SETUP                           ║
# ╚══════════════════════════════════════════════════════════╝

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

warnings_db:  dict = {}   # { guild_id: { user_id: [ {reason, moderator, time} ] } }
antispam_db:  dict = {}   # { guild_id: { user_id: [timestamps] } }
ANTISPAM_LIMIT  = 5       # messages …
ANTISPAM_WINDOW = 5       # … in this many seconds = spam

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

def embed_info(title: str, description: str = None, color: int = C_BLUE) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=color)
    e.timestamp = datetime.datetime.utcnow()
    return e

def embed_mod(action: str, emoji: str, moderator, target,
              reason: str, color: int, extra: dict = None) -> discord.Embed:
    e = discord.Embed(title=f"{emoji} {action}", color=color,
                      timestamp=datetime.datetime.utcnow())
    e.set_author(
        name=f"Moderation • {moderator.guild.name}",
        icon_url=moderator.guild.icon.url if moderator.guild.icon else None
    )
    e.set_thumbnail(url=target.display_avatar.url)
    e.add_field(name="👤 Target",    value=f"{target.mention}\n`{target} • {target.id}`", inline=True)
    e.add_field(name="🛡️ Moderator", value=f"{moderator.mention}\n`{moderator}`",          inline=True)
    e.add_field(name="📝 Reason",    value=f"```{reason or 'No reason provided'}```",      inline=False)
    if extra:
        for k, v in extra.items():
            e.add_field(name=k, value=v, inline=True)
    e.set_footer(text="TSR Moderation System")
    return e

# ╔══════════════════════════════════════════════════════════╗
# ║                       HELPERS                            ║
# ╚══════════════════════════════════════════════════════════╝

async def send_log(guild: discord.Guild, embed: discord.Embed) -> None:
    ch = discord.utils.get(guild.text_channels, name=LOG_CHANNEL)
    if ch:
        await ch.send(embed=embed)

async def dm_member(member: discord.Member, embed: discord.Embed) -> None:
    try:
        await member.send(embed=embed)
    except Exception:
        pass  # DMs may be closed — that's fine

def no_perm(action: str) -> discord.Embed:
    return embed_error("Missing Permissions",
                       f"You need **{action}** permission to use this command.")

def role_too_high() -> discord.Embed:
    return embed_error("Role Hierarchy",
                       "You cannot moderate someone with an equal or higher role.")

def warn_user(guild_id: str, user_id: str, reason: str, mod_name: str) -> int:
    warnings_db.setdefault(guild_id, {}).setdefault(user_id, [])
    warnings_db[guild_id][user_id].append({
        "reason":    reason,
        "moderator": mod_name,
        "time":      datetime.datetime.utcnow().strftime("%b %d, %Y %H:%M UTC"),
    })
    return len(warnings_db[guild_id][user_id])

def parse_duration(s: str) -> datetime.timedelta | None:
    """Parse a duration string like 10m, 2h, 1d into a timedelta."""
    m = re.match(r"^(\d+)([smhd])$", s.lower())
    if not m:
        return None
    v, u = int(m.group(1)), m.group(2)
    return {
        "s": datetime.timedelta(seconds=v),
        "m": datetime.timedelta(minutes=v),
        "h": datetime.timedelta(hours=v),
        "d": datetime.timedelta(days=v),
    }.get(u)

# ╔══════════════════════════════════════════════════════════╗
# ║                        EVENTS                            ║
# ╚══════════════════════════════════════════════════════════╝

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"\n{'═'*50}")
    print(f"  {E['bot']}  Online  : {bot.user}")
    print(f"  {E['server']}  Servers : {len(bot.guilds)}")
    print(f"{'═'*50}\n")
    if not status_rotation.is_running():
        status_rotation.start()

@tasks.loop(seconds=30)
async def status_rotation():
    statuses = [
        discord.Activity(type=discord.ActivityType.watching,
                         name=f"{sum(g.member_count for g in bot.guilds)} members"),
        discord.Activity(type=discord.ActivityType.watching,
                         name=f"{len(bot.guilds)} servers"),
        discord.Activity(type=discord.ActivityType.playing,   name="Use /help"),
        discord.Activity(type=discord.ActivityType.listening, name="slash commands"),
    ]
    await bot.change_presence(activity=random.choice(statuses))

@bot.event
async def on_member_join(member: discord.Member):
    ch = discord.utils.get(member.guild.text_channels, name=WELCOME_CHANNEL)
    if not ch:
        return
    e = discord.Embed(
        title=f"{E['wave']} Welcome to {member.guild.name}!",
        description=(
            f"Hey {member.mention}, we're glad you're here!\n\n"
            f"{E['star']} You are member **#{member.guild.member_count}**\n"
            f"{E['shield']} Please read the rules and enjoy your stay!"
        ),
        color=C_BLUE,
    )
    e.set_thumbnail(url=member.display_avatar.url)
    e.set_footer(text=f"Account created {member.created_at.strftime('%b %d, %Y')}")
    e.timestamp = datetime.datetime.utcnow()
    await ch.send(embed=e)

@bot.event
async def on_member_remove(member: discord.Member):
    ch = discord.utils.get(member.guild.text_channels, name=LOG_CHANNEL)
    if not ch:
        return
    e = embed_info(
        f"{E['wave']} Member Left",
        f"**{member}** (`{member.id}`) has left the server.",
        color=C_ORANGE,
    )
    e.set_thumbnail(url=member.display_avatar.url)
    await ch.send(embed=e)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    guild_id = str(message.guild.id)
    user_id  = str(message.author.id)
    now      = datetime.datetime.utcnow().timestamp()

    # ── Anti-spam tracking ───────────────────────────────────
    antispam_db.setdefault(guild_id, {}).setdefault(user_id, [])
    antispam_db[guild_id][user_id] = [
        t for t in antispam_db[guild_id][user_id] if now - t < ANTISPAM_WINDOW
    ]
    antispam_db[guild_id][user_id].append(now)

    if len(antispam_db[guild_id][user_id]) >= ANTISPAM_LIMIT:
        if not message.author.guild_permissions.manage_messages:
            antispam_db[guild_id][user_id] = []
            try:
                await message.channel.purge(
                    limit=ANTISPAM_LIMIT,
                    check=lambda m: m.author == message.author,
                )
            except Exception:
                pass
            try:
                await message.author.timeout(
                    datetime.timedelta(minutes=5), reason="AutoMod: Spamming"
                )
            except Exception:
                pass
            warn_user(guild_id, user_id, "AutoMod: Spamming", "AutoMod")
            alert = embed_error(
                "⚡ Anti-Spam Triggered",
                f"{message.author.mention} was timed out for **5 minutes** for spamming.",
            )
            alert.set_footer(text="AutoMod System")
            await message.channel.send(embed=alert, delete_after=8)
            await send_log(
                message.guild,
                embed_mod("AutoMod: Spam", "⚡", message.guild.me,
                          message.author, "Spamming messages", C_ORANGE),
            )

    await bot.process_commands(message)

# ╔══════════════════════════════════════════════════════════╗
# ║                  MODERATION COMMANDS                     ║
# ╚══════════════════════════════════════════════════════════╝

@bot.tree.command(name="ban", description="Ban a member from the server")
@app_commands.describe(member="Member to ban", reason="Reason",
                       delete_days="Days of messages to delete (0–7)")
async def ban(interaction: discord.Interaction, member: discord.Member,
              reason: str = None, delete_days: int = 1):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message(embed=no_perm("Ban Members"), ephemeral=True)
    if member.top_role >= interaction.user.top_role and interaction.user.id not in OWNER_IDS:
        return await interaction.response.send_message(embed=role_too_high(), ephemeral=True)
    if member == interaction.user:
        return await interaction.response.send_message(
            embed=embed_error("Invalid Target", "You cannot ban yourself."), ephemeral=True)

    dm_e = discord.Embed(
        title=f"{E['ban']} You've been banned from {interaction.guild.name}", color=C_RED)
    dm_e.add_field(name="Reason", value=reason or "No reason provided")
    dm_e.set_footer(text="Contact a server admin if you believe this is a mistake.")
    await dm_member(member, dm_e)

    await member.ban(reason=reason, delete_message_days=min(max(delete_days, 0), 7))
    res_e = embed_success("Member Banned", f"{member.mention} has been permanently banned.")
    res_e.add_field(name="User",   value=f"`{member}`",         inline=True)
    res_e.add_field(name="Reason", value=reason or "No reason", inline=True)
    await interaction.response.send_message(embed=res_e)
    await send_log(interaction.guild, embed_mod(
        "Member Banned", E["ban"], interaction.user, member, reason, C_RED,
        {"Deleted Messages": f"{delete_days} day(s)"},
    ))

@bot.tree.command(name="unban", description="Unban a user by their ID")
@app_commands.describe(user_id="User ID to unban", reason="Reason")
async def unban(interaction: discord.Interaction, user_id: str, reason: str = None):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message(embed=no_perm("Ban Members"), ephemeral=True)
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user, reason=reason)
        res_e = embed_success("Member Unbanned", f"**{user}** has been unbanned.")
        res_e.add_field(name="Reason", value=reason or "No reason provided")
        await interaction.response.send_message(embed=res_e)
        await send_log(interaction.guild, embed_mod(
            "Member Unbanned", E["unban"], interaction.user, user, reason, C_GREEN))
    except (discord.NotFound, ValueError):
        await interaction.response.send_message(
            embed=embed_error("Not Found", "User not found or not currently banned."),
            ephemeral=True)

@bot.tree.command(name="kick", description="Kick a member from the server")
@app_commands.describe(member="Member to kick", reason="Reason")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if not interaction.user.guild_permissions.kick_members:
        return await interaction.response.send_message(embed=no_perm("Kick Members"), ephemeral=True)
    if member.top_role >= interaction.user.top_role and interaction.user.id not in OWNER_IDS:
        return await interaction.response.send_message(embed=role_too_high(), ephemeral=True)

    dm_e = discord.Embed(
        title=f"{E['kick']} You've been kicked from {interaction.guild.name}", color=C_ORANGE)
    dm_e.add_field(name="Reason", value=reason or "No reason provided")
    dm_e.set_footer(text="You may rejoin with a valid invite.")
    await dm_member(member, dm_e)

    await member.kick(reason=reason)
    res_e = embed_success("Member Kicked", f"{member.mention} has been kicked.")
    res_e.add_field(name="User",   value=f"`{member}`",         inline=True)
    res_e.add_field(name="Reason", value=reason or "No reason", inline=True)
    await interaction.response.send_message(embed=res_e)
    await send_log(interaction.guild, embed_mod(
        "Member Kicked", E["kick"], interaction.user, member, reason, C_ORANGE))

@bot.tree.command(name="timeout", description="Timeout a member — e.g. 10m, 2h, 1d")
@app_commands.describe(member="Member to timeout", duration="Duration e.g. 10m 2h 1d",
                       reason="Reason")
async def timeout_cmd(interaction: discord.Interaction, member: discord.Member,
                      duration: str, reason: str = None):
    if not interaction.user.guild_permissions.moderate_members:
        return await interaction.response.send_message(
            embed=no_perm("Moderate Members"), ephemeral=True)
    if member.top_role >= interaction.user.top_role and interaction.user.id not in OWNER_IDS:
        return await interaction.response.send_message(embed=role_too_high(), ephemeral=True)

    td = parse_duration(duration)
    if not td:
        return await interaction.response.send_message(
            embed=embed_error("Invalid Duration", "Use `10m`, `2h`, `1d` format."), ephemeral=True)

    await member.timeout(td, reason=reason)
    res_e = embed_success("Member Timed Out", f"{member.mention} timed out for **{duration}**.")
    res_e.add_field(name="Duration", value=duration,              inline=True)
    res_e.add_field(name="Reason",   value=reason or "No reason", inline=True)
    await interaction.response.send_message(embed=res_e)

    dm_e = discord.Embed(
        title=f"{E['timeout']} You've been timed out in {interaction.guild.name}", color=C_YELLOW)
    dm_e.add_field(name="Duration", value=duration)
    dm_e.add_field(name="Reason",   value=reason or "No reason provided")
    await dm_member(member, dm_e)
    await send_log(interaction.guild, embed_mod(
        "Member Timed Out", E["timeout"], interaction.user, member, reason, C_YELLOW,
        {"Duration": duration},
    ))

@bot.tree.command(name="untimeout", description="Remove timeout from a member")
@app_commands.describe(member="Member to untimeout", reason="Reason")
async def untimeout(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if not interaction.user.guild_permissions.moderate_members:
        return await interaction.response.send_message(
            embed=no_perm("Moderate Members"), ephemeral=True)
    await member.timeout(None, reason=reason)
    await interaction.response.send_message(
        embed=embed_success("Timeout Removed", f"Timeout removed from {member.mention}."))
    await send_log(interaction.guild, embed_mod(
        "Timeout Removed", E["untimeout" if "untimeout" in E else "unlock"],
        interaction.user, member, reason, C_GREEN))

@bot.tree.command(name="warn", description="Warn a member")
@app_commands.describe(member="Member to warn", reason="Reason")
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message(
            embed=no_perm("Manage Messages"), ephemeral=True)

    count = warn_user(str(interaction.guild.id), str(member.id),
                      reason or "No reason provided", str(interaction.user))
    dm_e = discord.Embed(
        title=f"{E['warn']} You've received a warning in {interaction.guild.name}",
        color=C_YELLOW)
    dm_e.add_field(name="Reason",          value=reason or "No reason provided")
    dm_e.add_field(name="Total Warnings",  value=str(count))
    await dm_member(member, dm_e)

    res_e = embed_success("Member Warned",
                          f"{member.mention} warned. They now have **{count}** warning(s).")
    res_e.add_field(name="Reason", value=reason or "No reason provided")
    await interaction.response.send_message(embed=res_e)
    await send_log(interaction.guild, embed_mod(
        "Member Warned", E["warn"], interaction.user, member, reason, C_YELLOW,
        {"Total Warnings": str(count)},
    ))

@bot.tree.command(name="warnings", description="View warnings for a member")
@app_commands.describe(member="Member to check")
async def warnings_cmd(interaction: discord.Interaction, member: discord.Member):
    guild_id, user_id = str(interaction.guild.id), str(member.id)
    user_warns = warnings_db.get(guild_id, {}).get(user_id, [])
    if not user_warns:
        return await interaction.response.send_message(
            embed=embed_success("No Warnings", f"{member.mention} has no warnings."),
            ephemeral=True)
    e = embed_info(f"{E['warn']} Warnings for {member}", color=C_YELLOW)
    e.set_thumbnail(url=member.display_avatar.url)
    for i, w in enumerate(user_warns, 1):
        e.add_field(
            name=f"Warning {i}",
            value=f"**Reason:** {w['reason']}\n**By:** {w['moderator']}\n**At:** {w['time']}",
            inline=False,
        )
    e.set_footer(text=f"Total: {len(user_warns)} warning(s)")
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="clearwarnings", description="Clear all warnings for a member")
@app_commands.describe(member="Member to clear warnings for")
async def clearwarnings(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message(
            embed=no_perm("Manage Messages"), ephemeral=True)
    warnings_db.setdefault(str(interaction.guild.id), {})[str(member.id)] = []
    await interaction.response.send_message(
        embed=embed_success("Warnings Cleared",
                            f"All warnings cleared for {member.mention}."))

@bot.tree.command(name="purge", description="Delete messages from this channel")
@app_commands.describe(amount="Number of messages (1–100)",
                       member="Only delete from this member")
async def purge(interaction: discord.Interaction, amount: int,
                member: discord.Member = None):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message(
            embed=no_perm("Manage Messages"), ephemeral=True)
    if not 1 <= amount <= 100:
        return await interaction.response.send_message(
            embed=embed_error("Invalid Amount", "Amount must be between 1 and 100."),
            ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    check = (lambda m: m.author == member) if member else None
    deleted = await interaction.channel.purge(limit=amount, check=check)
    target_str = f" from {member.mention}" if member else ""
    await interaction.followup.send(
        embed=embed_success("Messages Purged",
                            f"Deleted **{len(deleted)}** message(s){target_str}."),
        ephemeral=True)
    await send_log(interaction.guild, embed_info(
        f"{E['purge']} Purge",
        f"**{len(deleted)}** messages deleted in {interaction.channel.mention}{target_str}.\n"
        f"**By:** {interaction.user.mention}",
        color=C_BLUE,
    ))

@bot.tree.command(name="slowmode", description="Set slowmode for this channel")
@app_commands.describe(seconds="Seconds (0 to disable, max 21600)")
async def slowmode(interaction: discord.Interaction, seconds: int):
    if not interaction.user.guild_permissions.manage_channels:
        return await interaction.response.send_message(
            embed=no_perm("Manage Channels"), ephemeral=True)
    if not 0 <= seconds <= 21600:
        return await interaction.response.send_message(
            embed=embed_error("Invalid Value", "Must be between 0 and 21600 seconds."),
            ephemeral=True)
    await interaction.channel.edit(slowmode_delay=seconds)
    msg = f"Slowmode set to **{seconds}s**." if seconds else "Slowmode **disabled**."
    await interaction.response.send_message(embed=embed_success("Slowmode Updated", msg))

@bot.tree.command(name="lock", description="Lock the current channel")
@app_commands.describe(reason="Reason for locking")
async def lock(interaction: discord.Interaction, reason: str = None):
    if not interaction.user.guild_permissions.manage_channels:
        return await interaction.response.send_message(
            embed=no_perm("Manage Channels"), ephemeral=True)
    ow = interaction.channel.overwrites_for(interaction.guild.default_role)
    ow.send_messages = False
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=ow)
    await interaction.response.send_message(embed=embed_info(
        f"{E['lock']} Channel Locked",
        f"**Reason:** {reason or 'No reason provided'}",
        color=C_RED,
    ))

@bot.tree.command(name="unlock", description="Unlock the current channel")
async def unlock(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_channels:
        return await interaction.response.send_message(
            embed=no_perm("Manage Channels"), ephemeral=True)
    ow = interaction.channel.overwrites_for(interaction.guild.default_role)
    ow.send_messages = True
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=ow)
    await interaction.response.send_message(embed=embed_info(
        f"{E['unlock']} Channel Unlocked", "This channel is now open.", color=C_GREEN))

@bot.tree.command(name="lockdown", description="Lock ALL channels in the server (emergency)")
@app_commands.describe(reason="Reason for lockdown")
async def lockdown(interaction: discord.Interaction, reason: str = None):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            embed=no_perm("Administrator"), ephemeral=True)
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
    await interaction.followup.send(embed=embed_info(
        "🚨 SERVER LOCKDOWN",
        f"**{count}** channels locked.\n"
        f"**Reason:** {reason or 'No reason'}\n"
        f"**By:** {interaction.user.mention}",
        color=C_RED,
    ))

@bot.tree.command(name="endlockdown", description="End server lockdown and unlock all channels")
async def endlockdown(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            embed=no_perm("Administrator"), ephemeral=True)
    await interaction.response.defer()
    count = 0
    for ch in interaction.guild.text_channels:
        try:
            ow = ch.overwrites_for(interaction.guild.default_role)
            ow.send_messages = True
            await ch.set_permissions(interaction.guild.default_role, overwrite=ow)
            count += 1
        except Exception:
            pass
    await interaction.followup.send(
        embed=embed_success("Lockdown Ended", f"**{count}** channels unlocked."))

@bot.tree.command(name="nick", description="Change a member's nickname")
@app_commands.describe(member="Target member", nickname="New nickname (blank to reset)")
async def nick(interaction: discord.Interaction, member: discord.Member,
               nickname: str = None):
    if not interaction.user.guild_permissions.manage_nicknames:
        return await interaction.response.send_message(
            embed=no_perm("Manage Nicknames"), ephemeral=True)
    old = member.display_name
    await member.edit(nick=nickname)
    await interaction.response.send_message(embed=embed_success(
        "Nickname Updated", f"**{old}** → **{nickname or member.name}**"))

@bot.tree.command(name="role", description="Add or remove a role from a member")
@app_commands.describe(member="Target member", role="Role to toggle")
async def role_cmd(interaction: discord.Interaction, member: discord.Member,
                   role: discord.Role):
    if not interaction.user.guild_permissions.manage_roles:
        return await interaction.response.send_message(
            embed=no_perm("Manage Roles"), ephemeral=True)
    if role >= interaction.guild.me.top_role:
        return await interaction.response.send_message(
            embed=embed_error("Role Too High", "I can't manage that role."), ephemeral=True)
    if role in member.roles:
        await member.remove_roles(role)
        await interaction.response.send_message(
            embed=embed_success("Role Removed", f"Removed {role.mention} from {member.mention}."))
    else:
        await member.add_roles(role)
        await interaction.response.send_message(
            embed=embed_success("Role Added", f"Added {role.mention} to {member.mention}."))

# ╔══════════════════════════════════════════════════════════╗
# ║                   UTILITY COMMANDS                       ║
# ╚══════════════════════════════════════════════════════════╝

@bot.tree.command(name="userinfo", description="Get info about a user")
@app_commands.describe(member="Member to look up")
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    m = member or interaction.user
    roles  = [r.mention for r in reversed(m.roles) if r.name != "@everyone"]
    badges = []
    if m.public_flags.staff:           badges.append("👮 Discord Staff")
    if m.public_flags.partner:         badges.append("🤝 Partner")
    if m.public_flags.bug_hunter:      badges.append("🐛 Bug Hunter")
    if m.public_flags.early_supporter: badges.append("⭐ Early Supporter")
    if m.bot:                          badges.append("🤖 Bot")
    warns = len(warnings_db.get(str(interaction.guild.id), {}).get(str(m.id), []))
    e = discord.Embed(
        title=f"{E['user']} User Information",
        color=m.color if m.color.value else C_BLUE,
    )
    e.set_thumbnail(url=m.display_avatar.url)
    e.set_author(name=str(m), icon_url=m.display_avatar.url)
    e.add_field(name="🏷️ Username",       value=f"`{m}`",                                  inline=True)
    e.add_field(name="🆔 User ID",         value=f"`{m.id}`",                               inline=True)
    e.add_field(name="✏️ Nickname",        value=m.nick or "None",                          inline=True)
    e.add_field(name="📅 Account Created", value=f"<t:{int(m.created_at.timestamp())}:R>",  inline=True)
    e.add_field(name="📥 Joined Server",   value=f"<t:{int(m.joined_at.timestamp())}:R>",   inline=True)
    e.add_field(name="👑 Top Role",        value=m.top_role.mention,                        inline=True)
    e.add_field(name=f"🎭 Roles ({len(roles)})", value=" ".join(roles[:10]) or "None",      inline=False)
    if badges:
        e.add_field(name="🏅 Badges", value="\n".join(badges), inline=False)
    e.add_field(name="⚠️ Warnings", value=str(warns), inline=True)
    e.set_footer(text=f"Requested by {interaction.user}")
    e.timestamp = datetime.datetime.utcnow()
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="serverinfo", description="Get info about the server")
async def serverinfo(interaction: discord.Interaction):
    g      = interaction.guild
    bots   = sum(1 for m in g.members if m.bot)
    humans = g.member_count - bots
    online = sum(1 for m in g.members if m.status != discord.Status.offline and not m.bot)
    e = discord.Embed(title=f"{E['server']} Server Information", color=C_BLUE)
    if g.icon:
        e.set_thumbnail(url=g.icon.url)
    if g.banner:
        e.set_image(url=g.banner.url)
    e.set_author(name=g.name, icon_url=g.icon.url if g.icon else None)
    e.add_field(name="🏠 Name",         value=g.name,                                                           inline=True)
    e.add_field(name="🆔 ID",           value=f"`{g.id}`",                                                       inline=True)
    e.add_field(name="👑 Owner",        value=g.owner.mention,                                                   inline=True)
    e.add_field(name="👥 Members",      value=f"👤 {humans} humans\n🤖 {bots} bots",                             inline=True)
    e.add_field(name="🟢 Online",       value=str(online),                                                       inline=True)
    e.add_field(name="💬 Channels",     value=f"💬 {len(g.text_channels)} text\n🔊 {len(g.voice_channels)} voice", inline=True)
    e.add_field(name="🎭 Roles",        value=str(len(g.roles)),                                                 inline=True)
    e.add_field(name="😀 Emojis",       value=str(len(g.emojis)),                                                inline=True)
    e.add_field(name="💎 Boosts",       value=f"Level {g.premium_tier} ({g.premium_subscription_count})",        inline=True)
    e.add_field(name="📅 Created",      value=f"<t:{int(g.created_at.timestamp())}:R>",                          inline=True)
    e.add_field(name="🔒 Verification", value=str(g.verification_level).title(),                                 inline=True)
    e.set_footer(text=f"Requested by {interaction.user}")
    e.timestamp = datetime.datetime.utcnow()
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

@bot.tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    quality = ("🟢 Excellent" if latency < 100
                else "🟡 Good" if latency < 200
                else "🔴 High")
    await interaction.response.send_message(embed=embed_info(
        f"{E['ping']} Pong!",
        f"**Latency:** `{latency}ms`\n**Status:** {quality}",
        color=C_BLUE,
    ))

@bot.tree.command(name="say", description="Make the bot send a message")
@app_commands.describe(message="Message content", channel="Channel to send to")
async def say(interaction: discord.Interaction, message: str,
              channel: discord.TextChannel = None):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message(
            embed=no_perm("Manage Messages"), ephemeral=True)
    target = channel or interaction.channel
    await target.send(message)
    await interaction.response.send_message(
        embed=embed_success("Message Sent", f"Sent to {target.mention}."), ephemeral=True)

@bot.tree.command(name="embed", description="Send a custom embed message")
@app_commands.describe(title="Embed title", description="Embed description",
                       color="Hex color e.g. ff0000", channel="Channel to send to")
async def embed_cmd(interaction: discord.Interaction, title: str, description: str,
                    color: str = "5865f2", channel: discord.TextChannel = None):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message(
            embed=no_perm("Manage Messages"), ephemeral=True)
    try:
        col = int(color.replace("#", ""), 16)
    except Exception:
        col = C_BLUE
    target = channel or interaction.channel
    e = discord.Embed(title=title, description=description, color=col)
    e.set_footer(text=f"Sent by {interaction.user}")
    e.timestamp = datetime.datetime.utcnow()
    await target.send(embed=e)
    await interaction.response.send_message(
        embed=embed_success("Embed Sent", f"Sent to {target.mention}."), ephemeral=True)

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

@bot.tree.command(name="help", description="View all available commands")
async def help_cmd(interaction: discord.Interaction):
    e = discord.Embed(
        title=f"{E['bot']} Command List",
        description="All commands use `/` — type `/` in chat to see them all.",
        color=C_BLUE,
    )
    e.set_thumbnail(url=bot.user.display_avatar.url)
    e.add_field(name="🔨 Moderation", value=(
        "`/ban` `/unban` `/kick`\n"
        "`/timeout` `/untimeout`\n"
        "`/warn` `/warnings` `/clearwarnings`\n"
        "`/purge` `/slowmode`\n"
        "`/lock` `/unlock`\n"
        "`/lockdown` `/endlockdown`\n"
        "`/nick` `/role`"
    ), inline=True)
    e.add_field(name="🛠️ Utility", value=(
        "`/userinfo` `/serverinfo`\n"
        "`/avatar` `/ping`\n"
        "`/say` `/embed` `/poll`"
    ), inline=True)
    e.add_field(name="⚡ AutoMod", value=(
        "• Anti-spam (auto timeout + warn)\n"
        "• Welcome messages\n"
        "• Leave logging\n"
        "• Full mod action logging"
    ), inline=False)
    e.set_footer(text="TSR Bot • Made with ❤️")
    e.timestamp = datetime.datetime.utcnow()
    await interaction.response.send_message(embed=e, ephemeral=True)

# ╔══════════════════════════════════════════════════════════╗
# ║                          RUN                             ║
# ╚══════════════════════════════════════════════════════════╝
bot.run(BOT_TOKEN)
