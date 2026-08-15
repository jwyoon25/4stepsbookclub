export type WonderFeedbackId =
  | "thesis"
  | "precision"
  | "evidence"
  | "relevance"
  | "reasoning"
  | "interpretation"
  | "analysis"
  | "big-picture";

export interface EssayComment {
  id: WonderFeedbackId;
  text: string;
}

export interface EssaySegment {
  text: string;
  commentId?: WonderFeedbackId;
  mobileCommentAfter?: WonderFeedbackId;
  italic?: boolean;
}

export interface EssayExcerpt {
  id: string;
  segments: EssaySegment[];
}

export const wonderComments: EssayComment[] = [
  {
    id: "thesis",
    text: "Can you make this more of an argument? Right now you're telling me what the essay will cover, but not what you think Palacio is trying to show through these different reactions to August."
  },
  {
    id: "precision",
    text: "Is \"the majority\" accurate here? That's a pretty big claim. I'd either name the specific characters you're talking about or make this a little less broad."
  },
  {
    id: "evidence",
    text: "This is a good place to bring in a specific example from the book. Pick one moment with Julian and explain what it shows about how he sees August."
  },
  {
    id: "relevance",
    text: "I get the comparison you're making, but this feels a little too broad and takes us away from the novel. Could you make the same point using Julian's behavior instead?"
  },
  {
    id: "reasoning",
    text: "I'm not sure this example quite works. Saying \"good luck\" could still be genuine encouragement. What exactly makes something pity rather than kindness? Try tightening that distinction first."
  },
  {
    id: "interpretation",
    text: "How do we know this for sure? I think you need some evidence here. If the book doesn't clearly tell us what Summer is thinking, you could say her actions seem motivated by pity at first rather than stating it as a fact."
  },
  {
    id: "analysis",
    text: "Good — now explain what changed. Why is this different from simply feeling sorry for him? What shows that Summer actually sees August as a friend?"
  },
  {
    id: "big-picture",
    text: "This might actually be your strongest idea. I'd bring more of this into the introduction. Why do you think Palacio wants readers to see the difference between pity and genuine respect?"
  }
];

export const wonderHomepageCommentIds: WonderFeedbackId[] = [
  "thesis",
  "evidence",
  "reasoning",
  "interpretation",
  "analysis"
];

export const wonderHomepageComments = wonderHomepageCommentIds.map((id) => {
  const comment = wonderComments.find((item) => item.id === id);
  if (!comment) throw new Error(`Missing Wonder feedback comment: ${id}`);
  return comment;
});

export const wonderEssayExcerpts: EssayExcerpt[] = [
  {
    id: "opening",
    segments: [
      { text: "Throughout the novel " },
      { text: "Wonder", italic: true },
      { text: ", August is treated in a variety of ways, whether it is cruelty, pity, or genuine respect. These reactions can show how someone truly feels about August —for example when Julian showed his cruel personality, making jokes about August's face. The novel shows the different ways of treating a person who appears different, and " },
      {
        text: "this essay will focus on analyzing each of these ways of treating a new person.",
        commentId: "thesis",
        mobileCommentAfter: "thesis"
      }
    ]
  },
  {
    id: "cruelty",
    segments: [
      { text: "Out of the many different ways, the majority of the characters treat August with cruelty or, like Julian. " },
      {
        text: "They show this by constantly avoiding him, making jokes about him, or talking bad behind his back.",
        commentId: "evidence",
        mobileCommentAfter: "evidence"
      },
      { text: " This is not a very respectful way to treat someone—since doing this would hurt others' feelings. The individuals who treat August with cruelty are looking at him the same way the rich used to look at the poor in the olden times; not caring a single bit about him. This would definitely not be a very respectful way to treat a person who is already struggling to adapt to the new environment." }
    ]
  },
  {
    id: "pity",
    segments: [
      { text: "Pity however, is actually feeling bad for someone, unlike cruelty, where they don't care about the 'victim'. However, pity is not true kindness; instead, it's helping someone because you feel bad for them, not necessarily because you want to help them. Think of it like this: You have a friend struggling with studying for a test, and " },
      {
        text: "you say 'Good luck' but not actually helping them directly. This is not an example of showing kindness, this is an example of pity.",
        commentId: "reasoning",
        mobileCommentAfter: "reasoning"
      },
      { text: " This can be helpful for helping someone who is struggling, but not directly helpful. In August's case, " },
      { text: "Summer initially was only feeling a sense of pity", commentId: "interpretation" },
      { text: ", because August was just sitting alone, quietly.", mobileCommentAfter: "interpretation" }
    ]
  },
  {
    id: "respect",
    segments: [
      { text: "Finally, genuine respect is when someone truly cares about another individual. This was shown in the novel when " },
      {
        text: "summer began hanging out with August more; asking what had happened when he was gone, and helping him in tough situations.",
        commentId: "analysis",
        mobileCommentAfter: "analysis"
      },
      { text: " This is true kindness, when you deeply care about another person. This is almost identical to treating your best friend." }
    ]
  },
  {
    id: "conclusion",
    segments: [
      { text: "In conclusion, Palacio distinguishes genuine kindness from pity and social obligation by showing the differences such as cruelty is not caring about another's feelings, pity is feeling bad for someone but not truly caring for them, and genuine kindness is caring and helping another in any situation." }
    ]
  }
];
