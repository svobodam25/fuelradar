# Fuel Radar

Desktopová aplikace pro hledání polohy s našeptáváním a porovnání cen okolních čerpacích stanic v Česku. Používá Python 3.10+ s Tkinterem a pouze standardní knihovnu.

## Spuštění

Hotový Windows x64 release je ve složce `release/FuelRadar-1.0.0-windows-x64/` v kořeni projektu. Spusť `FuelRadar.exe`; Python ani instalace nejsou potřeba. Stejný balíček je dostupný jako ZIP. EXE ukládá databázi do `%LOCALAPPDATA%\FuelRadar\fuel_radar.db`, mimo dočasnou složku aplikace. Zdrojová verze používá původní databázi vedle `main.py`; osobní databáze se do release nepřibaluje.

Je potřeba Python 3.10 nebo novější. Aplikace používá pouze standardní knihovnu Pythonu; další balíčky není nutné instalovat.

V PowerShellu otevři tuto složku a spusť:

```powershell
py -3.10 main.py
```

Z kořene repozitáře použij `py -3.10 FuelRadar/main.py`. Lze použít i jinou nainstalovanou verzi Pythonu 3.10+ s Tkinterem. Žádné balíčky přes pip nejsou potřeba.

## Použití

1. Začni psát město nebo adresu (alespoň dva znaky). Návrhy se zobrazí po krátké pauze v psaní.
   Místo psaní můžeš kliknout na **Použít moji polohu**. Aplikace jednorázově zjistí souřadnice zařízení přes službu polohy Windows a rovnou vyhledá stanice ve zvoleném okruhu. Pokud Windows poskytne údaj o přesnosti, zobrazí se dole ve stavovém řádku.
2. Klikni na návrh nebo jej vyber šipkou dolů a Enterem. Stanice a ceny se načtou automaticky. Enter přímo v textovém poli nebo tlačítko Hledat stanice použije první nalezenou polohu.
3. Zvol okruh 5–50 km. Tabulku můžeš řadit podle stanice, adresy, vzdálenosti, ceny každého paliva i typu ceny. Klikni na záhlaví sloupce; dalším kliknutím obrátíš směr. Stejné řazení lze zvolit v nabídce Seřadit podle a tlačítkem Vzestupně/Sestupně. Šipka v záhlaví ukazuje aktivní směr. Čísla se řadí podle hodnoty a chybějící ceny zůstávají vždy na konci. Vzdálenost se měří vzdušnou čarou.
4. Vyber stanici a klikni na **Navigovat ↗**. V Google Mapách se otevře **trasa autem** z polohy zadané nahoře v poli **Odkud vyrážíš?** k přesným souřadnicím pumpy. Stejně funguje dvojklik na řádek nebo Enter při vybrané stanici. Pokud jsi použil tlačítko Použít moji polohu nebo vybral návrh adresy, předají se přesné souřadnice začátku. Nově napsanou adresu lze použít jako výchozí bod přímo, bez dalšího hledání stanic; Google Mapy ji převedou na polohu. Pro přesný začátek cesty zadej celou adresu, samotné město vede z jeho středu. Tlačítko **Jen poloha ↗** nadále otevře pouze bod stanice v OpenStreetMap.
5. Nabídkou Všechny typy cen nad tabulkou můžeš ponechat jen ceník, hlášení, odhady nebo stanice bez ceny. Počet vedle nadpisu ukazuje počet zobrazených stanic. Tlačítko Stanice v okolí v postranním panelu obnoví výchozí filtr a řazení.

Rozhraní má světlou pracovní plochu, tmavý postranní panel, zaoblené karty a střídající se pozadí řádků. Při menším okně jsou další sloupce dostupné vodorovným posuvníkem. Výběr stanice se při změně řazení zachovává.

Navigace používá [oficiální odkazy Google Maps pro trasu](https://developers.google.com/maps/documentation/urls/get-started#directions-action). Na Windows se otevřou ve výchozím prohlížeči; na podporovaných zařízeních mohou otevřít aplikaci Google Maps. Výpočet trasy probíhá v mapové službě, vyžaduje internet a nevyžaduje API klíč v aplikaci. Výchozí bod a souřadnice cíle se předají Googlu po kliknutí na navigaci. Aplikace sama neposkytuje průběžné hlasové pokyny.

Sloupec **Město / místo** zobrazuje dostupnou textovou adresu. Pokud zdroj obsahuje jen GPS souřadnice nebo adresa chybí, aplikace dohledá obec, případně část obce a blízkou ulici přes Photon. Údaj „poblíž“ popisuje okolí stanice, nikoli ověřenou poštovní adresu. Město z cenového zdroje se u těchto záznamů nepřebírá, protože může být chybně přiřazené. Dohledání běží postupně na pozadí, s nejvýše jedním požadavkem za sekundu; výsledky se ukládají na 30 dní. Při nedostupné službě se zobrazí „Obec nezjištěna · otevři mapu“. Souřadnice se nadále používají pro mapu a vzdálenost, nikoli jako adresa v tabulce. Úprava platí i pro dříve uložené výsledky.

## Poloha zařízení

Funkce používá [Windows GeoCoordinateWatcher](https://learn.microsoft.com/en-us/dotnet/api/system.device.location.geocoordinatewatcher?view=netframework-4.8) přes vestavěný Windows PowerShell a .NET Framework, bez dalších balíčků. Spouští se až kliknutím na tlačítko, na pozadí a bez okna konzole. Nejde o průběžné sledování. Určení polohy čeká nejvýše přibližně 35 sekund a přijímá jen nedávné platné souřadnice. Přesnost závisí na zařízení a dostupných službách Windows; nenahrazuje se odhadem podle IP adresy.

Při zakázaném přístupu nebo nedostupné poloze zůstává možné hledat ručně. Tlačítko **Nastavení polohy** otevře příslušnou stránku Windows, kde lze zapnout služby určování polohy a přístup aplikací. Aplikace oprávnění sama nemění. Pokud během zjišťování polohy zadáš vlastní adresu, opožděná odpověď ji nepřepíše. Pro hledání stanic se používají přímo souřadnice zařízení, bez posunu na střed města. Poslední použitá poloha se ukládá do místní databáze stejně jako ručně vybraná adresa.

## Zdroje a přesnost cen

Našeptávání poskytuje [Photon](https://github.com/komoot/photon), který podporuje průběžné hledání. Požadavky běží na pozadí, s prodlevou a nejvýše jedním požadavkem našeptávače současně. Starší odpovědi nepřepíšou novější zadání.

Stanice a ceny se načítají z veřejného datového souboru [BenzinMapa.cz](https://www.benzinmapa.cz/). Zdroj nyní obsahuje převážně **odhady**, ne hlášené ceny jednotlivých stanic. V aplikaci jsou označené **≈** a typem **Odhad**, včetně neznámých typů zdroje. Záznamy označené poskytovatelem `tank-ono.cz` se zobrazují jako Ceník Tank ONO a `uzivatel` jako Hlášení uživatele. Jde o převzaté údaje, nikoli nezávislé ověření aplikací. Chybějící ceny jsou **—**, nikdy nula nebo celostátní průměr. Datum v detailu je datum záznamu poskytovatele, nemusí být datem poslední kontroly ceny na pumpě. Cenu před tankováním ověř na stanici.

Pokrytí odpovídá seznamu poskytovatele; nemusí zahrnovat všechny stanice. Mapové údaje pocházejí od [© přispěvatelů OpenStreetMap](https://www.openstreetmap.org/copyright). Oddělené horní karty zůstávají týdenními celostátními průměry z [ČSÚ](https://data.csu.gov.cz/opendata/sady/CENPHMT/distribuce/json), nejsou průměrem cen v okolí.

Poslední poloha, výsledky a ceny se ukládají do `fuel_radar.db`. Cache platí 15 minut, odděleně podle souřadnic a okruhu. Při výpadku internetu aplikace ukáže uložené výsledky daného hledání s upozorněním. První hledání vyžaduje internet. Veřejné služby mohou být dočasně nedostupné.

## Ověření

```powershell
py -3.10 -m unittest -v
```

Release lze znovu vytvořit z kořene projektu:

```powershell
py -3.10 -m venv .venv-build
./.venv-build/Scripts/python.exe -m pip install -r requirements-build.txt
./.venv-build/Scripts/python.exe build_release.py
```

Skript spustí testy a sestaví samostatné EXE, ikonu, ZIP a kontrolní součty SHA-256. Vyžaduje Windows, 64bitový Python a při instalaci sestavovacích balíčků internet.

Testy zahrnují našeptávání, přesné souřadnice výběru, okruh, původ cen, oddělenou cache, formát týdne, všechny sloupce v obou směrech, chybějící ceny a ovládání skutečného okna Tkinteru včetně kliknutí na záhlaví, filtru a menší velikosti okna. Testy polohy pokrývají předání souřadnic do hledání, přesnost, zamítnutí přístupu, timeout, neplatné souřadnice a ignorování staré odpovědi. Test okna vyžaduje desktopovou relaci; odpovědi síťových služeb a služby polohy v testech jsou nahrazené pevnými daty.
