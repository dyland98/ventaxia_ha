"""Check fork packaging and version consistency, without publishing anything."""

import argparse
import json
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]
FORK = "https://github.com/dyland98/ventaxia_ha"


def check(tag=None):
    integration = ROOT / "custom_components" / "ventaxia_ha"
    manifest = json.loads((integration / "manifest.json").read_text())
    hacs = json.loads((ROOT / "hacs.json").read_text())
    project = tomllib.loads((integration / "pyproject.toml").read_text())["project"]
    version = manifest["version"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), "Use a stable x.y.z version"
    assert manifest["domain"] == integration.name == "ventaxia_ha"
    assert project["version"] == version, "pyproject and manifest versions differ"
    assert project["dependencies"] == manifest["requirements"]
    assert manifest["documentation"] == FORK
    assert manifest["issue_tracker"] == FORK + "/issues"
    assert not hacs.get("zip_release"), "This fork uses repository source releases"
    assert not hacs.get("content_in_root"), "Integration lives in custom_components"
    assert hacs["homeassistant"] == "2026.10.0"
    assert (integration / "config_flow.py").is_file()
    for language in ("en", "fr"):
        json.loads((integration / "translations" / f"{language}.json").read_text())
    if tag:
        assert tag == f"v{version}", f"Tag must be v{version}"
    print(f"Local packaging checks passed: {version}; no HACS installation tested")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag")
    check(parser.parse_args().tag)
