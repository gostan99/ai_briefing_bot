import dayjs from "dayjs";
import { VideoStatus } from "../types";

interface Props {
  video: VideoStatus | null;
  onClose: () => void;
}

export function VideoDetail({ video, onClose }: Props) {
  if (!video) return null;

  return (
    <div className="detail-overlay" onClick={onClose}>
      <div className="detail-card" onClick={(e) => e.stopPropagation()}>
        <div className="detail-header">
          <h2>{video.title}</h2>
          <button onClick={onClose} className="close-button">
            ×
          </button>
        </div>
        <div className="detail-meta">
          <div><strong>Channel:</strong> {video.channel ?? "Unknown"}</div>
          <div>
            <strong>Published:</strong>{" "}
            {video.published_at ? dayjs(video.published_at).format("YYYY-MM-DD HH:mm") : "Unknown"}
          </div>
          <div>
            <strong>Transcript status:</strong> {video.transcript_status} (retries: {video.transcript_retries})
          </div>
          {video.transcript_last_error && (
            <div className="warning">Last transcript error: {video.transcript_last_error}</div>
          )}
        </div>

        <section>
          <h3>Summary</h3>
          <p>{video.summary.tl_dr ?? "Pending"}</p>
          {video.summary.highlights.length > 0 && (
            <ul>
              {video.summary.highlights.map((highlight, idx) => (
                <li key={idx}>{highlight}</li>
              ))}
            </ul>
          )}
          {video.summary.key_quote && (
            <blockquote>“{video.summary.key_quote}”</blockquote>
          )}
          {video.summary.last_error && (
            <div className="warning">LLM error: {video.summary.last_error}</div>
          )}
        </section>

        <section>
          <h3>Metadata</h3>
          <div className="tag-group">
            <strong>Tags:</strong>
            {video.metadata.tags.length ? (
              video.metadata.tags.map((tag) => (
                <span className="chip" key={tag}>{tag}</span>
              ))
            ) : (
              <span className="muted">None</span>
            )}
          </div>
          <div className="tag-group">
            <strong>Hashtags:</strong>
            {video.metadata.hashtags.length ? (
              video.metadata.hashtags.map((tag) => (
                <span className="chip" key={tag}>{tag}</span>
              ))
            ) : (
              <span className="muted">None</span>
            )}
          </div>
          {video.metadata.sponsors.length ? (
            <div className="tag-group">
              <strong>Sponsors:</strong>
              {video.metadata.sponsors.map((sponsor, idx) => (
                <span className="chip chip-warning" key={idx}>{sponsor}</span>
              ))}
            </div>
          ) : null}
          {video.metadata.urls.length ? (
            <div className="tag-group">
              <strong>URLs:</strong>
              {video.metadata.urls.map((url) => (
                <a key={url} href={url} target="_blank" rel="noreferrer" className="chip chip-link">
                  {url}
                </a>
              ))}
            </div>
          ) : null}
          <p className="muted small">
            Status: {video.metadata.status}
            {video.metadata.last_error ? ` (last error: ${video.metadata.last_error})` : ""}
          </p>
          {video.metadata_clean_description && (
            <details>
              <summary>Cleaned description</summary>
              <pre>{video.metadata_clean_description}</pre>
            </details>
          )}
        </section>

        {video.transcript_text && (
          <section>
            <h3>Transcript (first 1,000 chars)</h3>
            <pre>{video.transcript_text.slice(0, 1000)}</pre>
          </section>
        )}
      </div>
    </div>
  );
}
