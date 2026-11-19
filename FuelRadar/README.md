# Fuel Radar

Desktopová aplikace pro hledání polohy s našeptáváním a porovnání cen okolních čerpacích stanic v Česku. Používá Python 3.10+ s Tkinterem a pouze standardní knihovnu.

## Spuštění

Je potřeba Python 3.10 nebo novější. Aplikace používá pouze standardní knihovnu Pythonu; další balíčky není nutné instalovat.

V PowerShellu otevři tuto složku a spusť:

```powershell
py -3.10 main.py
```

Z kořene repozitáře použij `py -3.10 FuelRadar/main.py`. Lze použít i jinou nainstalovanou verzi Pythonu 3.10+ s Tkinterem. Žádné balíčky přes pip nejsou potřeba.

## Použití

1. Začni psát město nebo adresu (alespoň dva znaky). Návrhy se zobrazí po krátké pauze v psaní.
2. Klikni na návrh nebo jej vyber šipkou dolů a Enterem. Stanice a ceny se načtou automaticky. Enter přímo v textovém poli nebo tlačítko Hledat stanice použije první nalezenou polohu.
3. Zvol okruh 5–50 km. Tabulku můžeš řadit podle stanice, adresy, vzdálenosti, ceny každého paliva i typu ceny. Klikni na záhlaví sloupce; dalším kliknutím obrátíš směr. Stejné řazení lze zvolit v nabídce Seřadit podle a tlačítkem Vzestupně/Sestupně. Šipka v záhlaví ukazuje aktivní směr. Čísla se řadí podle hodnoty a chybějící ceny zůstávají vždy na konci. Vzdálenost se měří vzdušnou čarou.
4. Vyber stanici pro zobrazení zdroje a data záznamu. Dvojklik nebo tlačítko otevře její polohu v mapě.
5. Nabídkou Všechny typy cen nad tabulkou můžeš ponechat jen ceník, hlášení, odhady nebo stanice bez ceny. Počet vedle nadpisu ukazuje počet zobrazených stanic. Tlačítko Stanice v okolí v postranním panelu obnoví výchozí filtr a řazení.

Rozhraní má světlou pracovní plochu, tmavý postranní panel, zaoblené karty a střídající se pozadí řádků. Při menším okně jsou další sloupce dostupné vodorovným posuvníkem. Výběr stanice se při změně řazení zachovává.

## Zdroje a přesnost cen

Našeptávání poskytuje [Photon](https://github.com/komoot/photon), který podporuje průběžné hledání. Požadavky běží na pozadí, s prodlevou a nejvýše jedním požadavkem našeptávače současně. Starší odpovědi nepřepíšou novější zadání.

Stanice a ceny se načítají z veřejného datového souboru [BenzinMapa.cz](https://www.benzinmapa.cz/). Zdroj nyní obsahuje převážně **odhady**, ne hlášené ceny jednotlivých stanic. V aplikaci jsou označené **≈** a typem **Odhad**, včetně neznámých typů zdroje. Záznamy označené poskytovatelem `tank-ono.cz` se zobrazují jako Ceník Tank ONO a `uzivatel` jako Hlášení uživatele. Jde o převzaté údaje, nikoli nezávislé ověření aplikací. Chybějící ceny jsou **—**, nikdy nula nebo celostátní průměr. Datum v detailu je datum záznamu poskytovatele, nemusí být datem poslední kontroly ceny na pumpě. Cenu před tankováním ověř na stanici.

Pokrytí odpovídá seznamu poskytovatele; nemusí zahrnovat všechny stanice. Mapové údaje pocházejí od [© přispěvatelů OpenStreetMap](https://www.openstreetmap.org/copyright). Oddělené horní karty zůstávají týdenními celostátními průměry z [ČSÚ](https://data.csu.gov.cz/opendata/sady/CENPHMT/distribuce/json), nejsou průměrem cen v okolí.

Poslední poloha, výsledky a ceny se ukládají do `fuel_radar.db`. Cache platí 15 minut, odděleně podle souřadnic a okruhu. Při výpadku internetu aplikace ukáže uložené výsledky daného hledání s upozorněním. První hledání vyžaduje internet. Veřejné služby mohou být dočasně nedostupné.

## Ověření

```powershell
py -3.10 -m unittest -v
```

Testy zahrnují našeptávání, přesné souřadnice výběru, okruh, původ cen, oddělenou cache, formát týdne, všechny sloupce v obou směrech, chybějící ceny a ovládání skutečného okna Tkinteru včetně kliknutí na záhlaví, filtru a menší velikosti okna. Test okna vyžaduje desktopovou relaci; síťové odpovědi v testech jsou nahrazené pevnými daty.
