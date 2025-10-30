import { FormEvent, useEffect, useState } from "react";
import axios from "axios";
import { addChannel, fetchChannels, removeChannel } from "../api";
import type { ChannelInfo } from "../types";

export function ChannelManager() {
  const [channels, setChannels] = useState<ChannelInfo[]>([]);
  const [identifier, setIdentifier] = useState("");
  const [loading, setLoading] = useState(false);
  const [info, setInfo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadChannels();
  }, []);

  const loadChannels = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchChannels();
      setChannels(result);
    } catch (err) {
      console.error(err);
      setError("Unable to load tracked channels. Is the API running?");
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = identifier.trim();
    if (!value) {
      setError("Provide a channel handle, URL, or UC identifier.");
      return;
    }
    setLoading(true);
    setError(null);
    setInfo(null);
    try {
      const channel = await addChannel(value);
      setChannels((prev) => {
        const exists = prev.some((item) => item.external_id === channel.external_id);
        if (exists) {
          return prev.map((item) =>
            item.external_id === channel.external_id ? channel : item
          );
        }
        return [channel, ...prev];
      });
      setIdentifier("");
      setInfo(`Tracking ${channel.external_id}.`);
    } catch (err) {
      console.error(err);
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Unable to add that channel.");
      } else {
        setError("Unable to add that channel.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleRemove = async (channelId: string) => {
    setLoading(true);
    setError(null);
    setInfo(null);
    try {
      await removeChannel(channelId);
      setChannels((prev) => prev.filter((channel) => channel.external_id !== channelId));
      setInfo(`Stopped tracking ${channelId}.`);
    } catch (err) {
      console.error(err);
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Unable to remove that channel.");
      } else {
        setError("Unable to remove that channel.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="channel-card">
      <h2>Tracked Channels</h2>
      <p className="muted small">
        Add YouTube channels to monitor. We'll subscribe via WebSub and process new uploads automatically.
      </p>

      <form className="channel-form" onSubmit={handleAdd}>
        <label htmlFor="channel-identifier">Channel identifier</label>
        <input
          id="channel-identifier"
          type="text"
          placeholder="@handle or UC..."
          value={identifier}
          onChange={(event) => setIdentifier(event.target.value)}
        />
        <button type="submit" disabled={loading}>
          Add channel
        </button>
        <button type="button" onClick={() => void loadChannels()} disabled={loading}>
          Refresh
        </button>
      </form>

      {info && <p className="info">{info}</p>}
      {error && <p className="warning">{error}</p>}
      {loading && <p className="muted small">Working…</p>}

      <div className="channel-list">
        {channels.length === 0 ? (
          <span className="muted">No channels tracked yet.</span>
        ) : (
          channels.map((channel) => (
            <span key={channel.external_id} className="channel-pill">
              <span>
                <strong>{channel.external_id}</strong>
                {channel.title && channel.title !== channel.external_id ? ` – ${channel.title}` : ""}
              </span>
              <button type="button" onClick={() => handleRemove(channel.external_id)} disabled={loading}>
                ×
              </button>
            </span>
          ))
        )}
      </div>
    </section>
  );
}
