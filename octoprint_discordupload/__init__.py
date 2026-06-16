from __future__ import absolute_import, division, print_function, unicode_literals

import octoprint.plugin
import flask
from .discord_bot import DiscordBot


class DiscordUploadPlugin(
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

    def on_after_startup(self):
        self._logger.info("Discord Upload Plugin starting...")
        self._start_bot()

    def on_shutdown(self):
        self._stop_bot()

    def on_settings_cleanup(self):
        self._stop_bot()
        self._start_bot()

    def on_settings_save(self, data):
        old_token = self._settings.get(["bot_token"])
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        new_token = self._settings.get(["bot_token"])
        if old_token != new_token:
            self._logger.info("Bot token changed, restarting bot...")
            self._stop_bot()
            self._start_bot()

    def _start_bot(self):
        token = self._settings.get(["bot_token"])
        if token:
            self.discord_bot = DiscordBot(self)
            self.discord_bot.start()
        else:
            self._logger.warning("No Discord bot token configured - plugin loaded but inactive. Configure it in settings.")

    def _stop_bot(self):
        if self.discord_bot:
            self.discord_bot.stop()
            self.discord_bot = None

    def get_settings_defaults(self):
        return {
            "bot_token": "",
            "channel_ids": "",
            "allowed_role_ids": "",
            "admin_user_ids": "",
            "command_prefix": "!",
            "use_slash_commands": True,
            "upload_path": "",
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
            dict(type="settings", name="Discord Upload", custom_bindings=True)
        ]

    def get_assets(self):
        return dict(
            js=["js/octoprint_discordupload.js"],
            css=["css/octoprint_discordupload.css"],
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
                    f":white_check_mark: **Tisk dokončen!**\nSoubor: `{path}`\nČas: {payload.get('time', '?')}s"
                )
                if self._settings.get(["auto_remove_after_print"]):
                    try:
                        self._file_manager.remove_file(("local", path))
                        self.discord_bot.send_to_notify_channel(f":wastebasket: Soubor `{path}` byl smazán")
                    except Exception as e:
                        self._logger.error(f"Failed to remove file after print: {e}")

        elif event == "PrintFailed":
            if self._settings.get(["notify_on_error"]):
                path = payload.get("path", "neznámý soubor")
                self.discord_bot.send_to_notify_channel(
                    f":x: **Tisk selhal!**\nSoubor: `{path}`"
                )

        elif event == "PrintStarted":
            if self._settings.get(["notify_on_completion"]):
                path = payload.get("path", "neznámý soubor")
                self.discord_bot.send_to_notify_channel(
                    f":arrow_forward: **Tisk spuštěn!**\nSoubor: `{path}`"
                )

        elif event == "Error":
            if self._settings.get(["notify_on_error"]):
                error = payload.get("error", "neznámá chyba")
                self.discord_bot.send_to_notify_channel(
                    f":warning: **Chyba tiskárny!**\n`{error}`"
                )

    def get_update_information(self):
        return dict(
            discordupload=dict(
                displayName="Discord Upload",
                displayVersion=self._plugin_version,
                type="github_release",
                user="outwo",
                repo="OctoPrint-DiscordBot",
                current=self._plugin_version,
                pip="https://github.com/outwo/OctoPrint-DiscordUpload/archive/{target_version}.zip",
            )
        )


__plugin_name__ = "Discord Upload"
__plugin_python__ = ">=3.7,<4"
__plugin_implementation__ = DiscordUploadPlugin()
