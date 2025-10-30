import axios from "axios";
import { ChannelInfo, VideoStatus } from "./types";

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

export async function fetchChannels(): Promise<ChannelInfo[]> {
  const response = await axios.get<{ channels: ChannelInfo[] }>(`${API_BASE}/channels`);
  return response.data.channels;
}

export async function addChannel(identifier: string): Promise<ChannelInfo> {
  const response = await axios.post<ChannelInfo>(`${API_BASE}/channels`, {
    identifier,
  });
  return response.data;
}

export async function removeChannel(identifier: string): Promise<ChannelInfo> {
  const response = await axios.delete<ChannelInfo>(
    `${API_BASE}/channels/${encodeURIComponent(identifier)}`
  );
  return response.data;
}
