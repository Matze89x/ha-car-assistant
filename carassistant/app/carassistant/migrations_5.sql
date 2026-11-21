-- Vehicle data page: technical details and papers. All optional, brand-neutral.
ALTER TABLE vehicles ADD COLUMN build_date TEXT;          -- YYYY-MM-DD (manufacturing date)
ALTER TABLE vehicles ADD COLUMN model_type TEXT;          -- type / generation code
ALTER TABLE vehicles ADD COLUMN engine TEXT;              -- engine designation
ALTER TABLE vehicles ADD COLUMN power_kw INTEGER;
ALTER TABLE vehicles ADD COLUMN displacement_ccm INTEGER;
ALTER TABLE vehicles ADD COLUMN drivetrain TEXT;          -- fwd | rwd | awd
ALTER TABLE vehicles ADD COLUMN transmission TEXT;        -- manual | automatic | dct | cvt
ALTER TABLE vehicles ADD COLUMN body_type TEXT;           -- sedan | wagon | hatchback | suv | coupe | convertible | van | pickup
ALTER TABLE vehicles ADD COLUMN engine_code TEXT;
ALTER TABLE vehicles ADD COLUMN gearbox_code TEXT;
ALTER TABLE vehicles ADD COLUMN battery TEXT;             -- free text: type, Ah, fitted date
ALTER TABLE vehicles ADD COLUMN paint_code TEXT;
ALTER TABLE vehicles ADD COLUMN hsn TEXT;                 -- registration codes (DE: HSN / TSN)
ALTER TABLE vehicles ADD COLUMN tsn TEXT;
ALTER TABLE vehicles ADD COLUMN key_numbers TEXT;
ALTER TABLE vehicles ADD COLUMN parts_note TEXT;          -- bulbs, part numbers, ...
