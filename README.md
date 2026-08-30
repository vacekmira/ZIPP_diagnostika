# ZIPP Diagnostika - Alpha 4

ZIPP Diagnostika je lokální webová aplikace pro evidenci diagnostiky betonových dodatečně předpínaných ZIPP vazníků. Funguje bez internetového připojení na Windows 11 i Raspberry Pi; pro vzdálený provoz lze použít vlastní doménu a Cloudflare Tunnel.

Aktuální vydání: **Alpha 4**

## Hlavní funkce

- zakázky, lodě a vazníky s oddělenými hodnotami `id / position / label`,
- diagnostika levé a pravé strany,
- běžné a štítové vazníky,
- explicitní sousední dilatační dvojice,
- vyřazení Trhlina / Zatečený / Jiné,
- audit změn a identifikace technika,
- CZ/SK rozhraní,
- společné Argon2id heslo a invalidace starých session,
- realtime synchronizace a automatický reconnect,
- souvislý půdorys vícelodní haly se společnými hranicemi,
- PDF celé zakázky a lokalizovaný PDF report jednotlivé lodě,
- volba velikosti písma reportu lodě,
- přejmenování, archivace a silně potvrzené trvalé smazání zakázky,
- ověřené SQLite zálohy a bezpečný update.

Databáze je jediným zdrojem pravdy. Renderer nikdy automaticky nemění labely, typy, L/P, vyřazení ani dilatační dvojice.

## Označování nových zakázek

- nová jednolodní zakázka používá `V1`, `V2`, ...,
- nová vícelodní zakázka používá `A1`, `B1`, `C1`, ...,
- historické a ručně upravené labely se při upgradu ani renderování nepřepisují,
- pokud se k projektu se schématem `single_v` později přidají další lodě, první loď si ponechá V labely a další lodě používají svůj B/C/... prefix.

## Půdorys

Loď A je dole, další lodě jsou nad ní. Sousední lodě sdílejí právě jednu hranici. Pozice 1 je standardně vpravo a vyšší pozice pokračují doleva.

Dilatační dvojice se vykreslí blíž k sobě pouze tehdy, když existuje explicitní `DilationPair`. Štítový vzhled se použije pouze pro databázový typ `gable`.

Stejný geometrický model používá:

- živé SVG,
- PDF celé zakázky,
- schéma v PDF reportu lodě.

## Windows 11

1. Nainstalujte Python 3.10+ a Git.
2. Spusťte `INSTALL.bat`.
3. Nastavte společné heslo pomocí `CHANGE_PASSWORD.bat`.
4. Aplikaci spouštějte přes `START.bat`.
5. Otevřete `http://127.0.0.1:8000`.

Zálohu vytvoří `BACKUP.bat`. Bezpečný update spustí `UPDATE.bat`.

## Raspberry Pi - Docker

Doporučený provoz používá Docker Compose:

```bash
sudo ./install_raspberry.sh --docker
```

Samostatné skripty jsou v `scripts/raspberry/`:

- `install_raspberry_docker.sh`,
- `update_raspberry_docker.sh`,
- `backup_raspberry_docker.sh`,
- `change_password_raspberry.sh`.

Compose používá image `zipp-diagnostics:alpha4`, persistentní databázový svazek, health check a automatický restart. PDF vzniká lokálně bez cloudové služby.

## Cloudflare Tunnel

Do `/etc/zipp-diagnostics/docker.env` nastavte vlastní `CLOUDFLARE_TUNNEL_TOKEN` a bezpečné hodnoty:

```env
PUBLIC_URL=https://diagnostika.example.cz
SESSION_COOKIE_SECURE=true
SESSION_SECRET=<dlouhý náhodný řetězec>
```

Poté spusťte Compose profil `cloudflare`. Aplikace zůstává za společným heslem; znalost adresy není náhradou autentizace.

## Backup a update

Windows i Raspberry Pi update vždy:

1. vytvoří pre-update SQLite backup,
2. ověří jeho integritu,
3. aktualizuje kód a dependencies,
4. spustí Alembic migrace,
5. ověří schéma,
6. spustí health check,
7. ponechá databázi i backup při selhání.

Migrace Alpha 4 přidávají:

- Alpha 3 metadata `single_v` bez změny existujících labelů,
- FK-free `project_deletion_logs` pro minimální stopu trvalého smazání.

Historie: migrace `0002_alpha2` přidala společné heslo, stabilní WebSocket backend a označila původní Alpha 1 projekty jako `legacy`. Tyto názvy jsou historické a zůstávají záměrně.

## Archivace a smazání

Archivace je vratná a data zachová. Trvalé smazání je samostatná operace:

- vyžaduje přesné napsání názvu zakázky,
- proběhne v jedné databázové transakci,
- odstraní pouze vybraný Project a všechna jeho související data,
- zachová minimální deletion log bez FK na odstraněný Project,
- oznámí smazání ostatním klientům přes stávající realtime spojení.

## PDF report lodě

Před exportem lze vybrat Menší / Normální / Větší / Velké písmo. Normální je výchozí čitelnější profil Alpha 4 a poslední volba se uchovává pouze v prohlížeči.

Report obsahuje aktuální název zakázky a lodě, čas, souhrn, společně renderované schéma a tabulku skutečných stavů L/P. Vyřazení nikdy nepředstírá dokončení neprovedené strany.

## Testování

Rychlá kompletní sada:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Krátká lokální stabilita:

```powershell
$env:RUN_STABILITY="1"
$env:STABILITY_SECONDS="30"
.\.venv\Scripts\python.exe -m pytest tests/test_stability.py
```

Produkční desetiminutový víceklientový test ponechte s výchozím `STABILITY_SECONDS=600`.

Health endpoint `/health` vrací stav databáze a aktuální označení **Alpha 4**.
