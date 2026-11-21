# Manual package

🇬🇧 English · [🇩🇪 Deutsch](manual-package.de.md)

Besides PDF, EPUB and text files, the manual of a car can be imported as a **package**: a zip file with page images, so the pages look like the printed book. *Manual → Import manual* (or *Import again*) accepts it like any other file.

## Simplest form

A zip that holds **only numbered page images** is enough: `001.avif`, `002.avif`, ... at the top level, in one folder or in `p/`. The title is taken from the file name, the page offset is 0, and there is one chapter. Add `meta.json` and `index.json.gz` later for chapters, the offset and search.

## Full layout

The zip may hold everything at its top level or inside one folder:

| File | Meaning |
|---|---|
| `meta.json` | optional (without it: title from the file name, offset 0, one chapter): `title`, `pages` (number of pages), `offset` (printed page number + offset = page of the file; the cover and front matter come first), `chapters` |
| `p/001.avif` ... | required (in `p/` or, in the simple form, next to the other files): the page images, one per page (AVIF, JPEG, PNG or WebP, up to 8 MB each; the type is recognised from the file, not from its name) |
| `t/003.json.gz` ... | optional, one per page that has references: `{"x": [[137, 120, 300, 380, 330], ...]}` - each entry is `[printed page, left, top, right, bottom]` of a reference such as "page 137" on the image, the four values in **thousandths** of the image width and height (0-1000). The reader lays a tappable area over it: faintly red always, strongly on hover, a tap jumps to that page (printed page + offset). Other keys in the file are ignored. |
| `index.json.gz` | optional: a gzip-compressed list `[{"p": 1, "t": "text of page 1"}, ...]` - the text of each page, used for the search and the *Text* view |

`chapters` is a tree: `[{"t": "Title", "p": 10, "g": "Part", "c": [{"t": "Section", "p": 12}]}]` - `p` is the page of the file, `g` (optional, top level only) the part the chapter belongs to, `c` the sections below it. Page references in the text ("page 137") name the **printed** page, so the app adds the `offset` to jump to the right image.

At most 3000 pages and 400 MB (unpacked).

## How it is kept

Text, chapters and the offset are in the database; the images are files in the car's own data folder. Images are only handed out to signed-in people. Both backups carry them: the [vehicle backup](backup.md) and the system backup. Nothing is sent anywhere. Manuals are usually protected by copyright: import only what you may use, and keep the package private.

In the reader, *Page image* and *Text* switch the view (the choice is remembered per person). Search hits are marked in the text.
