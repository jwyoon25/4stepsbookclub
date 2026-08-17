import type { CollectionEntry } from "astro:content";

export type NoticeEntry = CollectionEntry<"notices">;

export function sortNotices(notices: NoticeEntry[]) {
  return [...notices].sort(
    (left, right) => right.data.postedAt.getTime() - left.data.postedAt.getTime()
  );
}

export function formatNoticeDate(value: Date) {
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "long",
    day: "numeric"
  }).format(value);
}

export function noticeImageAlt(title: string, index: number) {
  return `${title} 안내 이미지 ${index + 1}`;
}
