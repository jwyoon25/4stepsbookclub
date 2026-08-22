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

#how-to-page()

#lesson-cover(
  lesson: "Lesson 3",
  title: "[Lesson Title]",
  chapters: "Chapters 9–13",
  framing: [This lesson asks you to look closely at how the narrator's account of
    events differs from what actually happens. Read the chapters once for the
    story, then a second time with the questions in front of you.],
  sections: (
    (name: "Comprehension", detail: "5 questions"),
    (name: "Analysis", detail: "3 questions"),
    (name: "Writing", detail: "1 prompt"),
    (name: "Vocabulary", detail: "9 words"),
  ),
  note: [*Writing your answers in Google Docs?* Label each answer with its code —
    L3-C2, L3-A1, and so on — so your tutor can match your responses to the
    workbook.],
)

// --- Step 1: Comprehension --------------------------------------------------

#interior-pages(1, "Comprehension")[
#section-band(
  1,
  "Comprehension",
  "Short, factual answers. Keep them concise and cite supporting pages in parentheses.",
)

#question(
  "1",
  [Where does the opening scene take place, and how much time has passed since
    the end of the previous section?],
  lines: lines-short,
  first-in-section: true,
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
]

// --- Step 2: Analysis -------------------------------------------------------

#interior-pages(2, "Analysis")[
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
  step: 2,
  first-in-section: true,
)

#question(
  "2",
  [Compare how two different characters respond to the same piece of news. What
    does the difference between their reactions suggest about each of them?],
  lines: lines-extended,
  step: 2,
)

#question(
  "3",
  [The same image appears in Chapter 9 and again in Chapter 13. What has changed
    about its meaning by the second time we see it?],
  lines: lines-extended,
  step: 2,
)

// The specimen demonstrates the optional fixed-height reflection tail. The
// data-driven renderer leaves section-end space blank for stable pagination.
#ruled-tail("Anything you noticed that the questions didn't ask about")
]

// --- Step 3: Writing --------------------------------------------------------

#interior-pages(3, "Writing")[
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
  response-guidance: (
    [Begin with a sentence that states your position directly.],
    [Choose two moments from Chapters 9–13 as evidence. Quote briefly.],
    [After each quotation, explain what it shows — do not let it speak for itself.],
    [End by acknowledging what a reader who disagreed with you might point to.],
  ),
  first-in-section: true,
)
]

// --- Step 4: Vocabulary -----------------------------------------------------

#interior-pages(4, "Vocabulary")[
#section-band(
  4,
  "Vocabulary",
  "Reference for this lesson. Read these before you begin Chapter 9.",
)

#vocab-entry(
  "01",
  "resolute",
  "단호한",
  index: 0,
  first-in-section: true,
  definition: [Determined and unwavering; refusing to be moved from a decision once
    it has been made.],
  from-book: ["She remained resolute even as the others began, one by one, to
    reconsider."],
  excerpt-context: [The rest of the group has begun to doubt the plan, but she
    continues to defend the decision they made earlier.],
)

#vocab-entry(
  "02",
  "inevitable",
  "피할 수 없는",
  index: 1,
  definition: [Certain to happen; impossible to prevent or avoid.],
  from-book: ["He spoke of the outcome as inevitable, though he had arranged every
    step of it himself."],
  excerpt-context: [The others have challenged him about the outcome, and he is
    defending a result that his own choices helped bring about.],
)

#vocab-entry(
  "03",
  "scrutiny",
  "면밀한 조사",
  index: 2,
  definition: [Close, critical examination; careful attention paid to something in
    order to find fault or detail.],
  from-book: ["Under such scrutiny the smallest hesitation began to look like an
    admission."],
  excerpt-context: [The character is being questioned, and the group begins to
    treat even a brief pause as evidence of guilt.],
)

#vocab-entry(
  "04",
  "candid",
  "솔직한",
  index: 3,
  definition: [Honest and direct, especially about something awkward or unflattering.],
  from-book: ["It was the first candid thing anyone had said all evening."],
  excerpt-context: [The group has spent the evening avoiding the truth until one
    person finally speaks directly about what happened.],
)

#vocab-entry(
  "05",
  "reluctance",
  "꺼림, 주저함",
  index: 4,
  definition: [Unwillingness to do something, shown through hesitation rather than
    outright refusal.],
  from-book: ["Her reluctance was plain to everyone except, apparently, the man
    asking."],
  excerpt-context: [She has been asked to take part and hesitates in front of the
    group even though she eventually agrees.],
)

#vocab-entry(
  "06",
  "pretext",
  "구실, 핑계",
  index: 5,
  definition: [A stated reason that conceals the real one.],
  from-book: ["The letter was a pretext; he had wanted only to see the house again."],
  excerpt-context: [He has returned after a long absence and presents the letter
    as his official reason for visiting the house.],
)

#vocab-entry(
  "07",
  "complicit",
  "공모한, 연루된",
  index: 6,
  definition: [Involved in wrongdoing with others, often by staying silent rather
    than by acting.],
  from-book: ["They were all complicit, and all of them knew it, and none of them
    said so."],
  excerpt-context: [The group realizes that their shared silence has made everyone
    partly responsible for what followed.],
)

#vocab-entry(
  "08",
  "restraint",
  "자제, 절제",
  index: 7,
  definition: [Self-control; holding back a reaction that would have been
    understandable.],
  from-book: ["What looked like restraint was, she later understood, simply fear."],
  excerpt-context: [She first interprets his silence as self-control, then learns
    that he stayed quiet because he was afraid.],
)

#vocab-entry(
  "09",
  "vindicated",
  "정당성이 입증된",
  index: 8,
  definition: [Proved to have been right after being doubted or blamed.],
  from-book: ["He was vindicated eventually, though by then it made very little
    difference."],
  excerpt-context: [Later evidence proves that he was right, but it arrives too
    late to repair the consequences of the earlier accusation.],
)

// The specimen also demonstrates the optional fixed-height own-words surface.
#own-words()
]
