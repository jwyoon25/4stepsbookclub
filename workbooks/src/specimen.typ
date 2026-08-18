// ---------------------------------------------------------------------------
// Design specimen.
//
// A typographic proof of the page grammar, not a real workbook. Proper nouns
// are bracketed placeholders; prompts are deliberately book-agnostic but
// realistic in length, because line counts are what the design has to survive.
//
// Build: npm run workbook:specimen
// ---------------------------------------------------------------------------

#import "../system/components.typ": *
#import "../system/tokens.typ": *

#show: workbook.with(book: "[Book Title]", lesson: "Lesson 3")

#workbook-cover(
  series: "Reading Workbook",
  book: "[Book Title]",
  author: "[Author Name]",
  span: "Lessons 1–12  ·  Complete workbook",
)

#lesson-cover(
  lesson: "Lesson 3",
  title: "[Lesson Title]",
  chapters: "Chapters 9–13",
  framing: [This lesson asks you to look closely at how the narrator's account of
    events differs from what actually happens. Read the chapters once for the
    story, then a second time with the questions in front of you.],
  sections: ("Comprehension", "Analysis", "Writing", "Vocabulary"),
  note: [*Writing your answers in Google Docs?* Label each answer with its code —
    L3-C2, L3-A1, and so on — so your tutor can match your responses to the
    workbook.],
)

// --- Step 1: Comprehension --------------------------------------------------

#section-band(
  1,
  "Comprehension",
  "Short, factual answers. One or two sentences is enough. Note the page you found it on.",
)

#question(
  "1",
  [Where does the opening scene take place, and how much time has passed since
    the end of the previous section?],
  lines: lines-short,
)

#question(
  "2",
  [List the three conditions the narrator agrees to. Note which one they hesitate
    over.],
)

#question(
  "3",
  [Reread the passage below. What has the narrator chosen not to tell us, and at
    what point in the chapter does that omission become obvious?],
  quote: [It was easier, in the end, to say nothing at all — and so that is what
    I did, and what I went on doing for a great many years afterwards.],
)

#question(
  "4",
  [Who else is present during the conversation in Chapter 11, and what do they do
    while it is happening?],
  lines: lines-short,
)

#question(
  "5",
  [Summarise, in your own words, what changes between the beginning and the end of
    Chapter 13.],
  lines: lines-extended,
)

// --- Step 2: Analysis -------------------------------------------------------

#section-band(
  2,
  "Analysis",
  "Interpretive answers. There is no single right answer — give your reasoning and point to the text.",
)

#question(
  "1",
  [The narrator describes their decision as inevitable. Do you find that
    convincing? Use at least one detail from Chapter 10 to support your view.],
  lines: lines-extended,
)

#question(
  "2",
  [Compare how two different characters respond to the same piece of news. What
    does the difference between their reactions suggest about each of them?],
  lines: lines-extended,
)

#question(
  "3",
  [The same image appears in Chapter 9 and again in Chapter 13. What has changed
    about its meaning by the second time we see it?],
  lines: lines-extended,
)

// The Analysis section ends here, and the writing surface that follows cannot
// fit on this page. The remainder becomes the student's, rather than a hole.
#ruled-tail("Anything you noticed that the questions didn't ask about")

// --- Step 3: Writing --------------------------------------------------------

#section-band(
  3,
  "Writing",
  "One developed paragraph. Make a claim, support it with evidence, and explain the connection.",
)

#writing-prompt(
  "1",
  [Some readers finish this section believing the narrator is being honest with
    us; others believe they are managing what we are allowed to see. Which reading
    do you find more persuasive, and why?],
  hints: (
    [Begin with a sentence that states your position directly.],
    [Choose two moments from Chapters 9–13 as evidence. Quote briefly.],
    [After each quotation, explain what it shows — do not let it speak for itself.],
    [End by acknowledging what a reader who disagreed with you might point to.],
  ),
)

#writing-continuation("1", [Is the narrator honest with us?])

// --- Step 4: Vocabulary -----------------------------------------------------

#section-band(
  4,
  "Vocabulary",
  "Reference for this lesson. Read these before you begin Chapter 9.",
  continued-label: true,
)

#vocab-entry(
  "01",
  "resolute",
  "단호한",
  index: 0,
  definition: [Determined and unwavering; refusing to be moved from a decision once
    it has been made.],
  in-context: [Used of people, not objects. Carries approval — a resolute person is
    admirable, whereas a stubborn one is not.],
  from-book: ["She remained resolute even as the others began, one by one, to
    reconsider."],
)

#vocab-entry(
  "02",
  "inevitable",
  "피할 수 없는",
  index: 1,
  definition: [Certain to happen; impossible to prevent or avoid.],
  in-context: [Often used by characters to justify a choice they did in fact make
    freely. Watch for who is calling something inevitable, and what they gain by
    it.],
  from-book: ["He spoke of the outcome as inevitable, though he had arranged every
    step of it himself."],
)

#vocab-entry(
  "03",
  "scrutiny",
  "면밀한 조사",
  index: 2,
  definition: [Close, critical examination; careful attention paid to something in
    order to find fault or detail.],
  in-context: [Almost always negative in tone. To be "under scrutiny" is
    uncomfortable, even when you have nothing to hide.],
  from-book: ["Under such scrutiny the smallest hesitation began to look like an
    admission."],
)

#vocab-entry(
  "04",
  "candid",
  "솔직한",
  index: 3,
  definition: [Honest and direct, especially about something awkward or unflattering.],
  in-context: [Stronger than "honest". A candid remark is one most people would have
    kept to themselves.],
  from-book: ["It was the first candid thing anyone had said all evening."],
)

#vocab-entry(
  "05",
  "reluctance",
  "꺼림, 주저함",
  index: 4,
  definition: [Unwillingness to do something, shown through hesitation rather than
    outright refusal.],
  in-context: [Describes the feeling, not the action — a character can act with
    reluctance and still act.],
  from-book: ["Her reluctance was plain to everyone except, apparently, the man
    asking."],
)

#vocab-entry(
  "06",
  "pretext",
  "구실, 핑계",
  index: 5,
  definition: [A stated reason that conceals the real one.],
  in-context: [Implies deliberate concealment. A pretext is offered, an excuse is
    made — the difference matters.],
  from-book: ["The letter was a pretext; he had wanted only to see the house again."],
)

#vocab-entry(
  "07",
  "complicit",
  "공모한, 연루된",
  index: 6,
  definition: [Involved in wrongdoing with others, often by staying silent rather
    than by acting.],
  in-context: [A key word for this section. Notice how often characters are
    complicit through what they choose not to say.],
  from-book: ["They were all complicit, and all of them knew it, and none of them
    said so."],
)

#vocab-entry(
  "08",
  "restraint",
  "자제, 절제",
  index: 7,
  definition: [Self-control; holding back a reaction that would have been
    understandable.],
  in-context: [Can be praise or criticism depending on who is exercising it and
    what it costs them.],
  from-book: ["What looked like restraint was, she later understood, simply fear."],
)

#vocab-entry(
  "09",
  "vindicated",
  "정당성이 입증된",
  index: 8,
  definition: [Proved to have been right after being doubted or blamed.],
  in-context: [Requires an earlier accusation or doubt. You cannot be vindicated
    unless someone first thought you were wrong.],
  from-book: ["He was vindicated eventually, though by then it made very little
    difference."],
)

// The list ends short of the page foot, as a tutor-authored list almost always
// will. The remainder becomes the student's own.
#own-words()
