import assert from "node:assert/strict";
import { join, relative } from "node:path";
import test from "node:test";

import { createBuildTargets } from "../workbooks/lib/build.mjs";

const outputDirectory = "/tmp/4steps-workbook-build-test";

function targetNames(targets) {
  return targets.map(({ outputPath }) => relative(outputDirectory, outputPath));
}

test("plans complete and standalone PDFs for both editions", () => {
  const firstLesson = { content: { lessonNumber: 2 } };
  const secondLesson = { content: { lessonNumber: 12 } };
  const workbook = {
    manifest: { id: "book-alpha" },
    lessons: [firstLesson, secondLesson],
  };

  const targets = createBuildTargets(workbook, outputDirectory);

  assert.deepEqual(targetNames(targets), [
    "book-alpha-workbook-student.pdf",
    "book-alpha-lesson-02-student.pdf",
    "book-alpha-lesson-12-student.pdf",
    "book-alpha-workbook-teacher.pdf",
    "book-alpha-lesson-02-teacher.pdf",
    "book-alpha-lesson-12-teacher.pdf",
  ]);
  assert.deepEqual(
    targets.map(({ scope, edition }) => [scope, edition]),
    [
      ["workbook", "student"],
      ["lesson", "student"],
      ["lesson", "student"],
      ["workbook", "teacher"],
      ["lesson", "teacher"],
      ["lesson", "teacher"],
    ],
  );
  assert.deepEqual(targets[0].lessons, [firstLesson, secondLesson]);
  assert.deepEqual(targets[1].lessons, [firstLesson]);
  assert.deepEqual(targets[2].lessons, [secondLesson]);
  assert.deepEqual(targets[3].lessons, [firstLesson, secondLesson]);
  assert.equal(targets[1].lessonNumber, 2);
  assert.equal(targets[2].lessonNumber, 12);
});

test("resolves every output below the requested directory", () => {
  const workbook = {
    manifest: { id: "example-book" },
    lessons: [{ content: { lessonNumber: 3 } }],
  };

  const targets = createBuildTargets(workbook, outputDirectory);

  for (const target of targets) {
    assert.equal(
      target.outputPath,
      join(outputDirectory, relative(outputDirectory, target.outputPath)),
    );
    assert.doesNotMatch(relative(outputDirectory, target.outputPath), /^\.\./);
  }
});
