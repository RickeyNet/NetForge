"""How-To Guide tab."""

import tkinter as tk
from tkinter import ttk

from netforge.ui.helpers import _attach_context_menu
from netforge.ui.theme import C
from netforge.ui.widgets import ScrollFrame

class GuideTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._guide_sections = []
        self._build()

    def _clear_guide_search(self):
        self._guide_search.delete(0, "end")
        self._apply_guide_search()

    def _on_guide_search(self, _event=None):
        self._apply_guide_search()

    def _apply_guide_search(self):
        q = self._guide_search.get().strip().lower()
        terms = [t for t in q.split() if t]
        visible = 0
        first_visible = None
        for sec in self._guide_sections:
            haystacks = [t.lower() for _, t in sec["texts"]]
            if not terms:
                match = True
            else:
                match = all(
                    any(term in text for text in haystacks)
                    for term in terms
                )
            if match:
                if not sec["frame"].winfo_ismapped():
                    sec["frame"].pack(fill="x")
                visible += 1
                if first_visible is None:
                    first_visible = sec["frame"]
            else:
                sec["frame"].pack_forget()
        if terms:
            word = "section" if visible == 1 else "sections"
            self._guide_match_lbl.configure(text=f"{visible} {word}")
        else:
            self._guide_match_lbl.configure(text="")
        self._guide_scroll.sync_scrollregion()
        if first_visible and terms:
            self.after_idle(lambda w=first_visible: self._scroll_guide_to(w))

    def _scroll_guide_to(self, widget):
        canvas = self._guide_scroll.canvas
        try:
            canvas.update_idletasks()
            y = widget.winfo_y()
            total = max(1, self._guide_scroll.inner.winfo_reqheight())
            canvas.yview_moveto(max(0.0, min(1.0, (y - 12) / total)))
        except tk.TclError:
            pass

    def _build(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(toolbar, text="Search:").pack(side="left")
        self._guide_search = ttk.Entry(toolbar)
        self._guide_search.pack(side="left", fill="x", expand=True, padx=(6, 4))
        _attach_context_menu(self._guide_search)
        self._guide_search.bind("<KeyRelease>", self._on_guide_search)
        self._guide_search.bind("<Return>", self._on_guide_search)
        self._guide_search.bind("<Escape>", lambda _e: self._clear_guide_search())
        self._guide_match_lbl = ttk.Label(toolbar, text="", style="Hint.TLabel")
        self._guide_match_lbl.pack(side="left", padx=(0, 4))
        ttk.Button(toolbar, text="Clear",
                   command=self._clear_guide_search).pack(side="left")

        self._guide_scroll = ScrollFrame(self)
        self._guide_scroll.pack(fill="both", expand=True)
        f = self._guide_scroll.inner

        self._guide_sections = []
        current_section = [None]

        def _register(widget, text):
            if current_section[0] is not None:
                current_section[0]["texts"].append((widget, text))

        def _start_section():
            sec = {"frame": ttk.Frame(f), "texts": []}
            sec["frame"].pack(fill="x")
            self._guide_sections.append(sec)
            current_section[0] = sec
            return sec

        def heading(text):
            sec = _start_section()
            lbl = ttk.Label(sec["frame"], text=text, font=("Segoe UI", 13, "bold"),
                            foreground=C["accent"], background=C["bg"])
            lbl.pack(anchor="w", padx=12, pady=(18, 2))
            _register(lbl, text)
            ttk.Separator(sec["frame"]).pack(fill="x", padx=12)

        def subheading(text):
            if current_section[0] is None:
                _start_section()
            lbl = ttk.Label(current_section[0]["frame"], text=text,
                            font=("Segoe UI", 10, "bold"),
                            foreground=C["accent"], background=C["bg"])
            lbl.pack(anchor="w", padx=16, pady=(12, 2))
            _register(lbl, text)

        def body(text):
            if current_section[0] is None:
                _start_section()
            lbl = ttk.Label(current_section[0]["frame"], text=text, wraplength=750,
                            justify="left", foreground=C["fg"], background=C["bg"],
                            font=("Segoe UI", 9))
            lbl.pack(anchor="w", padx=20, pady=(2, 2))
            _register(lbl, text)

        def code(text):
            if current_section[0] is None:
                _start_section()
            box = tk.Text(current_section[0]["frame"], height=text.count("\n") + 1,
                          font=("Consolas", 9), wrap="none",
                          bg=C["bg_input"], fg=C["green"],
                          relief="flat", bd=4, padx=6, pady=4)
            box.insert("1.0", text)
            box.configure(state="disabled")
            box.pack(anchor="w", padx=24, pady=(2, 4), fill="x")
            _attach_context_menu(box)
            _register(box, text)

        # ---- Overview ----
        heading("How To Use This App")
        body(
            "This app generates ready-to-paste initial configurations for "
            "Cisco switches and routers (Layer 2 access, Layer 3 distribution, "
            "and L3 edge/BGP). There are two phases:\n\n"
            "ONE-TIME SETUP  (tabs 2-5)\n"
            "Define your switch models, interface roles, site profiles, and "
            "base settings. This only needs to be done once - after that the "
            "definitions are saved and reused.\n\n"
            "DAILY USE  (tab 1 - Generate Config)\n"
            "Pick a model, pick a profile, review port assignments, enter "
            "the per-switch details (hostname, local users, IPs, SVI IPs, "
            "routed-interface IPs, BGP values, etc.), click Generate, then "
            "copy or save the config.")

        # ---- Recommended order ----
        heading("Recommended Setup Order")
        body(
            "Complete the setup tabs in this order. Each step builds on "
            "the previous one:\n\n"
            "1.  Base Settings   - Global IOS commands shared by all switches\n"
            "2.  Switch Models   - Hardware definitions (port groups)\n"
            "3.  Interface Roles - Reusable per-port command templates\n"
            "4.  Site Profiles   - VLANs, services, L3, and port assignments\n"
            "5.  Generate Config - Use the wizard to build a config")

        # ---- Menu Bar ----
        heading("Menu Bar")
        body(
            "The application has a small menu bar across the top with two "
            "menus:\n\n"
            "File\n"
            "  Export Settings...    Save all your models, roles, profiles, "
            "base settings, and theme as a single ZIP. Use this to back up or "
            "share your setup with teammates.\n"
            "  Import Settings...    Load a previously exported ZIP. "
            "Overwrites the current data.\n"
            "  Recent Profiles       Jump straight to a recently used site "
            "profile in the wizard.\n"
            "  Recent Settings ZIPs  Re-import a recent settings backup.\n"
            "  Recent Configs        Re-open a previously generated config "
            "file in the preview pane.\n\n"
            "Theme\n"
            "  Pick a built-in theme (Default, Coral, Sandstone, Chris, "
            "Voyager, Light) or one of your custom themes. Choose "
            "'Edit Custom Themes...' to create, edit, duplicate, or delete "
            "your own colour palettes.")

        # ---- Step 1: Base Settings ----
        heading("Step 1 - Base Settings Tab")
        body(
            "The Base Settings tab contains IOS commands that are the same "
            "across every switch you configure. Each section is a text area "
            "where you paste raw IOS commands. Leave a section blank to skip "
            "it.\n\n"
            "Sections include: Global Services, Management VRF, Logging, "
            "AAA, Security, SSH/Crypto, Switching Features, Management Port, "
            "Line Configuration, Banner, Disabled Port Template, and "
            "Custom Config Sections for production extras like SNMP, "
            "QoS, DHCP Snooping, ACLs, etc.")

        subheading("Multiple Base Sets")
        body(
            "The Base Settings tab supports multiple named sets. The list on "
            "the left shows every set you have defined. Use the buttons to "
            "manage them:\n\n"
            "  + Add        Create a new base set (gives you a clean editor).\n"
            "  Duplicate    Clone the selected set so you can tweak a copy.\n"
            "  Set Default  Mark the selected set as the fallback used when "
            "a Site Profile does not name a base set, or when the named one "
            "is missing.\n"
            "  Delete       Remove the selected set.\n\n"
            "Each Site Profile picks one base set in the 'Base Settings' "
            "dropdown on the Site Profiles tab. This lets you keep different "
            "AAA / SSH / banner blocks for, say, corporate vs. lab vs. "
            "DMZ sites and select the right one per profile.")

        subheading("Global Services Example")
        code(
            "no service pad\n"
            "service timestamps debug datetime msec localtime\n"
            "service timestamps log datetime msec localtime\n"
            "service password-encryption\n"
            "no service call-home\n"
            "no platform punt-keepalive disable-kernel-core")

        subheading("AAA Example")
        code(
            "aaa new-model\n"
            "aaa authentication login default local\n"
            "aaa authentication enable default enable\n"
            "aaa authorization exec default local")

        subheading("SSH / Crypto Example")
        code(
            "crypto key generate rsa modulus 4096\n"
            "ip ssh version 2\n"
            "ip ssh time-out 60\n"
            "ip ssh authentication-retries 2")

        subheading("Line Configuration Example")
        code(
            "line con 0\n"
            "logging synchronous\n"
            "exec-timeout 15 0\n"
            "line vty 0 15\n"
            "transport input ssh\n"
            "exec-timeout 15 0")

        subheading("Disabled Port Template")
        body(
            "This template is applied to unassigned ports on the switch - "
            "ports that do not have a role assigned in Step 2 of Generate "
            "Config (or in the profile's port assignments). Assigned ports "
            "skip this template and are configured through their role "
            "instead. It is the security baseline - typically shuts down "
            "unused ports and puts them on a blackhole VLAN.\n\n"
            "You can use {{ variable }} placeholders here. The variable "
            "values come from the Site Profile's Role Variables section. "
            "For example, {{ blackhole_vlan }} will be replaced with the "
            "VLAN number you define in the profile.")
        code(
            "description //Disabled Port\n"
            "switchport access vlan {{ blackhole_vlan }}\n"
            "switchport mode access\n"
            "shutdown\n"
            "spanning-tree bpduguard enable")
        body("Click 'Save Base Settings' when done.")

        subheading("Custom Config Sections")
        body(
            "Use the Custom Config Sections area to add production-ready "
            "config blocks that go beyond the basics - things like SNMP, "
            "NTP, QoS, DHCP Snooping, Dynamic ARP Inspection, ACLs, "
            "TACACS+, and anything else your production environment needs.\n\n"
            "Click '+ Add Section' to create a new block. Each section has:\n\n"
            "  Name - A label for your reference (e.g. 'SNMP Config')\n\n"
            "  Position - Where it appears in the generated config:\n"
            "    'Before Interfaces' - after VLANs, before ports are "
            "configured. Good for DHCP Snooping, DAI, and global "
            "policies that must exist before interface commands.\n"
            "    'After Interfaces' - after all port and VLAN interface "
            "config. Good for SNMP, NTP, ACLs, route-maps, and "
            "monitoring.\n\n"
            "  Commands - Raw IOS commands, just like the other Base "
            "Settings sections. You can use {{ variable }} placeholders "
            "here - values come from the Site Profile's Role Variables.\n\n"
            "You can add as many sections as you need. They are saved "
            "with your Base Settings and included in every generated "
            "config. Delete a section with the X button.")

        subheading("Custom Section Example: SNMP")
        code(
            "snmp-server community {{ snmp_ro_community }} RO\n"
            "snmp-server location {{ site_location }}\n"
            "snmp-server contact {{ contact_email }}")

        body(
            "Note: DNS name-servers, NTP servers, clock timezone, and "
            "summer-time are now configured per-profile in the Site Profiles "
            "tab under 'Services' instead of as a custom Base section.")

        subheading("Custom Section Example: DHCP Snooping")
        code(
            "ip dhcp snooping\n"
            "ip dhcp snooping vlan {{ access_vlan }}\n"
            "no ip dhcp snooping information option\n"
            "ip arp inspection vlan {{ access_vlan }}")

        subheading("Custom Section Example: QoS")
        code(
            "mls qos\n"
            "class-map match-any VOICE\n"
            "match ip dscp ef\n"
            "policy-map QOS-POLICY\n"
            "class VOICE\n"
            "priority percent 30\n"
            "class class-default\n"
            "bandwidth remaining percent 70")

        # ---- Step 2: Switch Models ----
        heading("Step 2 - Switch Models Tab")
        body(
            "Define each switch hardware model your organization uses. "
            "The app needs to know what interfaces exist on each model so "
            "it can disable all ports before selectively enabling the ones "
            "you assign.\n\n"
            "For each model, provide:")
        body(
            "Model Name - The exact Cisco model identifier "
            "(e.g. C9200L-24T-4G-A).\n\n"
            "Port Groups - Each group of interfaces on the switch. "
            "Click '+ Add Port Group' for each group and fill in:")
        body(
            "  Prefix  - The IOS interface prefix including the trailing "
            "slash, e.g. GigabitEthernet1/0/\n"
            "  Start   - First port number in the range\n"
            "  End     - Last port number in the range")

        subheading("Stack Members")
        body(
            "Set Stack Members to the number of switches in a stack (1 for "
            "standalone). Port groups are replicated per member - e.g. "
            "GigabitEthernet1/0/1-24 on a 4-member stack becomes "
            "GigabitEthernet1/0/1-24 through GigabitEthernet4/0/1-24 in "
            "the Generate wizard.")

        subheading("Example: C9200L-24T-4G-A")
        code(
            "Model Name:     C9200L-24T-4G-A\n"
            "Provision Type: c9200l-24t\n"
            "Stack Members:  1\n"
            "\n"
            "Port Group 1:   GigabitEthernet1/0/    Start: 1    End: 24\n"
            "Port Group 2:   GigabitEthernet1/1/    Start: 1    End: 4")

        subheading("Example: C9300-24S-A")
        code(
            "Model Name:     C9300-24S-A\n"
            "Provision Type: c9300-24\n"
            "\n"
            "Port Group 1:   GigabitEthernet1/0/       Start: 1   End: 24\n"
            "Port Group 2:   TenGigabitEthernet1/1/    Start: 1   End: 8\n"
            "Port Group 3:   AppGigabitEthernet1/0/    Start: 1   End: 1\n"
            "Port Group 4:   GigabitEthernet0/          Start: 0   End: 0")
        body("Click 'Save Model' when done.")

        # ---- Step 3: Interface Roles ----
        heading("Step 3 - Interface Roles Tab")
        body(
            "An Interface Role is a reusable block of IOS commands that can "
            "be applied to any interface. Think of it as a template for a "
            "type of port - access port, trunk port, uplink, etc.\n\n"
            "For each role, provide a name and the IOS commands that should "
            "be applied to the interface. The commands go between 'interface "
            "...' and 'exit' - do NOT include those lines.")

        subheading("Using Variables in Roles")
        body(
            "You can include {{ variable }} placeholders in your commands. "
            "These variables are defined in the Site Profile's Role Variables "
            "section, so the same role template can be reused across sites "
            "with different VLAN numbers.\n\n"
            "{{ description }} is always available - it is set per port "
            "assignment in the profile or in the Generate wizard.")

        subheading("Example: Access Port Role")
        code(
            "description {{ description }}\n"
            "switchport access vlan {{ access_vlan }}\n"
            "switchport mode access\n"
            "no shutdown\n"
            "spanning-tree portfast\n"
            "spanning-tree bpduguard enable")

        subheading("Example: Trunk Uplink Role")
        code(
            "description {{ description }}\n"
            "switchport trunk native vlan {{ native_vlan }}\n"
            "switchport trunk allowed vlan {{ trunk_allowed }}\n"
            "switchport mode trunk\n"
            "no shutdown")

        subheading("Example: Private VLAN Promiscuous Role")
        code(
            "description {{ description }}\n"
            "switchport private-vlan mapping "
            "{{ pvlan_primary }} {{ pvlan_isolated }}\n"
            "switchport mode private-vlan Promiscuous\n"
            "no shutdown\n"
            "spanning-tree portfast\n"
            "spanning-tree bpduguard enable")

        subheading("Example: Private VLAN Isolated Role")
        code(
            "description {{ description }}\n"
            "switchport private-vlan host-association "
            "{{ pvlan_primary }} {{ pvlan_isolated }}\n"
            "switchport private-vlan mapping "
            "{{ pvlan_primary }} {{ pvlan_isolated }}\n"
            "switchport mode private-vlan host\n"
            "no shutdown\n"
            "spanning-tree portfast\n"
            "spanning-tree bpduguard enable")

        subheading("Routed Interfaces (Requires IP)")
        body(
            "Tick 'Requires per-switch IP (L3 interface)' for roles that turn "
            "an interface into a layer-3 routed port (no switchport). When a "
            "port is assigned to such a role, Step 3 grows a Routed Interface "
            "IPs row for that port. Use {{ ip }} and {{ mask }} as placeholders "
            "in the role template. If Step 3 leaves IP or Mask blank, the "
            "renderer falls back to the profile's Routed Interfaces section "
            "defaults.")
        code(
            "desc //Routed Uplink\n"
            "no switchport\n"
            "ip address {{ ip }} {{ mask }}\n"
            "no shut")
        body("Click 'Save Role' when done.")

        # ---- Step 4: Site Profiles ----
        heading("Step 4 - Site Profiles Tab")
        body(
            "A Site Profile ties everything together for a specific type of "
            "deployment. It defines the VLANs, the variable values that feed "
            "into your role templates, and which interfaces get which roles.\n\n"
            "Create one profile per deployment type (e.g. 'Office-Floor3', "
            "'Warehouse', 'Data-Center-ToR').")

        subheading("Profile Name & Management VLAN")
        body(
            "Give the profile a descriptive name. The Management VLAN ID is "
            "a legacy/default field used when migrating older profiles. On "
            "L3 profiles, management IP is configured through the Management "
            "VLANs L3 section (or Loopbacks / Routed Interfaces). On plain "
            "L2 profiles, Step 3's Management IP goes on interface "
            "vlan<mgmt_vlan>.")

        subheading("Base Settings Selector")
        body(
            "Pick which Base set this profile should use. The dropdown is "
            "populated from the Base Settings tab. If the named set is "
            "missing at generate time, the app falls back to the default "
            "set marked on the Base Settings tab.")

        subheading("Services (DNS / NTP / Clock)")
        body(
            "These per-profile values render as IOS commands in the generated "
            "config so different sites can point at different DNS/NTP "
            "infrastructure without duplicating Base sets:\n\n"
            "  Name Servers         One or more DNS IPs, comma separated. "
            "Becomes 'ip name-server ...' lines.\n"
            "  Clock Timezone       Free-form 'clock timezone ...' value, "
            "e.g. 'EST -5'.\n"
            "  Clock Summer-Time    Free-form 'clock summer-time ...' value, "
            "e.g. 'EDT recurring'.\n"
            "  NTP Commands         Free-form paste box - lines emit "
            "verbatim in the Global section (same pattern as OSPF). Paste "
            "exactly the 'ntp ...' and related ACL lines you want, e.g. "
            "ntp authenticate, ntp server, ntp source, access-list for NTP.")

        subheading("Credential Defaults")
        body(
            "Optional defaults that pre-fill Generate Config Step 3 when "
            "this profile is selected:\n\n"
            "  Local Users         One row per IOS local account. Each row "
            "renders as 'username <name> privilege <P> secret <password>'. "
            "Step 3 loads an editable copy for each generated switch.\n"
            "  Enable Secret       Privileged EXEC password.\n\n"
            "These are defaults only - per-switch edits in the wizard are "
            "not written back to the profile.")

        subheading("VLAN Definitions")
        body(
            "Paste the raw IOS VLAN commands for this site. This includes "
            "standard VLANs, private VLANs, and any VLAN associations. "
            "These commands are inserted into the config exactly as entered.\n\n"
            "Tick 'Allow per-switch VLAN overrides in Step 3' when a site "
            "needs different VLAN IDs on individual switches. The wizard "
            "then shows a VLAN editor pre-filled from this block; edits "
            "replace the profile VLANs for that switch only. On L3 profiles, "
            "SVI VLAN IDs can also be edited per switch so they stay in sync "
            "with the VLAN block.")
        code(
            "vlan 100\n"
            "name Data\n"
            "vlan 200\n"
            "name Voice\n"
            "vlan 999\n"
            "name Blackhole\n"
            "vlan 500\n"
            "name MGMT")

        subheading("Private VLAN Example")
        code(
            "vlan 300\n"
            "name Isolated-PVLAN\n"
            "private-vlan isolated\n"
            "vlan 301\n"
            "name Primary-PVLAN\n"
            "private-vlan primary\n"
            "private-vlan association 300")

        subheading("Role Variables")
        body(
            "Key/value pairs that replace {{ key }} placeholders in your "
            "Interface Role commands and the Disabled Port Template. Click "
            "'+ Add Variable' for each one.\n\n"
            "Common examples:")
        code(
            "Key: access_vlan        Value: 100\n"
            "Key: native_vlan        Value: 100\n"
            "Key: trunk_allowed      Value: 100,200,500\n"
            "Key: blackhole_vlan     Value: 999\n"
            "Key: pvlan_primary      Value: 301\n"
            "Key: pvlan_isolated     Value: 300")

        subheading("Port Assignments")
        body(
            "Map interface ranges to roles. Each row specifies:\n\n"
            "  Interface(s) - The IOS interface or range text that goes after "
            "'interface'. For a single port: GigabitEthernet1/0/1  For "
            "multiple ports: range GigabitEthernet1/0/1-12\n\n"
            "  Role - Pick one of the roles you defined in the Interface "
            "Roles tab.\n\n"
            "  Description - The port description. This value is available as "
            "{{ description }} in the role template.\n\n"
            "Any ports from the switch model that are NOT assigned here will "
            "be disabled using the Disabled Port Template from Base Settings.")
        code(
            "Interface(s)                         Role           Description\n"
            "range GigabitEthernet1/0/1-20        Access Port    User Ports\n"
            "range GigabitEthernet1/0/21-22       Trunk Uplink   Core Uplink\n"
            "GigabitEthernet1/1/1                 Trunk Uplink   Stack Link")

        subheading("Layer 3 Toggle")
        body(
            "Tick 'Enable Layer 3' for sites that route. This reveals the L3 "
            "editor and tells the generator to emit routing-related blocks "
            "(L3 interfaces, OSPF paste, BGP, default route, etc.). Leave it "
            "off for plain access-layer switches.")

        subheading("L3 Interface Sections")
        body(
            "When Layer 3 is on, enable each section you need with its "
            "checkbox. You can enable more than one. Each section supports "
            "multiple rows (+ Add ...) and carries site-wide IP/Mask defaults "
            "that pre-fill Generate Config Step 3:\n\n"
            "  Loopbacks           One or more loopback interfaces. Typical "
            "for router-ID and management reachability. Each row has an "
            "Interface Config box for the full Loopback stanza body; use "
            "{{ ip }}, {{ mask }}, and {{ description }} placeholders.\n"
            "  Routed Interfaces   Standalone routed uplink(s). Interface "
            "name is optional - leave it blank when the uplink is assigned "
            "via a Requires-IP role in Step 2 instead.\n"
            "  Management VLANs    One or more management SVIs (interface "
            "vlan<ID>). Replaces the old single mgmt-VLAN approach.\n\n"
            "Typical workflow: set Mask (and optionally IP) on the profile, "
            "leave IP blank for per-switch entry on Step 3. "
            "'ip default-gateway' is emitted whenever Default Gateway is set "
            "on Step 3, regardless of which sections are enabled.")

        subheading("SVIs")
        body(
            "Define VLANs that need an SVI on every switch at the site "
            "(user gateways, voice, ISP handoff VLANs, etc.). Each row "
            "carries:\n\n"
            "  VLAN          The VLAN ID the SVI belongs to.\n"
            "  Description   Free-form text rendered as the SVI description.\n"
            "  IP / Mask     Optional site-wide defaults. Often leave IP "
            "blank and fill per-switch on Step 3.\n"
            "  Helpers (CSV) Optional DHCP helper IPs, comma separated. "
            "Each becomes an 'ip helper-address ...' line.\n\n"
            "Per-switch IP/Mask (and optionally VLAN ID when per-switch "
            "VLAN overrides are enabled) are entered in Generate Config "
            "Step 3 under SVI IPs.")

        subheading("OSPF")
        body(
            "Paste the site-wide OSPF IOS block for this profile. Lines "
            "emit verbatim in the Routing section. Router-ID can be "
            "included in the paste or left to Generate Config Step 3, "
            "which defaults to the first loopback IP.")
        code(
            "router ospf 1\n"
            "passive-interface default\n"
            "no passive-interface TenGigabitEthernet1/1/1\n"
            "network 10.0.0.0 0.0.255.255 area 0\n"
            "exit")

        subheading("BGP")
        body(
            "Add one BGP instance per local ASN (+ Add BGP). Each instance "
            "renders as its own 'router bgp <local_asn>' block. On the "
            "profile, define Peer Slots (remote ASN + description) for "
            "neighbours that exist on every switch. Per-switch values are "
            "filled in Generate Config Step 3:\n\n"
            "  ISP Gateway         Next-hop toward the ISP (often matches "
            "Default Gateway).\n"
            "  User Network        Prefix advertised to BGP.\n"
            "  User Network Mask   Mask for the advertised prefix.\n"
            "  Circuit ID          Optional description on the BGP session.\n"
            "  Peer IP / Password  One row per peer slot - neighbour address "
            "and optional MD5 key.\n\n"
            "Default Gateway on Step 3 auto-fills blank ISP Gateway and "
            "Peer IP fields (one-way sync). Edit those BGP fields "
            "independently afterward without changing Default Gateway.")
        code(
            "Local ASN: 65000\n"
            "Peer Slots:\n"
            "  Remote ASN: 65001   Description: ISP_Peer\n"
            "  Remote ASN: 65000   Description: Loopback_iBGP")

        subheading("ACLs")
        body(
            "Define named extended ACLs that render in the post-interface "
            "section of the config. Each ACL has a name, type "
            "(currently 'extended'), and a list of rules. Each rule is one "
            "of:\n\n"
            "  remark                Free-form comment line.\n"
            "  permit / deny         A rule with protocol, source + wildcard, "
            "destination + wildcard, and optional 'log'.\n\n"
            "Used for typical edge ACLs like 'block bogons' or 'deny user "
            "subnets to mgmt'.")
        body("Click 'Save Profile' when done.")

        # ---- Daily Use ----
        heading("Daily Use - Generate Config Tab")
        body(
            "Once setup is complete, generating a config is a 3-step wizard:")

        subheading("Wizard Step 1 - Select Model & Site")
        body(
            "Choose the switch model (determines available interfaces) and "
            "the site profile (determines VLANs, roles, and defaults). "
            "Click Next.")

        subheading("Wizard Step 2 - Port Assignments")
        body(
            "The wizard shows all available port groups from the model and "
            "pre-fills port assignments from the profile. You can:\n\n"
            "  - Modify assignments for this specific switch\n"
            "  - Add new rows with '+ Add Row'\n"
            "  - Remove rows with the X button\n"
            "  - Toggle Port Display between Range and Individual Ports\n"
            "  - Split a range into sub-ranges (e.g. change "
            "'range Gi1/0/1-24' into two rows: "
            "'range Gi1/0/1-12' and 'range Gi1/0/13-24' with different "
            "roles)\n\n"
            "Leave the Role dropdown on 'unassigned' for ranges you want to "
            "stay disabled. Only unassigned ports receive the Disabled Port "
            "Template from Base Settings; assigned ports are configured "
            "through their role instead. Click Next.")

        subheading("Wizard Step 3 - Switch Details")
        body(
            "Fill in the values unique to this specific switch. The fields "
            "shown depend on the profile - Layer 3 profiles unlock extra "
            "sections.\n\n"
            "Core fields (always shown):\n"
            "  Hostname         The switch hostname (e.g. SW-FLOOR3-01).\n"
            "  Local Users      Editable copy of the profile's user list. "
            "Each row becomes one 'username ... privilege ... secret ...' "
            "line. Use + Add User for extra accounts.\n"
            "  Enable Secret    Privileged EXEC password.\n"
            "  Domain Name      IP domain name (also used for SSH key "
            "generation).\n"
            "  Default Gateway  Always emits 'ip default-gateway'. For "
            "Layer 3 profiles, also auto-emits 'ip route 0.0.0.0 0.0.0.0 "
            "<gateway>' unless you supplied your own default route under "
            "Static Routes. When the profile has BGP, blank ISP Gateway "
            "and Peer IP fields auto-fill from Default Gateway (edit them "
            "independently afterward if needed).\n"
            "  Work Order #     Optional comment line in the config header.\n\n"
            "L2-only fields (hidden when the profile is Layer 3):\n"
            "  Management IP / Subnet Mask  Used for the management SVI on "
            "plain L2 profiles.\n\n"
            "Optional sections (shown when applicable):\n"
            "  OOB Management Port (Gi0/0)  Shown when the model defines "
            "GigabitEthernet0/x. Leave blank to use Base Settings default.\n"
            "  VLAN Definitions (this switch)  Shown when the profile allows "
            "per-switch VLAN overrides. Replaces the profile VLAN block for "
            "this switch only.\n\n"
            "Layer 3 sections (shown when the profile has Layer 3 enabled, "
            "each sub-section only when enabled on the profile):\n"
            "  Loopbacks            Per-switch IP/Mask for each loopback "
            "defined on the profile.\n"
            "  Routed Interfaces    Per-switch IP/Mask for standalone routed "
            "uplinks from the profile. Use this when the profile leaves "
            "interface blank and the uplink is assigned via a Requires-IP "
            "role - the IP typed here applies to that port.\n"
            "  Management VLANs     Per-switch IP/Mask for each management "
            "SVI defined on the profile.\n"
            "  OSPF Router ID       Shown when the profile has OSPF pasted. "
            "Optional; defaults to the first loopback IP if blank.\n"
            "  Routed Interface IPs One row per port assigned to a "
            "Requires-IP role. Alternative to Routed Interfaces above - "
            "fill IP/Mask per port. Mask pre-fills from the profile; blank "
            "IP/Mask inherit from the profile's Routed Interfaces section "
            "at render time.\n"
            "  SVI IPs              One row per SVI on the profile. Fill "
            "per-switch IP/Mask (and VLAN ID when per-switch VLAN overrides "
            "are enabled).\n"
            "  Static Routes        Optional 'ip route ...' entries with "
            "optional descriptions. A live preview shows what will emit, "
            "including the auto default route from Default Gateway.\n"
            "  BGP                  One block per BGP instance on the "
            "profile: ISP Gateway, User Network, User Network Mask, Circuit "
            "ID, plus Peer IP / Password rows for each peer slot.\n\n"
            "Click 'Generate Config' to build the configuration. It appears "
            "in the preview pane on the right. Use the quick-copy section "
            "buttons or 'Copy to Clipboard' to paste into the switch console, "
            "or 'Save to File' to save a .txt file (added to Recent Configs).\n\n"
            "'Push to Switch...' opens a dialog that streams the generated "
            "config to a switch over its console port via a USB-to-serial "
            "adapter. Pick the COM port, baud (9600 is the Cisco default), "
            "and optionally an enable password. The tool answers the day-0 "
            "setup dialog, enters enable mode, and sends the config line-by-"
            "line - waiting for the prompt between lines so a slow console "
            "doesn't lose characters. Tick 'Run write memory when finished' "
            "to save to startup-config at the end. Requires the 'pyserial' "
            "Python package.")

        # ---- Config Order ----
        heading("Generated Config Order")
        body(
            "The generated config assembles sections in this order. Layer-3 "
            "blocks are only emitted when the profile has Layer 3 enabled.\n\n"
            "Global / Base\n"
            "   Header comment with hostname\n"
            "   configure terminal\n"
            "   Global Services (Base)\n"
            "   hostname\n"
            "   Management VRF (Base)\n"
            "   Logging (Base)\n"
            "   Credentials (enable secret + local username/password)\n"
            "   AAA (Base)\n"
            "   Security (Base)\n"
            "   ip domain name\n"
            "   ip name-server lines (Profile Services)\n"
            "   clock timezone / summer-time (Profile Services)\n"
            "   NTP authentication + ntp server lines (Profile Services)\n"
            "   SSH / Crypto (Base)\n"
            "   Switching Features (Base)\n\n"
            "VLANs\n"
            "   VLAN Definitions (Profile, or per-switch override from Step 3)\n"
            "   Custom Sections - Before Interfaces (Base)\n"
            "   Disable unassigned ports (Model port groups + Disabled Port "
            "Template; assigned ports skip this)\n"
            "   VLAN 1 shutdown\n"
            "   Management Port (Base)\n\n"
            "L3 Interfaces  (Layer 3 only)\n"
            "   ip routing\n"
            "   Loopbacks (when Loopbacks section enabled on profile)\n"
            "   Standalone routed interfaces (when Routed Interfaces section "
            "enabled and not already covered by a Requires-IP role)\n"
            "   SVIs from profile svis list (user/voice gateways, etc.)\n"
            "   Embedded interface-Vlan blocks peeled from VLAN definitions\n\n"
            "Interfaces\n"
            "   Port Assignments - role templates applied per Step 2 row, "
            "including routed uplinks via Requires-IP roles with {{ ip }} / "
            "{{ mask }} from Step 3\n\n"
            "Management\n"
            "   Management VLAN interface(s) (when Management VLANs section "
            "enabled on profile, or L2 mgmt SVI from Step 3 Management IP)\n"
            "   ip default-gateway (always when set)\n\n"
            "Post-Interface\n"
            "   Custom Sections - After Interfaces (Base)\n"
            "   Profile ACLs (named extended ACLs)\n\n"
            "Routing  (Layer 3 only)\n"
            "   OSPF block pasted in the profile (router-id injected from "
            "Step 3 when omitted from the paste)\n"
            "   router bgp <asn> block(s) with neighbours, user-network "
            "advertisement, and MD5 auth\n"
            "   Static Routes from Step 3\n"
            "   Auto default route via Default Gateway (if no user-supplied "
            "0.0.0.0/0)\n\n"
            "Line Config\n"
            "   Line Configuration (Base)\n\n"
            "Banner / End\n"
            "   Banner Login (Base)\n"
            "   end")

        # ---- Tips ----
        heading("Tips")
        body(
            "- All data is saved as JSON files in the data/ folder. You can "
            "back up or share these files with your team, or use File > "
            "Export Settings to bundle them into a single ZIP.\n\n"
            "- You can create multiple Site Profiles for different deployment "
            "types using the same Interface Roles and Switch Models. Each "
            "profile can point at a different Base Settings set if needed.\n\n"
            "- If you need a port configured differently than the profile "
            "default, adjust it in the wizard's Step 2 - the changes only "
            "affect the current config, not the saved profile. The same is "
            "true for credentials and other per-switch fields in Step 3.\n\n"
            "- The Disabled Port Template runs on unassigned ports only. "
            "Ports you assign a role to in Step 2 are configured through "
            "that role instead and do not receive the disabled template.\n\n"
            "- Leave any Base Settings section blank to omit it entirely "
            "from the generated config.\n\n"
            "- The 'interface' keyword is added automatically. In port "
            "assignments, just enter the range text - e.g. "
            "'range GigabitEthernet1/0/1-12' (not 'interface range ...').\n\n"
            "- A role with 'Requires per-switch IP' produces an extra row in "
            "Step 3's Routed Interface IPs grid for every port it is assigned "
            "to. Use {{ ip }} and {{ mask }} in the role template.\n\n"
            "- Routed uplink IPs can be entered in either place on Step 3: "
            "the Routed Interface IPs grid (per port) or the Routed "
            "Interfaces grid (especially when the profile leaves interface "
            "blank). The renderer merges both sources; profile defaults fill "
            "in any blank IP or Mask at render time.\n\n"
            "- Enable L3 Interface Sections independently on the profile "
            "(Loopbacks, Routed Interfaces, Management VLANs). Old profiles "
            "that used mgmt_style are migrated automatically.\n\n"
            "- Per-switch VLAN overrides remap role variables (e.g. user_vlan) "
            "when VLAN IDs change on Step 3, so interface roles stay aligned "
            "with updated VLAN numbers.\n\n"
            "- For Layer 3 edge sites that talk BGP, define one BGP instance "
            "per local ASN and one peer slot per neighbour role. Each switch "
            "fills in ISP Gateway, User Network, Circuit ID, and peer "
            "IP/Password on Step 3. Default Gateway auto-fills blank ISP "
            "Gateway and Peer IP fields.\n\n"
            "- Default Gateway is required for most deployments. For Layer 3 "
            "profiles it also seeds the auto 'ip route 0.0.0.0 0.0.0.0' "
            "default route unless you supplied your own under Static Routes.\n\n"
            "- Use the Theme menu to switch between built-in palettes or "
            "open the custom theme editor to build your own.")


