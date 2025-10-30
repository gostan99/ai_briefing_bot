import { useEffect, useMemo, useState } from "react";
import dayjs from "dayjs";
import { fetchVideos } from "./api";
import { VideoStatus } from "./types";
import { VideoTable } from "./components/VideoTable";
import { VideoDetail } from "./components/VideoDetail";

const STATUS_FILTERS = ["all", "pending", "ready", "failed"] as const;

type StatusFilter = (typeof STATUS_FILTERS)[number];

export default function App() {
  const [videos, setVideos] = useState<VideoStatus[]>([]);
  const [selectedVideo, setSelectedVideo] = useState<VideoStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<StatusFilter>("all");

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        const response = await fetchVideos();
        setVideos(response);
        setError(null);
      } catch (err) {
        console.error(err);
        setError("Unable to load videos. Is the API running on port 8000?");
      } finally {
        setLoading(false);
      }
    };

    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  const filtered = useMemo(() => {
    if (filter === "all") return videos;
    return videos.filter((video) => video.summary.status.toLowerCase() === filter);
  }, [videos, filter]);

  return (
    <div className="app">
      <header>
        <h1>AI Briefing Bot – Pipeline Dashboard</h1>
        <p className="muted">
          Monitoring transcript, metadata, and summary stages. Last refresh: {dayjs().format("HH:mm:ss")}.
        </p>
      </header>

      <section className="controls">
        <div className="filter-group">
          <label htmlFor="filter">Summary status:</label>
          <select
            id="filter"
            value={filter}
            onChange={(e) => setFilter(e.target.value as StatusFilter)}
          >
            {STATUS_FILTERS.map((value) => (
              <option key={value} value={value}>
                {value.toUpperCase()}
              </option>
            ))}
          </select>
        </div>
        {error && <span className="warning">{error}</span>}
        {loading && <span className="muted">Refreshing…</span>}
      </section>

      <VideoTable videos={filtered} onSelect={setSelectedVideo} />
      <VideoDetail video={selectedVideo} onClose={() => setSelectedVideo(null)} />
    </div>
  );
}
