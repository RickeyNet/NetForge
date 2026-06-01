"""Reusable Tk/ttk widgets."""

import tkinter as tk
from tkinter import ttk

from netforge.ui.theme import C

# ---------------------------------------------------------------------------
# PanedWindow with non-opaque sash drag
# ---------------------------------------------------------------------------
class PanedWindow(tk.PanedWindow):
    """Drop-in replacement for ttk.PanedWindow that uses opaqueresize=False.

    During sash drag the panes do NOT resize live - Tk shows a thin guide
    line instead and resizes once on mouse release. This avoids the per-pixel
    Configure cascade through every nested ScrollFrame and Text widget, which
    is the main source of sash-drag lag on Windows.

    The ttk API uses add(child, weight=N); tk uses add(child, stretch=...).
    We accept weight= and translate it heuristically: weight 0 -> never,
    everything else -> always. That's enough for the two- and three-pane
    setups in this app - the largest non-zero weight gets the leftover
    space on window resize.
    """

    def __init__(self, parent, orient="horizontal", **kw):
        kw.setdefault("opaqueresize", False)
        kw.setdefault("orient", orient)
        kw.setdefault("bd", 0)
        kw.setdefault("sashwidth", 6)
        kw.setdefault("sashrelief", "flat")
        kw.setdefault("bg", C.get("border", "#444"))
        super().__init__(parent, **kw)

    def add(self, child, weight=None, **kw):
        if weight is not None and "stretch" not in kw:
            kw["stretch"] = "never" if weight == 0 else "always"
        super().add(child, **kw)

    def sashpos(self, index, position=None):
        # ttk-compatible shim. tk uses sash_place(index, x, y) for horizontal.
        if position is None:
            return self.sash_coord(index)[0]
        try:
            self.sash_place(index, position, 1)
        except tk.TclError:
            pass
        return position


# ---------------------------------------------------------------------------
# Scrollable frame widget
# ---------------------------------------------------------------------------
class ScrollFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, bg=C["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner,
                                              anchor="nw")
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        # Debounce both Configure handlers: collapse per-pixel resize events
        # into one idle-time update so dragging the window edge doesn't fire
        # an O(N) bbox/itemconfig cascade for every pixel of motion.
        self._last_width = -1
        self._sr_after_id = None
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        # Bind the wheel directly. We re-walk descendants the first time
        # the cursor enters the area (lazy) so we don't pay for the walk
        # if the user never scrolls this particular ScrollFrame.
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.inner.bind("<MouseWheel>", self._on_wheel)
        self._wheel_walked = False
        self._wheel_bound_ids = set()
        self.inner.bind("<Enter>", self._propagate_wheel_binds)

    def _on_inner_configure(self, _e):
        # Cancel any pending update so a continuous drag collapses to
        # ONE bbox/scrollregion call after motion stops, not one per
        # idle cycle (which still runs constantly during a drag).
        if self._sr_after_id is not None:
            try:
                self.after_cancel(self._sr_after_id)
            except tk.TclError:
                pass
        self._sr_after_id = self.after(60, self._apply_scrollregion)

    def _apply_scrollregion(self):
        self._sr_after_id = None
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except tk.TclError:
            pass

    def sync_scrollregion(self):
        """Force an immediate scrollregion recompute against the inner
        frame's requested height.  Use after batched DOM-style changes
        (clearing and rebuilding subsections) so the scrollbar doesn't
        keep slack from the previously taller layout."""
        try:
            self.update_idletasks()
            h = max(1, self.inner.winfo_reqheight())
            w = max(1, self.canvas.winfo_width())
            self.canvas.configure(scrollregion=(0, 0, w, h))
        except tk.TclError:
            pass

    def _on_canvas_resize(self, event):
        # Bindtag propagation routes descendant <Configure> events here too;
        # only the canvas's own resize should drive the inner-window width.
        if event.widget is not self.canvas:
            return
        if event.width == self._last_width:
            return
        self._last_width = event.width
        try:
            self.canvas.itemconfig(self._win, width=event.width)
        except tk.TclError:
            pass

    def _propagate_wheel_binds(self, _e=None):
        # Walk descendants ONCE per Enter and bind <MouseWheel> directly.
        # We track already-bound widget ids so re-entries are O(N) without
        # re-binding. Cheaper than bind_all (no global firing) and avoids
        # bindtag propagation (which leaks <Configure> events).
        stack = list(self.inner.winfo_children())
        while stack:
            w = stack.pop()
            wid = str(w)
            if wid not in self._wheel_bound_ids:
                try:
                    w.bind("<MouseWheel>", self._on_wheel, add="+")
                    self._wheel_bound_ids.add(wid)
                except tk.TclError:
                    pass
            stack.extend(w.winfo_children())

    def _on_wheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

class _CheckList(tk.Frame):
    """Scrollable list where every row has a checkbox and a clickable label."""

    def __init__(self, parent, on_click=None, **kw):
        super().__init__(parent, bg=C["bg_input"], **kw)
        vsb = ttk.Scrollbar(self, orient="vertical")
        vsb.pack(side="right", fill="y")
        self._canvas = tk.Canvas(self, bg=C["bg_input"], bd=0,
                                  highlightthickness=0,
                                  yscrollcommand=vsb.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        vsb.config(command=self._canvas.yview)
        self._inner = tk.Frame(self._canvas, bg=C["bg_input"])
        self._win_id = self._canvas.create_window(
            (0, 0), window=self._inner, anchor="nw")
        # Debounce Configure handlers so per-pixel resize doesn't kick off
        # an O(N) bbox/itemconfig cascade on every frame of motion.
        self._cl_last_width = -1
        self._cl_sr_after_id = None
        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._on_click = on_click
        self._vars     = {}   # name -> BooleanVar
        self._labels   = {}   # name -> tk.Label
        self._frames   = {}   # name -> tk.Frame
        self._selected = None

    def _on_wheel(self, e):
        self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def _on_inner_configure(self, _e):
        if self._cl_sr_after_id is not None:
            try:
                self.after_cancel(self._cl_sr_after_id)
            except tk.TclError:
                pass
        self._cl_sr_after_id = self.after(60, self._apply_scrollregion)

    def _apply_scrollregion(self):
        self._cl_sr_after_id = None
        try:
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        except tk.TclError:
            pass

    def _on_canvas_resize(self, event):
        if event.widget is not self._canvas:
            return
        if event.width == self._cl_last_width:
            return
        self._cl_last_width = event.width
        try:
            self._canvas.itemconfig(self._win_id, width=event.width)
        except tk.TclError:
            pass

    def populate(self, names):
        for w in self._inner.winfo_children():
            w.destroy()
        self._vars.clear()
        self._labels.clear()
        self._frames.clear()
        self._selected = None
        for name in names:
            self._add_row(name)

    def _add_row(self, name):
        var = tk.BooleanVar()
        row = tk.Frame(self._inner, bg=C["bg_input"])
        row.pack(fill="x", padx=2, pady=1)
        cb = tk.Checkbutton(row, variable=var,
                             bg=C["bg_input"], fg=C["fg"],
                             activebackground=C["bg_input"],
                             selectcolor=C["bg2"],
                             relief="flat", bd=0, cursor="hand2")
        cb.pack(side="left")
        lbl = tk.Label(row, text=name, anchor="w",
                       bg=C["bg_input"], fg=C["fg"],
                       font=("Consolas", 10), cursor="hand2")
        lbl.pack(side="left", fill="x", expand=True, padx=(2, 4))
        for w in (row, lbl):
            w.bind("<Button-1>", lambda e, n=name: self._click(n))
        for w in (row, lbl, cb):
            w.bind("<MouseWheel>", self._on_wheel)
        self._vars[name]   = var
        self._labels[name] = lbl
        self._frames[name] = row

    def _click(self, name):
        if self._selected and self._selected in self._labels:
            self._labels[self._selected].configure(bg=C["bg_input"])
            self._frames[self._selected].configure(bg=C["bg_input"])
        self._selected = name
        self._labels[name].configure(bg=C["sel_bg"])
        self._frames[name].configure(bg=C["sel_bg"])
        if self._on_click:
            self._on_click(name)

    def get_checked(self):
        return [n for n, v in self._vars.items() if v.get()]

    def get_selected(self):
        return self._selected

    def clear_selection(self):
        if self._selected and self._selected in self._labels:
            self._labels[self._selected].configure(bg=C["bg_input"])
            self._frames[self._selected].configure(bg=C["bg_input"])
        self._selected = None

    def select(self, name):
        if name not in self._frames:
            return
        self._click(name)
        self._frames[name].update_idletasks()
        y      = self._frames[name].winfo_y()
        total  = self._inner.winfo_height()
        ch     = self._canvas.winfo_height()
        if total > ch:
            self._canvas.yview_moveto(y / total)

    def set_dim(self, name, dimmed=True):
        """Render *name* in a dim color (used to mark hidden items)."""
        lbl = self._labels.get(name)
        if not lbl:
            return
        lbl.configure(fg=C["fg_dim"] if dimmed else C["fg"])

    def select_all(self):
        """Check all checkboxes. If all are already checked, uncheck all."""
        all_checked = all(v.get() for v in self._vars.values()) if self._vars else False
        for v in self._vars.values():
            v.set(not all_checked)
