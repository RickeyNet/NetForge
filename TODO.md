# NetForge TODO

Feature ideas based on the current app structure and product scope.

## High Priority

- [ ] Add configuration validation before render
  Validate IP addresses, subnet masks, VLAN IDs, empty required fields, duplicate interface assignments, overlapping ranges, and roles that reference undefined variables.

- [ ] Add Jinja variable checking and preview helpers
  Show missing variables, unused variables, and a small rendered preview for role templates and custom base sections before the user generates a full config.

- [ ] Add model/profile compatibility checks
  Warn when a site profile assigns interfaces that do not exist on the selected model or stack size.

- [ ] Add batch generation from CSV
  Let users import a CSV of hostnames, management IPs, gateways, passwords, and profile selections to generate many switch configs in one pass.

- [ ] Add per-project settings snapshots
  Save timestamped backups of models, roles, profiles, and base settings so users can roll back bad edits without replacing everything from a ZIP import.

- [ ] Add a saveable generation session
  Save and reload the Step 1 to Step 3 wizard state for a switch that is in progress, including chosen model, profile, assignments, and switch details.

## Workflow Improvements

- [x] Add clone/duplicate actions for models, roles, and profiles
  Most edits will be variants of an existing object. A duplicate action would be faster and safer than creating each item from scratch.

- [ ] Add search and filtering in the editor tabs
  Search boxes for models, roles, and profiles would keep the UI usable once teams build a larger library of templates.

- [ ] Add partial import/export
  Export or import a single model, role, or profile instead of only moving the full settings bundle.

- [ ] Add a config diff view
  Compare the newly generated config against a previously saved config or the current preview so engineers can see exactly what changed.

- [x] Default "write memory" to unchecked on console push
  Leave the "Run 'write memory' when finished" box off by default so the running-config can be verified before it is deliberately saved to startup-config.

- [x] Add a push error summary for switch and FTD pushes
  Track config lines/commands the device rejected or that failed to apply during the console push (switch) and the FTD console push, then show a consolidated error summary at the end instead of leaving failures buried in the transcript. (Switch attributes each '%' error to its line number; FTD console scans for ERROR:/Invalid markers. FDM API push already surfaces errors as exceptions.)

- [x] Add output naming templates
  Support file naming patterns like `{{ hostname }}_{{ profile }}` when saving generated configs or batch output.

- [x] Add quick-copy actions for sections
  Copy only the management VLAN block, only interface configs, or only the base/global sections instead of always copying the full config.

## Data Model Enhancements

- [ ] Add structured role parameters
  Let a role define its own expected fields, defaults, and descriptions so the UI can prompt for role-specific inputs instead of relying only on freeform profile variables.

- [ ] Add model capability flags
  Track details like OOB port support, stack support, uplink types, and Layer 3 capability explicitly instead of inferring behavior only from interface names.

- [ ] Add interface tags or groups
  Support logical groups like `user-access`, `uplink`, `ap-ports`, or `camera-ports` so profiles can target groups instead of repeating raw interface ranges.

- [ ] Add profile inheritance
  Allow a site profile to extend a base profile and override only a few VLANs, variables, or port assignments.

- [x] Add multiple BGP advertising options
  Support more ways to advertise routes in the BGP config: per-instance network statements, redistribution, and aggregate-address / summarization (summary-only). Entered in the profile BGP block and rendered into the `router bgp` stanza. (Per-address-family advertisements not yet covered.)


## Quality Of Life

- [ ] Add inline validation feedback in the UI
  Highlight invalid fields directly in the form instead of showing only message boxes after the user clicks save or generate.

- [ ] Add a dry-run summary panel
  Show a short summary before render: selected model, stack size, number of assigned ports, management VLAN, unresolved variables, and disabled-port coverage.

- [x] Add recent files and recent profiles
  Keep a short history of recently opened settings ZIPs, recently used profiles, and recently generated configs.

- [x] Add keyboard shortcuts
  Shortcuts for generate, copy, save, next/back step, and quick navigation between tabs would speed up daily use.

- [x] Add dark/light theme polish and custom themes
  A simple theme editor or JSON-driven theme import would let teams standardize the UI without changing code.

## Longer-Term Ideas

- [ ] Add multi-vendor support behind a renderer abstraction
  Keep the current Cisco flow, but make room for separate renderers or template packs for other platforms later.

- [ ] Add syntax/test rules for generated configs
  Implement a lightweight rules engine that can flag likely IOS mistakes such as switchport commands on routed interfaces or missing dependencies between features.

- [x] Add template packs and starter libraries
  Ship optional starter bundles for common campus, branch, and private VLAN use cases so first-time users can get productive faster.

- [ ] Add printable/exportable documentation for a profile
  Generate a human-readable profile summary showing VLANs, variables, interface roles, and custom sections for change review or peer approval.

## Suggested First Slice

- [ ] Build validation and compatibility warnings first
  This is the highest-leverage improvement because it reduces bad configs without changing the basic workflow.

- [ ] Add duplicate actions next
  This is a small implementation with immediate day-to-day value.

- [ ] Add batch generation after that
  This turns the tool from a single-switch helper into a stronger operational workflow tool.

## Code Refactoring: Break `NetForge.py` into Modules

The current `NetForge.py` is a single ~7,300-line file. It is well-organized internally (clear section dividers, consistent helper naming), but its size is the bottleneck for code review, testing, and onboarding. The goal of this refactor is to split the file into a `netforge/` package without changing behavior, user-visible data, or the PyInstaller build output.

### Target Layout

`NetForge.py` becomes a thin entry point (`from netforge.app import main; main()`). Everything else moves into a package:

```
netforge/
  __init__.py
  app.py                             # App class, _set_windows_app_id, main
  data/
    storage.py                       # load_json, save_json, DATA_DIR
    base_settings.py                 # load_base_settings, resolve_base, _migrate_base_set
    iface.py                         # expand_port_groups_for_stack, expand_range_iface
  render/
    __init__.py                      # re-exports render_config, render_config_sections
    sections.py                      # _render_ntp_block, _ntp_commands_for_edit, _render_acl, _render_bgp
    normalize.py                     # _normalize_l3_sections
    render.py                        # render_config_sections, render_config (orchestrators)
  ui/
    win_theme.py                     # _merge_bundled_data, DWM styling
    theme.py                         # _load_theme, _save_theme, apply_theme
    theme_editor.py                  # _ThemeEditorDialog
    widgets.py                       # PanedWindow, ScrollFrame, _CheckList, _attach_context_menu, _dark_listbox
    helpers.py                       # _section, _field, _textarea, _autosize_textarea, _scrolled_text, _combo, _copy_name, _toggle_hidden_batch, _dialog, _ask
    filename_template.py             # _apply_filename_template
  serial_push.py                     # _SerialPushDialog
  tabs/
    generate.py                      # GenerateTab (~1280 lines - still big but isolated)
    models.py                        # ModelsTab
    roles.py                         # RolesTab
    profiles.py                      # ProfilesTab (~1250 lines - still big but isolated)
    base.py                          # BaseTab
    guide.py                         # GuideTab
```

### Phasing (safest-first, one commit per module move)

- [ ] **Phase 1 - Pure leaves (no UI coupling).**
  Extract `data/storage.py`, `data/base_settings.py`, `data/iface.py`, `ui/filename_template.py`. These import nothing from the rest of the codebase, so they are risk-free. Add a tiny `tests/` directory with unit tests against the data + filename-template helpers before moving on - this is the safety net for everything else.

- [ ] **Phase 2 - UI primitives.**
  Extract `ui/win_theme.py`, `ui/theme.py`, `ui/widgets.py`, `ui/helpers.py`. Still no dependency on tabs or render. Verify dark-mode and DWM titlebar styling still work on Win 11.

- [ ] **Phase 3 - Renderer package.**
  Extract `render/sections.py`, `render/normalize.py`, `render/render.py`. The renderer is mostly pure (input dict -> output string), so add snapshot tests against a known-good config output *before* moving the code. These tests will catch the most likely regression class (subtly different config output).

- [ ] **Phase 4 - Dialogs.**
  Extract `serial_push.py` and `ui/theme_editor.py`. Depend only on UI primitives. Smoke-test the console-push dialog against a real switch (or a serial loopback) since pyserial behavior cannot easily be unit-tested.

- [ ] **Phase 5 - Tabs, one at a time, smallest first.**
  Order: `guide.py` -> `models.py` -> `roles.py` -> `base.py` -> `generate.py` -> `profiles.py`. Each tab move is its own commit; if the app breaks, the bisect points at exactly one tab. The two mega-tabs (`generate.py`, `profiles.py`) go last because they are the most likely to surface cross-tab coupling issues.

- [ ] **Phase 6 - App shell + entry point.**
  Move `App`, `_set_windows_app_id`, and `main` into `netforge/app.py`. Reduce `NetForge.py` to a ~10-line shim. Update `NetForge.spec` if needed so PyInstaller still picks up the new package.

### Tricky Bits

- **Underscore-prefixed module-level helpers.** Most top-level helpers start with `_` (file-private). When they cross module boundaries the underscore is technically misleading, but renaming all of them adds churn and review noise. Pragmatic call: leave the underscores - they still work across modules and signal "internal API" to future readers.
- **Circular-import risk between tabs and `App`.** Tabs likely take an `app` reference for cross-tab state. Keep the import direction one-way: `app.py` imports tabs; tabs import only from `data/`, `render/`, `ui/`, `serial_push.py`. If a tab needs the `App`, accept it as a constructor argument - do not `from netforge.app import App` inside a tab.
- **`DATA_DIR` resolution & PyInstaller `_merge_bundled_data`.** Some helpers inspect `sys._MEIPASS` / `__file__`. Confirm these still resolve correctly when called from a subpackage - the PyInstaller `.spec` may need `hiddenimports`, `pathex`, or `datas` updates so the bundled `data/` and `template_packs/` directories continue to ship.
- **The two mega-tab classes stay intact for now.** Splitting `GenerateTab` (~1,280 lines) and `ProfilesTab` (~1,250 lines) by file does not fix their internal complexity, but bundling that work into this refactor turns it into an un-reviewable diff. Schedule "Decompose GenerateTab into wizard steps" and "Decompose ProfilesTab into sub-editors" as separate follow-up tasks once the file split is merged.
- **One commit per module move, no behavior changes mixed in.** Each commit should be "Extract X" with the diff dominated by `mv`-style moves. Resist the urge to combine an extraction with a refactor in the same commit - it kills reviewability and bisectability.

### Explicitly Out of Scope for This Refactor

- No DI framework, plugin system, or vendor-renderer abstraction. The multi-vendor item is already on the longer-term list and should be designed once the file is split, not bundled into the split itself.
- No JSON-to-config-object layer. That is a real improvement worth doing later, but bundling it here hides the diff.
- No user-visible renames - file names in `data/`, theme keys, JSON schema, and exported ZIP contents stay identical. Existing users should not notice the upgrade.

### Follow-ups (after the file split lands)

- [ ] Decompose `GenerateTab` into per-step submodules (Step 1 / Step 2 / Step 3 / Preview).
- [ ] Decompose `ProfilesTab` into sub-editors (VLANs, SVIs, OSPF, Custom Sections, Role Variables).
- [ ] Add a config-object layer between the JSON files and the renderer so per-field validation can live with the data model instead of the UI.