"""Port-group expansion and interface name helpers."""

import re


def expand_port_groups_for_stack(port_groups, stack_members):
    """Replicate port groups for each member of a switch stack.

    For a prefix like ``GigabitEthernet1/0/`` the leading switch number
    (the ``1`` before the first ``/``) is replaced with each member number
    (1 … *stack_members*).  If the prefix doesn't contain a ``/`` or the
    stack is size 1 the original groups are returned unchanged.

    If the port groups already contain entries for multiple stack members
    (member numbers > 1) they are returned as-is to avoid duplication.
    """
    if stack_members <= 1:
        return list(port_groups)

    # Check if port_groups already include entries for stack members > 1.
    # If so, they were defined explicitly and should not be expanded again.
    for pg in port_groups:
        m = re.match(r'^([A-Za-z-]*)(\d+)(/.*)$', pg["prefix"])
        if m and int(m.group(2)) > 1:
            return list(port_groups)

    expanded = []
    for pg in port_groups:
        prefix = pg["prefix"]
        # Match the switch number before the first slash
        m = re.match(r'^([A-Za-z-]*)(\d+)(/.*)$', prefix)
        if m:
            name_part, _orig_num, tail = m.group(1), m.group(2), m.group(3)
            for member in range(1, stack_members + 1):
                expanded.append({
                    "prefix": f"{name_part}{member}{tail}",
                    "start": pg["start"],
                    "end": pg["end"],
                })
        else:
            # Can't parse switch number - just include as-is
            expanded.append(pg)
    return expanded


def expand_range_iface(iface_str):
    """Expand 'range PrefixN-M' into individual port strings.

    Returns a list of individual interface strings.  If the input is not
    a range specification, the original string is returned in a one-element
    list so callers can always iterate the result.
    """
    s = iface_str.strip()
    if not s.lower().startswith("range "):
        return [s]
    rest = s[6:]                       # strip leading "range "
    m = re.match(r'^(.+?)(\d+)-(\d+)$', rest)
    if not m:
        return [s]
    prefix, start_s, end_s = m.group(1), m.group(2), m.group(3)
    return [f"{prefix}{i}" for i in range(int(start_s), int(end_s) + 1)]


def _canon_iface(s):
    s = (s or "").strip()
    if s[:6].lower() == "range ":
        s = "range " + s[6:].strip()
    return s
