from __future__ import absolute_import, division, print_function, unicode_literals

import asyncio
import io
import os
import threading

import discord
from discord import app_commands
from discord.ext import commands


def flatten_files(files_dict, prefix=""):
    result = []
    for name, data in sorted(files_dict.items()):
        if data.get("type") == "folder":
            children = data.get("children", {})
            result.extend(flatten_files(children, prefix + name + "/"))
        elif data.get("type") == "machinecode" or data.get("type") == "model":
            result.append({
                "name": data.get("name", name),
                "path": prefix + name,
                "size": data.get("size", 0),
                "type": data.get("type", "unknown"),
            })
    return result


class DiscordBot:

    def __init__(self, plugin):
        self.plugin = plugin
        self._logger = plugin._logger
        self._printer = plugin._printer
        self._file_manager = plugin._file_manager
        self._settings = plugin._settings
        self._event_bus = plugin._event_bus

        self._loop = None
        self._thread = None
        self._bot = None
        self._ready_event = threading.Event()
        self._presence_task = None

    def start(self):
        token = self._settings.get(["bot_token"])
        if not token:
            self._logger.warning("Discord bot: No token configured")
            return

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_bot, args=(token,), daemon=True)
        self._thread.start()

    def _run_bot(self, token):
        asyncio.set_event_loop(self._loop)
        try:
            self._bot = self._build_bot()
            self._loop.run_until_complete(self._bot.start(token))
        except discord.LoginFailure:
            self._logger.error("Discord bot: Invalid token - login failed")
        except discord.PrivilegedIntentsRequired:
            self._logger.error(
                "Discord bot: Missing privileged intents. "
                "Enable MESSAGE CONTENT INTENT in Discord Developer Portal."
            )
        except Exception as e:
            self._logger.error("Discord bot error: {}".format(e))

    def stop(self):
        self._ready_event.clear()
        if self._bot and self._loop and not self._loop.is_closed():

            async def shutdown():
                try:
                    await self._bot.close()
                except Exception:
                    pass

            try:
                future = asyncio.run_coroutine_threadsafe(shutdown(), self._loop)
                future.result(timeout=10)
            except Exception:
                pass

        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop.close()

        self._bot = None

    def is_ready(self):
        return self._ready_event.is_set()

    def get_bot_user(self):
        if self._bot and self._bot.user:
            return self._bot.user
        return None

    def _build_bot(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True

        prefix = self._settings.get(["command_prefix"]) or "!"
        bot = commands.Bot(command_prefix=prefix, intents=intents)

        @bot.event
        async def on_ready():
            self._logger.info("Discord bot logged in as {} (ID: {})".format(bot.user, bot.user.id))
            try:
                await bot.tree.sync()
                self._logger.info("Slash commands synced successfully")
            except Exception as e:
                self._logger.error("Failed to sync slash commands: {}".format(e))
            self._ready_event.set()

            if self._settings.get(["rich_presence_enabled"]):
                self._presence_task = bot.loop.create_task(self._presence_updater())

        @bot.event
        async def on_message(message):
            if message.author.bot:
                return
            if not self._is_channel_allowed(message.channel.id):
                return
            if message.attachments and self._settings.get(["allow_file_upload"]):
                await self._handle_attachments(message)
            await bot.process_commands(message)

        self._register_commands(bot)
        return bot

    def _register_commands(self, bot):
        tree = bot.tree

        @tree.command(name="status", description="Zobrazí aktuální stav tiskárny")
        async def cmd_status(interaction: discord.Interaction):
            await self._cmd_status(interaction)

        @tree.command(name="print", description="Spustí tisk vybraného souboru")
        @app_commands.describe(filename="Název souboru k tisku")
        async def cmd_print(interaction: discord.Interaction, filename: str):
            await self._cmd_print(interaction, filename)

        @tree.command(name="pause", description="Pozastaví aktuální tisk")
        async def cmd_pause(interaction: discord.Interaction):
            await self._cmd_pause(interaction)

        @tree.command(name="resume", description="Obnoví pozastavený tisk")
        async def cmd_resume(interaction: discord.Interaction):
            await self._cmd_resume(interaction)

        @tree.command(name="cancel", description="Zruší aktuální tisk")
        async def cmd_cancel(interaction: discord.Interaction):
            await self._cmd_cancel(interaction)

        @tree.command(name="estop", description="Nouzové zastavení tiskárny (M112)")
        async def cmd_estop(interaction: discord.Interaction):
            await self._cmd_estop(interaction)

        @tree.command(name="home", description="Najet osami do výchozí pozice")
        @app_commands.describe(axes="Osy k najetí (all, xy, z, x, y)")
        async def cmd_home(interaction: discord.Interaction, axes: str = "all"):
            await self._cmd_home(interaction, axes)

        @tree.command(name="preheat", description="Předehřeje tiskárnu podle profilu")
        @app_commands.describe(profil="Název profilu (PLA, ABS, PETG, atd.)")
        async def cmd_preheat(interaction: discord.Interaction, profil: str):
            await self._cmd_preheat(interaction, profil)

        @tree.command(name="set_temp", description="Nastaví cílové teploty")
        @app_commands.describe(hotend="Teplota trysky (°C)", bed="Teplota podložky (°C)")
        async def cmd_set_temp(interaction: discord.Interaction, hotend: int = None, bed: int = None):
            await self._cmd_set_temp(interaction, hotend, bed)

        @tree.command(name="files", description="Zobrazí seznam souborů na tiskárně")
        async def cmd_files(interaction: discord.Interaction):
            await self._cmd_files(interaction)

        @tree.command(name="download", description="Stáhne soubor z tiskárny")
        @app_commands.describe(filename="Název souboru ke stažení")
        async def cmd_download(interaction: discord.Interaction, filename: str):
            await self._cmd_download(interaction, filename)

        @tree.command(name="delete", description="Smaže soubor z tiskárny")
        @app_commands.describe(filename="Název souboru ke smazání")
        async def cmd_delete(interaction: discord.Interaction, filename: str):
            await self._cmd_delete(interaction, filename)

        @tree.command(name="jog", description="Posune vybranou osou")
        @app_commands.describe(axis="Osa (x, y, z)", distance="Vzdálenost v mm", speed="Rychlost")
        async def cmd_jog(interaction: discord.Interaction, axis: str, distance: float = None, speed: int = None):
            await self._cmd_jog(interaction, axis, distance, speed)

        @tree.command(name="extrude", description="Extruduje nebo retraktuje filament")
        @app_commands.describe(length="Délka v mm (záporná = retrakce)", speed="Rychlost")
        async def cmd_extrude(interaction: discord.Interaction, length: float = None, speed: int = None):
            await self._cmd_extrude(interaction, length, speed)

        @tree.command(name="info", description="Zobrazí informace o tiskárně")
        async def cmd_info(interaction: discord.Interaction):
            await self._cmd_info(interaction)

        @tree.command(name="help", description="Zobrazí nápovědu k příkazům")
        async def cmd_help(interaction: discord.Interaction):
            await self._cmd_help(interaction)

        @tree.command(name="shutdown", description="Vypne systém (pouze admin)")
        async def cmd_shutdown(interaction: discord.Interaction):
            await self._cmd_shutdown(interaction)

    async def _presence_updater(self):
        await self._bot.wait_until_ready()
        while not self._bot.is_closed():
            try:
                if self._settings.get(["rich_presence_enabled"]):
                    await self._update_presence()
                elif self._bot.user and self._bot.activity:
                    await self._bot.change_presence(activity=None)
            except Exception as e:
                self._logger.debug("Presence update error: {}".format(e))
            interval = self._settings.get(["presence_update_interval"]) or 1
            interval = max(1, min(300, interval))
            await asyncio.sleep(interval)

    async def _update_presence(self):
        try:
            data = self._printer.get_current_data()
        except Exception:
            activity = discord.Activity(
                type=discord.ActivityType.playing,
                name="🔴 Tiskárna nedostupná",
            )
            try:
                await self._bot.change_presence(activity=activity)
            except Exception:
                pass
            return

        state = data.get("state", {})
        text = state.get("text", "Neznámý")
        flags = state.get("flags", {})

        temps = data.get("temperature", {})
        tool0 = temps.get("tool0", {})
        bed = temps.get("bed", {})

        hotend_actual = tool0.get("actual", 0)
        hotend_target = tool0.get("target", 0)
        bed_actual = bed.get("actual", 0)
        bed_target = bed.get("target", 0)

        progress = data.get("progress", {})
        completion = progress.get("completion", 0) or 0
        print_time_left = progress.get("printTimeLeft", 0) or 0
        current_file = data.get("job", {}).get("file", {}).get("name", "")

        if flags.get("printing"):
            m, s = divmod(int(print_time_left), 60)
            h, m = divmod(m, 60)
            left_str = ""
            if h:
                left_str = "{:d}h{:02d}m".format(h, m)
            elif m:
                left_str = "{:d}m".format(m)
            else:
                left_str = ""

            parts = ["🖨️ {}".format(current_file[:40])]
            if completion > 0:
                parts.append("{:.0f}%".format(completion))
            if left_str:
                parts.append("⏱{}".format(left_str))
            parts.append("🔥{:.0f}°C 🛏{:.0f}°C".format(hotend_actual, bed_actual))

            name = " • ".join(parts)

            activity = discord.Activity(
                type=discord.ActivityType.playing,
                name=name[:128],
            )

        elif flags.get("paused"):
            parts = ["⏸️ Pozastaveno"]
            if current_file:
                parts.append(current_file[:30])
            parts.append("🔥{:.0f}°C 🛏{:.0f}°C".format(hotend_actual, bed_actual))
            name = " • ".join(parts)

            activity = discord.Activity(
                type=discord.ActivityType.playing,
                name=name[:128],
            )

        elif text in ("Operational", "Připraven"):
            parts = ["🟢 Připraven"]
            if hotend_target > 0 or bed_target > 0:
                parts.append("🔥{:.0f}/{:.0f}°C 🛏{:.0f}/{:.0f}°C".format(
                    hotend_actual, hotend_target, bed_actual, bed_target
                ))
            elif hotend_actual > 30:
                parts.append("🔥{:.0f}°C 🛏{:.0f}°C".format(hotend_actual, bed_actual))
            name = " • ".join(parts)

            activity = discord.Activity(
                type=discord.ActivityType.playing,
                name=name[:128],
            )

        else:
            activity = discord.Activity(
                type=discord.ActivityType.playing,
                name="3D tiskárna - {}".format(text),
            )

        try:
            await self._bot.change_presence(activity=activity)
        except Exception:
            pass

    def _is_admin(self, user_id):
        admin_ids = self._settings.get(["admin_user_ids"]).strip()
        if not admin_ids:
            return False
        return str(user_id) in [x.strip() for x in admin_ids.split(",")]

    def _has_allowed_role(self, member):
        if not self._settings.get(["require_role_for_commands"]):
            return True
        role_ids = self._settings.get(["allowed_role_ids"]).strip()
        if not role_ids:
            return True
        allowed = [int(x.strip()) for x in role_ids.split(",") if x.strip().isdigit()]
        if not allowed:
            return True
        return any(role.id in allowed for role in member.roles)

    def _is_channel_allowed(self, channel_id):
        channel_ids = self._settings.get(["channel_ids"]).strip()
        if not channel_ids:
            return True
        allowed = [int(x.strip()) for x in channel_ids.split(",") if x.strip().isdigit()]
        if not allowed:
            return True
        return channel_id in allowed

    def _get_response_lang(self, key, *args):
        lang = self._settings.get(["language"])
        strings = {
            "cs": {
                "no_permission": "Nemáš oprávnění pro tento příkaz.",
                "not_printing": "Tiskárna právě netiskne.",
                "already_printing": "Tiskárna již tiskne.",
                "paused": "Tisk byl pozastaven.",
                "resumed": "Tisk byl obnoven.",
                "cancelled": "Tisk byl zrušen.",
                "estop_sent": "Nouzové zastavení (M112) odesláno!",
                "file_not_found": "Soubor `{}` nebyl nalezen.",
                "print_started": "Tisk `{}` byl spuštěn.",
                "no_file_selected": "Není vybrán žádný soubor k tisku.",
                "temp_set": "Teploty nastaveny: tryska {}°C, podložka {}°C",
                "preheat_set": "Předehřev `{}`: tryska {}°C, podložka {}°C",
                "profile_not_found": "Profil `{}` nebyl nalezen. Dostupné: {}",
                "home_done": "Najetí os {} dokončeno.",
                "file_deleted": "Soubor `{}` smazán.",
                "file_uploaded": "Soubor `{}` nahrán ({}).",
                "file_too_large": "Soubor je příliš velký (max {} MB).",
                "ext_denied": "Přípona `{}` není povolena. Povolené: {}",
                "shutdown_warning": "Vypínání systému...",
                "jog_done": "Osa {} posunuta o {} mm.",
                "extrude_done": "Extrudováno {} mm filamentu.",
                "select_profile": "Vyber profil:",
                "waiting": "Prosím čekejte...",
                "error_occurred": "Chyba: {}",
            },
            "en": {
                "no_permission": "You don't have permission to use this command.",
                "not_printing": "Printer is not currently printing.",
                "already_printing": "Printer is already printing.",
                "paused": "Print has been paused.",
                "resumed": "Print has been resumed.",
                "cancelled": "Print has been cancelled.",
                "estop_sent": "Emergency stop (M112) sent!",
                "file_not_found": "File `{}` not found.",
                "print_started": "Print of `{}` has started.",
                "no_file_selected": "No file selected for printing.",
                "temp_set": "Temperatures set: hotend {}°C, bed {}°C",
                "preheat_set": "Preheat `{}`: hotend {}°C, bed {}°C",
                "profile_not_found": "Profile `{}` not found. Available: {}",
                "home_done": "Homing of {} completed.",
                "file_deleted": "File `{}` deleted.",
                "file_uploaded": "File `{}` uploaded ({}).",
                "file_too_large": "File is too large (max {} MB).",
                "ext_denied": "Extension `{}` is not allowed. Allowed: {}",
                "shutdown_warning": "Shutting down system...",
                "jog_done": "Axis {} moved by {} mm.",
                "extrude_done": "Extruded {} mm of filament.",
                "select_profile": "Select profile:",
                "waiting": "Please wait...",
                "error_occurred": "Error: {}",
            },
        }
        s = strings.get(lang, strings["cs"]).get(key, key)
        if args:
            try:
                return s.format(*args)
            except (KeyError, IndexError):
                return s
        return s

    def _t(self, key, *args):
        s = self._get_response_lang(key)
        if args:
            try:
                return s.format(*args)
            except (KeyError, IndexError):
                return s
        return s

    async def _safe_respond(self, interaction, content=None, embed=None, ephemeral=False):
        kwargs = {}
        if content:
            kwargs["content"] = content
        if embed:
            kwargs["embed"] = embed
        if ephemeral:
            kwargs["ephemeral"] = True

        try:
            if interaction.response.is_done():
                await interaction.followup.send(**kwargs)
            else:
                await interaction.response.send_message(**kwargs)
        except discord.NotFound:
            self._logger.warning("Interaction channel not found")
        except discord.Forbidden:
            self._logger.warning("Bot lacks permissions to send message")
        except Exception as e:
            self._logger.error("Failed to send message: {}".format(e))

    def _check_permissions(self, interaction):
        if not self._is_channel_allowed(interaction.channel_id):
            return False
        if interaction.user and not self._has_allowed_role(interaction.user):
            return False
        return True

    async def _cmd_status(self, interaction):
        if not self._check_permissions(interaction):
            await self._safe_respond(interaction, self._t("no_permission"), ephemeral=True)
            return

        await interaction.response.defer()
        try:
            data = self._printer.get_current_data()
            state = data.get("state", {})
            text = state.get("text", "Neznámý")
            flags = state.get("flags", {})

            temps = data.get("temperature", {})
            tool0 = temps.get("tool0", {})
            bed = temps.get("bed", {})

            hotend_actual = tool0.get("actual", 0)
            hotend_target = tool0.get("target", 0)
            bed_actual = bed.get("actual", 0)
            bed_target = bed.get("target", 0)

            progress = data.get("progress", {})
            completion = progress.get("completion", 0) or 0
            print_time = progress.get("printTime", 0) or 0
            print_time_left = progress.get("printTimeLeft", 0) or 0

            current_file = data.get("job", {}).get("file", {}).get("name", "Žádný")

            status_icon = {
                "Printing": ":arrow_forward:",
                "Operational": ":white_circle:",
                "Pausing": ":pause_button:",
                "Paused": ":pause_button:",
                "Cancelling": ":x:",
                "Error": ":warning:",
                "Offline": ":zzz:",
                "Offline after error": ":warning:",
            }.get(text, ":grey_question:")

            embed = discord.Embed(
                title="{} Stav tiskárny".format(status_icon),
                color=discord.Color.green() if flags.get("printing") else discord.Color.blue(),
            )
            embed.add_field(name="Stav", value=text, inline=True)
            embed.add_field(name="Soubor", value=current_file, inline=True)

            embed.add_field(
                name="Tryska",
                value="{:.1f}°C / {:.1f}°C".format(hotend_actual, hotend_target),
                inline=True,
            )
            embed.add_field(
                name="Podložka",
                value="{:.1f}°C / {:.1f}°C".format(bed_actual, bed_target),
                inline=True,
            )

            if flags.get("printing"):
                embed.add_field(
                    name="Hotovo",
                    value="{:.1f}%".format(completion),
                    inline=True,
                )
                m, s = divmod(int(print_time), 60)
                h, m = divmod(m, 60)
                time_str = "{:d}h {:02d}m {:02d}s".format(h, m, s) if h else "{:d}m {:02d}s".format(m, s)
                embed.add_field(name="Čas tisku", value=time_str, inline=True)

                m, s = divmod(int(print_time_left), 60)
                h, m = divmod(m, 60)
                left_str = "{:d}h {:02d}m {:02d}s".format(h, m, s) if h else "{:d}m {:02d}s".format(m, s)
                embed.add_field(name="Zbývá", value=left_str, inline=True)

            if self._settings.get(["show_status_in_presence"]):
                try:
                    activity = discord.Activity(
                        type=discord.ActivityType.watching,
                        name="3D tisk - {}".format(text),
                    )
                    await self._bot.change_presence(activity=activity)
                except Exception:
                    pass

            await self._safe_respond(interaction, embed=embed)
        except Exception as e:
            self._logger.error("Status command error: {}".format(e))
            await self._safe_respond(interaction, self._t("error_occurred", error=str(e)), ephemeral=True)

    async def _cmd_print(self, interaction, filename):
        if not self._check_permissions(interaction):
            await self._safe_respond(interaction, self._t("no_permission"), ephemeral=True)
            return

        await interaction.response.defer()
        try:
            files_data = self._file_manager.list_files()
            local_files = files_data.get("local", {})
            all_files = flatten_files(local_files)

            found = None
            for f in all_files:
                if f["name"] == filename or f["path"] == filename:
                    found = f
                    break

            if not found:
                await self._safe_respond(interaction, self._t("file_not_found", filename))
                return

            self._printer.select_file(found["path"], printAfterSelect=True)
            await self._safe_respond(interaction, self._t("print_started", filename))

        except Exception as e:
            self._logger.error("Print command error: {}".format(e))
            await self._safe_respond(interaction, self._t("error_occurred", error=str(e)), ephemeral=True)

    async def _cmd_pause(self, interaction):
        if not self._check_permissions(interaction):
            await self._safe_respond(interaction, self._t("no_permission"), ephemeral=True)
            return
        try:
            data = self._printer.get_current_data()
            if not data.get("state", {}).get("flags", {}).get("printing"):
                await self._safe_respond(interaction, self._t("not_printing"), ephemeral=True)
                return
            self._printer.pause_print()
            await self._safe_respond(interaction, self._t("paused"))
        except Exception as e:
            await self._safe_respond(interaction, self._t("error_occurred", error=str(e)), ephemeral=True)

    async def _cmd_resume(self, interaction):
        if not self._check_permissions(interaction):
            await self._safe_respond(interaction, self._t("no_permission"), ephemeral=True)
            return
        try:
            self._printer.resume_print()
            await self._safe_respond(interaction, self._t("resumed"))
        except Exception as e:
            await self._safe_respond(interaction, self._t("error_occurred", error=str(e)), ephemeral=True)

    async def _cmd_cancel(self, interaction):
        if not self._check_permissions(interaction):
            await self._safe_respond(interaction, self._t("no_permission"), ephemeral=True)
            return
        try:
            self._printer.cancel_print()
            await self._safe_respond(interaction, self._t("cancelled"))
        except Exception as e:
            await self._safe_respond(interaction, self._t("error_occurred", error=str(e)), ephemeral=True)

    async def _cmd_estop(self, interaction):
        if not self._check_permissions(interaction):
            await self._safe_respond(interaction, self._t("no_permission"), ephemeral=True)
            return
        try:
            self._printer.commands("M112")
            await self._safe_respond(interaction, self._t("estop_sent"))
        except Exception as e:
            await self._safe_respond(interaction, self._t("error_occurred", error=str(e)), ephemeral=True)

    async def _cmd_home(self, interaction, axes):
        if not self._check_permissions(interaction):
            await self._safe_respond(interaction, self._t("no_permission"), ephemeral=True)
            return

        await interaction.response.defer()
        try:
            axis_map = {
                "all": ["x", "y", "z"],
                "xy": ["x", "y"],
                "x": ["x"],
                "y": ["y"],
                "z": ["z"],
            }
            to_home = axis_map.get(axes.lower(), None)
            if to_home is None:
                await self._safe_respond(
                    interaction,
                    "Neplatná volba os. Použij: all, xy, x, y, z",
                    ephemeral=True,
                )
                return
            self._printer.home(to_home)
            await self._safe_respond(interaction, self._t("home_done", axes.upper()))
        except Exception as e:
            await self._safe_respond(interaction, self._t("error_occurred", error=str(e)), ephemeral=True)

    async def _cmd_preheat(self, interaction, profil):
        if not self._check_permissions(interaction):
            await self._safe_respond(interaction, self._t("no_permission"), ephemeral=True)
            return

        await interaction.response.defer()
        try:
            profiles = self._settings.get(["preheat_profiles"])
            match = None
            for p in profiles:
                if p["name"].lower() == profil.lower():
                    match = p
                    break

            if not match:
                available = ", ".join(p["name"] for p in profiles)
                await self._safe_respond(
                    interaction,
                    self._t("profile_not_found", profil, available),
                    ephemeral=True,
                )
                return

            self._printer.set_temperature("tool0", match["hotend_temp"])
            self._printer.set_temperature("bed", match["bed_temp"])
            await self._safe_respond(
                interaction,
                self._t("preheat_set", profil, match["hotend_temp"], match["bed_temp"]),
            )
        except Exception as e:
            await self._safe_respond(interaction, self._t("error_occurred", error=str(e)), ephemeral=True)

    async def _cmd_set_temp(self, interaction, hotend, bed):
        if not self._check_permissions(interaction):
            await self._safe_respond(interaction, self._t("no_permission"), ephemeral=True)
            return

        if hotend is None and bed is None:
            await self._safe_respond(
                interaction,
                "Musíš zadat alespoň jednu teplotu. Příkaz: `/set_temp hotend:210 bed:60`",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        try:
            if hotend is not None:
                self._printer.set_temperature("tool0", hotend)
            if bed is not None:
                self._printer.set_temperature("bed", bed)
            await self._safe_respond(
                interaction,
                self._t("temp_set", hotend or "---", bed or "---"),
            )
        except Exception as e:
            await self._safe_respond(interaction, self._t("error_occurred", error=str(e)), ephemeral=True)

    async def _cmd_files(self, interaction):
        if not self._check_permissions(interaction):
            await self._safe_respond(interaction, self._t("no_permission"), ephemeral=True)
            return

        await interaction.response.defer()
        try:
            files_data = self._file_manager.list_files()
            local_files = files_data.get("local", {})
            all_files = flatten_files(local_files)

            if not all_files:
                await self._safe_respond(interaction, "Na tiskárně nejsou žádné soubory.")
                return

            lines = []
            for i, f in enumerate(all_files, 1):
                size_kb = f["size"] / 1024
                if size_kb > 1024:
                    size_str = "{:.1f} MB".format(size_kb / 1024)
                else:
                    size_str = "{:.1f} KB".format(size_kb)
                lines.append("`{}` - {}".format(f["path"], size_str))

            chunks = []
            chunk = []
            for line in lines:
                chunk.append(line)
                if len(chunk) >= 20:
                    chunks.append("\n".join(chunk))
                    chunk = []
            if chunk:
                chunks.append("\n".join(chunk))

            embed = discord.Embed(
                title=":open_file_folder: Soubory na tiskárně ({} celkem)".format(len(all_files)),
                color=discord.Color.blue(),
            )
            for i, chunk in enumerate(chunks):
                embed.add_field(
                    name="Strana {}".format(i + 1) if len(chunks) > 1 else "\u200b",
                    value=chunk,
                    inline=False,
                )

            await self._safe_respond(interaction, embed=embed)
        except Exception as e:
            self._logger.error("Files command error: {}".format(e))
            await self._safe_respond(interaction, self._t("error_occurred", error=str(e)), ephemeral=True)

    async def _cmd_download(self, interaction, filename):
        if not self._check_permissions(interaction):
            await self._safe_respond(interaction, self._t("no_permission"), ephemeral=True)
            return

        await interaction.response.defer()
        try:
            files_data = self._file_manager.list_files()
            local_files = files_data.get("local", {})
            all_files = flatten_files(local_files)

            found = None
            for f in all_files:
                if f["name"] == filename or f["path"] == filename:
                    found = f
                    break

            if not found:
                await self._safe_respond(interaction, self._t("file_not_found", filename))
                return

            disk_path = self._file_manager.path_on_disk(("local", found["path"]))
            if not os.path.isfile(disk_path):
                await self._safe_respond(interaction, self._t("file_not_found", filename), ephemeral=True)
                return

            file_size = os.path.getsize(disk_path)
            if file_size > 25 * 1024 * 1024:
                await self._safe_respond(
                    interaction,
                    "Soubor je příliš velký pro přímé stažení přes Discord (max 25 MB).",
                    ephemeral=True,
                )
                return

            await self._safe_respond(
                interaction,
                "Stahuji soubor `{}`...".format(found["path"]),
            )

            with open(disk_path, "rb") as fh:
                discord_file = discord.File(fh, filename=found["name"])

            if interaction.response.is_done():
                await interaction.followup.send(file=discord_file)
            else:
                await interaction.response.send_message(file=discord_file)

        except Exception as e:
            self._logger.error("Download command error: {}".format(e))
            await self._safe_respond(interaction, self._t("error_occurred", error=str(e)), ephemeral=True)

    async def _cmd_delete(self, interaction, filename):
        if not self._check_permissions(interaction):
            await self._safe_respond(interaction, self._t("no_permission"), ephemeral=True)
            return

        await interaction.response.defer()
        try:
            files_data = self._file_manager.list_files()
            local_files = files_data.get("local", {})
            all_files = flatten_files(local_files)

            found = None
            for f in all_files:
                if f["name"] == filename or f["path"] == filename:
                    found = f
                    break

            if not found:
                await self._safe_respond(interaction, self._t("file_not_found", filename))
                return

            self._file_manager.remove_file(("local", found["path"]))
            await self._safe_respond(interaction, self._t("file_deleted", found["path"]))
        except Exception as e:
            self._logger.error("Delete command error: {}".format(e))
            await self._safe_respond(interaction, self._t("error_occurred", error=str(e)), ephemeral=True)

    async def _cmd_jog(self, interaction, axis, distance, speed):
        if not self._check_permissions(interaction):
            await self._safe_respond(interaction, self._t("no_permission"), ephemeral=True)
            return

        await interaction.response.defer()
        try:
            axis = axis.lower()
            if axis not in ("x", "y", "z"):
                await self._safe_respond(interaction, "Neplatná osa. Použij: x, y, z", ephemeral=True)
                return

            if distance is None:
                distance = self._settings.get(["jog_distance"]) or 10

            kwargs = {"relative": True}
            kwargs[axis] = distance
            if speed:
                kwargs["speed"] = speed

            self._printer.jog_axes(**kwargs)
            await self._safe_respond(interaction, self._t("jog_done", axis.upper(), distance))
        except Exception as e:
            await self._safe_respond(interaction, self._t("error_occurred", error=str(e)), ephemeral=True)

    async def _cmd_extrude(self, interaction, length, speed):
        if not self._check_permissions(interaction):
            await self._safe_respond(interaction, self._t("no_permission"), ephemeral=True)
            return

        await interaction.response.defer()
        try:
            if length is None:
                length = self._settings.get(["extrude_length"]) or 100
            if speed is None:
                speed = self._settings.get(["extrude_speed"]) or 100

            self._printer.extrude(length, speed=speed)
            action = "Extrudováno" if length >= 0 else "Retraktováno"
            await self._safe_respond(interaction, "{} {} mm filamentu.".format(action, abs(length)))
        except Exception as e:
            await self._safe_respond(interaction, self._t("error_occurred", error=str(e)), ephemeral=True)

    async def _cmd_info(self, interaction):
        if not self._check_permissions(interaction):
            await self._safe_respond(interaction, self._t("no_permission"), ephemeral=True)
            return

        await interaction.response.defer()
        try:
            firmware_info = ""
            try:
                data = self._printer.get_current_data()
                firmware_info = data.get("state", {}).get("text", "Neznámý")
            except Exception:
                pass

            embed = discord.Embed(
                title=":information_source: Informace o tiskárně",
                color=discord.Color.blue(),
            )

            disk_info = self._file_manager.get_storage("local")
            if disk_info:
                free = disk_info.get("free", 0) / (1024 * 1024 * 1024)
                total = disk_info.get("total", 0) / (1024 * 1024 * 1024)
                embed.add_field(
                    name="Úložiště",
                    value="Celkem: {:.1f} GB\nVolné: {:.1f} GB".format(total, free),
                    inline=True,
                )

            embed.add_field(name="Stav", value=firmware_info, inline=True)
            embed.add_field(
                name="Bot",
                value="{} ({} příkazů)".format(
                    self._bot.user.name if self._bot and self._bot.user else "?",
                    len(self._bot.tree.get_commands()) if self._bot else 0,
                ),
                inline=False,
            )

            await self._safe_respond(interaction, embed=embed)
        except Exception as e:
            await self._safe_respond(interaction, self._t("error_occurred", error=str(e)), ephemeral=True)

    async def _cmd_help(self, interaction):
        if not self._check_permissions(interaction):
            await self._safe_respond(interaction, self._t("no_permission"), ephemeral=True)
            return

        embed = discord.Embed(
            title=":robot: Discord Upload - Nápověda",
            description="Ovládej svou 3D tiskárnu přes Discord!",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name=":arrow_forward: Ovládání tisku",
            value=(
                "`/print <file>` - Spustí tisk\n"
                "`/pause` - Pozastaví tisk\n"
                "`/resume` - Obnoví tisk\n"
                "`/cancel` - Zruší tisk\n"
                "`/estop` - Nouzové zastavení"
            ),
            inline=False,
        )
        embed.add_field(
            name=":thermometer: Teploty",
            value=(
                "`/preheat <profil>` - Předehřeje (PLA, ABS, atd.)\n"
                "`/set_temp hotend:210 bed:60` - Ruční nastavení"
            ),
            inline=False,
        )
        embed.add_field(
            name=":file_folder: Soubory",
            value=(
                "`/files` - Seznam souborů\n"
                "`/download <file>` - Stáhne soubor\n"
                "`/delete <file>` - Smaže soubor\n"
                "Pošli soubor v chatu - Nahraje na tiskárnu"
            ),
            inline=False,
        )
        embed.add_field(
            name=":joystick: Ovládání",
            value=(
                "`/home` - Najet do výchozí pozice\n"
                "`/jog axis:x distance:10` - Posun osou\n"
                "`/extrude length:100` - Extrudovat filament\n"
                "`/status` - Stav tiskárny\n"
                "`/info` - Info o tiskárně"
            ),
            inline=False,
        )
        embed.set_footer(text="Použij `/shutdown` pro vypnutí (pouze admin)")

        await self._safe_respond(interaction, embed=embed)

    async def _cmd_shutdown(self, interaction):
        if not self._is_admin(interaction.user.id):
            await self._safe_respond(
                interaction,
                "Pouze admin může použít tento příkaz.",
                ephemeral=True,
            )
            return
        await self._safe_respond(interaction, self._t("shutdown_warning"))
        try:
            self._printer.commands("M81")
        except Exception:
            pass

    async def _handle_attachments(self, message):
        allowed_exts = [
            e.strip().lower()
            for e in self._settings.get(["allowed_extensions"]).split(",")
            if e.strip()
        ]
        max_size_mb = self._settings.get(["max_file_size_mb"]) or 100
        max_size_bytes = max_size_mb * 1024 * 1024

        uploaded = []
        errors = []

        for attachment in message.attachments:
            ext = os.path.splitext(attachment.filename)[1].lower().lstrip(".")
            if ext not in allowed_exts:
                errors.append(
                    self._t("ext_denied", ext, ", ".join(allowed_exts))
                )
                continue

            if attachment.size > max_size_bytes:
                errors.append(
                    self._t("file_too_large", max_size_mb)
                )
                continue

            try:
                file_bytes = await attachment.read()
                file_obj = io.BytesIO(file_bytes)
                file_obj.filename = attachment.filename

                self._file_manager.add_file(
                    "local",
                    attachment.filename,
                    file_obj,
                    allow_overwrite=True,
                )

                size_kb = attachment.size / 1024
                if size_kb > 1024:
                    size_str = "{:.1f} MB".format(size_kb / 1024)
                else:
                    size_str = "{:.1f} KB".format(size_kb)
                uploaded.append(self._t("file_uploaded", attachment.filename, size_str))
            except Exception as e:
                self._logger.error("Upload error for {}: {}".format(attachment.filename, e))
                errors.append("Nahrávání `{}` selhalo: {}".format(attachment.filename, str(e)))

        if uploaded:
            await message.channel.send("\n".join(uploaded))
        if errors:
            await message.channel.send("\n".join(errors))

    def send_to_notify_channel(self, text):
        channel_id = self._settings.get(["notify_channel_id"])
        if not channel_id or not channel_id.strip():
            return
        try:
            channel_id = int(channel_id.strip())
        except ValueError:
            return

        if not self._bot or not self._loop or self._loop.is_closed():
            return

        async def _send():
            try:
                channel = self._bot.get_channel(channel_id)
                if channel:
                    await channel.send(text)
            except Exception as e:
                self._logger.error("Failed to send notification: {}".format(e))

        asyncio.run_coroutine_threadsafe(_send(), self._loop)
