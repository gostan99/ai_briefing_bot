import React from "react";
interface Props {
  videoId: string;
  onDelete: (videoId: string) => Promise<void>;
}

export function DeleteButton({ videoId, onDelete }: Props) {
  const handleClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (confirm(`Delete video ${videoId}? This removes transcript, metadata, and summary records.`)) {
      onDelete(videoId).catch((err) => console.error(err));
    }
  };

  return (
    <button onClick={handleClick} className="delete-button">
      Delete
    </button>
  );
}
