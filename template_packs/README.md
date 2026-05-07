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
| `cisco_l3_baseline.zip` | Cisco 9300 IOS XE hardened baseline (L3 Switch) | Pending Phase 2 |

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
  belong in the upcoming `cisco_l3_baseline.zip` pack, which depends
  on the Phase 2 `layer3` profile flag.
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
