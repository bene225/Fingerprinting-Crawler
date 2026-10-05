import subprocess
from pathlib import Path



# Region Version
tr_date = "2026.09.21"
tr_folder = Path("utils/trackerradar/data")

# Prüfen ob alles für TrackerRadar isntalliert
def check_tracker_radar() -> None:
    if (tr_folder / "domains").exists():
        return
    # Nur Ordnerstruktur
    subprocess.run(["git", "clone", "--depth", "1", "--branch", tr_date, "--filter=blob:none", "--sparse",
                    "https://github.com/duckduckgo/tracker-radar.git", str(tr_folder)], check=True)
    # Nur domains ordner
    subprocess.run(["git", "-C", str(tr_folder), "sparse-checkout", "set", "domains"], check=True)


if __name__ == "__main__":
    check_tracker_radar()
