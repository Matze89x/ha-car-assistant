# Golden backup files

One pair per backup format that ever existed: `vehicle-format<N>.zip` (a backup of one car), `system-format<N>.zip` (the whole system) and
`expected-format<N>.json` (what a restore of them has to bring back). Everything in them is made up (`tools/demo_data.py`).

**Rules**
- A golden file is made **once**, by the code of its own format, and is **never edited or made again**. It stands for a backup that a person may
  still have in a drawer.
- `tests/test_backup_compat.py` restores every one of them with the current code. When a backup format changes (`FORMAT` in `vehiclebackup.py` /
  `backup.py`), the new golden files are added **first**; the test `test_every_format_has_its_golden_file` fails until they are.
- A restore of an old file may add things the old format did not know (a default), never lose what it had.

Format 1 was made with Car Assistant 0.5.36 (system schema 61). Format 2 (0.5.37): secrets travel in one block encrypted with a passphrase,
more tables of a car are part of the backup, installed packages remember their source.
