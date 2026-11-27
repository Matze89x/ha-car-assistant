-- Invoices: a document of the category "invoice" is read (the text of a PDF, or text recognition of a photo) and can be booked as a cost.
-- Nothing is stored per invoice but the document itself and what the reading found; the booking is a link to the entry it created.
ALTER TABLE documents ADD COLUMN amount REAL;          -- the total (gross) of the invoice, as read
ALTER TABLE documents ADD COLUMN extract TEXT;         -- what the reading found, as JSON (vendor, number, kind, ...); empty = not read yet
ALTER TABLE documents ADD COLUMN sha256 TEXT;          -- of the file: the same file twice is noticed
ALTER TABLE documents ADD COLUMN booked_table TEXT;    -- the entry the invoice was booked as: service | mods | parts | fixed_costs | fuel
ALTER TABLE documents ADD COLUMN booked_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_documents_booked ON documents(vehicle_id, booked_table, booked_id);
