"""Units and currency: everything is stored in base units (km, litres, bar, °C, a plain number for money) and only *shown* in the
units chosen in Settings -> Region. That choice belongs to the server (one for the whole app)."""

from __future__ import annotations

from dataclasses import dataclass

from . import config, ha

SYSTEMS = ("metric", "us", "uk")
DEFAULT_SYSTEM = "metric"
KM_TO_MI = 0.621371
L_TO_US_GAL = 0.264172
L_TO_UK_GAL = 0.219969
BAR_TO_PSI = 14.5038

# code, symbol, symbol is written after the number (in most of continental Europe)
CURRENCIES: tuple[tuple[str, str, bool], ...] = (
    ("EUR", "€", True),
    ("USD", "$", False),
    ("GBP", "£", False),
    ("CHF", "CHF", True),
    ("PLN", "zł", True),
    ("CZK", "Kč", True),
    ("SEK", "kr", True),
    ("NOK", "kr", True),
    ("DKK", "kr", True),
    ("HUF", "Ft", True),
    ("RON", "lei", True),
    ("TRY", "₺", False),
    ("CAD", "$", False),
    ("AUD", "$", False),
    ("NZD", "$", False),
    ("JPY", "¥", False),
)
CURRENCY = {c: (sym, after) for c, sym, after in CURRENCIES}


@dataclass(frozen=True)
class Units:
    system: str
    currency: str

    @property
    def imperial(self) -> bool:
        return self.system in ("us", "uk")

    # ---- distance and speed
    @property
    def dist_unit(self) -> str:
        return "mi" if self.imperial else "km"

    def d(self, km):
        """km -> the unit shown."""
        return None if km is None else km * (KM_TO_MI if self.imperial else 1)

    def from_d(self, value):
        """The unit shown -> km (for input fields)."""
        return None if value is None else value / (KM_TO_MI if self.imperial else 1)

    def dist_str(self, km) -> str:
        """A distance for a sentence: '1,234 mi'."""
        return f"{round(self.d(km)):,} {self.dist_unit}"

    @property
    def speed_unit(self) -> str:
        return "mph" if self.imperial else "km/h"

    # ---- volume and consumption
    def vol_unit(self, base: str = "L") -> str:
        """``base`` is the energy unit of the vehicle (L, kWh, kg): only litres change."""
        if base != "L":
            return base
        return {"us": "gal", "uk": "gal"}.get(self.system, "L")

    def v(self, litres, base: str = "L"):
        if litres is None or base != "L":
            return litres
        return litres * {"us": L_TO_US_GAL, "uk": L_TO_UK_GAL}.get(self.system, 1)

    def _vol_factor(self, base: str = "L") -> float:
        return 1.0 if base != "L" else {"us": L_TO_US_GAL, "uk": L_TO_UK_GAL}.get(self.system, 1.0)

    def from_v(self, value, base: str = "L"):
        """The volume shown -> litres (for input fields)."""
        return None if value is None else value / self._vol_factor(base)

    def price_vol(self, per_litre, base: str = "L"):
        """Price per litre -> price per shown unit (per gallon)."""
        return None if per_litre is None else per_litre / self._vol_factor(base)

    def from_price_vol(self, shown, base: str = "L"):
        """Price per shown unit -> price per litre."""
        return None if shown is None else shown * self._vol_factor(base)

    def consumption_unit(self, base: str = "L") -> str:
        if base != "L":  # electric / gas: per 100 distance units
            return f"{base}/100 {self.dist_unit}"
        return {"us": "mpg", "uk": "mpg"}.get(self.system, "L/100 km")

    def c(self, per_100_km, base: str = "L"):
        """Consumption per 100 km -> shown value (mpg is the other way round: distance per volume)."""
        if per_100_km is None:
            return None
        if base != "L":
            return per_100_km / KM_TO_MI if self.imperial else per_100_km
        if self.system == "metric" or per_100_km <= 0:
            return per_100_km
        gal = L_TO_US_GAL if self.system == "us" else L_TO_UK_GAL
        return (100 * KM_TO_MI) / (per_100_km * gal)

    # ---- temperature, pressure
    @property
    def temp_unit(self) -> str:
        return "°F" if self.system == "us" else "°C"

    def t(self, celsius):
        return None if celsius is None else (celsius * 9 / 5 + 32 if self.system == "us" else celsius)

    @property
    def press_unit(self) -> str:
        return "psi" if self.imperial else "bar"

    def p(self, bar):
        return None if bar is None else bar * (BAR_TO_PSI if self.imperial else 1)

    def from_p(self, shown):
        """A pressure typed in the shown unit -> bar."""
        return None if shown is None else shown / (BAR_TO_PSI if self.imperial else 1)

    # ---- money
    @property
    def cur(self) -> str:
        return CURRENCY.get(self.currency, (self.currency, True))[0]

    def money_unit(self, base: str = "L") -> str:
        """e.g. "€/L"."""
        return f"{self.cur}/{self.vol_unit(base)}"


def default_currency() -> str:
    code = (config.stored_setting("region.currency") or (ha.currency() if ha.available() else "") or "EUR").upper()
    return code if code in CURRENCY else "EUR"


def default_system() -> str:
    value = config.stored_setting("region.units") or DEFAULT_SYSTEM
    return value if value in SYSTEMS else DEFAULT_SYSTEM


def of(vehicle=None) -> Units:
    """The units shown. They are SERVER settings (Settings -> Region): one choice for the whole app, not per user and not per vehicle.
    The argument is only kept so templates can pass the vehicle they are showing."""
    return Units(default_system(), default_currency())
