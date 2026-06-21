from __future__ import absolute_import, division, print_function, unicode_literals

import octoprint.plugin


class DiscordBotPlugin(
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.ShutdownPlugin,
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.SimpleApiPlugin,
    octoprint.plugin.EventHandlerPlugin,
):

    def __init__(self):
        self.discord_bot = None
        self._bot_import_error = None
        self._DiscordBot = None

    def initialize(self):
        self._try_import_bot()

    def _try_import_bot(self):
        try:
            from .discord_bot import DiscordBot
            self._DiscordBot = DiscordBot
            self._bot_import_error = None
        except ImportError as e:
            self._bot_import_error = str(e)
            self._logger.warning(
                "Discord.py is not installed. Discord bot functionality disabled. "
                "Run: pip install discord.py"
            )
        except Exception as e:
            self._bot_import_error = str(e)
            self._logger.error("Failed to import DiscordBot: {}".format(e))

    def on_after_startup(self):
        self._logger.info("Discord Bot Plugin starting...")
        self._start_bot()

    def on_settings_initialized(self):
        self._logger.info("Discord Bot Plugin settings initialized")
        self._start_bot()

    def on_shutdown(self):
        self._stop_bot()

    def on_settings_save(self, data):
        old_token = self._settings.get(["bot_token"])
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        new_token = self._settings.get(["bot_token"])
        if old_token != new_token:
            self._logger.info("Bot token changed, restarting bot...")
            self._stop_bot()
            self._start_bot()

    def _start_bot(self):
        if self._bot_import_error:
            self._logger.warning(
                "Cannot start Discord bot: {}".format(self._bot_import_error)
            )
            return

        if self._DiscordBot is None:
            self._try_import_bot()
            if self._DiscordBot is None:
                return

        token = self._settings.get(["bot_token"])
        if token:
            try:
                self.discord_bot = self._DiscordBot(self)
                self.discord_bot.start()
            except Exception as e:
                self._logger.error("Failed to start Discord bot: {}".format(e))
                self.discord_bot = None
        else:
            self._logger.warning(
                "No Discord bot token configured - plugin loaded but inactive. "
                "Configure it in Settings > Discord Bot."
            )

    def _stop_bot(self):
        if self.discord_bot:
            try:
                self.discord_bot.stop()
            except Exception as e:
                self._logger.error("Error stopping bot: {}".format(e))
            self.discord_bot = None

    def get_settings_defaults(self):
        return {
            "bot_token": "",
            "channel_ids": "",
            "allowed_role_ids": "",
            "admin_user_ids": "",
            "command_prefix": "!",
            "preheat_profiles": [
                {"name": "PLA", "hotend_temp": 210, "bed_temp": 60},
                {"name": "ABS", "hotend_temp": 240, "bed_temp": 100},
                {"name": "PETG", "hotend_temp": 235, "bed_temp": 80},
                {"name": "TPU", "hotend_temp": 220, "bed_temp": 60},
                {"name": "ASA", "hotend_temp": 250, "bed_temp": 95},
                {"name": "PC", "hotend_temp": 270, "bed_temp": 105},
            ],
            "notify_on_completion": True,
            "notify_on_error": True,
            "auto_remove_after_print": False,
            "allowed_extensions": "gcode,gco,g,GCODE,stl,obj,3mf",
            "notify_channel_id": "",
            "language": "cs",
            "show_status_in_presence": True,
            "rich_presence_enabled": True,
            "presence_update_interval": 1,
            "require_role_for_commands": False,
            "allow_file_upload": True,
            "max_file_size_mb": 100,
            "jog_distance": 10,
            "extrude_length": 100,
            "extrude_speed": 100,
        }

    def get_settings_version(self):
        return 1

    def get_template_configs(self):
        return [
            dict(type="settings", name="Discord Bot", custom_bindings=True)
        ]

    def get_assets(self):
        return dict(
            js=["js/octoprint_discordbot.js"],
            css=["css/octoprint_discordbot.css"],
        )

    def get_api_commands(self):
        return dict(
            restart_bot=[],
            test_bot=[],
        )

    def on_api_command(self, command, data):
        from flask import jsonify

        if command == "restart_bot":
            self._stop_bot()
            self._start_bot()
            if self.discord_bot:
                return jsonify(success=True, message="Bot byl restartován")
            return jsonify(success=False, message="Nepodařilo se spustit bota - zkontrolujte token")

        elif command == "test_bot":
            is_ready = self.discord_bot is not None and self.discord_bot.is_ready()
            if is_ready:
                return jsonify(
                    success=True,
                    message="Bot je připojen a aktivní",
                    bot_name=str(self.discord_bot.get_bot_user()),
                )
            else:
                return jsonify(
                    success=False,
                    message="Bot není připojen. Zkontrolujte token a restartujte bota.",
                )

        return jsonify(success=False, message="Neznámý příkaz")

    def on_event(self, event, payload):
        if not self.discord_bot or not self.discord_bot.is_ready():
            return

        if event == "PrintDone":
            if self._settings.get(["notify_on_completion"]):
                path = payload.get("path", "neznámý soubor")
                self.discord_bot.send_to_notify_channel(
                    ":white_check_mark: **Tisk dokončen!**\nSoubor: `{}`\nČas: {}s".format(
                        path, payload.get("time", "?")
                    )
                )
                if self._settings.get(["auto_remove_after_print"]):
                    try:
                        self._file_manager.remove_file(("local", path))
                        self.discord_bot.send_to_notify_channel(
                            ":wastebasket: Soubor `{}` byl smazán".format(path)
                        )
                    except Exception as e:
                        self._logger.error("Failed to remove file after print: {}".format(e))

        elif event == "PrintFailed":
            if self._settings.get(["notify_on_error"]):
                path = payload.get("path", "neznámý soubor")
                self.discord_bot.send_to_notify_channel(
                    ":x: **Tisk selhal!**\nSoubor: `{}`".format(path)
                )

        elif event == "PrintStarted":
            if self._settings.get(["notify_on_completion"]):
                path = payload.get("path", "neznámý soubor")
                self.discord_bot.send_to_notify_channel(
                    ":arrow_forward: **Tisk spuštěn!**\nSoubor: `{}`".format(path)
                )

        elif event == "Error":
            if self._settings.get(["notify_on_error"]):
                error = payload.get("error", "neznámá chyba")
                self.discord_bot.send_to_notify_channel(
                    ":warning: **Chyba tiskárny!**\n`{}`".format(error)
                )

    def get_update_information(self):
        return dict(
            discordbot=dict(
                displayName="Discord Bot",
                displayVersion=self._plugin_version,
                type="github_release",
                user="matejalbert",
                repo="OctoPrint-DiscordBot",
                current=self._plugin_version,
                pip="https://github.com/matejalbert/OctoPrint-DiscordBot/archive/{target_version}.zip",
            )
        )


__plugin_name__ = "Discord Bot"
__plugin_pythoncompat__ = ">=3.7,<4"
__plugin_implementation__ = DiscordBotPlugin()