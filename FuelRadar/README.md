# Fuel Radar

Tmavá desktopová aplikace pro Windows napsaná v Pythonu. Vyhledá čerpací stanice v zadaném českém městě, zobrazí jejich adresy, týdenní celostátní průměry cen benzínu, nafty a LPG, uloží data do místní SQLite databáze a otevře vybranou stanici v OpenStreetMap.

## Spuštění

Je potřeba Python 3.10 nebo novější. Aplikace používá pouze standardní knihovnu Pythonu; další balíčky není nutné instalovat.

V PowerShellu otevři tuto složku a spusť:

```powershell
py main.py
```

Při hledání stanic a aktualizaci cen aplikace potřebuje internetové připojení. Seznam zahrnuje všechny nalezené stanice; pokud v mapě chybí název nebo adresa, zobrazí se obecný název či město. Souřadnice měst se ukládají lokálně a výsledky hledání se používají z cache po dobu 15 minut. Cenové karty automaticky načítají při spuštění a pak jednou denně týdenní průměry za celé Česko z otevřených dat ČSÚ [CENPHMT](https://data.gov.cz/dataset?iri=https%3A%2F%2Fdata.gov.cz%2Fzdroj%2Fdatov%C3%A9-sady%2F00025593%2F1c335381defc8e7bcf3fb638a2e6e01e). ČSÚ nezveřejňuje ceny jednotlivých čerpacích stanic, proto jsou průměry zobrazené odděleně a nejsou vydávané za cenu konkrétní pumpy. Data i poslední hledané město se ukládají do souboru `fuel_radar.db` v této složce.

## Funkce

- vyhledání čerpacích stanic v okruhu 15 km od města,
- zobrazení čerpacích stanic v okolí včetně stanic s neúplnými mapovými údaji,
- týdenní průměry benzínu, nafty a LPG za celé Česko z ČSÚ,
- otevření polohy vybrané stanice v OpenStreetMap,
- místní cache seznamu stanic a posledních cenových průměrů.

V ČR není v této aplikaci použit otevřený zdroj s aktuální cenou pro každou jednotlivou pumpu. Ceny konkrétních stanic se proto nezobrazují. Celostátní průměr není vydáván za cenu konkrétní pumpy. Seznam stanic je z OpenStreetMap; při jeho dalším použití je potřeba uvést [atribuci OSM](https://www.openstreetmap.org/copyright).
