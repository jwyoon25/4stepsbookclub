# 4steps workbook operating runbook

This is the day-to-day workflow for creating a workbook from the protected
master Google Sheet and delivering its PDFs to Google Drive.

## Canonical workflow

```text
Make a copy → Set up workbook → Edit → Validate → Preview → Export
```

### 1. Make a copy

Open the protected master Sheet and choose **File → Make a copy**. Never edit
the master itself. The copy is the working file and becomes the source of truth
for that book.

The master is view-only/protected for normal collaborators. Keep the copy in
the intended Drive folder and give it a book-specific name.

### 2. Set up the workbook

In the copied Sheet, choose **4steps → Set up this workbook**.

The first run for a copied Apps Script project may show a Google permission
prompt. Approve it once for that copy. The setup must be launched from the
Sheet menu, not from the Apps Script editor; running `setupWorkbook` directly
in the editor cannot access the Sheet UI.

Wait for the **4steps workbook is ready** confirmation before continuing.

### 3. Edit

Edit the copy's workbook and content tabs:

- Keep the tab names and column headings unchanged.
- Enter one question, prompt, or vocabulary item per row.
- Keep response-space and teacher-guidance content within the visible rules on
  each tab.
- Do not edit the protected master as a shortcut.

### 4. Validate

Choose **4steps → Validate workbook**. In the validation dialog, click **Open
the workbook**. The preview window reads the live Sheet and reports whether the
workbook is valid.

Fix every tab/row/cell error before previewing. Keep the validation dialog open:
it is the bridge between the preview window and Google Sheets.

### 5. Preview

In the preview window:

1. Compile a student target and inspect the generated PDF.
2. Compile the corresponding teacher target and inspect it too.
3. For the complete edition, inspect both student and teacher targets when the
   book is ready for delivery.

The preview is the approval point. The system compiles the real PDF, not an
HTML mockup. Use **Refresh from the Sheet** after making edits.

### 6. Export

After the previews are approved, choose **Create all approved PDFs** in the
preview window. Leave the Sheet dialog open until the activity log confirms
that the files were saved.

Files are written to:

```text
<Sheet parent folder>/4steps PDF Builds/<book title>/<timestamp>/
```

The export produces two PDFs for each lesson (student and teacher) plus two
complete-workbook PDFs. In general, the expected count is:

```text
2 × (number of lessons + 1)
```

## Drive check

After export, open the folder named in the preview activity log and confirm:

- the timestamped build folder is inside the correct book folder;
- the expected number of PDFs is present;
- both editions exist for each lesson and for the complete workbook; and
- the files have non-zero sizes and the expected book title in their names.

## One-time authorization

Authorization is expected once per copied Apps Script project. If the first
menu click asks for approval, complete Google's review/allow flow and rerun the
Sheet menu item. A `Cannot call SpreadsheetApp.getUi() from this context` error
means the function was run from the Apps Script editor; return to the Sheet and
run it from **4steps** instead.

## Visibility and security

The preview host is public for the MVP. It serves the static compiler and UI;
live workbook data still travels through the authorized Apps Script bridge, and
the Sheet/Drive permissions control authoring and export. Cloudflare Access is
not required for the current workflow. Revisit it if the preview begins
containing private books, student data, or an internal-only teacher portal.

## Smoke-test checklist

Run this once for a new deployment or a meaningful workflow change:

- [ ] Create a genuinely fresh copy from the protected master.
- [ ] Set up the copy and complete any one-time authorization.
- [ ] Validate the live Sheet with no errors.
- [ ] Compile and inspect student preview.
- [ ] Compile and inspect teacher preview.
- [ ] Export the complete workbook.
- [ ] Verify the Drive folder, file names, count, and non-zero sizes.

The fresh-copy path was verified on 2026-08-20: a one-lesson workbook passed
setup, validation, student and teacher compilation, and a four-PDF Drive export
with zero compiler diagnostics.
