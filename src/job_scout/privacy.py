"""Privacy controls for uploaded resume files and transient resume text."""

from __future__ import annotations

import tempfile
from pathlib import Path


def delete_temporary_upload(path: str | Path) -> bool:
    """Delete a UI upload only when it is inside the operating-system temp tree.

    Gradio copies uploads into its temporary directory before invoking the
    callback. The boundary check prevents this helper from deleting a user's
    original CV when a caller supplies an arbitrary path.
    """
    candidate = Path(path).resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    if candidate == temp_root or not candidate.is_relative_to(temp_root):
        return False
    try:
        candidate.unlink(missing_ok=True)
    except OSError:
        return False
    return not candidate.exists()
