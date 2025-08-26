import aiosqlite
import os
import datetime

class Database:
   def __init__(self, path="data/todo.db"):
       self.path = path
       os.makedirs(os.path.dirname(self.path), exist_ok=True)
       self._conn = None

   async def initialize(self):
       self._conn = await aiosqlite.connect(self.path)
       # Enable Row access by name
       self._conn.row_factory = aiosqlite.Row
       await self._conn.execute("PRAGMA foreign_keys = ON;")
       await self._conn.execute("""
       CREATE TABLE IF NOT EXISTS lists (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           guild_id INTEGER NOT NULL,
           channel_id INTEGER NOT NULL,
           name TEXT NOT NULL,
           created_at TEXT NOT NULL
       );
       """)
       await self._conn.execute("""
       CREATE TABLE IF NOT EXISTS items (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           list_id INTEGER NOT NULL,
           name TEXT NOT NULL,
           priority INTEGER NOT NULL,
           status TEXT NOT NULL,
           created_at TEXT NOT NULL,
           FOREIGN KEY(list_id) REFERENCES lists(id) ON DELETE CASCADE
       );
       """)
       await self._conn.commit()

   # -------------------------
   # LIST FUNCTIONS
   # -------------------------
   async def create_list(self, guild_id, channel_id, name):
       cur = await self._conn.execute(
           "INSERT INTO lists (guild_id, channel_id, name, created_at) VALUES (?, ?, ?, ?)",
           (guild_id, channel_id, name, datetime.datetime.utcnow().isoformat())
       )
       await self._conn.commit()
       return cur.lastrowid

   async def get_list_by_name(self, channel_id, name):
       cur = await self._conn.execute(
           "SELECT id, guild_id, channel_id, name, created_at FROM lists WHERE channel_id = ? AND name = ?",
           (channel_id, name)
       )
       row = await cur.fetchone()
       if not row:
           return None
       return dict(row)

   async def rename_list(self, channel_id, old_name, new_name):
       cur = await self._conn.execute(
           "UPDATE lists SET name = ? WHERE channel_id = ? AND name = ?",
           (new_name, channel_id, old_name)
       )
       await self._conn.commit()
       return cur.rowcount > 0

   async def delete_list(self, channel_id, name):
       lst = await self.get_list_by_name(channel_id, name)
       if not lst:
           return False
       await self._conn.execute("DELETE FROM items WHERE list_id = ?", (lst["id"],))
       await self._conn.execute("DELETE FROM lists WHERE id = ?", (lst["id"],))
       await self._conn.commit()
       return True

   async def get_lists_for_channel(self, channel_id):
       cur = await self._conn.execute(
           "SELECT id, guild_id, channel_id, name, created_at FROM lists WHERE channel_id = ? ORDER BY name",
           (channel_id,)
       )
       rows = await cur.fetchall()
       return [dict(r) for r in rows]

   # -------------------------
   # ITEM FUNCTIONS
   # -------------------------
   async def get_items(self, list_id):
       cur = await self._conn.execute(
           "SELECT id, list_id, name, priority, status, created_at FROM items WHERE list_id = ? ORDER BY priority ASC",
           (list_id,)
       )
       rows = await cur.fetchall()
       return [dict(r) for r in rows]

   async def count_items(self, list_id):
       cur = await self._conn.execute("SELECT COUNT(*) as cnt FROM items WHERE list_id = ?", (list_id,))
       row = await cur.fetchone()
       return row["cnt"] if row else 0

   async def get_max_priority(self, list_id):
       cur = await self._conn.execute("SELECT MAX(priority) as mx FROM items WHERE list_id = ?", (list_id,))
       row = await cur.fetchone()
       return row["mx"] if row and row["mx"] is not None else 0

   async def add_item(self, list_id, name, priority, status="pending"):
       # Ensure priority is at least 1
       if priority < 1:
           priority = 1
       # Find current max to cap priority to max+1
       maxp = await self.get_max_priority(list_id)
       if priority > maxp + 1:
           priority = maxp + 1
       # Shift existing items with priority >= given priority down by +1
       await self._conn.execute(
           "UPDATE items SET priority = priority + 1 WHERE list_id = ? AND priority >= ?",
           (list_id, priority)
       )
       cur = await self._conn.execute(
           "INSERT INTO items (list_id, name, priority, status, created_at) VALUES (?, ?, ?, ?, ?)",
           (list_id, name, priority, status, datetime.datetime.utcnow().isoformat())
       )
       await self._conn.commit()
       return cur.lastrowid

   async def get_item(self, list_id, item_id):
       cur = await self._conn.execute(
           "SELECT id, list_id, name, priority, status, created_at FROM items WHERE list_id = ? AND id = ?",
           (list_id, item_id)
       )
       row = await cur.fetchone()
       return dict(row) if row else None

   async def rename_item(self, list_id, item_id, new_name):
       cur = await self._conn.execute(
           "UPDATE items SET name = ? WHERE list_id = ? AND id = ?",
           (new_name, list_id, item_id)
       )
       await self._conn.commit()
       return cur.rowcount > 0

   async def set_item_status(self, list_id, item_id, status):
       cur = await self._conn.execute(
           "UPDATE items SET status = ? WHERE list_id = ? AND id = ?",
           (status, list_id, item_id)
       )
       await self._conn.commit()
       return cur.rowcount > 0

   async def set_item_priority(self, list_id, item_id, new_priority):
       # Ensure positive integer
       if new_priority < 1:
           new_priority = 1
       item = await self.get_item(list_id, item_id)
       if not item:
           return False
       current = item["priority"]
       maxp = await self.get_max_priority(list_id)
       # Cap new_priority to maxp (moving to end allowed: maxp if not moving to append)
       if new_priority > maxp:
           new_priority = maxp
       if new_priority == current:
           return True

       # Moving up (to better priority, smaller number)
       if new_priority < current:
           # shift items with priority >= new_priority and < current up by +1 (push them down)
           await self._conn.execute(
               "UPDATE items SET priority = priority + 1 WHERE list_id = ? AND priority >= ? AND priority < ?",
               (list_id, new_priority, current)
           )
       else:
           # new_priority > current: move downwards: shift items with priority <= new_priority and > current down by -1
           await self._conn.execute(
               "UPDATE items SET priority = priority - 1 WHERE list_id = ? AND priority <= ? AND priority > ?",
               (list_id, new_priority, current)
           )
       # set item to new_priority
       await self._conn.execute(
           "UPDATE items SET priority = ? WHERE list_id = ? AND id = ?",
           (new_priority, list_id, item_id)
       )
       await self._conn.commit()
       return True

   async def delete_item(self, list_id, item_id):
       item = await self.get_item(list_id, item_id)
       if not item:
           return False
       priority = item["priority"]
       await self._conn.execute("DELETE FROM items WHERE list_id = ? AND id = ?", (list_id, item_id))
       # Shift items with priority > deleted priority up by -1 to close gap
       await self._conn.execute(
           "UPDATE items SET priority = priority - 1 WHERE list_id = ? AND priority > ?",
           (list_id, priority)
       )
       await self._conn.commit()
       return True

   async def close(self):
       if self._conn:
           await self._conn.close()
           self._conn = None