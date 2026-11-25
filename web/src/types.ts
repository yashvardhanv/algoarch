// Lesson Document schema v1. Pure data: the frontend decides how to present it.
export type Inline =
  | string
  | { t: 'br' }
  | { t: 'link'; href: string; c: Inline[] }
  | { t: 'strong' | 'em' | 'code' | 'kbd' | 'quote' | 'phrase' | 'sub' | 'sup'; c: Inline[] };

import type { DiagramScene } from './Diagram';

export interface ListItem { content: Inline[]; children: ListBlock[] }
export interface ListBlock { type: 'list'; ordered: boolean; items: ListItem[] }

export type Block =
  | { type: 'paragraph'; content: Inline[] }
  | { type: 'heading'; level: 3 | 4; content: Inline[] }
  | ListBlock
  | { type: 'code'; text: string; tone: 'good' | 'bad' | null; diagram?: boolean }
  | { type: 'table'; head: Inline[][] | null; rows: Inline[][][] }
  | { type: 'callout'; tone: 'warning' | 'danger' | 'info' | 'success'; label: string | null; blocks: Block[] }
  | { type: 'say'; label: string | null; content: Inline[] }
  | { type: 'quote'; content: Inline[] }
  | { type: 'card'; tone: 'neutral' | 'positive' | 'negative'; title: string | null; blocks: Block[] }
  | { type: 'qa'; summary: Inline[]; blocks: Block[] }
  | { type: 'diagram'; id: number; title: string | null; caption: string | null; scene: DiagramScene }
  | { type: 'code_cell'; title: string; badge?: string | null; language: string; starter: string; tests?: string }
  | { type: 'widget'; kind: string; title: string | null; description: string | null; blocks: Block[]; ported: boolean; data?: any; archetype?: string; inputs?: { ranges: number; selects: number; buttons: number; texts: number } | null };

export interface Section { anchor: string; number: string | null; title: string; subtitle: string | null; blocks: Block[] }
export interface LessonDocument { schemaVersion: number; title: string | null; lede: Inline[]; sections: Section[] }

export interface LessonMeta {
  n: string; id: string; title: string; stars: number; desc: string; duration: string;
  tags: string[]; companies: string[]; isNew: boolean; lab?: string; hasDocument: boolean;
  prereqs?: string[]; objectives?: string[]; level?: 'mid' | 'senior' | 'staff'; reviewedAt?: string;
  sources?: { title: string; url: string; accessed: string }[];
}
export interface PathwayLesson { id: string; title: string; trackId: string; duration: string; note?: string }
export interface Pathway {
  id: string; title: string; description: string; kind: 'horizon' | 'goal' | 'level'; minutes: number; lessons: PathwayLesson[];
}
export interface Video { id: string; youtubeId: string; title: string; channel: string; duration: string; description: string; thumbnail?: string }
export interface Article { title: string; org?: string; readTime?: string; description?: string; url?: string; link?: string }
export interface Repo { name: string; description?: string; language?: string; stars?: string; url?: string; link?: string }
export interface NavLesson { id: string; title: string; trackId: string }

export interface LessonPayload {
  lesson: LessonMeta;
  track: { id: string; name: string; color: string } | null;
  guide: string;
  document: LessonDocument | null;
  lab: { fileName: string; code: string } | null;
  videos: Video[];
  articles: Article[];
  repos: Repo[];
  drills: { title: string; notes: string }[];
  prev: NavLesson | null;
  next: NavLesson | null;
}

// Bridge to the host page (the existing vanilla shell).
export interface ReaderHost {
  lessonId: string;
  isCompleted: () => boolean;
  isBookmarked: () => boolean;
  onToggleComplete: (id: string) => void;
  onToggleBookmark: (id: string) => void;
  onAskMentor: () => void;
  onBack: () => void;
  onNavigate: (id: string, trackId: string) => void;
  can: (feature: string) => boolean;
  openPricing: () => void;
}
