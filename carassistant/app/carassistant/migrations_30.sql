-- Plugins with their own service (pluginsvc.py): the package the service comes from, the approval and the last state.
ALTER TABLE vehicle_addons ADD COLUMN pkg_sha TEXT;        -- sha256 of the package zip that was fetched and unpacked
ALTER TABLE vehicle_addons ADD COLUMN svc_ok TEXT;         -- fingerprint of the service description an admin approved (empty = never started)
ALTER TABLE vehicle_addons ADD COLUMN svc_error TEXT;      -- last problem, shown on the plugin card
ALTER TABLE vehicle_addons ADD COLUMN svc_started TEXT;    -- when the service was last started
