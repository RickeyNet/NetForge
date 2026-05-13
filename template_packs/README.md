# Template Packs

Importable settings bundles that pre-populate NetForge with a working baseline.
Use **Settings -> Import Settings** and select one of the `.zip` files in this
directory. Importing **overwrites** your current `models.json`, `roles.json`,
`profiles.json`, and `base_settings.json` - export your existing settings
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
- Global Services - `no service config/finger/pad/call-home`,
  `service password-encryption`, UDLD, errdisable recovery, `no cdp run`,
  HTTP server disabled, login block, etc.
- Logging - syslog hosts, login on-success/failure, archive log config.
- AAA - `aaa new-model`, common-criteria `PASSWORD_POLICY`, two RADIUS
  servers + `RADIUS_GROUP`, `ip radius source-interface vlan <MGMT_VLAN>`.
- Security - `spanning-tree mode rapid-pvst`, loopguard, extend system-id.
- SSH - version 2, modulus 2048, AES256-GCM/CTR, HMAC-SHA2-512/256.
- Switching - `vtp mode off`, transceiver monitoring, diagnostic boot level,
  punt-keepalive.
- Line Configuration - VTY 0-4 with `SWITCH_MGMT` ACL, VTY 5-98 disabled,
  console session-timeout/exec-timeout.
- Banner - placeholder warning banner.
- Disabled-port template - full hardened L2 disabled access port
  (port-security, BPDU guard, root guard, storm-control, shutdown).

**Custom Sections:**
- *Switch Management ACL* (pre-interface) - `SWITCH_MGMT` extended ACL with
  10 host slots referenced by `line vty`.
- *DHCP and IGMP Snooping* (pre-interface) - `no ip igmp snooping`,
  `ip dhcp snooping`, snooping VLAN list.
- *NTP* (post-interface) - authenticated NTP, two servers, UTC timezone.
- *SNMPv3* (post-interface) - view/group/user/host with SHA-2 auth and
  AES-256 priv.

**Roles (`roles.json`):**
- `L2 Access (Hardened)` - hardened access port with port-security,
  BPDU guard, root guard, storm-control.
- `L2 Trunk (Hardened)` - hardened trunk with native-VLAN pinning,
  pruned VLAN 1, root guard, storm-control.
- `L2 Trunk + DHCP Snooping Trust (Hardened)` - same as above plus
  `ip dhcp snooping trust`. Use only on uplinks where DHCP traffic
  must be trusted.
- Existing pre-loaded roles (Access Port, Trunk Uplink to Switch/Firewall,
  Private VLAN Promiscuous/Isolated) are preserved.

**Profile:** `Cisco L2 Baseline (example)` - pre-fills every role variable
the custom sections expect, using `<PLACEHOLDER>` markers you replace per
site (NTP, SNMP, ACL hosts).

**Models:** Unchanged from NetForge defaults.

### What you need to fill in per site

Two kinds of placeholders to replace, because NetForge only Jinja-renders
custom sections, roles, and the disabled-port template - the global
text-areas (AAA, Logging, etc.) are pasted as-is.

**1. Profile role variables (Jinja).** Open
*Site Profiles -> Cisco L2 Baseline (example) -> Role Variables* and replace
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
native blackhole, and VLAN 67 as the disabled-port blackhole - adjust
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

The pack splits config along two seams:

- **Site profile** owns site-wide things - VLAN definitions, SVI
  gateway IPs (shared across all switches at the site), OSPF
  process settings, port-to-role mappings.
- **Generate Config Step 3** owns per-switch things - Loopback0 IP,
  routed-uplink IPs, OSPF router-id (defaults to Loopback0), static
  routes.

### What's covered

**Base Settings text-areas** - same hardened policies as the L2 pack
(global services, AAA with `ip radius source-interface Loopback0`,
logging, SSH, line config, banner, custom sections), plus L3 globals:
- *Switching* - adds `ip cef`, `ipv6 unicast-routing`, `ipv6 cef`.
- *NTP / SNMP* - both source-interface Loopback0 (so the loopback IP
  is the consistent source for management traffic).

**Custom Sections** - same four as L2 (`SWITCH_MGMT` ACL, DHCP/IGMP
snooping, NTP, SNMPv3). The DHCP-snooping VLAN list is widened to
`10,20` (data + voice).

**Roles** - same hardened L2 roles as the L2 pack, plus one new role:
- `L3 Routed Uplink (Hardened)` - has `requires_ip: true`, so when
  you assign a port to it, Generate Config Step 3 prompts for the
  IP/mask. Hardened command set: `no switchport`, `mtu 9100`,
  `ip address {{ ip }} {{ mask }}`,
  `ip ospf {{ ospf_pid }} area 0`, `ip ospf network point-to-point`,
  `no ip redirects`, `no ip proxy-arp`, `no shutdown`.

**Profile** - `Cisco L3 Baseline (example)` with `layer3=true`,
`mgmt_style=loopback`, and:
- VLAN definitions for VLANs 3, 10, 20, 66 (native blackhole),
  67 (disabled).
- Two SVIs - VLAN 10 (USER_DATA) and VLAN 20 (VOICE), each with
  helper-address placeholders. SVI gateway IPs are profile-level
  because they're the same on every switch at the site.
- Port assignments - G1/0/1 -> "L3 Routed Uplink (Hardened)" (CORE-A),
  G1/0/2 -> "L3 Routed Uplink (Hardened)" (CORE-B). Per-switch IPs
  for these are entered in Generate Config.
- OSPF process 1, `passive-interface default` with the two uplinks
  marked active. `networks` is empty by default - add per-site
  network statements, or rely on per-interface `ip ospf 1 area 0`
  on the uplinks (already in the role) to bring up adjacencies.

**Models** - unchanged from NetForge defaults.

### What you fill in: profile vs. per-switch

**1. Profile fields (Site Profiles -> Cisco L3 Baseline (example)) - site-wide:**

| Field | What it is |
|---|---|
| SVIs -> VLAN 10 IP/Mask + Helpers | User VLAN gateway IP and DHCP helper addresses (same on every switch at the site). |
| SVIs -> VLAN 20 IP/Mask + Helpers | Voice VLAN gateway IP and DHCP helper addresses. |
| OSPF -> Networks (optional) | Add `network` statements if you prefer them over the per-interface `ip ospf` already in the L3 role. |
| Role Variables | NTP / SNMP / mgmt-ACL host placeholders (same as the L2 pack). |

**2. Base Settings find-and-replace** - same as L2:

| Section | Replace |
|---|---|
| Logging | `<SYSLOG_IP_1>`, `<SYSLOG_IP_2>` |
| AAA | `<RADIUS_IP_1>`, `<RADIUS_IP_2>`, `<RADIUS_KEY_1>`, `<RADIUS_KEY_2>` |

Note: AAA / NTP / SNMP all use `Loopback0` as their source-interface,
so RADIUS, syslog, NTP, and SNMP must be reachable from the loopback
(your OSPF advertisements and core ACLs need to allow it).

**3. Generate Config Step 3 - per-switch:**

| Field | What it is |
|---|---|
| Loopback0 -> IP | This switch's loopback. Used by mgmt traffic and OSPF router-id. |
| Loopback0 -> Mask | Default `255.255.255.255`. |
| OSPF -> Router ID | Optional. Defaults to the Loopback0 IP. |
| Routed Interface IPs | Auto-populated grid: one row per port assigned to an L3 role in Step 2. Fill in IP and mask for each uplink. |
| Static Routes | Optional. Add a fallback default or specific routes here. |
| Default Gateway | Disabled in this pack (`mgmt_style=loopback`) - mgmt traffic rides Loopback0, not a default-gateway. |

### What's *not* in this pack

- **HSRP/VRRP** - the v1 SVIs are plain. If you have redundant L3
  switches sharing a VLAN gateway, add HSRP via base_settings or a
  custom section.
- **OSPF authentication** - bare OSPF, no MD5 / SHA auth. Add via
  base_settings or per-interface custom commands once a v2 schema
  exposes per-interface auth fields.
- **OSPF network statements for SVIs/Loopback0** - networks list is
  empty by default. The role-based per-interface `ip ospf 1 area 0`
  on the uplinks brings up neighbor adjacencies, but you'll need
  network statements (or `ip ospf 1 area 0` on each SVI/Loopback0)
  if you want LSAs for the user/voice/loopback subnets. Easiest:
  add `network <subnet> <wildcard> area 0` lines to the profile's
  OSPF Networks grid.

### Verifying the import

After importing, open *Generate Config*, pick the L3 example profile
and a 9300 model. In Step 2, leave the seeded port assignments alone
(G1/0/1 and G1/0/2 should already be set to "L3 Routed Uplink
(Hardened)"). Move to Step 3 - the *Layer 3 Details* section should
appear, with a *Routed Interface IPs* grid pre-populated with rows
for G1/0/1 and G1/0/2.

Fill in: hostname, secret, admin password, domain, Loopback0 IP,
and uplink IPs. Click **Preview**. Spot-check:

1. `ip routing` appears at the top of *L3 Interfaces*.
2. Loopback0 has the per-switch IP with a /32 mask.
3. SVIs render with `ip helper-address` for VLANs 10 and 20.
4. The two routed uplinks appear in the *Interfaces* section
   (not L3 Interfaces) with `no switchport`, `mtu 9100`,
   `ip ospf 1 area 0`, `ip ospf network point-to-point`,
   `no ip redirects`, `no ip proxy-arp`, and the per-switch IP.
5. The disabled-port range starts at G1/0/3 (uplinks G1/0/1 and
   G1/0/2 are correctly excluded).
6. The *Routing* section contains `router ospf 1` with
   `passive-interface default` and `no passive-interface` exceptions
   for the two uplinks. `router-id` matches the Loopback0 IP you
   entered.
7. The *Management* section is empty (mgmt rides Loopback0, not an
   SVI + default-gateway).
