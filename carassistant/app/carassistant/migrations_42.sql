-- Designs: Classic red stays; the others became "dark / light / day-night + your colour". Stored choices move to the nearest one
-- (and the colour they had, so nothing changes its look).
INSERT OR IGNORE INTO settings(key, value)
  SELECT 'ui.accent', CASE value WHEN 'sunset' THEN '#ff7a1a' WHEN 'frost' THEN '#1f6fe5' WHEN 'ocean' THEN '#2f8cff' ELSE '#e2001a' END
  FROM settings WHERE key = 'ui.theme' AND value IN ('light', 'frost', 'auto', 'ocean', 'sunset');
UPDATE settings SET value = CASE value WHEN 'light' THEN 'custom-light' WHEN 'frost' THEN 'custom-light' WHEN 'auto' THEN 'custom-auto' ELSE 'custom-dark' END
  WHERE key = 'ui.theme' AND value IN ('light', 'frost', 'auto', 'ocean', 'sunset');
UPDATE vehicles SET theme = CASE theme WHEN 'light' THEN 'custom-light' WHEN 'frost' THEN 'custom-light' WHEN 'auto' THEN 'custom-auto' ELSE 'custom-dark' END
  WHERE theme IN ('light', 'frost', 'auto', 'ocean', 'sunset');
UPDATE user_prefs SET value = CASE value WHEN 'light' THEN 'custom-light' WHEN 'frost' THEN 'custom-light' WHEN 'auto' THEN 'custom-auto' ELSE 'custom-dark' END
  WHERE key = 'design' AND value IN ('light', 'frost', 'auto', 'ocean', 'sunset');
