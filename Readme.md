ToDo Discord Bot (Python, discord.py)

Kurzanleitung:
1. Erstelle eine .env Datei basierend auf .env.example und setze DISCORD_TOKEN und GUILD_ID.
2. Baue und starte lokal:
  - Ohne Docker: pip install -r requirements.txt && python bot.py
  - Mit Docker:
      docker build -t todo-bot .
      docker run --env-file .env -v $(pwd)/data:/app/data todo-bot

Beschreibung:
- Der Bot verwendet das Präfix `!todo`.
- Listen sind pro Kanal (nur Kanal-Mitglieder sehen/bearbeiten Listen dieses Kanals).
- Prioritäten sind numerisch und eindeutig; beim Einfügen/Ändern werden vorhandene Prioritäten automatisch verschoben.
- Status: pending (❌), in_progress (🔵), done (✅)

Wichtige Kommandos:
- !todo list create <name>
- !todo list rename <oldname> <newname>
- !todo list delete <name>
- !todo list show <name>
- !todo lists

- !todo item add <list> <name> [| <priority>]
- !todo item rename <list> <item-id> <new-name>
- !todo item set-priority <list> <item-id> <priority>
- !todo item set-status <list> <item-id> <pending|in_progress|done>
- !todo item delete <list> <item-id>

Hinweis:
- Verwende für Listennamen am besten keine Leerzeichen (z.B. MyList). Item-Namen können Leerzeichen enthalten.