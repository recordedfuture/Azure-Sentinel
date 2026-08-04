"""
Shared patcher utility for RF E2E test suites.
"""
import json
import tempfile


def write_temp(template: dict, prefix: str = "rf-test-") -> str:
    """
    Serialise *template* to a named temp file and return its path.
    The caller is responsible for deleting the file after use.
    """
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, prefix=prefix)
    json.dump(template, f, indent=2)
    f.close()
    return f.name
