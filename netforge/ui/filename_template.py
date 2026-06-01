"""Filename template expansion for saved configs."""

import re
from datetime import date


def apply_filename_template(template, *, hostname="", model="", profile="",
                            work_order=""):
    """Expand {{ var }} placeholders in a filename template.

    Supported variables: hostname, model, profile, date (YYYY-MM-DD),
    work_order.
    Returns a sanitized string safe for use as a file name.
    """
    today = date.today().strftime("%Y-%m-%d")
    subs = {"hostname": hostname, "model": model,
            "profile": profile, "date": today,
            "work_order": work_order}
    result = template
    for key, val in subs.items():
        result = result.replace("{{ " + key + " }}", val)
        result = result.replace("{{" + key + "}}", val)
    # remove characters invalid in file names on Windows and Unix
    result = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", result).strip()
    return result or "config"
