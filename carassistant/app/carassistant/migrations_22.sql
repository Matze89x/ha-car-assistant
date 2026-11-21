-- A source is one source for Integrations and Plugins alike: every existing source goes into both lists.
UPDATE sources SET for_integration = 1, for_plugin = 1;
