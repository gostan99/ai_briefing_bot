import { useEffect, useMemo, useState } from "react";
import dayjs from "dayjs";
import { deleteVideo as deleteVideoApi, fetchVideoDetail, fetchVideos } from "./api";
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

  const handleDelete = async (videoId: string) => {
    try {
      await deleteVideoApi(videoId);
      setVideos((prev) => prev.filter((video) => video.video_id !== videoId));
      setSelectedVideo(null);
    } catch (err) {
      console.error(err);
      alert("Failed to delete video. Check server logs.");
    }
  };

  const filtered = useMemo(() => {
    if (filter === "all") return videos;
    return videos.filter((video) => video.summary.status.toLowerCase() === filter);
  }, [videos, filter]);

  const handleSelect = async (video: VideoStatus) => {
    setSelectedVideo(video);
    try {
      const detail = await fetchVideoDetail(video.video_id);
      setSelectedVideo(detail);
    } catch (err) {
      console.error(err);
    }
  };

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

      <VideoTable videos={filtered} onSelect={handleSelect} onDelete={handleDelete} />
      <VideoDetail video={selectedVideo} onClose={() => setSelectedVideo(null)} onDelete={handleDelete} />
    </div>
  );
}
