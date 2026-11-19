"""One-shot Windows Location Service access through the installed .NET Framework."""
import base64
import json
import math
import os
import subprocess
from pathlib import Path


class LocationError(RuntimeError):
    pass


# No IP-based fallback: it can place the user at an ISP gateway in another city.
LOCATION_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$watcher = $null
try {
    Add-Type -AssemblyName System.Device
    $watcher = New-Object System.Device.Location.GeoCoordinateWatcher
    $watcher.Start()
    $deadline = [DateTime]::UtcNow.AddSeconds(25)
    do {
        if ($watcher.Permission -eq 'Denied') {
            @{ error = 'denied' } | ConvertTo-Json -Compress
            exit 0
        }
        $position = $watcher.Position
        if (-not $position.Location.IsUnknown -and
            $position.Timestamp.UtcDateTime -gt [DateTime]::UtcNow.AddMinutes(-2)) {
            $point = $position.Location
            $accuracy = $null
            if (-not [double]::IsNaN($point.HorizontalAccuracy) -and
                -not [double]::IsInfinity($point.HorizontalAccuracy)) {
                $accuracy = $point.HorizontalAccuracy
            }
            @{ lat = $point.Latitude; lon = $point.Longitude; accuracy = $accuracy } |
                ConvertTo-Json -Compress
            exit 0
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)
    @{ error = 'unavailable' } | ConvertTo-Json -Compress
} catch {
    @{ error = 'service' } | ConvertTo-Json -Compress
} finally {
    if ($null -ne $watcher) { $watcher.Dispose() }
}
"""


def detect_location():
    if os.name != "nt":
        raise LocationError("Automatické zjištění polohy je dostupné ve Windows. Zadej město nebo adresu ručně.")
    shell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    command = base64.b64encode(LOCATION_SCRIPT.encode("utf-16-le")).decode("ascii")
    try:
        result = subprocess.run([str(shell), "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", command],
                                capture_output=True, timeout=35, creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired as exc:
        raise LocationError("Zjišťování polohy trvalo příliš dlouho. Zkus to znovu nebo zadej polohu ručně.") from exc
    except OSError as exc:
        raise LocationError("Službu polohy Windows se nepodařilo spustit. Zadej polohu ručně.") from exc
    try:
        data = json.loads(result.stdout.decode("utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("Invalid response")
    except (ValueError, UnicodeError) as exc:
        raise LocationError("Windows nevrátil platnou polohu. Zkus to znovu nebo zadej adresu ručně.") from exc
    if data.get("error") == "denied":
        raise LocationError("Přístup k poloze je zakázaný. V Nastavení polohy Windows povol služby určování polohy "
                            "a přístup aplikací k poloze. Potom klikni znovu na Použít moji polohu.")
    if data.get("error") or result.returncode:
        raise LocationError("Windows zatím nedokáže zjistit polohu zařízení. V Nastavení polohy zkontroluj služby "
                            "určování polohy a přístup aplikací k poloze. Potom to zkus znovu, případně zadej adresu ručně.")
    try:
        lat, lon = float(data["lat"]), float(data["lon"])
        if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Invalid coordinates")
    except (KeyError, TypeError, ValueError) as exc:
        raise LocationError("Windows vrátil neplatné souřadnice. Zadej polohu ručně.") from exc
    accuracy = data.get("accuracy")
    if not isinstance(accuracy, (int, float)) or not math.isfinite(accuracy) or accuracy < 0:
        accuracy = None
    return {"label": f"Moje poloha · {lat:.5f}, {lon:.5f}", "lat": lat, "lon": lon,
            "accuracy": accuracy}
