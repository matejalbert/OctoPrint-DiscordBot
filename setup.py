# coding=utf-8
from setuptools import setup

plugin_identifier = "discordupload"
plugin_package = "octoprint_discordupload"
plugin_name = "OctoPrint Discord Upload"
plugin_version = "0.1.1"
plugin_description = "Ovládejte svou 3D tiskárnu přes Discord - nahrávejte soubory, spouštějte tisk a sledujte stav"
plugin_author = "matejalbert"
plugin_author_email = "matejalbert@users.noreply.github.com"
plugin_url = "https://github.com/matejalbert/OctoPrint-DiscordBot"
plugin_license = "AGPLv3"
plugin_requires = ["discord.py>=2.3.0"]

setup(
    name=plugin_package,
    version=plugin_version,
    description=plugin_description,
    author=plugin_author,
    author_email=plugin_author_email,
    url=plugin_url,
    license=plugin_license,
    packages=[plugin_package],
    include_package_data=True,
    install_requires=plugin_requires,
    entry_points={
        "octoprint.plugin": [
            f"{plugin_identifier} = {plugin_package}"
        ]
    },
)
