$(function () {
    function DiscordUploadViewModel(parameters) {
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

        self.onBeforeBinding = function () {
            var profiles = self.settingsViewModel.settings.plugins.discordupload.preheat_profiles;
            self.preheatProfiles(profiles());
            self.preheatProfiles.subscribe(function (newVal) {
                profiles(newVal);
            });
        };

        self.addPreheatProfile = function () {
            self.preheatProfiles.push({
                name: ko.observable(""),
                hotend_temp: ko.observable(200),
                bed_temp: ko.observable(60),
            });
        };

        self.removePreheatProfile = function (profile) {
            self.preheatProfiles.remove(profile);
        };

        self.resetPreheatProfiles = function () {
            var defaults = [
                { name: ko.observable("PLA"), hotend_temp: ko.observable(210), bed_temp: ko.observable(60) },
                { name: ko.observable("ABS"), hotend_temp: ko.observable(240), bed_temp: ko.observable(100) },
                { name: ko.observable("PETG"), hotend_temp: ko.observable(235), bed_temp: ko.observable(80) },
                { name: ko.observable("TPU"), hotend_temp: ko.observable(220), bed_temp: ko.observable(60) },
                { name: ko.observable("ASA"), hotend_temp: ko.observable(250), bed_temp: ko.observable(95) },
                { name: ko.observable("PC"), hotend_temp: ko.observable(270), bed_temp: ko.observable(105) },
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
                url: API_BASEURL + "plugin/discordupload",
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
                url: API_BASEURL + "plugin/discordupload",
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
        construct: DiscordUploadViewModel,
        dependencies: ["settingsViewModel"],
        elements: ["#settings_plugin_discordupload"],
    });
});
