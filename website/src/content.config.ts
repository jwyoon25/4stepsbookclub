import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

const noticeImagePath = z.string().transform((path) =>
  path.startsWith("images/notices/") ? `/${path}` : path
);

const notices = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/notices" }),
  schema: z.object({
    title: z.string().min(1),
    postedAt: z.coerce.date(),
    images: z.array(noticeImagePath).default([])
  })
});

export const collections = { notices };
