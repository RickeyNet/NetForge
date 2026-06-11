"""Form helpers, dialogs, and context menus."""

import tkinter as tk
from tkinter import ttk

from netforge.ui.theme import C
from netforge.ui.win_theme import _apply_icon

# ---------------------------------------------------------------------------
# Right-click context menu
# ---------------------------------------------------------------------------
def _attach_context_menu(widget):
    """Attach a right-click context menu with Cut/Copy/Paste/Select All."""
    def _show(event):
        menu = tk.Menu(widget, tearoff=0,
                       bg=C["bg2"], fg=C["fg"],
                       activebackground=C["border"],
                       activeforeground=C["fg"],
                       relief="flat", bd=1)
        is_text = isinstance(widget, tk.Text)
        is_entry = isinstance(widget, (ttk.Entry, ttk.Combobox))
        readonly = False
        if is_entry:
            readonly = str(widget.cget("state")) in ("readonly", "disabled")
        elif is_text:
            readonly = str(widget.cget("state")) == "disabled"

        has_sel = False
        try:
            if is_text:
                has_sel = bool(widget.tag_ranges("sel"))
            elif is_entry:
                widget.selection_get()
                has_sel = True
        except (tk.TclError, Exception):
            pass

        has_clip = False
        try:
            widget.clipboard_get()
            has_clip = True
        except (tk.TclError, Exception):
            pass

        if not readonly:
            menu.add_command(label="Cut", accelerator="Ctrl+X",
                            state="normal" if has_sel else "disabled",
                            command=lambda: widget.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", accelerator="Ctrl+C",
                         state="normal" if has_sel else "disabled",
                         command=lambda: widget.event_generate("<<Copy>>"))
        if not readonly:
            menu.add_command(label="Paste", accelerator="Ctrl+V",
                            state="normal" if has_clip else "disabled",
                            command=lambda: widget.event_generate("<<Paste>>"))
        menu.add_separator()
        if is_text:
            menu.add_command(label="Select All", accelerator="Ctrl+A",
                            command=lambda: (widget.tag_add("sel", "1.0", "end"),
                                             widget.mark_set("insert", "end")))
        elif is_entry:
            menu.add_command(label="Select All", accelerator="Ctrl+A",
                            command=lambda: (widget.select_range(0, "end"),
                                             widget.icursor("end")))
        menu.tk_popup(event.x_root, event.y_root)
    widget.bind("<Button-3>", _show)


# ---------------------------------------------------------------------------
# Reusable form helpers
# ---------------------------------------------------------------------------
def _section(parent, title):
    ttk.Label(parent, text=title, style="Sec.TLabel").pack(
        anchor="w", padx=5, pady=(14, 2))
    ttk.Separator(parent).pack(fill="x", padx=5)


def _field(parent, label, default="", width=35):
    f = ttk.Frame(parent); f.pack(fill="x", padx=5, pady=2)
    ttk.Label(f, text=label, width=26, anchor="w").pack(side="left", padx=(0, 6))
    e = ttk.Entry(f, width=width)
    e.pack(side="left", fill="x", expand=True)
    if default:
        e.insert(0, default)
    _attach_context_menu(e)
    return e


def _textarea(parent, label, default="", h=5):
    f = ttk.Frame(parent); f.pack(fill="x", padx=5, pady=2)
    if label:
        ttk.Label(f, text=label, width=26, anchor="nw").pack(
            side="left", padx=(0, 6))
    t = tk.Text(f, height=h, font=("Consolas", 9),
                bg=C["bg_input"], fg=C["fg"], insertbackground=C["fg"],
                selectbackground=C["sel_bg"], relief="flat", bd=2, wrap="word")
    t.pack(side="left", fill="x", expand=True)
    if default:
        t.insert("1.0", default)
    _attach_context_menu(t)
    return t


def _autosize_textarea(widget, min_h=2, max_h=20):
    """Make a tk.Text resize itself to fit its content.

    Recomputes height on every modification, clamped to [min_h, max_h].
    Use min_h=2 so an empty section visually shrinks but stays clickable;
    max_h prevents one big section from blowing out the form layout.
    """
    def _resize(_event=None):
        # 'end-1c' avoids counting Tk's trailing implicit newline.
        line_count = int(widget.index("end-1c").split(".")[0])
        # Count wrapped display lines too, so wide pasted text shows fully.
        try:
            display_lines = widget.count("1.0", "end-1c", "displaylines") or [0]
            wrapped = max(line_count, display_lines[0])
        except Exception:
            wrapped = line_count
        new_h = max(min_h, min(max_h, wrapped))
        if int(widget.cget("height")) != new_h:
            widget.configure(height=new_h)

    def _on_modified(_event=None):
        # tk.Text fires <<Modified>> once and latches; reset the flag.
        widget.edit_modified(False)
        _resize()

    widget.bind("<<Modified>>", _on_modified)
    # Run once after the widget is mapped so initial content sizes correctly.
    widget.after_idle(_resize)
    # Expose for callers that programmatically reload content.
    widget._autosize = _resize
    return widget


def _scrolled_text(parent, **text_kwargs):
    """tk.Text + themed ttk.Scrollbar pair packed into a frame.

    Drop-in replacement for scrolledtext.ScrolledText whose embedded
    classic tk.Scrollbar ignores our ttk theme. The frame uses the
    text widget's own pack/grid settings; callers should pack the
    *returned text widget* (its parent frame is auto-sized to it).
    """
    holder = ttk.Frame(parent)
    text = tk.Text(holder, **text_kwargs)
    sb = ttk.Scrollbar(holder, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    text.pack(side="left", fill="both", expand=True)
    # Forward pack/grid/place on the text widget to the holder so callers
    # can keep treating `text` like a single widget.
    for method in ("pack", "grid", "place",
                   "pack_forget", "grid_forget", "place_forget"):
        setattr(text, method, getattr(holder, method))
    return text


def _combo(parent, label, values, width=33):
    f = ttk.Frame(parent); f.pack(fill="x", padx=5, pady=2)
    ttk.Label(f, text=label, width=22, anchor="w").pack(side="left")
    cb = ttk.Combobox(f, values=values, width=width, state="readonly")
    cb.pack(side="left", fill="x", expand=True)
    return cb


def _copy_name(name, existing):
    """Return a unique copy name not already in *existing*."""
    candidate = f"{name} (copy)"
    n = 1
    while candidate in existing:
        n += 1
        candidate = f"{name} (copy {n})"
    return candidate


def _toggle_hidden_batch(tab, category, singular):
    """Hide or unhide the items currently selected on *tab*.

    Prefers checked items (multi-select) and falls back to the
    single-click selection. If the batch is a mix of hidden and visible,
    the action is normalized to 'hide all' (a second click then unhides
    them all). After the change the editor's list refreshes and the
    Generate tab's dropdowns are rebuilt so the effect is immediate.
    """
    names = tab.lb.get_checked()
    if not names:
        sel = tab.lb.get_selected()
        if not sel:
            _dialog("No Selection",
                    f"Select a {singular} (or check one or more) "
                    "to hide or unhide.")
            return
        names = [sel]

    hidden_set = tab.app.hidden.get(category, set())
    all_hidden = all(n in hidden_set for n in names)
    action_hide = not all_hidden  # mixed -> normalize to hide

    for n in names:
        already = n in hidden_set
        if action_hide and not already:
            tab.app.toggle_hidden(category, n)
        elif (not action_hide) and already:
            tab.app.toggle_hidden(category, n)

    tab._refresh()
    if hasattr(tab.app, "gen_tab"):
        tab.app.gen_tab.refresh_combos()
    if category == "base_sets" and hasattr(tab.app, "profiles_tab"):
        try:
            tab.app.profiles_tab.base_set_cb["values"] = \
                tab.app._visible_base_set_names()
        except Exception:
            pass

    verb = "hidden" if action_hide else "visible"
    if len(names) == 1:
        _dialog("Hidden" if action_hide else "Visible",
                f"'{names[0]}' is now {verb}.")
    else:
        _dialog("Hidden" if action_hide else "Visible",
                f"{len(names)} {singular}s are now {verb}.")


def _center_over(dlg, parent):
    """Centre a Toplevel over *parent*, clamped to on-screen."""
    dlg.update_idletasks()
    try:
        rx = parent.winfo_x() + (parent.winfo_width()
                                 - dlg.winfo_width()) // 2
        ry = parent.winfo_y() + (parent.winfo_height()
                                 - dlg.winfo_height()) // 2
        dlg.geometry(f"+{max(0, rx)}+{max(0, ry)}")
    except Exception:
        pass


def _dialog(title, msg, kind="info"):
    """Themed modal info / warning / error dialog."""
    accent = C["red"] if kind == "error" else C["accent"]
    dlg = tk.Toplevel()
    dlg.title(title)
    dlg.configure(bg=C["bg"])
    dlg.resizable(False, False)
    _apply_icon(dlg)
    dlg.grab_set()
    tk.Frame(dlg, bg=accent, height=3).pack(fill="x")
    inner = ttk.Frame(dlg, padding=(22, 14, 22, 18))
    inner.pack()
    ttk.Label(inner, text=title, style="Sec.TLabel").pack(anchor="w")
    ttk.Label(inner, text=msg, wraplength=320,
              justify="left").pack(anchor="w", pady=(6, 18))
    ttk.Button(inner, text="OK", command=dlg.destroy).pack(anchor="e")
    dlg.update_idletasks()
    try:
        root = dlg.nametowidget(".")
        rx = root.winfo_x() + (root.winfo_width()  - dlg.winfo_width())  // 2
        ry = root.winfo_y() + (root.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{max(0, rx)}+{max(0, ry)}")
    except Exception:
        pass
    dlg.wait_window()


def _ask(title, msg):
    """Themed yes/no confirmation dialog. Returns True if user clicks Yes."""
    result = [False]
    dlg = tk.Toplevel()
    dlg.title(title)
    dlg.configure(bg=C["bg"])
    dlg.resizable(False, False)
    _apply_icon(dlg)
    dlg.grab_set()
    tk.Frame(dlg, bg=C["red"], height=3).pack(fill="x")
    inner = ttk.Frame(dlg, padding=(22, 14, 22, 18))
    inner.pack()
    ttk.Label(inner, text=title, style="Sec.TLabel").pack(anchor="w")
    ttk.Label(inner, text=msg, wraplength=320,
              justify="left").pack(anchor="w", pady=(6, 18))
    bf = ttk.Frame(inner)
    bf.pack(anchor="e")
    def _yes():
        result[0] = True
        dlg.destroy()
    ttk.Button(bf, text="Yes", style="Del.TButton",
               command=_yes).pack(side="left", padx=(0, 6))
    ttk.Button(bf, text="Cancel", command=dlg.destroy).pack(side="left")
    dlg.update_idletasks()
    try:
        root = dlg.nametowidget(".")
        rx = root.winfo_x() + (root.winfo_width()  - dlg.winfo_width())  // 2
        ry = root.winfo_y() + (root.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{max(0, rx)}+{max(0, ry)}")
    except Exception:
        pass
    dlg.wait_window()
    return result[0]


def _dark_listbox(parent, **kw):
    return tk.Listbox(parent, font=("Consolas", 10),
                      bg=C["bg_input"], fg=C["fg"],
                      selectbackground=C["border"],
                      selectforeground=C["fg"],
                      selectmode="extended",
                      relief="flat", bd=2, **kw)
