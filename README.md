# ZIPP Diagnostika – Alpha 2

Lokální terénní aplikace pro evidenci diagnostiky betonových dodatečně předpínaných ZIPP vazníků. Eviduje zakázky, lodě, vazníky, samostatné stavy L/P, vyřazení, dilatační dvojice a audit změn. Neprovádí statický výpočet ani odborné posouzení konstrukce.

Alpha 2 přidává češtinu/slovenštinu, společné heslo, stabilní realtime spojení, automatický půdorys a PDF export. Upgrade používá Alembic a zachovává všechna Alpha 1 data.

> Jde o alfa verzi určenou k akceptačnímu a terénnímu ověření. Před ostrým nasazením ověřte zálohování, obnovu a produkční přístup na cílovém Raspberry Pi.

## Windows 11 – instalace a spuštění

1. Nainstalujte 64bit Python 3.10 nebo novější a zapněte **Add Python to PATH**.
2. Spusťte `INSTALL.bat`.
3. Na skrytou výzvu zadejte dvakrát společné heslo (nejméně 10 znaků).
4. Spusťte `START.bat`; otevře se `http://127.0.0.1:8000`.

Data a zálohy jsou mimo zdrojový kód v `%LOCALAPPDATA%\ZippDiagnostics`. `START.bat` nikdy automaticky nemigruje databázi; nejprve ověří, že byla bezpečně aktualizována.

Uživatelské nástroje:

- `BACKUP.bat` – ověřená ruční záloha,
- `UPDATE.bat` – záloha, aktualizace závislostí, migrace a health check,
- `CHANGE_PASSWORD.bat` – bezpečná lokální změna společného hesla.

## Bezpečný upgrade Alpha 1 → Alpha 2

Ukončete běžící `START.bat` a spusťte `UPDATE.bat`. Skript před změnou kódu a před migrací vytvoří SQLite zálohu pomocí Backup API, provede `PRAGMA integrity_check` a uloží SHA-256 manifest. Potom aktualizuje kód a závislosti, spustí Alembic, vyžádá první heslo a ověří databázové schéma i `/health` logiku.

Migrace přidá pouze:

- `projects.labeling_scheme` s hodnotou `legacy` pro existující zakázky,
- singleton tabulku `app_settings` pro Argon2id hash a `auth_version`.

Existující názvy lodí, labely, ID, pozice, typy, dilatační dvojice, L/P, vyřazení, audit a archiv se nepřepisují. Nové zakázky používají schéma `bay_prefix`.

Při chybě se databáze ani záloha nemažou. Neprovádějte ruční `alembic downgrade` na ostrých datech.

## Společné heslo a session

Heslo je společné pro aplikaci; jméno technika zůstává samostatný auditní údaj uložený v jeho prohlížeči. Databáze obsahuje pouze salted Argon2id hash. Heslo, session secret ani cookie se nelogují.

Session cookie je `HttpOnly`, `SameSite=Lax` a podepsaná náhodným `SESSION_SECRET`. Pro produkční HTTPS nastavte:

```env
SESSION_COOKIE_SECURE=true
```

Změna hesla zvýší `auth_version`. Staré REST session okamžitě přestanou platit a otevřené WebSockety jsou při nejbližší periodické kontrole (nejpozději přibližně do 30 sekund) uzavřeny kódem 4401. Přihlášení má lokální i globální omezení pokusů; za Cloudflare používá hlavičku `CF-Connecting-IP`.

## Čeština a slovenština

Přepínač **CZ | SK** je v horní liště i na přihlášení. Volba se ukládá do `localStorage` a stejnojmenné cookie, takže zůstane po reloadu. Šablony jsou společné a všechny systémové texty používají centralizovaný katalog v `app/i18n.py`. Uživatelská data se nepřekládají.

## Půdorys objektu a výchozí značení

Detail zakázky obsahuje záložku **Půdorys objektu / Pôdorys objektu**. Databáze je jediný zdroj pravdy; SVG zobrazuje:

- lodě v pořadí podle referenčních schémat (Loď A dole),
- pozici 1 vpravo a vyšší pozice směrem vlevo,
- P nahoře a L dole,
- běžný a dvojitou linií štítový vazník,
- dva samostatné sousední členy explicitní dilatační dvojice s konzolou,
- Trhlinu červenou čerchovanou čárou,
- Zatečený modrou přerušovanou čárou,
- Jiné šedou tečkovanou čárou,
- volitelně stav L/P pomocí plných/prázdných koncových bodů.

Na mobilu zůstává schéma čitelné díky posunu místo násilného zmenšení. Každá relevantní realtime událost načte novou revizi SVG.

Nové zakázky mají lodě `Loď A`, `Loď B`, …, `Loď Z`, `Loď AA`, … a výchozí labely `A1…Ax`, `B1…Bx`. Label je po vytvoření samostatný editovatelný údaj a změna názvu lodě ho nepřepíše. Dilatační typ se nadále nastavuje jen přes dva sousední vazníky v sekci **Dilatační dvojice**.

## PDF export

Tlačítko **Exportovat PDF / Exportovať PDF** použije stejné SVG jako web. Export je read-only, funguje bez internetu a používá vektorový formát A3 na šířku. Menší objekt je na jedné stránce; velké objekty se dělí po lodích a skupinách nejvýše 18 vazníků, aby text zůstal čitelný. Docker image obsahuje DejaVu Sans pro úplnou CZ/SK znakovou sadu; Windows používá systémový Arial.

## WebSocket stabilita

Potvrzenou lokální příčinou Alpha 1 bylo spuštění Uvicornu bez nainstalovaného WebSocket backendu: handshake končil HTTP 404 a server hlásil, že nemá podporovanou WebSocket knihovnu. Alpha 2 explicitně instaluje `websockets` a spouští moderní Uvicorn backend `--ws websockets-sansio`.

Connection manager má samostatné ID každého klienta, bezpečně odstraňuje ukončené sockety, posílá broadcasty paralelně s timeoutem a loguje connect, disconnect, close code, důvod a chyby broadcastu. Klient používá heartbeat, jediný reconnect loop, exponenciální backoff s jitterem a po návratu synchronizuje aktuální stav.

Technický log nesmí obsahovat hesla, session cookies ani secret.

## Raspberry Pi přes Docker

Docker je doporučený a podporovaný způsob. Na Raspberry Pi OS spusťte z checkoutu/release adresáře:

```bash
chmod +x install_raspberry.sh update_raspberry.sh backup_raspberry.sh change_password_raspberry.sh scripts/raspberry/*.sh
sudo ./install_raspberry.sh
```

Instalátor případně nainstaluje `docker.io` a Compose plugin, vytvoří:

- konfiguraci `/etc/zipp-diagnostics/docker.env` (režim 600),
- databázi `/var/lib/zipp-diagnostics/db/zipp.sqlite3`,
- zálohy `/var/lib/zipp-diagnostics/backups`,
- image `zipp-diagnostics:alpha2` a Compose službu s automatickým restartem a health checkem.

Port je standardně publikovaný jen na `127.0.0.1:8000`. Správa:

```bash
sudo docker compose --env-file /etc/zipp-diagnostics/docker.env -f docker-compose.yml ps
sudo docker compose --env-file /etc/zipp-diagnostics/docker.env -f docker-compose.yml logs -f app
sudo ./backup_raspberry.sh
sudo ./update_raspberry.sh
sudo ./change_password_raspberry.sh
```

Update nejprve vytvoří ověřenou `preupdate` zálohu ve starém image, poté aktualizuje a sestaví image, zastaví aplikaci, migruje, zkontroluje schéma, spustí službu, ověří HTTP health a nakonec `PRAGMA integrity_check`.

Původní nativní systemd skripty zůstávají ve `scripts/raspberry/` jako servisní alternativa, ale hlavní čtyři root skripty používají Docker.

## Cloudflare Tunnel

Preferovaná cesta je:

```text
prohlížeč → HTTPS/WSS doména → Cloudflare Tunnel → app:8000 → FastAPI → SQLite
```

V `/etc/zipp-diagnostics/docker.env` nastavte:

```env
PUBLIC_URL=https://diagnostika.example.cz
SESSION_COOKIE_SECURE=true
CLOUDFLARE_TUNNEL_TOKEN=...
```

V Cloudflare dashboardu nasměrujte public hostname na `http://app:8000`. Potom spusťte:

```bash
sudo docker compose --profile cloudflare --env-file /etc/zipp-diagnostics/docker.env -f docker-compose.yml up -d
```

Port routeru neotvírejte do internetu. Frontend, REST, SVG/PDF a WebSocket zůstávají pod jedním originem; klient automaticky odvodí `ws://` nebo `wss://`. Token nikdy necommitujte.

Nejprve vždy ověřte lokální `curl http://127.0.0.1:8000/health`, potom HTTPS přihlášení a změnu L/P ve dvou prohlížečích přes doménu.

## Vývoj a automatické testy

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
Copy-Item .env.example .env
python -m app.cli ensure-session-secret --env .env
alembic upgrade head
python -m app.cli ensure-password
python -m uvicorn app.main:app --reload --ws websockets-sansio
```

Rychlé testy včetně migrace Alpha 1, autentizace, CZ/SK, WebSocketů, půdorysu a PDF:

```powershell
python -m pytest -m "not stability"
```

Dlouhý test dvou klientů trvá standardně 600 sekund:

```powershell
$env:RUN_STABILITY="1"
$env:STABILITY_SECONDS="600"
python -m pytest tests/test_stability.py -m stability -vv
```

Pro krátké vývojové ověření lze `STABILITY_SECONDS` snížit. Akceptační test přes skutečnou Cloudflare doménu se provádí ručně na cílovém Raspberry Pi.

Pro test přes skutečně spuštěný Uvicorn (ne pouze in-process test klienta) lze použít:

```powershell
python -m scripts.stability_live --base-url http://127.0.0.1:8000 --password "VAŠE_TESTOVACÍ_HESLO" --seconds 600
```

Skript přihlásí dva klienty, ověří strukturální změny, dilatační dvojici, vyřazení/obnovení, idle interval, průběžné L/P a aktuální slovenské SVG. Používejte ho jen proti testovací databázi, protože vytváří testovací zakázku.

## Záloha a obnova

Zálohovací nástroj používá SQLite Backup API, ověřuje `PRAGMA integrity_check`, zapisuje SHA-256 manifest a až poté uplatní retention.

Obnovu provádějte jen při zastavené aplikaci:

1. ověřte kontrolní součet a `PRAGMA integrity_check` vybrané zálohy,
2. vytvořte ještě jednu zálohu současného stavu,
3. nahraďte pouze hlavní `.sqlite3` soubor; nekopírujte `-wal` ani `-shm`,
4. spusťte `alembic upgrade head`, kontrolu schématu a health check.

Automatický nevratný restore není implementován záměrně.

## Troubleshooting

- **Aplikace:** otevřete `/health`; na Windows sledujte okno `START.bat`, v Dockeru `docker compose logs app`.
- **Databáze:** ověřte cestu/volume, oprávnění a `PRAGMA integrity_check`; schema ověří `python -m app.cli check-schema`.
- **Autentizace:** při chybě „heslo není nastavené“ spusťte příslušný change-password nástroj; zkontrolujte, že `SESSION_SECRET` není prázdný.
- **Session přes HTTPS:** `SESSION_COOKIE_SECURE=true` používejte jen za HTTPS; pro čisté lokální HTTP musí být `false`.
- **WebSocket:** stav musí být **Připojeno / Pripojené**; ověřte instalovaný balík `websockets`, explicitní Uvicorn backend a proxy podporu WSS.
- **Cloudflare:** pokud localhost funguje a doména ne, zkontrolujte tunnel route `http://app:8000`, DNS, token a log služby `cloudflared`.
- **PDF:** chybějící diakritika znamená chybějící Unicode font; Dockerfile instaluje `fonts-dejavu-core`.
- **Update:** při selhání nic nemažte; uschovejte `preupdate` zálohu a technický log chyby.

## Omezení Alpha 2

- jedno společné heslo, bez účtů a rolí,
- bez offline fronty; při odpojení se změny neukládají,
- produkční Docker/Cloudflare nasazení je nutné ověřit v cílovém prostředí,
- update skripty předpokládají Git checkout nebo ručně připravený release adresář.
