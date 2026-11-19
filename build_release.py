"""Run with .venv-build/Scripts/python.exe build_release.py on Windows x64."""
import hashlib
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = "1.1.0"
NAME = f"FuelRadar-{VERSION}-windows-x64"


def build_icon(path):
    size = 64
    pixels = bytearray()
    for y in reversed(range(size)):
        for x in range(size):
            dx, dy = x - 32, y - 32
            r = dx * dx + dy * dy
            radar = 690 <= r <= 790 or 165 <= r <= 210 or r <= 18 or (dx >= 0 and dy <= 0 and abs(dx + dy) <= 2)
            red, green, blue = (100, 216, 172) if radar else (17, 43, 50)
            pixels.extend((blue, green, red, 255))
    dib = struct.pack("<IIIHHIIIIII", 40, size, size * 2, 1, 32, 0, len(pixels), 0, 0, 0, 0)
    image = dib + pixels + bytes(size * ((size + 31) // 32) * 4)
    header = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(image), 22)
    path.write_bytes(header + image)


def main():
    if sys.platform != "win32" or struct.calcsize("P") != 8:
        raise SystemExit("Build requires 64-bit Python on Windows.")
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "FuelRadar", "-v"], cwd=ROOT, check=True)
    work = ROOT / "build" / "release"
    work.mkdir(parents=True, exist_ok=True)
    icon = work / "fuelradar.ico"
    build_icon(icon)
    output = ROOT / "release" / NAME
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
                    "--noupx", "--name", "FuelRadar", "--icon", str(icon),
                    "--distpath", str(output), "--workpath", str(work / "pyinstaller"),
                    "--specpath", str(work), str(ROOT / "FuelRadar" / "main.py")], cwd=ROOT, check=True)
    shutil.copy2(ROOT / "LICENSE", output / "LICENSE.txt")
    shutil.copy2(ROOT / "FuelRadar" / "README.md", output / "README.md")
    (output / "START.txt").write_text(
        "Fuel Radar " + VERSION + " / Windows x64\n\n"
        "Spust FuelRadar.exe. Python ani instalace nejsou potreba.\n"
        "Pro online hledani a navigaci je potreba internet.\n"
        "Data: %LOCALAPPDATA%\\FuelRadar\\fuel_radar.db\n"
        "Navigace: zadej vychozi adresu, vyber stanici a klikni Navigovat.\n",
        encoding="utf-8")
    archive = Path(shutil.make_archive(str(ROOT / "release" / NAME), "zip", root_dir=output.parent, base_dir=output.name))
    files = (output / "FuelRadar.exe", archive)
    checksums = "".join(hashlib.sha256(p.read_bytes()).hexdigest() + "  " + str(p.relative_to(ROOT / "release")) + "\n" for p in files)
    (ROOT / "release" / "SHA256SUMS.txt").write_text(checksums, encoding="ascii")
    print("Release: " + str(output / "FuelRadar.exe"))
    print("ZIP: " + str(archive))


if __name__ == "__main__":
    main()
