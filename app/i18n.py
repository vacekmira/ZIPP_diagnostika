from __future__ import annotations

import json
from collections.abc import Callable

from fastapi import Request


TRANSLATIONS: dict[str, dict[str, str]] = {
    "cs": {
        "app.name": "ZIPP Diagnostika", "app.version": "verze", "lang.cs": "CZ", "lang.sk": "SK", "logout": "Odhlásit",
        "login.title": "Přihlášení", "login.password": "Společné heslo", "login.submit": "Přihlásit",
        "login.bad": "Nesprávné heslo.", "login.not_configured": "Heslo ještě není nastavené. Spusťte lokální nástroj pro změnu hesla.",
        "login.rate_limited": "Příliš mnoho neúspěšných pokusů. Chvíli počkejte.",
        "tech.audit": "Auditní evidence", "tech.who": "Kdo právě pracuje?", "tech.explain": "Jméno se ukládá jen v tomto prohlížeči. Nejde o přihlášení.",
        "tech.name": "Jméno technika", "tech.continue": "Pokračovat", "tech.current": "Technik", "tech.set": "Nastavit",
        "connection.local": "Lokální režim", "connection.connecting": "Připojuji…", "connection.online": "Připojeno", "connection.offline": "Odpojeno",
        "projects": "Zakázky", "projects.active": "Aktivní zakázky", "projects.eyebrow": "Terénní evidence",
        "projects.description": "Průběh diagnostiky betonových dodatečně předpínaných ZIPP vazníků.",
        "project.new": "Nová zakázka", "project.new_hall": "Nová hala", "project.create": "Založit zakázku",
        "project.name": "Název", "project.bay_count": "Počet lodí", "project.truss_count": "Vazníků v lodi", "project.note": "Poznámka",
        "project.cancel": "Zrušit", "project.create_submit": "Vytvořit zakázku", "project.empty": "Zatím tu není žádná zakázka.",
        "project.empty_help": "Založte první halu a aplikace automaticky vytvoří lodě i vazníky.",
        "project.archived_plural": "Archivované zakázky", "project.archive": "Archivovat", "project.reactivate": "Reaktivovat",
        "project.active": "Aktivní zakázka", "project.archived": "Archivovaná zakázka", "project.readonly": "pouze pro čtení",
        "progress.done": "požadovaných stran hotovo", "progress.total": "celkem dokončeno", "progress.remaining": "zbývá",
        "progress.excluded": "vyřazeno", "progress.bays": "lodí", "progress.trusses_excluded": "vyřazených vazníků",
        "tabs.overview": "Přehled", "tabs.plan": "Půdorys objektu", "bays": "Lodě", "bay": "Loď", "bay.total": "celkem",
        "bay.settings": "Nastavení lodě", "bay.position": "Pozice", "bay.archived_notice": "Archivovaná zakázka",
        "bay.archived_help": "Data jsou pouze pro čtení. Pro změny zakázku nejprve reaktivujte.",
        "state.pending": "Neprovedeno", "state.done": "Provedeno", "state.excluded": "Vyřazeno",
        "type.normal": "Běžný", "type.gable": "Štítový", "type.dilation": "Dilatační", "pair": "Dilatační dvojice",
        "duplicate": "Duplicitní označení", "detail": "Detail", "settings.structure": "Administrace struktury",
        "settings.title": "Nastavení lodě", "settings.audit_help": "Změny označení a typů jsou auditované.",
        "settings.basic": "Základní údaje", "settings.bay_name": "Název lodě", "settings.save_name": "Uložit název",
        "settings.active_trusses": "Počet aktivních vazníků", "settings.resize": "Upravit počet", "settings.labels_types": "Označení a typy",
        "settings.label_help": "Label není interní ID. Duplicity jsou povolené, ale zvýrazněné.", "settings.save_labels": "Uložit označení",
        "settings.label": "Označení", "settings.dilation_via_pair": "Dilatační – přes dvojici", "settings.pairs": "Dilatační dvojice",
        "settings.pair_help": "Vyberte dva sousední vazníky. Operace nastaví oba typy atomicky.",
        "settings.first_truss": "První vazník", "settings.neighbor": "Sousední vazník", "settings.create_pair": "Vytvořit dvojici",
        "settings.remove_pair": "Zrušit dvojici", "truss": "Vazník", "truss.internal_id": "interní ID", "truss.back": "Zpět do lodě",
        "diagnostic.status": "Stav diagnostiky", "audit.history": "Historie změn", "audit.empty": "Zatím bez změn.",
        "audit.action.project.created": "Zakázka vytvořena", "audit.action.project.archived": "Zakázka archivována",
        "audit.action.project.reactivated": "Zakázka reaktivována", "audit.action.bay.name.changed": "Název lodě změněn",
        "audit.action.bay.resized": "Počet vazníků změněn", "audit.action.truss.label.changed": "Označení vazníku změněno",
        "audit.action.truss.type.changed": "Typ vazníku změněn", "audit.action.truss.excluded": "Vazník vyřazen",
        "audit.action.truss.restored": "Vyřazení vazníku zrušeno", "audit.action.dilation_pair.created": "Dilatační dvojice vytvořena",
        "audit.action.dilation_pair.removed": "Dilatační dvojice zrušena", "audit.field.name": "název",
        "audit.action.diagnostic.left.set": "Stav levé strany změněn", "audit.action.diagnostic.right.set": "Stav pravé strany změněn",
        "audit.field.truss_count": "počet vazníků", "audit.field.label": "označení", "audit.field.type": "typ", "audit.field.excluded": "vyřazení",
        "audit.field.left_done": "levá strana", "audit.field.right_done": "pravá strana", "audit.field.archived": "archivace",
        "exclude.reason": "Důvod vyřazení", "exclude.note": "Poznámka", "exclude.action": "Vyřadit vazník",
        "exclude.restore": "Zrušit vyřazení", "exclude.no_note": "Bez poznámky", "reason.leak": "Zatečený", "reason.crack": "Trhlina", "reason.other": "Jiné",
        "plan.title": "Půdorys objektu", "plan.description": "Automatické schéma vytvořené z aktuálních dat zakázky.",
        "plan.export_pdf": "Exportovat PDF", "plan.legend": "Legenda", "plan.left": "Levá strana", "plan.right": "Pravá strana",
        "plan.other": "Jiné vyřazení", "plan.zoom_help": "Na menším displeji posouvejte schéma vodorovně.",
        "save.failed": "Změnu se nepodařilo uložit.", "save.left": "Levá strana uložena", "save.right": "Pravá strana uložena",
        "save.bay_name": "Název lodě uložen", "save.labels": "Označení a typy uloženy", "confirm.archive": "Archivovat zakázku? V archivu bude pouze pro čtení.",
        "confirm.resize": "Dotčené vazníky obsahují data. Budou zachovány v historii, ale skryty z aktuální struktury. Pokračovat?",
        "confirm.remove_pair": "Zrušit celou dilatační dvojici a nastavit oba vazníky jako běžné?",
        "error.technician": "Nejprve zadejte jméno technika.", "error.auth": "Přihlášení vypršelo. Přihlaste se znovu.",
        "error.validation": "Zkontrolujte zadané hodnoty.", "error.archived": "Archivovanou zakázku je nutné nejprve reaktivovat.",
        "error.excluded": "Na vyřazeném vazníku nelze měnit diagnostiku.", "error.conflict": "Vazník mezitím změnil jiný technik.",
        "error.other_note": "Pro důvod Jiné je poznámka povinná.", "error.pair_member": "Vazník je v dilatační dvojici; změňte celou dvojici.",
        "error.pair_only": "Dilatační typ lze vytvořit pouze jako dvojici.", "error.pair_adjacent": "Vyberte dva sousední vazníky ve stejné lodi.",
        "error.pair_exists": "Jeden z vazníků už je v jiné dilatační dvojici.", "error.pair_excluded": "Vyřazený vazník nelze přidat do dilatační dvojice.",
        "error.resize_data": "Zmenšení skryje vazníky s existujícími daty.", "error.resize_pair": "Zmenšení by rozdělilo dilatační dvojici.",
    },
    "sk": {
        "app.name": "ZIPP Diagnostika", "app.version": "verzia", "lang.cs": "CZ", "lang.sk": "SK", "logout": "Odhlásiť",
        "login.title": "Prihlásenie", "login.password": "Spoločné heslo", "login.submit": "Prihlásiť",
        "login.bad": "Nesprávne heslo.", "login.not_configured": "Heslo ešte nie je nastavené. Spustite lokálny nástroj na zmenu hesla.",
        "login.rate_limited": "Príliš veľa neúspešných pokusov. Chvíľu počkajte.",
        "tech.audit": "Auditná evidencia", "tech.who": "Kto práve pracuje?", "tech.explain": "Meno sa ukladá iba v tomto prehliadači. Nejde o prihlásenie.",
        "tech.name": "Meno technika", "tech.continue": "Pokračovať", "tech.current": "Technik", "tech.set": "Nastaviť",
        "connection.local": "Lokálny režim", "connection.connecting": "Pripájam…", "connection.online": "Pripojené", "connection.offline": "Odpojené",
        "projects": "Zákazky", "projects.active": "Aktívne zákazky", "projects.eyebrow": "Terénna evidencia",
        "projects.description": "Priebeh diagnostiky betónových dodatočne predpätých ZIPP väzníkov.",
        "project.new": "Nová zákazka", "project.new_hall": "Nová hala", "project.create": "Založiť zákazku",
        "project.name": "Názov", "project.bay_count": "Počet lodí", "project.truss_count": "Väzníkov v lodi", "project.note": "Poznámka",
        "project.cancel": "Zrušiť", "project.create_submit": "Vytvoriť zákazku", "project.empty": "Zatiaľ tu nie je žiadna zákazka.",
        "project.empty_help": "Založte prvú halu a aplikácia automaticky vytvorí lode aj väzníky.",
        "project.archived_plural": "Archivované zákazky", "project.archive": "Archivovať", "project.reactivate": "Reaktivovať",
        "project.active": "Aktívna zákazka", "project.archived": "Archivovaná zákazka", "project.readonly": "iba na čítanie",
        "progress.done": "požadovaných strán hotovo", "progress.total": "celkovo dokončené", "progress.remaining": "zostáva",
        "progress.excluded": "vyradené", "progress.bays": "lodí", "progress.trusses_excluded": "vyradených väzníkov",
        "tabs.overview": "Prehľad", "tabs.plan": "Pôdorys objektu", "bays": "Lode", "bay": "Loď", "bay.total": "celkom",
        "bay.settings": "Nastavenie lode", "bay.position": "Pozícia", "bay.archived_notice": "Archivovaná zákazka",
        "bay.archived_help": "Údaje sú iba na čítanie. Pre zmeny zákazku najprv reaktivujte.",
        "state.pending": "Nevykonané", "state.done": "Vykonané", "state.excluded": "Vyradené",
        "type.normal": "Bežný", "type.gable": "Štítový", "type.dilation": "Dilatačný", "pair": "Dilatačná dvojica",
        "duplicate": "Duplicitné označenie", "detail": "Detail", "settings.structure": "Administrácia štruktúry",
        "settings.title": "Nastavenie lode", "settings.audit_help": "Zmeny označení a typov sú auditované.",
        "settings.basic": "Základné údaje", "settings.bay_name": "Názov lode", "settings.save_name": "Uložiť názov",
        "settings.active_trusses": "Počet aktívnych väzníkov", "settings.resize": "Upraviť počet", "settings.labels_types": "Označenia a typy",
        "settings.label_help": "Label nie je interné ID. Duplicity sú povolené, ale zvýraznené.", "settings.save_labels": "Uložiť označenia",
        "settings.label": "Označenie", "settings.dilation_via_pair": "Dilatačný – cez dvojicu", "settings.pairs": "Dilatačné dvojice",
        "settings.pair_help": "Vyberte dva susedné väzníky. Operácia nastaví oba typy atomicky.",
        "settings.first_truss": "Prvý väzník", "settings.neighbor": "Susedný väzník", "settings.create_pair": "Vytvoriť dvojicu",
        "settings.remove_pair": "Zrušiť dvojicu", "truss": "Väzník", "truss.internal_id": "interné ID", "truss.back": "Späť do lode",
        "diagnostic.status": "Stav diagnostiky", "audit.history": "História zmien", "audit.empty": "Zatiaľ bez zmien.",
        "audit.action.project.created": "Zákazka vytvorená", "audit.action.project.archived": "Zákazka archivovaná",
        "audit.action.project.reactivated": "Zákazka reaktivovaná", "audit.action.bay.name.changed": "Názov lode zmenený",
        "audit.action.bay.resized": "Počet väzníkov zmenený", "audit.action.truss.label.changed": "Označenie väzníka zmenené",
        "audit.action.truss.type.changed": "Typ väzníka zmenený", "audit.action.truss.excluded": "Väzník vyradený",
        "audit.action.truss.restored": "Vyradenie väzníka zrušené", "audit.action.dilation_pair.created": "Dilatačná dvojica vytvorená",
        "audit.action.dilation_pair.removed": "Dilatačná dvojica zrušená", "audit.field.name": "názov",
        "audit.action.diagnostic.left.set": "Stav ľavej strany zmenený", "audit.action.diagnostic.right.set": "Stav pravej strany zmenený",
        "audit.field.truss_count": "počet väzníkov", "audit.field.label": "označenie", "audit.field.type": "typ", "audit.field.excluded": "vyradenie",
        "audit.field.left_done": "ľavá strana", "audit.field.right_done": "pravá strana", "audit.field.archived": "archivácia",
        "exclude.reason": "Dôvod vyradenia", "exclude.note": "Poznámka", "exclude.action": "Vyradiť väzník",
        "exclude.restore": "Zrušiť vyradenie", "exclude.no_note": "Bez poznámky", "reason.leak": "Zatečený", "reason.crack": "Trhlina", "reason.other": "Iné",
        "plan.title": "Pôdorys objektu", "plan.description": "Automatická schéma vytvorená z aktuálnych údajov zákazky.",
        "plan.export_pdf": "Exportovať PDF", "plan.legend": "Legenda", "plan.left": "Ľavá strana", "plan.right": "Pravá strana",
        "plan.other": "Iné vyradenie", "plan.zoom_help": "Na menšom displeji posúvajte schému vodorovne.",
        "save.failed": "Zmenu sa nepodarilo uložiť.", "save.left": "Ľavá strana uložená", "save.right": "Pravá strana uložená",
        "save.bay_name": "Názov lode uložený", "save.labels": "Označenia a typy uložené", "confirm.archive": "Archivovať zákazku? V archíve bude iba na čítanie.",
        "confirm.resize": "Dotknuté väzníky obsahujú údaje. Zostanú zachované v histórii, ale skryjú sa z aktuálnej štruktúry. Pokračovať?",
        "confirm.remove_pair": "Zrušiť celú dilatačnú dvojicu a nastaviť oba väzníky ako bežné?",
        "error.technician": "Najprv zadajte meno technika.", "error.auth": "Prihlásenie vypršalo. Prihláste sa znova.",
        "error.validation": "Skontrolujte zadané hodnoty.", "error.archived": "Archivovanú zákazku je potrebné najprv reaktivovať.",
        "error.excluded": "Na vyradenom väzníku nemožno meniť diagnostiku.", "error.conflict": "Väzník medzitým zmenil iný technik.",
        "error.other_note": "Pre dôvod Iné je poznámka povinná.", "error.pair_member": "Väzník je v dilatačnej dvojici; zmeňte celú dvojicu.",
        "error.pair_only": "Dilatačný typ možno vytvoriť iba ako dvojicu.", "error.pair_adjacent": "Vyberte dva susedné väzníky v rovnakej lodi.",
        "error.pair_exists": "Jeden z väzníkov už je v inej dilatačnej dvojici.", "error.pair_excluded": "Vyradený väzník nemožno pridať do dilatačnej dvojice.",
        "error.resize_data": "Zmenšenie skryje väzníky s existujúcimi údajmi.", "error.resize_pair": "Zmenšenie by rozdelilo dilatačnú dvojicu.",
    },
}


def normalize_language(value: str | None) -> str:
    return "sk" if value == "sk" else "cs"


def request_language(request: Request) -> str:
    return normalize_language(request.cookies.get("zipp_language"))


def translator(language: str) -> Callable[[str], str]:
    language = normalize_language(language)
    return lambda key: TRANSLATIONS[language].get(key, TRANSLATIONS["cs"].get(key, key))


def catalog_json() -> str:
    return json.dumps(TRANSLATIONS, ensure_ascii=False).replace("</", "<\\/")
