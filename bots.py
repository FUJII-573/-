import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import random
import os

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= DATABASE =================
conn = sqlite3.connect("data.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    points INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS box_config (
    item TEXT PRIMARY KEY,
    chance INTEGER
)
""")

conn.commit()

# ================= UTIL =================
def get_user(uid):
    cursor.execute("SELECT points FROM users WHERE id=?", (uid,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO users (id, points) VALUES (?, ?)", (uid, 0))
        conn.commit()
        return 0
    return row[0]

def add_points(uid, amount):
    get_user(uid)
    cursor.execute("UPDATE users SET points = points + ? WHERE id=?", (amount, uid))
    conn.commit()

def remove_points(uid, amount):
    get_user(uid)
    cursor.execute("UPDATE users SET points = points - ? WHERE id=?", (amount, uid))
    conn.commit()

# ================= EVENTS =================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

# ================= POINT COMMAND =================
@bot.tree.command(name="points")
async def points(interaction: discord.Interaction):
    pts = get_user(interaction.user.id)
    await interaction.response.send_message(f"คุณมี {pts} แต้ม")

# ================= ADD POINT =================
@bot.tree.command(name="addpoints")
async def addpoints(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin เท่านั้น", ephemeral=True)

    add_points(member.id, amount)
    await interaction.response.send_message(f"✅ เพิ่ม {amount} แต้มให้ {member.display_name}")

# ================= REMOVE POINT =================
@bot.tree.command(name="removepoints")
async def removepoints(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin เท่านั้น", ephemeral=True)

    remove_points(member.id, amount)
    await interaction.response.send_message(f"✅ ลบ {amount} แต้มจาก {member.display_name}")

# ================= BOX CONFIG =================
class BoxConfigView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.item = None
        self.chance = None

    @discord.ui.select(placeholder="เลือกไอเท็ม")
    async def select_item(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.item = select.values[0]
        await interaction.response.send_message(f"เลือก {self.item}", ephemeral=True)

    @discord.ui.button(label="ตั้ง %", style=discord.ButtonStyle.primary)
    async def set_percent(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BoxModal(self))

    @discord.ui.button(label="บันทึก", style=discord.ButtonStyle.green)
    async def save(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not self.item or self.chance is None:
            return await interaction.response.send_message("❌ ยังตั้งค่าไม่ครบ", ephemeral=True)

        cursor.execute("""
        INSERT INTO box_config (item, chance)
        VALUES (?, ?)
        ON CONFLICT(item) DO UPDATE SET chance=excluded.chance
        """, (self.item, self.chance))

        conn.commit()

        await interaction.response.send_message("✅ บันทึกแล้ว", ephemeral=True)


class BoxModal(discord.ui.Modal, title="ตั้ง %"):
    percent = discord.ui.TextInput(label="เปอร์เซ็นต์")

    def __init__(self, view):
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.chance = int(self.percent.value)
        await interaction.response.send_message("✅ ตั้งค่าเปอร์เซ็นต์แล้ว", ephemeral=True)

@bot.tree.command(name="boxconfig")
async def boxconfig(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin เท่านั้น", ephemeral=True)

    cursor.execute("SELECT item FROM box_config")
    items = cursor.fetchall()

    if not items:
        return await interaction.response.send_message("❌ ยังไม่มีไอเท็ม ใช้ /addboxitem", ephemeral=True)

    view = BoxConfigView()

    options = [discord.SelectOption(label=i[0], value=i[0]) for i in items]
    view.children[0].options = options[:25]

    await interaction.response.send_message("⚙️ ตั้งค่ากล่อง", view=view, ephemeral=True)

# ================= ADD ITEM =================
@bot.tree.command(name="addboxitem")
async def addboxitem(interaction: discord.Interaction, item: str):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin เท่านั้น", ephemeral=True)

    cursor.execute("INSERT OR IGNORE INTO box_config (item, chance) VALUES (?, ?)", (item, 0))
    conn.commit()

    await interaction.response.send_message(f"✅ เพิ่มไอเท็ม: {item}")

# ================= OPEN BOX =================
@bot.tree.command(name="box")
async def box(interaction: discord.Interaction):
    cursor.execute("SELECT item, chance FROM box_config")
    items = cursor.fetchall()

    if not items:
        return await interaction.response.send_message("❌ กล่องยังไม่มีไอเท็ม")

    choices = []
    for item, chance in items:
        choices.extend([item] * max(chance, 1))

    reward = random.choice(choices)

    await interaction.response.send_message(f"🎁 คุณได้: {reward}")

# ================= LEADERBOARD =================
@bot.tree.command(name="leaderboard")
async def leaderboard(interaction: discord.Interaction):
    cursor.execute("SELECT id, points FROM users ORDER BY points DESC LIMIT 10")
    rows = cursor.fetchall()

    embed = discord.Embed(
        title="🏆 Leaderboard",
        color=0xFFD700
    )

    medals = ["🥇", "🥈", "🥉"]

    for i, (uid, pts) in enumerate(rows, 1):
        member = interaction.guild.get_member(uid)

        if not member:
            try:
                member = await interaction.guild.fetch_member(uid)
            except:
                member = None

        if member:
            name = member.display_name
            avatar = member.display_avatar.url
        else:
            name = f"User-{uid}"
            avatar = None

        # emoji rank
        if i <= 3:
            rank = medals[i - 1]
        else:
            rank = f"{i}."

        embed.add_field(
            name=f"{rank} {name}",
            value=f"💳 {pts} แต้ม",
            inline=False
        )

        # set thumbnail เป็นคนอันดับ 1
        if i == 1 and avatar:
            embed.set_thumbnail(url=avatar)

    embed.set_footer(text="Top Players")

    await interaction.response.send_message(embed=embed)

# ================= RUN =================
bot.run("MTQ4ODI4MDA0ODY1Njk3Nzk3MQ.GiGqnX.CzbjMpavxJMcXoIiK2ll3_R-OtUMQqZtuxueko")