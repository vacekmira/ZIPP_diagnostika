# Alpha 8 – ověření 8. 9. 2026

Testováno na Windows v izolované SQLite databázi, bez změn produkčních dat.

## Automatické testy

- Kompletní sada: 45 úspěšných testů, 1 standardně přeskočený volitelný test stability.
- Volitelný víceklientový test byl následně spuštěn samostatně na 30 sekund a prošel. Desetiminutový běh nebyl proveden.
- Ověřeny výšky, dědění a vymazání override, všech pět přístupů, nezávislost L/P, poznámka, audit, atomické hromadné změny a konflikt verzí.
- Ověřena migrace historické databáze se zálohou, zachováním dat a kontrolou cizích klíčů. Historické názvy migrací zůstaly beze změny.
- Regresní testy pokrývají původní diagnostiku, páry, vyřazení, labely, mazání, autentizaci, realtime a exporty.

## Skutečný browser

Playwright ovládal nainstalovaný Edge a dva nezávislé browserové kontexty proti lokálnímu serveru.

- Výchozí výška 8,5 m, vlastní výška lodě A 12,25 m, další lodě zdědily 8,5 m.
- A1: L = Ž, P = K, československá poznámka; zachováno po reloadu.
- A2 a A3 vybrány dotykovými tlačítky; hromadně L = N a P = J.
- Realtime přístup, poznámka i výška ověřeny v druhém browseru bez reloadu.
- Telefon 390 × 844 a tablet 820 × 1180: bez vodorovného přetékání, čipy minimálně 44 × 48 px.
- Dodatečně dialog na šířce 320 px: bez přetékání, čipy 44 × 48 px.
- Přístupová vrstva skutečného půdorysu zapnuta i vypnuta, oba exportní dialogy použity k downloadu.
- Bez chyb konzole při běžných scénářích; očekávaná 404 po ověřeném smazání testovací zakázky.

## Stažená a vyrenderovaná PDF

| Export | Nastavení | Přístupy | Stran |
| --- | --- | --- | --- |
| Celý objekt | A4 Landscape / Auto | Ne | 1 |
| Celý objekt | A3 Landscape / 10 pt | Ano | 1 |
| Celý objekt | A2 Portrait / 14 pt | Ano | 1 |
| Loď A | A4 Landscape / 7 pt | Ne | 2 |
| Loď A | A3 Landscape / 10 pt | Ano | 2 |
| Loď A | A2 Portrait / 14 pt | Ano | 2 |

Všechny soubory byly staženy přes UI a vyrenderovány Popplerem. Kontrola pypdf ověřila MediaBox, počet stran, CZ/SK znaky, legendu a výšky pouze v zapnuté vrstvě, poznámku pouze v zapnutém reportu lodě, verzi právě jednou na stránku v souřadnicích zápatí a její nepřítomnost v metadatech.

Fyzická velikost otočeného labelu A1 měřená z PDF transformací: 7,00 / 10,00 / 14,00 pt. Opraven starší rozdíl mezi CSS px a PDF pt v SVG schématu.

Doplňková vizuální matice obsahovala 3 lodě × 24 vazníků, explicitní štíty, dilatační dvojice, vyřazení, všech pět přístupů a CZ/SK text. Prohlédnuty české i slovenské rendery, legendy a tabulky; kódy nepřekrývá opakovaný dlouhý popis dilatační dvojice.

## Nasazení

Přidána aditivní migrace `0005_alpha8`; nová pole jsou nullable. Použít stávající bezpečný aktualizační skript se zálohou před migrací. Docker metadata i skripty označují Alpha 8. Fyzický Raspberry Pi ani produkční Docker nebyly v tomto ověření spuštěny; verze nebyla v rámci této změny pushnuta na GitHub ani nasazena.
