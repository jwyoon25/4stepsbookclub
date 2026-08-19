import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { after, before, describe, test } from "node:test";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  compileWorkbookPdf,
  WorkbookCompilerError,
} from "../workbooks/builder/browser/workbook-compiler.mjs";
import { createFixtureBundles } from "../workbooks/lib/browser-bundle.mjs";
import {
  verifyWorkbookFixture,
  withVerificationDirectory,
} from "../workbooks/lib/browser-verification.mjs";
import { createWorkbookTypstCompiler } from "../workbooks/lib/typst-compiler.mjs";

const repositoryRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const examplePackage = join(
  repositoryRoot,
  "workbooks/schema/examples/example-book/workbook.json",
);
const typstAvailable =
  spawnSync("typst", ["--version"], { stdio: "ignore" }).status === 0;

let compiler;
let fixtures;

before(async () => {
  fixtures = new Map(
    (await createFixtureBundles(examplePackage)).map((fixture) => [
      fixture.id,
      fixture,
    ]),
  );
  ({ compiler } = await createWorkbookTypstCompiler());
});

after(async () => {
  await compiler?.dispose();
});

function verify(id) {
  return withVerificationDirectory((directory) =>
    verifyWorkbookFixture(compiler, fixtures.get(id), { directory }),
  );
}

describe("the browser compiler", { skip: !typstAvailable }, () => {
  test("renders a student lesson exactly as the native renderer does", async () => {
    const result = await verify("lesson-student");

    assert.equal(result.audit.passed, true, result.audit.error);
    assert.deepEqual(result.text.differences, []);
    assert.equal(result.text.worstOffsetPoints, 0);
    assert.deepEqual(result.pixels.differences, []);
    assert.equal(result.pixels.differingChannels, 0);
    assert.ok(
      result.pixels.totalChannels > 1_000_000,
      "every page should have been compared",
    );
    // A student edition is the one with somewhere to write.
    assert.ok(result.text.ruledLines > 0);
  });

  test("renders the teacher edition of the same lesson", async () => {
    const result = await verify("lesson-teacher");

    assert.equal(result.audit.passed, true, result.audit.error);
    assert.deepEqual(result.text.differences, []);
    assert.deepEqual(result.pixels.differences, []);
    // The teacher edition replaces the response space with guidance, so the
    // edition really did reach the browser compilation.
    assert.equal(result.text.ruledLines, 0);
  });

  test("compiles the two editions from the same templates and fonts", async () => {
    const student = await verify("lesson-student");
    const teacher = await verify("lesson-teacher");

    assert.notEqual(student.pageCount, teacher.pageCount);
    assert.equal(student.engines.browser, teacher.engines.browser);
  });
});

test("refuses a bundle the renderer cannot compile", async () => {
  const { bundle } = fixtures.get("lesson-student");
  const withoutEdition = {
    ...bundle,
    build: { scope: bundle.build.scope },
  };

  await assert.rejects(
    compileWorkbookPdf(compiler, withoutEdition),
    (error) =>
      error instanceof WorkbookCompilerError &&
      /Typst failed while compiling the workbook/.test(error.message),
  );
});
