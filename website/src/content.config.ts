import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

const notices = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/notices" }),
  schema: z.object({
    title: z.string().min(1),
    postedAt: z.coerce.date(),
    images: z.array(z.string()).default([])
  })
});

export const collections = { notices };
