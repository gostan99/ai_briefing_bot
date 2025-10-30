export interface MetadataSnapshot {
  status: string;
  tags: string[];
  hashtags: string[];
  sponsors: string[];
  urls: string[];
  fetched_at: string | null;
  last_error: string | null;
}

export interface SummarySnapshot {
  status: string;
  tl_dr: string | null;
  highlights: string[];
  key_quote: string | null;
  ready_at: string | null;
  last_error: string | null;
}

export interface VideoStatus {
  video_id: string;
  title: string;
  channel: string | null;
  published_at: string | null;
  transcript_status: string;
  transcript_retries: number;
  transcript_last_error: string | null;
  metadata: MetadataSnapshot;
  summary: SummarySnapshot;
  created_at: string;
  description?: string | null;
  transcript_text?: string | null;
  metadata_clean_description?: string | null;
  summary_highlights_raw?: string | null;
}
