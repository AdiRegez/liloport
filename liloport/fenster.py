"""Kleines Startfenster für das installierte Liloport (Desktop-Symbol).

Liloport ist ein lokaler Webserver; ohne Konsole sähe man sonst nicht, dass er läuft, und könnte ihn nicht
beenden. Das Fenster zeigt den Zustand, öffnet Dashboard und Inhalte-Ordner und beendet Liloport.
Es braucht nur tkinter aus der Standardbibliothek. Fehlt tkinter (manche Linux-Pythons), gibt
`verfuegbar()` False zurück und Liloport läuft ohne Fenster; beenden lässt es sich dann im Dashboard.
"""
import sys
import threading
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import font as tkfont, messagebox, ttk
except ImportError:   # pragma: no cover – je nach Python-Installation
    tk = None

TAKT_MS = 250   # so oft schaut das Fenster nach, ob Liloport von anderswo (Dashboard) beendet wurde


def verfuegbar() -> bool:
    """Ist tkinter vorhanden? (Ob es eine Anzeige gibt, zeigt sich erst beim Öffnen des Fensters: tk.TclError.)"""
    return tk is not None


GRAU = None if sys.platform == "darwin" else "#66597a"   # macOS: Systemfarbe (passt zum dunklen Modus)


def _windows_scharf():
    """Windows mit hoher Bildschirmauflösung: Fenster scharf statt hochskaliert und unscharf."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


class Startfenster:
    """Hauptfenster; läuft im Haupt-Thread (macOS verlangt das), Liloport selbst in einem Hintergrund-Thread.

    starten: Funktion ohne Argumente, richtet Liloport ein und gibt (adresse, ordner) zurück; läuft im Hintergrund.
    oeffnen: Funktion(adresse) – Browser öffnen.  ordner_oeffnen: Funktion(Path).
    beendet: threading.Event – wird gesetzt, wenn Liloport anderswo beendet wurde (Knopf im Dashboard).
    """

    def __init__(self, titel: str, version: str, icon: Path, starten, oeffnen, ordner_oeffnen, beendet: threading.Event):
        self.starten, self.oeffnen, self.ordner_oeffnen, self.beendet = starten, oeffnen, ordner_oeffnen, beendet
        self.adresse, self.ordner, self.fehler, self.bereit = None, None, None, False
        self.ergebnis = "beendet"
        _windows_scharf()
        self.root = tk.Tk(className="Liloport")   # Fensterklasse; unter Linux passend zu StartupWMClass
        self.root.title(titel)
        self.root.resizable(False, False)
        self._bild = None
        try:
            self._bild = tk.PhotoImage(file=str(icon))
            self.root.iconphoto(True, self._bild)
        except (tk.TclError, OSError):
            pass
        self._aufbauen(titel, version)
        self.root.protocol("WM_DELETE_WINDOW", self._schliessen_gefragt)
        # macOS: Cmd+Q bzw. «Beenden» im Programm-Menü, Klick aufs Dock-Symbol
        try:
            self.root.createcommand("::tk::mac::Quit", self.beenden)
            self.root.createcommand("::tk::mac::ReopenApplication", self._wieder_vorne)
        except tk.TclError:
            pass

    # ---------- Aufbau ----------

    def _aufbauen(self, titel, version):
        basis = tkfont.nametofont("TkDefaultFont")
        gross = basis.copy(); gross.configure(size=max(15, basis.cget("size") + 6), weight="bold")
        fett = basis.copy(); fett.configure(weight="bold")
        self._schriften = (gross, fett)
        rahmen = ttk.Frame(self.root, padding=(22, 18, 22, 16))
        rahmen.grid(sticky="nsew")
        kopf = ttk.Frame(rahmen)
        kopf.grid(row=0, column=0, sticky="w")
        if self._bild is not None:
            klein = self._bild.subsample(max(1, self._bild.width() // 48))
            self._klein = klein
            ttk.Label(kopf, image=klein).grid(row=0, column=0, rowspan=2, padx=(0, 12))
        ttk.Label(kopf, text=titel, font=gross).grid(row=0, column=1, sticky="w")
        ttk.Label(kopf, text=f"Version {version}" if version else "", foreground=GRAU).grid(row=1, column=1, sticky="w")

        self.status = ttk.Label(rahmen, text="Liloport startet …", font=fett, wraplength=360)
        self.status.grid(row=1, column=0, sticky="w", pady=(16, 4))
        self.info = ttk.Label(rahmen, text="Das Dashboard öffnet sich gleich im Browser.", wraplength=360, justify="left")
        self.info.grid(row=2, column=0, sticky="w")

        # Adresse zum Kopieren: hilft, wenn sich der Browser nicht von selbst öffnet
        self.adresszeile = ttk.Frame(rahmen)
        self.adresse_text = tk.StringVar(value="")
        self.adressfeld = ttk.Entry(self.adresszeile, textvariable=self.adresse_text, state="readonly", width=30)
        self.adressfeld.grid(row=0, column=0, sticky="we", padx=(0, 8))
        self.k_kopieren = ttk.Button(self.adresszeile, text="Adresse kopieren", command=self._kopieren)
        self.k_kopieren.grid(row=0, column=1)
        self.adresszeile.columnconfigure(0, weight=1)

        knoepfe = ttk.Frame(rahmen)
        knoepfe.grid(row=4, column=0, sticky="w", pady=(16, 10))
        self.k_dashboard = ttk.Button(knoepfe, text="Dashboard öffnen", command=self._dashboard, state="disabled")
        self.k_dashboard.grid(row=0, column=0, padx=(0, 8))
        self.k_ordner = ttk.Button(knoepfe, text="Ordner öffnen", command=self._ordner, state="disabled")
        self.k_ordner.grid(row=0, column=1, padx=(0, 8))
        ttk.Button(knoepfe, text="Beenden", command=self.beenden).grid(row=0, column=2)

        ttk.Label(rahmen, text="Dieses Fenster offen lassen, solange du mit Liloport arbeitest. "
                               "Schliessen beendet Liloport; deine Inhalte bleiben im Inhalte-Ordner.",
                  foreground=GRAU, wraplength=360, justify="left").grid(row=5, column=0, sticky="w")

    # ---------- Ablauf ----------

    def ausfuehren(self) -> str:
        """Zeigt das Fenster, startet Liloport im Hintergrund und kehrt zurück, wenn beendet wird.
        Rückgabe: 'beendet' oder 'fehler'."""
        import time
        self._t0 = time.monotonic()
        threading.Thread(target=self._starten_im_hintergrund, daemon=True).start()
        self._uhr = self.root.after(TAKT_MS, self._pruefen)
        self.root.mainloop()
        return self.ergebnis

    def _starten_im_hintergrund(self):
        try:
            self.adresse, self.ordner = self.starten()
        except Exception as e:  # noqa: BLE001 – jede Ursache soll im Fenster erscheinen
            import traceback
            traceback.print_exc()
            self.fehler = e
        self.bereit = True

    def _pruefen(self):
        if self.beendet.is_set():
            self._zu()
            return
        if self.bereit and self.fehler is not None:
            self.ergebnis = "fehler"
            self.root.withdraw()
            messagebox.showerror("Liloport konnte nicht starten", str(self.fehler) or type(self.fehler).__name__)
            self._zu()
            return
        if not self.bereit and not getattr(self, "_lang_gemeldet", False):
            import time
            if time.monotonic() - self._t0 > 12:
                self._lang_gemeldet = True
                self.info.configure(text="Das dauert länger als üblich: Liloport bereitet deine Seiten vor. "
                                         "Bitte warten. Bleibt es dabei, hilft die Datei liloport.log im "
                                         "Einstellungsordner bei der Fehlersuche.")
        if self.bereit and self.adresse and str(self.k_dashboard["state"]) == "disabled":
            self.status.configure(text="Liloport läuft.")
            self.info.configure(text=f"Inhalte-Ordner: {self.ordner}")
            self.adresse_text.set(self.adresse)
            self.adresszeile.grid(row=3, column=0, sticky="we", pady=(10, 0))
            self.k_dashboard.configure(state="normal")
            self.k_ordner.configure(state="normal")
            self._dashboard()
        if self._browser_ok is False:
            self._browser_ok = None
            self.status.configure(text="Liloport läuft – bitte den Browser selbst öffnen.")
            self.info.configure(text="Der Browser liess sich nicht automatisch öffnen. Bitte «Adresse kopieren» "
                                     "klicken, einen Browser starten (z. B. Edge, Firefox oder Chrome) und die "
                                     "Adresse dort in die Adresszeile einfügen.")
        self._uhr = self.root.after(TAKT_MS, self._pruefen)

    # ---------- Knöpfe ----------

    _browser_ok = None   # None: unbekannt/läuft, True: geöffnet, False: ging nicht (Hinweis anzeigen)

    def _dashboard(self):
        """Browser in einem eigenen Thread öffnen: Hängt das Betriebssystem dabei, bleibt das Fenster bedienbar."""
        if not self.adresse:
            return

        def lauf():
            try:
                ok = self.oeffnen(self.adresse)
            except Exception:  # noqa: BLE001
                ok = False
            if ok is False:
                self._browser_ok = False

        threading.Thread(target=lauf, name="browser", daemon=True).start()

    def _kopieren(self):
        if not self.adresse:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.adresse)
            self.root.update()   # Windows: Zwischenablage sofort übernehmen
            self.k_kopieren.configure(text="Kopiert ✓")
            self.root.after(2000, lambda: self.k_kopieren.configure(text="Adresse kopieren"))
        except tk.TclError:
            pass

    def _ordner(self):
        if self.ordner:
            try:
                self.ordner_oeffnen(Path(self.ordner))
            except OSError as e:
                messagebox.showerror("Ordner öffnen", str(e))

    def _wieder_vorne(self, *args):
        self.root.deiconify()
        self.root.lift()
        self._dashboard()

    def _schliessen_gefragt(self):
        if messagebox.askokcancel("Liloport beenden?", "Liloport wird beendet. Das Dashboard und die Seiten im "
                                  "Browser lassen sich danach nur noch lesen, nicht mehr bearbeiten.",
                                  parent=self.root):
            self.beenden()

    def beenden(self):
        self.ergebnis = "beendet"
        self.beendet.set()
        self._zu()

    def _zu(self):
        """Fenster schliessen; geplante Prüfung vorher abbestellen (sonst meldet Tcl einen Fehler)."""
        try:
            if getattr(self, "_uhr", None):
                self.root.after_cancel(self._uhr)
            self.root.destroy()
        except tk.TclError:
            pass
