"""Invented prose for the fixture books.

Written for this repository, so nothing copyrighted is committed. The wording is
chosen to exercise the ingester: mid-sentence dialogue with curly quotes,
abbreviations that a naive sentence splitter breaks on, long words that will be
hyphenated across a line break, and target vocabulary that appears in exactly
one chapter so occurrence checks have a known answer.
"""

from __future__ import annotations

CHAPTER_PROSE: dict[int, list[str]] = {
    1: [
        "The lift shuddered once and began its ascent, and Mara pressed both "
        "palms against the cold wall to keep from falling. She did not know how "
        "long she had been inside it. She did not know her own age, which "
        "frightened her more than the dark did.",
        "“Somebody up there,” she called, and her voice came back to her flat "
        "and small. No one answered. The chains overhead kept up their "
        "incomprehensible rattling, a sound with no beginning she could "
        "remember and no end she could imagine.",
        "Mr. Alder had told her something once. She was certain of that much, "
        "and certain of nothing after it. The memory arrived without its "
        "contents, like a room emptied of furniture but still shaped by where "
        "the furniture had stood.",
        "When the ceiling opened, the light was so sudden that she made a "
        "sound she was ashamed of afterwards. Faces looked down at her. One of "
        "them was laughing.",
    ],
    2: [
        "They gave her a bed in the long hut and left her there to consider her "
        "predicament. Someone had scratched a tally into the beam above her "
        "head, and she counted it twice before deciding she did not want to "
        "know what it counted.",
        "By morning the settlement had arranged itself into work. Boys carried "
        "water. Girls mended the fence line. Everything ran on a schedule "
        "nobody had written down, and everyone but Mara appeared to know it.",
        "“You'll get used to it,” said the tall one, whose name she would not "
        "learn until Tuesday. He said it kindly, which somehow made it worse. "
        "“Everyone does. That's the whole trick of this place.”",
        "She watched the wall beyond the fields all afternoon. It was "
        "monotonous in the way that only enormous things are monotonous, grey "
        "and patient and entirely indifferent to being looked at.",
    ],
    3: [
        "The alarm came at dusk, a single note held far too long. Mara felt the "
        "settlement lurch around her, every person turning at once toward the "
        "eastern gate as though they had rehearsed it.",
        "“Runner's late,” someone said, and the words travelled through the "
        "crowd and changed as they went, the way a rumour does. By the time "
        "they reached the far fence they had become something much worse.",
        "Dr. Vance would have called this a study in collective behaviour. Mara "
        "had no idea who Dr. Vance was, or why the name surfaced now, or why it "
        "carried with it the smell of disinfectant and a corridor with no "
        "windows in it.",
        "The gate began to close. It did so slowly and without apology, and the "
        "sound it made was the least negotiable sound she had ever heard.",
    ],
    4: [
        "Afterwards they held a council, which turned out to mean forty people "
        "shouting in a barn. Mara stood at the back and listened to them "
        "deliberate, and understood perhaps one word in five.",
        "The tall one argued for waiting. A thin boy with a burned hand argued "
        "for going out at first light, and argued badly, and was right anyway. "
        "Mara found that she believed him, and found that she resented "
        "believing him.",
        "“You're new,” the tall one said to her later, outside, where the air "
        "was cooler. “New people always want to do something. It's the wanting "
        "that gets people killed here.”",
        "She did not answer. Above the wall the sky had gone the colour of wet "
        "slate, and somewhere behind it, she was increasingly certain, someone "
        "was watching all of this happen and writing it down.",
    ],
    5: [
        "They went out at first light, because the thin boy had been right and "
        "everyone had known it. The corridor beyond the gate was tall enough "
        "that Mara's estimation of the place reorganised itself entirely.",
        "Ivy had taken the lower stones. Higher up the walls were bare and "
        "showed their seams, and the seams were too regular to be accidental. "
        "Somebody had built this. That was the thought she could not put down.",
        "“Don't touch anything,” the tall one said, unnecessarily. Mara had "
        "already decided that. She was cataloguing instead: the turns, the "
        "distances, the places where the light behaved strangely.",
        "At the fourth turning they found the marks. They were fresh, and they "
        "were not made by anything with hands, and the tall one's face when he "
        "saw them was the most articulate thing Mara had seen since she "
        "arrived.",
    ],
    6: [
        "The return was worse than the going. Mara's arithmetic of the place "
        "had been correct in every particular except the one that mattered, "
        "and the gate was already closing when the barn came into view.",
        "She got through it. The thin boy did not, at first, and the noise he "
        "made afterwards was one she would keep. Later she would be unable to "
        "recall the sound itself, only her own perfect stillness while it "
        "happened.",
        "“That,” said the tall one, sitting down heavily in the dirt, “is why "
        "we wait.” He did not sound vindicated. He sounded exhausted, and "
        "underneath the exhaustion, ashamed.",
        "Mara looked at the wall until the light went out of it. She had "
        "decided something. She would not tell anyone what, because telling "
        "people was how a decision got taken away from you.",
    ],
}


def chapter_specs(count: int, titles: dict[int, str] | None = None):
    """Build `count` chapters, cycling the prose so a book can be any length."""
    from .synthetic_book import ChapterSpec

    titles = titles or {}
    source_numbers = sorted(CHAPTER_PROSE)
    specs = []
    for number in range(1, count + 1):
        prose = CHAPTER_PROSE[source_numbers[(number - 1) % len(source_numbers)]]
        specs.append(
            ChapterSpec(number=number, title=titles.get(number), paragraphs=list(prose))
        )
    return specs
