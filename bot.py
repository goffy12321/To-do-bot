import os
import asyncio
import discord
from discord.ext import commands
from db import Database

# Einstellungen aus ENV
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
DB_PATH = os.getenv("DB_PATH", "data/todo.db")

if not DISCORD_TOKEN:
   raise RuntimeError("DISCORD_TOKEN must be set in environment (see .env.example)")
if not GUILD_ID:
   raise RuntimeError("GUILD_ID must be set in environment (bot is restricted to a single server)")
GUILD_ID = int(GUILD_ID)

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Status-Emoji mapping
STATUS_EMOJIS = {
   "pending": "❌",       # Ausständig
   "in_progress": "🔵",   # In Bearbeitung
   "done": "✅"           # Erledigt
}

def guild_only():
   async def predicate(ctx):
       if ctx.guild is None:
           await ctx.send("Dieser Bot funktioniert nur auf dem konfigurierten Server.")
           return False
       if ctx.guild.id != GUILD_ID:
           await ctx.send("Dieser Bot ist auf einen bestimmten Server beschränkt.")
           return False
       return True
   return commands.check(predicate)

@bot.event
async def on_ready():
   print(f"Bot ist online als {bot.user} (ID: {bot.user.id})")
   bot.db = Database(DB_PATH)
   await bot.db.initialize()
   print("Datenbank initialisiert")

# Hauptgruppe
@bot.group(name="todo", invoke_without_command=True)
@guild_only()
async def todo(ctx):
   help_text = (
       "ToDo-Bot Befehle (Präfix: !):\n\n"
       "Listen:\n"
       "!todo list create <name>\n"
       "!todo list rename <oldname> <newname>\n"
       "!todo list delete <name>\n"
       "!todo list show <name>\n"
       "!todo lists\n\n"
       "Items:\n"
       "!todo item add <list> <name> [| <priority>]   (wenn priority weggelassen wird, hängt es ans Ende)\n"
       "!todo item rename <list> <item-id> <new-name>\n"
       "!todo item set-priority <list> <item-id> <priority>\n"
       "!todo item set-status <list> <item-id> <pending|in_progress|done>\n"
       "!todo item delete <list> <item-id>\n\n"
       "Hinweis: Listennamen sollten als ein Wort ohne Leerzeichen genutzt werden (z.B. MyList). "
       "Item-Namen können Leerzeichen enthalten. Für die Priorität beim Hinzufügen: "
       "Benutze `Task name | 2` (Priority 2)."
   )
   await ctx.send(f"```{help_text}```")

# LIST Gruppe
@todo.group(name="list", invoke_without_command=True)
@guild_only()
async def _list(ctx):
   await ctx.send("Benutze `!todo` für Hilfe zu List-Befehlen.")

@_list.command(name="create")
@guild_only()
async def list_create(ctx, name: str):
   channel_id = ctx.channel.id
   existing = await bot.db.get_list_by_name(channel_id, name)
   if existing:
       await ctx.send(f"Eine Liste mit dem Namen `{name}` existiert bereits in diesem Kanal.")
       return
   list_id = await bot.db.create_list(ctx.guild.id, channel_id, name)
   await ctx.send(f"Liste `{name}` erstellt (ID: {list_id}).")

@_list.command(name="rename")
@guild_only()
async def list_rename(ctx, old_name: str, new_name: str):
   channel_id = ctx.channel.id
   ok = await bot.db.rename_list(channel_id, old_name, new_name)
   if ok:
       await ctx.send(f"Liste `{old_name}` wurde in `{new_name}` umbenannt.")
   else:
       await ctx.send(f"Liste `{old_name}` wurde nicht gefunden in diesem Kanal.")

@_list.command(name="delete")
@guild_only()
async def list_delete(ctx, name: str):
   channel_id = ctx.channel.id
   ok = await bot.db.delete_list(channel_id, name)
   if ok:
       await ctx.send(f"Liste `{name}` und ihre Items wurden gelöscht.")
   else:
       await ctx.send(f"Liste `{name}` wurde nicht gefunden in diesem Kanal.")

@_list.command(name="show")
@guild_only()
async def list_show(ctx, name: str):
   channel_id = ctx.channel.id
   lst = await bot.db.get_list_by_name(channel_id, name)
   if not lst:
       await ctx.send(f"Liste `{name}` wurde nicht gefunden.")
       return
   items = await bot.db.get_items(lst["id"])
   embed = discord.Embed(title=f"ToDo-Liste: {lst['name']}", color=discord.Color.blue())
   embed.set_footer(text=f"Liste ID: {lst['id']} • Kanal: {ctx.channel.name}")
   if not items:
       embed.description = "Keine Einträge."
       await ctx.send(embed=embed)
       return
   lines = []
   for it in items:
       emoji = STATUS_EMOJIS.get(it["status"], "?")
       lines.append(f"{it['id']}. {emoji} **{it['name']}** (Priority: {it['priority']})")
   # Split in Felder falls nötig
   MAX_FIELD = 1024
   cur = ""
   idx = 1
   for line in lines:
       if len(cur) + len(line) + 1 > MAX_FIELD:
           embed.add_field(name=f"Items ({idx})", value=cur or "—", inline=False)
           cur = line + "\n"
           idx += 1
       else:
           cur += line + "\n"
   if cur:
       embed.add_field(name=f"Items ({idx})", value=cur, inline=False)
   await ctx.send(embed=embed)

@todo.command(name="lists")
@guild_only()
async def lists_show(ctx):
   channel_id = ctx.channel.id
   lists = await bot.db.get_lists_for_channel(channel_id)
   if not lists:
       await ctx.send("Keine Listen in diesem Kanal.")
       return
   lines = []
   for l in lists:
       count = await bot.db.count_items(l["id"])
       lines.append(f"- `{l['name']}` (ID: {l['id']}) — {count} Items")
   await ctx.send("Listen in diesem Kanal:\n" + "\n".join(lines))

# ITEM Gruppe
@todo.group(name="item", invoke_without_command=True)
@guild_only()
async def item_group(ctx):
   await ctx.send("Benutze `!todo` für Hilfe zu Item-Befehlen.")

@item_group.command(name="add")
@guild_only()
async def item_add(ctx, list_name: str, *, rest: str):
   """
   Usage:
   !todo item add <list> <name> [| <priority>]
   Beispiel:
   !todo item add MyList Erledige Bericht | 2
   """
   channel_id = ctx.channel.id
   lst = await bot.db.get_list_by_name(channel_id, list_name)
   if not lst:
       await ctx.send(f"Liste `{list_name}` nicht gefunden in diesem Kanal.")
       return
   # Parse optional priority separator "|"
   name = rest.strip()
   priority = None
   if "|" in rest:
       parts = rest.rsplit("|", 1)
       name = parts[0].strip()
       try:
           priority = int(parts[1].strip())
       except ValueError:
           priority = None
   if priority is None:
       priority = (await bot.db.get_max_priority(lst["id"])) + 1
   item_id = await bot.db.add_item(lst["id"], name, priority, "pending")
   await ctx.send(f"Item `{name}` hinzugefügt mit Priority {priority} (ID: {item_id}).")

@item_group.command(name="rename")
@guild_only()
async def item_rename(ctx, list_name: str, item_id: int, *, new_name: str):
   channel_id = ctx.channel.id
   lst = await bot.db.get_list_by_name(channel_id, list_name)
   if not lst:
       await ctx.send(f"Liste `{list_name}` nicht gefunden.")
       return
   ok = await bot.db.rename_item(lst["id"], item_id, new_name)
   if ok:
       await ctx.send(f"Item {item_id} umbenannt zu `{new_name}`.")
   else:
       await ctx.send(f"Item {item_id} nicht gefunden in Liste `{list_name}`.")

@item_group.command(name="set-priority")
@guild_only()
async def item_set_priority(ctx, list_name: str, item_id: int, priority: int):
   channel_id = ctx.channel.id
   lst = await bot.db.get_list_by_name(channel_id, list_name)
   if not lst:
       await ctx.send(f"Liste `{list_name}` nicht gefunden.")
       return
   ok = await bot.db.set_item_priority(lst["id"], item_id, priority)
   if ok:
       await ctx.send(f"Priority von Item {item_id} auf {priority} gesetzt.")
   else:
       await ctx.send(f"Item {item_id} nicht gefunden in Liste `{list_name}`.")

@item_group.command(name="set-status")
@guild_only()
async def item_set_status(ctx, list_name: str, item_id: int, status: str):
   channel_id = ctx.channel.id
   status = status.lower()
   if status not in ("pending", "in_progress", "done"):
       await ctx.send("Status ungültig. Nutze: pending, in_progress, done")
       return
   lst = await bot.db.get_list_by_name(channel_id, list_name)
   if not lst:
       await ctx.send(f"Liste `{list_name}` nicht gefunden.")
       return
   ok = await bot.db.set_item_status(lst["id"], item_id, status)
   if ok:
       await ctx.send(f"Status von Item {item_id} gesetzt auf {status} {STATUS_EMOJIS[status]}")
   else:
       await ctx.send(f"Item {item_id} nicht gefunden in Liste `{list_name}`.")

@item_group.command(name="delete")
@guild_only()
async def item_delete(ctx, list_name: str, item_id: int):
   channel_id = ctx.channel.id
   lst = await bot.db.get_list_by_name(channel_id, list_name)
   if not lst:
       await ctx.send(f"Liste `{list_name}` nicht gefunden.")
       return
   ok = await bot.db.delete_item(lst["id"], item_id)
   if ok:
       await ctx.send(f"Item {item_id} gelöscht.")
   else:
       await ctx.send(f"Item {item_id} nicht gefunden in Liste `{list_name}`.")

@bot.command(name="help")
async def help_cmd(ctx):
   await todo(ctx)

if __name__ == "__main__":
   bot.run(DISCORD_TOKEN)