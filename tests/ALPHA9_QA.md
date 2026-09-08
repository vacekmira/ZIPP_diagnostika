# Alpha 9 – ověření 8. 9. 2026

Testováno na Windows v izolované SQLite databázi proti lokálnímu serveru. Produkční data ani konfigurace nebyly změněny.

## Rozdělení pracovních režimů

Diagnostika a Obhlídka jsou dvě zobrazení stejných databázových objektů. Nevznikají kopie zakázek, lodí ani vazníků. Přepínač mění pouze režim stránky; odkazy a návrat po přihlášení režim zachovávají. Diagnostika zobrazuje diagnostické zadávání, Obhlídka výšky, přístupy a přístupové poznámky. Historie přístupů je oddělena od diagnostické historie. Společná geometrie a stávající půdorys/export zůstávají dostupné v obou režimech.

Databázové schéma ani exportní renderer nebyly měněny. Není nová migrace; poslední historická migrace zůstává `0005_alpha8`.

## Automatické testy

- Kompletní sada: **52 passed, 1 skipped**, jedno existující upozornění Starlette na zastarávající propojení TestClient/httpx.
- Volitelný víceklientový test stability spuštěn samostatně na 30 sekund: **1 passed**. Desetiminutový běh nebyl proveden.
- Nové testy ověřují shodná ID a geometrii v obou režimech, nezávislost diagnostických a přístupových změn, filtrování historie, zachování historických labelů a ID při rozšíření lodě, společné exportní volby, režim v navigaci, archivaci a návrat po přihlášení.
- Regresní sada zahrnuje dosavadní diagnostiku, vyřazení, páry, labely, výšky, přístupy, hromadné změny, audit, konflikty verzí, autentizaci, realtime, bezpečné migrace a exporty.

## Skutečný browser

Playwright ovládal nainstalovaný Edge ve dvou nezávislých browserových kontextech.

- Stejná zakázka se třemi loděmi: shodná ID lodí a vazníků v Diagnostice i Obhlídce.
- Výchozí výška 8,5 m, vlastní výška lodě A 12,25 m, další lodě dědí 8,5 m.
- Samostatné přístupy L = Ž a P = K, CZ/SK poznámka, hromadně L = N a P = J pro dva vybrané vazníky.
- Diagnostické označení L jako hotové nezměnilo přístupy, poznámku ani výšku. Následná změna přístupu zachovala diagnostiku L hotovo / P nehotovo.
- Změna labelu na `HIST-02` a rozšíření lodě z 24 na 25 vazníků se přes existující realtime spojení projevily v obou režimech. Původních 24 ID zůstalo zachováno.
- Detail vazníku v Obhlídce obsahuje přístupové čipy a poznámku, nikoliv diagnostické ovládání nebo vyřazení.
- Telefon 390 × 844 a tablet 820 × 1180: přepínání režimů a hromadné nastavení bez vodorovného přetékání; pořízeny a prohlédnuty screenshoty.
- Dodatečně šířka 320 px: režimová tlačítka 144 × 54 px, hromadný dialog bez přetékání, přepnutí na Diagnostiku bez přístupových čipů.
- Přímý odkaz do Obhlídky po odhlášení zachová režim přes přihlášení.
- Ověřena přístupová vrstva půdorysu zapnutá i vypnutá, realtime přejmenování a odstranění testovací zakázky bez ovlivnění jiné zakázky.
- Běžné scénáře bez chyb browserové konzole; po odstranění zakázky ověřena očekávaná odpověď 404.
- `/health` hlásí `Alpha 9`.

## Stažená a vyrenderovaná PDF

Exportní funkčnost Alpha 8 byla zachována; aktuální verze v zápatí je Alpha 9. Oba režimy používají stejné dosavadní exportní dialogy včetně volby přístupů.

| Export | Nastavení | Přístupy | Stran |
| --- | --- | --- | --- |
| Celý objekt | A4 Landscape / Auto | Ne | 1 |
| Celý objekt | A3 Landscape / 10 pt | Ano | 1 |
| Celý objekt | A2 Portrait / 14 pt | Ano | 1 |
| Loď A | A4 Landscape / 7 pt | Ne | 2 |
| Loď A | A3 Landscape / 10 pt | Ano | 2 |
| Loď A | A2 Portrait / 14 pt | Ano | 2 |

Všech šest souborů bylo staženo přes skutečné dialogy v browseru. Kontrola pypdf ověřila rozměry stran, orientaci, jednostránkový půdorys, CZ/SK znaky bez černých čtverečků, legendu a výšky pouze při zapnutých přístupech, poznámku v přístupovém reportu lodě a verzi právě jednou na stránku pouze v zápatí. Verze není v metadatech ani hlavním nadpisu. Fyzická velikost labelu uvnitř schématu odpovídá 7 / 10 / 14 pt.

Všech devět stran bylo vyrenderováno Popplerem a vizuálně prohlédnuto. Bez zjištěných chyb diakritiky, překryvů nebo oříznutí obsahu.

## Reprodukce a omezení

- Jednotkové/regresní testy: `python -m pytest -o addopts='' -q`.
- Browserový scénář: `tests/browser_alpha9.mjs` proti izolovanému lokálnímu serveru; následně `python tests/verify_alpha9_qa.py` a renderování PDF Popplerem.
- Doplňkový generátor exportní matice: `tests/render_alpha9_qa.py`.
- Testy a QA soubory jsou součástí zdrojového balíčku; do balíčku se nepřidávají pracovní databáze, hesla ani vygenerované QA soubory.
- Fyzický Raspberry Pi ani produkční Docker nebyly v tomto ověření spuštěny. Alpha 9 nebyla v rámci této změny nahrána na GitHub ani nasazena.
