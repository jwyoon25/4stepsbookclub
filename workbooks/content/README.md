# Content

Production book- and lesson-specific curriculum data belongs here. Each workbook
uses one directory containing a `workbook.json` manifest and one JSON file per
lesson:

```text
content/
└── the-book-id/
    ├── workbook.json
    └── lessons/
        ├── lesson-01.json
        └── lesson-02.json
```

The versioned definitions, field documentation, defaults, and a valid example
are in [`../schema/`](../schema/README.md). No production curriculum has been
added yet.
