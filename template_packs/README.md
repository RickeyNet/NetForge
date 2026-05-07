# Template Packs

Importable settings bundles that pre-populate NetForge with a working baseline.
Use **Settings → Import Settings** and select one of the `.zip` files in this
directory. Importing **overwrites** your current `models.json`, `roles.json`,
`profiles.json`, and `base_settings.json` — export your existing settings
first if you want to keep them.

## Available packs

| Pack | Source | Status |
|------|--------|--------|
| `cisco_l2_baseline.zip` | Cisco 9300 IOS XE hardened baseline (L2 Switch) | Ready |
| `cisco_l3_baseline.zip` | Cisco 9300 IOS XE hardened baseline (L3 Switch) | Ready |

---

## cisco_l2_baseline

A hardened Layer 2 access-switch baseline for Cisco Catalyst 9300/9200
running IOS XE.

### What's covered

**Base Settings text-areas:**
- Global Services — `no service config/finger/pad/call-home`,
  `service password-encryption`, UDLD, errdisable recovery, `no cdp run`,
  HTTP server disabled, login block, etc.
- Logging — syslog hosts, login on-success/failure, archive log config.
- AAA — `aaa new-model`, common-criteria `PASSWORD_POLICY`, two RADIUS
  servers + `RADIUS_GROUP`, `ip radius source-interface vlan <MGMT_VLAN>`.
- Security — `spanning-tree mode rapid-pvst`, loopguard, extend system-id.
- SSH — version 2, modulus 2048, AES256-GCM/CTR, HMAC-SHA2-512/256.
- Switching — `vtp mode off`, transceiver monitoring, diagnostic boot level,
  punt-keepalive.
- Line Configuration — VTY 0-4 with `SWITCH_MGMT` ACL, VTY 5-98 disabled,
  console session-timeout/exec-timeout.
- Banner — placeholder warning banner.
- Disabled-port template — full hardened L2 disabled access port
  (port-security, BPDU guard, root guard, storm-control, shutdown).

**Custom Sections:**
- *Switch Management ACL* (pre-interface) — `SWITCH_MGMT` extended ACL with
  10 host slots referenced by `line vty`.
- *DHCP and IGMP Snooping* (pre-interface) — `no ip igmp snooping`,
  `ip dhcp snooping`, snooping VLAN list.
- *NTP* (post-interface) — authenticated NTP, two servers, UTC timezone.
- *SNMPv3* (post-interface) — view/group/user/host with SHA-2 auth and
  AES-256 priv.

**Roles (`roles.json`):**
- `L2 Access (Hardened)` — hardened access port with port-security,
  BPDU guard, root guard, storm-control.
- `L2 Trunk (Hardened)` — hardened trunk with native-VLAN pinning,
  pruned VLAN 1, root guard, storm-control.
- `L2 Trunk + DHCP Snooping Trust (Hardened)` — same as above plus
  `ip dhcp snooping trust`. Use only on uplinks where DHCP traffic
  must be trusted.
- Existing pre-loaded roles (Access Port, Trunk Uplink to Switch/Firewall,
  Private VLAN Promiscuous/Isolated) are preserved.

**Profile:** `Cisco L2 Baseline (example)` — pre-fills every role variable
the custom sections expect, using `<PLACEHOLDER>` markers you replace per
site (NTP, SNMP, ACL hosts).

**Models:** Unchanged from NetForge defaults.

### What you need to fill in per site

Two kinds of placeholders to replace, because NetForge only Jinja-renders
custom sections, roles, and the disabled-port template — the global
text-areas (AAA, Logging, etc.) are pasted as-is.

**1. Profile role variables (Jinja).** Open
*Site Profiles → Cisco L2 Baseline (example) → Role Variables* and replace
every `<PLACEHOLDER>` value:

| Variable | What it is |
|---|---|
| `ntp_server_1/2`, `ntp_key` | NTP servers + Type-7 SHA1 key |
| `snmp_host`, `snmp_user`, `snmp_auth_password`, `snmp_priv_password` | SNMPv3 trap receiver + creds |
| `mgmt_acl_host_1`..`_10` | Hosts allowed to SSH into the switch |
| `dhcp_snooping_vlans` | Comma list of VLANs running DHCP |
| `access_vlan`, `native_vlan`, `trunk_allowed`, `blackhole_vlan` | Per-port defaults |

**2. Base Settings find-and-replace.** Open *Base Settings* and edit:

| Section | Replace |
|---|---|
| Logging | `<SYSLOG_IP_1>`, `<SYSLOG_IP_2>` |
| AAA | `<RADIUS_IP_1>`, `<RADIUS_IP_2>`, `<RADIUS_KEY_1>`, `<RADIUS_KEY_2>`, `<MGMT_VLAN>` |

The example profile uses VLAN 3 for management, VLAN 66 as the trunk
native blackhole, and VLAN 67 as the disabled-port blackhole — adjust
these to match your environment if different. If you change the
management VLAN, also update `<MGMT_VLAN>` in the AAA text-area so
RADIUS source-interface matches.

### What's *not* in this pack

- **Loopback0 + L3 routed uplinks + SVIs.** These are L3 features and
  live in `cisco_l3_baseline.zip`. Use that pack instead if you need
  routed interfaces, OSPF, or SVIs.
- **Per-site SNMP location/contact and IP-helper addresses.** These vary
  per site and aren't yet expressible without per-site custom sections.

### Verifying the import

After importing, open *Generate Config*, pick the example profile and any
9300/9200 model, fill in switch details, and click **Preview**. Spot-check:

1. Disabled-port block runs from G1/0/1 through the last data port and
   ends with `shutdown`.
2. The `SWITCH_MGMT` ACL appears before interface configs.
3. NTP and SNMPv3 blocks appear after interface configs.
4. `line vty 0 4` has `access-class SWITCH_MGMT in vrf-also`.
5. RADIUS servers, syslog hosts, NTP servers, SNMP host all show
   placeholder values that you still need to replace before deploying.

---

## cisco_l3_baseline

A hardened Layer 3 distribution-switch baseline for Cisco Catalyst 9300
running IOS XE. Mgmt rides Loopback0 and OSPF area 0 reaches it through
two routed uplinks; SVIs act as default gateways for user/voice VLANs.

### What's covered

**Base Settings text-areas** — same hardened policies as the L2 pack
(global services, AAA with `ip radius source-interface Loopback0`,
logging, SSH, line config, banner, custom sections), plus L3 globals:
- *Switching* — adds `ip cef`, `ipv6 unicast-routing`, `ipv6 cef`.
- *NTP / SNMP* — both source-interface Loopback0 (so the loopback IP
  is the consistent source for management traffic).

**Custom Sections** — same four as L2 (`SWITCH_MGMT` ACL, DHCP/IGMP
snooping, NTP, SNMPv3). The DHCP-snooping VLAN list is widened to
`10,20` (data + voice).

**Profile** — `Cisco L3 Baseline (example)` with `layer3=true`,
`mgmt_style=loopback`, and:
- Loopback0 with `<LOOPBACK_IP>/32` for mgmt + OSPF router-id.
- VLAN definitions for VLANs 3, 10, 20, 66 (native blackhole),
  67 (disabled).
- Three SVIs — VLAN 3 (mgmt SVI for any L2 stragglers), VLAN 10
  (USER_DATA, with helper-addresses), VLAN 20 (VOICE, with helpers).
- Two routed uplinks (G1/0/1 → CORE-A, G1/0/2 → CORE-B) with `mtu 9100`
  and `ip ospf 1 area 0`.
- OSPF process 1, `<LOOPBACK_IP>` as router-id, `passive-interface
  default` with the two uplinks marked active. Loopback0 is advertised
  via `network <LOOPBACK_IP> 0.0.0.0 area 0`.
- No static routes (use the structured editor to add a fallback default
  if your design needs one).

**Roles** — same as the L2 pack. A routed L3 switch still has access
ports for users; routed uplinks are configured directly via the
*Routed Uplinks* grid in the profile, not via roles.

**Models** — unchanged from NetForge defaults.

### What you need to fill in per site

**1. Profile fields (Site Profiles → Cisco L3 Baseline (example)):**

| Field | What it is |
|---|---|
| Loopback0 → IP | Switch loopback address (used for mgmt and OSPF router-id). The `<LOOPBACK_IP>` placeholder also appears in the OSPF router-id and a `network` statement — replace all three. |
| SVIs → VLAN 3 IP/Mask | Mgmt SVI gateway (only if you keep an L2 mgmt SVI alongside the loopback). |
| SVIs → VLAN 10 IP/Mask + Helpers | User VLAN gateway and DHCP helper addresses. |
| SVIs → VLAN 20 IP/Mask + Helpers | Voice VLAN gateway and DHCP helper addresses. |
| Routed Uplinks → IP/Mask | Per-uplink point-to-point /30 addresses to the upstream cores. |
| OSPF → Router ID | Replace `<LOOPBACK_IP>` with the same IP you used for Loopback0. |
| OSPF → Networks | Already includes Loopback0. Add user/voice subnets if you want them advertised. |
| Role Variables | Same NTP / SNMP / mgmt-ACL host placeholders as the L2 pack. |

**2. Base Settings find-and-replace.** Same as L2:

| Section | Replace |
|---|---|
| Logging | `<SYSLOG_IP_1>`, `<SYSLOG_IP_2>` |
| AAA | `<RADIUS_IP_1>`, `<RADIUS_IP_2>`, `<RADIUS_KEY_1>`, `<RADIUS_KEY_2>` |

Note: AAA / NTP / SNMP all use `Loopback0` as their source-interface,
so RADIUS, syslog, NTP, and SNMP must be reachable from the loopback
(your OSPF advertisements and core ACLs need to allow it).

**3. Generate Config (per-switch fields):**
- *Loopback0 IP* — same value you put in the profile's Loopback0 field
  (or override per switch).
- *Default Gateway* — disabled when `layer3=true`. OSPF or static
  routes provide the path of last resort instead.

### What's *not* in this pack

- **HSRP/VRRP** — the v1 SVIs are plain. If you have redundant L3
  switches sharing a VLAN gateway, add HSRP via base_settings or a
  custom section.
- **OSPF authentication** — bare OSPF, no MD5 / SHA auth. Add via
  base_settings or per-interface custom commands once a v2 schema
  exposes per-interface auth fields.
- **Static-route examples** — the profile ships an empty list. Use
  the *Static Routes* grid in the profile editor to add a fallback
  default or specific routes.

### Verifying the import

After importing, open *Generate Config*, pick the L3 example profile
and a 9300 model, fill in switch details (notice the *Loopback0 IP*
label and the disabled *Default Gateway* field), and click **Preview**.
Spot-check the new "L3 Interfaces" and "Routing" sections:

1. `ip routing` appears at the top of *L3 Interfaces*.
2. Loopback0 has the per-switch mgmt IP with a /32 mask.
3. SVIs render with `ip helper-address` for VLANs 10 and 20.
4. Routed uplinks have `no switchport`, `mtu 9100`, and
   `ip ospf 1 area 0`.
5. The disabled-port range starts at G1/0/3 (uplinks G1/0/1 and
   G1/0/2 are correctly excluded).
6. The *Routing* section contains `router ospf 1` with
   `passive-interface default` and `no passive-interface` exceptions
   for the two uplinks.
7. The *Management* section is empty (mgmt rides Loopback0, not an
   SVI + default-gateway).
