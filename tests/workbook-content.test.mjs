import assert from "node:assert/strict";
import { cp, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  defaultResponseSpaceFor,
  loadWorkbookPackage,
  WorkbookContentError,
} from "../workbooks/lib/content.mjs";

const repositoryRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const examplePackage = join(
  repositoryRoot,
  "workbooks/schema/examples/example-book",
);
const exampleManifest = join(examplePackage, "workbook.json");

async function readJson(filePath) {
  return JSON.parse(await readFile(filePath, "utf8"));
}

async function writeJson(filePath, value) {
  await writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

async function withTemporaryPackage(run) {
  const temporaryRoot = await mkdtemp(join(tmpdir(), "4steps-workbook-content-"));
  const packageDirectory = join(temporaryRoot, "example-book");
  await cp(examplePackage, packageDirectory, { recursive: true });

  try {
    return await run({
      packageDirectory,
      manifestPath: join(packageDirectory, "workbook.json"),
      lessonPath: join(packageDirectory, "lessons/lesson-03.json"),
    });
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
}

test("loads a complete workbook package and applies semantic defaults", async () => {
  const workbook = await loadWorkbookPackage(exampleManifest);

  assert.equal(workbook.manifest.id, "example-book");
  assert.equal(workbook.lessons.length, 1);
  assert.equal(workbook.lessons[0].content.lessonNumber, 3);

  const sections = workbook.lessons[0].content.sections;
  assert.deepEqual(sections.readingComprehension[0].responseSpace, {
    mode: "short-answer",
  });
  assert.deepEqual(sections.criticalThinkingAndAnalysis[0].responseSpace, {
    mode: "short-paragraph",
  });
  assert.deepEqual(sections.paragraphWriting[0].responseSpace, {
    mode: "full-page",
  });
  assert.deepEqual(
    sections.readingComprehension[0].responseGuidance,
    ["Answer in 2–3 complete sentences."],
  );
  assert.deepEqual(
    sections.criticalThinkingAndAnalysis[0].responseGuidance,
    [
      "Write one paragraph.",
      "Use at least two quotations from the book.",
    ],
  );
  assert.deepEqual(
    sections.paragraphWriting[0].responseGuidance,
    [
      "Write two paragraphs.",
      "State your position directly.",
      "Use at least three short quotations from the book.",
      "Explain how each quotation supports your position.",
    ],
  );
  assert.equal(
    sections.readingComprehension[1].responseGuidance,
    undefined,
  );

  assert.deepEqual(sections.readingComprehension[1].responseSpace, {
    mode: "custom-lines",
    lines: 5,
  });
  assert.deepEqual(sections.criticalThinkingAndAnalysis[1].responseSpace, {
    mode: "extended-answer",
  });
  assert.deepEqual(sections.paragraphWriting[1].responseSpace, {
    mode: "multiple-pages",
    pages: 2,
  });
});

test("returns independent response-space defaults", () => {
  const first = defaultResponseSpaceFor("readingComprehension");
  first.mode = "full-page";

  assert.deepEqual(defaultResponseSpaceFor("readingComprehension"), {
    mode: "short-answer",
  });
  assert.throws(
    () => defaultResponseSpaceFor("vocabulary"),
    WorkbookContentError,
  );
});

test("reports schema paths for invalid lesson content", async () => {
  await withTemporaryPackage(async ({ manifestPath, lessonPath }) => {
    const lesson = await readJson(lessonPath);
    delete lesson.sections.vocabulary[0].excerptContext;
    await writeJson(lessonPath, lesson);

    await assert.rejects(
      loadWorkbookPackage(manifestPath),
      (error) => {
        assert.ok(error instanceof WorkbookContentError);
        assert.match(
          error.message,
          /\/sections\/vocabulary\/0\/excerptContext/,
        );
        return true;
      },
    );
  });
});

test("rejects malformed response-space choices", async () => {
  await withTemporaryPackage(async ({ manifestPath, lessonPath }) => {
    const lesson = await readJson(lessonPath);
    lesson.sections.readingComprehension[0].responseSpace = {
      mode: "custom-lines",
    };
    await writeJson(lessonPath, lesson);

    await assert.rejects(
      loadWorkbookPackage(manifestPath),
      (error) => {
        assert.ok(error instanceof WorkbookContentError);
        assert.match(error.message, /responseSpace/);
        assert.match(error.message, /lines/);
        return true;
      },
    );
  });
});

test("rejects blank items in optional response guidance", async () => {
  await withTemporaryPackage(async ({ manifestPath, lessonPath }) => {
    const lesson = await readJson(lessonPath);
    lesson.sections.criticalThinkingAndAnalysis[0].responseGuidance = ["   "];
    await writeJson(lessonPath, lesson);

    await assert.rejects(
      loadWorkbookPackage(manifestPath),
      (error) => {
        assert.ok(error instanceof WorkbookContentError);
        assert.match(error.message, /responseGuidance/);
        return true;
      },
    );
  });
});

test("migrates legacy Writing hints into shared response guidance", async () => {
  await withTemporaryPackage(async ({ manifestPath, lessonPath }) => {
    const lesson = await readJson(lessonPath);
    const prompt = lesson.sections.paragraphWriting[1];
    prompt.hints = ["Plan the scene before drafting."];
    await writeJson(lessonPath, lesson);

    const workbook = await loadWorkbookPackage(manifestPath);
    const normalizedPrompt =
      workbook.lessons[0].content.sections.paragraphWriting[1];

    assert.deepEqual(normalizedPrompt.responseGuidance, [
      "Plan the scene before drafting.",
    ]);
    assert.equal(normalizedPrompt.hints, undefined);
  });
});

test("rejects cover text beyond its standardized field limit", async () => {
  await withTemporaryPackage(async ({ manifestPath, lessonPath }) => {
    const lesson = await readJson(lessonPath);
    lesson.title = "T".repeat(101);
    await writeJson(lessonPath, lesson);

    await assert.rejects(
      loadWorkbookPackage(manifestPath),
      (error) => {
        assert.ok(error instanceof WorkbookContentError);
        assert.match(error.message, /\/title/);
        assert.match(error.message, /more than 100 characters/);
        return true;
      },
    );
  });
});

test("rejects individually valid lesson-cover fields that overflow together", async () => {
  await withTemporaryPackage(async ({ manifestPath, lessonPath }) => {
    const lesson = await readJson(lessonPath);
    lesson.title = "A focused lesson title";
    lesson.readingRange = "Chapters 1–10";
    lesson.framingNote = "framing ".repeat(40).trim();
    lesson.studentInstructions = "instruction ".repeat(33).trim();
    await writeJson(lessonPath, lesson);

    await assert.rejects(
      loadWorkbookPackage(manifestPath),
      (error) => {
        assert.ok(error instanceof WorkbookContentError);
        assert.match(error.message, /\/lesson-cover/);
        assert.match(error.message, /standardized workbook layout/);
        return true;
      },
    );
  });
});

test("rejects a prompt and guidance combination that cannot fit its response space", async () => {
  await withTemporaryPackage(async ({ manifestPath, lessonPath }) => {
    const lesson = await readJson(lessonPath);
    lesson.sections.paragraphWriting[0].prompt = "prompt ".repeat(92).trim();
    lesson.sections.paragraphWriting[0].responseGuidance = [
      "guide ".repeat(26).trim(),
      "evidence ".repeat(20).trim(),
    ];
    await writeJson(lessonPath, lesson);

    await assert.rejects(
      loadWorkbookPackage(manifestPath),
      (error) => {
        assert.ok(error instanceof WorkbookContentError);
        assert.match(error.message, /\/sections\/paragraphWriting\/0/);
        assert.match(error.message, /choose fewer first-page response lines/);
        return true;
      },
    );
  });
});

test("rejects unbroken text that cannot wrap inside the page measure", async () => {
  await withTemporaryPackage(async ({ manifestPath, lessonPath }) => {
    const lesson = await readJson(lessonPath);
    lesson.sections.readingComprehension[0].prompt = "P".repeat(81);
    await writeJson(lessonPath, lesson);

    await assert.rejects(
      loadWorkbookPackage(manifestPath),
      (error) => {
        assert.ok(error instanceof WorkbookContentError);
        assert.match(
          error.message,
          /\/sections\/readingComprehension\/0\/prompt/,
        );
        assert.match(error.message, /unbroken text segment of 81 characters/);
        return true;
      },
    );
  });
});

test("rejects a vocabulary entry whose fields cannot fit together", async () => {
  await withTemporaryPackage(async ({ manifestPath, lessonPath }) => {
    const lesson = await readJson(lessonPath);
    lesson.sections.vocabulary[0] = {
      term: "term ".repeat(10).trim(),
      koreanMeaning: "뜻 ".repeat(45).trim(),
      definition: "detail ".repeat(82).trim(),
      bookExcerpt: "evidence ".repeat(65).trim(),
      excerptContext: "context ".repeat(85).trim(),
      chapterReference: "reference ".repeat(8).trim(),
    };
    await writeJson(lessonPath, lesson);

    await assert.rejects(
      loadWorkbookPackage(manifestPath),
      (error) => {
        assert.ok(error instanceof WorkbookContentError);
        assert.match(error.message, /\/sections\/vocabulary\/0/);
        assert.match(error.message, /estimated layout size/);
        return true;
      },
    );
  });
});

test("rejects duplicate lesson numbers", async () => {
  await withTemporaryPackage(
    async ({ packageDirectory, manifestPath, lessonPath }) => {
      const duplicatePath = join(packageDirectory, "lessons/lesson-04.json");
      await cp(lessonPath, duplicatePath);

      const manifest = await readJson(manifestPath);
      manifest.lessonFiles.push("lessons/lesson-04.json");
      await writeJson(manifestPath, manifest);

      await assert.rejects(
        loadWorkbookPackage(manifestPath),
        /Duplicate lesson number 3/,
      );
    },
  );
});

test("preserves manifest lesson order instead of sorting lesson numbers", async () => {
  await withTemporaryPackage(
    async ({ packageDirectory, manifestPath, lessonPath }) => {
      const laterLessonPath = join(packageDirectory, "lessons/lesson-04.json");
      const laterLesson = await readJson(lessonPath);
      laterLesson.lessonNumber = 4;
      await writeJson(laterLessonPath, laterLesson);

      const manifest = await readJson(manifestPath);
      manifest.lessonFiles = [
        "lessons/lesson-04.json",
        "lessons/lesson-03.json",
      ];
      await writeJson(manifestPath, manifest);

      const workbook = await loadWorkbookPackage(manifestPath);
      assert.deepEqual(
        workbook.lessons.map(({ content }) => content.lessonNumber),
        [4, 3],
      );
    },
  );
});

test("rejects missing and unsafe lesson paths", async (t) => {
  await t.test("missing lesson", async () => {
    await withTemporaryPackage(async ({ manifestPath }) => {
      const manifest = await readJson(manifestPath);
      manifest.lessonFiles = ["lessons/missing.json"];
      await writeJson(manifestPath, manifest);

      await assert.rejects(
        loadWorkbookPackage(manifestPath),
        /Lesson file does not exist: lessons\/missing\.json/,
      );
    });
  });

  await t.test("path outside package", async () => {
    await withTemporaryPackage(async ({ manifestPath }) => {
      const manifest = await readJson(manifestPath);
      manifest.lessonFiles = ["../outside.json"];
      await writeJson(manifestPath, manifest);

      await assert.rejects(
        loadWorkbookPackage(manifestPath),
        (error) => {
          assert.ok(error instanceof WorkbookContentError);
          assert.match(error.message, /lessonFiles\/0/);
          return true;
        },
      );
    });
  });
});

test("reports malformed JSON without an internal stack trace", async () => {
  await withTemporaryPackage(async ({ manifestPath, lessonPath }) => {
    await writeFile(lessonPath, "{ definitely not JSON\n");

    await assert.rejects(
      loadWorkbookPackage(manifestPath),
      (error) => {
        assert.ok(error instanceof WorkbookContentError);
        assert.match(error.message, /Invalid JSON/);
        assert.match(error.message, /lesson-03\.json/);
        return true;
      },
    );
  });
});
