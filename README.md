# ZIPP Diagnostika - Alpha 8

ZIPP Diagnostika je lokální webová aplikace pro evidenci diagnostiky betonových dodatečně předpínaných ZIPP vazníků. Funguje bez internetového připojení na Windows 11 i Raspberry Pi; pro vzdálený provoz lze použít vlastní doménu a Cloudflare Tunnel.

Aktuální vydání: **Alpha 8**

## Hlavní funkce

- zakázky, lodě a vazníky s oddělenými hodnotami `id / position / label`,
- diagnostika levé a pravé strany,
- výchozí výška zakázky s možností vlastní výšky jednotlivých lodí,
- nezávislé přístupy L/P, poznámka a dotykové hromadné nastavení,
- volitelná vrstva přístupů a výšek v půdorysu i obou PDF exportech,
- běžné a štítové vazníky,
- explicitní sousední dilatační dvojice,
- vyřazení Trhlina / Zatečený / Jiné,
- audit změn a identifikace technika,
- CZ/SK rozhraní,
- společné Argon2id heslo a invalidace starých session,
- realtime synchronizace a automatický reconnect,
- souvislý půdorys vícelodní haly se společnými hranicemi,
- PDF celé zakázky a lokalizovaný PDF report jednotlivé lodě,
- společné volby A4/A3/A2/A1/A0, Landscape/Portrait a Auto/7/9/10/12/14 pt pro export objektu i jednotlivé lodě,
- jednostránkový export celé zakázky na A4/A3/A2/A1/A0, Landscape/Portrait a Auto nebo 7/9/10/12/14 pt,
- vložený otevřený Unicode font DejaVu Sans pro spolehlivou CZ/SK diakritiku bez internetového připojení,
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

Compose používá image `zipp-diagnostics:alpha8`, persistentní databázový svazek, health check a automatický restart. PDF vzniká lokálně bez cloudové služby a bez závislosti na systémových fontech.

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

Alpha 8 používá aditivní migraci `0005_alpha8`: výchozí výška zakázky, vlastní výška lodě a samostatné přístupy L/P s poznámkou. Nová pole jsou prázdná a stávající záznamy zůstávají zachované. Použijte stávající aktualizační skript, který před migrací vytvoří zálohu. Historické migrace přidávají:

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

## Výška a přístupy

Výška se zadává v metrech (např. `8,5`). Zakázka má volitelnou výchozí výšku; prázdná výška lodě ji přebírá. Vlastní hodnotu upravíte přímo na stránce lodě. Vymazáním hodnoty obnovíte dědění.

U každého vazníku jsou dotykové čipy pro L a P: N = nůžková plošina, K = kloubová plošina, Ž = žebřík, L = lezecká technika a J = jeřábová dráha. Opětovné klepnutí vymaže aktivní přístup. Společná poznámka k přístupu je oddělená od poznámky k vyřazení.

V režimu **Vybrat více** označte jednotlivé vazníky nebo celou loď a otevřete hromadné nastavení. Strany lze nastavit nezávisle, vymazat nebo ponechat beze změny. Zastaralý výběr se odmítne celý; po konfliktu výběr obnovte. Změny jsou auditované a přenášené existujícím realtime spojením.

Půdorys i oba exporty nabízejí **Bez přístupů / Zobrazit přístupy**. Zapnutá vrstva obsahuje krátké kódy, legendu a skutečné výšky lodí. Poznámky jsou pouze v přehledné tabulce reportu lodě. Čistý export neobsahuje přístupovou vrstvu.

## PDF report lodě

Před exportem lze stejně jako u celého objektu vybrat A4 až A0, Landscape / Portrait a Auto / 7 / 9 / 10 / 12 / 14 pt. Volba mění rozměr stránky i texty reportu včetně labelů, L/P, názvů, stavů a legendy uvnitř schématu. Poslední společná volba se uchovává pouze v prohlížeči.

Report obsahuje aktuální název zakázky a lodě, čas, souhrn, společně renderované schéma a tabulku skutečných stavů L/P. Vyřazení nikdy nepředstírá dokončení neprovedené strany.

Schéma používá skutečné body PDF, nikoliv CSS pixely. Pokud se při zvoleném písmu nevejde přístupová legenda, export doporučí větší papír nebo menší písmo. Report lodě může mít více stránek; jednostránkovost platí pro půdorys celého objektu.

## PDF celé zakázky

Před stažením se otevře dialog s formátem A4 až A0, orientací Landscape / Portrait a velikostí písma Auto / 7 / 9 / 10 / 12 / 14 pt. Výchozí volba je A3 Landscape a Auto. Poslední volba se ukládá jen v prohlížeči.

Export má vždy právě jednu stranu. Geometrie se přizpůsobuje prostoru odděleně od fyzické velikosti textu. Pokud výslovně zvolená kombinace bezpečně nevyjde, server vrátí srozumitelné odmítnutí a doporučí větší papír nebo menší písmo; nikdy nevytvoří druhou stranu ani potichu nezmenší explicitní písmo.

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

Praktický browserový scénář je v `tests/browser_alpha8.mjs` (Playwright/Edge, samostatný testovací server a databáze). Ověřuje telefon 390 × 844, tablet 820 × 1180, hromadné nastavení, poznámku, realtime a šest exportů přes skutečné dialogy. Cesty k Playwrightu a Edge upravte podle svého PC. Nikdy jej nespouštějte nad produkční databází: vytváří a maže vlastní testovací zakázku.

Stažená PDF kontroluje `python tests/verify_alpha8_qa.py`: formát, počet stran, přístupová vrstva, CZ/SK, verze jen v zápatí i fyzická velikost labelů. `python -m tests.render_alpha8_qa` vytváří doplňkovou CZ/SK matici se štítovými, vyřazenými a dilatačními vazníky. PDF je nutné také vyrenderovat a vizuálně projít.

Verze aplikace se v PDF uvádí pouze v zápatí. Health endpoint `/health` vrací stav databáze a aktuální označení **Alpha 8**.
