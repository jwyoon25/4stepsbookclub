// ---------------------------------------------------------------------------
// What can be previewed or exported, and what gets handed to the compiler.
//
// A workbook produces one PDF per lesson and one for the whole book, in a
// student and a teacher edition each. That list is the same whether an author
// is choosing something to look at in the preview or a build is writing every
// approved file, so it is described once, here, and the bundle it produces is
// the same `schemaVersion: 1` shape the native renderer reads.
// ---------------------------------------------------------------------------

export const EDITIONS = Object.freeze(["student", "teacher"]);

function twoDigits(lessonNumber) {
  return String(lessonNumber).padStart(2, "0");
}

/**
 * Every target a workbook offers, lessons first.
 *
 * An author is usually looking at the lesson they are editing, so the complete
 * workbook sits at the end rather than the top.
 */
export function listWorkbookTargets(lessons) {
  const targets = lessons.flatMap((lesson) =>
    EDITIONS.map((edition) => ({
      id: `lesson-${twoDigits(lesson.lessonNumber)}-${edition}`,
      label: `Lesson ${lesson.lessonNumber} · ${edition}`,
      scope: "lesson",
      edition,
      lessonNumbers: [lesson.lessonNumber],
    })),
  );

  return [
    ...targets,
    ...EDITIONS.map((edition) => ({
      id: `workbook-${edition}`,
      label: `Complete workbook · ${edition}`,
      scope: "workbook",
      edition,
      lessonNumbers: lessons.map(({ lessonNumber }) => lessonNumber),
    })),
  ];
}

/**
 * What one target's PDF is called.
 *
 * `lib/build.mjs` names the files the native renderer writes to disk, and the
 * Drive export writes the same set from the browser. An author comparing a
 * folder built one way with a folder built the other has to be looking at the
 * same file names, so the target ids above are the only thing that decides
 * them.
 */
export function workbookPdfName(workbookId, target) {
  return `${workbookId}-${target.id}.pdf`;
}

/** Assemble the normalized bundle the Typst renderer compiles. */
export function createBuildBundle(manifest, lessons, { scope, edition }) {
  return {
    schemaVersion: 1,
    build: { scope, edition },
    manifest,
    lessons,
  };
}

/** Assemble the bundle for one of `listWorkbookTargets`'s entries. */
export function createTargetBundle(manifest, lessons, target) {
  const wanted = new Set(target.lessonNumbers);
  return createBuildBundle(
    manifest,
    lessons.filter(({ lessonNumber }) => wanted.has(lessonNumber)),
    target,
  );
}
