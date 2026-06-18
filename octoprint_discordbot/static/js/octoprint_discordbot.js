$(function () {
    function DiscordBotViewModel(parameters) {
        var self = this;
        self.settingsViewModel = parameters[0];

        self.currentTab = ko.observable(0);

        self.tabs = ko.observableArray([
            { name: gettext("Základní") },
            { name: gettext("Oprávnění") },
            { name: gettext("Nahrávání") },
            { name: gettext("Profily předehřevu") },
            { name: gettext("Upozornění") },
            { name: gettext("Ovládání") },
            { name: gettext("Stav bota") },
        ]);

        self.switchTab = function (tab, event) {
            var index = self.tabs.indexOf(tab);
            if (index >= 0) {
                self.currentTab(index);
            }
        };

        self.preheatProfiles = ko.observableArray([]);

        self._makeProfile = function (data) {
            var obs = {
                name: ko.observable(data.name || ""),
                hotend_temp: ko.observable(data.hotend_temp || 200),
                bed_temp: ko.observable(data.bed_temp || 60),
            };
            obs.displayLabel = ko.pureComputed(function () {
                var n = obs.name();
                var h = obs.hotend_temp();
                var b = obs.bed_temp();
                if (!n) return gettext("(nevyplněno)");
                return n + " - " + h + "°C / " + b + "°C";
            });
            return obs;
        };

        self.onBeforeBinding = function () {
            var profiles = self.settingsViewModel.settings.plugins.discordbot.preheat_profiles;
            var raw = profiles();
            var converted = [];
            for (var i = 0; i < raw.length; i++) {
                converted.push(self._makeProfile(raw[i]));
            }
            self.preheatProfiles(converted);

            self.preheatProfiles.subscribe(function (newVal) {
                var plain = [];
                for (var i = 0; i < newVal.length; i++) {
                    plain.push({
                        name: ko.unwrap(newVal[i].name),
                        hotend_temp: ko.unwrap(newVal[i].hotend_temp),
                        bed_temp: ko.unwrap(newVal[i].bed_temp),
                    });
                }
                profiles(plain);
            });
        };

        self.addPreheatProfile = function () {
            self.preheatProfiles.push(self._makeProfile({ name: "", hotend_temp: 200, bed_temp: 60 }));
        };

        self.removePreheatProfile = function (profile) {
            self.preheatProfiles.remove(profile);
        };

        self.resetPreheatProfiles = function () {
            var defaults = [
                self._makeProfile({ name: "PLA", hotend_temp: 210, bed_temp: 60 }),
                self._makeProfile({ name: "ABS", hotend_temp: 240, bed_temp: 100 }),
                self._makeProfile({ name: "PETG", hotend_temp: 235, bed_temp: 80 }),
                self._makeProfile({ name: "TPU", hotend_temp: 220, bed_temp: 60 }),
                self._makeProfile({ name: "ASA", hotend_temp: 250, bed_temp: 95 }),
                self._makeProfile({ name: "PC", hotend_temp: 270, bed_temp: 105 }),
            ];
            self.preheatProfiles(defaults);
        };

        self.botStatusText = ko.observable("Neznámý stav");
        self.botStatusClass = ko.observable("alert-info");
        self.botTesting = ko.observable(false);
        self.botRestarting = ko.observable(false);

        self.testBot = function () {
            self.botTesting(true);
            self.botStatusText(gettext("Testuji připojení..."));
            self.botStatusClass("alert-info");

            $.ajax({
                url: API_BASEURL + "plugin/discordbot",
                type: "POST",
                contentType: "application/json",
                data: JSON.stringify({ command: "test_bot" }),
                success: function (response) {
                    self.botTesting(false);
                    if (response.success) {
                        self.botStatusText(
                            interpolate(
                                gettext("Bot je připojen: %s"),
                                [response.bot_name]
                            )
                        );
                        self.botStatusClass("alert-success");
                    } else {
                        self.botStatusText(
                            gettext("Bot není připojen. Zkontrolujte token a restartujte bota.")
                        );
                        self.botStatusClass("alert-error");
                    }
                },
                error: function () {
                    self.botTesting(false);
                    self.botStatusText(gettext("Chyba připojení k OctoPrint API"));
                    self.botStatusClass("alert-error");
                },
            });
        };

        self.restartBot = function () {
            self.botRestarting(true);
            self.botStatusText(gettext("Restartuji bota..."));
            self.botStatusClass("alert-info");

            $.ajax({
                url: API_BASEURL + "plugin/discordbot",
                type: "POST",
                contentType: "application/json",
                data: JSON.stringify({ command: "restart_bot" }),
                success: function (response) {
                    self.botRestarting(false);
                    if (response.success) {
                        self.botStatusText(gettext("Bot byl úspěšně restartován."));
                        self.botStatusClass("alert-success");
                    } else {
                        self.botStatusText(
                            response.message ||
                            gettext("Nepodařilo se restartovat bota.")
                        );
                        self.botStatusClass("alert-error");
                    }
                },
                error: function () {
                    self.botRestarting(false);
                    self.botStatusText(gettext("Chyba při restartování bota"));
                    self.botStatusClass("alert-error");
                },
            });
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: DiscordBotViewModel,
        dependencies: ["settingsViewModel"],
        elements: ["#settings_plugin_discordbot"],
    });
});
