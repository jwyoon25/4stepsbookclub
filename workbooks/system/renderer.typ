#import "components.typ": *
#import "tokens.typ": *

#let section-names = (
  "Reading Comprehension",
  "Critical Thinking & Analysis",
  "Paragraph Writing",
  "Vocabulary",
)

#let optional(data, key, default: none) = data.at(key, default: default)

#let response-line-count(space) = {
  let mode = space.at("mode")
  if mode == "short-answer" {
    response-short-answer-lines
  } else if mode == "short-paragraph" {
    response-short-paragraph-lines
  } else if mode == "extended-answer" {
    response-extended-answer-lines
  } else if mode == "custom-lines" {
    space.at("lines")
  } else {
    none
  }
}

#let render-teacher-item(number, item, hints: none) = question(
  str(number),
  item.at("prompt"),
  quote: optional(item, "quotation"),
  cite: false,
  hints: hints,
  teacher: true,
  teacher-guidance: optional(item, "teacherGuidance"),
  rubric: optional(item, "exampleStructureOrRubric"),
)

#let render-student-item(
  number,
  item,
  step,
  section-name,
  hints: none,
  cite: true,
) = {
  let space = item.at("responseSpace")
  let mode = space.at("mode")
  let prompt = item.at("prompt")
  let quote = optional(item, "quotation")
  let line-count = response-line-count(space)

  if line-count != none {
    let first-page-count = calc.min(line-count, response-first-page-lines)
    question(
      str(number),
      prompt,
      lines: first-page-count,
      quote: quote,
      cite: cite,
      hints: hints,
    )

    let remaining = line-count - first-page-count
    while remaining > 0 {
      let page-lines = calc.min(remaining, response-continuation-lines)
      response-continuation(
        str(number),
        prompt,
        step: step,
        section: section-name + " (continued)",
        lines: page-lines,
      )
      remaining -= page-lines
    }
  } else {
    writing-prompt(
      str(number),
      prompt,
      hints: hints,
      quote: quote,
      cite: cite,
    )

    let page-count = if mode == "multiple-pages" { space.at("pages") } else { 1 }
    for _ in range(page-count - 1) {
      response-continuation(
        str(number),
        prompt,
        step: step,
        section: section-name + " (continued)",
        break-before: false,
      )
    }
  }
}

#let render-question-section(
  items,
  step,
  name,
  description,
  edition,
) = {
  section-band(step, name, description)
  for ((index, item)) in items.enumerate() {
    if edition == "Teacher" {
      render-teacher-item(index + 1, item)
    } else {
      render-student-item(index + 1, item, step, name)
    }
  }
}

#let render-writing-section(items, edition) = {
  let name = section-names.at(2)
  section-band(
    3,
    name,
    "Develop a clear response. Make a claim, support it with evidence, and explain the connection.",
  )
  for ((index, item)) in items.enumerate() {
    let hints = optional(item, "hints")
    if edition == "Teacher" {
      render-teacher-item(index + 1, item, hints: hints)
    } else {
      render-student-item(
        index + 1,
        item,
        3,
        name,
        hints: hints,
        cite: false,
      )
    }
  }
}

#let render-vocabulary-section(items, edition) = {
  section-band(
    4,
    section-names.at(3),
    "Return to these words and the moments in which they appear in the assigned reading.",
    continued-label: true,
  )
  for ((index, item)) in items.enumerate() {
    let number = index + 1
    vocab-entry(
      if number < 10 { "0" + str(number) } else { str(number) },
      item.at("term"),
      item.at("koreanMeaning"),
      definition: item.at("definition"),
      from-book: item.at("bookExcerpt"),
      excerpt-context: item.at("excerptContext"),
      chapter-reference: optional(item, "chapterReference"),
      index: index,
    )
  }
  if edition != "Teacher" { own-words() }
}

#let render-lesson(lesson, edition, include-how-to: false) = {
  let number = lesson.at("lessonNumber")
  let label = "Lesson " + str(number)
  let sections = lesson.at("sections")
  lesson-start(label)
  lesson-cover(
    lesson: label,
    title: lesson.at("title"),
    chapters: lesson.at("readingRange"),
    framing: optional(lesson, "framingNote", default: ""),
    instructions: optional(lesson, "studentInstructions"),
    sections: section-names,
    edition: edition,
    note: if edition == "Teacher" {
      [Teacher guidance is shown beside each question and is omitted from the student version.]
    } else {
      [*Writing your answers in Google Docs?* Label each answer with its code — #("L" + str(number) + "-C2"), #("L" + str(number) + "-A1"), and so on — so your tutor can match your responses to the workbook.]
    },
  )
  if include-how-to { how-to-page() }

  render-question-section(
    sections.at("readingComprehension"),
    1,
    section-names.at(0),
    "Answer from the text. Keep factual responses concise and note the page where you found the evidence.",
    edition,
  )
  render-question-section(
    sections.at("criticalThinkingAndAnalysis"),
    2,
    section-names.at(1),
    "Interpret the reading. Give your reasoning and point to specific evidence from the text.",
    edition,
  )
  if edition != "Teacher" {
    ruled-tail("Anything you noticed that the questions didn't ask about")
  }
  render-writing-section(sections.at("paragraphWriting"), edition)
  render-vocabulary-section(sections.at("vocabulary"), edition)
}

#let render-bundle(data) = {
  let manifest = data.at("manifest")
  let build = data.at("build")
  let lessons = data.at("lessons")
  let edition = if build.at("edition") == "teacher" { "Teacher" } else { "Student" }
  let standalone-lesson = build.at("scope") == "lesson"

  workbook(
    book: manifest.at("bookTitle"),
    edition: edition,
  )[
    #if build.at("scope") == "workbook" {
      workbook-cover(
        book: manifest.at("bookTitle"),
        author: manifest.at("author"),
        series: manifest.at("seriesTitle"),
        span: manifest.at("lessonRange"),
        subtitle: optional(manifest, "coverSubtitle"),
        edition: edition,
      )
      how-to-page()
    }

    #for lesson in lessons {
      render-lesson(lesson, edition, include-how-to: standalone-lesson)
    }
  ]
}
