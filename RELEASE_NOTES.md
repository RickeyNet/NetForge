# NetForge v1.5.3 - Release Notes

A small UI-clarity release: clearer tab names, a tidier layout, and an up-to-date How-To Guide.

## Renamed and Reordered Tabs

- **"Generate Config" is now "Generator"** and **"FTD Setup" is now "Provisioner"** - shorter names that read better across the tab bar.
- **The Provisioner now sits second**, right after the Generator, so the two day-to-day workflows are side by side. The keyboard shortcuts follow the new order (Ctrl+1 = Generator, Ctrl+2 = Provisioner, then the setup tabs).

## At-a-Glance Descriptions

Both primary tabs now open with a short description of what they do:

- **Generator** - summarizes the model -> profile -> config wizard and what it produces.
- **Provisioner** - explains that it stages Cisco FTD firewalls over the console cable and the FDM/FMC REST APIs, from factory-default to site-ready.

## How-To Guide Refresh

- Updated the stale tab numbers and "Generate Config" references throughout to match the new names and order.
- Added a new **Provisioner - FTD Firewall Setup** section (the tab was previously undocumented), covering the shared connection/profiles bar, the pre-stage console and FDM steps, and the pre-ship FMC registration and config capture.

---

# NetForge v1.5.2 - Release Notes

A reliability and safety release: catch bad input before it reaches a device, see what the device rejected, recover from a known FTD upgrade failure, and more ways to advertise BGP routes. Plus a test/CI foundation under the hood.

## Validate Before You Generate

Generate Config now checks the switch details before rendering, so a typo is caught at the desk instead of on the wire:

- **Errors block generation** - malformed IPv4 addresses, non-contiguous subnet masks, out-of-range VLAN IDs (across management, OOB, SVIs, routed interfaces, static routes, and BGP), and an interface assigned to more than one role.
- **Warnings let you proceed** - a role that references a `{{ variable }}` the profile never sets, a profile variable defined but never used (catches typos from both sides), and an assigned port that doesn't exist on the selected model or stack size (abbreviations like `Gi` are matched correctly).

The **FTD Setup** dialog reuses the same checks: management/FMC/interface addresses are validated before a run, and a soft check on Save Profile flags bad-looking addresses while still letting you save a partial profile.

## Push Error Summary

After a console push, NetForge now surfaces what the device complained about instead of leaving it buried in the transcript:

- **Switch push** - scans each line's reply for `% ...` errors and lists them by line number and command at the end, with the count in the status bar.
- **FTD console** - watches for `ERROR:` / `Invalid input` markers during setup and pre-ship and summarizes them when finished.

## FTD: Regenerate an Expired Certificate

A new **Regenerate Certificate** action on the FTD console tab fixes the Cisco upgrade failure (bug CSCwd11825) where an expired internal HTTPS/web-server certificate aborts the FDM software upgrade. It regenerates the keyring (`fdm`, `default`, or both) over the console - which takes effect immediately, needs no deployment, and sidesteps the cert-deploy loop that the FDM web GUI gets stuck in.

## More BGP Advertising Options

Each BGP instance in a Site Profile now has an **Advertising** section: multiple `network` statements, `redistribute` sources (connected / static / ospf 1 / ...), and `aggregate-address` summarization (with `summary-only`). Existing profiles are untouched - the new fields only render when filled.

## Template Previews

The **Interface Roles** tab and each **Base Settings** custom config section now have a live **Preview** pane that renders the template through the real engine, filling `{{ description }}` (and `{{ ip }}`/`{{ mask }}` when applicable) with sample values and showing other variables as `<name>` placeholders - so you can see where Site Profile values land before generating.

## Console Push Polish

- **`no logging console` is emitted up front** - the generated config now silences console logging right after `configure terminal`, before the rest of the config runs, so a serial console push isn't flooded by the device's own log messages. (It's de-duplicated from the base Logging section.)
- **"Run 'write memory'" is now off by default** so the running-config can be reviewed before it's saved to startup-config.
- **Show-output capture is more reliable** - it pages through `--More--`, re-asserts `terminal length 0`, and uses an idle timeout so a long `show running-config` is never truncated.
- **The dialog now says when the COM port is released** ("safe to open the switch console now"), since opening PuTTY while NetForge still holds the cable looks like a dead, black screen.

## Under the Hood

- Added a test suite for the FDM REST client and a full-App smoke test, and began splitting the large Profiles tab into sub-editors (BGP first).
- Added Continuous Integration (GitHub Actions): ruff linting, Bandit security scanning, and the pytest suite across Python 3.9 / 3.12 on Linux and Windows.

---

# NetForge v1.5.1 - Release Notes

Point release on top of v1.5.0, focused on the FTD setup workflow.

## Saved Profiles for FTD Setup

The **FTD 1010 Setup** dialog can now save and reload its field values as named profiles, the same way the rest of NetForge persists reusable settings. A new **Profile** bar sits with the COM port and baud settings at the top of the dialog.

- **Save** - type a name and click Save to store every field across all three tabs: management IP, netmask, gateway, hostname, DNS, search domain, passwords, the FDM device IP / username / password / firmware path, and the full pre-ship set (FMC IP, registration key, data interface, IPs, masks, gateway, DNS, DDNS, mgmt0, and the checkboxes). Reusing an existing name asks before overwriting.
- **Load** - pick a profile from the dropdown to populate every field at once.
- **Delete** - removes the selected profile (with a confirmation prompt).

Profiles are stored in `data/ftd_profiles.json` and persist across sessions. The per-device Site Name and S Rack # (used only for the capture filename) are deliberately left out, so loading a profile never clobbers them.

---

# NetForge v1.5.0 - Release Notes

First release to automate a firewall: end-to-end staging of the Cisco FTD 1010 from a new **Tools** menu.

## New Feature: FTD 1010 Setup (Console + FDM)

**Tools -> FTD 1010 Setup (Console + FDM)...** automates both halves of FTD 1010 day-0 staging that were previously done by hand against the console and the FDM web GUI.

### Step 1 - Console Setup (serial)

Drives the interactive first-boot wizard over a USB-to-serial cable using an expect-style rule engine that watches the console and answers each prompt:

- FXOS login (factory default `admin` / `Admin123`) and the forced password change
- `connect ftd`, EULA display and paging (`--More--`), and the YES agreement
- Management network: IPv4 yes / IPv6 no / manual, your management IP, netmask, and gateway
- Hostname, DNS servers, and search domain (blank fields accept the device defaults)
- "Manage the device locally?" -> yes
- Detects a device that is already configured and reports it instead of hanging

Timeouts are sized for real first boots: the appliance can sit silent at "System initialization in progress" for 10-15 minutes before the EULA appears, and the engine waits through it.

A second button, **Erase Configuration...**, runs the recovery flow for the login-loop / "FTD service not installed" failure modes: `connect local-mgmt` -> `erase configuration` -> confirm (paperclip-reset the unit first, then run it). The flow handles the case where the erase has to run twice.

### Step 2 - FDM Setup (network)

Replaces the FDM web GUI steps with REST API calls over the management port - no browser needed. Step 1 pre-fills the device IP and password.

| GUI step | What the dialog does |
|----------|----------------------|
| Skip Device Setup + EULA | `POST devices/default/action/provision` (acceptEULA) |
| Start 90-day evaluation | `POST license/smartagentconnections` (skipped if already licensed) |
| Deploy Now | `POST operational/deploy`, polls until deployed |
| Browse + upload firmware | Streamed multipart upload with MB progress (a ~1 GB image never loads into memory) |
| Run Upgrade | `POST action/upgrade` - the device installs and reboots itself (~45 min) |

The FDM client is stdlib-only, so NetForge gains no new dependencies. FDM's self-signed certificate is accepted (this is for staging a directly attached appliance).

### Safety and polish

- Live transcript with passwords scrubbed, even when a device echoes one back split across serial reads
- **Stop** cancels any operation, including mid-upload and mid-deploy
- Non-ASCII console input (e.g. an accented password) is rejected up front instead of being silently mangled on the wire
- COM ports are listed automatically when the dialog opens

## Shared Serial Plumbing

The COM-port enumeration, serial open parameters, and dialog-centering code used by both the IOS **Push to Switch** dialog and the new FTD dialog now live in one place (`netforge/serial_common.py` and a shared UI helper), so console fixes land in both tools at once. No behavior change to the IOS push.

---

# NetForge v1.4.1 - Release Notes

Point release on top of v1.4.0, focused on the console push workflow.

## Capture Show Output to the Config File After a Push

After a successful console push, the **Push Config to Switch (Console)** dialog can now run `show version`, `show interfaces status`, and `show running-config` and save each command's output to the same file the generated config was saved to. The result is a single as-built reference file holding the pushed config plus the device's post-push state for later verification.

- **New checkbox** - "Capture show version / interfaces status / running-config" (on by default). When off, the push behaves exactly as before.
- **Appends to the config's file** - If the config was saved to a file before pushing, the captured output is appended to that file under delimited per-command headers (command + hostname + timestamp).
- **Fallback when not yet saved** - If the config was never saved, the dialog prompts for a location and writes a complete file (generated config followed by the captured output) so you still get one coherent reference artifact.
- Each capture also appears in the live transcript pane regardless of the file destination.

## Faster Console Push

The push now runs as fast as the switch console echoes, instead of pausing for a fixed serial timeout on every line.

- **Root cause** - Each config line blocked for the full serial read timeout because the reader waited for a 512-byte block that a short prompt echo never filled, so every line cost roughly half a second regardless of the **Line Delay** setting.
- **Fix** - The reader now consumes only the bytes already waiting and returns the instant the switch's prompt comes back, and the serial read timeout was lowered. On the same baud rate this makes a typical push several times faster.
- **Line Delay now works** - The **Line Delay (ms)** field is now a real per-line pause and defaults to **0** (as fast as the switch echoes). Raise it only if a finicky console drops characters.

---

# NetForge v1.4.0 - Release Notes

First public release after v1.3.0. Everything documented below is included in v1.4.0.

## ACL Rule Reordering

Rules inside a named ACL can now be reordered directly in the Site Profile editor. Each rule row has a **↑** and **↓** button to the right of the delete button. Clicking either swaps the rule's values with the adjacent row above or below; clicking at the top or bottom boundary is a no-op. The new order is reflected immediately in the saved profile and in any config generated from it.

## ACL Block Reordering

The ACL blocks themselves (each named access-list) can now also be reordered within the Site Profile editor using **↑** and **↓** buttons in each block's header row. This makes it easy to add new ACLs before existing ones without deleting and recreating them.

## BGP Neighbor Lines Now Generate Without Explicit Slots

Previously, `neighbor` lines were only emitted in the BGP block if the profile's BGP instance had explicit peer slots defined under **Site Profiles -> BGP -> Add Slot**. Profiles that set a **Default Peer ASN** but left the slots table empty produced a `router bgp` block with no neighbor statements, and **Generate Config Step 3** showed "No peer slots defined" with no rows to fill in.

The renderer and Step 3 UI now treat a non-empty **Default Peer ASN** as an implied single slot when no explicit slots exist. Step 3 shows one peer row (Remote ASN pre-filled from the default) where you enter the per-switch Peer IP and Password. The rendered output emits the corresponding `neighbor <ip> remote-as <asn>` and `neighbor <ip> password <pwd>` lines. Profiles with explicit slots are unaffected.

## Step 3 Preview Pane Defaults to 50/50

The adjustable divider between the Step 3 form and the config preview pane now defaults to an even 50/50 split on first load. Previously it opened at 60/40, which left the preview visibly cramped before the user manually adjusted it.

## Routed Interface IPs Now Always Apply

Fixed a bug where the per-switch IP / Mask typed in **Generate Config Step 3 -> Routed Interface IPs** would silently fail to land on the routed interface, producing an `ip address` line with blank values even though the role template had `{{ ip }}` and `{{ mask }}` and `requires_ip` was on. Root cause: the IP rows could be keyed by a stale interface name if Step 2 was edited after the user typed an IP, and any trivial whitespace difference between the Step-2 string and the Step-3 dict key bypassed the renderer's lookup.

- **Re-sync on Generate** - **Generate Config** now refreshes the Routed Interface IPs grid against the current Step-2 port assignments before reading them, so edits made after a Back / Forward through Step 2 don't leave the IP dict keyed by an interface name that no longer exists.
- **Canonicalized lookup** - The renderer now strips and normalizes the `range ` token on both sides of the `routed_iface_ips` lookup, so a leading space or a mixed-case `RANGE Gi1/0/23-24` still resolves to the typed IP.
- **Visible warning on orphans** - If the renderer finishes the Interfaces section with any `routed_iface_ips` entry that was never consumed, a `! WARNING` block listing the orphaned interface / IP / mask is prepended to the Interfaces section. Silent drops become a visible diagnostic.
- **Routed Interface fallback chain for routed-port IP / Mask** - When a port assigned to a `requires_ip` role has a blank IP or Mask in Step 3's Routed Interface IPs grid, the renderer now falls back through: per-switch values typed into Step 3's **Routed Interface** box (`sw.routed_mgmt_ip` / `sw.routed_mgmt_mask`) → the profile's `l3_sections.routed_mgmt` defaults. Lets the user type a site-wide mask on the profile, a per-switch IP into Step 3's Routed Interface box, and have both flow into the role-driven `interface ... / ip address ...` block without retyping into the per-port grid.
- **Dedup when role and Routed Interface name the same port** - If the profile's Routed Interface section names an interface that is also assigned to a `requires_ip` role in Step 2, the standalone L3 Interfaces block for that interface is now suppressed. The port_assignment's role template wins, so extra config it carries (MTU, OSPF, etc.) is preserved without a duplicate `interface` block.

## Default Routed Mask Field Removed

The standalone **Default Routed Mask** field has been removed from the Site Profile editor. The Layer 3 -> **Routed Interface** section's **Mask** field is now the single source for a site-wide routed-port mask: Step 3 pre-fills its Mask column from it, and the renderer falls back to it whenever Step 3 leaves IP or Mask blank.

- **Auto-migration** - Existing profiles with a `default_routed_mask` key still work. On read, `_normalize_l3_sections` promotes the legacy value into `l3_sections.routed_mgmt.mask` when that field is blank. The next save of the profile drops the legacy key. No manual edit required.

## Security Hardening

- **Sandboxed template rendering** - Role and profile command templates now render through Jinja2's `SandboxedEnvironment`. These templates come from user-editable JSON that can be replaced via **Import Settings**, so an unsandboxed environment allowed server-side template injection -> arbitrary code execution on **Generate Config**. The sandbox blocks attribute access to private/dunder names and dangerous builtins while leaving all legitimate `{{ variable }}` substitutions working.
- **Zip Slip / arbitrary write protection on import** - `Import Settings` no longer calls `zipfile.extract()`. Each ZIP member is now read into memory, the destination path is recomputed from `os.path.basename()` against `DATA_DIR`, and a `realpath` containment check rejects any member that would write outside the data directory. Every member is also JSON-validated before being allowed to overwrite a real settings file.
- **Export Settings confirmation** - **Export Settings** now shows an explicit confirmation dialog noting that the ZIP contains credentials (enable secrets, user passwords, SNMP / NTP / BGP keys) in plain text. Helps avoid accidental sharing of a ZIP that contains live secrets.
- **Redacted enable password in push transcript** - The push-to-switch console log replaces the enable password with `********` in the echoed transcript so a non-standard console or terminal-server setup that echoes the password locally cannot leak it into the visible log.
- **Security Notes in README** - Added a Security Notes section to `README.md` covering plaintext credential storage in `data/*.json` and exported ZIPs, the type-0 nature of generated `username ... secret` and `enable secret` lines, and the trust expectation around imported settings ZIPs.

## Base Settings Categories Changed

The named sections on the **Base Settings** tab have been replaced with a slim category set aligned to the Cisco 9300 Layer 3-2 Switch IOS XE Baseline workbook. The new sections (in order) are:

| # | Section | Replaces |
|---|---------|----------|
| 1 | Basic Configuration | *(new)* |
| 2 | Services and Functions Config | Global Services |
| 3 | IP Services | *(new)* |
| 4 | Snooping | *(new)* |
| 5 | HTTP Server | *(new)* |
| 6 | Management VRF | Management VRF |
| 7 | AAA Password Policy / RADIUS / Local Account | AAA Configuration |
| 8 | SSH Config | SSH / Crypto |
| 9 | Logging | Logging |
| 10 | Archive Config | *(new)* |
| 11 | VTY Config | Line Configuration |
| 12 | Miscellaneous Configs | Security + Switching Features |

The earlier draft of this release included additional spreadsheet sections (**Management**, **IP Routes**, **Access Control List**, **VLAN Config**, **Configure NTP**, **Configure SNMPv3**) but these were dropped before release because the same commands are already produced by other parts of the app: VLAN and ACL editors on the Site Profile, NTP on the profile's **Services** block, IP routes from the per-switch Static Routes editor, etc. Keeping them as raw text boxes invited duplicated output. **Banner LOGIN**, **Disabled Port Template**, and **Custom Config Sections** retain their existing behavior.

- **Auto-migration** - Existing base sets are migrated on app launch: `global_services` -> `services_functions`, `aaa` -> `aaa_radius`, `line_config` -> `vty_config`, and `security` + `switching` -> `misc`. Merged keys are joined with a blank line. `ssh`, `logging`, and `mgmt_vrf` keep their names. Legacy / removed-section keys (`mgmt_port`, `management`, `ip_routes`, `acl`, `vlan_config`, `ntp`, `snmpv3`) are dropped on load. The migration runs idempotently and writes back to `base_settings.json` on next save.
- **Dedicated mgmt-port interface block** - The dedicated `interface GigabitEthernet0/0` block (when the model has an OOB port and Step 3 left **OOB IP** blank) now emits a fixed `no ip address / negotiation auto` default instead of pulling from the old `mgmt_port` key.

## Larger Base Settings Text Boxes

The auto-sizing text areas on the **Base Settings** tab now grow up to **40 lines** before scrolling (was 20 for sections, 30 for the banner, 20 for the disabled-port template). Long ACL blocks, SNMPv3 configs, and multi-line banners can now stay fully visible without forcing a scroll. The minimum height (2 lines) and the auto-shrink-on-delete behavior are unchanged.

## Base Settings Search

The Base Settings tab now has a sticky search bar pinned to the top of the right pane. Type a string and hit Enter (or click **Find**) to see whether a command already exists in the currently loaded base set.

- Case-insensitive substring match across every section text area (Global Services, Logging, AAA, Security, SSH, Switching, Line Configuration, Banner LOGIN, Disabled Port Template, etc.), the Filename Template field, and every Custom Config Section's commands box.
- All matches are highlighted in yellow; the first match auto-scrolls into view.
- A status label reports the count and the sections that contained matches, e.g. `5 matches: Global Services (3), Switching Features (1), Custom Section: NTP (1)`.
- **Clear** removes highlights. Highlights also auto-clear when switching to a different base set in the left list.

## NTP Access-Group Support

Site Profiles gain two new optional fields under **DNS / NTP**:
- **NTP Access-Group ACL #** - the numbered ACL bound to NTP peers.
- **NTP Peer IPs** - comma-separated list of peer IPs that should be permitted.

When both are set, the Global section emits `ntp access-group peer <N>` plus a matching `access-list <N> permit host <peer>` line per IP. Persisted on the profile under `services.ntp.access_group_acl` and `services.ntp.access_group_peers`. Existing `ntp source` / `authenticate` / `trusted-key` emission is unchanged.

## ACL Editor Improvements

- **Column headers** - Each ACL block now has `Action | Proto | Source | Source Wildcard | Destination | Dest Wildcard | Log | Del` labels above its rule rows. Headers and rule widgets share a single grid parent so the columns line up exactly.
- **Aligned right edge** - The per-rule delete button now stays in the same horizontal position on remark rows (where the Log checkbox is hidden), thanks to a reserved minsize on the Log column.
- **Wider Proto field** - Bumped from 4 to 6 characters wide so `tcp` / `udp` / `icmp` are easier to read.
- **Protocol dropdown** - The Proto field is now an editable combobox prefilled with the common protocols (`ip, tcp, udp, icmp, gre, esp, ahp, eigrp, ospf, pim, igmp, sctp`). Free-text input is still accepted for protocol numbers or any other keyword.

## Form Layout Polish

- **Label column widened** - The shared `_field` / `_textarea` helpers now reserve a wider label column (26 chars + 6px gap) so longer labels like "NTP Access-Group ACL #" and "User Network (advertised)" no longer crowd or overlap the entry column. Affects every form built via these helpers.
- **Sticky Save on Base Settings** - The Base Settings tab now has the same sticky footer pattern as Site Profiles: **Save Base Settings** stays pinned to the bottom of the right pane regardless of scroll position.
- **Output Settings hint fix** - The filename template hint now lists `work_order` alongside `hostname`, `model`, `profile`, and `date`.

## Auto-Sizing Text Areas

- **Base Settings sections** - Every named section text area (Global Services, Logging, AAA, Security, SSH, Switching, Line Configuration, Banner LOGIN, Disabled Port Template, and Custom Config Section command boxes) now starts compact and grows as you type, shrinking back when content is removed. Heights are clamped to a min of 2 and a max of 20 lines (30 for the banner) so one section can't blow out the form.
- **VLAN Definitions on Site Profiles** - The VLAN list textarea uses the same autosizing helper (min 4 / max 40 lines) and resizes immediately when switching between profiles.

## Site Profile Layout Polish

- **Role Variables stretch** - The Key/Value table on Site Profiles now uses a 2-column grid with equal weights so both columns share the available width and stretch with the window. Long variable names and values are no longer truncated at the previous fixed 18-char entry width.
- **Collapsible BGP and ACL hints** - The multi-line descriptive hints under **BGP Instances** and **Named Extended ACLs** automatically hide when at least one block exists and reappear when the section is emptied, so profiles with populated L3 sections render compact instead of padded.
- **Template pack data merged in** - The `cisco_l2_baseline` and `cisco_l3_baseline` packs are now merged directly into `data/*.json` (2 base sets, 2 profiles, 4 hardened roles). Existing entries with the same names are preserved so user edits always win. `template_packs/` is retained as repo documentation.

## Keyboard Shortcuts

NetForge now responds to keyboard shortcuts from any tab or focused widget:

| Shortcut | Action |
|----------|--------|
| **Ctrl+1..6** | Jump to Generate / Models / Roles / Profiles / Base Settings / How-To Guide |
| **Ctrl+S** | Save the active editor (dispatches to the focused tab's save action) |
| **Ctrl+G** | Switch to the Generate tab and run **Generate Config** |
| **Ctrl+Shift+C** | Copy the generated config to the clipboard |
| **Ctrl+Right / Ctrl+Left** | Wizard navigation on the Generate tab (Next / Back) |
| **F1** | Show the Keyboard Shortcuts help dialog |

- A new **Help** menubutton on the custom menubar exposes the **Keyboard Shortcuts** entry.
- A dim **Press F1 for shortcuts** label is pinned to the right side of the menubar so the F1 hint is discoverable without opening the menu.

## Theme Polish

- **Themed dialog icons** - All Toplevel dialogs (F1 shortcuts, theme editor, push console, info / confirm / warning) now carry the NetForge icon instead of the default Tk feather.
- **Themed title bars (Windows)** - Root and Toplevel title bars are painted via DWM: immersive dark mode on Win10 1809+, plus border / caption / text colors on Win11 22H2+. Restyling re-runs on every theme switch so inactive windows no longer flash a stock white border when focus moves to another app or dialog.
- **Stronger focus ring** - `TCombobox`, `TEntry`, `TButton`, and `Del.TButton` now set `lightcolor` / `darkcolor` (not just `bordercolor`), so the focus highlight is clearly visible on dark themes when tabbing through fields with the keyboard.
- **Themed check / radio buttons** - Hover and active states on `TCheckbutton` and `TRadiobutton` keep the theme background instead of flashing white on mouseover.
- **Themed scrollbars in Step 3 and Push Console** - The generated-config preview and the push-to-switch transcript now use a `tk.Text` + `ttk.Scrollbar` pair (via a small `_scrolled_text` helper) instead of `ScrolledText`'s embedded classic `tk.Scrollbar`, so their scrollbars match the rest of the app.

## Multiple Local Users per Profile

Site Profiles now hold a list of local users instead of a single username / password pair. Each row in the new **Local Users** table on the profile (Username, Password, Privilege, with a + Add User button and X delete) renders as its own `username NAME privilege P secret PW` line in the generated config. Enable Secret stays singular.

- **Step 3 seeding** - Generate Config Step 3 shows the same Local Users table, pre-populated as an editable copy of the profile's users. Edits stay per-switch and don't write back to the profile, so you can rename an account or bump a privilege on a single switch without touching the template.
- **Privilege defaults to 15** - per-user privilege is editable from 0-15. Previously every user was emitted with `privilege 0`.
- **Auto-migration** - profiles using the old `credentials.local_username` / `admin_password` shape are converted to a single-entry users list at app launch and after importing a settings ZIP. The legacy keys are removed and `profiles.json` is rewritten only when something actually changed.
- The renderer keeps a legacy fallback so partly-migrated configs still produce a sane `username` line.

## Per-Switch VLAN Overrides

Site Profiles gain a new **Allow per-switch VLAN overrides in Step 3** checkbox under the VLAN Definitions block. When on, Generate Config Step 3 grows a **VLAN Definitions (this switch)** editor pre-filled with the profile's VLAN block.

- The text from Step 3 replaces the profile's VLAN definitions for that one switch at render time; an empty box falls back to the profile.
- Useful for sites that mostly share a VLAN plan but tweak one or two VLANs (different printer / camera / guest IDs, extra site-specific VLANs, etc.) without forking the profile.
- The editor uses the same auto-sizing text area as the profile's VLAN block.

## Performance

- **Non-opaque pane dividers** - Dragging the middle divider between the form and preview panes (Step 3, Switch Models, Interface Roles, Site Profiles, Base Settings) no longer resizes the panes live. A thin guide line tracks the cursor and the panes resize once on release, eliminating the per-pixel layout cascade through every nested form widget. This was the largest source of UI lag on Windows.
- **Throttled scroll-region updates** - Scrollable form areas now coalesce their `scrollregion` recomputes through a cancelable 60ms timer, so a continuous window resize or panel drag collapses to a single bounding-box walk after motion stops instead of one per frame.
- **No more global mousewheel rebinds** - Replaced the per-Enter `bind_all`/`unbind_all` mousewheel binding pattern with per-descendant binds walked once on first entry. Scrolling no longer thrashes wheel bindings across the whole app whenever the cursor passes over a panel boundary.
- **Cheaper redundant Configure events** - The scrollable canvas now skips re-applying its width when the value hasn't actually changed, cutting unnecessary work during nested layout passes.

---

## New Feature: Push Config to Switch (Console)

Step 3 of the Generate Config tab now has a **Push to Switch...** button that streams the generated config straight to a switch over its console port via a USB-to-serial adapter. No more copy/paste into PuTTY.

### How it works
- Pick the COM port (auto-detected from `pyserial`'s `list_ports`), baud rate (9600 default), and optional enable password.
- The dialog answers the day-0 setup-dialog prompt automatically (`Would you like to enter the initial configuration dialog?` -> no).
- Enters enable mode (handles the password prompt if you supplied one).
- Quiets the session with `terminal length 0` / `terminal width 511`.
- Sends the generated config **line by line**, waiting for the switch prompt between lines so a slow console doesn't drop characters. Falls back to a configurable inter-line delay if no echo arrives.
- Optional **Run 'write memory' when finished** checkbox saves to startup-config at the end.

### Transcript pane
- Everything the switch sends back is shown in a live scrollable transcript, so you can watch the push happen and spot errors immediately.
- Stop button halts the push mid-flight (the dialog warns if you try to close while one is still running).

### Requirements
- The `pyserial` package is now in `requirements.txt`. Install with `pip install -r requirements.txt` or `pip install pyserial`.
- If pyserial isn't installed, the button shows a friendly install-instructions dialog instead of crashing.

## Major Feature: Layer 3 Support

NetForge now generates full Layer 3 configurations alongside the existing Layer 2 workflows. Site Profiles gain a new **Enable Layer 3** toggle that unlocks an L3 editor and tells the generator to emit routing-related blocks.

### L3 Interface Sections
- Layer 3 profiles use three independently enabled sections instead of a single management-style dropdown:
  - **Loopbacks** - one or more loopback interfaces (Loopback0, Loopback1, …) with per-switch IP/mask in Step 3
  - **Routed Interface** - standalone routed ports defined on the profile; site-wide mask defaults pre-fill Step 3
  - **Management VLAN** - one or more mgmt SVIs with per-switch IP/mask in Step 3
- `ip default-gateway` is always emitted when a Default Gateway is set, regardless of which sections are enabled.

### Routed Interfaces (Requires IP)
- Interface Roles now have a **Requires IP** checkbox - tick it for roles that turn an interface into an L3 routed port (no switchport).
- When a port is assigned to a Requires-IP role, the wizard's Step 3 grows an extra grid for per-switch IP/mask entry.
- Use `{{ ip }}` and `{{ mask }}` as placeholders in the role template.
- The Site Profile's **Routed Interface** section **Mask** field pre-fills the Mask column of every routed-interface row in Step 3 (useful for sites with uniform /30 point-to-points).

### SVIs
- Define VLANs that need an SVI on every switch at the site, with description and optional DHCP helper addresses.
- IPs and masks are entered per-switch in Generate Config Step 3 under **SVI IPs**.
- DHCP helpers render as `ip helper-address ...` lines.

### OSPF
- Per-profile OSPF block: process ID, passive-interface default toggle, passive interface list, and one or more `network ... area ...` statements.
- Router-ID is set per switch in Step 3 and defaults to the first loopback IP.

### BGP
- One or more BGP instances per profile, each rendering its own `router bgp <local_asn>` block.
- Each instance defines **Peer Slots** (remote ASN + description) that describe BGP neighbours present on every switch at the site.
- Per-switch values (neighbour IP, MD5 key, circuit ID) are filled in during Generate Config Step 3.

### Named Extended ACLs
- Profile-level structured ACL editor produces `ip access-list extended <name>` blocks.
- Each rule is either a remark (free-form comment) or a permit/deny with protocol, source + wildcard, destination + wildcard, and optional `log`.
- ACLs render in the post-interface section of the generated config.

### Static Routes + Auto Default Route
- Per-switch static routes are entered in Step 3 (prefix, mask, next-hop, optional description).
- When a Layer 3 device has a Default Gateway set and no user-supplied 0.0.0.0/0 entry, NetForge auto-emits `ip route 0.0.0.0 0.0.0.0 <gateway>`.

## New Feature: Multiple Base Settings Sets

- The Base Settings tab now supports multiple named sets, managed from a side-by-side list panel.
- Buttons: **+ Add**, **Duplicate**, **Set Default**, **Delete**.
- Each Site Profile picks one set via a **Base Settings** dropdown. If the named set is missing at generate time, the app falls back to the entry marked as default.
- Lets you keep different AAA / SSH / banner blocks per deployment type (corporate / lab / DMZ) and select the right one per profile.

## New Feature: Profile-Level Services (DNS, NTP, Clock)

Per-profile values render directly as IOS commands so different sites can point at different infrastructure without duplicating Base sets:

- **DNS Servers** - comma-separated name-server IPs, becomes `ip name-server ...` lines
- **NTP Servers** - comma-separated NTP server IPs, becomes `ntp server ...` lines
- **NTP Source Interface** - optional `ntp source <iface>`
- **NTP Auth Key ID + Key** - optional MD5 authenticated NTP
- **Clock Timezone** - free-form `clock timezone ...` value (e.g. `EST -5`)
- **Clock Summer-Time** - free-form `clock summer-time ...` value (e.g. `EDT recurring`)

## New Feature: Profile Credential Defaults

- Each Site Profile can carry optional defaults for **Local Username**, **Local User Password**, and **Enable Secret**.
- Selecting a profile pre-fills the matching fields in Generate Config Step 3.
- The wizard always lets you override per switch; per-switch edits are not written back to the profile.
- The renderer prefers per-switch `local_username` over the Base set's default.

## New Feature: Local Username Field in Step 3

- Step 3 (Switch Details) gains a **Local Username** field alongside Enable Secret / Admin Password so the active user is visible and editable per switch.

## New Theme: Voyager

- Deep navy-blue background with warm orange accents - inspired by a starry-sky aesthetic.

## Theme Refinement: Sandstone

- Sandstone has been darkened and rebalanced for a more cohesive look:
  - Deeper olive-drab background with progressively darker panels and inputs (proper recessed hierarchy)
  - Warm cream foreground with muted khaki hints
  - Warm terracotta orange accent (replaces the previous maroon/dusty rose)
  - Darker borders for crisp panel definition

## UI Improvements

- **Sticky Save Profile button** - the Save Profile button on the Site Profiles tab is now pinned as a footer so it stays visible as the Layer 3 body grows.
- **Header / row alignment** - column headers in BGP Peer Slots, SVIs, and OSPF Networks now line up with their entry rows; "+ Add" buttons moved to the section hint row so they no longer disrupt the column grid.
- **Section hint text** - relocated long format hints from field-label parentheticals into section hints so labels like Clock Timezone, Clock Summer-Time, and NTP Auth Key are no longer truncated.
- **Em-dash cleanup** - replaced all em-dash characters with hyphens across docs and source for consistent typography in environments without Unicode rendering.

## Bug Fixes

- **Default gateway on Layer 3 devices** - `ip default-gateway` is now emitted whenever a value is set, regardless of which L3 interface sections are enabled (previously gated to L2-only in some cases).
- **Routed Uplink template** - fixed a mismatched-brace typo in the bundled Routed Uplink role so per-switch `{{ ip }}` / `{{ mask }}` substitutions actually land in the config.
- **Role-template errors surface** - if a role template fails to render, the interface block now contains an `! ERROR rendering role '<name>': <exc>` comment instead of silently emitting the unrendered template.

---

# NetForge v1.3.0 - Release Notes

## New Feature: Work Order Number Field

- Step 3 (Switch Details) now includes a **Work Order #** field
- When filled in, the work order number appears as a comment in the generated config header: `! Work Order: <number>`
- `{{ work_order }}` is now a supported variable in the output filename template (Base Settings -> Filename Template)
  - Example: `{{ hostname }}_{{ work_order }}` produces `SW-CORE-01_WO-12345.txt`

## New Feature: Output Filename Templates

- Generated config filenames are now driven by a customizable **Filename Template** in Base Settings
- Supported variables: `{{ hostname }}`, `{{ model }}`, `{{ profile }}`, `{{ date }}`, `{{ work_order }}`
- Default template: `{{ hostname }}_{{ profile }}_{{ model }}_{{ work_order }}`
- Invalid filename characters are automatically stripped from the result

## New Feature: Quick-Copy Section Toolbar

- The config preview pane now has a **Copy section** toolbar with one button per named config section
- Sections: **Global / Base**, **VLANs**, **Interfaces**, **Management**, **Line Config**, **Banner / End**
- Buttons are enabled only after a config is generated and disabled when the section is empty
- Clicking a section button copies only that block to the clipboard

## New Feature: Recent Files Menu

- The **File** menu now contains three **Recent** sub-menus: **Recent Profiles**, **Recent Settings ZIPs**, and **Recent Configs**
- Recently used profiles are remembered and can be selected directly from the menu to jump straight to the Generate tab
- Recently imported settings ZIPs can be re-imported from the menu
- Recently saved configs can be re-opened into the config preview pane
- Up to 10 recent items are tracked per category and persisted across sessions

## New Feature: Duplicate Action for Models, Roles, and Profiles

- Models, Roles, and Profiles tabs now each have a **Duplicate** button
- Duplicating an item creates a copy with a unique name (e.g., `My Profile (copy)`)
- The duplicate is immediately selected and ready to edit

## New Feature: Checkbox Multi-Select Delete

- The item lists in Models, Roles, and Profiles tabs now use a checkbox-based list (`_CheckList`)
- Check multiple items and click **Delete** to remove them all at once
- Single-item delete still works by selecting (clicking) an item without checking it

## New Feature: Select All Button

- Models, Roles, and Profiles tabs now each have a **Select All** button
- Clicking it checks all checkboxes at once; clicking again unchecks all (toggle behavior)
- Works together with the multi-select Delete to quickly remove an entire list

## New Feature: Custom Theme Editor

- A new **Edit Custom Themes…** option is available at the bottom of the **Theme** menu
- The editor lets you create, duplicate, and delete custom color themes without touching any code
- Each of the 12 palette colors has a labeled text field and a clickable swatch that opens the system color picker - swatches update live as you type hex values
- **Preview** applies your colors to the running app immediately without saving
- **Save Theme** persists the theme to `theme.json`; it appears instantly as a new entry in the Theme menu under a separator below the built-in themes
- Custom themes survive restarts and are included in settings export/import ZIP files

## New Feature: Light Theme

- A new built-in **Light** theme is now available in the Theme menu
- Off-white background with blue accent, suitable as a clean light-mode alternative to the existing dark themes

## UI Improvements

- **Read-only config preview** - the config preview pane is now read-only; it can no longer be accidentally edited
- **Themed dialogs** - all info, warning, and error message boxes replaced with fully themed custom dialogs that match the active theme
- **Config preview cleared on back** - navigating back from Step 3 to Step 2 now clears the preview pane and disables the section copy buttons
- **Responsive section copy toolbar** - the Copy section buttons now shrink and grow with the window instead of overflowing off-screen at smaller widths

---

# NetForge v1.2.2 - Release Notes

## Fix: OOB Management Port (GigabitEthernet0/0) on C9300

- The disabled port template (which contains `switchport` commands) is no longer applied to the OOB management port - GigabitEthernet0/0 is a routed interface that does not accept switchport commands
- The `mgmt_port` base setting now renders with the correct `interface GigabitEthernet0/0` header

## New Feature: OOB Management Port IP Assignment

- Step 3 (Switch Details) now shows optional **OOB IP Address** and **OOB Subnet Mask** fields when the selected model has a GigabitEthernet0/0 port
- If both fields are filled in, GigabitEthernet0/0 is configured with the specified IP address
- If left blank, the default `mgmt_port` base setting is used as a fallback
- If a role is assigned to GigabitEthernet0/0 in the Step 2 port assignment table, that role's commands take priority over both the OOB fields and the base setting

## Model Update: C9300 Port Groups

- Added `GigabitEthernet1/1/1-4` port group to all C9300 switch models

---

# NetForge v1.2.0 - Release Notes

## Bug Fix: Management Port on C9200 Models

- The `mgmt_port` base setting (GigabitEthernet0/0 config) was being included in every generated config, even for switch models that don't have that interface
- Config generation now checks the selected model's port groups and only includes the management port block when a GigabitEthernet0/ interface exists (e.g., C9300 models)
- C9200 models no longer generate invalid GigabitEthernet0/0 config lines

## New Feature: Right-Click Context Menu

- All text fields, text areas, and the config preview now support a right-click context menu
- Menu includes **Cut**, **Copy**, **Paste**, and **Select All** with keyboard shortcut hints
- Read-only widgets (config preview, guide code blocks) show only Copy and Select All
- Menu items are contextually enabled/disabled based on selection and clipboard state
- Styled to match the active theme

## New Theme: Sandstone

- Added a warm, light-mode theme with olive/sage backgrounds, cream input fields, and dusty rose accents

| Theme         | Description                                                         |
|---------------|---------------------------------------------------------------------|
| **Sandstone** | Warm olive-sage background with cream inputs and dusty rose accents |

## UI Improvements

- **Themed combo dropdowns** - combobox dropdown lists now match the active theme instead of showing a white system default
- **Themed menu bar** - replaced the native Windows menu bar with a custom frame-based menu bar that fully respects theme colors
- **Guide headings** - heading text in the How-To Guide now uses the theme accent color instead of hardcoded white, improving readability on light themes

## Wizard: Back Button Clears Preview

- Pressing the Back button on Step 3 (Switch Details) now clears the generated config preview
- All input fields (hostname, IP, passwords, etc.) are preserved when navigating back

---

# NetForge v1.1.0 - Release Notes

## New Feature: Theme Selector

- Added a **Theme** menu in the menu bar for switching between colour themes
- Themes apply instantly - all tabs, menus, and widgets update in place
- Selected theme is saved to `data/theme.json` and persists across sessions
- Theme preference is included in Settings Export/Import

### Included Themes

| Theme | Description |
|-------|-------------|
| **Default** | The original grey/black dark mode palette |
| **Coral** | A deep ocean-teal background with warm coral accents |

---

# NetForge v1.0.1 - Release Notes

## New Feature: Custom Config Sections in Base Settings

- Add your own IOS config sections (SNMP, NTP, QoS, DHCP Snooping, ACLs, etc.) directly in Base Settings
- Each custom section includes a name, position control (before or after interfaces), and a raw IOS command block
- Sections are included in every generated config
- Supports Jinja2 `{{ variable }}` placeholders - values are pulled from the Site Profile's Role Variables
- Add as many sections as needed using the "+ Add Section" button

---

# NetForge v1.0.0 - Release Notes

## Overview
NetForge is a standalone Windows desktop application for generating initial configurations for Cisco switches. It provides a dark-themed GUI wizard where network engineers define switch models, interface roles, site profiles, and base IOS settings as reusable presets - then generate complete, ready-to-paste configurations in seconds.

## Features

### Configuration Generator (3-Step Wizard)
- Select a switch model and site profile
- Review and customize port assignments per switch
- Enter per-switch details (hostname, credentials, IPs)
- Generate, copy to clipboard, or save config to file

### Switch Models
- Define any Cisco switch model with its port groups (prefix, start, end)
- Stack support - automatically replicates port groups across stack members (up to 4)
- Provision type for `switch X provision` commands

### Interface Roles
- Create reusable port configuration templates (access, trunk, private VLAN, etc.)
- Jinja2 variable support (`{{ description }}`, `{{ access_vlan }}`, etc.)

### Site Profiles
- Define VLAN configurations, role variables, and default port assignments per site
- Variables feed into role templates for site-specific values (VLAN IDs, allowed VLANs, etc.)

### Base Settings
- Global IOS command sections: services, VRF, logging, AAA, security, SSH/crypto, STP, line config, banner
- Disabled port template with variable support for security baseline
- Configurable port display mode (range vs. individual)

### Built-in How-To Guide
- Step-by-step setup instructions with IOS command examples embedded in the app

## Technical Details
- **Platform:** Windows (standalone .exe via PyInstaller)
- **Dependencies:** Python, Tkinter, Jinja2
- **Data storage:** Local JSON files in `data/` directory
- **Fully offline** - no network connections, no telemetry, no external services
- **Dark mode UI** with Segoe UI / Consolas fonts

## Pre-loaded Data
- 7 switch models (C9200CX, C9200L, C9300 with 1-4 stack variants)
- 5 interface roles (Private VLAN Promiscuous/Isolated, Trunk to Switch/Firewall, Access Port)
- Sample base settings with AAA, SSH, STP, and security defaults
