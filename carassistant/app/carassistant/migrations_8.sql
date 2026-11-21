-- Battery capacity (kWh) of electric and hybrid vehicles, separate from the fuel tank size.
ALTER TABLE vehicles ADD COLUMN battery_kwh REAL;
