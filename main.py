import discord
from discord.ext import commands
from discord import app_commands, ui
import asyncio
import os
import json
from datetime import datetime
from typing import Optional, Dict, List
from aiohttp import web

# --- Health Check Server ---
async def handle_health(request):
    return web.Response(text="Custom Tickets läuft erfolgreich!", content_type="text/plain")

async def start_health_server():
    app = web.Application()
    app.router.add_get("/", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 5000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Health Check Server läuft auf Port {port}")

# --- Konfigurationsdatei ---
CONFIG_FILE = "ticket_config.json"
AI_TRAINING_FILE = "ai_training.json"
PERMISSIONS_FILE = "permissions.json"

def load_config():
    """Lädt die Konfiguration aus der JSON-Datei."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "servers": {}
    }

def save_config(config):
    """Speichert die Konfiguration in der JSON-Datei."""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

def load_ai_training():
    """Lädt AI Training Daten."""
    if os.path.exists(AI_TRAINING_FILE):
        with open(AI_TRAINING_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"servers": {}}

def save_ai_training(data):
    """Speichert AI Training Daten."""
    with open(AI_TRAINING_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_permissions():
    """Lädt Berechtigungen."""
    if os.path.exists(PERMISSIONS_FILE):
        with open(PERMISSIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"servers": {}}

def save_permissions(data):
    """Speichert Berechtigungen."""
    with open(PERMISSIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# Konfiguration laden
config = load_config()
save_config(config)
ai_training = load_ai_training()
permissions = load_permissions()

# --- Bot Initialisierung ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Hilfsfunktionen ---

def get_server_config(guild_id: int) -> dict:
    """Gibt die Server-spezifische Konfiguration zurück."""
    # Stelle sicher, dass "servers" existiert
    if "servers" not in config:
        config["servers"] = {}
        save_config(config)

    guild_id_str = str(guild_id)
    if guild_id_str not in config["servers"]:
        config["servers"][guild_id_str] = {
            "log_channel_id": 0,
            "staff_role_id": 0,
            "ai_training_channel_id": 0,
            "transcript_path": f"transcripts/{guild_id}",
            "embed_colors": {
                "default": 0x5865F2,
                "success": 0x57F287,
                "error": 0xED4245,
                "warning": 0xFEE75C,
                "info": 0x5865F2
            },
            "panels": {},
            "multipanels": {},
            "ticket_counter": 0
        }
        save_config(config)
        print(f"✅ Neue Server-Konfiguration erstellt für Guild ID: {guild_id}")

    # Transkript-Ordner erstellen
    transcript_path = config["servers"][guild_id_str].get("transcript_path", f"transcripts/{guild_id}")
    if not os.path.exists(transcript_path):
        os.makedirs(transcript_path)

    return config["servers"][guild_id_str]

def get_color(guild_id: int, color_type: str) -> int:
    """Gibt die konfigurierte Farbe zurück."""
    server_config = get_server_config(guild_id)
    return server_config.get("embed_colors", {}).get(color_type, 0x5865F2)

def has_permission(user_id: int, guild_id: int, command_name: str) -> bool:
    """Prüft, ob ein User Berechtigung für einen Command hat."""
    # Stelle sicher, dass "servers" existiert
    if "servers" not in permissions:
        permissions["servers"] = {}
        save_permissions(permissions)

    guild_id_str = str(guild_id)
    user_id_str = str(user_id)

    if guild_id_str not in permissions["servers"]:
        return False

    user_perms = permissions["servers"][guild_id_str].get("users", {}).get(user_id_str, [])
    return command_name in user_perms or "*" in user_perms

def is_staff(member: discord.Member, staff_role_id: int = None) -> bool:
    """Prüft, ob ein Mitglied Staff ist."""
    if staff_role_id is None:
        server_config = get_server_config(member.guild.id)
        staff_role_id = server_config.get("staff_role_id", 0)
    return any(role.id == staff_role_id for role in member.roles)

async def log_action(guild: discord.Guild, message: str, color_type: str = "info"):
    """Sendet eine Log-Nachricht."""
    server_config = get_server_config(guild.id)
    log_channel_id = server_config.get("log_channel_id", 0)
    log_channel = guild.get_channel(log_channel_id)
    if log_channel and isinstance(log_channel, discord.TextChannel):
        embed = discord.Embed(
            description=message,
            color=get_color(guild.id, color_type),
            timestamp=datetime.now()
        )
        await log_channel.send(embed=embed)

async def create_transcript(channel: discord.TextChannel) -> Optional[str]:
    """Erstellt ein Transkript des Kanals."""
    server_config = get_server_config(channel.guild.id)
    transcript_path = server_config.get("transcript_path", f"transcripts/{channel.guild.id}")
    filename = f"{transcript_path}/transcript-{channel.name}-{channel.id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"

    content = [
        f"╔══════════════════════════════════════════════════════════╗",
        f"║  TICKET TRANSCRIPT - #{channel.name}",
        f"║  Kanal ID: {channel.id}",
        f"║  Erstellt am: {datetime.now().strftime('%d.%m.%Y um %H:%M:%S')}",
        f"╚══════════════════════════════════════════════════════════╝\n"
    ]

    try:
        messages = [msg async for msg in channel.history(limit=1000, oldest_first=True)]
        for msg in messages:
            timestamp = msg.created_at.strftime("%d.%m.%Y %H:%M:%S")
            line = f"[{timestamp}] {msg.author.display_name} ({msg.author.id}):"
            if msg.content:
                line += f"\n  {msg.content}"
            if msg.attachments:
                line += f"\n  📎 Anhänge: {', '.join([a.url for a in msg.attachments])}"
            if msg.embeds:
                line += f"\n  📋 {len(msg.embeds)} Embed(s)"
            content.append(line + "\n")
    except discord.Forbidden:
        return None

    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(content))

    return filename

def get_ai_response(guild_id: int, reason: str) -> Optional[str]:
    """Generiert eine KI-Antwort basierend auf trainierten Keywords."""
    # Stelle sicher, dass "servers" existiert
    if "servers" not in ai_training:
        ai_training["servers"] = {}
        save_ai_training(ai_training)

    guild_id_str = str(guild_id)
    if guild_id_str not in ai_training["servers"]:
        return None

    reason_lower = reason.lower()
    keywords = ai_training["servers"][guild_id_str].get("keywords", {})

    for keyword, response in keywords.items():
        if keyword.lower() in reason_lower:
            return response

    return None

async def request_ai_training(channel: discord.TextChannel, reason: str, ticket_id: int, creator: discord.Member):
    """Fordert AI-Training vom Staff an."""
    server_config = get_server_config(channel.guild.id)
    ai_channel_id = server_config.get("ai_training_channel_id", 0)
    if not ai_channel_id:
        return

    ai_channel = channel.guild.get_channel(ai_channel_id)
    if not ai_channel:
        return

    staff_role = channel.guild.get_role(server_config.get("staff_role_id", 0))

    embed = discord.Embed(
        title="🤖 KI-Training benötigt",
        description=f"Ein neues Ticket wurde erstellt, aber die KI konnte keine passende Antwort finden.\n\n**Ticket:** <#{channel.id}>\n**Ersteller:** {creator.mention}\n**Grund:**\n```{reason[:500]}```",
        color=get_color(channel.guild.id, "warning"),
        timestamp=datetime.now()
    )
    embed.add_field(name="📝 Aktion erforderlich", value="Nutze die Buttons unten, um der KI beizubringen, wie sie auf ähnliche Anfragen reagieren soll.", inline=False)

    training_id = f"train_{ticket_id}_{int(datetime.now().timestamp())}"
    guild_id_str = str(channel.guild.id)

    if guild_id_str not in ai_training["servers"]:
        ai_training["servers"][guild_id_str] = {"keywords": {}, "pending_training": {}}

    ai_training["servers"][guild_id_str].setdefault("pending_training", {})[training_id] = {
        "reason": reason,
        "ticket_id": ticket_id,
        "channel_id": channel.id
    }
    save_ai_training(ai_training)

    await ai_channel.send(
        content=staff_role.mention if staff_role else "@Staff",
        embed=embed,
        view=AITrainingView(training_id, reason, channel.guild.id)
    )

# --- Modals ---

class TicketReasonModal(ui.Modal):
    """Modal für die Ticket-Erstellung."""

    reason_input = ui.TextInput(
        label='Dein Anliegen',
        style=discord.TextStyle.paragraph,
        placeholder='Beschreibe dein Problem so genau wie möglich...',
        required=True,
        max_length=1500,
        min_length=10
    )

    def __init__(self, panel_key: str, panel_data: dict, guild_id: int):
        super().__init__(title=f'Ticket: {panel_data["label"]}')
        self.panel_key = panel_key
        self.panel_data = panel_data
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        user = interaction.user
        guild = interaction.guild
        reason = self.reason_input.value
        server_config = get_server_config(guild.id)

        category = guild.get_channel(self.panel_data['category_id'])
        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.followup.send(
                f"❌ Fehler: Kategorie nicht gefunden. Bitte kontaktiere einen Administrator.",
                ephemeral=True
            )
            return

        staff_role_id = self.panel_data.get('staff_role_id', server_config.get('staff_role_id', 0))
        staff_role = guild.get_role(staff_role_id)
        if not staff_role:
            await interaction.followup.send(
                f"❌ Fehler: Staff-Rolle nicht konfiguriert.",
                ephemeral=True
            )
            return

        # Ticket-Nummer aus Counter generieren
        server_config["ticket_counter"] = server_config.get("ticket_counter", 0) + 1
        ticket_number = server_config["ticket_counter"]
        save_config(config)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True),
            staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True, manage_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }

        ticket_channel = await guild.create_text_channel(
            name=f"{self.panel_key}-{ticket_number:04d}",
            category=category,
            overwrites=overwrites,
            topic=f"Ticket von {user.name} | Typ: {self.panel_data['label']} | ID: {user.id}"
        )

        welcome_embed = discord.Embed(
            title=f"{self.panel_data.get('emoji', '🎫')} {self.panel_data['label']}",
            description=f"Vielen Dank, dass Sie uns kontaktiert haben. Ein Mitglied unseres Teams wird sich gleich bei Ihnen melden. Wir bitten Sie um Verständnis bei der Wartezeit.",
            color=get_color(guild.id, "default")
        )
        welcome_embed.add_field(
            name="❓ Reason",
            value=f"```{reason[:1000]}```",
            inline=False
        )
        welcome_embed.set_footer(text="© Custom Tickets by Custom Discord Development", icon_url=bot.user.display_avatar.url)
        welcome_embed.timestamp = datetime.now()

        await ticket_channel.send(
            content=f"{user.mention} {staff_role.mention}",
            embed=welcome_embed,
            view=TicketControlView(user.id, ticket_number, self.panel_key, staff_role_id, guild.id)
        )

        ai_response = get_ai_response(guild.id, reason)
        if ai_response:
            ai_embed = discord.Embed(
                description=f"🤖 **KI-Support Vorschlag:**\n{ai_response}",
                color=get_color(guild.id, "info")
            )
            await ticket_channel.send(embed=ai_embed)
        else:
            await request_ai_training(ticket_channel, reason, ticket_number, user)

        await interaction.followup.send(
            f"✅ Dein Ticket wurde erstellt: {ticket_channel.mention}",
            ephemeral=True
        )

        await log_action(
            guild,
            f"🎫 **Neues Ticket erstellt**\n"
            f"**Ersteller:** {user.mention} (`{user.id}`)\n"
            f"**Kanal:** {ticket_channel.mention}\n"
            f"**Typ:** {self.panel_data['label']}\n"
            f"**Grund:** {reason[:200]}...",
            "success"
        )

class PanelCreateModal(ui.Modal):
    """Modal zum Erstellen eines neuen Panels."""

    panel_id = ui.TextInput(
        label='Panel ID (eindeutig, keine Leerzeichen)',
        placeholder='z.B. support, bug, payment',
        required=True,
        max_length=50
    )

    label = ui.TextInput(
        label='Panel Name/Label',
        placeholder='z.B. Allgemeiner Support',
        required=True,
        max_length=100
    )

    emoji = ui.TextInput(
        label='Emoji',
        placeholder='z.B. 🛠️',
        required=True,
        max_length=10
    )

    category_id = ui.TextInput(
        label='Kategorie ID',
        placeholder='Rechtsklick auf Kategorie > ID kopieren',
        required=True,
        max_length=20
    )

    staff_role_id = ui.TextInput(
        label='Staff Rollen ID für dieses Panel',
        placeholder='Rechtsklick auf Rolle > ID kopieren',
        required=True,
        max_length=20
    )

    def __init__(self, guild_id: int):
        super().__init__(title='Neues Panel erstellen')
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        panel_key = self.panel_id.value.lower().replace(" ", "_")
        server_config = get_server_config(self.guild_id)

        if panel_key in server_config.get("panels", {}):
            await interaction.response.send_message(
                f"❌ Ein Panel mit der ID `{panel_key}` existiert bereits!",
                ephemeral=True
            )
            return

        try:
            category_id = int(self.category_id.value)
            category = interaction.guild.get_channel(category_id)
            if not category or not isinstance(category, discord.CategoryChannel):
                await interaction.response.send_message(
                    f"❌ Kategorie mit ID `{category_id}` nicht gefunden!",
                    ephemeral=True
                )
                return
        except ValueError:
            await interaction.response.send_message(
                f"❌ Ungültige Kategorie-ID!",
                ephemeral=True
            )
            return

        try:
            staff_role_id = int(self.staff_role_id.value)
            staff_role = interaction.guild.get_role(staff_role_id)
            if not staff_role:
                await interaction.response.send_message(
                    f"❌ Staff-Rolle mit ID `{staff_role_id}` nicht gefunden!",
                    ephemeral=True
                )
                return
        except ValueError:
            await interaction.response.send_message(
                f"❌ Ungültige Staff-Rollen-ID!",
                ephemeral=True
            )
            return

        if "panels" not in server_config:
            server_config["panels"] = {}

        server_config["panels"][panel_key] = {
            "label": self.label.value,
            "emoji": self.emoji.value,
            "category_id": category_id,
            "staff_role_id": staff_role_id,
            "enabled": True,
            "description": ""
        }

        save_config(config)

        # Öffne Description Modal
        await interaction.response.send_modal(PanelDescriptionModal(panel_key, self.guild_id))

class PanelDescriptionModal(ui.Modal):
    """Modal für Panel-Beschreibung."""

    description_input = ui.TextInput(
        label='Panel Beschreibung',
        style=discord.TextStyle.paragraph,
        placeholder='Beschreibe, wofür dieses Panel verwendet wird...',
        required=True,
        max_length=1000
    )

    def __init__(self, panel_key: str, guild_id: int):
        super().__init__(title='Panel Beschreibung')
        self.panel_key = panel_key
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        server_config = get_server_config(self.guild_id)
        server_config["panels"][self.panel_key]["description"] = self.description_input.value
        save_config(config)

        panel = server_config["panels"][self.panel_key]
        success_embed = discord.Embed(
            title="✅ Panel erstellt",
            description=f"Das Panel **{panel['label']}** wurde erfolgreich erstellt!",
            color=get_color(self.guild_id, "success")
        )
        success_embed.add_field(name="Panel ID", value=f"`{self.panel_key}`", inline=True)
        success_embed.add_field(name="Emoji", value=panel['emoji'], inline=True)
        success_embed.add_field(name="Kategorie", value=f"<#{panel['category_id']}>", inline=True)
        success_embed.add_field(name="Staff Rolle", value=f"<@&{panel['staff_role_id']}>", inline=True)
        success_embed.add_field(name="Beschreibung", value=self.description_input.value, inline=False)

        await interaction.response.send_message(embed=success_embed, ephemeral=True)

class CloseReasonModal(ui.Modal):
    """Modal für Close with Reason."""

    reason_input = ui.TextInput(
        label='Grund für das Schließen',
        style=discord.TextStyle.paragraph,
        placeholder='Warum wird dieses Ticket geschlossen?',
        required=True,
        max_length=500
    )

    def __init__(self, ticket_view):
        super().__init__(title='Ticket schließen')
        self.ticket_view = ticket_view

    async def on_submit(self, interaction: discord.Interaction):
        reason = self.reason_input.value

        for item in self.ticket_view.children:
            item.disabled = True
        await interaction.response.edit_message(view=self.ticket_view)

        closing_embed = discord.Embed(
            description=f"🔐 **Ticket wird geschlossen...**\n**Grund:** {reason}\n\nTranskript wird erstellt und der Kanal wird in 5 Sekunden gelöscht.",
            color=get_color(interaction.guild.id, "warning")
        )
        await interaction.followup.send(embed=closing_embed)

        await asyncio.sleep(3)
        await self.ticket_view.close_ticket(interaction.channel, interaction.user, reason)

class AITrainingModal(ui.Modal):
    """Modal für AI Training."""

    response_input = ui.TextInput(
        label='KI-Antwort für ähnliche Anfragen',
        style=discord.TextStyle.paragraph,
        placeholder='Was soll die KI bei ähnlichen Anfragen antworten?',
        required=True,
        max_length=1000
    )

    keywords_input = ui.TextInput(
        label='Keywords (kommagetrennt)',
        placeholder='z.B. rolle, rank, berechtigung',
        required=True,
        max_length=200
    )

    def __init__(self, training_id: str, original_reason: str, guild_id: int):
        super().__init__(title='KI Training')
        self.training_id = training_id
        self.original_reason = original_reason
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        response = self.response_input.value
        keywords = [k.strip().lower() for k in self.keywords_input.value.split(',')]

        guild_id_str = str(self.guild_id)
        if guild_id_str not in ai_training["servers"]:
            ai_training["servers"][guild_id_str] = {"keywords": {}, "pending_training": {}}

        for keyword in keywords:
            ai_training["servers"][guild_id_str]["keywords"][keyword] = response

        if self.training_id in ai_training["servers"][guild_id_str].get("pending_training", {}):
            del ai_training["servers"][guild_id_str]["pending_training"][self.training_id]

        save_ai_training(ai_training)

        success_embed = discord.Embed(
            title="✅ KI Training abgeschlossen",
            description=f"Die KI wurde erfolgreich trainiert!\n\n**Keywords:** {', '.join(keywords)}\n**Antwort:** {response[:200]}...",
            color=get_color(self.guild_id, "success")
        )

        await interaction.response.send_message(embed=success_embed, ephemeral=True)

        try:
            await interaction.message.edit(view=None)
        except:
            pass

# --- Views ---

class TicketLauncherView(ui.View):
    """Hauptview mit Buttons für jedes Panel."""

    def __init__(self, guild_id: int, panel_keys: List[str] = None):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.panel_keys = panel_keys
        self.build_buttons()

    def build_buttons(self):
        """Erstellt Buttons für ausgewählte oder alle Panels."""
        self.clear_items()

        server_config = get_server_config(self.guild_id)
        panels = server_config.get("panels", {})

        if self.panel_keys:
            panels = {k: v for k, v in panels.items() if k in self.panel_keys}

        for key, panel in panels.items():
            if not panel.get("enabled", True):
                continue

            button = ui.Button(
                label=panel.get("label", key),
                emoji=panel.get("emoji", "🎫"),
                style=discord.ButtonStyle.primary,
                custom_id=f"ticket_create_{self.guild_id}_{key}"
            )
            button.callback = self.create_button_callback(key, panel)
            self.add_item(button)

    def create_button_callback(self, panel_key: str, panel_data: dict):
        async def callback(interaction: discord.Interaction):
            await interaction.response.send_modal(TicketReasonModal(panel_key, panel_data, self.guild_id))
        return callback

class TicketControlView(ui.View):
    """Kontroll-Buttons für Ticket-Management."""

    def __init__(self, creator_id: int, ticket_number: int, panel_key: str, staff_role_id: int, guild_id: int):
        super().__init__(timeout=None)
        self.creator_id = creator_id
        self.ticket_number = ticket_number
        self.panel_key = panel_key
        self.staff_role_id = staff_role_id
        self.guild_id = guild_id
        self.claimed_by = None

    @ui.button(label="Claim", emoji="🔰", style=discord.ButtonStyle.success, custom_id="ticket_claim")
    async def claim_button(self, interaction: discord.Interaction, button: ui.Button):
        if not is_staff(interaction.user, self.staff_role_id):
            await interaction.response.send_message(
                "❌ Nur das Staff-Team dieses Tickets kann es claimen.",
                ephemeral=True
            )
            return

        if self.claimed_by:
            await interaction.response.send_message(
                f"❌ Dieses Ticket wurde bereits von <@{self.claimed_by}> geclaimed.",
                ephemeral=True
            )
            return

        self.claimed_by = interaction.user.id
        button.label = f"Claimed"
        button.style = discord.ButtonStyle.secondary
        button.disabled = True

        await interaction.message.edit(view=self)

        claim_embed = discord.Embed(
            description=f"🔰 **Ticket geclaimed von {interaction.user.mention}**",
            color=get_color(self.guild_id, "success"),
            timestamp=datetime.now()
        )
        await interaction.response.send_message(embed=claim_embed)

        await log_action(
            interaction.guild,
            f"🔰 **Ticket geclaimed**\n**Kanal:** {interaction.channel.mention}\n**Claimer:** {interaction.user.mention}",
            "info"
        )

    @ui.button(label="Close", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close_button(self, interaction: discord.Interaction, button: ui.Button):
        if not is_staff(interaction.user, self.staff_role_id):
            await interaction.response.send_message(
                "❌ Nur das Staff-Team dieses Tickets kann es schließen.",
                ephemeral=True
            )
            return

        confirm_embed = discord.Embed(
            title="⚠️ Bestätigung erforderlich",
            description="Bist du sicher, dass du dieses Ticket schließen möchtest?",
            color=get_color(self.guild_id, "warning")
        )

        await interaction.response.send_message(
            embed=confirm_embed,
            view=ConfirmCloseView(self, None),
            ephemeral=True
        )

    @ui.button(label="Close With Reason", emoji="📝", style=discord.ButtonStyle.danger, custom_id="ticket_close_reason")
    async def close_reason_button(self, interaction: discord.Interaction, button: ui.Button):
        if not is_staff(interaction.user, self.staff_role_id):
            await interaction.response.send_message(
                "❌ Nur das Staff-Team dieses Tickets kann es schließen.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(CloseReasonModal(self))

    async def close_ticket(self, channel: discord.TextChannel, closer: discord.Member, reason: str = None):
        """Schließt das Ticket mit Tickets v2 Style Log."""
        guild = channel.guild

        opener = guild.get_member(self.creator_id)
        opener_mention = opener.mention if opener else f"<@{self.creator_id}>"

        open_time = "Nicht verfügbar"
        try:
            created_at = channel.created_at
            open_time = f"{created_at.strftime('%d. %B %Y')} um {created_at.strftime('%H:%M')}"
        except:
            pass

        transcript_path = await create_transcript(channel)

        close_embed = discord.Embed(
            title="Ticket Closed",
            color=get_color(self.guild_id, "success")
        )

        close_embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)

        close_embed.add_field(
            name="<:TicketID:1458138937703796958> Ticket ID",
            value=f"{self.ticket_number}",
            inline=True
        )
        close_embed.add_field(
            name="<:Openedby:1458138940094808084> Opened By",
            value=opener_mention,
            inline=True
        )
        close_embed.add_field(
            name="<:Closedby:1458138943504781536> Closed By",
            value=closer.mention,
            inline=True
        )

        close_embed.add_field(
            name="<:OpenTime:1458138941814472867> Open Time",
            value=open_time,
            inline=True
        )
        close_embed.add_field(
            name="<:Claimedby:1458138947451359438> Claimed By",
            value=f"<@{self.claimed_by}>" if self.claimed_by else "Not claimed",
            inline=True
        )

        if reason:
            close_embed.add_field(
                name="<:Reason:1458138945773895804> Reason",
                value=reason,
                inline=False
            )
        else:
            close_embed.add_field(
                name="<:Reason:1458138945773895804> Reason",
                value="No reason given!",
                inline=False
            )

        close_embed.set_footer(text="© Custom Tickets by Custom Discord Development", icon_url=bot.user.display_avatar.url)

        server_config = get_server_config(self.guild_id)
        log_channel = guild.get_channel(server_config.get("log_channel_id", 0))
        if log_channel and transcript_path:
            try:
                transcript_file = discord.File(transcript_path, filename=f"transcript-{self.ticket_number:04d}.txt")
                await log_channel.send(embed=close_embed, file=transcript_file)
                os.remove(transcript_path)
            except Exception as e:
                await log_channel.send(embed=close_embed)
                print(f"Fehler beim Senden des Transkripts: {e}")

        if opener:
            try:
                await opener.send(embed=close_embed)
            except:
                pass

        try:
            await channel.delete(reason=f"Ticket geschlossen von {closer.name}")
        except Exception as e:
            print(f"Fehler beim Löschen des Kanals: {e}")

class ConfirmCloseView(ui.View):
    """Bestätigungs-View für Close."""

    def __init__(self, ticket_view, reason: str = None):
        super().__init__(timeout=60)
        self.ticket_view = ticket_view
        self.reason = reason

    @ui.button(label="Ja, schließen", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm_button(self, interaction: discord.Interaction, button: ui.Button):
        for item in self.ticket_view.children:
            item.disabled = True

        try:
            original_msg = [msg async for msg in interaction.channel.history(limit=10) if msg.embeds and msg.author == interaction.guild.me][0]
            await original_msg.edit(view=self.ticket_view)
        except:
            pass

        closing_embed = discord.Embed(
            description="🔐 **Ticket wird geschlossen...**\nTranskript wird erstellt und der Kanal wird in 5 Sekunden gelöscht.",
            color=get_color(interaction.guild.id, "warning")
        )
        await interaction.response.send_message(embed=closing_embed)

        await asyncio.sleep(3)
        await self.ticket_view.close_ticket(interaction.channel, interaction.user, self.reason)

    @ui.button(label="Abbrechen", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("❌ Aktion abgebrochen.", ephemeral=True)
        self.stop()

class AITrainingView(ui.View):
    """View für AI Training."""

    def __init__(self, training_id: str, reason: str, guild_id: int):
        super().__init__(timeout=None)
        self.training_id = training_id
        self.reason = reason
        self.guild_id = guild_id

    @ui.button(label="KI Trainieren", style=discord.ButtonStyle.primary, emoji="🤖")
    async def train_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(AITrainingModal(self.training_id, self.reason, self.guild_id))

    @ui.button(label="Ignorieren", style=discord.ButtonStyle.secondary, emoji="🚫")
    async def ignore_button(self, interaction: discord.Interaction, button: ui.Button):
        guild_id_str = str(self.guild_id)
        if guild_id_str in ai_training.get("servers", {}):
            if self.training_id in ai_training["servers"][guild_id_str].get("pending_training", {}):
                del ai_training["servers"][guild_id_str]["pending_training"][self.training_id]
                save_ai_training(ai_training)

        await interaction.response.send_message("✅ Training-Anfrage ignoriert.", ephemeral=True)
        await interaction.message.edit(view=None)

class PanelSelectView(ui.View):
    """View für Multipanel-Auswahl."""

    def __init__(self, multipanel_id: str, guild_id: int):
        super().__init__(timeout=180)
        self.multipanel_id = multipanel_id
        self.guild_id = guild_id
        self.selected_panels = []

        server_config = get_server_config(guild_id)
        panels = server_config.get("panels", {})
        options = []

        for key, panel in panels.items():
            options.append(discord.SelectOption(
                label=panel.get("label", key),
                value=key,
                emoji=panel.get("emoji", "🎫"),
                description=f"Kategorie: {panel.get('category_id')}"
            ))

        if options:
            select = ui.Select(
                placeholder="Wähle Panels für dieses Multipanel...",
                options=options[:25],
                min_values=1,
                max_values=min(len(options), 25)
            )
            select.callback = self.select_callback
            self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        self.selected_panels = interaction.data['values']
        server_config = get_server_config(self.guild_id)

        await interaction.response.send_message(
            f"✅ **{len(self.selected_panels)} Panels ausgewählt:**\n" + 
            "\n".join([f"• {server_config['panels'][p]['label']}" for p in self.selected_panels]),
            ephemeral=True
        )

    @ui.button(label="Multipanel Speichern", style=discord.ButtonStyle.success, emoji="💾", row=1)
    async def save_button(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_panels:
            await interaction.response.send_message("❌ Bitte wähle zuerst Panels aus!", ephemeral=True)
            return

        server_config = get_server_config(self.guild_id)
        if "multipanels" not in server_config:
            server_config["multipanels"] = {}

        server_config["multipanels"][self.multipanel_id] = {
            "panels": self.selected_panels,
            "created_by": interaction.user.id,
            "created_at": datetime.now().isoformat()
        }

        save_config(config)

        success_embed = discord.Embed(
            title="✅ Multipanel erstellt",
            description=f"Das Multipanel **{self.multipanel_id}** wurde mit {len(self.selected_panels)} Panels erstellt!",
            color=get_color(self.guild_id, "success")
        )

        await interaction.response.send_message(embed=success_embed, ephemeral=True)
        self.stop()

# --- Permission Check Decorator ---
def check_permission(command_name: str):
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        if has_permission(interaction.user.id, interaction.guild.id, command_name):
            return True
        raise app_commands.MissingPermissions(['administrator'])
    return app_commands.check(predicate)

# --- Admin Commands ---

@bot.tree.command(name="ticket_setup", description="🎫 Sendet das Ticket-Panel in diesen Kanal")
@check_permission("ticket_setup")
@app_commands.describe(multipanel="Optional: Name des Multipanels, das gesendet werden soll")
async def ticket_setup(interaction: discord.Interaction, multipanel: str = None):
    """Sendet das Ticket-Panel oder ein Multipanel."""
    server_config = get_server_config(interaction.guild.id)

    if multipanel:
        if multipanel not in server_config.get("multipanels", {}):
            await interaction.response.send_message(
                f"❌ Multipanel `{multipanel}` existiert nicht!",
                ephemeral=True
            )
            return

        panel_keys = server_config["multipanels"][multipanel]["panels"]

        # Erstelle Embed mit allen Panel-Beschreibungen
        main_embed = discord.Embed(
            title="🎫 Support Tickets",
            description="Willkommen beim Support-System!\n\nWähle unten den passenden Grund für dein Ticket aus.",
            color=get_color(interaction.guild.id, "default")
        )

        # Füge Panel-Beschreibungen hinzu
        for panel_key in panel_keys:
            if panel_key in server_config.get("panels", {}):
                panel = server_config["panels"][panel_key]
                panel_desc = panel.get("description", "Keine Beschreibung verfügbar")
                main_embed.add_field(
                    name=f"{panel.get('emoji', '🎫')} {panel.get('label', panel_key)}",
                    value=panel_desc,
                    inline=False
                )

        main_embed.set_footer(text="© Custom Tickets by Custom Discord Development")

        await interaction.channel.send(embed=main_embed, view=TicketLauncherView(interaction.guild.id, panel_keys))
        await interaction.response.send_message(f"✅ Multipanel **{multipanel}** wurde gesendet!", ephemeral=True)

    else:
        if not server_config.get("panels"):
            await interaction.response.send_message(
                "❌ Es sind noch keine Panels konfiguriert!",
                ephemeral=True
            )
            return

        # Erstelle Embed mit allen Panel-Beschreibungen
        main_embed = discord.Embed(
            title="🎫 Support Tickets",
            description="Willkommen beim Support-System!\n\nWähle unten den passenden Grund für dein Ticket aus.",
            color=get_color(interaction.guild.id, "default")
        )

        # Füge alle Panel-Beschreibungen hinzu
        for panel_key, panel in server_config.get("panels", {}).items():
            if panel.get("enabled", True):
                panel_desc = panel.get("description", "Keine Beschreibung verfügbar")
                main_embed.add_field(
                    name=f"{panel.get('emoji', '🎫')} {panel.get('label', panel_key)}",
                    value=panel_desc,
                    inline=False
                )

        main_embed.set_footer(text="© Custom Tickets by Custom Discord Development")

        await interaction.channel.send(embed=main_embed, view=TicketLauncherView(interaction.guild.id))
        await interaction.response.send_message("✅ Ticket-Panel wurde gesendet!", ephemeral=True)

@bot.tree.command(name="panel_send", description="📤 Sendet ein einzelnes Panel in einen Kanal")
@check_permission("panel_send")
@app_commands.describe(
    panel_id="Die ID des Panels",
    channel="Der Kanal (optional, Standard: aktueller Kanal)"
)
async def panel_send(interaction: discord.Interaction, panel_id: str, channel: discord.TextChannel = None):
    """Sendet ein einzelnes Panel."""
    server_config = get_server_config(interaction.guild.id)

    if panel_id not in server_config.get("panels", {}):
        await interaction.response.send_message(
            f"❌ Panel `{panel_id}` existiert nicht!",
            ephemeral=True
        )
        return

    target_channel = channel or interaction.channel
    panel = server_config["panels"][panel_id]

    panel_embed = discord.Embed(
        title=f"{panel.get('emoji', '🎫')} {panel['label']}",
        description=panel.get("description", "Klicke auf den Button unten, um ein Ticket zu erstellen."),
        color=get_color(interaction.guild.id, "default")
    )
    panel_embed.set_footer(text="© Custom Tickets by Custom Discord Development")

    await target_channel.send(embed=panel_embed, view=TicketLauncherView(interaction.guild.id, [panel_id]))
    await interaction.response.send_message(
        f"✅ Panel **{panel['label']}** wurde in {target_channel.mention} gesendet!",
        ephemeral=True
    )

@bot.tree.command(name="multipanel_create", description="📋 Erstellt ein neues Multipanel")
@check_permission("multipanel_create")
@app_commands.describe(multipanel_id="Eindeutige ID für das Multipanel")
async def multipanel_create(interaction: discord.Interaction, multipanel_id: str):
    """Erstellt ein Multipanel."""
    server_config = get_server_config(interaction.guild.id)
    multipanel_key = multipanel_id.lower().replace(" ", "_")

    if multipanel_key in server_config.get("multipanels", {}):
        await interaction.response.send_message(
            f"❌ Multipanel `{multipanel_key}` existiert bereits!",
            ephemeral=True
        )
        return

    if not server_config.get("panels"):
        await interaction.response.send_message(
            "❌ Es sind noch keine Panels vorhanden! Erstelle zuerst Panels mit `/panel_create`.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"🎨 **Erstelle Multipanel: {multipanel_key}**\n\nWähle die Panels aus, die in diesem Multipanel enthalten sein sollen:",
        view=PanelSelectView(multipanel_key, interaction.guild.id),
        ephemeral=True
    )

@bot.tree.command(name="multipanel_list", description="📋 Zeigt alle Multipanels")
@check_permission("multipanel_list")
async def multipanel_list(interaction: discord.Interaction):
    """Listet alle Multipanels."""
    server_config = get_server_config(interaction.guild.id)
    multipanels = server_config.get("multipanels", {})

    if not multipanels:
        await interaction.response.send_message(
            "❌ Es sind noch keine Multipanels konfiguriert!",
            ephemeral=True
        )
        return

    list_embed = discord.Embed(
        title="📋 Konfigurierte Multipanels",
        color=get_color(interaction.guild.id, "info")
    )

    for key, data in multipanels.items():
        panel_names = [server_config["panels"][p]["label"] for p in data["panels"] if p in server_config.get("panels", {})]
        value = f"**Panels:** {', '.join(panel_names)}\n"
        value += f"**Erstellt von:** <@{data.get('created_by', 0)}>"

        list_embed.add_field(name=f"📦 {key}", value=value, inline=False)

    await interaction.response.send_message(embed=list_embed, ephemeral=True)

@bot.tree.command(name="multipanel_delete", description="🗑️ Löscht ein Multipanel")
@check_permission("multipanel_delete")
@app_commands.describe(multipanel_id="Die ID des Multipanels")
async def multipanel_delete(interaction: discord.Interaction, multipanel_id: str):
    """Löscht ein Multipanel."""
    server_config = get_server_config(interaction.guild.id)

    if multipanel_id not in server_config.get("multipanels", {}):
        await interaction.response.send_message(
            f"❌ Multipanel `{multipanel_id}` existiert nicht!",
            ephemeral=True
        )
        return

    del server_config["multipanels"][multipanel_id]
    save_config(config)

    await interaction.response.send_message(
        f"✅ Multipanel **{multipanel_id}** wurde gelöscht!",
        ephemeral=True
    )

@bot.tree.command(name="panel_create", description="➕ Erstellt ein neues Ticket-Panel")
@check_permission("panel_create")
async def panel_create(interaction: discord.Interaction):
    """Öffnet das Modal zum Erstellen eines Panels."""
    await interaction.response.send_modal(PanelCreateModal(interaction.guild.id))

@bot.tree.command(name="panel_delete", description="🗑️ Löscht ein Ticket-Panel")
@check_permission("panel_delete")
@app_commands.describe(panel_id="Die ID des Panels")
async def panel_delete(interaction: discord.Interaction, panel_id: str):
    """Löscht ein Panel."""
    server_config = get_server_config(interaction.guild.id)

    if panel_id not in server_config.get("panels", {}):
        await interaction.response.send_message(
            f"❌ Panel `{panel_id}` existiert nicht!",
            ephemeral=True
        )
        return

    panel_data = server_config["panels"][panel_id]
    del server_config["panels"][panel_id]
    save_config(config)

    delete_embed = discord.Embed(
        title="🗑️ Panel gelöscht",
        description=f"Das Panel **{panel_data.get('label', panel_id)}** wurde erfolgreich gelöscht.",
        color=get_color(interaction.guild.id, "error")
    )

    await interaction.response.send_message(embed=delete_embed, ephemeral=True)

@bot.tree.command(name="panel_list", description="📋 Zeigt alle konfigurierten Panels")
@check_permission("panel_list")
async def panel_list(interaction: discord.Interaction):
    """Listet alle Panels auf."""
    server_config = get_server_config(interaction.guild.id)
    panels = server_config.get("panels", {})

    if not panels:
        await interaction.response.send_message(
            "❌ Es sind noch keine Panels konfiguriert!",
            ephemeral=True
        )
        return

    list_embed = discord.Embed(
        title="📋 Konfigurierte Panels",
        color=get_color(interaction.guild.id, "info")
    )

    for key, panel in panels.items():
        status = "✅ Aktiv" if panel.get("enabled", True) else "❌ Deaktiviert"
        value = f"**Label:** {panel.get('label', key)}\n"
        value += f"**Emoji:** {panel.get('emoji', '🎫')}\n"
        value += f"**Kategorie:** <#{panel.get('category_id', 0)}>\n"
        value += f"**Staff Rolle:** <@&{panel.get('staff_role_id', 0)}>\n"
        value += f"**Status:** {status}"

        list_embed.add_field(name=f"🎫 {key}", value=value, inline=True)

    await interaction.response.send_message(embed=list_embed, ephemeral=True)

@bot.tree.command(name="config_set", description="⚙️ Setzt Bot-Konfigurationen")
@check_permission("config_set")
@app_commands.describe(
    setting="Die Einstellung die geändert werden soll",
    value="Der neue Wert"
)
@app_commands.choices(setting=[
    app_commands.Choice(name="Log Kanal ID", value="log_channel_id"),
    app_commands.Choice(name="Staff Rollen ID", value="staff_role_id"),
    app_commands.Choice(name="AI Training Kanal ID", value="ai_training_channel_id"),
    app_commands.Choice(name="Embed Farbe: Default", value="color_default"),
    app_commands.Choice(name="Embed Farbe: Success", value="color_success"),
    app_commands.Choice(name="Embed Farbe: Error", value="color_error"),
    app_commands.Choice(name="Embed Farbe: Warning", value="color_warning"),
    app_commands.Choice(name="Embed Farbe: Info", value="color_info"),
])
async def config_set(interaction: discord.Interaction, setting: str, value: str):
    """Setzt Konfigurationswerte."""
    server_config = get_server_config(interaction.guild.id)

    try:
        if setting.startswith("color_"):
            color_key = setting.replace("color_", "")
            if value.startswith("#"):
                value = value[1:]
            color_int = int(value, 16)

            if "embed_colors" not in server_config:
                server_config["embed_colors"] = {}
            server_config["embed_colors"][color_key] = color_int

            success_msg = f"✅ Farbe **{color_key}** wurde auf `#{value}` gesetzt."

        else:
            server_config[setting] = int(value)
            success_msg = f"✅ **{setting}** wurde auf `{value}` gesetzt."

        save_config(config)

        embed = discord.Embed(
            description=success_msg,
            color=get_color(interaction.guild.id, "success")
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    except ValueError:
        await interaction.response.send_message(
            f"❌ Ungültiger Wert!",
            ephemeral=True
        )

@bot.tree.command(name="config_show", description="📊 Zeigt die aktuelle Konfiguration")
@check_permission("config_show")
async def config_show(interaction: discord.Interaction):
    """Zeigt die aktuelle Konfiguration."""
    server_config = get_server_config(interaction.guild.id)
    guild_id_str = str(interaction.guild.id)

    embed = discord.Embed(
        title="⚙️ Bot Konfiguration",
        color=get_color(interaction.guild.id, "info")
    )

    log_channel = interaction.guild.get_channel(server_config.get("log_channel_id", 0))
    staff_role = interaction.guild.get_role(server_config.get("staff_role_id", 0))
    ai_channel = interaction.guild.get_channel(server_config.get("ai_training_channel_id", 0))

    base_config = f"**Log Kanal:** {log_channel.mention if log_channel else '`Nicht gesetzt`'}\n"
    base_config += f"**Staff Rolle:** {staff_role.mention if staff_role else '`Nicht gesetzt`'}\n"
    base_config += f"**AI Training Kanal:** {ai_channel.mention if ai_channel else '`Nicht gesetzt`'}\n"
    base_config += f"**Panels:** {len(server_config.get('panels', {}))}\n"
    base_config += f"**Multipanels:** {len(server_config.get('multipanels', {}))}\n"

    ai_keywords = 0
    if guild_id_str in ai_training.get("servers", {}):
        ai_keywords = len(ai_training["servers"][guild_id_str].get("keywords", {}))
    base_config += f"**AI Keywords:** {ai_keywords}\n"
    base_config += f"**Ticket Counter:** {server_config.get('ticket_counter', 0)}"

    embed.add_field(name="🔧 Basis-Konfiguration", value=base_config, inline=False)

    colors = server_config.get("embed_colors", {})
    color_text = ""
    for key, value in colors.items():
        color_text += f"**{key.capitalize()}:** `#{value:06x}`\n"

    if color_text:
        embed.add_field(name="🎨 Embed-Farben", value=color_text, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="ai_keywords", description="🤖 Zeigt alle trainierten AI Keywords")
@check_permission("ai_keywords")
async def ai_keywords_cmd(interaction: discord.Interaction):
    """Zeigt AI Keywords."""
    guild_id_str = str(interaction.guild.id)
    keywords = {}

    if guild_id_str in ai_training.get("servers", {}):
        keywords = ai_training["servers"][guild_id_str].get("keywords", {})

    if not keywords:
        await interaction.response.send_message(
            "❌ Es sind noch keine Keywords trainiert!",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="🤖 Trainierte AI Keywords",
        color=get_color(interaction.guild.id, "info")
    )

    for keyword, response in list(keywords.items())[:25]:
        embed.add_field(
            name=f"🔑 {keyword}",
            value=response[:100] + "..." if len(response) > 100 else response,
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="permission_grant", description="🔑 Erteilt einem User Berechtigungen für Commands")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    user="Der User dem Berechtigungen erteilt werden",
    command="Der Command (oder * für alle)",
)
async def permission_grant(interaction: discord.Interaction, user: discord.Member, command: str):
    """Erteilt Berechtigungen."""
    guild_id_str = str(interaction.guild.id)
    user_id_str = str(user.id)

    if guild_id_str not in permissions["servers"]:
        permissions["servers"][guild_id_str] = {"users": {}}

    if "users" not in permissions["servers"][guild_id_str]:
        permissions["servers"][guild_id_str]["users"] = {}

    if user_id_str not in permissions["servers"][guild_id_str]["users"]:
        permissions["servers"][guild_id_str]["users"][user_id_str] = []

    if command not in permissions["servers"][guild_id_str]["users"][user_id_str]:
        permissions["servers"][guild_id_str]["users"][user_id_str].append(command)
        save_permissions(permissions)

        embed = discord.Embed(
            title="✅ Berechtigung erteilt",
            description=f"{user.mention} hat nun Zugriff auf den Command **{command}**",
            color=get_color(interaction.guild.id, "success")
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(
            f"❌ {user.mention} hat bereits Zugriff auf **{command}**!",
            ephemeral=True
        )

@bot.tree.command(name="permission_revoke", description="🔒 Entzieht einem User Berechtigungen")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    user="Der User dem Berechtigungen entzogen werden",
    command="Der Command (oder * für alle)",
)
async def permission_revoke(interaction: discord.Interaction, user: discord.Member, command: str):
    """Entzieht Berechtigungen."""
    guild_id_str = str(interaction.guild.id)
    user_id_str = str(user.id)

    if (guild_id_str not in permissions["servers"] or 
        user_id_str not in permissions["servers"][guild_id_str].get("users", {})):
        await interaction.response.send_message(
            f"❌ {user.mention} hat keine Berechtigungen!",
            ephemeral=True
        )
        return

    if command in permissions["servers"][guild_id_str]["users"][user_id_str]:
        permissions["servers"][guild_id_str]["users"][user_id_str].remove(command)
        save_permissions(permissions)

        embed = discord.Embed(
            title="✅ Berechtigung entzogen",
            description=f"{user.mention} hat keinen Zugriff mehr auf **{command}**",
            color=get_color(interaction.guild.id, "success")
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(
            f"❌ {user.mention} hat keinen Zugriff auf **{command}**!",
            ephemeral=True
        )

@bot.tree.command(name="permission_list", description="📋 Zeigt alle Berechtigungen")
@app_commands.checks.has_permissions(administrator=True)
async def permission_list(interaction: discord.Interaction):
    """Listet alle Berechtigungen auf."""
    guild_id_str = str(interaction.guild.id)

    if guild_id_str not in permissions["servers"] or not permissions["servers"][guild_id_str].get("users"):
        await interaction.response.send_message(
            "❌ Es sind noch keine Berechtigungen konfiguriert!",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="📋 Berechtigungen",
        color=get_color(interaction.guild.id, "info")
    )

    for user_id, commands in permissions["servers"][guild_id_str]["users"].items():
        if commands:
            embed.add_field(
                name=f"👤 <@{user_id}>",
                value=", ".join([f"`{cmd}`" for cmd in commands]),
                inline=False
            )

    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Bot Events ---

@bot.event
async def on_ready():
    """Bot ist bereit."""
    print("═" * 50)
    print(f"✅ Bot ist online: {bot.user.name}")
    print(f"📊 Discord.py Version: {discord.__version__}")
    print(f"🔗 Verbunden mit {len(bot.guilds)} Server(n)")

    # Initialisiere alle Server
    for guild in bot.guilds:
        get_server_config(guild.id)
        print(f"   ├─ {guild.name} (ID: {guild.id})")

    total_panels = sum(len(server.get("panels", {})) for server in config.get("servers", {}).values())
    total_multipanels = sum(len(server.get("multipanels", {})) for server in config.get("servers", {}).values())
    total_keywords = sum(len(server.get("keywords", {})) for server in ai_training.get("servers", {}).values())

    print(f"🎫 {total_panels} Panels geladen (alle Server)")
    print(f"📦 {total_multipanels} Multipanels geladen (alle Server)")
    print(f"🤖 {total_keywords} AI Keywords trainiert (alle Server)")
    print("═" * 50)

    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} Slash Commands synchronisiert")
        print("═" * 50)
    except Exception as e:
        print(f"❌ Fehler beim Synchronisieren: {e}")

@bot.event
async def on_guild_join(guild: discord.Guild):
    """Bot tritt einem neuen Server bei."""
    print(f"✅ Bot ist neuem Server beigetreten: {guild.name} (ID: {guild.id})")
    get_server_config(guild.id)
    print(f"   └─ Konfiguration erstellt für {guild.name}")

@bot.event
async def on_guild_remove(guild: discord.Guild):
    """Bot wird von einem Server entfernt."""
    print(f"⚠️ Bot wurde von Server entfernt: {guild.name} (ID: {guild.id})")
    print(f"   └─ Konfiguration bleibt erhalten für späteren Beitritt")

# --- Error Handlers ---

@ticket_setup.error
@panel_create.error
@panel_delete.error
@panel_list.error
@panel_send.error
@multipanel_create.error
@multipanel_list.error
@multipanel_delete.error
@config_set.error
@config_show.error
@ai_keywords_cmd.error
@permission_grant.error
@permission_revoke.error
@permission_list.error
async def command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Fehlerbehandlung für Commands."""
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ Du hast keine Berechtigung diesen Command zu nutzen!",
            ephemeral=True
        )
    elif isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            "❌ Du hast keine Berechtigung diesen Command zu nutzen!",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"❌ Ein Fehler ist aufgetreten: {str(error)}",
            ephemeral=True
        )

# --- Bot Start ---

if __name__ == "__main__":
    bot_token = os.environ.get("DISCORD_BOT_TOKEN")

    if not bot_token or bot_token == "DEIN_BOT_TOKEN_HIER":
        print("❌ FEHLER: Bitte überprüfe die Umgebungsvariable DISCORD_BOT_TOKEN!")
        print("Für Render: Setze DISCORD_BOT_TOKEN als Environment Variable")
        print("═" * 50)
        exit(1)

    try:
        # Port für Render (Web-Service benötigt einen Port)
        port = int(os.environ.get("PORT", 5000))
        print(f"🌐 Port: {port} (für Render Web Service)")

        async def run_bot():
            await start_health_server()
            async with bot:
                await bot.start(bot_token)

        asyncio.run(run_bot())
    except discord.errors.LoginFailure:
        print("❌ FEHLER: Ungültiger Bot-Token!")
    except Exception as e:
        print(f"❌ Kritischer Fehler: {e}")