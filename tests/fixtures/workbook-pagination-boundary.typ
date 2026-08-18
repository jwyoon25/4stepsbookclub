#import "../../workbooks/system/components.typ": *

#workbook(
  book: "Pagination Boundary Fixture",
  lesson: "Diagnostic",
  edition: "Student",
  {
    interior-pages(1, "Reading Comprehension", {
      section-band(
        1,
        "Reading Comprehension",
        "Verify that a finite response never fragments across pages.",
      )

      v(191mm)
      question(
        "9",
        [This six-line response must move to the next page intact.],
        lines: 6,
        step: 1,
      )
    })
  },
)
