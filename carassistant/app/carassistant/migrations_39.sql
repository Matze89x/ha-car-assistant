-- Equipment: the categories are a fixed set of twelve now; rows of the first version stored a (localized) name, from here on the key.
UPDATE equipment SET category = 'exterior' WHERE category IN ('Exterior', 'Außen');
UPDATE equipment SET category = 'interior' WHERE category IN ('Interior', 'Innenraum');
UPDATE equipment SET category = 'comfort'  WHERE category IN ('Comfort', 'Komfort');
UPDATE equipment SET category = 'lights'   WHERE category IN ('Lights', 'Licht');
UPDATE equipment SET category = 'assist'   WHERE category IN ('Safety & assistance', 'Sicherheit & Assistenz', 'safety');
UPDATE equipment SET category = 'media'    WHERE category IN ('Infotainment');
-- anything else goes to the first area
UPDATE equipment SET category = 'comfort' WHERE category NOT IN ('comfort', 'seats', 'controls', 'lights', 'packages', 'interior', 'wheels', 'tech', 'exterior', 'media', 'assist', 'roof');
