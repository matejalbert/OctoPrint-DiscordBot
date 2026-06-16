# OctoPrint Discord Bot

Ovládejte svou 3D tiskárnu přes Discord — nahrávejte soubory, spouštějte tisk a sledujte stav, vše přímo z Discord chatu.

Lehký OctoPrint plugin, který běží přímo na Raspberry Pi (Zero/3/4/5) vedle OctoPrintu. Žádný externí server, žádný extra hardware.

## Funkce

### Příkazy

| Příkaz | Popis |
|---|---|
| `/status` | Stav tiskárny s teplotami a průběhem |
| `/print <soubor>` | Spustí tisk souboru |
| `/pause` | Pozastaví tisk |
| `/resume` | Obnoví tisk |
| `/cancel` | Zruší tisk |
| `/estop` | Nouzové zastavení (M112) |
| `/home [all\|xy\|z\|x\|y]` | Najetí os do výchozí pozice |
| `/preheat <profil>` | Předehřev podle profilu (PLA, ABS, PETG...) |
| `/set_temp [hotend] [bed]` | Ruční nastavení teplot |
| `/files` | Seznam souborů na tiskárně |
| `/download <soubor>` | Stažení souboru z tiskárny |
| `/delete <soubor>` | Smazání souboru |
| `/jog <osa> [mm] [speed]` | Posun osou (volitelně rychlost) |
| `/extrude [mm] [speed]` | Extrudování/retrakce filamentu |
| `/info` | Informace o tiskárně |
| `/help` | Nápověda |
| `/shutdown` | Vypnutí systému (jen admin) |

### Nahrávání souborů

Pošlete soubor (.gcode, .stl, .obj, .3mf) jako přílohu v Discord chatu — bot ho automaticky nahraje do OctoPrintu.

### Upozornění

- Odeslání souboru na tisk
- Dokončení tisku
- Chyba tisku
- Automatické smazání souboru po tisku (volitelné)

## Instalace

### Přes Plugin Manager (doporučeno)

1. V OctoPrint jděte do **Settings** → **Plugin Manager** → **Get More**
2. Vložte URL: `https://github.com/matejalbert/OctoPrint-DiscordBot/releases/latest/download/master.zip`
3. Klikněte **Install** a restartujte OctoPrint

### Ručně

```bash
cd ~
git clone https://github.com/matejalbert/OctoPrint-DiscordBot.git
cd OctoPrint-DiscordBot
pip install -e .
```

Restartujte OctoPrint.

## Nastavení Discord bota

1. Jděte na [Discord Developer Portal](https://discord.com/developers/applications)
2. Klikněte **New Application** → dejte jméno (např. "3D Printer Bot")
3. Jděte do **Bot** → **Add Bot**
4. V sekci **Privileged Gateway Intents** zapněte:
   - ✅ MESSAGE CONTENT INTENT
   - ✅ SERVER MEMBERS INTENT
5. Klikněte **Reset Token** a zkopírujte token
6. Jděte do **OAuth2** → **URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot permissions: `Send Messages`, `Read Messages`, `Attach Files`, `Embed Links`, `Read Message History`
7. Otevřete vygenerovanou URL a pozvěte bota na svůj Discord server
8. V OctoPrint jděte do **Settings** → **Discord Upload** → vložte token → **Restartovat bota**
9. Klikněte **Test připojení**

## Nastavení pluginu

Plugin má 7 záložek v nastavení OctoPrintu:

| Záložka | Popis |
|---|---|
| **Základní** | Bot token, prefix příkazů, slash commands, jazyk (CS/EN) |
| **Oprávnění** | Povolené Discord kanály, role, admin uživatelé |
| **Nahrávání** | Povolené přípony, max velikost, cesta pro upload, auto-mazání |
| **Profily předehřevu** | Vlastní profily teplot (PLA, ABS, PETG, TPU, ASA, PC) |
| **Upozornění** | Notifikace na dokončení/chybu, kanál pro notifikace |
| **Ovládání** | Výchozí vzdálenost jogu, délka a rychlost extrudování |
| **Stav bota** | Test připojení a restart bota |

## Vývoj

### Požadavky

- Python 3.7+
- OctoPrint 1.8.0+
- discord.py 2.3.0+

### Lokální vývoj

```bash
git clone https://github.com/matejalbert/OctoPrint-DiscordBot.git
cd OctoPrint-DiscordBot
pip install -e .[dev]
```

## Licence

AGPLv3
