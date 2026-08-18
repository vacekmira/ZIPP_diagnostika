# ZIPP Diagnostika

První alfa verze interní terénní aplikace pro evidenci diagnostiky betonových dodatečně předpínaných ZIPP vazníků. Aplikace eviduje zakázky, lodě, vazníky, samostatné strany L/P, vyřazení, explicitní dilatační dvojice a audit změn. Neprovádí statický výpočet ani neposuzuje bezpečnost konstrukce.

> Alfa verze je určená k funkčnímu a terénnímu ověření. Před nasazením s ostrými daty proveďte akceptační testy a nastavte pravidelné zálohy.

## Quick Start – Windows 11

1. Nainstalujte 64bit Python 3.10 nebo novější z python.org a při instalaci zapněte **Add Python to PATH**.
2. Dvojklikem spusťte `INSTALL.bat`.
3. Po dokončení spusťte `START.bat`.
4. Otevře se `http://127.0.0.1:8000`.

Databáze a zálohy se ukládají mimo zdrojový kód do `%LOCALAPPDATA%\ZippDiagnostics`. Skutečný `.env` instalační ani aktualizační skript nepřepisuje.

Pro ruční zálohu použijte `BACKUP.bat`. Pro update použijte `UPDATE.bat`; před změnou kódu vždy nejprve vytvoří a ověří SQLite zálohu.

## Advanced Development – Windows 11

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
Copy-Item .env.example .env
alembic upgrade head
python -m uvicorn app.main:app --reload
```

Testy:

```powershell
pytest
```

## Quick Start – Raspberry Pi

Na Raspberry Pi OS spusťte z adresáře aplikace:

```bash
chmod +x install_raspberry.sh scripts/raspberry/*.sh
sudo ./install_raspberry.sh
```

Instalátor připraví:

- aplikaci přes `/opt/zipp-diagnostics/current`,
- konfiguraci `/etc/zipp-diagnostics/app.env`,
- databázi `/var/lib/zipp-diagnostics/db/zipp.sqlite3`,
- zálohy `/var/lib/zipp-diagnostics/backups`,
- systemd službu `zipp-diagnostics`.

## Raspberry Pi Service

```bash
sudo systemctl status zipp-diagnostics
sudo systemctl start zipp-diagnostics
sudo systemctl stop zipp-diagnostics
sudo systemctl restart zipp-diagnostics
sudo journalctl -u zipp-diagnostics -f
```

Výchozí služba naslouchá pouze na `127.0.0.1:8000`. Pro vědomé povolení LAN změňte `--host` v systemd jednotce na `0.0.0.0`, spusťte `sudo systemctl daemon-reload` a službu restartujte.

## Local-only operation

Cloudflare ani internet nejsou pro běh aplikace potřeba. HTML, CSS a JavaScript jsou součástí projektu a nepoužívají CDN. Na jednom zařízení otevřete dvě různá okna nebo dva prohlížeče, nastavte různá jména techniků a otevřete stejnou loď.

## Práce s aplikací

Po prvním otevření zadejte jméno technika. Jméno je auditní údaj uložený v prohlížeči, nikoliv přihlášení.

1. Založte zakázku, počet lodí a výchozí počet vazníků.
2. Otevřete zakázku a loď.
3. Klepnutím na velké tlačítko L/P okamžitě změňte stav.
4. Přes **Nastavení lodě** upravte název, počet vazníků, labely a dilatační dvojice.
5. V detailu vazníku lze vazník vyřadit, obnovit a prohlížet audit.

Duplicitní labely jsou povolené, ale UI je zvýrazní. Interní vazby vždy používají neměnné ID a fyzickou pozici.

## Dilation pairs

Dilatační typ nevzniká změnou jediného vazníku. V nastavení lodě se vyberou dva sousední vazníky a server atomicky:

- ověří stejnou loď a sousedství,
- ověří, že nejsou v jiné dvojici,
- vytvoří explicitní dvojici,
- nastaví oba typy na dilatační,
- zapíše audit.

Zrušení je opět operace celé dvojice; alfa UI nastaví oba vazníky zpět na běžné.

## Cloudflare deployment

Produkční cesta je:

```text
prohlížeč → HTTPS/WSS doména → Cloudflare Tunnel → 127.0.0.1:8000 → FastAPI → SQLite
```

1. Nainstalujte `cloudflared` podle aktuální dokumentace Cloudflare.
2. Vytvořte tunnel a DNS hostname.
3. Upravte kopii `deployment/cloudflare/config.yml.example`.
4. Nainstalujte cloudflared jako samostatnou systemd službu.
5. FastAPI ponechte na localhostu; port routeru neotvírejte do internetu.

Cloudflare je jen síťová vrstva. Aplikace nemá vlastní přihlášení; znalost adresy je podle zadání přístupovým omezením. Pro vyšší ochranu lze později před aplikaci zapnout Cloudflare Access bez změny datového modelu.

Kontrola tunnelu:

```bash
sudo systemctl status cloudflared
sudo journalctl -u cloudflared -f
```

## WebSocket verification

Lokálně otevřete stejnou loď v Chrome a Edge, nastavte Novák/Svoboda a změňte L nebo P. Druhé okno se má aktualizovat téměř okamžitě. Stav v horní liště musí být **Připojeno**. Po dočasném výpadku spojení se zobrazí **Odpojeno**, zápis L/P se zablokuje a klient se automaticky znovu připojí a načte průběh.

Stejný test proveďte přes HTTPS doménu; prohlížeč automaticky použije `wss://` aktuálního hostname.

## Database migrations

Schéma je verzováno Alembicem:

```bash
alembic current
alembic upgrade head
```

Produkční update nikdy nemaže ani znovu nevytváří databázi. Nepoužívejte `alembic downgrade` na ostrých datech bez ověřené zálohy a konkrétního migračního plánu.

## Backup

Windows: `BACKUP.bat`.

Raspberry Pi:

```bash
sudo ./backup_raspberry.sh
```

Nástroj používá SQLite Backup API, na výsledku spustí `PRAGMA integrity_check`, vytvoří SHA-256 manifest a až potom uplatní retention.

## Updating

Windows: ukončete běžící `START.bat` a spusťte `UPDATE.bat`.

Raspberry Pi:

```bash
sudo ./update_raspberry.sh
```

Update nejprve vytvoří povinnou `preupdate` zálohu. Pokud záloha, instalace závislostí nebo migrace selže, databáze ani záloha se nemažou.

## Restore / rollback

Obnovu provádějte pouze při zastavené aplikaci:

1. Zastavte aplikaci.
2. Ověřte vybranou zálohu pomocí `PRAGMA integrity_check` a kontrolního součtu z `.json` manifestu.
3. Vytvořte ještě jednu zálohu současné databáze.
4. Nahraďte databázový soubor ověřenou zálohou; nekopírujte soubory `-wal` nebo `-shm`.
5. Spusťte `alembic upgrade head`.
6. Spusťte službu a zkontrolujte `/health`.

Na Raspberry Pi pracujte s `/var/lib/zipp-diagnostics/db/zipp.sqlite3`. Automatický nevratný restore není implementován záměrně.

## Health check

`GET /health` vrací stav aplikace, dostupnost databáze a verzi. Nevrací diagnostická data.

## Troubleshooting

- **Aplikace:** ověřte `/health` a technický log procesu nebo journald.
- **Databáze:** zkontrolujte cestu v `.env`, oprávnění adresáře a `PRAGMA integrity_check`.
- **Systemd:** `systemctl status zipp-diagnostics` a `journalctl -u zipp-diagnostics -n 100`.
- **Cloudflare:** aplikace musí nejprve fungovat na Raspberry Pi přes `curl http://127.0.0.1:8000/health`; potom řešte tunnel.
- **WebSocket:** zkontrolujte stav v horní liště, službu a zda stránka pod HTTPS používá WSS.
- **Update:** obnovu provádějte jen z ověřené pre-update zálohy podle předchozí kapitoly.

## Omezení alfa verze

- Neobsahuje vlastní autentizaci ani oprávnění.
- Neobsahuje offline frontu; bez serveru se změny neukládají.
- Update skripty očekávají instalaci z Git repozitáře nebo ručně připraveného release adresáře.
- Produkční instalaci a Cloudflare tunnel je nutné ověřit na cílovém Raspberry Pi.
