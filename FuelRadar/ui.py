"""Native desktop presentation for Fuel Radar."""
import tkinter as tk
from tkinter import ttk

BG = "#f3f6f8"
PANEL = "#ffffff"
TEXT = "#182c39"
MUTED = "#71818d"
GREEN = "#087f68"
LINE = "#e3e9ed"
NAV = "#112b32"
SORT_LABELS = {"Vzdálenost": "distance", "Benzín": "benzín", "Nafta": "nafta",
               "LPG": "lpg", "Stanice": "name", "Adresa": "address", "Typ ceny": "kind"}
HEADINGS = {"name": "Stanice", "address": "Město / místo", "distance": "Vzdálenost",
            "benzín": "Natural 95", "nafta": "Nafta", "lpg": "LPG", "kind": "Typ ceny"}


class RoundedPanel(tk.Canvas):
    def __init__(self, parent, color=PANEL, padding=18):
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0, height=110)
        self.padding = padding
        self.color = color
        self.shape = self.create_polygon(0, 0, 1, 1, fill=color, smooth=True, splinesteps=24)
        self.body = tk.Frame(self, bg=color)
        self.window = self.create_window(padding, padding, window=self.body, anchor="nw")
        self.bind("<Configure>", self._resize)
        self.body.bind("<Configure>", lambda _e: self.configure(height=self.body.winfo_reqheight() + padding * 2))

    def _resize(self, event):
        w, h, r = event.width, event.height, 18
        self.coords(self.shape, r, 0, w-r, 0, w, 0, w, r, w, h-r, w, h,
                    w-r, h, r, h, 0, h, 0, h-r, 0, r, 0, 0)
        self.itemconfigure(self.window, width=max(1, w - self.padding * 2))


class FuelRadarUI:
    def _configure_styles(self):
        self._app_icon = tk.PhotoImage(width=32, height=32)
        self._app_icon.put(NAV, to=(0, 0, 32, 32))
        for x in range(32):
            for y in range(32):
                radius_squared = (x - 16) ** 2 + (y - 16) ** 2
                if (180 <= radius_squared <= 215 or 40 <= radius_squared <= 60 or
                        radius_squared <= 5 or (x >= 16 and y <= 16 and abs(x + y - 32) <= 1)):
                    self._app_icon.put("#64d8ac", (x, y))
        self.iconphoto(True, self._app_icon)
        style = ttk.Style(self)
        style.theme_use("clam")
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", "#d8eee7")
        self.option_add("*TCombobox*Listbox.selectForeground", GREEN)
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                        rowheight=52, borderwidth=0, font=("Segoe UI", 10), relief="flat")
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure("Treeview.Heading", background="#f5f8f9", foreground="#526773",
                        borderwidth=0, relief="flat", font=("Segoe UI", 9, "bold"), padding=(12, 14))
        style.map("Treeview.Heading", background=[("active", "#e3f2ed")], foreground=[("active", GREEN)])
        style.map("Treeview", background=[("selected", "#dcefe8")], foreground=[("selected", "#075e4e")])
        style.configure("Fuel.TCombobox", fieldbackground=PANEL, background=PANEL,
                        foreground=TEXT, arrowcolor=GREEN, bordercolor=LINE,
                        lightcolor=LINE, darkcolor=LINE, padding=(10, 8), font=("Segoe UI", 10))
        style.map("Fuel.TCombobox", fieldbackground=[("readonly", PANEL)],
                  foreground=[("readonly", TEXT)], selectbackground=[("readonly", PANEL)],
                  selectforeground=[("readonly", TEXT)])
        style.configure("Vertical.TScrollbar", background="#d4dfe3", troughcolor="#f5f8f9",
                        borderwidth=0, arrowsize=12)
        style.configure("Horizontal.TScrollbar", background="#d4dfe3", troughcolor="#f5f8f9", borderwidth=0)

    def _button(self, parent, text, command, primary=False):
        color = GREEN if primary else "#edf4f1"
        button = tk.Button(parent, text=text, command=command, bg=color,
                           fg="white" if primary else GREEN, activebackground="#096e5b" if primary else "#dcece5",
                           activeforeground="white" if primary else GREEN,
                           disabledforeground="#9aaca5", relief="flat", borderwidth=0,
                           padx=18, pady=10, cursor="hand2", font=("Segoe UI", 10, "bold"))
        button.bind("<Enter>", lambda _e: button.configure(bg="#096e5b" if primary else "#dcece5"))
        button.bind("<Leave>", lambda _e: button.configure(bg=color))
        return button

    def _build_ui(self):
        self.sort_column = "distance"
        self.sort_descending = False
        sidebar = tk.Frame(self, bg=NAV, width=196)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        brand = tk.Frame(sidebar, bg=NAV)
        brand.pack(fill="x", padx=22, pady=(30, 38))
        radar = tk.Canvas(brand, bg=NAV, width=38, height=38, highlightthickness=0)
        radar.pack(side="left", padx=(0, 10))
        for inset in (2, 10):
            radar.create_oval(inset, inset, 36-inset, 36-inset, outline="#64d8ac", width=1.5)
        radar.create_line(19, 19, 31, 7, fill="#64d8ac", width=2)
        radar.create_oval(16, 16, 22, 22, fill="#64d8ac", outline="")
        tk.Label(brand, text="fuelradar", bg=NAV, fg="white", font=("Segoe UI", 16, "bold")).pack(side="left")
        tk.Label(sidebar, text="TVŮJ PRŮVODCE NA CESTÁCH", bg=NAV, fg="#719397",
                 font=("Segoe UI", 7, "bold")).pack(anchor="w", padx=22, pady=(0, 14))
        nav = tk.Button(sidebar, text="◉   Stanice v okolí", bg="#23443f", fg="#a1eccb",
                        activebackground="#2b534b", activeforeground="white", relief="flat", anchor="w",
                        padx=16, pady=13, font=("Segoe UI", 10, "bold"), cursor="hand2", command=self._reset_filters)
        nav.pack(fill="x", padx=12)
        tk.Label(sidebar, text="Méně za palivo.\nVíce na zážitky.", bg=NAV, fg="#c5d8d7",
                 justify="left", font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=22, pady=(42, 16))
        tk.Label(sidebar, text="Najdi si svou příští\nzastávku na pár kliknutí.", bg=NAV, fg="#85a2a4",
                 justify="left", font=("Segoe UI", 10)).pack(anchor="w", padx=22)
        foot = tk.Frame(sidebar, bg=NAV)
        foot.pack(side="bottom", fill="x", padx=22, pady=24)
        tk.Label(foot, text="JAK ČÍST CENY", bg=NAV, fg="#719397", font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 12))
        for label, color in (("●  Ceník / hlášení", "#9de4c3"), ("≈  Odhad ceny", "#e1bd7d"), ("—  Cena není uvedena", "#91a8a9")):
            tk.Label(foot, text=label, bg=NAV, fg=color, font=("Segoe UI", 9)).pack(anchor="w", pady=4)
        tk.Frame(foot, bg="#2d474c", height=1).pack(fill="x", pady=16)
        tk.Label(foot, text="BenzinMapa.cz · ČSÚ\n© OpenStreetMap", bg=NAV, fg="#719397",
                 justify="left", font=("Segoe UI", 8)).pack(anchor="w")

        content = tk.Frame(self, bg=BG)
        content.pack(side="left", fill="both", expand=True, padx=30, pady=20)
        top = tk.Frame(content, bg=BG)
        top.pack(fill="x", pady=(0, 14))
        tk.Label(top, text="CHYTŘEJŠÍ TANKOVÁNÍ", bg=BG, fg=GREEN, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tk.Label(top, text="Další zastávka? Ta výhodnější.", bg=BG, fg=TEXT,
                 font=("Segoe UI", 24, "bold")).pack(anchor="w", pady=(5, 4))
        tk.Label(top, text="Porovnej ceny paliv a najdi stanici, která ti sedne.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 11)).pack(anchor="w")

        self.search_panel = RoundedPanel(content, padding=16)
        self.search_panel.pack(fill="x", pady=(0, 14))
        search = self.search_panel.body
        tk.Label(search, text="ODKUD VYRÁŽÍŠ?  ·  POLOHA PRO HLEDÁNÍ A TRASU", bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 8))
        row = tk.Frame(search, bg=PANEL)
        row.pack(fill="x")
        entry_border = tk.Frame(row, bg="#f5f8f9", highlightbackground=LINE, highlightthickness=1)
        entry_border.pack(side="left", fill="x", expand=True, padx=(0, 16))
        tk.Label(entry_border, text="⌕", bg="#f5f8f9", fg=GREEN, font=("Segoe UI", 22)).pack(side="left", padx=(12, 9))
        self.city_var = tk.StringVar()
        self.city_entry = tk.Entry(entry_border, textvariable=self.city_var, bg="#f5f8f9", fg=TEXT,
                                   insertbackground=GREEN, relief="flat", font=("Segoe UI", 12))
        self.city_entry.pack(side="left", fill="x", expand=True, ipady=9, padx=(0, 12))
        self.city_entry.bind("<Return>", self._location_enter)
        self.city_entry.bind("<Down>", self._focus_suggestions)
        self.city_entry.bind("<Escape>", lambda _e: self._hide_suggestions())
        self.city_entry.bind("<FocusIn>", lambda _e: entry_border.configure(highlightbackground=GREEN))
        self.city_entry.bind("<FocusOut>", lambda _e: entry_border.configure(highlightbackground=LINE))
        tk.Label(row, text="Okruh", bg=PANEL, fg=MUTED, font=("Segoe UI", 10)).pack(side="left", padx=(0, 8))
        self.radius_var = tk.StringVar(value="15")
        radius = ttk.Combobox(row, textvariable=self.radius_var, values=(5, 10, 15, 25, 50),
                             width=4, state="readonly", style="Fuel.TCombobox")
        radius.pack(side="left")
        tk.Label(row, text="km", bg=PANEL, fg=MUTED).pack(side="left", padx=(6, 18))
        radius.bind("<<ComboboxSelected>>", lambda _e: self.search() if self.city_var.get().strip() else None)
        self.search_button = self._button(row, "Hledat stanice", self.search, primary=True)
        self.search_button.pack(side="right")
        self.city_var.trace_add("write", self._location_changed)
        location_row = tk.Frame(search, bg=PANEL)
        location_row.pack(fill="x", pady=(7, 0))
        self.location_button = tk.Button(location_row, text="◎ Použít moji polohu", command=self.use_my_location,
                                         bg=PANEL, fg=GREEN, activebackground="#edf4f1", activeforeground=GREEN,
                                         disabledforeground=MUTED, relief="flat", cursor="hand2", borderwidth=0,
                                         font=("Segoe UI", 9, "bold"), padx=0, pady=0)
        self.location_button.pack(side="left")
        tk.Label(location_row, text="nebo zadej město či adresu", bg=PANEL,
                 fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=12)
        tk.Button(location_row, text="Nastavení polohy", command=self.open_location_settings, bg=PANEL, fg=MUTED,
                  activebackground=PANEL, activeforeground=GREEN, relief="flat", borderwidth=0, cursor="hand2",
                  font=("Segoe UI", 9), padx=0, pady=0).pack(side="right")
        self.suggestion_box = tk.Listbox(content, bg=PANEL, fg=TEXT, height=5, selectbackground="#dcefe8",
                                         selectforeground=GREEN, relief="flat", exportselection=False,
                                         highlightthickness=1, highlightbackground=LINE,
                                         font=("Segoe UI", 11), activestyle="none")
        self.suggestion_box.bind("<ButtonRelease-1>", self._choose_suggestion)
        self.suggestion_box.bind("<Return>", self._choose_suggestion)
        self.suggestion_box.bind("<Escape>", lambda _e: self._hide_suggestions())
        self.suggestion_hint = tk.Label(content, bg=BG, fg=MUTED, anchor="w", font=("Segoe UI", 9))

        cards = tk.Frame(content, bg=BG)
        cards.pack(fill="x", pady=(0, 14))
        for i in range(4):
            cards.columnconfigure(i, weight=1, uniform="card")
        self.station_count = self._stat_card(cards, "STANICE V OKOLÍ", "—", "Vzdálenost vzdušnou čarou", 0, True)
        self.average_cards = {
            "benzín": self._stat_card(cards, "PRŮMĚR ČR / NATURAL 95", "—", "ČSÚ · týdenní cena", 1),
            "nafta": self._stat_card(cards, "PRŮMĚR ČR / NAFTA", "—", "ČSÚ · týdenní cena", 2),
            "lpg": self._stat_card(cards, "PRŮMĚR ČR / LPG", "—", "ČSÚ · týdenní cena", 3),
        }

        toolbar = tk.Frame(content, bg=BG)
        toolbar.pack(fill="x", pady=(0, 8))
        tk.Label(toolbar, text="Stanice v okolí", bg=BG, fg=TEXT, font=("Segoe UI", 17, "bold")).pack(side="left")
        self.result_count_var = tk.StringVar(value="Zatím žádné výsledky")
        tk.Label(toolbar, textvariable=self.result_count_var, bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=14)
        self.type_var = tk.StringVar(value="Všechny typy cen")
        self.type_filter = ttk.Combobox(toolbar, textvariable=self.type_var,
                                       values=("Všechny typy cen", "Ceník Tank ONO", "Hlášení uživatele", "Odhad", "Cena neznámá"),
                                       state="readonly", width=20, style="Fuel.TCombobox")
        self.type_filter.pack(side="right")
        self.type_var.trace_add("write", lambda *_: self._render())

        controls = tk.Frame(content, bg=BG)
        controls.pack(fill="x", pady=(0, 8))
        tk.Label(controls, text="Seřadit podle", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(0, 10))
        self.sort_var = tk.StringVar(value="Vzdálenost")
        self.sort_combo = ttk.Combobox(controls, textvariable=self.sort_var, values=tuple(SORT_LABELS),
                                      state="readonly", width=15, style="Fuel.TCombobox")
        self.sort_combo.pack(side="left")
        self.sort_var.trace_add("write", self._sort_selected)
        self.direction_button = self._button(controls, "↑ Vzestupně", self._toggle_sort_direction)
        self.direction_button.pack(side="left", padx=8)
        tk.Label(controls, text="Řadit můžeš i kliknutím na záhlaví sloupce.", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="right")

        table_frame = tk.Frame(content, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        table_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table_frame, columns=tuple(HEADINGS), show="headings", selectmode="browse")
        widths = {"name": 170, "address": 220, "distance": 110, "benzín": 115, "nafta": 115, "lpg": 115, "kind": 150}
        for column in HEADINGS:
            self.tree.heading(column, text=HEADINGS[column], command=lambda col=column: self._sort_by(col))
            self.tree.column(column, width=widths[column], minwidth=90 if column in ("name", "address", "kind") else 80,
                             anchor="w" if column in ("name", "address", "kind") else "center")
        self.tree.tag_configure("even", background=PANEL)
        self.tree.tag_configure("odd", background="#f7fafb")
        vertical = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", self._select_station)
        self.tree.bind("<Double-1>", self._table_double_click)
        self.tree.bind("<Return>", lambda _e: self.navigate())
        self.empty = tk.Label(table_frame, text="Tvoje další zastávka začíná tady.\n\nZadej město nebo adresu do vyhledávání.",
                              bg=PANEL, fg=MUTED, font=("Segoe UI", 12), justify="center")
        self.empty.place(relx=.5, rely=.5, anchor="center")

        bottom = tk.Frame(content, bg=BG)
        bottom.pack(before=table_frame, side="bottom", fill="x", pady=(14, 0))
        self.detail_var = tk.StringVar(value="Vyber stanici pro detail ceny.  ≈ odhad   ·   — cena není uvedena")
        self.detail_label = tk.Label(bottom, textvariable=self.detail_var, bg=BG, fg=MUTED, justify="left",
                                     font=("Segoe UI", 9), anchor="w")
        self.detail_label.pack(side="left", fill="x", expand=True)
        self.detail_label.bind("<Configure>", lambda e: self.detail_label.configure(wraplength=max(1, e.width)))
        self.navigate_button = self._button(bottom, "Navigovat ↗", self.navigate, primary=True)
        self.navigate_button.configure(state="disabled")
        self.navigate_button.pack(side="right", padx=(10, 0))
        self.map_button = self._button(bottom, "Jen poloha ↗", self.open_map)
        self.map_button.configure(state="disabled")
        self.map_button.pack(side="right", padx=(16, 0))
        self.status_var = tk.StringVar(value="Připraveno na cestu")
        tk.Label(content, textvariable=self.status_var, bg=BG, fg=MUTED, anchor="w", font=("Segoe UI", 8)).pack(
            before=bottom, side="bottom", fill="x", pady=(10, 0))
        self._update_sort_headers()

    def _stat_card(self, parent, title, value, hint, column, accent=False):
        color = GREEN if accent else PANEL
        panel = RoundedPanel(parent, color=color, padding=14)
        panel.grid(row=0, column=column, sticky="nsew", padx=(0, 12 if column < 3 else 0))
        body = panel.body
        tk.Label(body, text=title, bg=color, fg="#bce1d6" if accent else MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        label = tk.Label(body, text=value, bg=color, fg="white" if accent else TEXT, font=("Segoe UI", 21, "bold"))
        label.pack(anchor="w", pady=(7, 3))
        label.hint_label = tk.Label(body, text=hint, bg=color, fg="#bce1d6" if accent else MUTED, font=("Segoe UI", 8))
        label.hint_label.pack(anchor="w")
        return label
