#import "components.typ": *
#import "tokens.typ": *

#let section-names = (
  "Reading Comprehension",
  "Critical Thinking & Analysis",
  "Paragraph Writing",
  "Vocabulary",
)

#let optional(data, key, default: none) = data.at(key, default: default)

#let item-count(items, singular, plural) = {
  let n = items.len()
  str(n) + " " + if n == 1 { singular } else { plural }
}

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

#let render-teacher-item(number, item, step) = question(
  str(number),
  item.at("prompt"),
  quote: optional(item, "quotation"),
  response-guidance: optional(item, "responseGuidance"),
  teacher: true,
  teacher-guidance: optional(item, "teacherGuidance"),
  rubric: optional(item, "exampleStructureOrRubric"),
  step: step,
)

#let render-student-item(
  number,
  item,
  step,
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
      response-guidance: optional(item, "responseGuidance"),
      step: step,
    )

    let remaining = line-count - first-page-count
    while remaining > 0 {
      let page-lines = calc.min(remaining, response-continuation-lines)
      response-continuation(
        str(number),
        prompt,
        step: step,
        lines: page-lines,
      )
      remaining -= page-lines
    }
  } else {
    let page-count = if mode == "multiple-pages" { space.at("pages") } else { 1 }
    let continuation-count = page-count - 1
    writing-prompt(
      str(number),
      prompt,
      response-guidance: optional(item, "responseGuidance"),
      quote: quote,
      step: step,
    )

    for index in range(continuation-count) {
      response-continuation(
        str(number),
        prompt,
        step: step,
        break-before: true,
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
  interior-pages(step, name, {
    section-band(step, name, description)
    for ((index, item)) in items.enumerate() {
      if edition == "Teacher" {
        render-teacher-item(index + 1, item, step)
      } else {
        render-student-item(index + 1, item, step)
      }
    }
  })
}

#let render-writing-section(items, edition) = {
  let name = section-names.at(2)
  interior-pages(3, name, {
    section-band(
      3,
      name,
      "Develop a clear response. Make a claim, support it with evidence, and explain the connection.",
    )
    for ((index, item)) in items.enumerate() {
      if edition == "Teacher" {
        render-teacher-item(index + 1, item, 3)
      } else {
        render-student-item(
          index + 1,
          item,
          3,
        )
      }
    }
  })
}

#let render-vocabulary-section(items, edition) = {
  let name = section-names.at(3)
  interior-pages(4, name, {
    section-band(
      4,
      name,
      "Return to these words and the moments in which they appear in the assigned reading.",
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
  })
}

#let render-lesson(lesson, edition, include-how-to: false) = {
  let number = lesson.at("lessonNumber")
  let label = "Lesson " + str(number)
  let sections = lesson.at("sections")
  let section-summaries = (
    (name: section-names.at(0), detail: item-count(sections.at("readingComprehension"), "question", "questions")),
    (name: section-names.at(1), detail: item-count(sections.at("criticalThinkingAndAnalysis"), "question", "questions")),
    (name: section-names.at(2), detail: item-count(sections.at("paragraphWriting"), "prompt", "prompts")),
    (name: section-names.at(3), detail: item-count(sections.at("vocabulary"), "word", "words")),
  )
  lesson-start(label)
  lesson-cover(
    lesson: label,
    title: lesson.at("title"),
    chapters: lesson.at("readingRange"),
    framing: optional(lesson, "framingNote", default: ""),
    instructions: optional(lesson, "studentInstructions"),
    sections: section-summaries,
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
    "Answer from the text. Keep factual responses concise and cite supporting pages in parentheses.",
    edition,
  )
  render-question-section(
    sections.at("criticalThinkingAndAnalysis"),
    2,
    section-names.at(1),
    "Interpret the reading. Give your reasoning and point to specific evidence from the text.",
    edition,
  )
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
