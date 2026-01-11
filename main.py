import discord
from discord.ext import commands
from discord import app_commands, ui
import asyncio
import os
import json
from datetime import datetime
from typing import Optional, Dict, List
from aiohttp import web
from discord.types.embed import EmbedField

# --- Health Check Server ---
async def handle_health(request):
    return web.Response(text="Custom Tickets Bot läuft erfolgreich!", content_type="text/plain")

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

def get_server_config(guild_id: int):
    """Gibt die Konfiguration für einen bestimmten Server zurück."""
    guild_id_str = str(guild_id)
    if guild_id_str not in config["servers"]:
        config["servers"][guild_id_str] = {
            "panels": {},
            "multipanels": {},
            "log_channel_id": 0,
            "staff_role_id": 0,
            "ai_training_channel_id": 0,
            "ticket_counter": 0,
            "embed_colors": {
                "default": 0x2b2d31,
                "success": 0x2ecc71,
                "error": 0xe74c3c,
                "warning": 0xf1c40f,
                "info": 0x3498db
            }
        }
        save_config(config)
    return config["servers"][guild_id_str]

def get_color(guild_id: int, color_name: str):
    """Gibt eine Embed-Farbe für den Server zurück."""
    server_config = get_server_config(guild_id)
    return server_config.get("embed_colors", {}).get(color_name, 0x2b2d31)

def is_staff(user: discord.Member, staff_role_id: int):
    """Prüft, ob ein User Staff-Berechtigungen hat."""
    if user.guild_permissions.administrator:
        return True
    return any(role.id == staff_role_id for role in user.roles)

def check_permission(command_name: str):
    """Decorator für Berechtigungsprüfungen."""
    async def predicate(interaction: discord.Interaction):
        guild_id_str = str(interaction.guild.id)
        user_id_str = str(interaction.user.id)
        
        if interaction.user.guild_permissions.administrator:
            return True
            
        if guild_id_str in permissions["servers"]:
            server_perms = permissions["servers"][guild_id_str]
            user_perms = server_perms.get("users", {}).get(user_id_str, [])
            if command_name in user_perms:
                return True
                
        return False
    return app_commands.check(predicate)

async def log_action(guild: discord.Guild, message: str, color_name: str = "info"):
    """Loggt eine Aktion in den konfigurierten Log-Kanal."""
    server_config = get_server_config(guild.id)
    log_channel_id = server_config.get("log_channel_id", 0)
    if not log_channel_id:
        return

    log_channel = guild.get_channel(log_channel_id)
    if not log_channel:
        return

    embed = discord.Embed(
        description=message,
        color=get_color(guild.id, color_name),
        timestamp=datetime.now()
    )
    try:
        await log_channel.send(embed=embed)
    except:
        pass

# --- AI Helper Functions ---
def get_ai_response(guild_id: int, message: str):
    """Sucht nach einer passenden Antwort in den AI-Keywords."""
    guild_id_str = str(guild_id)
    if guild_id_str not in ai_training["servers"]:
        return None
    
    keywords = ai_training["servers"][guild_id_str].get("keywords", {})
    message_lower = message.lower()
    
    for keyword_str, response in keywords.items():
        keyword_list = [k.strip().lower() for k in keyword_str.split(",")]
        if any(k in message_lower for k in keyword_list):
            return response
    return None

async def request_ai_training(channel: discord.TextChannel, reason: str, ticket_id: int, creator: discord.Member):
    """Sendet eine Anfrage für KI-Training in den Admin-Kanal."""
    server_config = get_server_config(channel.guild.id)
    ai_channel_id = server_config.get("ai_training_channel_id", 0)
    if not ai_channel_id:
        return

    ai_channel = channel.guild.get_channel(ai_channel_id)
    if not ai_channel:
        return

    staff_role = channel.guild.get_role(server_config.get("staff_role_id", 0))

    embed = discord.Embed(
        title="KI-Training benötigt!",
        description=f"Ein neues Ticket wurde erstellt, aber die KI konnte keine passende Antwort finden.\n\n**Ticket:** <#{channel.id}>\n**Ersteller:** {creator.mention}\n**Grund:**\n```{reason}```",
        color=get_color(channel.guild.id, "warning"),
        timestamp=datetime.now()
    )
    embed.add_field(name="Aktion erforderlich", value="Nutze die Buttons unten, um der KI beizubringen, wie sie auf ähnliche Anfragen reagieren soll.", inline=False)
    
    bot_avatar = bot.user.display_avatar.url if bot.user and bot.user.display_avatar else None
    embed.set_footer(text="© Custom Tickets by Custom Discord Development", icon_url=bot_avatar)
    
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
                f"<:4934error:1459953806870708388> Fehler: Kategorie nicht gefunden. Bitte kontaktiere einen Administrator.",
                ephemeral=True
            )
            return

        staff_role_id = self.panel_data.get('staff_role_id', server_config.get('staff_role_id', 0))
        staff_role = guild.get_role(staff_role_id)
        if not staff_role:
            await interaction.followup.send(
                f"<:4934error:1459953806870708388> Fehler: Staff-Rolle nicht konfiguriert.",
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
            name="<:9396info:1459954159850881076> Anliegen",
            value=f"```{reason}```",
            inline=False
        )
        
        bot_avatar = bot.user.display_avatar.url if bot.user and bot.user.display_avatar else None
        welcome_embed.set_footer(text="© Custom Tickets by Custom Discord Development", icon_url=bot_avatar)
        welcome_embed.timestamp = datetime.now()

        await ticket_channel.send(
            content=f"{user.mention} {staff_role.mention}",
            embed=welcome_embed,
            view=TicketControlView(user.id, ticket_number, self.panel_key, staff_role_id, guild.id)
        )

        ai_response = get_ai_response(guild.id, reason)
        if ai_response:
            ai_embed = discord.Embed(
                description=f"**KI-Support**\n{ai_response}",
                color=get_color(guild.id, "info")
            )
            await ticket_channel.send(embed=ai_embed)
        else:
            await request_ai_training(ticket_channel, reason, ticket_number, user)

        await interaction.followup.send(
            f"<:4569ok:1459953782556463250> Dein Ticket wurde erstellt: {ticket_channel.mention}",
            ephemeral=True
        )

        await log_action(
            guild,
            f"**Neues Ticket erstellt**\n"
            f"**Ersteller:** {user.mention} (`{user.id}`)\n"
            f"**Kanal:** {ticket_channel.mention}\n"
            f"**Typ:** {self.panel_data['label']}\n"
            f"**Grund:** {reason}...",
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
                f"<:4934error:1459953806870708388> Ein Panel mit der ID `{panel_key}` existiert bereits!",
                ephemeral=True
            )
            return

        try:
            category_id = int(self.category_id.value)
            category = interaction.guild.get_channel(category_id)
            if not category or not isinstance(category, discord.CategoryChannel):
                await interaction.response.send_message(
                    f"<:4934error:1459953806870708388> Kategorie mit ID `{category_id}` nicht gefunden!",
                    ephemeral=True
                )
                return
        except ValueError:
            await interaction.response.send_message(f"<:4934error:1459953806870708388> Ungültige Kategorie-ID!", ephemeral=True)
            return

        try:
            staff_role_id = int(self.staff_role_id.value)
            staff_role = interaction.guild.get_role(staff_role_id)
            if not staff_role:
                await interaction.response.send_message(f"<:4934error:1459953806870708388> Staff-Rolle mit ID `{staff_role_id}` nicht gefunden!", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message(f"<:4934error:1459953806870708388> Ungültige Staff-Rollen-ID!", ephemeral=True)
            return

        # Wir speichern die Daten direkt, aber lassen die Beschreibung leer.
        if "panels" not in server_config:
            server_config["panels"] = {}

        server_config["panels"][panel_key] = {
            "label": self.label.value,
            "emoji": self.emoji.value,
            "category_id": category_id,
            "staff_role_id": staff_role_id,
            "description": "Klicke auf den Button unten, um ein Ticket zu erstellen.",
            "enabled": True
        }
        save_config(config)

        # Nachricht mit Button senden
        view = ui.View()
        button = ui.Button(label="Beschreibung hinzufügen", style=discord.ButtonStyle.primary, emoji="📝")
        
        async def button_callback(b_interaction: discord.Interaction):
            await b_interaction.response.send_modal(PanelDescriptionModal(panel_key, self.guild_id))
            
        button.callback = button_callback
        view.add_item(button)

        await interaction.response.send_message(
            content=f"<:4569ok:1459953782556463250> Panel-Basisdaten für `{self.label.value}` gespeichert! Bitte klicke auf den Button unten, um die **Beschreibung** hinzuzufügen.",
            view=view,
            ephemeral=True
        )

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
        if self.panel_key in server_config.get("panels", {}):
            server_config["panels"][self.panel_key]["description"] = self.description_input.value
            save_config(config)

            success_embed = discord.Embed(
                title="<:4569ok:1459953782556463250> Panel fertiggestellt!",
                description=f"Das Panel wurde erfolgreich mit Beschreibung gespeichert!",
                color=get_color(self.guild_id, "success")
            )
            await interaction.response.send_message(embed=success_embed, ephemeral=True)
        else:
            await interaction.response.send_message("<:4934error:1459953806870708388> Fehler: Panel wurde nicht gefunden.", ephemeral=True)

class CloseReasonModal(ui.Modal):
    """Modal für Close with Reason."""

    reason_input = ui.TextInput(
        label='Grund für das Schließen',
        style=discord.TextStyle.paragraph,
        placeholder='Warum wird dieses Ticket geschlossen?',
        required=True,
        max_length=1000
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
            description=f"<:Closedby:1458138943504781536> **Ticket wird geschlossen...**\n**Grund:** {reason}\n\nTranskript wird erstellt und der Kanal wird in 5 Sekunden gelöscht.",
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
        max_length=3000
    )

    keywords_input = ui.TextInput(
        label='Keywords (kommagetrennt)',
        placeholder='z.B. rolle, rank, berechtigung',
        required=True,
        max_length=500
    )

    def __init__(self, training_id: str, guild_id: int):
        super().__init__(title='KI-Training')
        self.training_id = training_id
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        guild_id_str = str(self.guild_id)
        keywords = self.keywords_input.value
        response = self.response_input.value
        
        if guild_id_str not in ai_training["servers"]:
            ai_training["servers"][guild_id_str] = {"keywords": {}, "pending_training": {}}
            
        ai_training["servers"][guild_id_str]["keywords"][keywords] = response
        
        # Entferne aus Pending
        if guild_id_str in ai_training["servers"] and self.training_id in ai_training["servers"][guild_id_str].get("pending_training", {}):
            del ai_training["servers"][guild_id_str]["pending_training"][self.training_id]
            
        save_ai_training(ai_training)

        # Update Admin Message
        embed = interaction.message.embeds[0]
        embed.color = get_color(self.guild_id, "success")
        embed.title = "<:4569ok:1459953782556463250> KI-Training abgeschlossen"
        embed.add_field(name="Keywords", value=f"`{keywords}`", inline=False)
        embed.add_field(name="Antwort", value=response, inline=False)
        
        await interaction.response.edit_message(embed=embed, view=None)

# --- Views ---

class TicketControlView(ui.View):
    """View für die Ticket-Steuerung im Channel."""

    def __init__(self, creator_id: int, ticket_number: int, panel_key: str, staff_role_id: int, guild_id: int):
        super().__init__(timeout=None)
        self.creator_id = creator_id
        self.ticket_number = ticket_number
        self.panel_key = panel_key
        self.staff_role_id = staff_role_id
        self.guild_id = guild_id
        self.claimed_by = None

    @ui.button(label="Claim", emoji="✋", style=discord.ButtonStyle.success, custom_id="ticket_claim")
    async def claim_button(self, interaction: discord.Interaction, button: ui.Button):
        if not is_staff(interaction.user, self.staff_role_id):
            await interaction.response.send_message(
                "<:4934error:1459953806870708388> Nur Teammitglieder können dieses Ticket claimen.",
                ephemeral=True
            )
            return

        if self.claimed_by:
            await interaction.response.send_message(
                f"<:4934error:1459953806870708388> Dieses Ticket wurde bereits von <@{self.claimed_by}> übernommen.",
                ephemeral=True
            )
            return

        self.claimed_by = interaction.user.id
        button.disabled = True
        button.label = f"Claimed by {interaction.user.name}"
        
        # Permissions anpassen
        await interaction.channel.set_permissions(interaction.user, view_channel=True, send_messages=True, manage_channels=True)
        
        await interaction.response.edit_message(view=self)
        
        claim_embed = discord.Embed(
            description=f"<:8649warning:1459953895689162842> **{interaction.user.mention}** hat das Ticket übernommen!",
            color=get_color(self.guild_id, "success")
        )
        await interaction.channel.send(embed=claim_embed)

    @ui.button(label="Close", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close_button(self, interaction: discord.Interaction, button: ui.Button):
        if not is_staff(interaction.user, self.staff_role_id):
            await interaction.response.send_message(
                "<:4934error:1459953806870708388> Nur das Staff-Team dieses Tickets kann es schließen.",
                ephemeral=True
            )
            return

        confirm_embed = discord.Embed(
            title="Ticket schließen?",
            description="Bist du sicher, dass du dieses Ticket schließen möchtest?",
            color=get_color(self.guild_id, "error")
        )

        await interaction.response.send_message(
            embed=confirm_embed,
            view=ConfirmCloseView(self, None),
            ephemeral=True
        )

    @ui.button(label="Close With Reason", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ticket_close_reason")
    async def close_reason_button(self, interaction: discord.Interaction, button: ui.Button):
        if not is_staff(interaction.user, self.staff_role_id):
            await interaction.response.send_message(
                "<:4934error:1459953806870708388> Nur das Staff-Team dieses Tickets kann es schließen.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(CloseReasonModal(self))

    async def close_ticket(self, channel: discord.TextChannel, closer: discord.Member, reason: str = None):
        """Schließt das Ticket und erstellt Transkript."""
        guild = channel.guild
        opener = guild.get_member(self.creator_id)
        opener_mention = f"<@{self.creator_id}>" if not opener else opener.mention
        
        # Transkript erstellen
        messages = [message async for message in channel.history(limit=None, oldest_first=True)]
        transcript_content = f"TRANSKRIPT - TICKET {self.panel_key}-{self.ticket_number:04d}\n"
        transcript_content += f"Server: {guild.name}\n"
        transcript_content += f"Ersteller: {opener.name if opener else 'Unknown'} ({self.creator_id})\n"
        transcript_content += f"Geschlossen von: {closer.name} ({closer.id})\n"
        transcript_content += f"Grund: {reason if reason else 'Kein Grund angegeben.'}\n"
        transcript_content += "="*50 + "\n\n"
        
        for msg in messages:
            timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
            content = msg.content if msg.content else "[Embed/Anhang]"
            transcript_content += f"[{timestamp}] {msg.author.name}: {content}\n"
            
        os.makedirs("transcripts", exist_ok=True)
        filename = f"transcripts/ticket-{self.panel_key}-{self.ticket_number}-{int(datetime.now().timestamp())}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(transcript_content)

        open_time = "Unbekannt"
        try:
            created_at = channel.created_at
            open_time = f"{created_at.strftime('%d. %B %Y')} um {created_at.strftime('%H:%M')}"
        except:
            pass

        close_embed = discord.Embed(
            title="Ticket Closed",
            color=get_color(self.guild_id, "success")
        )

        close_embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)

        close_embed.add_field(
            name="<:8907top:1459954041336365118> Ticket ID",
            value=f"{self.ticket_number}",
            inline=True
        )
        close_embed.add_field(
            name="<:4569ok:1459953782556463250> Opened By",
            value=opener_mention,
            inline=True
        )
        close_embed.add_field(
            name="<:4934error:1459953806870708388> Closed By",
            value=closer.mention,
            inline=True
        )

        close_embed.add_field(
            name="<:8649cooldown:1459953871572046133> Open Time",
            value=open_time,
            inline=True
        )
        close_embed.add_field(
            name="<:9081settings:1459954085464772799> Claimed By",
            value=f"<@{self.claimed_by}>" if self.claimed_by else "Not claimed",
            inline=True
        )

        if reason:
            close_embed.add_field(
                name="<:8649warning:1459953895689162842> Reason",
                value=reason,
                inline=False
            )
        else:
            close_embed.add_field(
                name="<:8649warning:1459953895689162842> Reason",
                value="Kein Grund angegeben.",
                inline=False
            )

        close_embed.set_footer(
            text=f"© Custom Tickets by Custom Discord Development | {datetime.now().strftime('%d.%m.%y, %H:%M')}", 
            icon_url=guild.me.display_avatar.url if guild.me.display_avatar else None
        )

        log_channel = guild.get_channel(get_server_config(self.guild_id).get("log_channel_id", 0))
        if log_channel:
            try:
                await log_channel.send(embed=close_embed)
            except Exception as e:
                print(f"<:4934error:1459953806870708388> Kritischer Fehler: {e}")
                print(f"Fehler beim Senden des Close-Logs: {e}")

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

    @ui.button(label="Schließen", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: ui.Button):
        for item in self.ticket_view.children:
            item.disabled = True

        try:
            original_msg = [msg async for msg in interaction.channel.history(limit=10) if msg.embeds and msg.author == interaction.guild.me][0]
            await original_msg.edit(view=self.ticket_view)
        except:
            pass

        closing_embed = discord.Embed(
            description="<:8649warning:1459953895689162842> **Ticket wird geschlossen...**\nDer Kanal wird in 5 Sekunden gelöscht.",
            color=get_color(interaction.guild.id, "warning")
        )
        await interaction.response.send_message(embed=closing_embed)

        await asyncio.sleep(5)
        await self.ticket_view.close_ticket(interaction.channel, interaction.user, self.reason)

    @ui.button(label="Abbrechen", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("<:4934error:1459953806870708388> Aktion abgebrochen.", ephemeral=True)
        self.stop()

class AITrainingView(ui.View):
    """View für AI Training."""

    def __init__(self, training_id: str, reason: str, guild_id: int):
        super().__init__(timeout=None)
        self.training_id = training_id
        self.reason = reason
        self.guild_id = guild_id

    @ui.button(label="Trainieren", style=discord.ButtonStyle.primary, emoji="🤖")
    async def train_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(AITrainingModal(self.training_id, self.guild_id))

    @ui.button(label="Ablehnen", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def ignore_button(self, interaction: discord.Interaction, button: ui.Button):
        guild_id_str = str(self.guild_id)
        if guild_id_str in ai_training["servers"] and self.training_id in ai_training["servers"][guild_id_str].get("pending_training", {}):
            del ai_training["servers"][guild_id_str]["pending_training"][self.training_id]
            save_ai_training(ai_training)

        embed = interaction.message.embeds[0]
        embed.color = get_color(self.guild_id, "error")
        embed.title = "<:4934error:1459953806870708388> KI-Training abgelehnt"
        await interaction.response.edit_message(embed=embed, view=None)

class TicketPanelView(ui.View):
    """View für die Ticket-Panel Buttons."""

    def __init__(self, panel_id: str, panel_data: dict, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.add_item(TicketButton(panel_id, panel_data, guild_id))

class MultiTicketPanelView(ui.View):
    """View für Multipanels."""
    def __init__(self, panels_data: dict, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        for key, panel in panels_data.items():
            if panel.get("enabled", True):
                self.add_item(TicketButton(key, panel, guild_id))

class TicketButton(ui.Button):
    """Individueller Ticket-Button."""

    def __init__(self, panel_key: str, panel_data: dict, guild_id: int):
        super().__init__(
            label=panel_data.get('label', panel_key),
            emoji=panel_data.get('emoji', '🎫'),
            style=discord.ButtonStyle.secondary,
            custom_id=f"ticket_{panel_key}"
        )
        self.panel_key = panel_key
        self.panel_data = panel_data
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketReasonModal(self.panel_key, self.panel_data, self.guild_id))

# --- Bot Setup ---

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.tree.command(name="ticket_setup", description="🚀 Sendet das Ticket-Panel")
@check_permission("ticket_setup")
async def ticket_setup(interaction: discord.Interaction):
    """Sendet das Ticket-Panel."""
    server_config = get_server_config(interaction.guild.id)
    panels = server_config.get("panels", {})
    
    if not panels:
        await interaction.response.send_message("<:4934error:1459953806870708388> Keine Panels konfiguriert! Nutze `/panel_create`.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🎫 Ticket-System",
        description="Wähle eine Kategorie aus, um ein Ticket zu erstellen.",
        color=get_color(interaction.guild.id, "default")
    )
    
    bot_avatar = bot.user.display_avatar.url if bot.user and bot.user.display_avatar else None
    embed.set_footer(text="© Custom Tickets by Custom Discord Development", icon_url=bot_avatar)
    
    # Multipanel View verwenden um alle Panels zu zeigen
    view = MultiTicketPanelView(panels, interaction.guild.id)
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("<:4569ok:1459953782556463250> Ticket-Panel wurde gesendet.", ephemeral=True)

@bot.tree.command(name="panel_create", description="➕ Erstellt ein neues Ticket-Panel")
@check_permission("panel_create")
async def panel_create(interaction: discord.Interaction):
    """Erstellt ein neues Panel."""
    await interaction.response.send_modal(PanelCreateModal(interaction.guild.id))

@bot.tree.command(name="panel_delete", description="➖ Löscht ein Ticket-Panel")
@app_commands.describe(panel_id="Die ID des zu löschenden Panels")
@check_permission("panel_delete")
async def panel_delete(interaction: discord.Interaction, panel_id: str):
    """Löscht ein Panel."""
    server_config = get_server_config(interaction.guild.id)
    if panel_id in server_config.get("panels", {}):
        del server_config["panels"][panel_id]
        save_config(config)
        await interaction.response.send_message(f"<:4569ok:1459953782556463250> Panel `{panel_id}` wurde gelöscht.", ephemeral=True)
    else:
        await interaction.response.send_message(f"<:4934error:1459953806870708388> Panel `{panel_id}` nicht gefunden.", ephemeral=True)

@bot.tree.command(name="panel_list", description="📋 Listet alle konfigurierten Panels auf")
@check_permission("panel_list")
async def panel_list(interaction: discord.Interaction):
    """Listet Panels auf."""
    server_config = get_server_config(interaction.guild.id)
    panels = server_config.get("panels", {})
    
    if not panels:
        await interaction.response.send_message("<:4934error:1459953806870708388> Keine Panels konfiguriert.", ephemeral=True)
        return

    list_embed = discord.Embed(title="📋 Konfigurierte Panels", color=get_color(interaction.guild.id, "info"))
    
    for key, panel in panels.items():
        status = "<:4569ok:1459953782556463250> Aktiv" if panel.get("enabled", True) else "<:4934error:1459953806870708388> Deaktiviert"
        value = f"**Label:** {panel.get('label', key)}\n"
        value += f"**Emoji:** {panel.get('emoji', '🎫')}\n"
        value += f"**Kategorie:** <#{panel.get('category_id', 0)}>\n"
        value += f"**Staff Rolle:** <@&{panel.get('staff_role_id', 0)}>\n"
        value += f"**Status:** {status}"

        list_embed.add_field(name=f"🎫 {key}", value=value, inline=True)

    await interaction.response.send_message(embed=list_embed, ephemeral=True)

@bot.tree.command(name="config_set", description="⚙️ Setzt Bot-Konfigurationen")
@check_permission("config_set")
@app_commands.describe(setting="Die Einstellung die geändert werden soll", value="Der neue Wert")
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
            success_msg = f"<:4569ok:1459953782556463250> Farbe **{color_key}** wurde auf `#{value}` gesetzt."
        else:
            server_config[setting] = int(value)
            success_msg = f"<:4569ok:1459953782556463250> **{setting}** wurde auf `{value}` gesetzt."

        save_config(config)
        embed = discord.Embed(description=success_msg, color=get_color(interaction.guild.id, "success"))
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except ValueError:
        await interaction.response.send_message(f"<:4934error:1459953806870708388> Ungültiger Wert!", ephemeral=True)

@bot.tree.command(name="config_show", description="📊 Zeigt die aktuelle Konfiguration")
@check_permission("config_show")
async def config_show(interaction: discord.Interaction):
    """Zeigt die aktuelle Konfiguration."""
    server_config = get_server_config(interaction.guild.id)
    embed = discord.Embed(
        title="⚙️ Serverkonfiguration",
        color=get_color(interaction.guild.id, "info"),
        timestamp=datetime.now()
    )
    
    # Basis-Informationen
    log_channel = interaction.guild.get_channel(server_config.get("log_channel_id", 0))
    staff_role = interaction.guild.get_role(server_config.get("staff_role_id", 0))
    ai_channel = interaction.guild.get_channel(server_config.get("ai_training_channel_id", 0))
    
    log_mention = log_channel.mention if log_channel else "<:4934error:1459953806870708388> Nicht gesetzt"
    staff_mention = staff_role.mention if staff_role else "<:4934error:1459953806870708388> Nicht gesetzt"
    ai_mention = ai_channel.mention if ai_channel else "<:4934error:1459953806870708388> Nicht gesetzt"
    
    embed.add_field(name="Allgemein", value=f"**Log-Kanal:** {log_mention}\n**Staff-Rolle:** {staff_mention}\n**KI-Training:** {ai_mention}\n**Tickets gesamt:** `{server_config.get('ticket_counter', 0)}`", inline=False)
    
    # Panels
    panels = server_config.get("panels", {})
    if panels:
        panel_list = []
        for p_id, p_data in panels.items():
            status = "<:4569ok:1459953782556463250>" if p_data.get("enabled", True) else "<:4934error:1459953806870708388>"
            panel_list.append(f"{status} `{p_id}`: {p_data['label']} ({p_data.get('emoji', '🎫')})")
        embed.add_field(name="Panels", value="\n".join(panel_list), inline=True)
    
    # Multipanels
    multipanels = server_config.get("multipanels", {})
    if multipanels:
        mp_list = [f"<:8907top:1459954041336365118> `{mp_id}`" for mp_id in multipanels.keys()]
        embed.add_field(name="Multipanels", value="\n".join(mp_list), inline=True)

    # Farben
    colors = server_config.get("embed_colors", {})
    if colors:
        color_info = "\n".join([f"**{name}:** `{hex(val)}`" for name, val in colors.items()])
        embed.add_field(name="Farben", value=color_info, inline=False)
        
    # Nützliche Infos
    embed.add_field(name="Nützliche Befehle", value="`/config_set` - Einstellungen ändern\n`/panel_create` - Neues Panel\n`/multipanel_create` - Multipanel\n`/multipanel_list` - Multipanels anzeigen\n`/multipanel_delete` - Multipanel löschen\n`/permission_grant` - Rechte vergeben", inline=False)
    
    bot_avatar = bot.user.display_avatar.url if bot.user and bot.user.display_avatar else None
    embed.set_footer(text="© Custom Tickets by Custom Discord Development", icon_url=bot_avatar)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="panel_send", description="📤 Sendet ein einzelnes Ticket-Panel")
@app_commands.describe(panel_id="Die ID des Panels, das gesendet werden soll")
@check_permission("panel_send")
async def panel_send(interaction: discord.Interaction, panel_id: str):
    """Sendet ein einzelnes Ticket-Panel."""
    server_config = get_server_config(interaction.guild.id)
    panels = server_config.get("panels", {})
    
    if panel_id not in panels:
        await interaction.response.send_message(f"<:4934error:1459953806870708388> Panel `{panel_id}` wurde nicht gefunden!", ephemeral=True)
        return
        
    panel_data = panels[panel_id]
    if not panel_data.get("enabled", True):
        await interaction.response.send_message(f"<:4934error:1459953806870708388> Panel `{panel_id}` ist deaktiviert!", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"{panel_data.get('emoji', '🎫')} {panel_data['label']}",
        description=panel_data.get('description', 'Klicke auf den Button unten, um ein Ticket zu erstellen.'),
        color=get_color(interaction.guild.id, "default")
    )
    
    bot_avatar = bot.user.display_avatar.url if bot.user and bot.user.display_avatar else None
    embed.set_footer(text="© Custom Tickets by Custom Discord Development", icon_url=bot_avatar)
    
    view = TicketPanelView(panel_id, panel_data, interaction.guild.id)
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message(f"<:4569ok:1459953782556463250> Panel `{panel_id}` wurde gesendet.", ephemeral=True)

class MultipanelSelect(ui.Select):
    def __init__(self, panels: dict):
        options = [
            discord.SelectOption(label=data["label"], value=pid, emoji=data.get("emoji", "🎫"))
            for pid, data in panels.items()
        ]
        super().__init__(placeholder="Wähle die Panels für das Multipanel aus...", min_values=1, max_values=len(options), options=options)

    async def callback(self, interaction: discord.Interaction):
        # We don't defer here because we'll handle it in the command if needed, 
        # or we use the interaction directly.
        # However, to avoid "interaction already responded", we should be careful.
        self.view.selected_panels = self.values
        await interaction.response.send_message(f"<:4569ok:1459953782556463250> {len(self.values)} Panels ausgewählt.", ephemeral=True)
        self.view.stop()

class MultipanelCreateView(ui.View):
    def __init__(self, panels: dict):
        super().__init__(timeout=60)
        self.selected_panels = []
        self.add_item(MultipanelSelect(panels))

@bot.tree.command(name="multipanel_create", description="📚 Erstellt ein neues Multipanel")
@app_commands.describe(multipanel_id="Eindeutige ID für das Multipanel")
@check_permission("multipanel_create")
async def multipanel_create(interaction: discord.Interaction, multipanel_id: str):
    """Erstellt ein Multipanel via Auswahl-Menü."""
    server_config = get_server_config(interaction.guild.id)
    panels = server_config.get("panels", {})
    
    if not panels:
        await interaction.response.send_message("<:4934error:1459953806870708388> Keine Panels vorhanden. Erstelle erst Panels mit `/panel_create`.", ephemeral=True)
        return

    multipanel_id = multipanel_id.lower().replace(" ", "_")
    if multipanel_id in server_config.get("multipanels", {}):
        await interaction.response.send_message(f"<:4934error:1459953806870708388> Multipanel `{multipanel_id}` existiert bereits!", ephemeral=True)
        return

    view = MultipanelCreateView(panels)
    await interaction.response.send_message("Bitte wähle die Panels aus, die in diesem Multipanel enthalten sein sollen:", view=view, ephemeral=True)
    
    await view.wait()
    if not view.selected_panels:
        return

    if "multipanels" not in server_config:
        server_config["multipanels"] = {}
        
    server_config["multipanels"][multipanel_id] = view.selected_panels
    save_config(config)
    
    try:
        await interaction.followup.send(f"<:4569ok:1459953782556463250> Multipanel `{multipanel_id}` mit {len(view.selected_panels)} Panels erstellt!", ephemeral=True)
    except Exception as e:
        print(f"Fehler beim Senden der Bestätigung: {e}")

@bot.tree.command(name="multipanel_delete", description="🗑️ Löscht ein Multipanel")
@app_commands.describe(multipanel_id="Die ID des zu löschenden Multipanels")
@check_permission("multipanel_delete")
async def multipanel_delete(interaction: discord.Interaction, multipanel_id: str):
    """Löscht ein Multipanel."""
    server_config = get_server_config(interaction.guild.id)
    if multipanel_id in server_config.get("multipanels", {}):
        del server_config["multipanels"][multipanel_id]
        save_config(config)
        await interaction.response.send_message(f"<:4569ok:1459953782556463250> Multipanel `{multipanel_id}` wurde gelöscht.", ephemeral=True)
    else:
        await interaction.response.send_message(f"<:4934error:1459953806870708388> Multipanel `{multipanel_id}` nicht gefunden.", ephemeral=True)

@bot.tree.command(name="multipanel_list", description="📋 Listet alle Multipanels auf")
@check_permission("multipanel_list")
async def multipanel_list(interaction: discord.Interaction):
    """Listet Multipanels auf."""
    server_config = get_server_config(interaction.guild.id)
    multipanels = server_config.get("multipanels", {})
    
    if not multipanels:
        await interaction.response.send_message("<:4934error:1459953806870708388> Keine Multipanels konfiguriert.", ephemeral=True)
        return

    embed = discord.Embed(title="📚 Konfigurierte Multipanels", color=get_color(interaction.guild.id, "info"))
    for mp_id, p_ids in multipanels.items():
        embed.add_field(name=f"🆔 {mp_id}", value=f"Panels: {', '.join([f'`{pid}`' for pid in p_ids])}", inline=False)
        
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="multipanel_send", description="📤 Sendet ein Multipanel")
@app_commands.describe(multipanel_id="Die ID des Multipanels")
@check_permission("multipanel_send")
async def multipanel_send(interaction: discord.Interaction, multipanel_id: str):
    """Sendet ein Multipanel."""
    server_config = get_server_config(interaction.guild.id)
    multipanels = server_config.get("multipanels", {})
    
    if multipanel_id not in multipanels:
        await interaction.response.send_message(f"<:4934error:1459953806870708388> Multipanel `{multipanel_id}` nicht gefunden!", ephemeral=True)
        return
        
    p_ids = multipanels[multipanel_id]
    panels = server_config.get("panels", {})
    
    active_panels = {pid: panels[pid] for pid in p_ids if pid in panels and panels[pid].get("enabled", True)}
    
    if not active_panels:
        await interaction.response.send_message("<:4934error:1459953806870708388> Keine aktiven Panels in diesem Multipanel gefunden.", ephemeral=True)
        return

    # Beschreibungen der Panels sammeln
    desc_parts = []
    for pid, p_data in active_panels.items():
        desc_parts.append(f"**{p_data.get('emoji', '🎫')} {p_data['label']}**\n{p_data.get('description', 'Keine Beschreibung.')}")
    
    description = "\n\n".join(desc_parts)

    embed = discord.Embed(
        title="Kontakt",
        description=description,
        color=get_color(interaction.guild.id, "default")
    )
    bot_avatar = bot.user.display_avatar.url if bot.user and bot.user.display_avatar else None
    embed.set_footer(text="© Custom Tickets by Custom Discord Development", icon_url=bot_avatar)
    
    view = MultiTicketPanelView(active_panels, interaction.guild.id)
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message(f"<:4569ok:1459953782556463250> Multipanel `{multipanel_id}` gesendet.", ephemeral=True)

@bot.tree.command(name="add", description="👤 Fügt einen User zum Ticket hinzu")
@app_commands.describe(user="Der User, der hinzugefügt werden soll")
async def add(interaction: discord.Interaction, user: discord.Member):
    """Fügt einen User zum Ticket hinzu."""
    if not interaction.channel.topic or "Ticket von" not in interaction.channel.topic:
        await interaction.response.send_message("<:4934error:1459953806870708388> Dieser Befehl kann nur in Ticket-Kanälen verwendet werden.", ephemeral=True)
        return

    # Berechtigungen prüfen (nur Staff oder Ersteller darf Leute hinzufügen)
    # Hier vereinfacht: Jedes Teammitglied kann Leute hinzufügen
    # Wir suchen die staff_role_id aus dem Topic oder der Config
    server_config = get_server_config(interaction.guild.id)
    staff_role_id = server_config.get("staff_role_id", 0)
    
    if not is_staff(interaction.user, staff_role_id):
        await interaction.response.send_message("<:4934error:1459953806870708388> Keine Berechtigung!", ephemeral=True)
        return

    await interaction.channel.set_permissions(user, view_channel=True, send_messages=True, attach_files=True, embed_links=True)
    
    embed = discord.Embed(
        description=f"<:8649warning:1459953895689162842> {user.mention} wurde zum Ticket hinzugefügt.",
        color=get_color(interaction.guild.id, "success")
    )
    await interaction.response.send_message(embed=embed)
    
    await log_action(
        interaction.guild,
        f"**User zum Ticket hinzugefügt**\n"
        f"**Kanal:** {interaction.channel.mention}\n"
        f"**Hinzugefügt:** {user.mention} (`{user.id}`)\n"
        f"**Durch:** {interaction.user.mention}",
        "info"
    )

@bot.tree.command(name="remove", description="👤 Entfernt einen User vom Ticket")
@app_commands.describe(user="Der User, der entfernt werden soll")
async def remove(interaction: discord.Interaction, user: discord.Member):
    """Entfernt einen User vom Ticket."""
    if not interaction.channel.topic or "Ticket von" not in interaction.channel.topic:
        await interaction.response.send_message("<:4934error:1459953806870708388> Dieser Befehl kann nur in Ticket-Kanälen verwendet werden.", ephemeral=True)
        return

    server_config = get_server_config(interaction.guild.id)
    staff_role_id = server_config.get("staff_role_id", 0)
    
    if not is_staff(interaction.user, staff_role_id):
        await interaction.response.send_message("<:4934error:1459953806870708388> Keine Berechtigung!", ephemeral=True)
        return

    await interaction.channel.set_permissions(user, overwrite=None)
    
    embed = discord.Embed(
        description=f"<:8649warning:1459953895689162842> {user.mention} wurde vom Ticket entfernt.",
        color=get_color(interaction.guild.id, "error")
    )
    await interaction.response.send_message(embed=embed)
    
    await log_action(
        interaction.guild,
        f"**User vom Ticket entfernt**\n"
        f"**Kanal:** {interaction.channel.mention}\n"
        f"**Entfernt:** {user.mention} (`{user.id}`)\n"
        f"**Durch:** {interaction.user.mention}",
        "warning"
    )

@bot.tree.command(name="permission_grant", description="🔐 Gibt einem User Berechtigungen")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(user="Der User", command="Der Command Name (oder 'all')")
async def permission_grant(interaction: discord.Interaction, user: discord.Member, command: str):
    """Gibt einem User Berechtigungen."""
    guild_id_str = str(interaction.guild.id)
    user_id_str = str(user.id)
    
    if guild_id_str not in permissions["servers"]:
        permissions["servers"][guild_id_str] = {"users": {}}
    
    if user_id_str not in permissions["servers"][guild_id_str]["users"]:
        permissions["servers"][guild_id_str]["users"][user_id_str] = []
        
    if command == "all":
        permissions["servers"][guild_id_str]["users"][user_id_str] = [
            "ticket_setup", "panel_create", "panel_delete", "panel_list", "panel_send", "config_set", "config_show", "ai_keywords", "multipanel_create", "multipanel_list", "multipanel_delete", "multipanel_send"
        ]
    elif command not in permissions["servers"][guild_id_str]["users"][user_id_str]:
        permissions["servers"][guild_id_str]["users"][user_id_str].append(command)
        
    save_permissions(permissions)
    await interaction.response.send_message(f"<:4569ok:1459953782556463250> Berechtigung `{command}` für {user.mention} hinzugefügt!", ephemeral=True)

@bot.tree.command(name="permission_revoke", description="🔐 Entfernt einem User Berechtigungen")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(user="Der User", command="Der Command Name (oder 'all')")
async def permission_revoke(interaction: discord.Interaction, user: discord.Member, command: str):
    """Entfernt Berechtigungen."""
    guild_id_str = str(interaction.guild.id)
    user_id_str = str(user.id)
    
    if guild_id_str in permissions["servers"] and user_id_str in permissions["servers"][guild_id_str]["users"]:
        if command == "all":
            permissions["servers"][guild_id_str]["users"][user_id_str] = []
        elif command in permissions["servers"][guild_id_str]["users"][user_id_str]:
            permissions["servers"][guild_id_str]["users"][user_id_str].remove(command)
            
        save_permissions(permissions)
        await interaction.response.send_message(f"<:4569ok:1459953782556463250> Berechtigung `{command}` für {user.mention} entfernt!", ephemeral=True)
    else:
        await interaction.response.send_message("<:4934error:1459953806870708388> User hat keine konfigurierten Berechtigungen.", ephemeral=True)

@bot.tree.command(name="permission_list", description="📋 Zeigt alle Berechtigungen")
@app_commands.checks.has_permissions(administrator=True)
async def permission_list(interaction: discord.Interaction):
    """Listet alle Berechtigungen auf."""
    guild_id_str = str(interaction.guild.id)
    if guild_id_str not in permissions["servers"] or not permissions["servers"][guild_id_str].get("users"):
        await interaction.response.send_message("<:4934error:1459953806870708388> Keine Berechtigungen konfiguriert!", ephemeral=True)
        return

    embed = discord.Embed(title="Berechtigungen", color=get_color(interaction.guild.id, "info"))
    for user_id, commands in permissions["servers"][guild_id_str]["users"].items():
        if commands:
            user = interaction.guild.get_member(int(user_id))
            user_display = user.name if user else f"Unknown ({user_id})"
            embed.add_field(name=f"<:Admin:1458137140025360478> {user_display}", value=", ".join([f"`{cmd}`" for cmd in commands]), inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Bot Events ---

@bot.event
async def on_ready():
    """Bot ist bereit."""
    print("═" * 50)
    print(f"✅ Bot ist online: {bot.user.name}")
    print(f"📊 Discord.py Version: {discord.__version__}")
    print(f"🔗 Verbunden mit {len(bot.guilds)} Server(n)")
    
    for guild in bot.guilds:
        get_server_config(guild.id)
        print(f"   ├─ {guild.name} (ID: {guild.id})")

    print("═" * 50)
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} Slash Commands synchronisiert")
        print("═" * 50)
    except Exception as e:
        print(f"<:4934error:1459953806870708388> Fehler beim Synchronisieren: {e}")

@bot.event
async def on_guild_join(guild: discord.Guild):
    print(f"✅ Bot beigetreten: {guild.name} (ID: {guild.id})")
    get_server_config(guild.id)

@bot.event
async def on_guild_remove(guild: discord.Guild):
    print(f"⚠️ Bot entfernt: {guild.name} (ID: {guild.id})")

# --- Error Handlers ---
@ticket_setup.error
@panel_create.error
@panel_delete.error
@panel_list.error
@multipanel_create.error
@multipanel_list.error
@multipanel_delete.error
@multipanel_send.error
@add.error
@remove.error
@config_set.error
@config_show.error
@permission_grant.error
@permission_revoke.error
@permission_list.error
async def command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions) or isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("<:4934error:1459953806870708388> Keine Berechtigung!", ephemeral=True)
    else:
        await interaction.response.send_message(f"<:4934error:1459953806870708388> Fehler: {str(error)}", ephemeral=True)

# --- Bot Start ---
if __name__ == "__main__":
    bot_token = os.environ.get("DISCORD_BOT_TOKEN") or config.get("bot_token", "")
    if not bot_token or bot_token == "DEIN_BOT_TOKEN_HIER" or bot_token == "":
        print("❌ FEHLER: Kein Bot-Token gefunden!")
        if os.environ.get("REPLIT_SLUG"):
            print("💡 Tipp: Trage deinen Token in der Datei 'ticket_config.json' bei 'bot_token' ein.")

        async def run_health_only():
            await start_health_server()
            while True:
                await asyncio.sleep(3600)

        try:
            asyncio.run(run_health_only())
        except KeyboardInterrupt:
            pass
        exit(1)

    try:
        port = int(os.environ.get("PORT", 5000))
        async def run_bot():
            await start_health_server()
            async with bot:
                await bot.start(bot_token)
        asyncio.run(run_bot())
    except Exception as e:
        print(f"❌ Kritischer Fehler beim Starten des Bots: {e}")
