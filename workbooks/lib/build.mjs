import { execFile } from "node:child_process";
import { mkdir, mkdtemp, rename, rm, writeFile } from "node:fs/promises";
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

import { loadWorkbookPackage, WorkbookContentError } from "./content.mjs";
import { auditWorkbookPdf, WorkbookPdfAuditError } from "./pdf-audit.mjs";

const execFileAsync = promisify(execFile);
const moduleDirectory = dirname(fileURLToPath(import.meta.url));
const workbooksRoot = resolve(moduleDirectory, "..");
const repositoryRoot = resolve(workbooksRoot, "..");
const renderSource = resolve(workbooksRoot, "src/render.typ");
const fontPath = resolve(workbooksRoot, "assets/fonts");
const defaultOutputDirectory = resolve(workbooksRoot, "output");
const temporaryBuildParent = resolve(defaultOutputDirectory, ".build");

export class WorkbookBuildError extends Error {
  constructor(message, options) {
    super(message, options);
    this.name = "WorkbookBuildError";
  }
}

export function containsTypstWarning(diagnostics) {
  return /^warning:/im.test(diagnostics ?? "");
}

function twoDigitLessonNumber(number) {
  return String(number).padStart(2, "0");
}

export function createBuildTargets(workbook, outputDirectory = defaultOutputDirectory) {
  const targets = [];
  const editions = ["student", "teacher"];

  for (const edition of editions) {
    targets.push({
      scope: "workbook",
      edition,
      lessons: workbook.lessons,
      outputPath: resolve(
        outputDirectory,
        `${workbook.manifest.id}-workbook-${edition}.pdf`,
      ),
    });

    for (const lesson of workbook.lessons) {
      targets.push({
        scope: "lesson",
        edition,
        lessons: [lesson],
        lessonNumber: lesson.content.lessonNumber,
        outputPath: resolve(
          outputDirectory,
          `${workbook.manifest.id}-lesson-${twoDigitLessonNumber(lesson.content.lessonNumber)}-${edition}.pdf`,
        ),
      });
    }
  }

  return targets;
}

function typstRootPath(filePath) {
  const pathFromRoot = relative(workbooksRoot, filePath);
  if (
    pathFromRoot === "" ||
    pathFromRoot === ".." ||
    pathFromRoot.startsWith(`..${sep}`) ||
    isAbsolute(pathFromRoot)
  ) {
    throw new WorkbookBuildError(
      `Typst input must stay inside ${workbooksRoot}: ${filePath}`,
    );
  }

  return `/${pathFromRoot.split(sep).join("/")}`;
}

async function compileTarget(workbook, target, temporaryDirectory) {
  const bundlePath = join(
    temporaryDirectory,
    `${target.scope}-${target.lessonNumber ?? "all"}-${target.edition}.json`,
  );
  const bundle = {
    schemaVersion: 1,
    build: {
      scope: target.scope,
      edition: target.edition,
    },
    manifest: workbook.manifest,
    lessons: target.lessons.map(({ content }) => content),
  };
  await writeFile(bundlePath, `${JSON.stringify(bundle, null, 2)}\n`);

  const stagedOutputPath = join(
    dirname(target.outputPath),
    `.${basename(target.outputPath, ".pdf")}.building-${process.pid}.pdf`,
  );

  const argumentsForTypst = [
    "compile",
    "--root",
    workbooksRoot,
    "--font-path",
    fontPath,
    "--input",
    `data=${typstRootPath(bundlePath)}`,
    renderSource,
    stagedOutputPath,
  ];

  let compileResult;
  try {
    compileResult = await execFileAsync("typst", argumentsForTypst, {
      cwd: repositoryRoot,
      maxBuffer: 10 * 1024 * 1024,
    });
  } catch (cause) {
    await rm(stagedOutputPath, { force: true });
    if (cause?.code === "ENOENT") {
      throw new WorkbookBuildError(
        "Typst CLI is not installed or is not available on PATH.",
        { cause },
      );
    }

    const diagnostics = cause?.stderr?.trim();
    throw new WorkbookBuildError(
      `Typst failed while building ${target.outputPath}${
        diagnostics ? `:\n${diagnostics}` : "."
      }`,
      { cause },
    );
  }

  const successfulDiagnostics = [compileResult.stdout, compileResult.stderr]
    .filter(Boolean)
    .join("\n")
    .trim();
  if (containsTypstWarning(successfulDiagnostics)) {
    await rm(stagedOutputPath, { force: true });
    throw new WorkbookBuildError(
      `Typst reported warnings while building ${target.outputPath}:\n${successfulDiagnostics}`,
    );
  }

  try {
    await auditWorkbookPdf(stagedOutputPath, target);
    await rename(stagedOutputPath, target.outputPath);
  } catch (cause) {
    await rm(stagedOutputPath, { force: true });
    if (cause instanceof WorkbookPdfAuditError) {
      throw new WorkbookBuildError(
        `Generated PDF failed the workbook consistency audit:\n${cause.message}`,
        { cause },
      );
    }
    throw cause;
  }
}

export async function buildWorkbookPdfs(
  manifestPath,
  { outputDirectory = defaultOutputDirectory } = {},
) {
  const absoluteOutputDirectory = resolve(outputDirectory);
  const workbook = await loadWorkbookPackage(manifestPath);
  const targets = createBuildTargets(workbook, absoluteOutputDirectory);

  await mkdir(absoluteOutputDirectory, { recursive: true });
  await mkdir(temporaryBuildParent, { recursive: true });
  const temporaryDirectory = await mkdtemp(join(temporaryBuildParent, "render-"));

  try {
    for (const target of targets) {
      await compileTarget(workbook, target, temporaryDirectory);
    }
  } finally {
    await rm(temporaryDirectory, { recursive: true, force: true });
  }

  return targets;
}

export function isExpectedBuildError(error) {
  return error instanceof WorkbookBuildError || error instanceof WorkbookContentError;
}
