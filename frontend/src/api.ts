import axios from "axios";
import { VideoStatus } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export async function fetchVideos(limit = 50): Promise<VideoStatus[]> {
  const response = await axios.get<VideoStatus[]>(`${API_BASE}/videos`, {
    params: { limit },
  });
  return response.data;
}

export async function fetchVideoDetail(videoId: string): Promise<VideoStatus> {
  const response = await axios.get<VideoStatus>(`${API_BASE}/videos/${videoId}`);
  return response.data;
}

export async function deleteVideo(videoId: string): Promise<void> {
  await axios.delete(`${API_BASE}/videos/${videoId}`);
}
