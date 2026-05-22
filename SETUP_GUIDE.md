# TSR Advanced Discord Bot — Setup Guide

## Quick-Start Checklist

1. [Invite the bot](#1-invite-the-bot)
2. [Host on Railway](#2-host-on-railway)
3. [First commands (in Discord)](#3-first-commands-run-these-in-order)
4. [Command permissions — who can use what](#4-command-permissions-system)
5. [Features reference](#5-feature-setup-reference)

---

## 1. Invite the Bot

Create a Discord application at https://discord.com/developers/applications

**Required bot permissions (tick these when generating the invite link):**

| Permission             | Why                                 |
|------------------------|-------------------------------------|
| Administrator          | Needed for full moderation features |
| *(or individually:)*   |                                     |
| Manage Channels        | Lock / unlock / tickets             |
| Manage Roles           | Verification, massrole              |
| Manage Messages        | Purge, automod                      |
| Ban Members            | Ban, hardban, tempban               |
| Kick Members           | Kick                                |
| Moderate Members       | Timeout                             |
| View Audit Log         | Anti-nuke detection                 |
| Manage Nicknames       | Nick command                        |
| Send Messages          | Posting embeds                      |
| Embed Links            | All embeds                          |
| Attach Files           | Transcripts                         |
| Read Message History   | Purge, snipe, transcripts           |
| Add Reactions          | Poll, verify (reaction method)      |
| Manage Webhooks        | Anti-nuke webhook detection         |

**Bot intents required (Discord Developer Portal → Bot tab):**
- [x] SERVER MEMBERS INTENT
- [x] MESSAGE CONTENT INTENT
- [x] PRESENCE INTENT

---

## 2. Host on Railway

1. Push your bot folder to a GitHub repository (or upload directly to Railway)
2. On Railway, create a **New Project → Deploy from GitHub repo**
3. In **Variables**, add:

| Variable     | Value                        | Required |
|--------------|------------------------------|----------|
| `BOT_TOKEN`  | Your bot token from Discord  | ✅        |
| `OWNER_IDS`  | Your Discord User ID(s), comma-separated | Optional |

4. Railway auto-detects Python. Add a `Procfile` with:
   ```
   worker: python bot.py
   ```
   Or set the **Start Command** in Railway settings to `python bot.py`

5. The bot stores all data in a `data/` folder inside the container.
   > ⚠️ **Important:** Railway volumes are ephemeral on free plans. For persistent data, use a Railway Volume or store the `data/` folder in a mounted volume.

---

## 3. First Commands (run these in order)

Run all of these in a **private admin channel** in your Discord server.

```
/setuplog channel:#your-log-channel
```
> Everything the bot does gets logged here: bans, kicks, message deletes, edits, joins, leaves, anti-nuke alerts, automod actions, voice changes — all of it.

```
/setupwelcome channel:#welcome
/setupgoodbye channel:#general
```

```
/setupverify channel:#verify role:@Verified method:button min_age_days:3
```
> `min_age_days:3` means accounts less than 3 days old cannot verify. Set to 0 to allow any age.
> Methods: `button` (instant click), `math` (solve a math problem in DMs), `code` (DM code), `reaction` (react with ✅)

```
/setuptickets channel:#support category:Support support_role:@Staff transcript_channel:#ticket-logs
```

```
/setupmodmail channel:#modmail-threads
```

```
/setupantinuke enabled:True action:strip bans:3 kicks:5 channels:3 roles:3 window:10
```

```
/setupautomod links:True caps:True caps_percent:80
```

---

## 4. Command Permissions System

### How it works

The bot has **4 command groups**:

| Group          | Commands in it                                                        |
|----------------|-----------------------------------------------------------------------|
| `moderation`   | ban, kick, timeout, warn, purge, lock, unlock, role, nick, etc.       |
| `utility`      | userinfo, serverinfo, avatar, ping, say, embed, announce, poll, etc.  |
| `community`    | rank, leaderboard, suggest, afk, remind, 8ball, coinflip, roll, etc.  |
| `setup`        | All /setup* commands, setpermission, viewpermissions, help            |

**Default behaviour (no config needed):**
- `moderation` and `setup` — only users with the matching Discord permission can see and use these (e.g. `/ban` requires "Ban Members" in Discord). Normal members can't even see them.
- `utility` and `community` — available to everyone by default.

**Using `/setpermission` restricts a group to specific roles only.**
Once you configure a group, ONLY those roles (plus admins) can use it.

---

### Example: Members role can use /leaderboard, /rank, /suggest — but NOT /ban or /kick

**Step 1** — Make sure you have a `@Member` role (or whatever your verified member role is called).

**Step 2** — Grant the `community` group to `@Member`:
```
/setpermission group:community role:@Member
```
Now only `@Member` (and admins) can use `/rank`, `/leaderboard`, `/suggest`, `/afk`, `/remind`, `/8ball`, `/coinflip`, `/roll`, `/choose`, `/giveaway`, `/verify`.

Unverified users who don't have `@Member` will see the ❌ permission denied embed.

**Step 3** — Optionally restrict `utility` too:
```
/setpermission group:utility role:@Member
```
Now `/userinfo`, `/serverinfo`, `/avatar`, `/ping`, `/poll` etc. also require `@Member`.

**Step 4** — Check what's configured:
```
/viewpermissions
```

---

### More examples

**Multiple roles can use a group** — run `/setpermission` twice:
```
/setpermission group:community role:@Member
/setpermission group:community role:@Verified
```
Both roles now have access.

**Override a single command** (e.g. only `@Giveaway Manager` can use `/giveaway`):
```
/setpermission group:community command:giveaway role:@GiveawayManager
```

**Remove access from a role** — run the same command again to toggle off:
```
/setpermission group:community role:@Member
```
Running it again removes `@Member` from the group.

**Restrict `/announce` to only `@Admin`:**
```
/setpermission group:utility command:announce role:@Admin
```

---

### What normal members CAN'T do (this is automatic, no config needed)

These commands require Discord permissions that normal members don't have.
Even if you never run `/setpermission`, these are always protected:

| Command          | Requires Discord Permission  |
|------------------|------------------------------|
| `/ban`           | Ban Members                  |
| `/kick`          | Kick Members                 |
| `/timeout`       | Moderate Members             |
| `/warn`          | Manage Messages              |
| `/purge`         | Manage Messages              |
| `/lock` `/unlock`| Manage Channels              |
| `/role`          | Manage Roles                 |
| `/hardban`       | Administrator                |
| `/setuplog` etc. | Administrator                |
| `/setupantinuke` | Administrator                |

Normal members simply can't see these commands in the slash menu.

---

## 5. Feature Setup Reference

### 🎵 Music (Spotify-style)

The bot plays audio from **YouTube** but accepts **Spotify links** to look up the track/playlist/album name.  
No Spotify Premium required — the Spotify API (free) is only used to read track metadata.

#### Step 1 — Get free Spotify API credentials (2 minutes)

1. Go to **https://developer.spotify.com/dashboard**
2. Log in with your free Spotify account
3. Click **Create App** → give it any name/description → check "Web API" → Save
4. Click **Settings** → copy your **Client ID** and **Client Secret**

#### Step 2 — Add environment variables on Railway

In your Railway project → **Variables** tab, add:
```
SPOTIFY_CLIENT_ID     = (your Client ID)
SPOTIFY_CLIENT_SECRET = (your Client Secret)
```

> **Without these vars**, the bot still works — `/play` accepts YouTube URLs and song name searches. Only Spotify links won't resolve.

#### Commands

| Command | Description |
|---------|-------------|
| `/play Blinding Lights` | Search and play by name |
| `/play https://open.spotify.com/track/...` | Play a Spotify track |
| `/play https://open.spotify.com/playlist/...` | Queue a Spotify playlist (up to 50 tracks) |
| `/play https://open.spotify.com/album/...` | Queue a full Spotify album |
| `/play https://youtu.be/...` | Play a YouTube video directly |
| `/pause` | Pause current track |
| `/resume` | Resume paused track |
| `/skip` | Skip to next track |
| `/skip count:3` | Skip the next 3 tracks |
| `/stop` | Stop and clear queue |
| `/queue` | Show the current queue + total time |
| `/nowplaying` | Show the current track card |
| `/search query:song name` | See top 5 YouTube results before playing |
| `/volume level:80` | Set volume 0–200% (default 100) |
| `/loop` | Toggle loop on current track |
| `/shuffle` | Shuffle the queue |
| `/disconnect` | Leave voice + clear queue |

#### Permission setup (optional)
By default everyone can use music. To restrict it:
```
/setpermission group:music role:@DJ
```

#### Railway / FFmpeg note
The included `nixpacks.toml` already installs FFmpeg automatically on Railway. No extra steps needed.

---

### Anti-Nuke (v4 — improved embeds + @everyone protection)
```
/setupantinuke enabled:True action:strip bans:3 kicks:5 channels:3 roles:3 window:10
/setupantinuke action:strip+ban anti_everyone:True
```
- **action** — `strip` (remove all roles), `strip+ban` (roles + permanent ban), `kick`, or `ban`
- **anti_everyone** — trigger anti-nuke when a member without permission uses @everyone or @here
- **bans/kicks/channels/roles** — how many actions within `window` seconds trigger it
- **whitelist_role** — run again to toggle a role as immune (admins are always immune)
- Embed format matches screenshot: Event Type / Mode / Action / Executor / Reason / Guild ID

---

### Honeypot Channels (NEW in v4)
Honeypot channels catch raid bots and ban evaders — anyone who types gets actioned instantly.

```
/setuphoneypot channel:#hidden-channel action:softban
/setuphoneypot channel:#another-trap action:ban log:True
```
- **channel** — toggles the channel as a honeypot (run again to remove)
- **action** — `softban` (ban + unban, clears messages), `ban`, `kick`, or `timeout`
- **log** — whether to log triggers to the log channel (default: on)

**Tip:** Create a channel visible to @everyone but hidden from mods. Give it a name like `#rules-old` or `#free-nitro`. Raid bots will find it first.

---

### Stats Channels (NEW in v4)
Voice channels that automatically update their name to show server statistics.

```
/setupstatschannels members_channel:"Members: ?" online_channel:"Online: ?" bots_channel:"Bots: ?" channels_channel:"Channels: ?" roles_channel:"Roles: ?"
```
- Pass the voice channel objects for any/all stats you want
- Channel names update every **10 minutes** (Discord rate-limits channel renames)
- **Tip:** Create locked voice channels (deny Connect for @everyone) and position them at the top

---

### Invite Tracking (NEW in v4)
The bot automatically tracks which invite was used when each member joins.

**No setup required** — invite tracking is automatic once the bot has the `Manage Server` permission.

View invite data:
```
/inviteleaderboard       — top 15 inviters with medal ranks
/inviteinfo              — your own invite stats
/inviteinfo member:@User — another member's invite stats
```
Invite info is also shown in:
- The **welcome message** (if a welcome channel is set)
- The **member join log** (log channel)

---

### AutoMod (v4 — expanded)
```
/setupautomod links:True caps:True caps_percent:80 caps_min_length:10
/setupautomod invites:True mentions:True mentions_limit:5
/setupautomod emojis:True emojis_limit:10
/setupautomod zalgo:True repeated_chars:True repeated_limit:8
```
```
/badword word:badword1 action:add
/badword word:badword1 action:remove
/filterlist
```
```
/setupautomod exempt_role:@Staff
```

| Filter | What it catches |
|--------|-----------------|
| `links` | Any http/https/www URL |
| `invites` | discord.gg invite links |
| `caps` | Messages with % uppercase above threshold |
| `mentions` | Too many @user or @role mentions in one message |
| `emojis` | Emoji spam (Unicode + custom Discord emojis) |
| `zalgo` | Corrupted/zalgo text (Unicode combining characters) |
| `repeated_chars` | Long runs of the same character (aaaaaaa, !!!!!!) |

---

### Roblox Watcher (v4 — future + live detection)
```
/setuproblox channel:#roblox-updates live_ping_role:@RobloxUpdates future_ping_role:@RobloxFuture
```
- **channel** — where updates are posted
- **live_ping_role** — role pinged when Player version changes (live update, all players must update)
- **future_ping_role** — role pinged when Studio is ahead of Player (update is coming, not live yet)

**How detection works:**

| Type | Trigger | Embed color | What it means |
|------|---------|-------------|---------------|
| 🟡 Future | Studio version ≠ Player version | Yellow | Update staged, not deployed yet |
| 🔴 Live | Player version changed | Red | Roblox client is updating now |

Each embed includes: **Platform**, **Version Hash**, **Date/Time**, and a direct **Download link**.

Checks run every **3 minutes**. The first `/setuproblox` seeds the current versions so no false alerts fire on startup.

---

### Verification Methods

| Method     | How it works                                           | Security level |
|------------|--------------------------------------------------------|----------------|
| `button`   | Click a button → instant role                         | Low            |
| `reaction` | React with ✅ → instant role                          | Low            |
| `code`     | Click button → receive 8-char code in DMs → `/verify` | Medium         |
| `math`     | Click button → solve a DM math problem → `/verify`    | High           |

Add extra gates:
```
/setupverify channel:#verify role:@Verified method:math min_age_days:7 require_phone:True
```

---

### Tickets
```
/setuptickets channel:#open-ticket category:Tickets support_role:@Support transcript_channel:#ticket-logs
```
- Transcripts are automatically saved when a ticket is closed
- Staff can close with `/closeticket reason:Resolved` or the Close button

---

### ModMail
```
/setupmodmail channel:#modmail-inbox
```
- Members DM the bot → private channel is created
- Staff reply in the channel → member receives as DM
- `/mmclose reason:Resolved` — saves transcript and closes

---

### Giveaways
```
/giveaway prize:Nitro duration:24h winners:1
```
- `/greroll message_id:12345` — reroll a winner (right-click the giveaway → Copy Message ID)
- `/gend message_id:12345` — end early and pick winner now

---

### Lock / Unlock

**Basic (no setup needed):**
```
/lock reason:Raid incoming
/unlock
```

**Configure which permission gets denied (run once):**
```
/setuplock permission:send_messages exempt_role:@Staff
```
Exempt roles keep sending access even when the channel is locked.

**Emergency full server lockdown:**
```
/lockdown reason:Active raid
/endlockdown
```

---

### Roblox Update Watcher
```
/setuproblox channel:#roblox-updates
```
Checks every 5 minutes. Posts an embed whenever a new Roblox client version is detected.

---

## Recommended Role Setup

```
@Admin       — has Administrator permission in Discord
@Moderator   — has Ban Members, Kick Members, Manage Messages, Moderate Members
@Staff       — has Manage Messages, Manage Channels
@Member      — your base verified member role
@Verified    — set as the /setupverify role, granted on verification
```

Then run:
```
/setpermission group:community role:@Member
/setpermission group:utility   role:@Member
```

This means:
- **Everyone** can see `/help`, `/verify`
- **@Member and above** can use community + utility commands
- **@Staff and above** (via Discord permissions) can use moderation commands
- **@Admin only** can run setup commands

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `/lock` says "Interaction failed" | Make sure the bot has **Manage Channels** permission and its role is **higher** than @everyone in the role list |
| `/purge` deletes nothing | Messages older than 14 days can't be bulk-deleted (Discord limitation). Bot needs **Manage Messages** in that channel. |
| Commands not showing up | Wait ~1 hour for slash commands to propagate, or kick and re-invite the bot |
| Anti-nuke not working | Run `/setupantinuke enabled:True` — it starts disabled. Bot needs **View Audit Log** permission. |
| Verification not working | Check the bot has **Manage Roles** and its role is **above** the verify role in Server Settings → Roles |
| Logs not showing | Run `/setuplog channel:#your-log-channel` first |
| ModMail threads not creating | Bot needs **Manage Channels** in the category |
